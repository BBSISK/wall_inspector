import unittest
from app import app, generate_mobile_admin_token, verify_mobile_admin_token

class TestMobileAuthAndPairing(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()

    def test_token_generation_and_verification(self):
        with self.app.app_context():
            token = generate_mobile_admin_token()
            self.assertTrue(isinstance(token, str) and len(token) > 20)
            self.assertTrue(verify_mobile_admin_token(token))
            self.assertFalse(verify_mobile_admin_token("tampered-token-12345"))
            self.assertFalse(verify_mobile_admin_token(None))
            self.assertFalse(verify_mobile_admin_token(""))

    def test_unauthenticated_mobile_admin_redirects_to_login(self):
        # Client without session or token should be redirected to admin login
        response = self.client.get("/mobile/admin", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.headers.get("Location", ""))

    def test_token_authenticated_mobile_admin_direct_access(self):
        with self.app.app_context():
            valid_token = generate_mobile_admin_token()

        # Client accessing /mobile/admin?token=... directly
        response = self.client.get(f"/mobile/admin?token={valid_token}", follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        content = response.data.decode("utf-8")
        self.assertIn("Field Wall Capture", content)

        # Check session is now authenticated
        with self.client.session_transaction() as sess:
            self.assertTrue(sess.get("is_admin"))

    def test_skill_assessment_mode_direct_access(self):
        with self.app.app_context():
            valid_token = generate_mobile_admin_token()

        response = self.client.get(f"/mobile/admin?token={valid_token}&mode=skill_assessment", follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        content = response.data.decode("utf-8")
        self.assertIn("Skill Ingestion", content)
        self.assertIn("Skill Assessment Ingestion Mode", content)
        self.assertIn('checked', content)

    def test_admin_login_redirect_when_already_authenticated(self):
        # When authenticated, visiting /admin/login with next_url should redirect directly
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True

        response = self.client.get("/admin/login?next=/mobile/admin", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), "/mobile/admin")

    def test_skill_assessment_admin_renders_mobile_pair_ui(self):
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True

        response = self.client.get("/skill-assessment/admin")
        self.assertEqual(response.status_code, 200)
        content = response.data.decode("utf-8")
        self.assertIn("Connect Phone Camera", content)
        self.assertIn("modal-skill-qr", content)
        self.assertIn("openSkillQrModal", content)

    def test_promote_wall_by_slug(self):
        from app import db, Wall
        with self.app.app_context():
            slug = "test-catalog-wall-promo-slug"
            existing = Wall.query.filter_by(slug=slug).first()
            if existing:
                db.session.delete(existing)
                db.session.commit()
            w = Wall(
                slug=slug,
                title="Unassigned Catalog Wall",
                wall_type="brick_cavity",
                difficulty="medium",
                country="Ireland",
                image_filename="ashlar_quarry.jpg",
                is_published=True,
                is_skill_assessment=False
            )
            db.session.add(w)
            db.session.commit()

        with self.client.session_transaction() as sess:
            sess["is_admin"] = True

        response = self.client.get(f"/admin/walls/{slug}/promote", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/skill-assessment/admin/grade/{slug}", response.headers.get("Location", ""))

        with self.app.app_context():
            updated = Wall.query.filter_by(slug=slug).first()
            self.assertTrue(updated.is_skill_assessment)
            self.assertEqual(updated.grading_status, "auto_suggested")
            db.session.delete(updated)
            db.session.commit()

    def test_mobile_upload_defaults_to_skill_assessment(self):
        import io
        from app import db, Wall
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True

        # 1x1 valid transparent PNG
        dummy_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'
        data = {
            "title": "Field Test Auto Skill Capture",
            "wall_type": "brick_cavity",
            "difficulty": "medium",
            "wall_image": (io.BytesIO(dummy_png), "auto_field_test.png")
            # is_skill_assessment intentionally omitted to test automatic default
        }

        response = self.client.post("/mobile/admin/upload", data=data, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        res_json = response.get_json()
        self.assertTrue(res_json.get("success"))
        created_slug = res_json.get("wall", {}).get("slug")
        self.assertTrue(res_json.get("wall", {}).get("is_skill_assessment"))

        with self.app.app_context():
            created_wall = Wall.query.filter_by(slug=created_slug).first()
            if created_wall:
                self.assertTrue(created_wall.is_skill_assessment)
                self.assertEqual(created_wall.grading_status, "auto_suggested")
                db.session.delete(created_wall)
                db.session.commit()

if __name__ == "__main__":
    unittest.main()

