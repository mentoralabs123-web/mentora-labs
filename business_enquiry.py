"""Business (IT services) enquiries: validation, storage and table setup.

Kept separate from the student ``orders`` table on purpose: these are a different
kind of record (a business asking for a website/app) and the future admin
dashboard will manage them with a status and internal notes.

Everything here is additive and safe to run on every start-up:
* the table and indexes use ``IF NOT EXISTS``; nothing existing is touched,
* all queries are parameterized,
* works on SQLite (local) and PostgreSQL (``DATABASE_URL``) through the same
  ``?`` placeholder convention used by ``project_service``.

Stored values
-------------
``service`` and ``budget`` are stored as stable codes (see ``SERVICES`` and
``BUDGETS``); use ``SERVICE_LABELS`` / ``BUDGET_LABELS`` to show them.
``status`` is stored as the exact words in ``STATUSES`` and defaults to ``New``.
``created_at`` / ``updated_at`` are ISO-8601 UTC text, like the other tables.
"""
import hashlib
import hmac
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone

import project_service as _ps

# ---------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------

SERVICES = [
    ("website-design", "Website Design"),
    ("website-development", "Website Development"),
    ("web-application-development", "Web Application Development"),
    ("application-development", "Application Development"),
    ("ui-ux-design", "UI/UX Design"),
    ("custom-software", "Custom Software Development"),
    ("other", "Other / Custom Digital Solution"),
]
SERVICE_LABELS = dict(SERVICES)

# Ranges are in Indian rupees. The two non-range answers keep budget optional.
BUDGETS = [
    ("undecided", "Not decided yet"),
    ("discuss", "Prefer to discuss"),
    ("under-25k", "Under ₹25,000"),
    ("25k-75k", "₹25,000 – ₹75,000"),
    ("75k-2l", "₹75,000 – ₹2,00,000"),
    ("2l-5l", "₹2,00,000 – ₹5,00,000"),
    ("over-5l", "Above ₹5,00,000"),
]
BUDGET_LABELS = dict(BUDGETS)

STATUSES = ["New", "Contacted", "In Progress", "Completed", "Closed"]
DEFAULT_STATUS = "New"

# Which IT Services page CTA (``?cta=``) maps to which service. Anything not in
# SERVICE_LABELS is ignored, so a crafted link cannot select an invalid value.
CTA_SERVICE = {
    "hero-discuss": "other",
    "cta-discuss": "other",
    "cta-website": "website-development",
    "cta-application": "application-development",
}

# ---------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------

MIN_NAME, MAX_NAME = 2, 100
MAX_EMAIL = 254
MAX_PHONE = 30
MAX_BUSINESS = 150
MIN_DESCRIPTION, MAX_DESCRIPTION = 10, 2000
MAX_LINKS = 5
MAX_SOURCE = 40

RATE_LIMIT_PER_HOUR = 5       # accepted enquiries per client per hour
DUPLICATE_WINDOW_HOURS = 24   # identical enquiry inside this window is not stored twice

_EMAIL_RE = re.compile(r"^[^@\s,;<>()\[\]\\\"]+@[^@\s,;<>()\[\]\\\"]+\.[^@\s,;<>()\[\]\\\"]{2,}$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s().\-]*$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-]{16,64}$")
_SOURCE_RE = re.compile(r"^[a-z0-9\-]{1,%d}$" % MAX_SOURCE)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_LINK_RE = re.compile(r"(?:https?://|www\.)", re.I)


# ---------------------------------------------------------------------
# Cleaning + validation (pure functions: no database, easy to test)
# ---------------------------------------------------------------------

def _clean_line(value):
    """Single-line text: NFC, control/bidi characters removed, whitespace collapsed."""
    value = unicodedata.normalize("NFC", str(value or ""))
    value = _CONTROL_RE.sub("", value)
    return re.sub(r"\s+", " ", value).strip()


def _clean_text(value):
    """Multi-line text: like ``_clean_line`` but keeps line breaks (max one blank line)."""
    value = unicodedata.normalize("NFC", str(value or "")).replace("\r\n", "\n").replace("\r", "\n")
    value = _CONTROL_RE.sub("", value)
    lines = [re.sub(r"[ \t\f\v]+", " ", ln).strip() for ln in value.split("\n")]
    value = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def clean_email(value):
    """Trim and lower-case the domain part (the local part is left as typed)."""
    value = _clean_line(value)
    if "@" in value:
        local, _, domain = value.rpartition("@")
        value = f"{local}@{domain.lower()}"
    return value


def phone_digits(value):
    return re.sub(r"\D", "", value or "")


def clean_form(raw):
    """Normalize raw form values (anything missing becomes an empty string)."""
    get = lambda k: raw.get(k, "") if hasattr(raw, "get") else ""  # noqa: E731
    return {
        "name": _clean_line(get("name")),
        "email": clean_email(get("email")),
        "phone": _clean_line(get("phone")),
        "business_name": _clean_line(get("business_name")),
        "service": _clean_line(get("service")),
        "project_description": _clean_text(get("project_description")),
        "budget": _clean_line(get("budget")),
        "source": _clean_line(get("source")).lower(),
        "submission_token": _clean_line(get("submission_token")),
    }


def validate(values):
    """Return ``{field: message}`` for everything wrong with cleaned ``values``.

    The ``contact`` key is used when neither an email nor a phone number was given.
    """
    errors = {}

    name = values["name"]
    if not name:
        errors["name"] = "Please enter your name."
    elif len(name) < MIN_NAME:
        errors["name"] = f"Your name should be at least {MIN_NAME} characters."
    elif len(name) > MAX_NAME:
        errors["name"] = f"Please keep your name under {MAX_NAME} characters."
    elif not re.search(r"[^\W\d_]", name):
        errors["name"] = "Please enter your name using letters."

    email, phone = values["email"], values["phone"]
    if not email and not phone:
        errors["contact"] = "Please give us an email address or a phone number so we can reach you."
    if email:
        if len(email) > MAX_EMAIL:
            errors["email"] = "That email address is too long."
        elif not _EMAIL_RE.match(email):
            errors["email"] = "Please enter a valid email address, for example name@example.com."
    if phone:
        digits = phone_digits(phone)
        if len(phone) > MAX_PHONE:
            errors["phone"] = "That phone number is too long."
        elif not _PHONE_RE.match(phone) or not 7 <= len(digits) <= 15:
            errors["phone"] = "Please enter a valid phone number. Include the country code if it is outside India."

    if len(values["business_name"]) > MAX_BUSINESS:
        errors["business_name"] = f"Please keep this under {MAX_BUSINESS} characters."

    if values["service"] not in SERVICE_LABELS:
        errors["service"] = "Please choose the service you are interested in."

    desc = values["project_description"]
    if not desc:
        errors["project_description"] = "Please describe what you need."
    elif len(desc) < MIN_DESCRIPTION:
        errors["project_description"] = f"Please add a little more detail (at least {MIN_DESCRIPTION} characters)."
    elif len(desc) > MAX_DESCRIPTION:
        errors["project_description"] = f"Please keep this under {MAX_DESCRIPTION:,} characters."
    elif len(_LINK_RE.findall(desc)) > MAX_LINKS:
        errors["project_description"] = f"Please include no more than {MAX_LINKS} links."

    if values["budget"] and values["budget"] not in BUDGET_LABELS:
        errors["budget"] = "Please choose one of the budget options, or leave it blank."

    return errors


def normalize_source(value):
    value = _clean_line(value).lower()
    return value if _SOURCE_RE.match(value) else None


def service_for_cta(cta):
    """Service code a CTA key preselects, or ``None``."""
    code = CTA_SERVICE.get(_clean_line(cta).lower())
    return code if code in SERVICE_LABELS else None


def service_code(value):
    """``value`` if it is a valid service code, else ``None`` (for ?service= preselection)."""
    value = _clean_line(value).lower()
    return value if value in SERVICE_LABELS else None


def new_submission_token():
    return secrets.token_urlsafe(18)


def valid_submission_token(token):
    return bool(_TOKEN_RE.match(token or ""))


def fingerprint(values):
    """Stable hash of the enquiry's substance, used to spot an identical re-submission."""
    contact = (values["email"] or "").lower() + "|" + phone_digits(values["phone"])
    body = re.sub(r"\s+", " ", values["project_description"]).lower()
    raw = "\x1f".join([contact, values["service"], body])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def client_hash(secret, ip):
    """Keyed hash of the client IP: lets us rate-limit without storing the address itself."""
    key = secret if isinstance(secret, bytes) else str(secret).encode("utf-8")
    return hmac.new(key, (ip or "unknown").encode("utf-8"), hashlib.sha256).hexdigest()[:32]


# ---------------------------------------------------------------------
# Schema (additive, idempotent)
# ---------------------------------------------------------------------

MIGRATION = "business_enquiries_v1"


def _ddl(is_pg):
    pk = "BIGSERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    return [
        f"""CREATE TABLE IF NOT EXISTS business_enquiries (
            id {pk},
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            business_name TEXT,
            service TEXT NOT NULL,
            project_description TEXT NOT NULL,
            budget TEXT,
            status TEXT NOT NULL DEFAULT 'New',
            admin_notes TEXT,
            source TEXT,
            submission_token TEXT UNIQUE,
            fingerprint TEXT,
            client_hash TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS idx_business_enquiries_created ON business_enquiries (created_at)",
        "CREATE INDEX IF NOT EXISTS idx_business_enquiries_status ON business_enquiries (status)",
        "CREATE INDEX IF NOT EXISTS idx_business_enquiries_client ON business_enquiries (client_hash, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_business_enquiries_fingerprint ON business_enquiries (fingerprint)",
    ]


def init_table(db):
    """Create the table/indexes if missing. Safe to call on every start-up and from several workers."""
    for attempt in (1, 2):
        try:
            for statement in _ddl(_ps._is_pg(db)):
                db.execute(statement)
            db.commit()
            break
        except Exception:
            db.rollback()  # e.g. two workers creating the table at the same moment
            if attempt == 2:
                raise
    # Record the migration like project_schema does (the table is created above regardless).
    try:
        _ps._execute(db, "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        if not _ps._fetch(db, "SELECT name FROM schema_migrations WHERE name = ?", (MIGRATION,)):
            _ps._execute(
                db, "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                (MIGRATION, _now()),
            )
        db.commit()
    except Exception:
        db.rollback()  # marker already written by another worker


# ---------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc).isoformat()


def _cutoff(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def recent_count(db, client):
    """Enquiries accepted from this client hash in the last hour."""
    rows = _ps._fetch(
        db, "SELECT COUNT(*) AS n FROM business_enquiries WHERE client_hash = ? AND created_at >= ?",
        (client, _cutoff(1)),
    )
    return int(rows[0]["n"]) if rows else 0


def find_by_token(db, token):
    rows = _ps._fetch(db, "SELECT id, fingerprint FROM business_enquiries WHERE submission_token = ?", (token,))
    return rows[0] if rows else None


def find_duplicate(db, fp):
    rows = _ps._fetch(
        db, "SELECT id FROM business_enquiries WHERE fingerprint = ? AND created_at >= ? ORDER BY id DESC",
        (fp, _cutoff(DUPLICATE_WINDOW_HOURS)),
    )
    return rows[0]["id"] if rows else None


def create(db, values, client=None):
    """Store a validated enquiry. Returns ``(id, created)``.

    ``created`` is False when the same submission was already stored (same form
    token, or an identical enquiry in the last 24 hours): the earlier row's id is
    returned and nothing new is written. Raises on database errors; the caller
    decides what the visitor sees.
    """
    fp = fingerprint(values)
    token = values.get("submission_token") or None
    if token and not valid_submission_token(token):
        token = None

    if token:
        existing = find_by_token(db, token)
        if existing:
            if existing["fingerprint"] == fp:
                return existing["id"], False
            token = new_submission_token()  # same form re-used with different content: store as new
    dup = find_duplicate(db, fp)
    if dup:
        return dup, False

    now = _now()
    params = (
        values["name"], values["email"] or None, values["phone"] or None,
        values["business_name"] or None, values["service"], values["project_description"],
        values["budget"] or None, DEFAULT_STATUS, normalize_source(values.get("source", "")),
        token, fp, client, now, now,
    )
    sql = (
        "INSERT INTO business_enquiries (name, email, phone, business_name, service, project_description, "
        "budget, status, source, submission_token, fingerprint, client_hash, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    try:
        if _ps._is_pg(db):
            row = _ps._execute(db, sql + " RETURNING id", params).fetchone()
            new_id = row["id"] if isinstance(row, dict) else row[0]
        else:
            new_id = _ps._execute(db, sql, params).lastrowid
        db.commit()
        return new_id, True
    except Exception:
        db.rollback()
        # Two identical requests racing: the unique token means the other one won.
        if token:
            existing = find_by_token(db, token)
            if existing:
                return existing["id"], False
        raise
