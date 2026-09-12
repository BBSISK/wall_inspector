import uuid
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Wall(db.Model):
    __tablename__ = "walls"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug = db.Column(db.String(100), unique=True, nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    country = db.Column(db.String(80), nullable=False)
    region = db.Column(db.String(100))
    wall_type = db.Column(db.String(50), nullable=False)
    structural_function = db.Column(db.String(50), default="boundary")
    difficulty = db.Column(db.String(20), default="beginner")
    image_filename = db.Column(db.String(255))
    image_url_direct = db.Column(db.String(500))
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        # Prefer direct Cloudinary URL, otherwise fall back to local static asset
        if self.image_url_direct:
            url = self.image_url_direct
        elif self.image_filename:
            url = f"/static/img/walls/{self.image_filename}"
        else:
            url = "https://placehold.co/600x400/1e293b/94a3b8?text=Image+Pending"

        return {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "description": self.description,
            "country": self.country,
            "region": self.region,
            "wall_type": self.wall_type,
            "structural_function": self.structural_function,
            "difficulty": self.difficulty,
            "image_filename": self.image_filename,
            "image_url": url,
            "is_published": self.is_published
        }

class Defect(db.Model):
    __tablename__ = "defects"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    wall_id = db.Column(db.String(36), db.ForeignKey("walls.id"), nullable=False)
    target_type = db.Column(db.String(20), default="bounding_box")
    x_min = db.Column(db.Float, nullable=False)
    y_min = db.Column(db.Float, nullable=False)
    x_max = db.Column(db.Float, nullable=False)
    y_max = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), default="moderate")
    title = db.Column(db.String(100), nullable=False)
    explanation = db.Column(db.Text)

    def to_dict(self):
        return {
            "id": self.id,
            "wall_id": self.wall_id,
            "target_type": self.target_type,
            "x_min": self.x_min,
            "y_min": self.y_min,
            "x_max": self.x_max,
            "y_max": self.y_max,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "explanation": self.explanation
        }

class AssessmentAttempt(db.Model):
    __tablename__ = "assessment_attempts"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    wall_id = db.Column(db.String(36), db.ForeignKey("walls.id"), nullable=False)
    student_session_id = db.Column(db.String(100), nullable=False)
    student_name = db.Column(db.String(100), default="Anonymous")
    submitted_markers = db.Column(db.JSON)
    true_positives = db.Column(db.Integer, default=0)
    false_positives = db.Column(db.Integer, default=0)
    false_negatives = db.Column(db.Integer, default=0)
    score_percentage = db.Column(db.Float, default=0.0)
    passed = db.Column(db.Boolean, default=False)
    feedback_notes = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Certificate(db.Model):
    __tablename__ = "certificates"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    certificate_code = db.Column(db.String(20), unique=True, default=lambda: "GWI-" + uuid.uuid4().hex[:8].upper())
    student_name = db.Column(db.String(100), nullable=False)
    tier = db.Column(db.String(50), default="Certified Masonry Inspector")
    average_score = db.Column(db.Float, default=0.0)
    total_walls_evaluated = db.Column(db.Integer, default=0)
    issued_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
