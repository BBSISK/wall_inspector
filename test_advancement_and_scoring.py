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

    def test_four_sequential_specimens_completed_for_barry_sisk(self):
        """Simulate candidate Barry Sisk completing 4 sequential specimens and verify all 4 are recorded."""
        with self.app.app_context():
            walls = Wall.query.filter_by(is_skill_assessment=True, is_published=True).order_by(Wall.id.asc()).limit(4).all()
            self.assertEqual(len(walls), 4)

        token = "cand_test_barry_sisk_4walls"
        completed_slugs = []

        # Complete each of the 4 specimens
        for i, wall in enumerate(walls):
            payload = {
                "pins": [
                    {"id": f"pin-{i}", "x": 0.45, "y": 0.45, "category": "mortar_erosion", "severity": "moderate"}
                ],
                "student_name": "Barry Sisk",
                "candidate_token": token
            }
            res = self.client.post(
                f"/api/skill-assessment/evaluate/{wall.slug}",
                data=json.dumps(payload),
                content_type="application/json"
            )
            self.assertEqual(res.status_code, 200)
            data = json.loads(res.data.decode("utf-8"))
            self.assertTrue(data.get("success"))
            completed_slugs.append(wall.slug)

        # Query progress for Barry Sisk
        progress_res = self.client.get(f"/api/skill-assessment/student-progress?student_name=Barry%20Sisk&candidate_token={token}")
        self.assertEqual(progress_res.status_code, 200)
        prog_data = json.loads(progress_res.data.decode("utf-8"))
        self.assertEqual(prog_data["completed_count"], 4)
        for s in completed_slugs:
            self.assertIn(s, prog_data["by_slug"])
            self.assertTrue(prog_data["by_slug"][s]["completed"])

        # Check Student Portal reflects 4 completed
        portal_res = self.client.get("/portal?student_name=Barry%20Sisk")
        self.assertEqual(portal_res.status_code, 200)
        portal_html = portal_res.data.decode("utf-8")
        self.assertIn("Barry Sisk", portal_html)
        self.assertIn("4 / ", portal_html)

        # Check Skills Hub reflects 4 completed
        hub_res = self.client.get("/skill-assessment?student_name=Barry%20Sisk")
        self.assertEqual(hub_res.status_code, 200)
        hub_html = hub_res.data.decode("utf-8")
        self.assertIn("Barry Sisk", hub_html)
        self.assertIn("4 / ", hub_html)

    def test_auto_claim_orphaned_inspector_candidate_attempts(self):
        """Verify that an attempt recorded as Inspector Candidate from the same token is auto-claimed for Barry Sisk."""
        with self.app.app_context():
            wall = Wall.query.filter_by(is_skill_assessment=True, is_published=True).order_by(Wall.id.desc()).first()

        token = "cand_orphaned_claim_token_999"

        # Submit attempt defaulting to Inspector Candidate with the token
        payload = {
            "pins": [{"id": "pin-orphan", "x": 0.5, "y": 0.5, "category": "lime_washout", "severity": "moderate"}],
            "student_name": "Inspector Candidate",
            "candidate_token": token
        }
        res = self.client.post(f"/api/skill-assessment/evaluate/{wall.slug}",
                               data=json.dumps(payload),
                               content_type="application/json")
        self.assertEqual(res.status_code, 200)

        # Now Barry Sisk syncs or checks progress with this token
        prog_res = self.client.get(f"/api/skill-assessment/student-progress?student_name=Barry%20Sisk&candidate_token={token}&claim_recent=1")
        self.assertEqual(prog_res.status_code, 200)
        prog_data = json.loads(prog_res.data.decode("utf-8"))

        # The orphaned attempt should now be claimed by Barry Sisk
        self.assertGreaterEqual(prog_data["completed_count"], 1)
        self.assertIn(wall.slug, prog_data["by_slug"])

        with self.app.app_context():
            saved_attempt = AssessmentAttempt.query.filter_by(student_session_id=token).first()
            self.assertIsNotNone(saved_attempt)
            self.assertEqual(saved_attempt.student_name, "Barry Sisk")

    def test_workstation_candidate_badge_in_header(self):
        """Verify the candidate badge and interactive switcher are rendered in workstation header."""
        with self.app.app_context():
            wall = Wall.query.filter_by(is_skill_assessment=True, is_published=True).first()

        res = self.client.get(f"/skill-assessment/{wall.slug}?student_name=Barry%20Sisk")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("candidate-pill-badge", html)
        self.assertIn("workstation-candidate-display", html)
        self.assertIn("editCandidateName()", html)
        self.assertIn("top-portal-btn", html)
        self.assertIn("top-hub-btn", html)

if __name__ == "__main__":
    unittest.main()
