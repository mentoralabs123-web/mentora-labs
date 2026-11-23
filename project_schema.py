"""Schema creation and one-time data migration for the projects tables.

Everything here is additive and safe to run on every start-up:
* tables use CREATE TABLE IF NOT EXISTS (existing tables/data are never touched),
* the original nine projects are seeded once, tracked in ``schema_migrations``,
* seeding skips any slug that already exists, so it can never create duplicates
  or overwrite later edits.
"""
from datetime import datetime, timezone

import project_seed_data as seed
import project_service as svc

SEED_MIGRATION = "seed_projects_v1"


def _ddl(is_pg):
    pk = "BIGSERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    idt = "BIGINT" if is_pg else "INTEGER"
    return [
        "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)",
        f"""CREATE TABLE IF NOT EXISTS project_categories (
            id {pk}, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            art_kind TEXT NOT NULL DEFAULT 'web', display_order INTEGER NOT NULL DEFAULT 0)""",
        f"""CREATE TABLE IF NOT EXISTS projects (
            id {pk}, slug TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
            short_description TEXT, description TEXT,
            technologies TEXT NOT NULL DEFAULT '[]',
            image TEXT, gallery_images TEXT NOT NULL DEFAULT '[]',
            problem_statement TEXT, objective TEXT, implementation_details TEXT,
            project_url TEXT, domain_tag TEXT, learning_group TEXT,
            featured INTEGER NOT NULL DEFAULT 0, published INTEGER NOT NULL DEFAULT 1,
            display_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
        f"""CREATE TABLE IF NOT EXISTS project_category_links (
            project_id {idt} NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            category_id {idt} NOT NULL REFERENCES project_categories(id) ON DELETE CASCADE,
            position INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (project_id, category_id))""",
        "CREATE INDEX IF NOT EXISTS idx_projects_published_order ON projects (published, display_order)",
    ]


def create_tables(db):
    for statement in _ddl(svc._is_pg(db)):
        db.execute(statement)
    db.commit()


def seed_categories(db):
    """Insert any missing category (matched by slug). Returns number inserted."""
    added = 0
    for order, cat in enumerate(seed.CATEGORIES, start=1):
        if svc._fetch(db, "SELECT id FROM project_categories WHERE slug = ?", (cat["slug"],)):
            continue
        try:
            svc._execute(
                db,
                "INSERT INTO project_categories (slug, name, art_kind, display_order) VALUES (?, ?, ?, ?)",
                (cat["slug"], cat["name"], cat["art_kind"], order * 10),
            )
            db.commit()
            added += 1
        except Exception:
            db.rollback()  # another worker inserted it first
    return added


def seed_projects(db):
    """Migrate the original projects. Idempotent: existing slugs are skipped.

    Returns ``(inserted, skipped)``.
    """
    seed_categories(db)
    inserted = skipped = 0
    for item in seed.PROJECTS:
        if svc._fetch(db, "SELECT id FROM projects WHERE slug = ?", (item["slug"],)):
            skipped += 1
            continue
        try:
            svc.create_project(db, {**item, "published": True, "featured": False})
            inserted += 1
        except svc.ValidationError as exc:
            if "slug" in exc.errors:  # lost a start-up race to another worker
                skipped += 1
            else:
                raise
    return inserted, skipped


def _migration_applied(db, name):
    return bool(svc._fetch(db, "SELECT name FROM schema_migrations WHERE name = ?", (name,)))


def init_projects(db):
    """Create tables and run the one-time seed. Safe to call on every start-up.

    The seed runs once and is then recorded, so a project an admin later
    deletes is not brought back by the next restart.
    """
    create_tables(db)
    seed_categories(db)
    if not _migration_applied(db, SEED_MIGRATION):
        seed_projects(db)
        try:
            svc._execute(
                db, "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                (SEED_MIGRATION, datetime.now(timezone.utc).isoformat()),
            )
            db.commit()
        except Exception:
            db.rollback()  # marker already written by another worker
