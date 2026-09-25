import os
import io
import json
import unittest
from PIL import Image
from app import app, db, Wall, Defect
from sentinel_agent import audit_image_optics, enrich_geological_context, run_sentinel_audit, GEOLOGICAL_REGIONS

def create_synthetic_image(width=1200, height=800, color=(140, 130, 120)):
    """Helper to generate in-memory synthetic image bytes."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()

class TestIntakeSentinelAgent(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            self.test_slug = "test-sentinel-specimen-wall"
            wall = Wall.query.filter_by(slug=self.test_slug).first()
            if not wall:
                wall = Wall(
                    slug=self.test_slug,
                    title="Test Sentinel Field Wall Specimen",
                    description="Field trial specimen for Intake Sentinel QA tests.",
                    country="Ireland",
                    region="Co. Clare",
                    wall_type="dry_stone",
                    structural_function="boundary",
                    difficulty="intermediate",
                    is_published=True,
                    is_skill_assessment=True,
                    sentinel_status="passed",
                    sentinel_score=94,
                    sentinel_override=False
                )
                db.session.add(wall)
                db.session.commit()
            self.wall_id = wall.id

    def tearDown(self):
        with self.app.app_context():
            Wall.query.filter(Wall.slug == self.test_slug).delete()
            upload_walls = Wall.query.filter(Wall.slug.ilike("sentinel-test-%")).all()
            for w in upload_walls:
                Defect.query.filter_by(wall_id=w.id).delete()
                db.session.delete(w)
            db.session.commit()

    def test_audit_image_optics_high_res(self):
        """Test optical evaluation of a high-resolution, balanced-lighting image."""
        img_bytes = create_synthetic_image(1920, 1080, color=(128, 120, 110))
        optics = audit_image_optics(img_bytes)

        self.assertEqual(optics["width"], 1920)
        self.assertEqual(optics["height"], 1080)
        self.assertTrue(optics["resolution_pass"])
        self.assertGreaterEqual(optics["megapixels"], 2.0)
        self.assertEqual(optics["aspect_ratio"], "Landscape (Ideal)")
        self.assertGreaterEqual(optics["brightness_score"], 80)

    def test_audit_image_optics_low_res_advisory(self):
        """Test optical evaluation of a low-resolution image triggers resolution advisory."""
        img_bytes = create_synthetic_image(640, 480, color=(128, 120, 110))
        optics = audit_image_optics(img_bytes)

        self.assertEqual(optics["width"], 640)
        self.assertEqual(optics["height"], 480)
        self.assertFalse(optics["resolution_pass"])

    def test_enrich_geological_context_regions(self):
        """Verify geological bedrock and mortar enrichment across regions."""
        with self.app.app_context():
            wall = Wall.query.filter_by(slug=self.test_slug).first()
            # Co. Clare limestone
            geo_clare = enrich_geological_context(wall)
            self.assertIn("Burren Karst", geo_clare["bedrock_formation"])
            self.assertIn("lime", geo_clare["compatible_mortar"].lower())

            # Galway granite
            wall.region = "Connemara, Galway"
            geo_galway = enrich_geological_context(wall)
            self.assertIn("Galway Granite", geo_galway["bedrock_formation"])

            # Bath limestone
            wall.region = "Bath, Somerset"
            geo_bath = enrich_geological_context(wall)
            self.assertIn("Bath Freestone", geo_bath["bedrock_formation"])

    def test_run_sentinel_audit_composite(self):
        """Verify Sentinel audit computes composite score and 4 checklist pillars."""
        with self.app.app_context():
            wall = Wall.query.filter_by(slug=self.test_slug).first()
            img_bytes = create_synthetic_image(1920, 1080)

            report = run_sentinel_audit(wall, img_bytes)

            self.assertIn("score", report)
            self.assertIn("status", report)
            self.assertIn("checklist", report)
            self.assertIn("geology", report)
            self.assertIn("optics", report)
            self.assertIn("recommendations", report)

            # Ensure all 4 pillars exist
            checklist = report["checklist"]
            self.assertIn("orthogonal_plane", checklist)
            self.assertIn("diffuse_lighting", checklist)
            self.assertIn("framing_scope", checklist)
            self.assertIn("resolution", checklist)

            # Persisted to model
            self.assertEqual(wall.sentinel_status, report["status"])
            self.assertEqual(wall.sentinel_score, report["score"])

    def test_sentinel_report_endpoint(self):
        """Test GET /api/skill-assessment/sentinel-report/<slug> returns full structured audit."""
        with self.app.app_context():
            wall = Wall.query.filter_by(slug=self.test_slug).first()
            img_bytes = create_synthetic_image(1920, 1080)
            run_sentinel_audit(wall, img_bytes)
            db.session.commit()

        # Login as admin
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True

        res = self.client.get(f"/api/skill-assessment/sentinel-report/{self.test_slug}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["slug"], self.test_slug)
        self.assertIn("report", data)
        self.assertIn("checklist", data["report"])

    def test_sentinel_override_endpoint(self):
        """Test POST /api/skill-assessment/sentinel-override/<slug> sets override flag and overridden status."""
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True

        res = self.client.post(f"/api/skill-assessment/sentinel-override/{self.test_slug}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["sentinel_status"], "overridden")
        self.assertTrue(data["sentinel_override"])

        with self.app.app_context():
            wall = Wall.query.filter_by(slug=self.test_slug).first()
            self.assertTrue(wall.sentinel_override)
            self.assertEqual(wall.sentinel_status, "overridden")

    def test_grader_template_renders_sentinel_components(self):
        """Verify grader workstation renders the Sentinel badge button and modal markup."""
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True

        res = self.client.get(f"/skill-assessment/admin/grade/{self.test_slug}")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("sentinel-badge-btn", html)
        self.assertIn("sentinel-modal", html)
        self.assertIn("Intake Sentinel Quality Audit", html)
        self.assertIn("acknowledgeSentinelOverride", html)

    def test_admin_template_renders_sentinel_components(self):
        """Verify admin ingestion page displays Sentinel reassurance notice and Sentinel QA table header."""
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True

        res = self.client.get("/skill-assessment/admin")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Intake Sentinel audits optics", html)
        self.assertIn("<th>Sentinel QA</th>", html)

if __name__ == "__main__":
    unittest.main()
