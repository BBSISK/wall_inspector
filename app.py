import os
import uuid
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify, redirect, url_for
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader
from config import Config
from models import db, Wall, Defect, AssessmentAttempt, Certificate

# Configure Cloudinary automatically if environment variable is set
cloudinary_url = os.getenv("CLOUDINARY_URL", "").strip()
if cloudinary_url:
    if cloudinary_url.startswith("CLOUDINARY_URL="):
        cloudinary_url = cloudinary_url.replace("CLOUDINARY_URL=", "", 1).strip()
    cloudinary.config(cloudinary_url=cloudinary_url)

TAXONOMY_BY_WALL_TYPE = {
    "brick_cavity": [
        {"id": "efflorescence", "label": "Efflorescence (Salt Leaching)"},
        {"id": "spalling", "label": "Frost-Thaw Spalling (Blown Brick Faces)"},
        {"id": "mortar_erosion", "label": "Bed Joint Mortar Washout / Erosion"},
        {"id": "stepped_crack", "label": "Stepped Settlement Shear Crack"},
        {"id": "expansion_failure", "label": "Vertical Thermal Expansion Fracture"}
    ],
    "dry_stone": [
        {"id": "coping_displacement", "label": "Coping Stone Dislodgement / Loss"},
        {"id": "hearting_washout", "label": "Hearting / Core Stone Voiding"},
        {"id": "lateral_bulge", "label": "Out-of-Plumb Lateral Bulge"},
        {"id": "through_stone_failure", "label": "Missing or Fractured Through-Stone"},
        {"id": "base_subsidence", "label": "Differential Foundation / Ground Settlement"},
        {"id": "vegetation_roots", "label": "Invasive Root Wedge Disruption"}
    ],
    "lime_mortar": [
        {"id": "lime_washout", "label": "Deep Joint Lime Washout"},
        {"id": "render_delamination", "label": "Lime Render Hollow / Delamination"},
        {"id": "ivy_penetration", "label": "Structural Ivy / Biological Root Penetration"},
        {"id": "rubble_voiding", "label": "Internal Core Rubble Voiding"}
    ],
    "ashlar": [
        {"id": "ashlar_spall", "label": "Surface Face Delamination / Exfoliation"},
        {"id": "joint_separation", "label": "Fine Ashlar Joint Separation"},
        {"id": "iron_cramp_burst", "label": "Oxidized Iron Cramp Stone Fracture"}
    ]
}

def calculate_iou(box_a, box_b):
    x_left = max(box_a["x_min"], box_b["x_min"])
    y_top = max(box_a["y_min"], box_b["y_min"])
    x_right = min(box_a["x_max"], box_b["x_max"])
    y_bottom = min(box_a["y_max"], box_b["y_max"])

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    intersection = (x_right - x_left) * (y_bottom - y_top)
    area_a = (box_a["x_max"] - box_a["x_min"]) * (box_a["y_max"] - box_a["y_min"])
    area_b = (box_b["x_max"] - box_b["x_min"]) * (box_b["y_max"] - box_b["y_min"])

    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    upload_folder = os.path.join(app.root_path, "static", "img", "walls")
    os.makedirs(upload_folder, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = upload_folder
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    db.init_app(app)

    with app.app_context():
        db.create_all()

        # Seed baseline Industrial Brick Wall if missing
        brick = Wall.query.filter_by(slug="industrial-brick-efflorescence").first()
        if not brick:
            brick = Wall(
                slug="industrial-brick-efflorescence",
                title="Industrial Red Brick Cavity Wall",
                description="Red brick masonry exhibiting heavy white crystalline efflorescence and weathered bed joint pointing.",
                country="United Kingdom",
                region="Manchester",
                wall_type="brick_cavity",
                structural_function="load_bearing",
                difficulty="beginner",
                image_filename="brick_efflorescence_01.jpg",
                is_published=True
            )
            db.session.add(brick)
            db.session.commit()

            gt = Defect(
                wall_id=brick.id,
                target_type="bounding_box",
                x_min=0.18,
                y_min=0.20,
                x_max=0.82,
                y_max=0.80,
                category="efflorescence",
                severity="moderate",
                title="Crystalline Salt Efflorescence",
                explanation="White salt deposits migrated through porous brickwork during evaporative drying."
            )
            db.session.add(gt)
            db.session.commit()

    @app.route("/")
    def index():
        walls = Wall.query.filter_by(is_published=True).all()
        return render_template("index.html", walls=[w.to_dict() for w in walls])

    @app.route("/admin/walls/<wall_id>/delete", methods=["POST"])
    def admin_delete_wall(wall_id):
        wall = Wall.query.get_or_404(wall_id)
        if wall.image_filename:
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], wall.image_filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass

        Defect.query.filter_by(wall_id=wall.id).delete()
        AssessmentAttempt.query.filter_by(wall_id=wall.id).delete()
        db.session.delete(wall)
        db.session.commit()
        return redirect(url_for("index"))

    @app.route("/dashboard")
    def dashboard():
        attempts_raw = AssessmentAttempt.query.all()
        attempts_raw.sort(key=lambda x: getattr(x, 'created_at', None) or getattr(x, 'timestamp', datetime.min), reverse=True)
        attempts = attempts_raw[:25]
        certificates = Certificate.query.all()

        total_attempts = len(attempts_raw)
        total_passed = sum(1 for a in attempts_raw if getattr(a, 'passed', False))
        pass_rate = round((total_passed / total_attempts * 100), 1) if total_attempts > 0 else 0

        return render_template(
            "dashboard.html",
            attempts=attempts,
            certificates=certificates,
            total_attempts=total_attempts,
            pass_rate=pass_rate
        )

    @app.route("/admin/walls/new", methods=["GET", "POST"])
    def admin_create_wall():
        if request.method == "GET":
            return render_template("admin_create_wall.html")

        file = request.files.get("wall_image")
        if not file or not file.filename:
            return "No image selected", 400

        title = request.form.get("title", "Untitled Wall").strip()
        slug = secure_filename(title.lower().replace(" ", "-")) + "-" + uuid.uuid4().hex[:6]
        
        image_url_direct = None
        filename = None

        # Upload directly to Cloudinary if configured
        if os.getenv("CLOUDINARY_URL"):
            upload_result = cloudinary.uploader.upload(
                file,
                folder="wall_inspector",
                public_id=slug,
                overwrite=True,
                resource_type="image"
            )
            image_url_direct = upload_result.get("secure_url")
        else:
            # Fallback to local storage
            ext = os.path.splitext(file.filename)[1].lower()
            filename = f"{slug}{ext}"
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        wall = Wall(
            slug=slug,
            title=title,
            description=request.form.get("description", ""),
            country=request.form.get("country", "Unknown"),
            region=request.form.get("region", ""),
            wall_type=request.form.get("wall_type", "dry_stone"),
            structural_function=request.form.get("structural_function", "boundary"),
            difficulty=request.form.get("difficulty", "beginner"),
            image_filename=filename,
            image_url_direct=image_url_direct,
            is_published=True
        )
        db.session.add(wall)
        db.session.commit()
        return redirect(url_for("admin_tagger", wall_id=wall.id))

    @app.route("/admin/walls/<wall_id>/tagger")
    def admin_tagger(wall_id):
        wall = Wall.query.get_or_404(wall_id)
        categories = TAXONOMY_BY_WALL_TYPE.get(wall.wall_type, TAXONOMY_BY_WALL_TYPE["dry_stone"])
        return render_template("tagger.html", wall=wall.to_dict(), categories=categories)

    @app.route("/admin/walls/<wall_id>/defects", methods=["GET"])
    def get_admin_defects(wall_id):
        defects = Defect.query.filter_by(wall_id=wall_id).all()
        return jsonify([d.to_dict() for d in defects])

    @app.route("/admin/walls/<wall_id>/defects", methods=["POST"])
    def add_admin_defect(wall_id):
        wall = Wall.query.get_or_404(wall_id)
        data = request.get_json() or {}
        defect = Defect(
            wall_id=wall.id,
            target_type=data.get("target_type", "bounding_box"),
            x_min=float(data["x_min"]),
            y_min=float(data["y_min"]),
            x_max=float(data["x_max"]),
            y_max=float(data["y_max"]),
            category=data.get("category", "unspecified"),
            severity=data.get("severity", "moderate"),
            title=data.get("title", "Structural Defect"),
            explanation=data.get("explanation", "")
        )
        db.session.add(defect)
        db.session.commit()
        return jsonify(defect.to_dict()), 201

    @app.route("/admin/defects/<defect_id>", methods=["DELETE"])
    def delete_admin_defect(defect_id):
        defect = Defect.query.get_or_404(defect_id)
        db.session.delete(defect)
        db.session.commit()
        return jsonify({"status": "deleted", "id": defect_id})

    @app.route("/inspect/<wall_slug>")
    def inspect_wall(wall_slug):
        wall = Wall.query.filter_by(slug=wall_slug, is_published=True).first_or_404()
        categories = TAXONOMY_BY_WALL_TYPE.get(wall.wall_type, TAXONOMY_BY_WALL_TYPE["dry_stone"])
        return render_template("inspect.html", wall=wall.to_dict(), categories=categories)

    @app.route("/inspect/<wall_slug>/submit", methods=["POST"])
    def submit_inspection(wall_slug):
        wall = Wall.query.filter_by(slug=wall_slug, is_published=True).first_or_404()
        data = request.get_json() or {}

        submitted_markers = data.get("markers", [])
        student_name = data.get("student_name", "Inspector Candidate").strip()
        session_id = data.get("session_id", "session_default")

        ground_truth = Defect.query.filter_by(wall_id=wall.id).all()
        ground_truth_dicts = [d.to_dict() for d in ground_truth]

        matched_defect_ids = set()
        feedback = []
        false_positives = 0

        for marker in submitted_markers:
            hit = False
            for gt in ground_truth_dicts:
                iou = calculate_iou(marker, gt)
                if iou >= 0.20 and marker.get("category") == gt["category"]:
                    hit = True
                    matched_defect_ids.add(gt["id"])
                    feedback.append({
                        "title": gt["title"],
                        "category": gt["category"],
                        "status": "correct",
                        "explanation": f"Diagnostic Confirmed: {gt['explanation']}"
                    })
                    break
                elif iou >= 0.20:
                    hit = True
                    feedback.append({
                        "title": gt["title"],
                        "category": gt["category"],
                        "status": "misclassified",
                        "explanation": f"Zone located, but fault was {gt['category'].replace('_', ' ')}. {gt['explanation']}"
                    })
                    break
            if not hit:
                false_positives += 1

        true_positives = len(matched_defect_ids)
        total_defects = len(ground_truth_dicts)
        false_negatives = max(0, total_defects - true_positives)

        for gt in ground_truth_dicts:
            if gt["id"] not in matched_defect_ids and not any(f["title"] == gt["title"] for f in feedback):
                feedback.append({
                    "title": gt["title"],
                    "category": gt["category"],
                    "status": "missed",
                    "explanation": f"Missed structural fault: {gt['explanation']}"
                })

        if total_defects > 0:
            raw_score = (true_positives / total_defects) * 100
            score = max(0.0, round(raw_score - (false_positives * 15), 1))
        else:
            score = 100.0 if false_positives == 0 else 0.0

        passed = score >= 70.0

        attempt = AssessmentAttempt(
            wall_id=wall.id,
            student_session_id=session_id,
            student_name=student_name,
            submitted_markers=submitted_markers,
            true_positives=true_positives,
            false_positives=false_positives,
            false_negatives=false_negatives,
            score_percentage=score,
            passed=passed,
            feedback_notes={"items": feedback}
        )
        db.session.add(attempt)
        db.session.commit()

        student_attempts = AssessmentAttempt.query.filter_by(student_name=student_name).all()
        qualifies_for_cert = False
        cert_code = None

        if len(student_attempts) >= 2:
            avg_score = sum(a.score_percentage for a in student_attempts) / len(student_attempts)
            if avg_score >= 70.0:
                qualifies_for_cert = True
                existing_cert = Certificate.query.filter_by(student_name=student_name).first()
                if not existing_cert:
                    tier = "Level 2 Inspector (Distinction)" if avg_score >= 85.0 else "Level 1 Certified Inspector"
                    new_cert = Certificate(
                        student_name=student_name,
                        tier=tier,
                        average_score=round(avg_score, 1),
                        total_walls_evaluated=len(student_attempts)
                    )
                    db.session.add(new_cert)
                    db.session.commit()
                    cert_code = new_cert.certificate_code
                else:
                    cert_code = existing_cert.certificate_code

        return jsonify({
            "score": score,
            "passed": passed,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "ground_truth": ground_truth_dicts,
            "feedback": feedback,
            "qualifies_for_cert": qualifies_for_cert,
            "certificate_code": cert_code
        })

    @app.route("/certificate/<cert_code>")
    def view_certificate(cert_code):
        cert = Certificate.query.filter_by(certificate_code=cert_code).first_or_404()
        return render_template("certificate.html", cert=cert)

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
