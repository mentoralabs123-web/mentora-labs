"""Task 5A admin authentication and CSRF regression tests."""
import os
import sys
import unittest
from werkzeug.security import generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    import psycopg  # noqa
except ImportError:
    import types
    stub = types.ModuleType("psycopg"); stub.rows = types.ModuleType("psycopg.rows"); stub.rows.dict_row = None
    sys.modules["psycopg"], sys.modules["psycopg.rows"] = stub, stub.rows
import app as site


class AdminAuthTests(unittest.TestCase):
    def setUp(self):
        self.old = (site.ADMIN_USER, site._ADMIN_PASSWORD_HASH, site.app.secret_key)
        site.ADMIN_USER = "task5a-test-admin"
        site._ADMIN_PASSWORD_HASH = generate_password_hash("task5a-test-password")
        site.app.secret_key = "test-only-secret-key-longer-than-32-characters"
        site.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.client = site.app.test_client()

    def tearDown(self):
        site.ADMIN_USER, site._ADMIN_PASSWORD_HASH, site.app.secret_key = self.old

    def token(self):
        html = self.client.get("/admin").get_data(as_text=True)
        import re
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def login(self, username="task5a-test-admin", password="task5a-test-password"):
        token = self.token()
        return self.client.post("/admin", data={"username": username, "password": password, "csrf_token": token})

    def test_login_page_and_logged_out_redirect(self):
        self.assertEqual(self.client.get("/admin").status_code, 200)
        response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin?", response.headers["Location"])

    def test_valid_login_and_dashboard(self):
        response = self.login()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 200)

    def test_invalid_login_is_generic(self):
        response = self.login(password="wrong")
        self.assertEqual(response.status_code, 401)
        self.assertIn("username or password is incorrect", response.get_data(as_text=True))
        self.assertNotIn("does not exist", response.get_data(as_text=True))

    def test_admin_csrf_is_required(self):
        self.token()
        response = self.client.post("/admin", data={"username": "x", "password": "y"})
        self.assertEqual(response.status_code, 400)

    def test_unauthorized_state_changing_requests_are_rejected(self):
        self.token()
        for method in ("post", "put", "patch", "delete"):
            response = getattr(self.client, method)("/admin/dashboard", data={"csrf_token": "invalid"})
            self.assertEqual(response.status_code, 400, method)

    def test_logout_invalidates_session(self):
        self.login()
        with self.client.session_transaction() as sess:
            token = sess["admin_csrf"]
        response = self.client.post("/admin/logout", data={"csrf_token": token})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 302)

    def test_public_pages_and_order_api_do_not_require_admin_login(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        response = self.client.post("/api/orders", json={"name": "Test", "contact": "test@example.com", "track": "Demo"})
        self.assertEqual(response.status_code, 201)


if __name__ == "__main__":
    unittest.main()
