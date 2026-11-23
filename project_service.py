"""Project data access layer (no Flask imports, no route logic).

Every function takes an open DB connection (``sqlite3`` or ``psycopg``) as its
first argument, uses parameterised queries only, and works with both backends:
SQL uses ``?`` placeholders which are translated to ``%s`` for psycopg.

Reads: get_published_projects, get_all_projects, get_project_by_id,
       get_project_by_slug, get_featured_projects, get_projects_by_category,
       get_categories
Writes (foundation for the future admin panel; not exposed by any route yet):
       create_project, update_project, delete_project
"""
import json
import os
import re
import secrets
from datetime import datetime, timezone

IMAGE_DIR = "uploads/projects"          # relative to the Flask static folder
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_\-./]+$")

MAX_TITLE = 150
MAX_SHORT = 300
MAX_LONG = 5000
MAX_TECH = 20
MAX_TECH_LEN = 40
MAX_GALLERY = 12

_COLUMNS = (
    "id, slug, title, short_description, description, technologies, image, gallery_images, "
    "problem_statement, objective, implementation_details, project_url, domain_tag, "
    "learning_group, featured, published, display_order, created_at, updated_at"
)


class ValidationError(ValueError):
    """Raised for invalid project data. ``errors`` maps field name -> message."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))


# ---------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------

def _is_pg(db):
    return type(db).__module__.split(".")[0] == "psycopg"


def _sql(db, query):
    return query.replace("?", "%s") if _is_pg(db) else query


def _execute(db, query, params=()):
    return db.execute(_sql(db, query), tuple(params))


def _fetch(db, query, params=()):
    """Run a SELECT and return a list of plain dicts (any row factory)."""
    cur = _execute(db, query, params)
    cols = [d[0] for d in cur.description]
    out = []
    for row in cur.fetchall():
        out.append(dict(row) if isinstance(row, dict) else dict(zip(cols, row)))
    return out


def _now():
    return datetime.now(timezone.utc).isoformat()


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return slug[:80].strip("-")


def _loads_list(value):
    try:
        data = json.loads(value) if value else []
    except (TypeError, ValueError):
        return []
    return [str(x) for x in data if isinstance(x, str) and x] if isinstance(data, list) else []


# ---------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------

def _hydrate(db, rows):
    """Turn raw project rows into dicts with decoded JSON, booleans and categories."""
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    marks = ",".join("?" * len(ids))
    links = _fetch(
        db,
        "SELECT l.project_id, c.slug, c.name, c.art_kind FROM project_category_links l "
        "JOIN project_categories c ON c.id = l.category_id "
        f"WHERE l.project_id IN ({marks}) ORDER BY l.position, c.display_order, c.id",
        ids,
    )
    by_project = {}
    for link in links:
        by_project.setdefault(link["project_id"], []).append(
            {"slug": link["slug"], "name": link["name"], "art_kind": link["art_kind"]}
        )
    projects = []
    for r in rows:
        p = dict(r)
        p["technologies"] = _loads_list(r.get("technologies"))
        p["gallery_images"] = _loads_list(r.get("gallery_images"))
        p["featured"] = bool(r.get("featured"))
        p["published"] = bool(r.get("published"))
        p["categories"] = by_project.get(r["id"], [])
        projects.append(p)
    return projects


def _list(db, where="", params=(), limit=None):
    query = f"SELECT {_COLUMNS} FROM projects {where} ORDER BY display_order, id"
    if limit:
        query += " LIMIT " + str(int(limit))
    return _hydrate(db, _fetch(db, query, params))


def get_published_projects(db):
    return _list(db, "WHERE published = 1")


def get_all_projects(db):
    """Every project including unpublished ones. For admin use only."""
    return _list(db)


def get_project_by_id(db, project_id, published_only=False):
    where = "WHERE id = ?" + (" AND published = 1" if published_only else "")
    rows = _list(db, where, (project_id,), limit=1)
    return rows[0] if rows else None


def get_project_by_slug(db, slug, published_only=False):
    where = "WHERE slug = ?" + (" AND published = 1" if published_only else "")
    rows = _list(db, where, (slug,), limit=1)
    return rows[0] if rows else None


def get_featured_projects(db, limit=None):
    return _list(db, "WHERE published = 1 AND featured = 1", limit=limit)


def get_projects_by_category(db, category_slug, published_only=True):
    where = (
        "WHERE id IN (SELECT l.project_id FROM project_category_links l "
        "JOIN project_categories c ON c.id = l.category_id WHERE c.slug = ?)"
    )
    if published_only:
        where += " AND published = 1"
    return _list(db, where, (category_slug,))


def get_categories(db, only_used=True, published_only=True):
    """Categories with a project_count. ``only_used`` hides empty categories."""
    extra = " AND p.published = 1" if published_only else ""
    rows = _fetch(
        db,
        "SELECT c.id, c.slug, c.name, c.art_kind, c.display_order, COUNT(p.id) AS project_count "
        "FROM project_categories c "
        "LEFT JOIN project_category_links l ON l.category_id = c.id "
        f"LEFT JOIN projects p ON p.id = l.project_id{extra} "
        "GROUP BY c.id, c.slug, c.name, c.art_kind, c.display_order "
        "ORDER BY c.display_order, c.id",
    )
    for r in rows:
        r["project_count"] = int(r["project_count"] or 0)
    return [r for r in rows if r["project_count"] > 0] if only_used else rows


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------

def _clean_text(data, field, limit, errors, required=False):
    value = data.get(field)
    if value is None or str(value).strip() == "":
        if required:
            errors[field] = "is required"
        return None
    value = str(value).strip()
    if len(value) > limit:
        errors[field] = f"must be at most {limit} characters"
    return value


def is_safe_image_path(path):
    """Relative path inside the static folder; no traversal, no absolute paths."""
    return (
        isinstance(path, str) and 0 < len(path) <= 200 and bool(_SAFE_PATH.match(path))
        and not path.startswith(("/", ".")) and ".." not in path
    )


def _clean_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _validate(db, data, partial, project_id=None):
    errors, out = {}, {}
    has = (lambda f: f in data) if partial else (lambda f: True)

    if has("title"):
        out["title"] = _clean_text(data, "title", MAX_TITLE, errors, required=True)
    if has("short_description"):
        out["short_description"] = _clean_text(data, "short_description", MAX_SHORT, errors)
    for f in ("description", "problem_statement", "objective", "implementation_details"):
        if has(f):
            out[f] = _clean_text(data, f, MAX_LONG, errors)
    if has("domain_tag"):
        out["domain_tag"] = _clean_text(data, "domain_tag", 60, errors)
    if has("learning_group"):
        out["learning_group"] = _clean_text(data, "learning_group", 30, errors)

    if has("technologies"):
        raw = data.get("technologies") or []
        if isinstance(raw, str):
            raw = [t for t in raw.split(",")]
        techs, seen = [], set()
        for t in raw:
            t = str(t).strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                techs.append(t)
        if len(techs) > MAX_TECH or any(len(t) > MAX_TECH_LEN for t in techs):
            errors["technologies"] = f"at most {MAX_TECH} items of {MAX_TECH_LEN} characters"
        out["technologies"] = json.dumps(techs)

    if has("image"):
        img = (data.get("image") or "").strip() or None
        if img and not is_safe_image_path(img):
            errors["image"] = "must be a safe relative path"
        out["image"] = img
    if has("gallery_images"):
        gallery = [str(g).strip() for g in (data.get("gallery_images") or []) if str(g).strip()]
        if len(gallery) > MAX_GALLERY or not all(is_safe_image_path(g) for g in gallery):
            errors["gallery_images"] = "must be safe relative paths (max %d)" % MAX_GALLERY
        out["gallery_images"] = json.dumps(gallery)

    if has("project_url"):
        url = (data.get("project_url") or "").strip() or None
        if url and (not re.match(r"^https?://[^\s]+$", url, re.I) or len(url) > 500):
            errors["project_url"] = "must be an http(s) URL"
        out["project_url"] = url

    if has("featured"):
        out["featured"] = 1 if _clean_bool(data.get("featured")) else 0
    if has("published"):
        out["published"] = 1 if _clean_bool(data.get("published", True)) else 0
    if has("display_order") and data.get("display_order") not in (None, ""):
        try:
            out["display_order"] = int(data["display_order"])
        except (TypeError, ValueError):
            errors["display_order"] = "must be a whole number"

    categories = None
    if "categories" in data:
        categories = []
        known = {r["slug"]: r["id"] for r in _fetch(db, "SELECT id, slug FROM project_categories")}
        for slug in data.get("categories") or []:
            if slug not in known:
                errors["categories"] = f"unknown category: {slug}"
                break
            if known[slug] not in [c[1] for c in categories]:
                categories.append((slug, known[slug]))

    if "slug" in data and (data.get("slug") or "").strip():
        slug = slugify(data["slug"])
        if not slug:
            errors["slug"] = "is invalid"
        else:
            out["slug"] = slug
    if errors:
        raise ValidationError(errors)
    return out, categories


def _unique_slug(db, base, exclude_id=None):
    base = base or "project"
    slug, n = base, 2
    while True:
        rows = _fetch(db, "SELECT id FROM projects WHERE slug = ?", (slug,))
        if not rows or (exclude_id is not None and rows[0]["id"] == exclude_id):
            return slug
        slug = f"{base}-{n}"
        n += 1


def _set_categories(db, project_id, categories):
    _execute(db, "DELETE FROM project_category_links WHERE project_id = ?", (project_id,))
    for position, (_slug, cat_id) in enumerate(categories):
        _execute(
            db,
            "INSERT INTO project_category_links (project_id, category_id, position) VALUES (?, ?, ?)",
            (project_id, cat_id, position),
        )


# ---------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------

def create_project(db, data):
    """Validate and insert a project; returns the stored project dict.

    Nothing is committed unless every step succeeds. An explicit ``slug`` that
    already exists raises ValidationError; an auto-generated one gets a suffix.
    """
    clean, categories = _validate(db, data, partial=False)
    try:
        if "slug" in clean:
            if _fetch(db, "SELECT id FROM projects WHERE slug = ?", (clean["slug"],)):
                raise ValidationError({"slug": "already exists"})
        else:
            clean["slug"] = _unique_slug(db, slugify(clean["title"]))
        if "display_order" not in clean:
            top = _fetch(db, "SELECT MAX(display_order) AS m FROM projects")[0]["m"]
            clean["display_order"] = (top or 0) + 10
        clean.setdefault("published", 1)
        clean.setdefault("featured", 0)
        now = _now()
        clean["created_at"] = clean["updated_at"] = now
        cols = list(clean)
        _execute(
            db,
            f"INSERT INTO projects ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [clean[c] for c in cols],
        )
        pid = _fetch(db, "SELECT id FROM projects WHERE slug = ?", (clean["slug"],))[0]["id"]
        _set_categories(db, pid, categories or [])
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_project_by_id(db, pid)


def update_project(db, project_id, data):
    """Update only the fields present in ``data``. Returns the project, or None if missing."""
    if not _fetch(db, "SELECT id FROM projects WHERE id = ?", (project_id,)):
        return None
    clean, categories = _validate(db, data, partial=True, project_id=project_id)
    try:
        if "slug" in clean and _fetch(
            db, "SELECT id FROM projects WHERE slug = ? AND id <> ?", (clean["slug"], project_id)
        ):
            raise ValidationError({"slug": "already exists"})
        clean["updated_at"] = _now()
        sets = ", ".join(f"{c} = ?" for c in clean)
        _execute(db, f"UPDATE projects SET {sets} WHERE id = ?", [*clean.values(), project_id])
        if categories is not None:
            _set_categories(db, project_id, categories)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_project_by_id(db, project_id)


def delete_project(db, project_id):
    """Delete a project and its category links. Returns True if a row was removed."""
    try:
        _execute(db, "DELETE FROM project_category_links WHERE project_id = ?", (project_id,))
        cur = _execute(db, "DELETE FROM projects WHERE id = ?", (project_id,))
        removed = cur.rowcount > 0
        db.commit()
    except Exception:
        db.rollback()
        raise
    return removed


# ---------------------------------------------------------------------
# Images (for the future upload feature) and public presentation
# ---------------------------------------------------------------------

def make_image_path(original_filename, slug="project"):
    """Return a safe static-relative path for a newly uploaded image.

    The client's filename is never used as-is: only its extension (from an
    allow-list) survives, plus the project slug and a random token.
    """
    ext = os.path.splitext(str(original_filename or ""))[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise ValidationError({"image": "unsupported image type"})
    return f"{IMAGE_DIR}/{slugify(slug) or 'project'}-{secrets.token_hex(4)}{ext}"


def _existing(path, static_dir):
    """The path if it is safe and the file exists under static_dir, else None."""
    if not is_safe_image_path(path):
        return None
    if static_dir is None:
        return path
    full = os.path.realpath(os.path.join(static_dir, path))
    root = os.path.realpath(static_dir)
    return path if full.startswith(root + os.sep) and os.path.isfile(full) else None


def to_public_dict(p, static_dir=None, static_url=lambda f: f):
    """Shape a project for the public Projects page (cards + details dialog).

    Missing image files are dropped so the page never renders a broken image;
    optional sections with no data are left out entirely.
    """
    cats = p.get("categories", [])
    cover = _existing(p.get("image"), static_dir)
    gallery = [g for g in (_existing(g, static_dir) for g in p.get("gallery_images", [])) if g]
    images = ([cover] if cover else []) + [g for g in gallery if g != cover]
    item = {
        "key": p["slug"],
        "title": p["title"],
        "desc": p.get("short_description") or "",
        "overview": p.get("description") or p.get("short_description") or "",
        "chips": list(p.get("technologies", [])),
        "domain": (p.get("domain_tag") or "").replace(" · ", " / "),
        "group": p.get("learning_group"),
        "categories": [{"key": c["slug"], "label": c["name"]} for c in cats],
        "primary": cats[0]["name"] if cats else "",
        "kind": cats[0]["art_kind"] if cats else "web",
        "image": static_url(cover) if cover else None,
        "images": [static_url(i) for i in images],
    }
    for public, field in (("problem", "problem_statement"), ("objective", "objective"),
                          ("implementation", "implementation_details"), ("link", "project_url")):
        if p.get(field):
            item[public] = p[field]
    return item


def to_track(p):
    """Legacy shape used by Home/About/Learning/Services and the enquiry form."""
    return {
        "key": p["slug"], "group": p.get("learning_group"), "tag": p.get("domain_tag") or "",
        "title": p["title"], "desc": p.get("short_description") or "", "chips": list(p.get("technologies", [])),
    }
