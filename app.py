import os
from flask import Flask, render_template, request, jsonify
from config import Config
from models import db, Wall, Defect, AssessmentAttempt

def calculate_iou(box_a, box_b):
    x_left = max(box_a["x_min"], box_b["x_min"])
    y_top = max(box_a["y_min"], box_b["y_min"])
    x_right = min(box_a["x_max"], box_b["x_max"])
    y_bottom = min(box_a["y_max"], box_b["y_max"])

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    intersection_area = (x_right - x_left) * (y_bottom - y_top)
    area_a = (box_a["x_max"] - box_a["x_min"]) * (box_a["y_max"] - box_a["y_min"])
    area_b = (box_b["x_max"] - box_b["x_min"]) * (box_b["y_max"] - box_b["y_min"])

    union_area = area_a + area_b - intersection_area
    return intersection_area / union_area if union_area > 0 else 0.0


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    with app.app_context():
        db.create_all()

        # Seed sample dry-stone wall if table is empty
        if not Wall.query.filter_by(slug="sample-drystone-collapse").first():
            sample_wall = Wall(
                slug="sample-drystone-collapse",
                title="Collapsed Dry Stone Field Boundary",
                description="Traditional dry stone wall showing core collapse and structural bowing.",
                country="United Kingdom",
                region="Yorkshire Dales",
                wall_type="dry_stone",
                structural_function="boundary",
                difficulty="beginner",
                image_filename="drystone_collapse_01.jpg",
                is_published=True
            )
            db.session.add(sample_wall)
            db.session.commit()

    # --- Home & Health Routes ---
    @app.route("/")
    def index():
        walls = Wall.query.filter_by(is_published=True).all()
        return render_template("index.html", walls=[w.to_dict() for w in walls])

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "app": "wall_inspector"})

    # --- Admin Tagger Endpoints ---
    @app.route("/admin/walls/<wall_id>/tagger")
    def admin_tagger(wall_id):
        wall = Wall.query.get_or_404(wall_id)
        return render_template("tagger.html", wall=wall)

    @app.route("/admin/walls/<wall_id>/defects", methods=["GET"])
    def get_admin_defects(wall_id):
        defects = Defect.query.filter_by(wall_id=wall_id).all()
        return jsonify([d.to_dict() for d in defects])

    @app.route("/admin/walls/<wall_id>/defects", methods=["POST"])
    def add_admin_defect(wall_id):
        wall = Wall.query.get_or_404(wall_id)
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid payload"}), 400

        defect = Defect(
            wall_id=wall.id,
            target_type=data.get("target_type", "bounding_box"),
            x_min=float(data["x_min"]),
            y_min=float(data["y_min"]),
            x_max=float(data["x_max"]),
            y_max=float(data["y_max"]),
            category=data.get("category", "unspecified"),
            severity=data.get("severity", "moderate"),
            title=data.get("title", "Untitled Defect"),
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

    # --- Student Inspection Endpoints ---
    @app.route("/inspect/<wall_slug>")
    def inspect_wall(wall_slug):
        wall = Wall.query.filter_by(slug=wall_slug, is_published=True).first_or_404()
        return render_template("inspect.html", wall=wall)

    @app.route("/inspect/<wall_slug>/submit", methods=["POST"])
    def submit_inspection(wall_slug):
        wall = Wall.query.filter_by(slug=wall_slug, is_published=True).first_or_404()
        data = request.get_json() or {}

        submitted_markers = data.get("markers", [])
        student_name = data.get("student_name", "Anonymous Inspector")
        session_id = data.get("session_id", "guest-session")

        ground_truth = Defect.query.filter_by(wall_id=wall.id).all()
        ground_truth_dicts = [d.to_dict() for d in ground_truth]

        matched_defects = set()
        feedback = []
        false_positives = 0

        for marker in submitted_markers:
            hit = False
            for gt in ground_truth_dicts:
                iou = calculate_iou(marker, gt)
                if iou >= 0.25:
                    hit = True
                    matched_defects.add(gt["id"])
                    feedback.append({
                        "title": gt["title"],
                        "category": gt["category"],
                        "status": "correct",
                        "explanation": gt["explanation"]
                    })
                    break
            if not hit:
                false_positives += 1

        true_positives = len(matched_defects)
        total_defects = len(ground_truth_dicts)
        false_negatives = max(0, total_defects - true_positives)

        if total_defects > 0:
            raw_score = (true_positives / total_defects) * 100
            score = max(0.0, round(raw_score - (false_positives * 10), 1))
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

        return jsonify({
            "score": score,
            "passed": passed,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "ground_truth": ground_truth_dicts,
            "feedback": feedback
        })

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)