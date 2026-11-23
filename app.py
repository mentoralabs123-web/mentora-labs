import hmac
import os
import secrets
import sqlite3
import smtplib
import threading
import time
import os.path
from collections import deque
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import Flask, render_template, request, jsonify, g, Response, url_for, session, redirect, make_response
from werkzeug.middleware.proxy_fix import ProxyFix
import psycopg
from psycopg.rows import dict_row

import business_enquiry as enquiry_svc
import project_schema
import project_service as projects_svc
from faq_content import FAQ_CATEGORIES

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "mentora.db")
DATABASE_URL = os.environ.get("DATABASE_URL")

ADMIN_USER = os.environ.get("ADMIN_USER", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or os.environ.get("ADMIN_PASS", "")


SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")  # where new-order alerts get sent


# ---------------------------------------------------------------------
# Session / security configuration
# ---------------------------------------------------------------------

def _load_secret_key():
    """Use an explicitly configured strong secret; never create a production fallback."""
    key = os.environ.get("SECRET_KEY", "")
    if len(key) >= 32:
        return key
    # Local development/test runs remain usable with a cryptographically strong,
    # process-local key. Production deployments fail closed in the request guard.
    if os.environ.get("RENDER") or os.environ.get("FLASK_ENV") == "production":
        return None
    app.logger.warning("SECRET_KEY is unset/short; using an ephemeral development key. Set SECRET_KEY before deployment.")
    return secrets.token_urlsafe(48)


app.secret_key = _load_secret_key()
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    SESSION_COOKIE_NAME="mentora_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(os.environ.get("RENDER") == "true"
                           or os.environ.get("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes")),
    SESSION_REFRESH_EACH_REQUEST=True,
    MAX_CONTENT_LENGTH=6 * 1024 * 1024,
)

# Behind Render's proxy the real client address is in X-Forwarded-For.
_PROXY_HOPS = int(os.environ.get("TRUSTED_PROXY_COUNT", "1" if os.environ.get("RENDER") else "0"))
if _PROXY_HOPS > 0:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=_PROXY_HOPS, x_proto=_PROXY_HOPS, x_host=0)

from werkzeug.security import check_password_hash, generate_password_hash

_ADMIN_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD) if ADMIN_PASSWORD else None
_LOGIN_ATTEMPTS = {}
_LOGIN_ATTEMPTS_LOCK = threading.Lock()
_LOGIN_LIMIT = 8
_LOGIN_WINDOW = 900


def _admin_configured():
    return bool(app.secret_key and ADMIN_USER and _ADMIN_PASSWORD_HASH)


def _admin_authenticated():
    return session.get("admin_authenticated") is True and session.get("admin_username") == ADMIN_USER


def _admin_csrf_token():
    token = session.get("admin_csrf")
    if not token:
        token = session["admin_csrf"] = secrets.token_urlsafe(32)
    return token


def _admin_csrf_valid():
    supplied = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("admin_csrf", "")
    return bool(supplied and expected) and hmac.compare_digest(supplied, expected)


def _admin_login_limited():
    now = time.monotonic()
    key = enquiry_svc.client_hash(app.secret_key or "unconfigured", request.remote_addr)
    with _LOGIN_ATTEMPTS_LOCK:
        hits = [t for t in _LOGIN_ATTEMPTS.get(key, []) if now - t < _LOGIN_WINDOW]
        _LOGIN_ATTEMPTS[key] = hits
        return len(hits) >= _LOGIN_LIMIT


def _record_admin_login_attempt():
    key = enquiry_svc.client_hash(app.secret_key or "unconfigured", request.remote_addr)
    with _LOGIN_ATTEMPTS_LOCK:
        _LOGIN_ATTEMPTS.setdefault(key, []).append(time.monotonic())


def requires_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _admin_authenticated():
            if request.method in ("GET", "HEAD"):
                return redirect(url_for("admin_entry", next=request.full_path.rstrip("?")))
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated


@app.before_request
def protect_admin_and_check_csrf():
    if request.path.startswith("/admin"):
        if not _admin_configured():
            return render_template("admin_config_error.html"), 503
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not _admin_csrf_valid():
            return jsonify({"error": "CSRF validation failed"}), 400


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.path.startswith("/admin"):
        response.headers["Cache-Control"] = "no-store"
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# ---------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------

def get_db():
    if "db" not in g:
        if DATABASE_URL:
            g.db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        else:
            g.db = sqlite3.connect(DB_PATH)
            g.db.row_factory = sqlite3.Row
    return g.db


def execute_query(db, query, params=()):
    if DATABASE_URL:
        query = query.replace("?", "%s")
    return db.execute(query, params)


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    if DATABASE_URL:
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        id_column = "BIGSERIAL PRIMARY KEY"
    else:
        conn = sqlite3.connect(DB_PATH)
        id_column = "INTEGER PRIMARY KEY AUTOINCREMENT"
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS orders (
            id {id_column},
            name TEXT NOT NULL,
            contact TEXT NOT NULL,
            track TEXT NOT NULL,
            message TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    # Projects tables + one-time migration of the original projects (additive, idempotent)
    project_schema.init_projects(conn)
    # Business enquiries table (additive, idempotent)
    enquiry_svc.init_table(conn)
    conn.close()


# ---------------------------------------------------------------------
# Optional email notification (only fires if SMTP env vars are set)
# ---------------------------------------------------------------------

def notify_new_order(order):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and NOTIFY_EMAIL):
        return  # email notifications not configured — order is still saved in the DB
    try:
        body = (
            f"New order on Mentora Labs\n\n"
            f"Name: {order['name']}\n"
            f"Contact: {order['contact']}\n"
            f"Track: {order['track']}\n"
            f"Message: {order['message'] or '(none)'}\n"
            f"Received: {order['created_at']}\n"
        )
        msg = MIMEText(body)
        msg["Subject"] = f"New Mentora Labs order — {order['track']}"
        msg["From"] = SMTP_USER
        msg["To"] = NOTIFY_EMAIL

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, [NOTIFY_EMAIL], msg.as_string())
    except Exception as e:
        # never let a notification failure break the order submission
        app.logger.warning(f"Email notification failed: {e}")


# ---------------------------------------------------------------------
# Routes — site
# ---------------------------------------------------------------------

CONTACT = {
    "phones": ["+91 74491 52395", "+91 76048 94278", "+91 88258 28406"],
    "whatsapp_number": "917449152395",
    "additional_whatsapp_number": "918825828406",
    "email": "mentoralabs123@gmail.com",
    "instagram": "https://www.instagram.com/mentora_labs.builds?stkn=MWk1bXdvdHVtcngwOQ==",
    "facebook": "https://www.facebook.com/share/1HTCs92zzT/",
    "whatsapp_channel": "https://whatsapp.com/channel/0029VbDPRqj4tRrzaQ6QRk1h",
    "telegram": "https://t.me/mentoralabs",
    "linkedin": "https://www.linkedin.com/in/mentora-labs-9b292943a",
    "google_review": "https://share.google/nfG1TgIeV6ZU2LZHu",
}


@app.route("/")
def index():
    return render_template("index.html")


# Learning paths shown on Home / Learning / Projects. Each project belongs to one
# path via its ``learning_group`` column in the projects table.
GROUPS = [
    {
        "key": "ml",
        "title": "Machine Learning",
        "icon": "cpu",
        "desc": "Build and train models for classification and prediction, from network security to healthcare and agriculture.",
    },
    {
        "key": "data",
        "title": "Data Science",
        "icon": "chart",
        "desc": "Work with real datasets using regression and Pandas to predict outcomes such as house prices and flight fares.",
    },
    {
        "key": "fullstack",
        "title": "Full-Stack Development",
        "icon": "code",
        "desc": "Build complete web apps with Flask, SQL and JavaScript, including trackers, task managers and quiz apps.",
    },
]


def load_published_projects():
    """Published projects for this request (cached on ``g``). [] if the DB is unavailable."""
    if "published_projects" not in g:
        try:
            g.published_projects = projects_svc.get_published_projects(get_db())
            g.projects_error = False
        except Exception:
            app.logger.exception("Could not load projects")
            try:
                get_db().rollback()
            except Exception:
                pass
            g.published_projects = []
            g.projects_error = True
    return g.published_projects


@app.context_processor
def inject_site_data():
    """Make shared site data available to every template.

    ``tracks`` keeps the shape Home/About/Learning/Services and the enquiry form
    already use, but is now built from published projects in the database.
    """
    tracks = [projects_svc.to_track(p) for p in load_published_projects()]
    return {"tracks": tracks, "groups": GROUPS, "contact": CONTACT}


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/services")
def services():
    return render_template("services.html")


@app.route("/projects")
def projects():
    """Public Projects page. Reads published projects from the database only."""
    projs = load_published_projects()
    showcase = [
        projects_svc.to_public_dict(
            p, static_dir=app.static_folder, static_url=lambda f: url_for("static", filename=f)
        )
        for p in projs
    ]
    # Filter buttons: only categories used by a published project, with counts.
    categories = []
    if projs:
        try:
            categories = [
                {"key": c["slug"], "label": c["name"], "count": c["project_count"]}
                for c in projects_svc.get_categories(get_db(), only_used=True, published_only=True)
            ]
        except Exception:
            app.logger.exception("Could not load project categories")
            get_db().rollback()
    return render_template(
        "projects.html", showcase=showcase, categories=categories, load_error=g.get("projects_error", False)
    )


@app.route("/learning")
def learning():
    return render_template("learning.html")


@app.route("/contact")
def contact_page():
    return render_template("contact.html")


@app.route("/reviews")
def reviews():
    return render_template("reviews.html")


@app.route("/faq")
def faq():
    """Public, searchable FAQ content; structured data mirrors visible questions."""
    faq_schema = [
        {"@type": "Question", "name": item["question"],
         "acceptedAnswer": {"@type": "Answer", "text": item["answer"]}}
        for category in FAQ_CATEGORIES for item in category["items"]
    ]
    return render_template("faq.html", faq_categories=FAQ_CATEGORIES, faq_schema=faq_schema,
                           faq_total=sum(len(category['items']) for category in FAQ_CATEGORIES))


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


@app.route("/api/orders", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    contact = (data.get("contact") or "").strip()
    track = (data.get("track") or "").strip()
    message = (data.get("message") or "").strip()

    if not name or not contact or not track:
        return jsonify({"error": "name, contact, and track are required"}), 400

    created_at = datetime.now(timezone.utc).isoformat()

    db = get_db()
    execute_query(
        db,
        "INSERT INTO orders (name, contact, track, message, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, contact, track, message, created_at),
    )
    db.commit()

    notify_new_order({
        "name": name, "contact": contact, "track": track,
        "message": message, "created_at": created_at,
    })

    return jsonify({"status": "ok"}), 201


# ---------------------------------------------------------------------
# Business (IT services) enquiries — separate from student orders
# ---------------------------------------------------------------------

MAX_ENQUIRY_BODY = 32 * 1024      # bytes; the form is a few KB at most
ATTEMPT_LIMIT = 20                # POST attempts per client per window (best-effort, per worker)
ATTEMPT_WINDOW = 600              # seconds
_attempts = {}
_attempts_lock = threading.Lock()


def _csrf_token():
    token = session.get("csrf")
    if not token:
        token = session["csrf"] = secrets.token_urlsafe(32)
    return token


def _csrf_ok():
    sent = request.form.get("csrf_token", "")
    expected = session.get("csrf", "")
    return bool(sent and expected) and hmac.compare_digest(sent, expected)


def _client_key():
    return enquiry_svc.client_hash(app.secret_key, request.remote_addr)


def _too_many_attempts(client):
    """Sliding-window limit on POSTs per client. In-memory, so per worker process: it slows
    bursts; the database-backed limit in the route is the one that holds across workers."""
    now = time.monotonic()
    with _attempts_lock:
        hits = _attempts.setdefault(client, deque())
        while hits and now - hits[0] > ATTEMPT_WINDOW:
            hits.popleft()
        hits.append(now)
        if len(_attempts) > 5000:  # keep memory bounded
            for key in [k for k, v in _attempts.items() if not v or now - v[-1] > ATTEMPT_WINDOW]:
                _attempts.pop(key, None)
        return len(hits) > ATTEMPT_LIMIT


def _render_enquiry(values, errors=None, form_error=None, status=200):
    values = dict(values)
    if not enquiry_svc.valid_submission_token(values.get("submission_token")):
        values["submission_token"] = enquiry_svc.new_submission_token()
    resp = make_response(render_template(
        "business_enquiry.html",
        values=values, errors=errors or {}, form_error=form_error, csrf_token=_csrf_token(),
        services=enquiry_svc.SERVICES, budgets=enquiry_svc.BUDGETS,
        limits={
            "name": enquiry_svc.MAX_NAME, "email": enquiry_svc.MAX_EMAIL, "phone": enquiry_svc.MAX_PHONE,
            "business": enquiry_svc.MAX_BUSINESS, "description": enquiry_svc.MAX_DESCRIPTION,
        },
    ), status)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/services/enquiry", methods=["GET", "POST"])
def business_enquiry():
    if request.method == "GET":
        session.pop("enquiry_submitted", None)
        values = enquiry_svc.clean_form({})
        # CTA preselection: ?service=<code> or ?cta=<button key>. Invalid values are ignored.
        values["service"] = (
            enquiry_svc.service_code(request.args.get("service"))
            or enquiry_svc.service_for_cta(request.args.get("cta"))
            or ""
        )
        values["source"] = enquiry_svc.normalize_source(request.args.get("cta", "")) or ""
        return _render_enquiry(values)

    values = enquiry_svc.clean_form(request.form)
    client = _client_key()

    if request.content_length and request.content_length > MAX_ENQUIRY_BODY:
        return _render_enquiry(values, form_error="That submission is too large. Please shorten your message and try again.", status=413)

    if _too_many_attempts(client):
        return _render_enquiry(values, form_error="Too many attempts in a short time. Please wait a few minutes and try again.", status=429)

    if not _csrf_ok():
        return _render_enquiry(
            values,
            form_error="We couldn't verify this form, possibly because the page was open for a long time or cookies are turned off. Please try sending it again.",
            status=400,
        )

    # Honeypot: real visitors never see or fill this field.
    if request.form.get("nickname_hp", "").strip():
        app.logger.info("Business enquiry rejected by honeypot")
        return _render_enquiry(values, form_error="We couldn't process this submission. Please try again.", status=400)

    errors = enquiry_svc.validate(values)
    if errors:
        return _render_enquiry(values, errors=errors, status=400)

    try:
        db = get_db()
        if enquiry_svc.recent_count(db, client) >= enquiry_svc.RATE_LIMIT_PER_HOUR:
            return _render_enquiry(values, form_error="You have sent several enquiries recently. Please wait a while before sending another, or contact us directly by phone, WhatsApp or email.", status=429)
        _enquiry_id, _created = enquiry_svc.create(db, values, client=client)
    except Exception:
        app.logger.exception("Could not store business enquiry")
        try:
            get_db().rollback()
        except Exception:
            pass
        return _render_enquiry(
            values,
            form_error="Sorry, something went wrong on our side and your enquiry was not sent. Your details are still in the form, so please try again in a moment, or contact us directly.",
            status=503,
        )

    session.pop("csrf", None)
    session["enquiry_submitted"] = {
        "first_name": values["name"].split(" ")[0][:50],
        "service": enquiry_svc.SERVICE_LABELS[values["service"]],
        "via_email": bool(values["email"]),
        "via_phone": bool(values["phone"]),
    }
    return redirect(url_for("business_enquiry_submitted"), code=303)


@app.route("/services/enquiry/submitted")
def business_enquiry_submitted():
    info = session.get("enquiry_submitted")
    if not info:
        return redirect(url_for("business_enquiry"))
    resp = make_response(render_template("business_enquiry_submitted.html", info=info))
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------------------------------------------------------------------
# Admin portal — protected management workspace (Task 5B)
# ---------------------------------------------------------------------

from werkzeug.utils import secure_filename

ADMIN_UPLOAD_MAX_BYTES = 5 * 1024 * 1024
ADMIN_UPLOAD_DIR = os.path.join(app.root_path, "static", projects_svc.IMAGE_DIR)
ADMIN_PAGE_SIZE = 20


def _admin_page(template, **context):
    context.setdefault("csrf_token", _admin_csrf_token())
    return render_template(template, **context)


def _admin_project_form_data():
    return {
        "title": request.form.get("title", ""),
        "short_description": request.form.get("short_description", ""),
        "description": request.form.get("description", ""),
        "problem_statement": request.form.get("problem_statement", ""),
        "objective": request.form.get("objective", ""),
        "implementation_details": request.form.get("implementation_details", ""),
        "technologies": request.form.get("technologies", ""),
        "categories": request.form.getlist("categories"),
        "domain_tag": request.form.get("domain_tag", ""),
        "learning_group": request.form.get("learning_group", ""),
        "project_url": request.form.get("project_url", ""),
        "featured": request.form.get("featured") == "1",
        "published": request.form.get("published") == "1",
        "display_order": request.form.get("display_order", ""),
    }


def _image_signature_ok(data, ext):
    if ext in (".jpg", ".jpeg"):
        return data.startswith(b"\xff\xd8\xff")
    if ext == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == ".gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if ext == ".webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def _save_project_upload(file_storage, slug_hint):
    if not file_storage or not file_storage.filename:
        return None
    original = secure_filename(file_storage.filename)
    ext = os.path.splitext(original)[1].lower()
    if ext not in projects_svc.ALLOWED_IMAGE_EXT:
        raise projects_svc.ValidationError({"image": "Use a JPG, PNG, WEBP, or GIF image."})
    raw = file_storage.stream.read(ADMIN_UPLOAD_MAX_BYTES + 1)
    if not raw or len(raw) > ADMIN_UPLOAD_MAX_BYTES:
        raise projects_svc.ValidationError({"image": "Image must be no larger than 5 MB."})
    if not _image_signature_ok(raw, ext):
        raise projects_svc.ValidationError({"image": "The file content does not match its image extension."})
    rel = projects_svc.make_image_path("upload" + ext, slug_hint)
    os.makedirs(ADMIN_UPLOAD_DIR, exist_ok=True)
    full = os.path.realpath(os.path.join(ADMIN_UPLOAD_DIR, os.path.basename(rel)))
    if not full.startswith(os.path.realpath(ADMIN_UPLOAD_DIR) + os.sep):
        raise projects_svc.ValidationError({"image": "Invalid upload destination."})
    with open(full, "xb") as out:
        out.write(raw)
    return rel


def _remove_unreferenced_image(path):
    if not projects_svc.is_safe_image_path(path) or not path.startswith(projects_svc.IMAGE_DIR + "/"):
        return
    db = get_db()
    refs = projects_svc._fetch(db, "SELECT id FROM projects WHERE image = ? OR gallery_images LIKE ?", (path, "%" + path + "%"))
    if refs:
        return
    full = os.path.realpath(os.path.join(ADMIN_UPLOAD_DIR, os.path.basename(path)))
    root = os.path.realpath(ADMIN_UPLOAD_DIR)
    if full.startswith(root + os.sep) and os.path.isfile(full):
        try:
            os.remove(full)
        except OSError:
            app.logger.warning("Could not remove unreferenced project image")


def _page_number():
    try:
        return max(1, int(request.args.get("page", "1")))
    except (TypeError, ValueError):
        return 1


@app.route("/admin", methods=["GET", "POST"])
def admin_entry():
    if _admin_authenticated():
        return redirect(url_for("admin_dashboard"))
    if request.method == "GET":
        return render_template("admin_login.html", csrf_token=_admin_csrf_token(), error=None)
    if _admin_login_limited():
        return render_template("admin_login.html", csrf_token=_admin_csrf_token(),
                               error="Too many sign-in attempts. Please wait and try again."), 429
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    valid = bool(username and password and hmac.compare_digest(username.casefold(), ADMIN_USER.casefold())
                 and _ADMIN_PASSWORD_HASH and check_password_hash(_ADMIN_PASSWORD_HASH, password))
    _record_admin_login_attempt()
    if not valid:
        return render_template("admin_login.html", csrf_token=_admin_csrf_token(),
                               error="The username or password is incorrect."), 401
    session.clear()
    session.permanent = True
    session["admin_authenticated"] = True
    session["admin_username"] = ADMIN_USER
    session["admin_csrf"] = secrets.token_urlsafe(32)
    destination = request.args.get("next", "")
    if not destination.startswith("/admin") or destination.startswith("//"):
        destination = url_for("admin_dashboard")
    return redirect(destination, code=303)


@app.route("/admin/logout", methods=["POST"])
@requires_admin
def admin_logout():
    session.clear()
    return redirect(url_for("admin_entry"), code=303)


@app.route("/admin/dashboard")
@requires_admin
def admin_dashboard():
    db = get_db()
    project_rows = projects_svc._fetch(db, "SELECT COUNT(*) AS total, SUM(CASE WHEN published=1 THEN 1 ELSE 0 END) AS published FROM projects")
    order_rows = projects_svc._fetch(db, "SELECT COUNT(*) AS total FROM orders")
    enquiry_rows = projects_svc._fetch(db, "SELECT COUNT(*) AS total FROM business_enquiries")
    stats = {
        "projects": int(project_rows[0]["total"] or 0),
        "published": int(project_rows[0]["published"] or 0),
        "unpublished": int(project_rows[0]["total"] or 0) - int(project_rows[0]["published"] or 0),
        "orders": int(order_rows[0]["total"] or 0),
        "enquiries": int(enquiry_rows[0]["total"] or 0),
    }
    recent_orders = projects_svc._fetch(db, "SELECT id,name,track,created_at FROM orders ORDER BY id DESC LIMIT 5")
    recent_enquiries = projects_svc._fetch(db, "SELECT id,name,service,status,created_at FROM business_enquiries ORDER BY id DESC LIMIT 5")
    return _admin_page("admin_dashboard.html", active="dashboard", stats=stats,
                       recent_orders=recent_orders, recent_enquiries=recent_enquiries)


@app.route("/admin/projects")
@requires_admin
def admin_projects_placeholder():
    db = get_db()
    q = (request.args.get("q") or "").strip()[:100]
    status = request.args.get("status", "all")
    rows = projects_svc.get_all_projects(db)
    if q:
        needle = q.casefold()
        rows = [p for p in rows if needle in p["title"].casefold() or needle in (p.get("short_description") or "").casefold()]
    if status == "published": rows = [p for p in rows if p["published"]]
    elif status == "unpublished": rows = [p for p in rows if not p["published"]]
    page = _page_number(); total = len(rows); pages = max(1, (total + ADMIN_PAGE_SIZE - 1) // ADMIN_PAGE_SIZE)
    rows = rows[(page - 1) * ADMIN_PAGE_SIZE:page * ADMIN_PAGE_SIZE]
    return _admin_page("admin_projects.html", active="projects", projects=rows, q=q, status=status,
                       page=page, pages=pages, total=total)


@app.route("/admin/projects/new", methods=["GET", "POST"])
@requires_admin
def admin_project_new():
    db = get_db(); categories = projects_svc.get_categories(db, only_used=False, published_only=False)
    values = _admin_project_form_data() if request.method == "POST" else {"categories": [], "technologies": "", "published": True, "featured": False}
    errors = {}
    if request.method == "POST":
        uploaded = None
        try:
            uploaded = _save_project_upload(request.files.get("image_file"), values.get("title") or "project")
            payload = dict(values)
            if uploaded: payload["image"] = uploaded
            project = projects_svc.create_project(db, payload)
            return redirect(url_for("admin_project_edit", project_id=project["id"]) + "?saved=1", code=303)
        except projects_svc.ValidationError as exc:
            errors = exc.errors
        except Exception:
            db.rollback(); app.logger.exception("Admin project creation failed")
            errors = {"form": "The project could not be saved. Please try again."}
        if uploaded: _remove_unreferenced_image(uploaded)
    return _admin_page("admin_project_form.html", active="projects", page_title="Add project", values=values,
                       errors=errors, categories=categories, project=None)


@app.route("/admin/projects/<int:project_id>/edit", methods=["GET", "POST"])
@requires_admin
def admin_project_edit(project_id):
    db = get_db(); project = projects_svc.get_project_by_id(db, project_id)
    if not project: return _admin_page("admin_not_found.html", active="projects", page_title="Project not found"), 404
    categories = projects_svc.get_categories(db, only_used=False, published_only=False)
    values = _admin_project_form_data() if request.method == "POST" else {
        **project, "technologies": ", ".join(project.get("technologies", [])),
        "categories": [c["slug"] for c in project.get("categories", [])]}
    errors = {}; old_image = project.get("image"); uploaded = None
    if request.method == "POST":
        try:
            uploaded = _save_project_upload(request.files.get("image_file"), values.get("title") or project["slug"])
            payload = dict(values)
            if uploaded: payload["image"] = uploaded
            elif request.form.get("remove_image") == "1": payload["image"] = None
            updated = projects_svc.update_project(db, project_id, payload)
            if uploaded or request.form.get("remove_image") == "1": _remove_unreferenced_image(old_image)
            return redirect(url_for("admin_project_edit", project_id=project_id) + "?saved=1", code=303)
        except projects_svc.ValidationError as exc: errors = exc.errors
        except Exception:
            db.rollback(); app.logger.exception("Admin project update failed")
            errors = {"form": "The project could not be updated. Please try again."}
        if uploaded: _remove_unreferenced_image(uploaded)
    return _admin_page("admin_project_form.html", active="projects", page_title="Edit project", values=values,
                       errors=errors, categories=categories, project=project)


@app.route("/admin/projects/<int:project_id>/delete", methods=["POST"])
@requires_admin
def admin_project_delete(project_id):
    db = get_db(); project = projects_svc.get_project_by_id(db, project_id)
    if not project: return redirect(url_for("admin_projects_placeholder"), code=303)
    old_image = project.get("image")
    try:
        projects_svc.delete_project(db, project_id)
        _remove_unreferenced_image(old_image)
    except Exception:
        db.rollback(); app.logger.exception("Admin project deletion failed")
        return _admin_page("admin_projects.html", active="projects", projects=projects_svc.get_all_projects(db),
                           q="", status="all", page=1, pages=1, total=0, error="The project could not be deleted."), 500
    return redirect(url_for("admin_projects_placeholder") + "?deleted=1", code=303)


@app.route("/admin/orders")
@requires_admin
def admin_orders():
    db = get_db(); q = (request.args.get("q") or "").strip()[:100]
    sql = "SELECT * FROM orders"; params = []
    if q:
        sql += " WHERE name LIKE ? OR contact LIKE ? OR track LIKE ? OR message LIKE ?"
        params = ["%"+q+"%"] * 4
    rows = projects_svc._fetch(db, sql + " ORDER BY id DESC", params)
    page = _page_number(); total = len(rows); pages = max(1, (total + ADMIN_PAGE_SIZE - 1)//ADMIN_PAGE_SIZE)
    rows = rows[(page-1)*ADMIN_PAGE_SIZE:page*ADMIN_PAGE_SIZE]
    return _admin_page("admin_orders.html", orders=rows, q=q, page=page, pages=pages, total=total, active="orders")


@app.route("/admin/orders/<int:order_id>")
@requires_admin
def admin_order_detail(order_id):
    rows = projects_svc._fetch(get_db(), "SELECT * FROM orders WHERE id = ?", (order_id,))
    if not rows: return _admin_page("admin_not_found.html", active="orders", page_title="Order not found"), 404
    return _admin_page("admin_record_detail.html", active="orders", page_title="Student order", record=rows[0], kind="order")


@app.route("/admin/enquiries")
@requires_admin
def admin_enquiries():
    db = get_db(); q = (request.args.get("q") or "").strip()[:100]
    status = (request.args.get("status") or "all")[:30]
    sql = "SELECT id,name,email,phone,business_name,service,budget,status,created_at FROM business_enquiries WHERE 1=1"; params=[]
    if q:
        sql += " AND (name LIKE ? OR email LIKE ? OR phone LIKE ? OR business_name LIKE ? OR project_description LIKE ?)"
        params += ["%"+q+"%"]*5
    if status != "all": sql += " AND status = ?"; params.append(status)
    rows = projects_svc._fetch(db, sql + " ORDER BY id DESC", params)
    page = _page_number(); total=len(rows); pages=max(1,(total+ADMIN_PAGE_SIZE-1)//ADMIN_PAGE_SIZE)
    rows=rows[(page-1)*ADMIN_PAGE_SIZE:page*ADMIN_PAGE_SIZE]
    statuses = projects_svc._fetch(db, "SELECT DISTINCT status FROM business_enquiries ORDER BY status")
    return _admin_page("admin_enquiries.html", active="enquiries", enquiries=rows, q=q, status=status,
                       statuses=[r["status"] for r in statuses], page=page, pages=pages, total=total)


@app.route("/admin/enquiries/<int:enquiry_id>", methods=["GET", "POST"])
@requires_admin
def admin_enquiry_detail(enquiry_id):
    db=get_db(); rows=projects_svc._fetch(db,"SELECT * FROM business_enquiries WHERE id = ?",(enquiry_id,))
    if not rows: return _admin_page("admin_not_found.html",active="enquiries",page_title="Enquiry not found"),404
    record=rows[0]; errors={}
    if request.method=="POST":
        new_status=(request.form.get("status") or "").strip()
        notes=(request.form.get("admin_notes") or "").strip()
        if new_status not in (set(enquiry_svc.STATUSES) | {record.get("status")}): errors["status"]="Choose a valid status."
        if len(notes)>5000: errors["admin_notes"]="Notes must be 5,000 characters or fewer."
        if not errors:
            try:
                projects_svc._execute(db,"UPDATE business_enquiries SET status = ?, admin_notes = ?, updated_at = ? WHERE id = ?",
                                      (new_status,notes or None,datetime.now(timezone.utc).isoformat(),enquiry_id)); db.commit()
                return redirect(url_for("admin_enquiry_detail",enquiry_id=enquiry_id)+"?saved=1",code=303)
            except Exception:
                db.rollback(); app.logger.exception("Business enquiry update failed"); errors["form"]="Could not save these changes."
        record["status"]=new_status; record["admin_notes"]=notes
    return _admin_page("admin_enquiry_detail.html",active="enquiries",record=record,errors=errors, status_options=enquiry_svc.STATUSES)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
else:
    # also run under gunicorn (Render's production server)
    init_db()
