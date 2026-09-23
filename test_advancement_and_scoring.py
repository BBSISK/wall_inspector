import unittest
import json
from app import app, db, Wall, AssessmentAttempt

class TestAdvancementAndScoring(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            # Clean up test attempts created for Barry Sisk
            AssessmentAttempt.query.filter_by(student_name="Barry Sisk").delete()
            db.session.commit()

    def test_specimen_workstation_advancement_links(self):
        with self.app.app_context():
            walls = Wall.query.filter_by(is_skill_assessment=True, is_published=True).order_by(Wall.id.asc()).all()
            self.assertGreater(len(walls), 1)
            first_wall = walls[0]
            second_wall = walls[1]

        res = self.client.get(f"/skill-assessment/{first_wall.slug}?student_name=Barry%20Sisk")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Next Specimen", html)
        self.assertIn(second_wall.slug, html)
        self.assertIn("Barry", html)

    def test_evaluation_advancement_payload(self):
        with self.app.app_context():
            walls = Wall.query.filter_by(is_skill_assessment=True, is_published=True).order_by(Wall.id.asc()).all()
            first_wall = walls[0]
            second_wall = walls[1]

        payload = {
            "pins": [{"id": "pin-1", "x": 0.5, "y": 0.5, "category": "mortar_erosion", "severity": "moderate"}],
            "student_name": "Barry Sisk"
        }
        res = self.client.post(f"/api/skill-assessment/evaluate/{first_wall.slug}",
                               data=json.dumps(payload),
                               content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data.decode("utf-8"))
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("next_specimen_slug"), second_wall.slug)
        self.assertIn(second_wall.slug, data.get("next_specimen_url", ""))
        self.assertIn("Barry", data.get("next_specimen_url", ""))

    def test_student_progress_api_and_dashboard_level_scoring(self):
        with self.app.app_context():
            first_wall = Wall.query.filter_by(is_skill_assessment=True, is_published=True).order_by(Wall.id.asc()).first()

        # Initial check - 0 completed
        res = self.client.get("/api/skill-assessment/student-progress?student_name=Barry%20Sisk")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data.decode("utf-8"))
        self.assertEqual(data["completed_count"], 0)

        # Submit evaluation
        payload = {
            "pins": [{"id": "pin-1", "x": 0.5, "y": 0.5, "category": "mortar_erosion", "severity": "moderate"}],
            "student_name": "Barry Sisk"
        }
        self.client.post(f"/api/skill-assessment/evaluate/{first_wall.slug}",
                         data=json.dumps(payload),
                         content_type="application/json")

        # Now progress should reflect 1 completed
        res2 = self.client.get("/api/skill-assessment/student-progress?student_name=Barry%20Sisk")
        data2 = json.loads(res2.data.decode("utf-8"))
        self.assertEqual(data2["completed_count"], 1)
        self.assertIn(first_wall.slug, data2["by_slug"])

        # Check student portal rendering with progress
        portal_res = self.client.get("/portal?student_name=Barry%20Sisk")
        self.assertEqual(portal_res.status_code, 200)
        portal_html = portal_res.data.decode("utf-8")
        self.assertIn("candidate-progress-strip", portal_html)
        self.assertIn("Barry Sisk", portal_html)

        # Check assessment hub rendering with progress
        hub_res = self.client.get("/skill-assessment?student_name=Barry%20Sisk")
        self.assertEqual(hub_res.status_code, 200)
        hub_html = hub_res.data.decode("utf-8")
        self.assertIn("candidate-progress-strip", hub_html)
        self.assertIn("Review / Retake Score", hub_html)

if __name__ == "__main__":
    unittest.main()
