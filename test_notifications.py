import unittest
import uuid
from unittest.mock import patch, MagicMock
from app import app, db, User, Organization
from notification_service import (
    dispatch_email,
    notify_admin_access_requested,
    notify_user_access_approved,
    _send_email_resend,
    _send_email_sendgrid
)

class TestNotificationService(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_unconfigured_dispatch_does_not_crash(self):
        """When no email credentials exist, dispatcher falls back gracefully without errors."""
        try:
            dispatch_email(
                recipients=["test@example.com"],
                subject="Test Subject",
                html_content="<p>Test</p>",
                text_content="Test",
                app_config={}
            )
        except Exception as e:
            self.fail(f"dispatch_email raised an exception when unconfigured: {e}")

    @patch("requests.post")
    def test_resend_api_integration(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        result = _send_email_resend(
            api_key="re_test_key_123",
            sender="noreply@example.com",
            recipients=["admin@example.com"],
            subject="Test Subject",
            html_content="<p>Hello</p>",
            text_content="Hello"
        )
        self.assertTrue(result)
        self.assertTrue(mock_post.called)
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["json"]["subject"], "Test Subject")
        self.assertEqual(call_kwargs["json"]["to"], ["admin@example.com"])

    @patch("requests.post")
    def test_sendgrid_api_integration(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_post.return_value = mock_resp

        result = _send_email_sendgrid(
            api_key="SG.test_key_123",
            sender="Wall Inspector <noreply@example.com>",
            recipients=["admin@example.com"],
            subject="Test Subject",
            html_content="<p>Hello</p>",
            text_content="Hello"
        )
        self.assertTrue(result)
        self.assertTrue(mock_post.called)
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["json"]["subject"], "Test Subject")

    @patch("notification_service.dispatch_email")
    def test_notify_admin_access_requested_called(self, mock_dispatch):
        notify_admin_access_requested(
            user_name="John Doe",
            user_email="john@school.edu",
            provider="google",
            role="class_admin",
            admin_emails=["barry.b.sisk@gmail.com"],
            app_url="https://wall-inspector.onrender.com"
        )
        self.assertTrue(mock_dispatch.called)
        args, kwargs = mock_dispatch.call_args
        self.assertIn("barry.b.sisk@gmail.com", args[0])
        self.assertIn("John Doe", args[1])
        self.assertIn("Class Admin", args[3] if len(args) > 3 else "")

    @patch("notification_service.dispatch_email")
    def test_notify_user_access_approved_called(self, mock_dispatch):
        notify_user_access_approved(
            user_name="John Doe",
            user_email="john@school.edu",
            assigned_role="class_admin",
            app_url="https://wall-inspector.onrender.com"
        )
        self.assertTrue(mock_dispatch.called)
        args, kwargs = mock_dispatch.call_args
        self.assertEqual(args[0], ["john@school.edu"])
        self.assertIn("Approved", args[1])

if __name__ == "__main__":
    unittest.main()
