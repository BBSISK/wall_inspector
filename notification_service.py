import os
import smtplib
import threading
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone
import requests

logger = logging.getLogger(__name__)

def _send_email_resend(api_key, sender, recipients, subject, html_content, text_content):
    """Sends email via Resend REST API."""
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "from": sender,
        "to": recipients,
        "subject": subject,
        "html": html_content,
        "text": text_content or ""
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    if resp.status_code not in [200, 201]:
        raise RuntimeError(f"Resend API error ({resp.status_code}): {resp.text}")
    return True

def _send_email_sendgrid(api_key, sender, recipients, subject, html_content, text_content):
    """Sends email via SendGrid v3 Mail API."""
    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    sender_email = sender
    sender_name = "Wall Inspector Platform"
    if "<" in sender and ">" in sender:
        sender_name = sender.split("<")[0].strip()
        sender_email = sender.split("<")[1].split(">")[0].strip()

    payload = {
        "personalizations": [{"to": [{"email": r} for r in recipients]}],
        "from": {"email": sender_email, "name": sender_name},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text_content or "Please view this email in an HTML-compatible client."},
            {"type": "text/html", "value": html_content}
        ]
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    if resp.status_code not in [200, 202]:
        raise RuntimeError(f"SendGrid API error ({resp.status_code}): {resp.text}")
    return True

def _send_email_smtp(server, port, username, password, use_tls, sender, recipients, subject, html_content, text_content):
    """Sends email via standard Python smtplib."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    if text_content:
        msg.attach(MIMEText(text_content, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    if port == 465:
        with smtplib.SMTP_SSL(server, port, timeout=12) as smtp:
            if username and password:
                smtp.login(username, password)
            smtp.sendmail(sender, recipients, msg.as_string())
    else:
        with smtplib.SMTP(server, port, timeout=12) as smtp:
            if use_tls:
                smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.sendmail(sender, recipients, msg.as_string())
    return True

def dispatch_email(recipients, subject, html_content, text_content=None, app_config=None):
    """
    Non-blocking email dispatcher.
    Runs in a background thread to prevent latency on web requests.
    Supports Resend, SendGrid, and SMTP (Gmail, Outlook, Brevo, AWS SES).
    """
    if not recipients:
        return

    if isinstance(recipients, str):
        recipients = [r.strip() for r in recipients.split(",") if r.strip()]

    # Capture config before spawning thread
    cfg = app_config or {}
    resend_key = cfg.get("RESEND_API_KEY") or os.getenv("RESEND_API_KEY", "")
    sendgrid_key = cfg.get("SENDGRID_API_KEY") or os.getenv("SENDGRID_API_KEY", "")
    smtp_server = cfg.get("SMTP_SERVER") or os.getenv("SMTP_SERVER", os.getenv("MAIL_SERVER", ""))
    smtp_port = int(cfg.get("SMTP_PORT") or os.getenv("SMTP_PORT", os.getenv("MAIL_PORT", 587)))
    smtp_user = cfg.get("SMTP_USERNAME") or os.getenv("SMTP_USERNAME", os.getenv("MAIL_USERNAME", ""))
    smtp_pass = cfg.get("SMTP_PASSWORD") or os.getenv("SMTP_PASSWORD", os.getenv("MAIL_PASSWORD", ""))
    smtp_tls = str(cfg.get("SMTP_USE_TLS", os.getenv("SMTP_USE_TLS", "true"))).lower() in ["true", "1", "yes"]
    sender = cfg.get("SMTP_SENDER") or os.getenv("SMTP_SENDER", os.getenv("MAIL_DEFAULT_SENDER", "Wall Inspector <notifications@wallinspector.org>"))

    def _worker():
        try:
            if resend_key:
                _send_email_resend(resend_key, sender, recipients, subject, html_content, text_content)
                logger.info("Email dispatched successfully via Resend to %s", recipients)
            elif sendgrid_key:
                _send_email_sendgrid(sendgrid_key, sender, recipients, subject, html_content, text_content)
                logger.info("Email dispatched successfully via SendGrid to %s", recipients)
            elif smtp_server and smtp_user:
                _send_email_smtp(smtp_server, smtp_port, smtp_user, smtp_pass, smtp_tls, sender, recipients, subject, html_content, text_content)
                logger.info("Email dispatched successfully via SMTP (%s) to %s", smtp_server, recipients)
            else:
                # Log simulated notice if email provider not yet wired up
                print(f"\n[EMAIL NOTIFICATION SERVICE — UNCONFIGURED]")
                print(f"To: {recipients}")
                print(f"Subject: {subject}")
                print(f"Body Preview: {text_content or '(HTML content)'}")
                print(f"[Set SMTP_SERVER/SMTP_USERNAME/SMTP_PASSWORD or RESEND_API_KEY in Render to send live emails]\n")
        except Exception as e:
            logger.error("Failed to send notification email: %s", str(e), exc_info=True)
            print(f"[EMAIL DISPATCH ERROR] Failed to send email to {recipients}: {e}")

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

def notify_admin_access_requested(user_name, user_email, provider, role, admin_emails, app_url="https://wall-inspector.onrender.com", app_config=None):
    """
    Notifies all System Administrators that a new user has logged in and is awaiting access authorization.
    """
    if not admin_emails:
        return

    subject = f"[Wall Inspector] Action Required: Access Request from {user_name} ({user_email})"
    admin_system_url = f"{app_url.rstrip('/')}/admin/system"
    now_str = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")

    text_content = f"""
New Access Request Received — Wall Inspector

A new user has signed in and requires authorization before they can access administrative workstations or upload specimens:

• Name: {user_name}
• Email: {user_email}
• Identity Provider: {provider.capitalize()}
• Requested Role: {role.replace('_', ' ').title()}
• Timestamp: {now_str}

To approve or assign their role, visit the System Admin Workstation:
{admin_system_url}
"""

    html_content = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f172a; margin: 0; padding: 24px; color: #f8fafc; }}
    .card {{ max-width: 580px; margin: 0 auto; background: #1e293b; border-radius: 12px; border: 1px solid #334155; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.4); }}
    .header {{ background: linear-gradient(135deg, #1e1b4b, #0f172a); border-bottom: 2px solid #a78bfa; padding: 24px; text-align: center; }}
    .header h1 {{ margin: 0; font-size: 20px; color: #ffffff; letter-spacing: -0.5px; }}
    .badge {{ display: inline-block; background: rgba(167, 139, 250, 0.2); border: 1px solid #a78bfa; color: #c4b5fd; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; text-transform: uppercase; margin-top: 8px; }}
    .body {{ padding: 28px; }}
    .info-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; background: #0f172a; border-radius: 8px; overflow: hidden; }}
    .info-table td {{ padding: 12px 16px; border-bottom: 1px solid #1e293b; font-size: 14px; }}
    .info-table td.label {{ color: #94a3b8; font-weight: 600; width: 35%; }}
    .info-table td.val {{ color: #f8fafc; font-weight: 500; font-family: monospace; }}
    .btn {{ display: block; width: fit-content; margin: 24px auto 8px; padding: 14px 28px; background: linear-gradient(135deg, #0284c7, #0369a1); color: #ffffff !important; text-decoration: none; font-weight: 700; font-size: 14px; border-radius: 8px; text-align: center; border: 1px solid #38bdf8; }}
    .footer {{ padding: 16px 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #334155; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1>🏛️ Global Wall Inspector</h1>
      <span class="badge">Security &amp; Authorization Notification</span>
    </div>
    <div class="body">
      <h2 style="font-size: 18px; margin: 0 0 10px; color: #f8fafc;">New Access Request</h2>
      <p style="color: #cbd5e1; font-size: 14px; line-height: 1.5; margin: 0;">
        A user has signed in and is awaiting administrator authorization to access inspection catalogs and specimen ingestion workstations:
      </p>

      <table class="info-table">
        <tr>
          <td class="label">Full Name</td>
          <td class="val" style="font-family: inherit;">{user_name}</td>
        </tr>
        <tr>
          <td class="label">Email Address</td>
          <td class="val">{user_email}</td>
        </tr>
        <tr>
          <td class="label">Identity Provider</td>
          <td class="val" style="font-family: inherit;">{provider.capitalize()}</td>
        </tr>
        <tr>
          <td class="label">Requested Role</td>
          <td class="val" style="font-family: inherit; color: #38bdf8;">{role.replace('_', ' ').title()}</td>
        </tr>
        <tr>
          <td class="label">Timestamp</td>
          <td class="val" style="font-family: inherit;">{now_str}</td>
        </tr>
      </table>

      <a href="{admin_system_url}" class="btn">
        Review &amp; Authorize in System Admin Workstation &rarr;
      </a>
    </div>
    <div class="footer">
      Global Wall Inspector Platform &bull; Automated Access Sentinel
    </div>
  </div>
</body>
</html>
"""
    dispatch_email(admin_emails, subject, html_content, text_content, app_config=app_config)

def notify_user_access_approved(user_name, user_email, assigned_role, app_url="https://wall-inspector.onrender.com", app_config=None):
    """
    Notifies an individual user that their account request has been approved.
    """
    if not user_email:
        return

    subject = "[Wall Inspector] Your Account Access Has Been Approved"
    login_url = f"{app_url.rstrip('/')}/admin/login"

    text_content = f"""
Welcome to Global Wall Inspector, {user_name}!

Your account has been officially approved by a platform System Administrator.

• Account: {user_email}
• Assigned Role: {assigned_role.replace('_', ' ').title()}

You can now log in to access your administrative tools and specimen photo workstations:
{login_url}
"""

    html_content = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f172a; margin: 0; padding: 24px; color: #f8fafc; }}
    .card {{ max-width: 580px; margin: 0 auto; background: #1e293b; border-radius: 12px; border: 1px solid #334155; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.4); }}
    .header {{ background: linear-gradient(135deg, #064e3b, #0f172a); border-bottom: 2px solid #34d399; padding: 24px; text-align: center; }}
    .header h1 {{ margin: 0; font-size: 20px; color: #ffffff; letter-spacing: -0.5px; }}
    .badge {{ display: inline-block; background: rgba(52, 211, 153, 0.2); border: 1px solid #34d399; color: #34d399; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; text-transform: uppercase; margin-top: 8px; }}
    .body {{ padding: 28px; }}
    .btn {{ display: block; width: fit-content; margin: 24px auto 8px; padding: 14px 28px; background: linear-gradient(135deg, #059669, #047857); color: #ffffff !important; text-decoration: none; font-weight: 700; font-size: 14px; border-radius: 8px; text-align: center; border: 1px solid #10b981; }}
    .footer {{ padding: 16px 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #334155; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1>🏛️ Global Wall Inspector</h1>
      <span class="badge">Account Approved</span>
    </div>
    <div class="body">
      <h2 style="font-size: 18px; margin: 0 0 10px; color: #f8fafc;">Access Granted</h2>
      <p style="color: #cbd5e1; font-size: 14px; line-height: 1.5; margin: 0 0 16px;">
        Hello <strong>{user_name}</strong>, your account has been approved by a platform System Administrator.
      </p>

      <div style="background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 16px; margin: 20px 0;">
        <div style="font-size: 12px; color: #94a3b8; text-transform: uppercase; font-weight: 700; margin-bottom: 4px;">Assigned Role</div>
        <div style="font-size: 16px; color: #38bdf8; font-weight: 700;">{assigned_role.replace('_', ' ').title()}</div>
      </div>

      <p style="color: #94a3b8; font-size: 13px; margin: 0 0 20px;">
        You can now upload masonry specimens, calibrate ground-truth defects, and access administrative portals.
      </p>

      <a href="{login_url}" class="btn">
        Log In to Wall Inspector &rarr;
      </a>
    </div>
    <div class="footer">
      Global Wall Inspector Platform
    </div>
  </div>
</body>
</html>
"""
    dispatch_email([user_email], subject, html_content, text_content, app_config=app_config)
