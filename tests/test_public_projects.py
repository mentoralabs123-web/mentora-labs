"""Public Projects page + existing enquiry integration tests (SQLite, Flask test client)."""
import os
import re
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    import psycopg  # noqa: F401
except ImportError:   # only needed for PostgreSQL; tests run on SQLite
    stub = types.ModuleType("psycopg"); stub.rows = types.ModuleType("psycopg.rows"); stub.rows.dict_row = None
    sys.modules["psycopg"], sys.modules["psycopg.rows"] = stub, stub.rows

import app as site
import project_service as svc

TITLES = [
    "NIDS — Network Intrusion Detection", "Skin Disease Classification", "Expense Tracker",
    "Heart Disease Prediction", "House Price Prediction", "Flight Fare Prediction",
    "Rice Leaf Disease Prediction", "Task Manager", "Quiz App",
]


def grid_titles(html):
    grid = html.split('id="projectGrid"')[1].split('id="projectEmpty"')[0]
    return re.findall(r"<h3>([^<]+)</h3>", grid)


class PublicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = site.DB_PATH
        site.DB_PATH = os.path.join(self.tmp.name, "t.db")
        site.init_db()
        self.client = site.app.test_client()

    def tearDown(self):
        site.DB_PATH = self._old
        self.tmp.cleanup()

    def db(self):
        import sqlite3
        d = sqlite3.connect(site.DB_PATH); d.row_factory = sqlite3.Row
        return d

    def page(self, path="/projects"):
        r = self.client.get(path); self.assertEqual(r.status_code, 200); return r.get_data(as_text=True)

    def test_all_nine_in_order_from_database(self):
        html = self.page()
        self.assertEqual(grid_titles(html), TITLES)
        self.assertEqual(len(re.findall(r'class="pcard"', html)), 9)
        self.assertIn('"key": "nids"', html)

    def test_category_filter_buttons_from_database(self):
        html = self.page()
        got = re.findall(r'data-cat="([^"]+)"[^>]*>([^<]+?)\s*<span class="filter__n">(\d+)', html)
        self.assertEqual(got, [("all", "All Projects", "9"), ("machine-learning", "Machine Learning", "6"),
                               ("deep-learning", "Deep Learning", "3"), ("data-science", "Data Science", "3"),
                               ("full-stack-applications", "Full-Stack Applications", "3"),
                               ("web-development", "Web Development", "3")])
        self.assertIn('data-cats="deep-learning machine-learning"', html)

    def test_unpublished_hidden_everywhere(self):
        d = self.db(); pid = svc.get_project_by_slug(d, "quiz")["id"]
        svc.update_project(d, pid, {"published": False}); d.close()
        for path in ("/projects", "/", "/learning", "/about"):
            html = self.page(path)
            self.assertNotIn("Quiz App", html, path)
        html = self.page()
        self.assertEqual(len(grid_titles(html)), 8)
        self.assertNotIn('"key": "quiz"', html)
        self.assertIn("Showing 8 of 8 projects", html)

    def test_ordering_follows_display_order(self):
        d = self.db(); pid = svc.get_project_by_slug(d, "quiz")["id"]
        svc.update_project(d, pid, {"display_order": 1}); d.close()
        self.assertEqual(grid_titles(self.page())[0], "Quiz App")

    def test_new_project_and_category_appear(self):
        d = self.db()
        svc.create_project(d, {"title": "AI Chat Helper", "short_description": "Demo", "categories": ["artificial-intelligence"]})
        d.close()
        html = self.page()
        self.assertIn("AI Chat Helper", html)
        self.assertIn('data-cat="artificial-intelligence"', html)

    def test_images_real_and_missing(self):
        d = self.db()
        svc.update_project(d, svc.get_project_by_slug(d, "nids")["id"], {"image": "img/banner.jpg"})
        svc.update_project(d, svc.get_project_by_slug(d, "skin")["id"], {"image": "uploads/projects/missing.png"})
        d.close()
        html = self.page()
        self.assertIn('src="/static/img/banner.jpg"', html)
        self.assertNotIn("missing.png", html)

    def test_database_failure_is_handled(self):
        with mock.patch.object(svc, "get_published_projects", side_effect=RuntimeError("db down")):
            html = self.page()
            self.assertIn("temporarily unavailable", html)
            self.assertEqual(self.client.get("/").status_code, 200)
            self.assertEqual(self.client.get("/nope").status_code, 404)

    def test_empty_database_state(self):
        d = self.db(); d.execute("DELETE FROM project_category_links"); d.execute("DELETE FROM projects"); d.commit(); d.close()
        self.assertIn("No projects are published yet", self.page())

    def test_enquiry_flow_unchanged(self):
        r = self.client.post("/api/orders", json={"name": "T", "contact": "t@e.com", "track": "Quiz App", "message": "hi"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.client.post("/api/orders", json={"name": ""}).status_code, 400)
        d = self.db(); self.assertEqual(d.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 1); d.close()
        self.assertIn(self.client.get("/admin/orders").status_code, (302, 503))
        html = self.page("/contact")
        self.assertIn("Quiz App", html)  # enquiry dialog options come from the database

    def test_no_project_write_routes_exposed(self):
        for rule in site.app.url_map.iter_rules():
            if "project" in rule.rule:
                self.assertEqual(rule.methods - {"GET", "HEAD", "OPTIONS"}, set(), rule.rule)
        self.assertFalse([r.rule for r in site.app.url_map.iter_rules() if r.rule.startswith("/admin/project")])

    def test_legacy_group_links_still_present(self):
        html = self.page("/learning")
        self.assertIn("View 4 projects", html)


if __name__ == "__main__":
    unittest.main()
