import unittest
import uuid
from datetime import datetime, timezone, timedelta
from app import app, db, User, Organization, Student

class TestOAuthAndEmailAuth(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            self.test_org = Organization.query.filter_by(code="GWI-GENERAL").first()
            if not self.test_org:
                self.test_org = Organization(
                    id=str(uuid.uuid4()),
                    name="Global Masonry Academy",
                    code="GWI-GENERAL",
                    domain="masonryacademy.edu",
                    is_active=True
                )
                db.session.add(self.test_org)
                db.session.commit()
            self.org_id = self.test_org.id

    def test_oauth_login_renders_simulator_when_unconfigured(self):
        # When GOOGLE_CLIENT_ID is empty, accessing /auth/login/google renders simulator
        resp = self.client.get("/auth/login/google?role=student")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"OAuth Sandbox Simulator", resp.data)
        self.assertIn(b"Google OAuth Sandbox", resp.data)

        resp_ms = self.client.get("/auth/login/microsoft?role=class_admin")
        self.assertEqual(resp_ms.status_code, 200)
        self.assertIn(b"Microsoft 365 OAuth Sandbox", resp_ms.data)

    def test_oauth_simulate_student_enrolls_and_provisions_session(self):
        test_email = f"student_{uuid.uuid4().hex[:6]}@masonryacademy.edu"
        payload = {
            "name": "Jordan Stone",
            "email": test_email,
            "role": "student",
            "next": "/portal"
        }
        resp = self.client.post("/auth/simulate/google", data=payload, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/portal", resp.headers.get("Location", ""))

        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("user_role"), "student")
            self.assertEqual(sess.get("student_email"), test_email)
            self.assertEqual(sess.get("auth_provider"), "google")

        with self.app.app_context():
            user = User.query.filter_by(email=test_email).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.role, "student")
            self.assertEqual(user.auth_provider, "google")

            student = Student.query.filter_by(email=test_email).first()
            self.assertIsNotNone(student)
            self.assertEqual(student.name, "Jordan Stone")

            # Clean up
            db.session.delete(student)
            db.session.delete(user)
            db.session.commit()

    def test_oauth_simulate_class_admin_provisions_session(self):
        test_email = f"instructor_{uuid.uuid4().hex[:6]}@masonryacademy.edu"
        payload = {
            "name": "Dr. Sarah Mason",
            "email": test_email,
            "role": "class_admin",
            "next": "/admin/class"
        }
        resp = self.client.post("/auth/simulate/microsoft", data=payload, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/class", resp.headers.get("Location", ""))

        with self.client.session_transaction() as sess:
            self.assertTrue(sess.get("is_admin"))
            self.assertTrue(sess.get("is_class_admin"))
            self.assertEqual(sess.get("user_role"), "class_admin")
            self.assertEqual(sess.get("auth_provider"), "microsoft")

        with self.app.app_context():
            user = User.query.filter_by(email=test_email).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.role, "class_admin")
            self.assertEqual(user.auth_provider, "microsoft")

            # Clean up
            db.session.delete(user)
            db.session.commit()

    def test_oauth_simulate_system_admin_access(self):
        test_email = f"sys_{uuid.uuid4().hex[:6]}@wallinspector.org"
        payload = {
            "name": "Director Barry",
            "email": test_email,
            "role": "system_admin",
            "next": "/admin/system"
        }
        resp = self.client.post("/auth/simulate/google", data=payload, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/system", resp.headers.get("Location", ""))

        with self.client.session_transaction() as sess:
            self.assertTrue(sess.get("is_admin"))
            self.assertTrue(sess.get("is_system_admin"))
            self.assertTrue(sess.get("is_class_admin"))
            self.assertEqual(sess.get("user_role"), "system_admin")

        with self.app.app_context():
            user = User.query.filter_by(email=test_email).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.role, "system_admin")

            # Clean up
            db.session.delete(user)
            db.session.commit()

    def test_unapproved_class_admin_redirects_to_pending_approval(self):
        test_email = f"pending_{uuid.uuid4().hex[:6]}@unapproved.test"
        with self.app.app_context():
            unapproved_user = User(
                email=test_email,
                name="Pending Instructor",
                role="class_admin",
                organization_id=self.org_id,
                auth_provider="google",
                is_approved=False,
                is_active=True
            )
            db.session.add(unapproved_user)
            db.session.commit()

        payload = {
            "name": "Pending Instructor",
            "email": test_email,
            "role": "class_admin",
            "next": "/admin/class"
        }
        resp = self.client.post("/auth/simulate/google", data=payload, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/pending-approval", resp.headers.get("Location", ""))

        # Verify pending page renders
        pending_resp = self.client.get(resp.headers.get("Location"))
        self.assertEqual(pending_resp.status_code, 200)
        self.assertIn(b"Authorization Pending Approval", pending_resp.data)

        # Clean up
        with self.app.app_context():
            User.query.filter_by(email=test_email).delete()
            db.session.commit()

    def test_email_fallback_otp_request_and_verification_flow(self):
        test_email = f"emailuser_{uuid.uuid4().hex[:6]}@institution.test"

        # 1. Request OTP
        req_payload = {
            "email": test_email,
            "role": "class_admin",
            "next": "/admin/class"
        }
        req_resp = self.client.post("/auth/email/request", data=req_payload)
        self.assertEqual(req_resp.status_code, 200)
        self.assertIn(b"Enter Verification Code", req_resp.data)

        # Retrieve generated OTP from database
        otp_code = None
        with self.app.app_context():
            user = User.query.filter_by(email=test_email).first()
            self.assertIsNotNone(user)
            self.assertIsNotNone(user.otp_code)
            self.assertEqual(len(user.otp_code), 6)
            otp_code = user.otp_code

        # 2. Test Invalid OTP
        bad_verify_resp = self.client.post("/auth/email/verify", data={
            "email": test_email,
            "otp_code": "000000",
            "next": "/admin/class"
        })
        self.assertEqual(bad_verify_resp.status_code, 400)
        self.assertIn(b"Invalid or expired passcode", bad_verify_resp.data)

        # 3. Test Valid OTP
        good_verify_resp = self.client.post("/auth/email/verify", data={
            "email": test_email,
            "otp_code": otp_code,
            "next": "/admin/class"
        }, follow_redirects=False)
        self.assertEqual(good_verify_resp.status_code, 302)
        self.assertIn("/admin/class", good_verify_resp.headers.get("Location", ""))

        with self.client.session_transaction() as sess:
            self.assertTrue(sess.get("is_admin"))
            self.assertEqual(sess.get("auth_provider"), "email")

        # Clean up
        with self.app.app_context():
            User.query.filter_by(email=test_email).delete()
            db.session.commit()

    def test_auth_logout_clears_all_sessions(self):
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
            sess["student_id"] = "test-student-id"
            sess["user_role"] = "system_admin"

        resp = self.client.get("/auth/logout", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        with self.client.session_transaction() as sess:
            self.assertNotIn("is_admin", sess)
            self.assertNotIn("student_id", sess)
            self.assertNotIn("user_role", sess)

if __name__ == "__main__":
    unittest.main()
