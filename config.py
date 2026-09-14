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
