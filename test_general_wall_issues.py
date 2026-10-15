import json
import unittest
from app import app, db, Wall, Defect, AssessmentAttempt, GENERAL_WALL_ISSUES, GENERAL_WALL_ISSUES_MAP, get_wall_general_issues

class TestGeneralWallIssues(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()
        self.slug = "test-specimen-general-issues-suite"

        with self.app.app_context():
            existing = Wall.query.filter_by(slug=self.slug).first()
            if existing:
                AssessmentAttempt.query.filter_by(wall_id=existing.id).delete()
                Defect.query.filter_by(wall_id=existing.id).delete()
                db.session.delete(existing)
                db.session.commit()

            wall = Wall(
                slug=self.slug,
                title="Test Specimen General Issues",
                country="Ireland",
                wall_type="ashlar",
                difficulty="medium",
                image_filename="ashlar_quarry.jpg",
                is_published=True,
                is_skill_assessment=True,
                general_wall_issues=["frost_spall_weathering", "mortar_joint_decay"]
            )
            db.session.add(wall)
            db.session.commit()

            # Add one defect pin
            d = Defect(
                wall_id=wall.id,
                target_type="pin",
                x_min=0.45,
                y_min=0.45,
                x_max=0.45,
                y_max=0.45,
                tolerance_radius=0.08,
                category="spalling",
                severity="moderate",
                remedial_action="repoint_lime",
                title="Surface Spalling"
            )
            db.session.add(d)
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            wall = Wall.query.filter_by(slug=self.slug).first()
            if wall:
                AssessmentAttempt.query.filter_by(wall_id=wall.id).delete()
                Defect.query.filter_by(wall_id=wall.id).delete()
                db.session.delete(wall)
                db.session.commit()

    def test_ten_standard_general_issues_defined(self):
        self.assertEqual(len(GENERAL_WALL_ISSUES), 10)
        expected_ids = [
            "structural_settlement_cracking",
            "moisture_rising_damp",
            "mortar_joint_decay",
            "frost_spall_weathering",
            "lateral_bulge_instability",
            "vegetation_root_jacking",
            "inappropriate_cement_pointing",
            "coping_capping_failure",
            "core_voiding_pinning_loss",
            "salt_efflorescence_cryptoflorescence"
        ]
        for issue_id in expected_ids:
            self.assertIn(issue_id, GENERAL_WALL_ISSUES_MAP)
            self.assertTrue(len(GENERAL_WALL_ISSUES_MAP[issue_id]["label"]) > 0)
            self.assertTrue(len(GENERAL_WALL_ISSUES_MAP[issue_id]["description"]) > 0)

    def test_wall_general_issues_fallback_derivation(self):
        with self.app.app_context():
            # Wall with configured issues returns configured issues
            wall = Wall.query.filter_by(slug=self.slug).first()
            configured = get_wall_general_issues(wall)
            self.assertEqual(configured, ["frost_spall_weathering", "mortar_joint_decay"])

            # Wall without configured issues auto-derives from wall_type and pins
            empty_wall = Wall(
                slug="test-empty-general-issues",
                title="Empty Wall",
                wall_type="dry_stone",
                is_skill_assessment=True
            )
            derived = get_wall_general_issues(empty_wall)
            self.assertTrue(isinstance(derived, list))
            self.assertGreaterEqual(len(derived), 2)
            self.assertLessEqual(len(derived), 3)
            self.assertIn("core_voiding_pinning_loss", derived)

    def test_instructor_saves_ground_truth_general_issues(self):
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True

        payload = {
            "defects": [
                {
                    "x": 0.5,
                    "y": 0.5,
                    "tolerance_radius": 0.08,
                    "category": "crack",
                    "severity": "severe",
                    "remedial_action": "structural_pinning",
                    "title": "Through-Stone Fracture"
                }
            ],
            "general_wall_issues": [
                "structural_settlement_cracking",
                "lateral_bulge_instability"
            ]
        }

        resp = self.client.post(
            f"/api/skill-assessment/grade/{self.slug}",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("general_wall_issues"), ["structural_settlement_cracking", "lateral_bulge_instability"])

        with self.app.app_context():
            wall = Wall.query.filter_by(slug=self.slug).first()
            self.assertEqual(wall.general_wall_issues, ["structural_settlement_cracking", "lateral_bulge_instability"])

    def test_student_evaluation_with_correct_general_issues(self):
        eval_payload = {
            "pins": [
                {
                    "x": 0.45,
                    "y": 0.45,
                    "category": "spalling",
                    "severity": "moderate"
                }
            ],
            "general_issues": [
                "frost_spall_weathering",
                "mortar_joint_decay"
            ],
            "is_dry_run": True
        }

        resp = self.client.post(
            f"/api/skill-assessment/evaluate/{self.slug}",
            data=json.dumps(eval_payload),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("general_issues_evaluation", data)
        gen_eval = data["general_issues_evaluation"]
        self.assertEqual(gen_eval["score"], 100.0)
        self.assertEqual(len(gen_eval["matched_issues"]), 2)
        self.assertEqual(len(gen_eval["missed_issues"]), 0)
        self.assertEqual(len(gen_eval["false_issues"]), 0)
        self.assertEqual(data["pin_score"], 100.0)
        self.assertEqual(data["score"], 100.0)

    def test_student_evaluation_with_partial_and_false_general_issues(self):
        eval_payload = {
            "pins": [
                {
                    "x": 0.45,
                    "y": 0.45,
                    "category": "spalling",
                    "severity": "moderate"
                }
            ],
            "general_issues": [
                "frost_spall_weathering",  # Matched
                "vegetation_root_jacking"   # False positive
                # Missed: "mortar_joint_decay"
            ],
            "is_dry_run": True
        }

        resp = self.client.post(
            f"/api/skill-assessment/evaluate/{self.slug}",
            data=json.dumps(eval_payload),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        gen_eval = data["general_issues_evaluation"]
        self.assertEqual(gen_eval["matched_issues"], ["frost_spall_weathering"])
        self.assertEqual(gen_eval["missed_issues"], ["mortar_joint_decay"])
        self.assertEqual(gen_eval["false_issues"], ["vegetation_root_jacking"])
        # Matched 1 of 2 is 50%, minus 10% penalty for 1 false positive = 40% issue score
        self.assertEqual(gen_eval["score"], 40.0)
        # Blended score: 100% pin * 0.70 + 40% issue * 0.30 = 70.0 + 12.0 = 82.0
        self.assertEqual(data["score"], 82.0)

if __name__ == "__main__":
    unittest.main()
