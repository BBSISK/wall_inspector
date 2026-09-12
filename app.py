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


WALL_CATALOG = [
    {
        "slug": "sample-drystone-collapse",
        "title": "Traditional Irish Dry Stone Field Boundary",
        "description": "Double-faced dry stone wall with coping loss and hearting stone washout.",
        "country": "Ireland",
        "region": "Galway / Connemara",
        "wall_type": "dry_stone",
        "structural_function": "boundary",
        "difficulty": "beginner",
        "image_filename": "drystone_01.jpg",
    },
    {
        "slug": "rustic-retaining-dyke",
        "title": "Rustic Field Stone Retaining Dyke",
        "description": "Agricultural stone revetment showing root wedge displacement and out-of-plumb face.",
        "country": "United Kingdom",
        "region": "Cumbria",
        "wall_type": "dry_stone",
        "structural_function": "retaining",
        "difficulty": "intermediate",
        "image_filename": "drystone_02.jpg",
    },
    {
        "slug": "industrial-brick-efflorescence",
        "title": "Industrial Red Brick Cavity Wall",
        "description": "Severe crystalline salt leaching (efflorescence) and eroded bed joint mortar.",
        "country": "United Kingdom",
        "region": "Manchester",
        "wall_type": "brick_cavity",
        "structural_function": "load_bearing",
        "difficulty": "beginner",
        "image_filename": "brick_efflorescence_01.jpg",
    },
    {
        "slug": "historic-lime-rubble",
        "title": "Historic Lime-Mortared Rubble Wall",
        "description": "Rubble masonry with deep weathered lime mortar washout and loose bonding stones.",
        "country": "Ireland",
        "region": "Meath",
        "wall_type": "lime_mortar",
        "structural_function": "boundary",
        "difficulty": "intermediate",
        "image_filename": "stone_rubble_01.jpg",
    },
    {
        "slug": "aran-karst-boundary",
        "title": "Limestone Karst Dry Boundary",
        "description": "Single-stone lace karst wall vulnerable to lateral wind load and coping displacement.",
        "country": "Ireland",
        "region": "Inis Mór, Aran Islands",
        "wall_type": "dry_stone",
        "structural_function": "boundary",
        "difficulty": "intermediate",
        "image_filename": "drystone_aran_01.jpg",
    },
    {
        "slug": "granite-dyke-subsidence",
        "title": "Granite Field Dyke with Subsidence",
        "description": "Heavy boulder base showing differential ground settlement and core collapse.",
        "country": "United Kingdom",
        "region": "Scottish Highlands",
        "wall_type": "dry_stone",
        "structural_function": "boundary",
        "difficulty": "advanced",
        "image_filename": "stone_bulge_01.jpg",
    },
    {
        "slug": "ashlar-spalling-parapet",
        "title": "Dressed Ashlar Masonry Parapet",
        "description": "Finely dressed ashlar stonework showing surface spalling and frost-thaw delamination.",
        "country": "France",
        "region": "Normandy",
        "wall_type": "ashlar",
        "structural_function": "parapet",
        "difficulty": "advanced",
        "image_filename": "ashlar_cracking_01.jpg",
    },
    {
        "slug": "factory-brick-decay",
        "title": "Aged Factory Boundary with Spalling",
        "description": "Frost-heaved brickwork with blown faces and degraded cementitious repointing.",
        "country": "Germany",
        "region": "Ruhr",
        "wall_type": "brick_cavity",
        "structural_function": "boundary",
        "difficulty": "intermediate",
        "image_filename": "old_brick_decay_01.jpg",
    },
    {
        "slug": "terrace-retaining-wall",
        "title": "Terraced Dry Stone Retaining Boundary",
        "description": "Hillside gravity retaining wall subjected to hydrostatic pressure and lateral bulge.",
        "country": "Italy",
        "region": "Cinque Terre",
        "wall_type": "dry_stone",
        "structural_function": "retaining",
        "difficulty": "advanced",
        "image_filename": "retaining_drystone_01.jpg",
    },
    {
        "slug": "coursed-limestone-farm",
        "title": "Coursed Limestone Farm Wall",
        "description": "Substantial farm boundary showing invasive ivy root penetration and joint expansion.",
        "country": "Ireland",
        "region": "Kilkenny",
        "wall_type": "lime_mortar",
        "structural_function": "boundary",
        "difficulty": "beginner",
        "image_filename": "lime_coursed_01.jpg",
    },
    {
        "slug": "perimeter-brick-expansion",
        "title": "Perimeter Brick Wall with Joint Separation",
        "description": "Modern brick perimeter lacking expansion joints, showing vertical thermal fractures.",
        "country": "United Kingdom",
        "region": "York",
        "wall_type": "brick_cavity",
        "structural_function": "boundary",
        "difficulty": "intermediate",
        "image_filename": "modern_brick_damage_01.jpg",
    },
]


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    with app.app_context():
        db.create_all()

        for w_data in WALL_CATALOG:
            existing = Wall.query.filter_by(slug=w_data["slug"]).first()
            if not existing:
                wall = Wall(
                    slug=w_data["slug"],
                    title=w_data["title"],
                    description=w_data["description"],
                    country=w_data["country"],
                    region=w_data["region"],
                    wall_type=w_data["wall_type"],
                    structural_function=w_data["structural_function"],
                    difficulty=w_data["difficulty"],
                    image_filename=w_data["image_filename"],
                    is_published=True,
                )
                db.session.add(wall)
            else:
                existing.image_filename = w_data["image_filename"]
                existing.title = w_data["title"]
        db.session.commit()

    @app.route("/")
    def index():
        walls = Wall.query.filter_by(is_published=True).all()
        return render_template("index.html", walls=[w.to_dict() for w in walls])

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "app": "wall_inspector", "walls_count": len(WALL_CATALOG)})

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
            explanation=data.get("explanation", ""),
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
                        "explanation": gt["explanation"],
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
            feedback_notes={"items": feedback},
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
            "feedback": feedback,
        })

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
