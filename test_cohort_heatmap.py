import json
import unittest
from app import app, db, Wall, Defect, AssessmentAttempt, Student

class TestCohortHeatmap(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

        with self.app.app_context():
            self.test_slug = "test-cohort-heatmap-wall"
            wall = Wall.query.filter_by(slug=self.test_slug).first()
            if not wall:
                wall = Wall(
                    slug=self.test_slug,
                    title="Test Cohort Heatmap Wall",
                    description="Specimen for cohort inspection heatmap tests.",
                    country="Ireland",
                    wall_type="lime_mortar",
                    difficulty="intermediate",
                    is_published=True,
                    is_skill_assessment=True
                )
                db.session.add(wall)
                db.session.commit()
            self.wall_id = wall.id

            # Add ground truth defect
            Defect.query.filter_by(wall_id=self.wall_id).delete()
            gt = Defect(
                wall_id=self.wall_id,
                target_type="pin",
                x_min=0.40,
                y_min=0.50,
                x_max=0.40,
                y_max=0.50,
                tolerance_radius=0.08,
                category="mortar_erosion",
                severity="critical",
                remedial_action="repoint_lime",
                title="Bed Joint Lime Washout",
                explanation="Sacrificial lime binder erosion."
            )
            db.session.add(gt)
            db.session.commit()
            self.gt_id = gt.id

    def tearDown(self):
        with self.app.app_context():
            AssessmentAttempt.query.filter_by(wall_id=self.wall_id).delete()
            Defect.query.filter_by(wall_id=self.wall_id).delete()
            Wall.query.filter_by(id=self.wall_id).delete()
            db.session.commit()

    def test_cohort_heatmap_empty_specimen(self):
        res = self.client.get(f"/api/skill-assessment/cohort-heatmap/{self.test_slug}")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data.decode("utf-8"))
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("total_attempts"), 0)
        self.assertEqual(len(data.get("points", [])), 0)
        self.assertEqual(data.get("avg_score"), 0.0)
        self.assertEqual(len(data.get("gt_stats", [])), 1)
        self.assertEqual(data["gt_stats"][0]["hits"], 0)
        self.assertEqual(data["gt_stats"][0]["hit_rate_pct"], 0.0)

    def test_cohort_heatmap_aggregates_multiple_student_attempts(self):
        with self.app.app_context():
            # Student 1: Hits ground truth at (0.42, 0.51)
            att1 = AssessmentAttempt(
                wall_id=self.wall_id,
                student_name="Candidate Alice",
                student_session_id="session-alice-123",
                cohort_code="COHORT_2026",
                submitted_markers=[
                    {"x": 0.42, "y": 0.51, "category": "mortar_erosion", "severity": "critical"}
                ],
                score_percentage=100.0,
                passed=True
            )
            # Student 2: Misses ground truth, clicks at (0.80, 0.20)
            att2 = AssessmentAttempt(
                wall_id=self.wall_id,
                student_name="Candidate Bob",
                student_session_id="session-bob-456",
                cohort_code="COHORT_2026",
                submitted_markers=[
                    {"x": 0.80, "y": 0.20, "category": "spalling", "severity": "minor"}
                ],
                score_percentage=0.0,
                passed=False
            )
            db.session.add_all([att1, att2])
            db.session.commit()

        res = self.client.get(f"/api/skill-assessment/cohort-heatmap/{self.test_slug}")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data.decode("utf-8"))
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("total_attempts"), 2)
        self.assertEqual(data.get("unique_students"), 2)
        self.assertEqual(data.get("avg_score"), 50.0)
        self.assertEqual(len(data.get("points", [])), 2)

        # Alice hit, Bob missed -> 1 hit out of 2 attempts = 50.0%
        gt_stats = data.get("gt_stats", [])
        self.assertEqual(len(gt_stats), 1)
        self.assertEqual(gt_stats[0]["hits"], 1)
        self.assertEqual(gt_stats[0]["hit_rate_pct"], 50.0)

    def test_cohort_heatmap_filtering_by_cohort_code(self):
        with self.app.app_context():
            att_special = AssessmentAttempt(
                wall_id=self.wall_id,
                student_name="Apprentice Charlie",
                student_session_id="session-charlie-789",
                cohort_code="MASTERS",
                submitted_markers=[
                    {"x": 0.40, "y": 0.50, "category": "mortar_erosion"}
                ],
                score_percentage=100.0,
                passed=True
            )
            att_other = AssessmentAttempt(
                wall_id=self.wall_id,
                student_name="Candidate Dave",
                student_session_id="session-dave-000",
                cohort_code="NOVICES",
                submitted_markers=[
                    {"x": 0.10, "y": 0.10, "category": "efflorescence"}
                ],
                score_percentage=20.0,
                passed=False
            )
            db.session.add_all([att_special, att_other])
            db.session.commit()

        # Query specifically for MASTERS cohort
        res = self.client.get(f"/api/skill-assessment/cohort-heatmap/{self.test_slug}?cohort=MASTERS")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data.decode("utf-8"))
        self.assertEqual(data.get("total_attempts"), 1)
        self.assertEqual(data.get("avg_score"), 100.0)
        self.assertEqual(len(data.get("points")), 1)
        self.assertEqual(data["gt_stats"][0]["hit_rate_pct"], 100.0)

    def test_workstation_and_grader_templates_render_heatmap_elements(self):
        # Workstation HTML contains canvas and toggle buttons
        res_ws = self.client.get(f"/skill-assessment/{self.test_slug}")
        self.assertEqual(res_ws.status_code, 200)
        ws_html = res_ws.data.decode("utf-8")
        self.assertIn("cohort-heatmap-canvas", ws_html)
        self.assertIn("btn-cohort-heatmap", ws_html)
        self.assertIn("cohort-insights-hud", ws_html)

        # Grader HTML contains canvas and toggle button
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
        res_grader = self.client.get(f"/skill-assessment/admin/grade/{self.test_slug}")
        self.assertEqual(res_grader.status_code, 200)
        grader_html = res_grader.data.decode("utf-8")
        self.assertIn("cohort-heatmap-canvas", grader_html)
        self.assertIn("btn-grader-heatmap", grader_html)

if __name__ == "__main__":
    unittest.main()

