import unittest
import uuid
from app import app, db, Organization, User, Student, Assignment, AssessmentAttempt, Wall

class TestRolesAndOrganizations(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            # Create a test organization
            self.test_org_code = f"TEST-ORG-{uuid.uuid4().hex[:4].upper()}"
            self.test_org = Organization(
                id=str(uuid.uuid4()),
                name="Test Conservation Institute",
                code=self.test_org_code,
                domain="conservation.test",
                contact_email="director@conservation.test",
                is_active=True
            )
            db.session.add(self.test_org)

            # Create a test system admin user
            self.sys_user = User(
                id=str(uuid.uuid4()),
                email=f"sys_{uuid.uuid4().hex[:4]}@platform.test",
                name="Platform Sys Admin",
                role="system_admin",
                organization_id=self.test_org.id,
                is_approved=True,
                is_active=True
            )
            db.session.add(self.sys_user)

            # Create a test class admin user
            self.class_user = User(
                id=str(uuid.uuid4()),
                email=f"instructor_{uuid.uuid4().hex[:4]}@conservation.test",
                name="Class Instructor",
                role="class_admin",
                organization_id=self.test_org.id,
                is_approved=True,
                is_active=True
            )
            db.session.add(self.class_user)
            db.session.commit()

            self.org_id = self.test_org.id
            self.sys_user_id = self.sys_user.id
            self.class_user_id = self.class_user.id

    def tearDown(self):
        with self.app.app_context():
            # Clean up test students and assignments
            Student.query.filter_by(organization_id=self.org_id).delete()
            Assignment.query.filter_by(organization_id=self.org_id).delete()
            User.query.filter(User.id.in_([self.sys_user_id, self.class_user_id])).delete()
            Organization.query.filter_by(id=self.org_id).delete()
            db.session.commit()

    def test_organization_and_user_model_integrity(self):
        with self.app.app_context():
            org = db.session.get(Organization, self.org_id)
            self.assertIsNotNone(org)
            self.assertEqual(org.code, self.test_org_code)
            self.assertIn("students_count", org.to_dict())

            user = db.session.get(User, self.class_user_id)
            self.assertIsNotNone(user)
            self.assertEqual(user.role, "class_admin")
            self.assertEqual(user.organization_id, self.org_id)
            self.assertIn("organization_name", user.to_dict())

    def test_unauthenticated_access_redirects_to_login(self):
        resp_class = self.client.get("/admin/class")
        self.assertEqual(resp_class.status_code, 302)
        self.assertIn("/admin/login", resp_class.headers.get("Location", ""))

        resp_sys = self.client.get("/admin/system")
        self.assertEqual(resp_sys.status_code, 302)
        self.assertIn("/admin/login", resp_sys.headers.get("Location", ""))

    def test_class_admin_access_allowed_on_class_dashboard(self):
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
            sess["is_class_admin"] = True
            sess["user_role"] = "class_admin"
            sess["organization_id"] = self.org_id

        resp = self.client.get(f"/admin/class?org_id={self.org_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Test Conservation Institute", resp.data)
        self.assertIn(b"Student Roster", resp.data)

    def test_class_admin_forbidden_on_system_dashboard(self):
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
            sess["is_class_admin"] = True
            sess["user_role"] = "class_admin"
            sess["organization_id"] = self.org_id

        resp = self.client.get("/admin/system")
        self.assertEqual(resp.status_code, 403)

    def test_system_admin_access_allowed_on_both_dashboards(self):
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
            sess["is_system_admin"] = True
            sess["user_role"] = "system_admin"
            sess["organization_id"] = self.org_id

        # System admin can access /admin/system
        resp_sys = self.client.get("/admin/system")
        self.assertEqual(resp_sys.status_code, 200)
        self.assertIn(b"Platform Command", resp_sys.data)

        # System admin can access /admin/class
        resp_class = self.client.get(f"/admin/class?org_id={self.org_id}")
        self.assertEqual(resp_class.status_code, 200)
        self.assertIn(b"Test Conservation Institute", resp_class.data)

    def test_class_admin_enroll_student_with_pin(self):
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
            sess["is_class_admin"] = True
            sess["user_role"] = "class_admin"
            sess["organization_id"] = self.org_id

        payload = {
            "name": "Jane Mason",
            "email": "jmason@conservation.test",
            "cohort_code": "HERITAGE-2026",
            "pin": "7821",
            "org_id": self.org_id
        }
        resp = self.client.post("/admin/class/students/add", data=payload, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            student = Student.query.filter_by(email="jmason@conservation.test").first()
            self.assertIsNotNone(student)
            self.assertEqual(student.name, "Jane Mason")
            self.assertEqual(student.pin, "7821")
            self.assertEqual(student.cohort_code, "HERITAGE-2026")
            self.assertEqual(student.organization_id, self.org_id)

    def test_class_admin_provision_battery(self):
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
            sess["is_class_admin"] = True
            sess["user_role"] = "class_admin"
            sess["organization_id"] = self.org_id

        payload = {
            "title": "Heritage Diagnostic Sprint",
            "battery_size": 10,
            "time_limit_minutes": 30,
            "enable_dry_run": "1",
            "randomize_order": "1",
            "director_notes": "Look for stepped cracks and efflorescence.",
            "org_id": self.org_id
        }
        resp = self.client.post("/admin/class/battery/create", data=payload, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            assignment = Assignment.query.filter_by(organization_id=self.org_id).first()
            self.assertIsNotNone(assignment)
            self.assertEqual(assignment.title, "Heritage Diagnostic Sprint")
            self.assertEqual(assignment.battery_size, 10)
            self.assertEqual(assignment.time_limit_minutes, 30)
            self.assertTrue(assignment.code.startswith("BAT-"))

    def test_class_admin_export_csv(self):
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
            sess["is_class_admin"] = True
            sess["user_role"] = "class_admin"
            sess["organization_id"] = self.org_id

        resp = self.client.get(f"/admin/class/export-csv?org_id={self.org_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "text/csv")
        self.assertIn(b"School Name,Cohort,Student Name", resp.data)

    def test_system_admin_onboard_organization(self):
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
            sess["is_system_admin"] = True
            sess["user_role"] = "system_admin"

        new_code = f"NEW-GUILD-{uuid.uuid4().hex[:4].upper()}"
        payload = {
            "name": "Guild of Master Masons",
            "code": new_code,
            "domain": "mastermasons.org",
            "contact_email": "guild@mastermasons.org"
        }
        resp = self.client.post("/admin/system/organizations/create", data=payload, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            created_org = Organization.query.filter_by(code=new_code).first()
            self.assertIsNotNone(created_org)
            self.assertEqual(created_org.name, "Guild of Master Masons")
            # Clean up
            db.session.delete(created_org)
            db.session.commit()

    def test_system_admin_user_approval_and_role_management(self):
        with self.client.session_transaction() as sess:
            sess["is_admin"] = True
            sess["is_system_admin"] = True
            sess["user_role"] = "system_admin"

        # Toggle approval
        resp = self.client.post(
            "/admin/system/users/approve",
            json={"user_id": self.class_user_id, "action": "toggle_approval"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["user"]["is_approved"])

        # Change role to system_admin
        resp_role = self.client.post(
            "/admin/system/users/approve",
            json={"user_id": self.class_user_id, "action": "set_role", "role": "system_admin"}
        )
        self.assertEqual(resp_role.status_code, 200)
        data_role = resp_role.get_json()
        self.assertEqual(data_role["user"]["role"], "system_admin")

if __name__ == "__main__":
    unittest.main()
