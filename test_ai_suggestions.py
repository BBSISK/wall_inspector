import os
import io
import json
import unittest
from datetime import datetime, timezone
from app import app, db, Wall, Defect, create_app

class TestAiDefectSuggestions(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            # Create a test specimen wall
            self.test_slug = "test-ai-specimen-wall"
            wall = Wall.query.filter_by(slug=self.test_slug).first()
            if not wall:
                wall = Wall(
                    slug=self.test_slug,
                    title="Test Historical Lime Rubble Specimen",
                    description="Field trial masonry specimen for AI defect suggestion tests.",
                    country="Ireland",
                    region="Co. Clare",
                    wall_type="lime_mortar",
                    structural_function="boundary",
                    difficulty="intermediate",
                    is_published=True,
                    is_skill_assessment=True,
                    is_ai_reviewed=False
                )
                db.session.add(wall)
                db.session.commit()
            self.wall_id = wall.id

    def tearDown(self):
        with self.app.app_context():
            Defect.query.filter(Defect.wall_id == self.wall_id).delete()
            Wall.query.filter(Wall.slug == self.test_slug).delete()
            # Clean up any created upload test specimens
            upload_walls = Wall.query.filter(Wall.slug.ilike("skill-test-upload-%")).all()
            for w in upload_walls:
                Defect.query.filter_by(wall_id=w.id).delete()
                db.session.delete(w)
            db.session.commit()

    def test_wall_model_has_ai_reviewed_attributes(self):
        with self.app.app_context():
            wall = Wall.query.filter_by(slug=self.test_slug).first()
            self.assertIsNotNone(wall)
            self.assertIn("is_ai_reviewed", wall.to_dict())
            self.assertIn("ai_reviewed_at", wall.to_dict())
            self.assertFalse(wall.is_ai_reviewed)

    def test_generate_ai_defect_suggestions_direct(self):
        with self.app.app_context():
            wall = Wall.query.filter_by(slug=self.test_slug).first()
            # Call ai suggest endpoint or generate
            with self.client.session_transaction() as sess:
                sess["is_admin"] = True

            res = self.client.post(f"/api/skill-assessment/ai-suggest/{self.test_slug}")
            self.assertEqual(res.status_code, 200)
            data = json.loads(res.data.decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertGreater(data.get("count"), 0)
            self.assertTrue(data.get("is_ai_reviewed"))

            # Verify in DB
            db_wall = Wall.query.filter_by(slug=self.test_slug).first()
            self.assertTrue(db_wall.is_ai_reviewed)
            self.assertIsNotNone(db_wall.ai_reviewed_at)
            self.assertEqual(db_wall.grading_status, "auto_suggested")

            defects = Defect.query.filter_by(wall_id=db_wall.id).all()
            self.assertGreaterEqual(len(defects), 2)
            for d in defects:
                self.assertGreater(d.x_min, 0.0)
                self.assertLess(d.x_min, 1.0)
                self.assertGreater(d.y_min, 0.0)
                self.assertLess(d.y_min, 1.0)
                self.assertGreater(d.tolerance_radius, 0.0)
                self.assertTrue(bool(d.category))
                self.assertTrue(bool(d.title))
                self.assertEqual(d.provenance, "auto_suggested")

    def test_grader_can_edit_and_save_ai_suggested_defects(self):
        with self.app.app_context():
            with self.client.session_transaction() as sess:
                sess["is_admin"] = True
                sess["user_id"] = "test-assessor-id"
                sess["user_name"] = "Barry Sisk"

            # First trigger AI suggestions
            res = self.client.post(f"/api/skill-assessment/ai-suggest/{self.test_slug}")
            self.assertEqual(res.status_code, 200)

            # Now instructor reviews, adjusts a pin, and saves ground truth
            edited_payload = {
                "defects": [
                    {
                        "x": 0.45,
                        "y": 0.50,
                        "tolerance_radius": 0.09,
                        "category": "mortar_erosion",
                        "severity": "critical",
                        "remedial_action": "repoint_lime",
                        "title": "Instructor Confirmed: Bed Joint Lime Mortar Washout",
                        "explanation": "Verified deep binder erosion exceeding 25mm.",
                        "is_ai_suggested": True
                    }
                ]
            }
            save_res = self.client.post(
                f"/api/skill-assessment/grade/{self.test_slug}",
                data=json.dumps(edited_payload),
                content_type="application/json"
            )
            self.assertEqual(save_res.status_code, 200)
            save_data = json.loads(save_res.data.decode("utf-8"))
            self.assertTrue(save_data.get("success"))
            self.assertEqual(save_data.get("count"), 1)
            self.assertEqual(save_data.get("grading_status"), "auto_accepted")

            # Wall should now be marked as Auto-Accepted
            db_wall = Wall.query.filter_by(slug=self.test_slug).first()
            self.assertTrue(db_wall.is_ai_reviewed)
            self.assertEqual(db_wall.grading_status, "auto_accepted")
            self.assertEqual(db_wall.graded_by_user_name, "Barry Sisk")

            defects = Defect.query.filter_by(wall_id=db_wall.id).all()
            self.assertEqual(len(defects), 1)
            self.assertEqual(defects[0].title, "Instructor Confirmed: Bed Joint Lime Mortar Washout")
            self.assertEqual(defects[0].severity, "critical")
            self.assertEqual(defects[0].provenance, "auto_accepted")

    def test_human_graded_provenance_when_placed_from_scratch(self):
        with self.app.app_context():
            with self.client.session_transaction() as sess:
                sess["is_admin"] = True
                sess["user_name"] = "Barry Sisk"

            # Instructor marks defects directly from scratch (not AI suggested)
            scratch_payload = {
                "defects": [
                    {
                        "x": 0.30,
                        "y": 0.40,
                        "tolerance_radius": 0.08,
                        "category": "stepped_crack",
                        "severity": "severe",
                        "remedial_action": "helical_stitch",
                        "title": "Manual Expert Calibration: Stepped Fracture",
                        "explanation": "Expert hand-placed marker.",
                        "is_ai_suggested": False
                    }
                ]
            }
            res = self.client.post(
                f"/api/skill-assessment/grade/{self.test_slug}",
                data=json.dumps(scratch_payload),
                content_type="application/json"
            )
            self.assertEqual(res.status_code, 200)
            data = json.loads(res.data.decode("utf-8"))
            self.assertEqual(data.get("grading_status"), "human_graded")

            db_wall = Wall.query.filter_by(slug=self.test_slug).first()
            self.assertEqual(db_wall.grading_status, "human_graded")
            defects = Defect.query.filter_by(wall_id=db_wall.id).all()
            self.assertEqual(defects[0].provenance, "human_graded")

    def test_upload_auto_suggests_defects_and_tags_ai_reviewed(self):
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True

        fake_img = (io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"), "test_upload_ai.jpg")
        upload_data = {
            "wall_image": fake_img,
            "title": "Test Upload Dry Stone Specimen",
            "wall_type": "dry_stone",
            "difficulty": "intermediate",
            "country": "Ireland",
            "region": "Galway",
            "structural_function": "boundary",
            "grade_action": "later"
        }
        res = self.client.post(
            "/skill-assessment/admin/upload",
            data=upload_data,
            content_type="multipart/form-data",
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)

        with self.app.app_context():
            created_wall = Wall.query.filter(Wall.title == "Test Upload Dry Stone Specimen").first()
            self.assertIsNotNone(created_wall)
            # Specimen must be tagged as AI Reviewed
            self.assertTrue(created_wall.is_ai_reviewed)
            self.assertIsNotNone(created_wall.ai_reviewed_at)

            # Defects must have been suggested
            defects = Defect.query.filter_by(wall_id=created_wall.id).all()
            self.assertGreater(len(defects), 0)

            # Clean up file
            if created_wall.image_filename:
                for fld in [self.app.config.get("UPLOAD_FOLDER"), self.app.config.get("ASSESSMENT_FOLDER")]:
                    if fld:
                        p = os.path.join(fld, created_wall.image_filename)
                        if os.path.exists(p):
                            try:
                                os.remove(p)
                            except OSError:
                                pass

if __name__ == "__main__":
    unittest.main()

