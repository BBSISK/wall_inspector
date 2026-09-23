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

if __name__ == "__main__":
    unittest.main()

