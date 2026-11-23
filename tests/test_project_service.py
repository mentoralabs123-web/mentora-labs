"""Database, migration and service-layer tests (SQLite). Run: python -m unittest discover tests"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import project_schema as schema
import project_seed_data as seed
import project_service as svc

TITLES = [
    "NIDS — Network Intrusion Detection", "Skin Disease Classification", "Expense Tracker",
    "Heart Disease Prediction", "House Price Prediction", "Flight Fare Prediction",
    "Rice Leaf Disease Prediction", "Task Manager", "Quiz App",
]


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    return db


class DBTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "t.db")
        self.db = connect(self.path)
        schema.init_projects(self.db)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def count(self, table):
        return self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


class MigrationTests(DBTestCase):
    def test_initialisation_creates_tables(self):
        names = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"projects", "project_categories", "project_category_links", "schema_migrations"} <= names)

    def test_all_nine_projects_migrated_in_order(self):
        self.assertEqual([p["title"] for p in svc.get_published_projects(self.db)], TITLES)

    def test_migration_idempotent(self):
        schema.init_projects(self.db)
        schema.init_projects(self.db)
        self.assertEqual(self.count("projects"), 9)
        self.assertEqual(schema.seed_projects(self.db), (0, 9))   # direct re-run inserts nothing
        self.assertEqual(self.count("projects"), 9)
        self.assertEqual(self.count("project_category_links"), 18)
        self.assertEqual(self.count("project_categories"), len(seed.CATEGORIES))

    def test_no_duplicates(self):
        dup = self.db.execute("SELECT slug FROM projects GROUP BY slug HAVING COUNT(*) > 1").fetchall()
        dup_t = self.db.execute("SELECT title FROM projects GROUP BY title HAVING COUNT(*) > 1").fetchall()
        self.assertEqual((dup, dup_t), ([], []))

    def test_unique_slug_enforced_by_database(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO projects (slug, title, created_at, updated_at) VALUES ('nids','x','a','b')")

    def test_unknown_fields_not_invented(self):
        for p in svc.get_all_projects(self.db):
            for f in ("description", "image", "problem_statement", "objective",
                      "implementation_details", "project_url"):
                self.assertIsNone(p[f], f"{p['slug']}.{f}")
            self.assertEqual(p["gallery_images"], [])
            self.assertFalse(p["featured"])
            self.assertTrue(p["published"])

    def test_existing_orders_and_edits_survive_restart(self):
        self.db.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, "
                        "contact TEXT, track TEXT, message TEXT, created_at TEXT)")
        self.db.execute("INSERT INTO orders (name, contact, track, message, created_at) VALUES ('A','b','Quiz App','m','t')")
        self.db.commit()
        svc.update_project(self.db, svc.get_project_by_slug(self.db, "quiz")["id"], {"title": "Quiz App Renamed"})
        schema.init_projects(self.db)
        self.assertEqual(self.count("orders"), 1)
        self.assertEqual(svc.get_project_by_slug(self.db, "quiz")["title"], "Quiz App Renamed")

    def test_deleted_project_not_resurrected_by_restart(self):
        pid = svc.get_project_by_slug(self.db, "quiz")["id"]
        self.assertTrue(svc.delete_project(self.db, pid))
        schema.init_projects(self.db)
        self.assertIsNone(svc.get_project_by_slug(self.db, "quiz"))
        self.assertEqual(self.count("projects"), 8)


class RetrievalTests(DBTestCase):
    def test_by_id_and_slug(self):
        p = svc.get_project_by_slug(self.db, "heart")
        self.assertEqual(p["title"], "Heart Disease Prediction")
        self.assertEqual(svc.get_project_by_id(self.db, p["id"])["slug"], "heart")
        self.assertEqual(p["technologies"], ["Python", "Machine Learning", "Healthcare"])
        self.assertEqual([c["slug"] for c in p["categories"]], ["machine-learning", "data-science"])
        self.assertIsNone(svc.get_project_by_slug(self.db, "nope"))
        self.assertIsNone(svc.get_project_by_id(self.db, 99999))

    def test_category_filter(self):
        def slugs(cat): return [p["slug"] for p in svc.get_projects_by_category(self.db, cat)]
        self.assertEqual(slugs("machine-learning"), ["nids", "skin", "heart", "house", "flight", "rice-leaf"])
        self.assertEqual(slugs("deep-learning"), ["nids", "skin", "rice-leaf"])
        self.assertEqual(slugs("data-science"), ["heart", "house", "flight"])
        self.assertEqual(slugs("full-stack-applications"), ["expense", "task-manager", "quiz"])
        self.assertEqual(slugs("web-development"), ["expense", "task-manager", "quiz"])
        self.assertEqual(slugs("artificial-intelligence"), [])
        self.assertEqual(slugs("does-not-exist"), [])

    def test_categories_hide_empty(self):
        used = {c["slug"]: c["project_count"] for c in svc.get_categories(self.db)}
        self.assertEqual(used, {"machine-learning": 6, "deep-learning": 3, "data-science": 3,
                                "full-stack-applications": 3, "web-development": 3})
        self.assertEqual(len(svc.get_categories(self.db, only_used=False)), len(seed.CATEGORIES))

    def test_featured(self):
        self.assertEqual(svc.get_featured_projects(self.db), [])
        a = svc.get_project_by_slug(self.db, "nids")["id"]
        b = svc.get_project_by_slug(self.db, "quiz")["id"]
        svc.update_project(self.db, a, {"featured": True})
        svc.update_project(self.db, b, {"featured": True, "published": False})
        self.assertEqual([p["slug"] for p in svc.get_featured_projects(self.db)], ["nids"])
        self.assertEqual(svc.get_featured_projects(self.db, limit=1)[0]["slug"], "nids")

    def test_published_visibility(self):
        pid = svc.get_project_by_slug(self.db, "task-manager")["id"]
        svc.update_project(self.db, pid, {"published": False})
        self.assertNotIn("task-manager", [p["slug"] for p in svc.get_published_projects(self.db)])
        self.assertIn("task-manager", [p["slug"] for p in svc.get_all_projects(self.db)])
        self.assertIsNone(svc.get_project_by_slug(self.db, "task-manager", published_only=True))
        self.assertIsNone(svc.get_project_by_id(self.db, pid, published_only=True))
        self.assertNotIn("task-manager", [p["slug"] for p in svc.get_projects_by_category(self.db, "web-development")])
        counts = {c["slug"]: c["project_count"] for c in svc.get_categories(self.db)}
        self.assertEqual(counts["web-development"], 2)

    def test_sorting(self):
        quiz = svc.get_project_by_slug(self.db, "quiz")["id"]
        svc.update_project(self.db, quiz, {"display_order": 5})
        self.assertEqual(svc.get_published_projects(self.db)[0]["slug"], "quiz")
        nids = svc.get_project_by_slug(self.db, "nids")["id"]
        svc.update_project(self.db, nids, {"display_order": 5})   # tie -> lower id first
        self.assertEqual([p["slug"] for p in svc.get_published_projects(self.db)][:2], ["nids", "quiz"])


class WriteTests(DBTestCase):
    def test_create_defaults_and_slug(self):
        p = svc.create_project(self.db, {"title": "My New Project", "technologies": "Python, Flask, python",
                                         "categories": ["web-development"]})
        self.assertEqual(p["slug"], "my-new-project")
        self.assertEqual(p["technologies"], ["Python", "Flask"])
        self.assertTrue(p["published"] and not p["featured"])
        self.assertEqual(p["display_order"], 100)
        self.assertEqual(svc.create_project(self.db, {"title": "My New Project"})["slug"], "my-new-project-2")

    def test_validation(self):
        bad = [
            {"title": ""}, {"title": "x" * 200}, {"title": "ok", "project_url": "javascript:alert(1)"},
            {"title": "ok", "image": "../../etc/passwd"}, {"title": "ok", "image": "/abs/path.png"},
            {"title": "ok", "gallery_images": ["a b.png"]}, {"title": "ok", "categories": ["nope"]},
            {"title": "ok", "display_order": "abc"}, {"title": "ok", "slug": "quiz"},
        ]
        for data in bad:
            with self.assertRaises(svc.ValidationError, msg=str(data)):
                svc.create_project(self.db, data)
        self.assertEqual(self.count("projects"), 9)          # nothing half-created

    def test_failed_create_rolls_back(self):
        with self.assertRaises(svc.ValidationError):
            svc.create_project(self.db, {"title": "Ghost", "categories": ["machine-learning", "bogus"]})
        self.assertIsNone(svc.get_project_by_slug(self.db, "ghost"))

    def test_update_partial_and_categories(self):
        p = svc.get_project_by_slug(self.db, "house")
        before = p["updated_at"]
        u = svc.update_project(self.db, p["id"], {"objective": "Estimate prices", "categories": ["data-science"],
                                                  "project_url": "https://example.com/x", "featured": True})
        self.assertEqual(u["objective"], "Estimate prices")
        self.assertEqual([c["slug"] for c in u["categories"]], ["data-science"])
        self.assertEqual(u["title"], p["title"])
        self.assertEqual(u["technologies"], p["technologies"])
        self.assertTrue(u["featured"])
        self.assertGreaterEqual(u["updated_at"], before)
        self.assertIsNone(svc.update_project(self.db, 99999, {"title": "x"}))
        with self.assertRaises(svc.ValidationError):
            svc.update_project(self.db, p["id"], {"slug": "quiz"})
        svc.update_project(self.db, p["id"], {"slug": "house"})  # keeping own slug is fine

    def test_delete_removes_links(self):
        pid = svc.get_project_by_slug(self.db, "flight")["id"]
        self.assertTrue(svc.delete_project(self.db, pid))
        self.assertFalse(svc.delete_project(self.db, pid))
        self.assertEqual(self.count("projects"), 8)
        self.assertEqual(self.count("project_category_links"), 16)

    def test_sql_injection_attempt_is_inert(self):
        p = svc.create_project(self.db, {"title": "x'); DROP TABLE projects;--"})
        self.assertEqual(self.count("projects"), 10)
        self.assertIsNone(svc.get_project_by_slug(self.db, "' OR '1'='1"))
        self.assertTrue(p["title"].startswith("x'"))


class HelperTests(unittest.TestCase):
    def test_make_image_path(self):
        path = svc.make_image_path("../../My Photo!!.PNG", "Task Manager")
        self.assertRegex(path, r"^uploads/projects/task-manager-[0-9a-f]{8}\.png$")
        self.assertTrue(svc.is_safe_image_path(path))
        with self.assertRaises(svc.ValidationError):
            svc.make_image_path("shell.php", "x")

    def test_postgres_placeholder_translation(self):
        class FakePg:
            __module__ = "psycopg.connection"
        self.assertEqual(svc._sql(FakePg(), "SELECT 1 WHERE a = ? AND b = ?"), "SELECT 1 WHERE a = %s AND b = %s")
        self.assertEqual(svc._sql(sqlite3.connect(":memory:"), "a = ?"), "a = ?")

    def test_public_dict_image_fallback(self):
        static = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
        base = {"slug": "s", "title": "T", "short_description": "d", "technologies": ["A"], "categories": [],
                "domain_tag": "A · B", "learning_group": "ml"}
        ok = svc.to_public_dict({**base, "image": "img/banner.jpg"}, static, lambda f: "/static/" + f)
        self.assertEqual(ok["image"], "/static/img/banner.jpg")
        missing = svc.to_public_dict({**base, "image": "uploads/projects/nope.png",
                                      "gallery_images": ["img/banner.jpg", "../x.png"]}, static)
        self.assertIsNone(missing["image"])
        self.assertEqual(missing["images"], ["img/banner.jpg"])
        self.assertEqual(missing["domain"], "A / B")
        self.assertNotIn("problem", missing)


if __name__ == "__main__":
    unittest.main()
