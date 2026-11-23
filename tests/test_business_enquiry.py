"""Task 4B: business enquiry system (validation, storage, security, CTAs, regressions). SQLite."""
import os
import re
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    import psycopg  # noqa: F401
except ImportError:   # only needed for PostgreSQL; these tests run on SQLite
    stub = types.ModuleType("psycopg"); stub.rows = types.ModuleType("psycopg.rows"); stub.rows.dict_row = None
    sys.modules["psycopg"], sys.modules["psycopg.rows"] = stub, stub.rows

import app as site
import business_enquiry as be

GOOD = {
    "name": "Asha Raman",
    "email": "asha@example.com",
    "phone": "",
    "business_name": "Raman Clinic",
    "service": "website-development",
    "project_description": "We run a small clinic and need a website with appointment requests.",
    "budget": "discuss",
}


def hidden(html, name):
    m = re.search(r'<input type="hidden" name="%s" value="([^"]*)"' % name, html)
    return m.group(1) if m else ""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = site.DB_PATH
        site.DB_PATH = os.path.join(self.tmp.name, "t.db")
        site.init_db()
        site._attempts.clear()
        self.client = site.app.test_client()

    def tearDown(self):
        site.DB_PATH = self._old
        self.tmp.cleanup()

    def db(self):
        d = sqlite3.connect(site.DB_PATH)
        d.row_factory = sqlite3.Row
        return d

    def rows(self, table="business_enquiries"):
        d = self.db()
        try:
            return [dict(r) for r in d.execute(f"SELECT * FROM {table} ORDER BY rowid")]
        finally:
            d.close()

    def form(self, query=""):
        r = self.client.get("/services/enquiry" + query)
        self.assertEqual(r.status_code, 200)
        return r.get_data(as_text=True)

    def submit(self, fresh_form=True, **over):
        html = self.form() if fresh_form else ""
        data = dict(GOOD)
        data.update({"csrf_token": hidden(html, "csrf_token"), "submission_token": hidden(html, "submission_token"), "source": ""})
        data.update(over)
        data = {k: v for k, v in data.items() if v is not None}
        return self.client.post("/services/enquiry", data=data)


class ValidationTests(unittest.TestCase):
    def check(self, **over):
        raw = dict(GOOD); raw.update(over)
        return be.validate(be.clean_form(raw))

    def test_valid(self):
        self.assertEqual(self.check(), {})

    def test_name_rules(self):
        self.assertIn("name", self.check(name=""))
        self.assertIn("name", self.check(name="   "))
        self.assertIn("name", self.check(name="A"))
        self.assertIn("name", self.check(name="12345"))
        self.assertIn("name", self.check(name="x" * 101))
        self.assertEqual(self.check(name="Zoë O'Neil-Smith"), {})
        self.assertEqual(self.check(name="நித்யா"), {})

    def test_contact_rules(self):
        self.assertIn("contact", self.check(email="", phone=""))
        self.assertEqual(self.check(email="", phone="+91 74491 52395"), {})
        self.assertEqual(self.check(email="a@b.co", phone=""), {})
        for bad in ["plain", "a@b", "a@@b.com", "a b@c.com", "a@b.c", "<x>@b.com", "a@b.com, c@d.com"]:
            self.assertIn("email", self.check(email=bad), bad)
        self.assertIn("email", self.check(email="a" * 250 + "@b.com"))

    def test_phone_rules(self):
        for good in ["+91 74491 52395", "7449152395", "+1 (415) 555-0132", "+44 20 7946 0958", "044-2345 6789"]:
            self.assertEqual(self.check(email="", phone=good), {}, good)
        for bad in ["12", "abcdefghij", "+91 7449 15239 5123456", "123-456-78x", "++9112345678", "1" * 31]:
            self.assertIn("phone", self.check(email="", phone=bad), bad)

    def test_service_and_budget_whitelist(self):
        self.assertIn("service", self.check(service=""))
        self.assertIn("service", self.check(service="hacking"))
        self.assertIn("service", self.check(service="Website Development"))  # label is not a code
        for code in be.SERVICE_LABELS:
            self.assertEqual(self.check(service=code), {})
        self.assertEqual(self.check(budget=""), {})
        self.assertIn("budget", self.check(budget="1 billion"))
        for code in be.BUDGET_LABELS:
            self.assertEqual(self.check(budget=code), {})

    def test_description_rules(self):
        self.assertIn("project_description", self.check(project_description=""))
        self.assertIn("project_description", self.check(project_description="  \n  "))
        self.assertIn("project_description", self.check(project_description="short"))
        self.assertIn("project_description", self.check(project_description="x" * 2001))
        self.assertEqual(self.check(project_description="x" * 2000), {})
        self.assertIn("project_description", self.check(project_description="see " + "http://a.example " * 6))

    def test_business_name_limit(self):
        self.assertIn("business_name", self.check(business_name="x" * 151))
        self.assertEqual(self.check(business_name=""), {})

    def test_cleaning(self):
        v = be.clean_form({"name": "  Asha \u200b  Raman\x00 ", "email": " Asha@EXAMPLE.Com ", "project_description": "a\r\n\r\n\r\n\r\nb  c\x07"})
        self.assertEqual(v["name"], "Asha Raman")
        self.assertEqual(v["email"], "Asha@example.com")
        self.assertEqual(v["project_description"], "a\n\nb c")

    def test_preselection_helpers(self):
        self.assertEqual(be.service_code("Website-Development"), "website-development")
        self.assertIsNone(be.service_code("nope"))
        self.assertEqual(be.service_for_cta("cta-website"), "website-development")
        self.assertEqual(be.service_for_cta("cta-application"), "application-development")
        self.assertEqual(be.service_for_cta("hero-discuss"), "other")
        self.assertIsNone(be.service_for_cta("unknown"))


class FormPageTests(Base):
    def test_form_loads(self):
        html = self.form()
        for needle in ['method="post"', 'name="csrf_token"', 'name="submission_token"', 'name="nickname_hp"',
                       'name="name"', 'name="email"', 'name="phone"', 'name="business_name"',
                       'name="service"', 'name="project_description"', 'name="budget"', "enquiry.js"]:
            self.assertIn(needle, html)
        self.assertEqual(len(re.findall(r"<h1[ >]", html)), 1)
        for label in be.SERVICE_LABELS.values():
            self.assertIn(f">{label}</option>", html)
        for label in be.BUDGET_LABELS.values():
            self.assertIn(f">{label}</option>", html)
        self.assertIn("Not decided yet", html); self.assertIn("Prefer to discuss", html)
        self.assertIn("(optional)", html)
        self.assertIn("no-store", self.client.get("/services/enquiry").headers["Cache-Control"])

    def test_sidebar_marks_it_services_current(self):
        html = self.form()
        self.assertRegex(html, r'<a class="nav-link" href="/services" aria-current="page">')

    def test_preselect_from_service_param_and_cta(self):
        self.assertRegex(self.form("?service=ui-ux-design"), r'<option value="ui-ux-design" selected>')
        self.assertRegex(self.form("?cta=cta-website"), r'<option value="website-development" selected>')
        self.assertRegex(self.form("?cta=cta-application"), r'<option value="application-development" selected>')
        self.assertRegex(self.form("?cta=hero-discuss"), r'<option value="other" selected>')

    def test_invalid_preselect_ignored(self):
        html = self.form("?service=<script>alert(1)</script>&cta=%22%3E%3Cx")
        self.assertNotIn("<script>alert(1)", html)
        form = html.split('id="enquiryForm"')[1].split("</form>")[0]   # ignore the student dialog's own select
        self.assertNotRegex(form, r'<option value="[^"]+" selected>')
        self.assertIn('<option value="" selected disabled>Select a service', form)

    def test_services_page_ctas_point_to_form_with_right_service(self):
        html = self.client.get("/services").get_data(as_text=True)
        links = dict(re.findall(r'href="(/services/enquiry\?[^"]*)"\s+data-service-cta="([^"]+)"', html))
        by_key = {v: k for k, v in links.items()}
        self.assertIn("service=website-development", by_key["service-website-development"])
        self.assertIn("service=web-application-development", by_key["service-web-applications"])
        self.assertIn("service=custom-software", by_key["service-custom-software"])
        self.assertIn("cta=cta-website", by_key["cta-website"])
        self.assertIn("cta=cta-application", by_key["cta-application"])
        self.assertIn("cta=hero-discuss", by_key["hero-discuss"])
        # every link the page offers lands on a valid, preselected form
        for url in links:
            page = self.client.get(url.replace("&amp;", "&"))
            self.assertEqual(page.status_code, 200)
            self.assertRegex(page.get_data(as_text=True), r'<option value="[a-z\-]+" selected>')

    def test_contact_page_links_to_form_and_dialog_no_longer_offers_it(self):
        self.assertIn('href="/services/enquiry"', self.client.get("/contact").get_data(as_text=True))
        dialog = self.client.get("/").get_data(as_text=True).split('id="orderDialog"')[1]
        self.assertNotIn('<option value="IT services (business enquiry)"', dialog)
        self.assertIn('href="/services/enquiry"', dialog)


class SubmissionTests(Base):
    def test_valid_submission_is_stored(self):
        r = self.submit(source="")
        self.assertEqual(r.status_code, 303)
        self.assertTrue(r.headers["Location"].endswith("/services/enquiry/submitted"))
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["name"], "Asha Raman")
        self.assertEqual(row["email"], "asha@example.com")
        self.assertIsNone(row["phone"])
        self.assertEqual(row["business_name"], "Raman Clinic")
        self.assertEqual(row["service"], "website-development")
        self.assertEqual(row["budget"], "discuss")
        self.assertEqual(row["status"], "New")
        self.assertIsNone(row["admin_notes"])
        self.assertTrue(row["created_at"].endswith("+00:00"))
        self.assertEqual(row["created_at"], row["updated_at"])
        done = self.client.get(r.headers["Location"]).get_data(as_text=True)
        self.assertIn("Your enquiry has been submitted", done)
        self.assertIn("Website Development", done)
        self.assertIn("Thank you, Asha", done)

    def test_phone_only_and_optional_fields_blank(self):
        r = self.submit(email="", phone="+91 74491 52395", business_name="", budget="")
        self.assertEqual(r.status_code, 303)
        row = self.rows()[0]
        self.assertIsNone(row["email"]); self.assertEqual(row["phone"], "+91 74491 52395")
        self.assertIsNone(row["business_name"]); self.assertIsNone(row["budget"])

    def test_source_stored_only_when_safe(self):
        self.submit(source="cta-website")
        self.submit(source="<b>bad</b>", project_description="A different enquiry for the second row.")
        rows = self.rows()
        self.assertEqual(rows[0]["source"], "cta-website")
        self.assertIsNone(rows[1]["source"])

    def test_success_page_requires_a_submission(self):
        r = self.client.get("/services/enquiry/submitted")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/services/enquiry"))

    def test_each_validation_failure_is_rejected_and_not_stored(self):
        cases = {
            "name": {"name": ""},
            "contact": {"email": "", "phone": ""},
            "email": {"email": "not-an-email"},
            "service": {"service": "bogus"},
            "project_description": {"project_description": ""},
        }
        for field, over in cases.items():
            r = self.submit(**over)
            self.assertEqual(r.status_code, 400, field)
            html = r.get_data(as_text=True)
            self.assertIn(f'id="{field}-error"', html, field)
            self.assertIn("Please check the highlighted fields", html)
            self.assertNotIn("has been submitted", html)
        self.assertEqual(self.rows(), [])

    def test_overlong_inputs_rejected(self):
        for over in [{"name": "x" * 101}, {"email": "a" * 250 + "@b.com"}, {"business_name": "x" * 151},
                     {"project_description": "x" * 2001}, {"phone": "1" * 31}]:
            self.assertEqual(self.submit(**over).status_code, 400, list(over))
        self.assertEqual(self.rows(), [])

    def test_oversized_body_rejected(self):
        r = self.submit(project_description="x" * 40000)
        self.assertEqual(r.status_code, 413)
        self.assertEqual(self.rows(), [])

    def test_values_preserved_on_error_and_escaped(self):
        r = self.submit(name="<script>alert(1)</script> Bob", email="bad", business_name='Acme "Co" <b>',
                        project_description="Line one\nLine <img src=x onerror=alert(1)> two", service="ui-ux-design", budget="over-5l")
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; Bob", html)
        self.assertIn("Line one\nLine &lt;img src=x onerror=alert(1)&gt; two", html)
        self.assertRegex(html, r'<option value="ui-ux-design" selected>')
        self.assertRegex(html, r'<option value="over-5l" selected>')
        self.assertIn('value="bad"', html)

    def test_sql_injection_text_is_stored_literally(self):
        evil = "Robert'); DROP TABLE business_enquiries;--"
        r = self.submit(name=evil, project_description="'; DELETE FROM orders; -- please build a website")
        self.assertEqual(r.status_code, 303)
        self.assertEqual(self.rows()[0]["name"], evil)
        self.assertEqual(len(self.rows()), 1)

    def test_stored_xss_text_is_escaped_on_success_page(self):
        r = self.submit(name="<b>Eve</b> Smith")
        done = self.client.get(r.headers["Location"]).get_data(as_text=True)
        self.assertNotIn("<b>Eve</b>", done)
        self.assertIn("&lt;b&gt;Eve&lt;/b&gt;", done)

    def test_get_only_form_page_does_not_accept_other_methods(self):
        self.assertEqual(self.client.put("/services/enquiry").status_code, 405)
        self.assertEqual(self.client.delete("/services/enquiry").status_code, 405)


class SecurityTests(Base):
    def test_csrf_missing_or_wrong_rejected(self):
        self.form()
        for token in [None, "", "forged"]:
            r = self.submit(fresh_form=False, csrf_token=token, submission_token="a" * 20)
            self.assertEqual(r.status_code, 400)
            self.assertIn("couldn", r.get_data(as_text=True))
        self.assertEqual(self.rows(), [])

    def test_csrf_without_session_cookie_rejected(self):
        html = self.form()
        other = site.app.test_client()  # no cookie: token cannot match
        r = other.post("/services/enquiry", data={**GOOD, "csrf_token": hidden(html, "csrf_token"), "submission_token": hidden(html, "submission_token")})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.rows(), [])

    def test_csrf_failure_keeps_input_and_gives_working_form(self):
        r = self.submit(fresh_form=False, csrf_token="forged", submission_token="a" * 20)
        html = r.get_data(as_text=True)
        self.assertIn('value="Asha Raman"', html)
        retry = self.client.post("/services/enquiry", data={**GOOD, "csrf_token": hidden(html, "csrf_token"), "submission_token": hidden(html, "submission_token")})
        self.assertEqual(retry.status_code, 303)
        self.assertEqual(len(self.rows()), 1)

    def test_honeypot_rejected(self):
        r = self.submit(nickname_hp="http://spam.example")
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("has been submitted", r.get_data(as_text=True))
        self.assertEqual(self.rows(), [])

    def test_in_memory_attempt_limit(self):
        with mock.patch.object(site, "ATTEMPT_LIMIT", 3):
            codes = [self.submit(name="").status_code for _ in range(5)]
        self.assertEqual(codes[:3], [400, 400, 400])
        self.assertEqual(codes[3:], [429, 429])

    def test_database_hourly_limit(self):
        for i in range(be.RATE_LIMIT_PER_HOUR):
            r = self.submit(project_description=f"Distinct requirement number {i} for a new website.")
            self.assertEqual(r.status_code, 303, i)
        r = self.submit(project_description="One more distinct requirement for a new website.")
        self.assertEqual(r.status_code, 429)
        self.assertIn("several enquiries recently", r.get_data(as_text=True))
        self.assertEqual(len(self.rows()), be.RATE_LIMIT_PER_HOUR)

    def test_client_ip_is_not_stored_in_clear(self):
        self.submit()
        row = self.rows()[0]
        self.assertNotIn("127.0.0.1", " ".join(str(v) for v in row.values()))
        self.assertEqual(len(row["client_hash"]), 32)


class DuplicateTests(Base):
    def test_same_form_token_double_submit_stores_once(self):
        html = self.form()
        data = {**GOOD, "csrf_token": hidden(html, "csrf_token"), "submission_token": hidden(html, "submission_token")}
        first = self.client.post("/services/enquiry", data=data)
        # csrf is single-use after success (session cleared), so re-open the form but reuse the old token
        html2 = self.form()
        data2 = {**data, "csrf_token": hidden(html2, "csrf_token")}
        second = self.client.post("/services/enquiry", data=data2)
        self.assertEqual((first.status_code, second.status_code), (303, 303))
        self.assertEqual(len(self.rows()), 1)

    def test_identical_enquiry_with_new_token_not_duplicated(self):
        self.assertEqual(self.submit().status_code, 303)
        self.assertEqual(self.submit().status_code, 303)
        self.assertEqual(len(self.rows()), 1)

    def test_same_token_different_content_is_stored_as_new(self):
        html = self.form()
        base = {"csrf_token": hidden(html, "csrf_token"), "submission_token": hidden(html, "submission_token")}
        self.client.post("/services/enquiry", data={**GOOD, **base})
        html2 = self.form()
        base["csrf_token"] = hidden(html2, "csrf_token")
        r = self.client.post("/services/enquiry", data={**GOOD, **base, "project_description": "A completely different requirement for a mobile app."})
        self.assertEqual(r.status_code, 303)
        self.assertEqual(len(self.rows()), 2)

    def test_distinct_enquiries_both_stored(self):
        self.submit(); self.submit(project_description="Another, different, project description here.")
        self.assertEqual(len(self.rows()), 2)


class FailureTests(Base):
    def test_database_error_is_friendly_and_not_a_success(self):
        secret = "psycopg.OperationalError: connection to server at db.internal password=hunter2 failed"
        with mock.patch.object(be, "create", side_effect=RuntimeError(secret)):
            r = self.submit()
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 503)
        self.assertIn("your enquiry was not sent", html)
        self.assertNotIn("has been submitted", html)
        for leak in ["hunter2", "psycopg", "Traceback", "RuntimeError", "db.internal"]:
            self.assertNotIn(leak, html)
        self.assertIn('value="Asha Raman"', html)      # form data preserved for the retry
        self.assertEqual(self.rows(), [])
        # retry works once the database is back
        retry = self.client.post("/services/enquiry", data={**GOOD, "csrf_token": hidden(html, "csrf_token"), "submission_token": hidden(html, "submission_token")})
        self.assertEqual(retry.status_code, 303)
        self.assertEqual(len(self.rows()), 1)

    def test_missing_table_is_handled(self):
        d = self.db(); d.execute("DROP TABLE business_enquiries"); d.commit(); d.close()
        r = self.submit()
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("no such table", r.get_data(as_text=True))
        self.assertNotIn("has been submitted", r.get_data(as_text=True))


class DatabaseTests(Base):
    def test_table_schema(self):
        d = self.db()
        cols = {r["name"]: r for r in d.execute("PRAGMA table_info(business_enquiries)")}
        d.close()
        for c in ["id", "name", "email", "phone", "business_name", "service", "project_description", "budget",
                  "status", "admin_notes", "created_at", "updated_at"]:
            self.assertIn(c, cols)
        self.assertEqual(cols["status"]["dflt_value"], "'New'")
        self.assertEqual(cols["status"]["notnull"], 1)

    def test_init_is_idempotent_and_non_destructive(self):
        self.client.post("/api/orders", json={"name": "Stu", "contact": "s@x.com", "track": "Expense Tracker", "message": "hi"})
        self.submit()
        projects_before = self.rows("projects"); orders_before = self.rows("orders"); enq_before = self.rows()
        for _ in range(3):
            site.init_db()
        self.assertEqual(self.rows("projects"), projects_before)
        self.assertEqual(self.rows("orders"), orders_before)
        self.assertEqual(self.rows(), enq_before)
        migrations = [r["name"] for r in self.rows("schema_migrations")]
        self.assertEqual(migrations.count(be.MIGRATION), 1)
        d = self.db()
        n = d.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='business_enquiries'").fetchone()[0]
        d.close()
        self.assertEqual(n, 1)

    def test_upgrade_from_database_without_the_table(self):
        d = self.db(); d.execute("DROP TABLE business_enquiries"); d.execute("DELETE FROM schema_migrations WHERE name=?", (be.MIGRATION,)); d.commit(); d.close()
        n_projects = len(self.rows("projects"))
        site.init_db()
        self.assertEqual(len(self.rows("projects")), n_projects)
        self.assertEqual(self.submit().status_code, 303)

    def test_statuses_constant(self):
        self.assertEqual(be.STATUSES, ["New", "Contacted", "In Progress", "Completed", "Closed"])
        self.assertEqual(be.DEFAULT_STATUS, "New")


class RegressionTests(Base):
    def test_existing_order_api_still_works_and_stays_separate(self):
        r = self.client.post("/api/orders", json={"name": "Stu", "contact": "s@x.com", "track": "Expense Tracker", "message": "hi"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(self.rows("orders")), 1)
        self.assertEqual(self.rows(), [])                      # no business row from a student order
        self.submit()
        self.assertEqual(len(self.rows("orders")), 1)          # no order row from a business enquiry
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.client.post("/api/orders", json={"name": "x"}).status_code, 400)

    def test_public_pages(self):
        for path in ["/", "/about", "/services", "/projects", "/learning", "/contact", "/reviews", "/services/enquiry"]:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.client.get("/nope").status_code, 404)

    def test_student_dialog_still_present_with_project_options(self):
        html = self.client.get("/projects").get_data(as_text=True)
        self.assertIn('id="orderForm"', html)
        self.assertIn('<option value="Other / not sure yet" selected>', html)
        self.assertIn('<option value="Expense Tracker">', html)

    def test_no_admin_routes_added(self):
        rules = [str(r) for r in site.app.url_map.iter_rules()]
        self.assertEqual(sorted(x for x in rules if "enquir" in x), ["/services/enquiry", "/services/enquiry/submitted"])
        self.assertEqual(self.client.get("/admin/enquiries").status_code, 404)


if __name__ == "__main__":
    unittest.main()
