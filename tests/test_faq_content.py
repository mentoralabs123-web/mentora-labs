"""FAQ content and contact details regression tests (no Flask runtime required)."""
import unittest
from faq_content import FAQ_CATEGORIES


class FAQContentTests(unittest.TestCase):
    def test_all_eight_categories_and_110_questions_exist(self):
        self.assertEqual(len(FAQ_CATEGORIES), 8)
        self.assertEqual(sum(len(c["items"]) for c in FAQ_CATEGORIES), 110)
        for category in FAQ_CATEGORIES:
            self.assertTrue(category["name"])
            self.assertTrue(category["items"])
            for item in category["items"]:
                self.assertTrue(item["question"].endswith("?"))
                self.assertGreater(len(item["answer"]), 40)

    def test_no_duplicate_questions(self):
        questions = [item["question"] for category in FAQ_CATEGORIES for item in category["items"]]
        self.assertEqual(len(questions), len(set(questions)))

    def test_contact_update_preserves_existing_numbers(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "app.py").read_text(encoding="utf-8")
        self.assertIn('"+91 74491 52395"', app_source)
        self.assertIn('"+91 76048 94278"', app_source)
        self.assertIn('"+91 88258 28406"', app_source)
        self.assertIn('"additional_whatsapp_number": "918825828406"', app_source)
        contact_template = (root / "templates" / "contact.html").read_text(encoding="utf-8")
        self.assertIn("contact.phones", contact_template)
        self.assertIn("contact.additional_whatsapp_number", contact_template)


if __name__ == "__main__":
    unittest.main()
