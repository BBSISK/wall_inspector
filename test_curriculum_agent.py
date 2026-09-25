import unittest
import json
from app import app, db, Wall, Defect, Assignment, AssessmentAttempt, Student
from curriculum_agent import (
    assemble_battery_specimens,
    generate_student_battery_sequence,
    get_dry_run_calibration_data,
    analyze_cohort_intelligence
)

class MockWall:
    def __init__(self, id, slug, difficulty, wall_type="rubble", sentinel_score=90):
        self.id = id
        self.slug = slug
        self.difficulty = difficulty
        self.wall_type = wall_type
        self.sentinel_score = sentinel_score
        self.title = f"Wall {id}"
        self.is_skill_assessment = True
        self.is_published = True

class TestCurriculumDirectorAgent(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()

        with self.client.session_transaction() as sess:
            sess["is_admin"] = True

        with self.app.app_context():
            # Clean up test artifacts
            Assignment.query.filter(Assignment.code.ilike("TEST-%")).delete()
            AssessmentAttempt.query.filter(AssessmentAttempt.assignment_code.ilike("TEST-%")).delete()
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            Assignment.query.filter(Assignment.code.ilike("TEST-%")).delete()
            AssessmentAttempt.query.filter(AssessmentAttempt.assignment_code.ilike("TEST-%")).delete()
            db.session.commit()

    # --- Unit Tests: Battery Assembly & Difficulty Balancing ---

    def test_assemble_battery_default_10(self):
        """Assessor default battery size of 10 is balanced with 3-5-2 distribution."""
        mock_pool = [
            MockWall(i, f"slug-{i}", "beginner") for i in range(1, 10)
        ] + [
            MockWall(i, f"slug-{i}", "intermediate") for i in range(10, 25)
        ] + [
            MockWall(i, f"slug-{i}", "advanced") for i in range(25, 35)
        ]

        selected = assemble_battery_specimens(mock_pool, target_count=10)
        self.assertEqual(len(selected), 10)

        diffs = [w.difficulty for w in selected]
        self.assertEqual(diffs.count("beginner"), 3)
        self.assertEqual(diffs.count("intermediate"), 5)
        self.assertEqual(diffs.count("advanced"), 2)

    def test_assemble_battery_custom_size(self):
        """Assessor can define a custom battery count (e.g. 6 or 15)."""
        mock_pool = [
            MockWall(i, f"slug-{i}", "beginner") for i in range(1, 10)
        ] + [
            MockWall(i, f"slug-{i}", "intermediate") for i in range(10, 25)
        ] + [
            MockWall(i, f"slug-{i}", "advanced") for i in range(25, 35)
        ]

        # Test custom size 6
        selected_6 = assemble_battery_specimens(mock_pool, target_count=6)
        self.assertEqual(len(selected_6), 6)

        # Test custom size 12
        selected_12 = assemble_battery_specimens(mock_pool, target_count=12)
        self.assertEqual(len(selected_12), 12)

    def test_assemble_battery_empty_pool(self):
        """Empty pool safely returns empty selection without crashing."""
        selected = assemble_battery_specimens([], target_count=10)
        self.assertEqual(selected, [])

    # --- Unit Tests: Side-by-Side Anti-Collusion Randomization ---

    def test_generate_student_battery_sequence_deterministic_per_student(self):
        """Same student session seed maintains the exact sequence upon refresh."""
        slugs = [f"specimen-{i}" for i in range(1, 15)]
        seed = "TEST-BATTERY-101:candidate_session_abc"

        seq1 = generate_student_battery_sequence(slugs, seed, target_count=10)
        seq2 = generate_student_battery_sequence(slugs, seed, target_count=10)

        self.assertEqual(seq1, seq2)
        self.assertEqual(len(seq1), 10)

    def test_generate_student_battery_sequence_side_by_side_collusion_prevention(self):
        """Two adjacent candidates (Desk 1 vs Desk 2) receive different sequences."""
        slugs = [f"specimen-{i}" for i in range(1, 11)]
        battery = "COHORT-EXAM-2026"
        student_a = "Desk-1-Alice"
        student_b = "Desk-2-Bob"

        seq_a = generate_student_battery_sequence(slugs, f"{battery}:{student_a}", target_count=10)
        seq_b = generate_student_battery_sequence(slugs, f"{battery}:{student_b}", target_count=10)

        # They must receive the same set of specimens, but different orders
        self.assertEqual(set(seq_a), set(seq_b))
        self.assertNotEqual(seq_a, seq_b, "Adjacent candidates should not receive identical specimen ordering!")

    # --- Unit Tests: Dry-Run Tutorial Data & Skip Toggle ---

    def test_dry_run_calibration_data(self):
        """Dry-run tutorial returns 4 operational steps, skip button label, and advisory."""
        data = get_dry_run_calibration_data()
        self.assertIn("steps", data)
        self.assertEqual(len(data["steps"]), 4)
        self.assertIn("skip_label", data)
        self.assertIn("Skip Practice", data["skip_label"])
        self.assertIn("advisory", data)
        self.assertIn("unscored", data["advisory"].lower())

    # --- Unit Tests: Cohort Intelligence & Blindspot Detection ---

    def test_analyze_cohort_intelligence_empty(self):
        """Empty attempt list returns default safe diagnostics."""
        result = analyze_cohort_intelligence([], {})
        self.assertEqual(result["total_attempts"], 0)
        self.assertEqual(result["cohort_avg_score"], 0.0)

    # --- Integration Tests: Flask Endpoints ---

    def test_api_create_battery(self):
        """Assessor can generate an assessment battery defining custom battery size."""
        with self.app.app_context():
            resp = self.client.post("/api/skill-assessment/battery/create", json={
                "code": "TEST-BATTERY-1",
                "title": "Field Test Battery 1",
                "battery_size": 8,
                "randomize_order": True,
                "enable_dry_run": True,
                "target_cohort": "TEST-CLASS"
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
            self.assertEqual(data["battery"]["battery_size"], 8)
            self.assertTrue(data["battery"]["randomize_order"])
            self.assertTrue(data["battery"]["enable_dry_run"])

    def test_battery_start_routes_to_dry_run_first(self):
        """Starting a battery with enable_dry_run=True directs first to practice sample."""
        with self.app.app_context():
            # Create battery
            self.client.post("/api/skill-assessment/battery/create", json={
                "code": "TEST-BATTERY-DRY",
                "title": "Dry Run Test Battery",
                "battery_size": 10,
                "randomize_order": True,
                "enable_dry_run": True
            })

            # Student starts exam
            resp = self.client.get("/skill-assessment/battery/start?code=TEST-BATTERY-DRY&student_name=TestCandidate")
            self.assertEqual(resp.status_code, 302)
            self.assertIn("dry_run=1", resp.location)

    def test_battery_start_routes_to_q1_when_dry_run_skipped(self):
        """Starting a battery with skip_dry_run=1 directs candidate straight to Question 1."""
        with self.app.app_context():
            self.client.post("/api/skill-assessment/battery/create", json={
                "code": "TEST-BATTERY-SKIP",
                "title": "Skip Test Battery",
                "battery_size": 10,
                "randomize_order": True,
                "enable_dry_run": True
            })

            resp = self.client.get("/skill-assessment/battery/start?code=TEST-BATTERY-SKIP&skip_dry_run=1&student_name=TestCandidate")
            self.assertEqual(resp.status_code, 302)
            self.assertNotIn("dry_run=1", resp.location)
            self.assertIn("battery=TEST-BATTERY-SKIP", resp.location)
            self.assertIn("q=1", resp.location)

    def test_api_curriculum_intelligence_endpoint(self):
        """Assessor curriculum intelligence endpoint returns active batteries and analytics."""
        resp = self.client.get("/api/skill-assessment/curriculum-intelligence")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("intelligence", data)
        self.assertIn("active_batteries", data)

    def test_api_evaluate_dry_run_unscored(self):
        """Submitting a dry-run attempt does not write to AssessmentAttempt database."""
        with self.app.app_context():
            wall = Wall.query.filter_by(is_skill_assessment=True, is_published=True).first()
            if not wall:
                self.skipTest("No skill assessment wall available in database.")

            initial_count = AssessmentAttempt.query.count()

            resp = self.client.post(f"/api/skill-assessment/evaluate/{wall.slug}", json={
                "pins": [{"x": 0.5, "y": 0.5, "category": "spalling", "severity": "minor"}],
                "student_name": "DryRunCandidate",
                "is_dry_run": True,
                "battery_code": "TEST-DRY-EVAL"
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["is_dry_run"])
            self.assertEqual(data["grade"], "Practice Dry-Run (Unscored)")
            self.assertIn("skip_dry_run=1", data["next_specimen_url"])

            # Verify no record created
            after_count = AssessmentAttempt.query.count()
            self.assertEqual(initial_count, after_count, "Dry-run should not create AssessmentAttempt in DB.")

if __name__ == "__main__":
    unittest.main()
