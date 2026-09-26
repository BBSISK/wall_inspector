import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "masonry-inspector-prod-secret-2026")
    db_uri = os.getenv("DATABASE_URL", "sqlite:///app.db")
    if db_uri.startswith("postgres://"):
        db_uri = db_uri.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = db_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Prevent stale connection drops on cloud PostgreSQL (Render / Supabase / AWS)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_timeout": 20,
    }

    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "stonecraft2026")
    ADMIN_PIN = os.getenv("ADMIN_PIN", "2026")

    # OAuth 2.0 Credentials (Google & Microsoft)
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
    MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")
    MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID", "common")

    # Authorized System Admin Emails
    SYSTEM_ADMIN_EMAILS = [e.strip().lower() for e in os.getenv("SYSTEM_ADMIN_EMAILS", "barry.b.sisk@gmail.com,admin@wallinspector.org,barry.sisk@wallinspector.org").split(",") if e.strip()]

    # Transactional & Alert Email Configuration
    SMTP_SERVER = os.getenv("SMTP_SERVER", os.getenv("MAIL_SERVER", ""))
    SMTP_PORT = int(os.getenv("SMTP_PORT", os.getenv("MAIL_PORT", 587)))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", os.getenv("MAIL_USERNAME", ""))
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", os.getenv("MAIL_PASSWORD", ""))
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ["true", "1", "yes"]
    SMTP_SENDER = os.getenv("SMTP_SENDER", os.getenv("MAIL_DEFAULT_SENDER", "Wall Inspector <notifications@wallinspector.org>"))
    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
