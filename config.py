import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "masonry-inspector-prod-secret-2026")
    db_uri = os.getenv("DATABASE_URL", "sqlite:///app.db")
    if db_uri.startswith("postgres://"):
        db_uri = db_uri.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = db_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False
