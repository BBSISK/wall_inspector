import unittest
import json
from app import create_app
from models import db, Wall, Defect


class GraderAuthAndLabelSeparationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            wall = Wall.query.filter_by(is_skill_assessment=True).first()
            if not wall:
                wall = Wall(
                    slug="test-grader-wall",
                    title="Test Grader Wall",
                    country="Ireland",
                    region="Connemara",
                    wall_type="dry_stone",
                    difficulty="intermediate",
                    image_filename="connemara.jpg",
                    is_published=True,
                    is_skill_assessment=True,
                )
                db.session.add(wall)
                db.session.commit()
            self.slug = wall.slug

    def test_unauthenticated_redirects_to_grader_login(self):
        """Unauthenticated requests to /skill-assessment/admin should redirect to /grader/login."""
        res = self.client.get("/skill-assessment/admin")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/grader/login", res.headers["Location"])

        res_labels = self.client.get(f"/skill-assessment/admin/labels/{self.slug}")
        self.assertEqual(res_labels.status_code, 302)
        self.assertIn("/grader/login", res_labels.headers["Location"])

    def test_grader_credentials_grant_grading_and_label_access_only(self):
        """Grader password/PIN grants access to grading & label studio, but NOT system/class admin."""
        login_res = self.client.post(
            "/grader/login",
            data=json.dumps({"password": "grader2026"}),
            content_type="application/json",
        )
        self.assertEqual(login_res.status_code, 200)
        data = login_res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["role"], "grader")

        # Grader can access /skill-assessment/admin, /grade/<slug>, and /labels/<slug>
        self.assertEqual(self.client.get("/skill-assessment/admin").status_code, 200)
        self.assertEqual(self.client.get(f"/skill-assessment/admin/grade/{self.slug}").status_code, 200)
        self.assertEqual(self.client.get(f"/skill-assessment/admin/labels/{self.slug}").status_code, 200)

        # Grader cannot access /admin/system or /admin/class (requires admin)
        sys_res = self.client.get("/admin/system")
        self.assertIn(sys_res.status_code, [302, 401, 403])
        cls_res = self.client.get("/admin/class")
        self.assertIn(cls_res.status_code, [302, 401, 403])

    def test_admin_automatically_has_grader_access(self):
        """Admin login automatically grants full access to all grading and label definition routes."""
        login_res = self.client.post(
            "/admin/login",
            data=json.dumps({"password": "stonecraft2026"}),
            content_type="application/json",
        )
        self.assertEqual(login_res.status_code, 200)
        data = login_res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["role"], "system_admin")

        # Admin can access both Admin routes AND Grader/Label routes
        self.assertEqual(self.client.get("/admin/system").status_code, 200)
        self.assertEqual(self.client.get("/skill-assessment/admin").status_code, 200)
        self.assertEqual(self.client.get(f"/skill-assessment/admin/grade/{self.slug}").status_code, 200)
        self.assertEqual(self.client.get(f"/skill-assessment/admin/labels/{self.slug}").status_code, 200)

    def test_grading_and_label_screens_are_clearly_separated(self):
        """Verify grading screen has no inline palette builder tab and links to the separate label studio."""
        self.client.post(
            "/grader/login",
            data=json.dumps({"pin": "1010"}),
            content_type="application/json",
        )

        # 1. Check Grading Screen (/skill-assessment/admin/grade/<slug>)
        grade_html = self.client.get(f"/skill-assessment/admin/grade/{self.slug}").get_data(as_text=True)
        self.assertIn("1. Defect Pins", grade_html)
        self.assertIn("2. General Issues", grade_html)
        self.assertNotIn('id="tab-btn-palette"', grade_html)
        self.assertIn(f"/skill-assessment/admin/labels/{self.slug}", grade_html)

        # 2. Check Dedicated Label Studio Screen (/skill-assessment/admin/labels/<slug>)
        labels_html = self.client.get(f"/skill-assessment/admin/labels/{self.slug}").get_data(as_text=True)
        self.assertIn("Label &amp; Dropdown Definition Studio", labels_html)
        self.assertIn("1. Create Custom Defect Label for This Wall", labels_html)
        self.assertIn("2. Prioritise Standard Taxonomy Label", labels_html)
        self.assertIn("3. Active Specimen Dropdown Order", labels_html)
        self.assertIn(f"/skill-assessment/admin/grade/{self.slug}", labels_html)

        # 3. Grader can save custom label modes via the API
        save_modes_res = self.client.post(
            f"/api/skill-assessment/modes/{self.slug}",
            data=json.dumps({
                "prioritized_modes": [
                    {"id": "custom_basal_scour", "label": "Basal Scour Undercut", "is_custom": True}
                ]
            }),
            content_type="application/json",
        )
        self.assertEqual(save_modes_res.status_code, 200)
        modes_data = save_modes_res.get_json()
        self.assertTrue(modes_data["success"])
        self.assertTrue(any(m["id"] == "custom_basal_scour" for m in modes_data["prioritized_modes"]))

    def test_grader_studio_only_has_specimen_queue(self):
        """Verify /skill-assessment/admin only shows the Assessment Specimen Queue, while ingestion/batteries live in /skill-assessment/admin/ingest."""
        self.client.post(
            "/grader/login",
            data=json.dumps({"pin": "1010"}),
            content_type="application/json",
        )
        studio_html = self.client.get("/skill-assessment/admin").get_data(as_text=True)
        self.assertIn("Assessment Specimen Queue", studio_html)
        self.assertNotIn("Photographic Capture Standards", studio_html)
        self.assertNotIn("Curriculum Director Agent & Exam Battery Orchestrator", studio_html)
        self.assertNotIn("Ingest Assessment Specimen", studio_html)

        ingest_html = self.client.get("/skill-assessment/admin/ingest").get_data(as_text=True)
        self.assertIn("Photographic Capture Standards", ingest_html)
        self.assertIn("Curriculum Director Agent", ingest_html)
        self.assertIn("Ingest Assessment Specimen", ingest_html)


if __name__ == "__main__":
    unittest.main()
