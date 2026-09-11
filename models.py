import uuid
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Float, ForeignKey, Integer, String, Text, Boolean, JSON
from sqlalchemy.orm import relationship

db = SQLAlchemy()


def generate_uuid():
    return str(uuid.uuid4())


class Wall(db.Model):
    __tablename__ = "walls"

    id = db.Column(String(36), primary_key=True, default=generate_uuid)
    slug = db.Column(String(80), unique=True, nullable=False, index=True)
    title = db.Column(String(150), nullable=False)
    description = db.Column(Text, nullable=True)

    # Geographic & structural classification
    country = db.Column(String(100), nullable=False)
    region = db.Column(String(100), nullable=True)

    # 'dry_stone', 'lime_mortar', 'brick_cavity', 'ashlar', 'rubble', 'gabion'
    wall_type = db.Column(String(50), nullable=False, index=True)

    # 'boundary', 'retaining', 'load_bearing', 'parapet'
    structural_function = db.Column(String(50), nullable=True)

    # 'beginner', 'intermediate', 'advanced'
    difficulty = db.Column(String(20), default="beginner", nullable=False)

    # Image asset path (served from static/img/walls/...)
    image_filename = db.Column(String(255), nullable=False)
    image_width = db.Column(Integer, nullable=True)
    image_height = db.Column(Integer, nullable=True)

    is_published = db.Column(Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    defects = relationship("Defect", back_populates="wall", cascade="all, delete-orphan")
    assessments = relationship("AssessmentAttempt", back_populates="wall")

    def to_dict(self, include_defects=False):
        data = {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "description": self.description,
            "country": self.country,
            "region": self.region,
            "wall_type": self.wall_type,
            "structural_function": self.structural_function,
            "difficulty": self.difficulty,
            "image_url": f"/static/img/walls/{self.image_filename}",
            "defect_count": len(self.defects) if self.defects else 0,
        }
        if include_defects:
            data["defects"] = [d.to_dict() for d in self.defects]
        return data


class Defect(db.Model):
    """
    Ground-truth defect zones created by instructors.
    All coordinates are normalized floats between 0.0 and 1.0.
    """
    __tablename__ = "defects"

    id = db.Column(String(36), primary_key=True, default=generate_uuid)
    wall_id = db.Column(String(36), ForeignKey("walls.id"), nullable=False, index=True)

    # 'pin' or 'bounding_box'
    target_type = db.Column(String(20), default="bounding_box", nullable=False)

    # Normalized bounding coordinates (0.000 to 1.000)
    x_min = db.Column(Float, nullable=False)
    y_min = db.Column(Float, nullable=False)
    x_max = db.Column(Float, nullable=False)
    y_max = db.Column(Float, nullable=False)

    tolerance_radius = db.Column(Float, default=0.04, nullable=True)

    # Classification taxonomy
    category = db.Column(String(60), nullable=False)
    severity = db.Column(String(20), default="moderate")  # 'minor', 'moderate', 'critical'

    # Educational notes
    title = db.Column(String(120), nullable=False)
    explanation = db.Column(Text, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    wall = relationship("Wall", back_populates="defects")

    def to_dict(self):
        return {
            "id": self.id,
            "target_type": self.target_type,
            "x_min": self.x_min,
            "y_min": self.y_min,
            "x_max": self.x_max,
            "y_max": self.y_max,
            "tolerance_radius": self.tolerance_radius,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "explanation": self.explanation,
        }


class AssessmentAttempt(db.Model):
    """
    Records student submissions, marker coordinates, and evaluation scores.
    """
    __tablename__ = "assessment_attempts"

    id = db.Column(String(36), primary_key=True, default=generate_uuid)
    wall_id = db.Column(String(36), ForeignKey("walls.id"), nullable=False, index=True)

    student_session_id = db.Column(String(100), nullable=False, index=True)
    student_name = db.Column(String(100), nullable=True)

    # JSON payload of student clicks/boxes
    submitted_markers = db.Column(JSON, nullable=False)

    # Scores
    true_positives = db.Column(Integer, default=0)
    false_positives = db.Column(Integer, default=0)
    false_negatives = db.Column(Integer, default=0)
    score_percentage = db.Column(Float, default=0.0)
    passed = db.Column(Boolean, default=False)

    feedback_notes = db.Column(JSON, nullable=True)
    completed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    wall = relationship("Wall", back_populates="assessments")


class Certificate(db.Model):
    """
    Issued when a student satisfies certification criteria.
    """
    __tablename__ = "certificates"

    id = db.Column(String(36), primary_key=True, default=generate_uuid)
    certificate_code = db.Column(String(32), unique=True, nullable=False, index=True)
    student_name = db.Column(String(120), nullable=False)
    tier = db.Column(String(60), nullable=False)
    average_score = db.Column(Float, nullable=False)
    total_walls_evaluated = db.Column(Integer, nullable=False)
    issued_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "certificate_code": self.certificate_code,
            "student_name": self.student_name,
            "tier": self.tier,
            "average_score": round(self.average_score, 1),
            "total_walls_evaluated": self.total_walls_evaluated,
            "issued_at": self.issued_at.strftime("%Y-%m-%d"),
        }