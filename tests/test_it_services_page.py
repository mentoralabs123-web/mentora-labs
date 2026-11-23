"""Task 4A: public IT Services page (route, content, CTAs, no regressions).

Updated in Task 4B: the CTAs now link to the business enquiry form instead of opening the dialog."""
import os
import re
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    import psycopg  # noqa: F401
except ImportError:
    stub = types.ModuleType("psycopg"); stub.rows = types.ModuleType("psycopg.rows"); stub.rows.dict_row = None
    sys.modules["psycopg"], sys.modules["psycopg.rows"] = stub, stub.rows

import app as site

SERVICES = [
    "Website design", "Website development", "Web application development",
    "Application development", "UI/UX design", "Custom software and digital solutions",
]
STEPS = [
    "Requirement discussion", "Planning and solution design", "UI/UX and architecture",
    "Development", "Testing and refinement", "Delivery",
]
CLIENTS = ["Small businesses", "Startups", "Entrepreneurs", "Organizations", "Personal brands", "Professionals", "Individuals"]
PUBLIC_ROUTES = ["/", "/about", "/services", "/projects", "/learning", "/contact", "/reviews"]
# Claims the brief says must not appear unless agreed with a client
FORBIDDEN = ["unlimited", "lifetime", "guarantee", "24/7", "testimonial", "trusted by", "% ", "award"]


class ServicesPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = site.DB_PATH
        site.DB_PATH = os.path.join(self.tmp.name, "t.db")
        site.init_db()
        self.client = site.app.test_client()
        r = self.client.get("/services")
        self.assertEqual(r.status_code, 200)
        self.html = r.get_data(as_text=True)

    def tearDown(self):
        site.DB_PATH = self._old
        self.tmp.cleanup()

    def test_route_and_sidebar_link(self):
        self.assertEqual(site.app.url_map.bind("").match("/services")[0], "services")
        m = re.search(r'<a class="nav-link" href="/services" aria-current="page">\s*.*?IT Services', self.html, re.S)
        self.assertIsNotNone(m, "IT Services sidebar link should be current on /services")

    def test_single_h1_and_hero(self):
        self.assertEqual(len(re.findall(r"<h1[ >]", self.html)), 1)
        self.assertIn("Digital solutions designed around your business", self.html)
        self.assertIn("Discuss your project", self.html)
        self.assertIn('href="#services"', self.html)
        self.assertIn('id="services"', self.html)

    def test_all_six_services(self):
        for title in SERVICES:
            self.assertIn(f"<h3 id=", self.html)
            self.assertRegex(self.html, rf">{re.escape(title)}</h3>")
        self.assertEqual(len(re.findall(r'class="svc-card"', self.html)), 6)

    def test_six_process_steps_in_order(self):
        block = self.html.split('class="process"')[1].split("</ol>")[0]
        titles = re.findall(r"</span>([^<]+)</h3>", block)
        self.assertEqual([t.strip() for t in titles], STEPS)

    def test_client_types(self):
        block = self.html.split('class="svc-clients__list"')[1].split("</ul>")[0]
        self.assertEqual(re.findall(r"<h3>([^<]+)</h3>", block), CLIENTS)

    def test_cta_buttons_present_and_wired(self):
        for label in ["Discuss your project", "Request a website", "Build your application", "Contact Mentora Labs"]:
            self.assertIn(label, self.html)
        # Task 4B: every enquiry CTA is a link to the business enquiry form
        ctas = re.findall(r'<a[^>]*data-service-cta="[^"]+"[^>]*>', self.html)
        self.assertEqual(len(ctas), 6 + 1 + 3)  # 6 service cards, 1 hero, 3 closing CTAs
        for tag in ctas:
            self.assertIn('href="/services/enquiry?', tag)
        self.assertIn('href="/contact"', self.html)

    def test_contact_links_use_existing_details_only(self):
        self.assertIn(f"https://wa.me/{site.CONTACT['whatsapp_number']}?text=", self.html)
        self.assertIn(f"mailto:{site.CONTACT['email']}", self.html)
        for number in re.findall(r"wa\.me/(\d+)", self.html):
            self.assertEqual(number, site.CONTACT["whatsapp_number"])
        for email in re.findall(r"mailto:([^\"]+)", self.html):
            self.assertEqual(email, site.CONTACT["email"])

    def test_no_unsupported_claims(self):
        main = self.html.split('<main id="main"')[1].split("</main>")[0].lower()
        for word in FORBIDDEN:
            self.assertNotIn(word, main, f"unsupported claim wording: {word!r}")

    def test_no_horizontal_overflow_hooks(self):
        # Stylesheet must contain the responsive rules the page depends on
        css = open(os.path.join(ROOT, "static", "css", "style.css"), encoding="utf-8").read()
        for sel in [".svc-hero__grid", ".svc-card", ".process__item", ".svc-clients", ".svc-cta"]:
            self.assertIn(sel, css)

    def test_every_public_route_still_works(self):
        for path in PUBLIC_ROUTES:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.client.get("/does-not-exist").status_code, 404)

    def test_existing_enquiry_api_unchanged(self):
        r = self.client.post("/api/orders", json={"name": "Test", "contact": "t@example.com", "track": "Other / not sure yet", "message": "Hi"})
        self.assertEqual(r.status_code, 201)


if __name__ == "__main__":
    unittest.main()
