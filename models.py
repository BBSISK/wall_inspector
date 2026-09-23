import os
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
    image_filename = db.Column(db.String(255), nullable=True)
    image_url_direct = db.Column(db.String(500), nullable=True)
    is_published = db.Column(db.Boolean, default=True)
    is_skill_assessment = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        if self.image_url_direct:
            url = self.image_url_direct
        elif self.image_filename:
            url = f"/static/img/walls/{self.image_filename}"
        else:
            url = "https://images.unsplash.com/photo-1541888946425-d0fbb186c5f8?auto=format&fit=crop&w=1200&q=80"

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
            "is_published": self.is_published,
            "is_skill_assessment": bool(self.is_skill_assessment)
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
    tolerance_radius = db.Column(db.Float, default=0.06)
    category = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), default="moderate")
    remedial_action = db.Column(db.String(150), default="repoint_lime")
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
            "tolerance_radius": getattr(self, 'tolerance_radius', 0.06) or 0.06,
            "category": self.category,
            "severity": self.severity,
            "remedial_action": self.remedial_action,
            "title": self.title,
            "explanation": self.explanation
        }

class AssessmentAttempt(db.Model):
    __tablename__ = "assessment_attempts"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    wall_id = db.Column(db.String(36), db.ForeignKey("walls.id"), nullable=False)
    student_session_id = db.Column(db.String(100), nullable=False)
    cohort_code = db.Column(db.String(50), default="GENERAL")
    assignment_code = db.Column(db.String(50), nullable=True)
    student_name = db.Column(db.String(100), default="Anonymous")
    submitted_markers = db.Column(db.JSON)
    true_positives = db.Column(db.Integer, default=0)
    false_positives = db.Column(db.Integer, default=0)
    false_negatives = db.Column(db.Integer, default=0)
    score_percentage = db.Column(db.Float, default=0.0)
    passed = db.Column(db.Boolean, default=False)
    feedback_notes = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

assignment_walls = db.Table(
    "assignment_walls",
    db.Column("assignment_id", db.String(36), db.ForeignKey("assignments.id"), primary_key=True),
    db.Column("wall_id", db.String(36), db.ForeignKey("walls.id"), primary_key=True)
)

class Assignment(db.Model):
    __tablename__ = "assignments"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = db.Column(db.String(30), unique=True, nullable=False)
    title = db.Column(db.String(150), nullable=False)
    wall_id = db.Column(db.String(36), nullable=True)
    time_limit_minutes = db.Column(db.Integer, default=0)
    mode = db.Column(db.String(20), default="exam")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    walls = db.relationship("Wall", secondary=assignment_walls, backref=db.backref("assignments", lazy=True))

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "title": self.title,
            "wall_id": self.wall_id,
            "time_limit_minutes": self.time_limit_minutes or 0,
            "mode": self.mode or "exam",
            "is_active": self.is_active,
            "walls_count": len(self.walls) if self.walls else (1 if self.wall_id else 0)
        }

class Certificate(db.Model):
    __tablename__ = "certificates"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    certificate_code = db.Column(db.String(20), unique=True, default=lambda: "GWI-" + uuid.uuid4().hex[:8].upper())
    student_name = db.Column(db.String(100), nullable=False)
    tier = db.Column(db.String(50), default="Certified Masonry Inspector")
    average_score = db.Column(db.Float, default=0.0)
    total_walls_evaluated = db.Column(db.Integer, default=0)
    issued_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class StudentSubmission(db.Model):
    __tablename__ = "student_submissions"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    student_name = db.Column(db.String(100), nullable=False)
    student_identifier = db.Column(db.String(100), nullable=False, index=True)
    cohort_code = db.Column(db.String(50), default="GENERAL")
    title = db.Column(db.String(150), nullable=False)
    wall_type = db.Column(db.String(50), default="dry_stone")
    image_filename = db.Column(db.String(255), nullable=True)
    image_url_direct = db.Column(db.String(500), nullable=True)
    rubric_scores = db.Column(db.JSON, default=dict)
    self_critique = db.Column(db.Text, nullable=True)
    instructor_feedback = db.Column(db.Text, nullable=True)
    instructor_badge = db.Column(db.String(100), nullable=True)
    instructor_voice_url = db.Column(db.String(500), nullable=True)
    tilt_angle = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        url = self.image_url_direct or (f"/static/img/walls/{self.image_filename}" if self.image_filename else "")
        return {
            "id": self.id,
            "student_name": self.student_name,
            "student_identifier": self.student_identifier,
            "cohort_code": self.cohort_code,
            "title": self.title,
            "wall_type": self.wall_type,
            "image_url": url,
            "rubric_scores": self.rubric_scores or {},
            "self_critique": self.self_critique or "",
            "instructor_feedback": self.instructor_feedback or "",
            "instructor_badge": self.instructor_badge or "",
            "instructor_voice_url": self.instructor_voice_url or "",
            "tilt_angle": self.tilt_angle,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else ""
        }
