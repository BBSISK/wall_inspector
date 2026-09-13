import os
import math
import uuid
import random
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, session
from werkzeug.utils import secure_filename
from sqlalchemy import text, inspect
import cloudinary
import cloudinary.uploader
from config import Config
from models import db, Wall, Defect, AssessmentAttempt, Certificate, Assignment, StudentSubmission

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
    ],
    "retaining_wall": [
        {"id": "hydrostatic_bulge", "label": "Hydrostatic Outward Bulge"},
        {"id": "weep_blockage", "label": "Blocked / Missing Weep Hole Drainage"},
        {"id": "shear_slip", "label": "Base Shear Foundation Displacement"}
    ],
    "cob_earth": [
        {"id": "basal_erosion", "label": "Basal Splash / Ground Moisture Undercut"},
        {"id": "shrinkage_fissure", "label": "Vertical Desiccation / Shrinkage Fracture"},
        {"id": "compressive_slump", "label": "Plastic Compression Bulge"}
    ],
    "flint_knapped": [
        {"id": "flint_unseating", "label": "Knapped Flint Dislodgement / Popping"},
        {"id": "matrix_washout", "label": "Lime Matrix Weathering"},
        {"id": "gallet_loss", "label": "Flint Gallet Dressing Loss"}
    ],
    "terracotta_faience": [
        {"id": "glaze_crazing", "label": "Surface Glaze Spall / Crazing"},
        {"id": "iron_bracket_heave", "label": "Sub-surface Tie / Cramp Jacking"},
        {"id": "web_shear", "label": "Hollow Terracotta Core Fracture"}
    ],
    "concrete_block": [
        {"id": "block_bed_crack", "label": "Longitudinal Bed Shear Fracture"},
        {"id": "sulfate_crumble", "label": "Sulfate Attack Binder Degradation"},
        {"id": "face_shell_spall", "label": "Cavity Web Shear Failure"}
    ],
    "boulder_fieldstone": [
        {"id": "roll_out", "label": "Basal Boulder Foundation Roll-Out"},
        {"id": "core_void", "label": "Chinking Pin Stone Loss & Voids"},
        {"id": "frost_heave", "label": "Perma-Freeze Lateral Displacement"}
    ],
    "granite_quoin": [
        {"id": "arment_crushing", "label": "Quoin Angle Compressive Crushing"},
        {"id": "lead_plug_heave", "label": "Lead Dowel / Weather Expansion Split"},
        {"id": "relief_shear", "label": "Ashlar Return Joint Displacement"}
    ]
}

REMEDIAL_OPTIONS = [
    {"id": "repoint_lime", "label": "Hydraulic Lime Mortar Repointing (NHL 2 / 3.5)"},
    {"id": "helical_stitch", "label": "Helical Stainless Steel Crack Stitching"},
    {"id": "grout_injection", "label": "Internal Core Void Grout Injection"},
    {"id": "rebuild_section", "label": "Localized Stone/Brick Dismantling & Rebuild Plumb"},
    {"id": "drainage_relief", "label": "Weep Hole Core-Drilling & Hydrostatic Relief"},
    {"id": "biocide_root", "label": "Controlled Biocide Treatment & Root Extraction"},
    {"id": "underpin_base", "label": "Differential Foundation Underpinning"},
    {"id": "monitor_gauge", "label": "Calibrated Tell-Tale Crack Gauge Monitoring"}
]

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

def calculate_center_distance(box_a, box_b):
    center_a_x = (box_a["x_min"] + box_a["x_max"]) / 2.0
    center_a_y = (box_a["y_min"] + box_a["y_max"]) / 2.0
    center_b_x = (box_b["x_min"] + box_b["x_max"]) / 2.0
    center_b_y = (box_b["y_min"] + box_b["y_max"]) / 2.0
    return math.hypot(center_a_x - center_b_x, center_a_y - center_b_y)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    upload_folder = os.path.join(app.root_path, "static", "img", "walls")
    os.makedirs(upload_folder, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = upload_folder
    audio_folder = os.path.join(app.root_path, "static", "audio")
    os.makedirs(audio_folder, exist_ok=True)
    app.config["AUDIO_FOLDER"] = audio_folder
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    db.init_app(app)

    with app.app_context():
        db.create_all()
        try:
            inspector = inspect(db.engine)
            wall_cols = [c["name"] for c in inspector.get_columns("walls")]
            if "image_url_direct" not in wall_cols:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE walls ADD COLUMN image_url_direct VARCHAR(500);"))
                    conn.commit()

            defect_cols = [c["name"] for c in inspector.get_columns("defects")]
            if "remedial_action" not in defect_cols:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE defects ADD COLUMN remedial_action VARCHAR(150) DEFAULT 'repoint_lime';"))
                    conn.commit()

            attempt_cols = [c["name"] for c in inspector.get_columns("assessment_attempts")]
            if "cohort_code" not in attempt_cols:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE assessment_attempts ADD COLUMN cohort_code VARCHAR(50) DEFAULT 'GENERAL';"))
                    conn.commit()
            if "assignment_code" not in attempt_cols:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE assessment_attempts ADD COLUMN assignment_code VARCHAR(50);"))
                    conn.commit()

            assign_cols = [c["name"] for c in inspector.get_columns("assignments")]
            if "time_limit_minutes" not in assign_cols:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE assignments ADD COLUMN time_limit_minutes INTEGER DEFAULT 0;"))
                    conn.commit()
            if "mode" not in assign_cols:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE assignments ADD COLUMN mode VARCHAR(20) DEFAULT 'exam';"))
                    conn.commit()

            sub_cols = [c["name"] for c in inspector.get_columns("student_submissions")]
            if "instructor_badge" not in sub_cols:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE student_submissions ADD COLUMN instructor_badge VARCHAR(100);"))
                    conn.commit()
            if "instructor_voice_url" not in sub_cols:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE student_submissions ADD COLUMN instructor_voice_url VARCHAR(500);"))
                    conn.commit()
            if "tilt_angle" not in sub_cols:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE student_submissions ADD COLUMN tilt_angle FLOAT;"))
                    conn.commit()
        except Exception as e:
            print(f"Migration note: {e}")

        # Seed Demo Certificate
        cert_code = "GWI-DEMO2026"
        demo_cert = Certificate.query.filter_by(certificate_code=cert_code).first()
        if not demo_cert:
            demo_cert = Certificate(
                certificate_code=cert_code,
                student_name="Barry Sisk",
                tier="Level 2 Inspector (Distinction)",
                average_score=94.5,
                total_walls_evaluated=4
            )
            db.session.add(demo_cert)
            db.session.commit()

        seed_catalog = [
            {
                "slug": "industrial-brick-efflorescence",
                "title": "Industrial Red Brick Cavity Wall",
                "description": "Red brick masonry exhibiting heavy crystalline salt leaching and weathered bed joint pointing.",
                "country": "United Kingdom",
                "region": "Manchester",
                "wall_type": "brick_cavity",
                "structural_function": "load_bearing",
                "difficulty": "beginner",
                "image_filename": "brick_efflorescence_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.18, "y_min": 0.20, "x_max": 0.82, "y_max": 0.80,
                        "category": "efflorescence", "severity": "moderate",
                        "remedial_action": "repoint_lime",
                        "title": "Crystalline Salt Efflorescence",
                        "explanation": "White salt deposits migrated through porous brickwork during moisture evaporation."
                    }
                ]
            },
            {
                "slug": "historic-lime-mortar-rubble",
                "title": "Historic Lime Mortar Rubble Wall",
                "description": "18th-century random rubble masonry wall showing mortar washout, ivy displacement, and hollow render delamination.",
                "country": "Ireland",
                "region": "Wicklow",
                "wall_type": "lime_mortar",
                "structural_function": "boundary",
                "difficulty": "intermediate",
                "image_filename": None,
                "image_url_direct": "https://res.cloudinary.com/iltvgpiy/image/upload/v1789227079/wall_inspector/historic-lime-mortar-rubble.png",
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.22, "y_min": 0.30, "x_max": 0.65, "y_max": 0.75,
                        "category": "lime_washout", "severity": "critical",
                        "remedial_action": "repoint_lime",
                        "title": "Deep Joint Lime Washout",
                        "explanation": "Driving rain and freeze-thaw cycles have eroded the sacrificial lime mortar bed."
                    }
                ]
            },
            {
                "slug": "ashlar-dressed-limestone-facade",
                "title": "Georgian Dressed Ashlar Masonry",
                "description": "Fine-jointed ashlar limestone masonry displaying iron cramp oxidation fractures and surface spalling.",
                "country": "Ireland",
                "region": "Dublin",
                "wall_type": "ashlar",
                "structural_function": "load_bearing",
                "difficulty": "advanced",
                "image_filename": None,
                "image_url_direct": "https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=1200&q=80",
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.35, "y_min": 0.25, "x_max": 0.70, "y_max": 0.68,
                        "category": "joint_separation", "severity": "moderate",
                        "remedial_action": "helical_stitch",
                        "title": "Ashlar Joint Shear & Separation",
                        "explanation": "Differential thermal movement and foundation settlement opening fine precision arrises."
                    }
                ]
            },
            {
                "slug": "granite-retaining-wall-failure",
                "title": "Granite Gravity Retaining Wall",
                "description": "Heavy dry-jointed granite retaining structure experiencing hydrostatic outward bulging and drainage weep hole blockage.",
                "country": "Ireland",
                "region": "Galway",
                "wall_type": "retaining_wall",
                "structural_function": "retaining",
                "difficulty": "advanced",
                "image_filename": None,
                "image_url_direct": "https://images.unsplash.com/photo-1448375240586-882707db888b?auto=format&fit=crop&w=1200&q=80",
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.28, "y_min": 0.35, "x_max": 0.75, "y_max": 0.85,
                        "category": "hydrostatic_bulge", "severity": "critical",
                        "remedial_action": "drainage_relief",
                        "title": "Hydrostatic Outward Bulge",
                        "explanation": "Excess pore water pressure behind the masonry facing forcing stones out-of-plumb."
                    }
                ]
            },
            {
                "slug": "historic-cob-earth-structure",
                "title": "Vernacular Cob & Rammed Earth Wall",
                "description": "Mass-earth subsoil and straw wall exhibiting basal rain-splash erosion and vertical desiccation cracks.",
                "country": "Ireland",
                "region": "Wexford",
                "wall_type": "cob_earth",
                "structural_function": "load_bearing",
                "difficulty": "intermediate",
                "image_filename": None,
                "image_url_direct": "https://placehold.co/800x600/1e293b/38bdf8?text=Cob+Earth+Structure",
                "defects": []
            },
            {
                "slug": "knapped-flint-lime-facade",
                "title": "Knapped Flint & Flushwork Wall",
                "description": "Decorative and protective knapped field-flint facing showing chalk-matrix erosion and stone pop-outs.",
                "country": "United Kingdom",
                "region": "Norfolk",
                "wall_type": "flint_knapped",
                "structural_function": "load_bearing",
                "difficulty": "advanced",
                "image_filename": None,
                "image_url_direct": "https://placehold.co/800x600/1e293b/38bdf8?text=Knapped+Flint+Wall",
                "defects": []
            },
            {
                "slug": "glazed-architectural-terracotta",
                "title": "Edwardian Architectural Terracotta & Faience",
                "description": "Hollow glazed terracotta units experiencing hidden iron anchor corrosion and spider-web surface crazing.",
                "country": "United Kingdom",
                "region": "Birmingham",
                "wall_type": "terracotta_faience",
                "structural_function": "curtain",
                "difficulty": "advanced",
                "image_filename": None,
                "image_url_direct": "https://placehold.co/800x600/1e293b/38bdf8?text=Terracotta+Faience",
                "defects": []
            },
            {
                "slug": "hollow-concrete-blockwork-pier",
                "title": "Modular Concrete Block Boundary Wall",
                "description": "Core-filled concrete masonry blocks showing bed-joint shear fractures and moisture efflorescence.",
                "country": "Ireland",
                "region": "Cork",
                "wall_type": "concrete_block",
                "structural_function": "boundary",
                "difficulty": "beginner",
                "image_filename": None,
                "image_url_direct": "https://placehold.co/800x600/1e293b/38bdf8?text=Concrete+Blockwork",
                "defects": []
            },
            {
                "slug": "cyclopean-boulder-fieldstone-wall",
                "title": "Cyclopean Glacial Boulder Field Wall",
                "description": "Massive unshaped erratic granite boulders showing basal sliding and lost pin chinking.",
                "country": "Ireland",
                "region": "Donegal",
                "wall_type": "boulder_fieldstone",
                "structural_function": "retaining",
                "difficulty": "intermediate",
                "image_filename": None,
                "image_url_direct": "https://placehold.co/800x600/1e293b/38bdf8?text=Boulder+Fieldstone",
                "defects": []
            },
            {
                "slug": "granite-quoin-dressed-corner",
                "title": "Dressed Granite Quoin & Arris Corner",
                "description": "Heavy squared granite quoin blocks displaying arris edge spalling and dowel joint heaving.",
                "country": "Ireland",
                "region": "Dublin",
                "wall_type": "granite_quoin",
                "structural_function": "load_bearing",
                "difficulty": "advanced",
                "image_filename": None,
                "image_url_direct": "https://placehold.co/800x600/1e293b/38bdf8?text=Granite+Quoins",
                "defects": []
            },
            {
                "slug": "traditional-irish-dry-stone",
                "title": "Traditional Irish Dry Stone Field Boundary",
                "description": "Double-faced dry stone limestone wall constructed without mortar, featuring coping stones, hearting infill, and through-stone ties.",
                "country": "Ireland",
                "region": "Galway (Aran Islands)",
                "wall_type": "dry_stone",
                "structural_function": "boundary",
                "difficulty": "intermediate",
                "image_filename": "drystone_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.15, "y_min": 0.08, "x_max": 0.45, "y_max": 0.32,
                        "category": "coping_displacement", "severity": "moderate",
                        "remedial_action": "rebuild_section",
                        "title": "Coping Stone Dislodgement",
                        "explanation": "Top coping stones unseated by livestock or frost, exposing inner core hearting."
                    },
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.40, "y_min": 0.35, "x_max": 0.78, "y_max": 0.75,
                        "category": "lateral_bulge", "severity": "critical",
                        "remedial_action": "rebuild_section",
                        "title": "Out-of-Plumb Lateral Wythe Bulge",
                        "explanation": "Core settlement forcing face stones outward beyond safe frictional equilibrium."
                    }
                ]
            }
        ]

        for seed in seed_catalog:
            if not Wall.query.filter_by(slug=seed["slug"]).first():
                w = Wall(
                    slug=seed["slug"],
                    title=seed["title"],
                    description=seed["description"],
                    country=seed["country"],
                    region=seed["region"],
                    wall_type=seed["wall_type"],
                    structural_function=seed["structural_function"],
                    difficulty=seed["difficulty"],
                    image_filename=seed["image_filename"],
                    image_url_direct=seed["image_url_direct"],
                    is_published=True
                )
                db.session.add(w)
                db.session.commit()

                for d in seed.get("defects", []):
                    gt = Defect(
                        wall_id=w.id,
                        target_type=d["target_type"],
                        x_min=d["x_min"],
                        y_min=d["y_min"],
                        x_max=d["x_max"],
                        y_max=d["y_max"],
                        category=d["category"],
                        severity=d["severity"],
                        remedial_action=d.get("remedial_action", "repoint_lime"),
                        title=d["title"],
                        explanation=d["explanation"]
                    )
                    db.session.add(gt)
                db.session.commit()

    def admin_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("is_admin"):
                if request.path.startswith("/api/") or (request.method in ["POST", "DELETE"] and not request.path.startswith("/admin/login")):
                    return jsonify({"error": "Admin authentication required"}), 401
                next_path = request.full_path if request.query_string else request.path
                return redirect(url_for("admin_login", next=next_path))
            return f(*args, **kwargs)
        return decorated_function

    @app.context_processor
    def inject_admin_status():
        return {"is_admin": session.get("is_admin", False)}

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        error = None
        next_url = request.args.get("next") or request.form.get("next") or "/dashboard"
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            password = (request.form.get("admin_password") or request.form.get("password") or data.get("password") or "").strip()
            pin = (request.form.get("admin_pin") or request.form.get("pin") or data.get("pin") or "").strip()

            expected_password = app.config.get("ADMIN_PASSWORD", "stonecraft2026")
            expected_pin = str(app.config.get("ADMIN_PIN", "2026"))

            if (password and password == expected_password) or (pin and pin == expected_pin):
                session["is_admin"] = True
                if request.is_json:
                    return jsonify({"success": True, "redirect": next_url})
                return redirect(next_url)
            else:
                error = "Invalid instructor credentials. Please verify your password or 4-digit PIN."
                if request.is_json:
                    return jsonify({"success": False, "error": error}), 401
                return render_template("admin_login.html", error=error, next_url=next_url), 401

        already_auth = session.get("is_admin", False) and not request.args.get("show_form")
        return render_template("admin_login.html", error=error, next_url=next_url, already_authenticated=already_auth)

    @app.route("/admin/logout")
    def admin_logout():
        session.pop("is_admin", None)
        return redirect(url_for("index"))

    @app.route("/")
    def index():
        query = Wall.query.filter_by(is_published=True)

        selected_type = request.args.get("wall_type", "").strip()
        selected_difficulty = request.args.get("difficulty", "").strip()
        selected_location = request.args.get("country", "").strip()

        if selected_type:
            query = query.filter(Wall.wall_type == selected_type)
        if selected_difficulty:
            query = query.filter(Wall.difficulty == selected_difficulty)
        if selected_location:
            query = query.filter(Wall.country == selected_location)

        walls = query.all()

        all_walls = Wall.query.filter_by(is_published=True).all()
        wall_types = sorted(list(set(w.wall_type for w in all_walls if w.wall_type)))
        difficulties = ["beginner", "intermediate", "advanced"]
        locations = sorted(list(set(w.country for w in all_walls if w.country)))

        return render_template(
            "index.html",
            walls=[w.to_dict() for w in walls],
            wall_types=wall_types,
            difficulties=difficulties,
            locations=locations,
            selected_type=selected_type,
            selected_difficulty=selected_difficulty,
            selected_location=selected_location
        )

    # --- Student Assignment Portal ---
    @app.route("/portal", methods=["GET", "POST"])
    def student_portal():
        if request.method == "POST":
            code = request.form.get("assignment_code", "").strip().upper()
            student_name = request.form.get("student_name", "Inspector Candidate").strip()
            assignment = Assignment.query.filter_by(code=code, is_active=True).first()
            if not assignment:
                return render_template("student_portal.html", error="Invalid or inactive assignment code.")
            return redirect(url_for("run_assignment", code=code, student_name=student_name))
        return render_template("student_portal.html")

    @app.route("/portal/run/<code>")
    def run_assignment(code):
        assignment = Assignment.query.filter_by(code=code, is_active=True).first_or_404()
        assigned_walls = assignment.walls
        if not assigned_walls and assignment.wall_id:
            single = Wall.query.get(assignment.wall_id)
            if single:
                assigned_walls = [single]

        if not assigned_walls:
            return "No walls currently attached to this assignment.", 404

        wall_idx = request.args.get("wall_idx", 0, type=int)
        wall_idx = max(0, min(wall_idx, len(assigned_walls) - 1))
        wall = assigned_walls[wall_idx]

        student_name = request.args.get("student_name", "Inspector Candidate")
        categories = TAXONOMY_BY_WALL_TYPE.get(wall.wall_type, TAXONOMY_BY_WALL_TYPE["dry_stone"])
        next_wall_idx = (wall_idx + 1) if (wall_idx + 1) < len(assigned_walls) else None

        return render_template(
            "inspect.html",
            wall=wall.to_dict(),
            categories=categories,
            remedial_options=REMEDIAL_OPTIONS,
            assignment_code=code,
            assignment_title=assignment.title,
            student_name=student_name,
            total_assigned=len(assigned_walls),
            current_index=wall_idx + 1,
            next_index=next_wall_idx,
            time_limit_minutes=assignment.time_limit_minutes or 0,
            assignment_mode=assignment.mode or "exam"
        )

    @app.route("/handbook")
    def handbook():
        return render_template(
            "handbook.html",
            taxonomies=TAXONOMY_BY_WALL_TYPE,
            remedial_options=REMEDIAL_OPTIONS
        )

    # --- Instructor Assignment Creator with Filters & Bulk Assign ---
    @app.route("/admin/assignments", methods=["GET", "POST"])
    @admin_required
    def admin_assignments():
        if request.method == "POST":
            title = request.form.get("title", "Masonry Assessment").strip()
            code = request.form.get("code", "").strip().upper() or uuid.uuid4().hex[:6].upper()
            assign_mode = request.form.get("assign_mode", "selected")
            time_limit_minutes = request.form.get("time_limit_minutes", 0, type=int)
            mode = request.form.get("assignment_mode", "exam").strip()

            target_walls = []
            if assign_mode == "by_type":
                filter_type = request.form.get("bulk_wall_type")
                target_walls = Wall.query.filter_by(wall_type=filter_type, is_published=True).all()
            elif assign_mode == "by_difficulty":
                filter_diff = request.form.get("bulk_difficulty")
                target_walls = Wall.query.filter_by(difficulty=filter_diff, is_published=True).all()
            elif assign_mode == "by_type_and_difficulty":
                filter_type = request.form.get("bulk_wall_type")
                filter_diff = request.form.get("bulk_difficulty")
                target_walls = Wall.query.filter_by(wall_type=filter_type, difficulty=filter_diff, is_published=True).all()
            else:
                selected_ids = request.form.getlist("selected_wall_ids")
                if selected_ids:
                    target_walls = Wall.query.filter(Wall.id.in_(selected_ids)).all()

            if not target_walls:
                target_walls = Wall.query.filter_by(is_published=True).limit(1).all()

            assignment = Assignment(
                code=code,
                title=title,
                wall_id=target_walls[0].id if target_walls else None,
                time_limit_minutes=time_limit_minutes,
                mode=mode,
                is_active=True
            )
            assignment.walls = target_walls
            db.session.add(assignment)
            db.session.commit()
            return redirect(url_for("admin_assignments"))

        # Filtering catalog choices on the admin view
        query = Wall.query.filter_by(is_published=True)
        selected_type = request.args.get("wall_type", "").strip()
        selected_difficulty = request.args.get("difficulty", "").strip()
        selected_location = request.args.get("country", "").strip()

        if selected_type:
            query = query.filter(Wall.wall_type == selected_type)
        if selected_difficulty:
            query = query.filter(Wall.difficulty == selected_difficulty)
        if selected_location:
            query = query.filter(Wall.country == selected_location)

        filtered_walls = query.all()

        all_walls = Wall.query.filter_by(is_published=True).all()
        wall_types = sorted(list(set(w.wall_type for w in all_walls if w.wall_type)))
        difficulties = ["beginner", "intermediate", "advanced"]
        locations = sorted(list(set(w.country for w in all_walls if w.country)))
        assignments = Assignment.query.order_by(Assignment.created_at.desc()).all()

        return render_template(
            "admin_assignments.html",
            assignments=assignments,
            walls=filtered_walls,
            wall_types=wall_types,
            difficulties=difficulties,
            locations=locations,
            selected_type=selected_type,
            selected_difficulty=selected_difficulty,
            selected_location=selected_location
        )

    @app.route("/admin/walls/<wall_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_edit_wall(wall_id):
        wall = Wall.query.get_or_404(wall_id)
        if request.method == "GET":
            return render_template("admin_edit_wall.html", wall=wall.to_dict())

        try:
            wall.title = request.form.get("title", wall.title).strip()
            wall.description = request.form.get("description", wall.description)
            wall.country = request.form.get("country", wall.country)
            wall.region = request.form.get("region", wall.region)
            wall.wall_type = request.form.get("wall_type", wall.wall_type)
            wall.difficulty = request.form.get("difficulty", wall.difficulty)

            file = request.files.get("wall_image")
            if file and file.filename:
                slug = wall.slug
                c_url = os.getenv("CLOUDINARY_URL", "").strip()
                if c_url:
                    try:
                        upload_result = cloudinary.uploader.upload(
                            file,
                            folder="wall_inspector",
                            public_id=slug,
                            overwrite=True,
                            resource_type="image"
                        )
                        wall.image_url_direct = upload_result.get("secure_url")
                    except Exception as cloud_err:
                        print(f"Cloudinary upload error in edit: {cloud_err}")
                        file.seek(0)
                        ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
                        filename = f"{slug}{ext}"
                        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                        wall.image_filename = filename
                        wall.image_url_direct = None
                else:
                    ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
                    filename = f"{slug}{ext}"
                    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                    wall.image_filename = filename
                    wall.image_url_direct = None

            db.session.commit()
            return redirect(url_for("index"))
        except Exception as e:
            db.session.rollback()
            return f"Error updating wall: {str(e)}", 500

    @app.route("/admin/walls/<wall_id>/delete", methods=["POST"])
    @admin_required
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
    @admin_required
    def dashboard():
        selected_cohort = request.args.get("cohort", "").strip().upper()
        selected_assignment = request.args.get("assignment", "").strip().upper()

        query = AssessmentAttempt.query
        if selected_cohort:
            query = query.filter_by(cohort_code=selected_cohort)
        if selected_assignment:
            # Match attempts marked with the assignment code in feedback or cohort
            query = query.filter(
                (AssessmentAttempt.cohort_code == selected_assignment) |
                (AssessmentAttempt.student_session_id.like(f"%{selected_assignment}%"))
            )

        attempts_raw = query.all()
        attempts_raw.sort(key=lambda x: getattr(x, 'created_at', None) or datetime.min, reverse=True)
        attempts = attempts_raw[:50]

        all_attempts = AssessmentAttempt.query.all()
        cohorts = sorted(list(set(a.cohort_code or "GENERAL" for a in all_attempts)))
        assignments = Assignment.query.order_by(Assignment.created_at.desc()).all()

        total_attempts = len(attempts_raw)
        total_passed = sum(1 for a in attempts_raw if getattr(a, 'passed', False))
        pass_rate = round((total_passed / total_attempts * 100), 1) if total_attempts > 0 else 0
        avg_score = round(sum(a.score_percentage for a in attempts_raw) / total_attempts, 1) if total_attempts > 0 else 0.0

        # Analytics: Top Missed Faults
        missed_counts = {}
        for a in attempts_raw:
            if a.feedback_notes and isinstance(a.feedback_notes, dict):
                for item in a.feedback_notes.get("items", []):
                    if item.get("status") in ["missed", "misclassified"]:
                        fault_label = item.get("title", item.get("category", "Unspecified"))
                        missed_counts[fault_label] = missed_counts.get(fault_label, 0) + 1

        top_missed = sorted(missed_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        certificates = Certificate.query.order_by(Certificate.issued_at.desc()).all()
        student_submissions = StudentSubmission.query.order_by(StudentSubmission.created_at.desc()).limit(30).all()

        return render_template(
            "dashboard.html",
            attempts=attempts,
            certificates=certificates,
            student_submissions=student_submissions,
            total_attempts=total_attempts,
            pass_rate=pass_rate,
            avg_score=avg_score,
            cohorts=cohorts,
            assignments=assignments,
            selected_cohort=selected_cohort,
            selected_assignment=selected_assignment,
            top_missed=top_missed
        )

    @app.route("/admin/walls/new", methods=["GET", "POST"])
    @admin_required
    def admin_create_wall():
        if request.method == "GET":
            return render_template("admin_create_wall.html")

        try:
            file = request.files.get("wall_image")
            if not file or not file.filename:
                return "No image file selected", 400

            title = request.form.get("title", "Untitled Wall").strip()
            slug = secure_filename(title.lower().replace(" ", "-")) + "-" + uuid.uuid4().hex[:6]
            image_url_direct = None
            filename = None

            c_url = os.getenv("CLOUDINARY_URL", "").strip()
            if c_url:
                try:
                    upload_result = cloudinary.uploader.upload(
                        file,
                        folder="wall_inspector",
                        public_id=slug,
                        overwrite=True,
                        resource_type="image"
                    )
                    image_url_direct = upload_result.get("secure_url")
                except Exception as cloud_err:
                    print(f"Cloudinary upload error, fallback to local: {cloud_err}")
                    file.seek(0)
                    ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
                    filename = f"{slug}{ext}"
                    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            else:
                ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
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
        except Exception as e:
            db.session.rollback()
            return f"Error creating wall: {str(e)}", 500

    @app.route("/admin/walls/<wall_id>/tagger")
    @admin_required
    def admin_tagger(wall_id):
        wall = Wall.query.get_or_404(wall_id)
        categories = TAXONOMY_BY_WALL_TYPE.get(wall.wall_type, TAXONOMY_BY_WALL_TYPE["dry_stone"])
        return render_template(
            "tagger.html",
            wall=wall.to_dict(),
            categories=categories,
            remedial_options=REMEDIAL_OPTIONS
        )

    @app.route("/admin/walls/<wall_id>/defects", methods=["GET"])
    def get_admin_defects(wall_id):
        defects = Defect.query.filter_by(wall_id=wall_id).all()
        return jsonify([d.to_dict() for d in defects])

    @app.route("/admin/walls/<wall_id>/defects", methods=["POST"])
    @admin_required
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
            remedial_action=data.get("remedial_action", "repoint_lime"),
            title=data.get("title", "Structural Defect"),
            explanation=data.get("explanation", "")
        )
        db.session.add(defect)
        db.session.commit()
        return jsonify(defect.to_dict()), 201

    @app.route("/admin/defects/<defect_id>", methods=["DELETE"])
    @admin_required
    def delete_admin_defect(defect_id):
        defect = Defect.query.get_or_404(defect_id)
        db.session.delete(defect)
        db.session.commit()
        return jsonify({"status": "deleted", "id": defect_id})

    @app.route("/inspect/<wall_slug>")
    def inspect_wall(wall_slug):
        wall = Wall.query.filter_by(slug=wall_slug, is_published=True).first_or_404()
        categories = TAXONOMY_BY_WALL_TYPE.get(wall.wall_type, TAXONOMY_BY_WALL_TYPE["dry_stone"])
        return render_template(
            "inspect.html",
            wall=wall.to_dict(),
            categories=categories,
            remedial_options=REMEDIAL_OPTIONS,
            assignment_code=None,
            total_assigned=1,
            current_index=1,
            next_index=None,
            time_limit_minutes=0,
            assignment_mode="practice"
        )

    @app.route("/inspect/<wall_slug>/submit", methods=["POST"])
    def submit_inspection(wall_slug):
        wall = Wall.query.filter_by(slug=wall_slug, is_published=True).first_or_404()
        data = request.get_json() or {}

        submitted_markers = data.get("markers", [])
        student_name = data.get("student_name", "Inspector Candidate").strip()
        cohort_code = data.get("cohort_code", "GENERAL").strip().upper() or "GENERAL"
        assignment_code = data.get("assignment_code", "").strip().upper() or None
        session_id = data.get("session_id", "session_default")

        ground_truth = Defect.query.filter_by(wall_id=wall.id).all()
        ground_truth_dicts = [d.to_dict() for d in ground_truth]

        matched_defect_ids = set()
        partial_defect_ids = set()
        feedback = []
        false_positives = 0
        earned_points = 0.0

        for marker in submitted_markers:
            best_iou = 0.0
            best_gt = None
            closest_dist = 1.0

            for gt in ground_truth_dicts:
                iou = calculate_iou(marker, gt)
                dist = calculate_center_distance(marker, gt)
                if iou > best_iou:
                    best_iou = iou
                    best_gt = gt
                if dist < closest_dist and best_gt is None:
                    closest_dist = dist
                    if dist <= 0.20:
                        best_gt = gt

            if best_gt:
                category_match = (marker.get("category") == best_gt.get("category"))
                severity_match = (marker.get("severity") == best_gt.get("severity", "moderate"))
                remedial_match = (marker.get("remedial_action") == best_gt.get("remedial_action", "repoint_lime"))

                if best_iou >= 0.15:
                    matched_defect_ids.add(best_gt["id"])
                    # Location (0.60) + Category (0.20) + Severity (0.10) + Remediation (0.10)
                    marker_points = 0.60
                    if category_match: marker_points += 0.20
                    if severity_match: marker_points += 0.10
                    if remedial_match: marker_points += 0.10
                    earned_points += marker_points

                    status = "correct" if (category_match and severity_match and remedial_match) else ("partial" if category_match else "misclassified")
                    desc = f"Target Identified (IoU {round(best_iou*100)}%). "
                    if not category_match:
                        desc += f"Category mismatch (classified as {marker.get('category')}, expected {best_gt.get('category')}). "
                    if not severity_match:
                        desc += f"Severity misjudged (rated {marker.get('severity')}, expected {best_gt.get('severity')}). "
                    if not remedial_match:
                        desc += f"Alternative remediation recommended (prescribed: {marker.get('remedial_action')}). "
                    desc += f"Recommended intervention: {best_gt.get('remedial_action', 'repoint_lime')}. {best_gt.get('explanation', '')}"

                    feedback.append({
                        "title": best_gt["title"],
                        "category": best_gt["category"],
                        "severity": best_gt.get("severity", "moderate"),
                        "remedial_action": best_gt.get("remedial_action", "repoint_lime"),
                        "status": status,
                        "explanation": desc
                    })
                elif closest_dist <= 0.18 and category_match:
                    partial_defect_ids.add(best_gt["id"])
                    marker_points = 0.40
                    if severity_match: marker_points += 0.10
                    if remedial_match: marker_points += 0.10
                    earned_points += marker_points

                    feedback.append({
                        "title": best_gt["title"],
                        "category": best_gt["category"],
                        "severity": best_gt.get("severity", "moderate"),
                        "remedial_action": best_gt.get("remedial_action", "repoint_lime"),
                        "status": "partial",
                        "explanation": f"Near-Target Identification: Center accurate. Remedial standard: {best_gt.get('remedial_action', 'repoint_lime')}. {best_gt.get('explanation', '')}"
                    })
                else:
                    false_positives += 1
            else:
                false_positives += 1

        total_defects = len(ground_truth_dicts)
        full_hits = len(matched_defect_ids)
        partial_hits = len(partial_defect_ids - matched_defect_ids)
        false_negatives = max(0, total_defects - (full_hits + partial_hits))

        for gt in ground_truth_dicts:
            if gt["id"] not in matched_defect_ids and gt["id"] not in partial_defect_ids:
                if not any(f["title"] == gt["title"] for f in feedback):
                    feedback.append({
                        "title": gt["title"],
                        "category": gt["category"],
                        "severity": gt.get("severity", "moderate"),
                        "remedial_action": gt.get("remedial_action", "repoint_lime"),
                        "status": "missed",
                        "explanation": f"Missed structural pathology ({gt.get('severity', 'moderate')}). Prescription: {gt.get('remedial_action', 'repoint_lime')}. {gt.get('explanation', '')}"
                    })

        if total_defects > 0:
            raw_score = (earned_points / total_defects) * 100
            score = max(0.0, round(raw_score - (false_positives * 10), 1))
        else:
            score = 100.0 if false_positives == 0 else 0.0

        passed = score >= 70.0

        attempt = AssessmentAttempt(
            wall_id=wall.id,
            student_session_id=session_id,
            cohort_code=cohort_code,
            assignment_code=assignment_code,
            student_name=student_name,
            submitted_markers=submitted_markers,
            true_positives=full_hits + partial_hits,
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
            avg_s = sum(a.score_percentage for a in student_attempts) / len(student_attempts)
            if avg_s >= 70.0:
                qualifies_for_cert = True
                existing_cert = Certificate.query.filter_by(student_name=student_name).first()
                if not existing_cert:
                    tier = "Level 2 Inspector (Distinction)" if avg_s >= 85.0 else "Level 1 Certified Inspector"
                    new_cert = Certificate(
                        student_name=student_name,
                        tier=tier,
                        average_score=round(avg_s, 1),
                        total_walls_evaluated=len(student_attempts)
                    )
                    db.session.add(new_cert)
                    db.session.commit()
                    cert_code = new_cert.certificate_code
                else:
                    cert_code = existing_cert.certificate_code

        return jsonify({
            "attempt_id": attempt.id,
            "score": score,
            "passed": passed,
            "true_positives": full_hits,
            "partial_positives": partial_hits,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "ground_truth": ground_truth_dicts,
            "submitted_markers": submitted_markers,
            "feedback": feedback,
            "qualifies_for_cert": qualifies_for_cert,
            "certificate_code": cert_code
        })

    @app.route("/report/<attempt_id>")
    def view_survey_report(attempt_id):
        attempt = AssessmentAttempt.query.get_or_404(attempt_id)
        wall = Wall.query.get_or_404(attempt.wall_id)

        rem_dict = {r["id"]: r["label"] for r in REMEDIAL_OPTIONS}

        defect_items = []
        markers = attempt.submitted_markers or []
        for idx, m in enumerate(markers):
            cx = (m.get("x_min", 0.5) + m.get("x_max", 0.5)) / 2.0 * 100
            cy = (m.get("y_min", 0.5) + m.get("y_max", 0.5)) / 2.0 * 100
            cat_id = m.get("category", "unspecified")
            sev = m.get("severity", "moderate")
            rem_id = m.get("remedial_action", "repoint_lime")
            width_val = m.get("crack_width")

            item_title = cat_id.replace("_", " ").title()
            item_explanation = "Localized structural defect identified during candidate visual survey."
            if attempt.feedback_notes and isinstance(attempt.feedback_notes, dict):
                items = attempt.feedback_notes.get("items", [])
                if idx < len(items):
                    item_title = items[idx].get("title", item_title)
                    item_explanation = items[idx].get("explanation", item_explanation)

            defect_items.append({
                "index": idx + 1,
                "x_pct": round(cx, 1),
                "y_pct": round(cy, 1),
                "category": cat_id,
                "title": item_title,
                "severity": sev,
                "remedial_action": rem_id,
                "remedial_label": rem_dict.get(rem_id, rem_id.replace("_", " ").title()),
                "crack_width": width_val,
                "explanation": item_explanation
            })

        has_critical = any(d.get("severity") == "critical" for d in defect_items)
        has_moderate = any(d.get("severity") == "moderate" for d in defect_items)

        if has_critical or attempt.score_percentage < 70:
            risk_level = "high"
            risk_title = "Category A: Priority Remedial Action Required"
            risk_summary = "Active structural defects or severe joint failure posing progressive stability risks. Immediate stabilization recommended."
        elif has_moderate:
            risk_level = "moderate"
            risk_title = "Category B: Monitored Degradation"
            risk_summary = "Localized masonry distress and weather erosion observed. Interventions scheduled within a 3 to 6-month conservation window."
        else:
            risk_level = "low"
            risk_title = "Category C: Low Risk / Maintenance Standard"
            risk_summary = "Minor superficial weathering. Managed via standard cyclical lime pointing and non-destructive crack gauge monitoring."

        return render_template(
            "survey_report.html",
            attempt=attempt,
            wall=wall.to_dict(),
            defect_items=defect_items,
            risk_level=risk_level,
            risk_title=risk_title,
            risk_summary=risk_summary
        )

    @app.route("/certificate/<cert_code>")
    def view_certificate(cert_code):
        cert = Certificate.query.filter_by(certificate_code=cert_code).first_or_404()
        return render_template("certificate.html", cert=cert)

    @app.route("/wall/<wall_slug>/restoration")
    def view_wall_restoration(wall_slug):
        wall = Wall.query.filter_by(slug=wall_slug).first_or_404()
        defects = Defect.query.filter_by(wall_id=wall.id).all()
        rem_dict = {r["id"]: r["label"] for r in REMEDIAL_OPTIONS}

        remedial_specs = []
        for d in defects:
            rem_action = d.remedial_action or "repoint_lime"
            rem_label = rem_dict.get(rem_action, rem_action.replace("_", " ").title())

            if rem_action == "repoint_lime":
                desc = "Rake out failed joint bedding to 25mm depth without damaging arris edges. Flush with clean potable water. Flush-point using NHL 3.5 hydraulic lime and sharp well-graded sand (1:2.5)."
                mats = "Hydraulic Lime (NHL 2 or 3.5), washed sharp sand (0-4mm), hessian curing sheets"
                std = "BS EN 459-1 / SPAB Note 7"
                dur = "30–50 Years"
            elif rem_action == "helical_stitch":
                desc = "Cut 10mm slots in mortar beds at 450mm vertical centers across fracture zone. Install twin 6mm austenitic stainless steel helical tie bars anchored in thixotropic grout."
                mats = "316-grade austenitic helical wire (6mm), thixotropic anchor grout, color-matched pointing"
                std = "BRE Digest 329"
                dur = "50+ Years"
            elif rem_action == "grout_injection":
                desc = "Core drill 16mm injection ports into rubble core. Flush cavities and inject micro-fine hydraulic lime grout under low pressure (0.5 bar) to consolidate voiding."
                mats = "Micronized hydraulic lime grout, expander additives, injection ports"
                std = "Historic England Practical Conservation"
                dur = "40–60 Years"
            elif rem_action == "rebuild_section":
                desc = "Carefully dismantle unstable, out-of-plumb stones numbering and documenting course geometry. Clean sound stones and reconstruct plumb with core packing."
                mats = "Salvaged stone units, NHL 3.5 hydraulic lime mortar, clean aggregate"
                std = "BS 8298 Design & Installation"
                dur = "75+ Years"
            elif rem_action == "drainage_relief":
                desc = "Clear clogged weep tubes or core drill 50mm weep holes at 1200mm centers along retaining base. Insert geotextile-wrapped perforated drainage sleeves."
                mats = "Perforated PVC/HDPE drain sleeves, non-woven geotextile filter fabric, gravel backfill"
                std = "CIRIA C760 Retaining Walls"
                dur = "25–40 Years"
            elif rem_action == "biocide_root":
                desc = "Apply quaternary ammonium biocide treatment to masonry face. Carefully extract invasive root systems without prying bedding courses. Treat stump regrowth."
                mats = "Non-acidic conservation biocide, soft bristle brushes, root extraction calipers"
                std = "SPAB Advisory Note 3"
                dur = "5–10 Years Cyclical"
            elif rem_action == "underpin_base":
                desc = "Construct sequential concrete underpins in 1000mm alternating bays beneath settled masonry foundation to arrest differential ground subsidence."
                mats = "C28/35 sulfate-resisting structural concrete, high-tensile steel mesh, dry-pack non-shrink mortar"
                std = "BS 8110 Structural Concrete"
                dur = "100+ Years"
            else:
                desc = "Install calibrated optical crack monitoring gauges with vernier scales to monitor ongoing movement over a 12-month seasonal cycle."
                mats = "Polycarbonate tell-tale gauge, stainless steel fixing screws, tamper seal"
                std = "BRE Digest 251 / 361"
                dur = "12–24 Months Monitoring"

            remedial_specs.append({
                "title": d.title,
                "category": d.category,
                "severity": d.severity,
                "remedial_action": rem_action,
                "remedial_label": rem_label,
                "remedial_desc": desc,
                "materials": mats,
                "standard": std,
                "durability": dur
            })

        return render_template(
            "restoration_preview.html",
            wall=wall.to_dict(),
            defects=[d.to_dict() for d in defects],
            remedial_specs=remedial_specs
        )

    @app.route("/quiz")
    def view_quiz():
        return render_template("quiz.html", wall_types=list(TAXONOMY_BY_WALL_TYPE.keys()))

    @app.route("/api/quiz/questions")
    def get_quiz_questions():
        archetype_filter = request.args.get("archetype", "all").strip()
        limit = min(int(request.args.get("limit", 15)), 30)

        walls_query = Wall.query
        if archetype_filter and archetype_filter != "all":
            walls_query = walls_query.filter_by(wall_type=archetype_filter)
        walls = walls_query.all()

        questions = []
        defects = Defect.query.all()
        wall_map = {w.id: w for w in Wall.query.all()}
        for d in defects:
            w = wall_map.get(d.wall_id)
            if not w:
                continue
            if archetype_filter and archetype_filter != "all" and w.wall_type != archetype_filter:
                continue

            arch_taxa = TAXONOMY_BY_WALL_TYPE.get(w.wall_type, [])
            target_item = next((t for t in arch_taxa if t["id"] == d.category), None)
            target_label = target_item["label"] if target_item else d.title

            other_taxa = [t for t in arch_taxa if t["id"] != d.category]
            if len(other_taxa) < 3:
                for other_type, items in TAXONOMY_BY_WALL_TYPE.items():
                    if other_type != w.wall_type:
                        other_taxa.extend(items)
            distractors = random.sample(other_taxa, min(3, len(other_taxa)))

            options = [{"id": d.category, "label": target_label}]
            for dist in distractors:
                options.append({"id": dist["id"], "label": dist["label"]})
            random.shuffle(options)

            questions.append({
                "id": str(uuid.uuid4()),
                "image_url": w.to_dict()["image_url"],
                "archetype": w.wall_type,
                "archetype_label": w.wall_type.replace("_", " ").title(),
                "crop_box": {
                    "x_min": d.x_min,
                    "y_min": d.y_min,
                    "x_max": d.x_max,
                    "y_max": d.y_max
                },
                "target_defect_id": d.category,
                "target_defect_label": target_label,
                "explanation": d.explanation or f"Characteristic {target_label} diagnosed on {w.wall_type.replace('_', ' ')}.",
                "options": options
            })

        archetypes_to_sample = [archetype_filter] if archetype_filter != "all" and archetype_filter in TAXONOMY_BY_WALL_TYPE else list(TAXONOMY_BY_WALL_TYPE.keys())
        for atype in archetypes_to_sample:
            items = TAXONOMY_BY_WALL_TYPE.get(atype, [])
            sample_wall = next((w for w in walls if w.wall_type == atype), None) or (walls[0] if walls else None)
            wall_img = sample_wall.to_dict()["image_url"] if sample_wall else "https://images.unsplash.com/photo-1541888946425-d0fbb186c5f8?auto=format&fit=crop&w=1200&q=80"

            for item in items:
                other_taxa = [t for t in items if t["id"] != item["id"]]
                if len(other_taxa) < 3:
                    for ot, ot_items in TAXONOMY_BY_WALL_TYPE.items():
                        if ot != atype:
                            other_taxa.extend(ot_items)
                distractors = random.sample(other_taxa, min(3, len(other_taxa)))

                options = [{"id": item["id"], "label": item["label"]}]
                for dist in distractors:
                    options.append({"id": dist["id"], "label": dist["label"]})
                random.shuffle(options)

                questions.append({
                    "id": str(uuid.uuid4()),
                    "image_url": wall_img,
                    "archetype": atype,
                    "archetype_label": atype.replace("_", " ").title(),
                    "crop_box": None,
                    "target_defect_id": item["id"],
                    "target_defect_label": item["label"],
                    "explanation": f"Key diagnostic symptom for {item['label']} in {atype.replace('_', ' ').title()} masonry.",
                    "options": options
                })

        random.shuffle(questions)
        return jsonify({"questions": questions[:limit]})

    # ==========================================
    # 1. Defect Flashcard Trainer (Cards)
    # ==========================================
    @app.route("/cards")
    def flashcards():
        wall_types = list(TAXONOMY_BY_WALL_TYPE.keys())
        return render_template("flashcards.html", wall_types=wall_types)

    @app.route("/api/cards/deck")
    def api_cards_deck():
        archetype_filter = request.args.get("archetype", "all").strip()

        REMEDIAL_COSTS_EURO = {
            "repoint_lime": "€45 - €75 / linear meter",
            "helical_stitch": "€85 - €160 / linear meter",
            "grout_injection": "€120 - €240 / cubic meter void",
            "rebuild_section": "€280 - €550 / square meter",
            "drainage_relief": "€65 - €110 / weep station",
            "biocide_root": "€25 - €45 / square meter",
            "underpin_base": "€750 - €1,400 / linear meter",
            "monitor_gauge": "€35 - €60 / station"
        }

        REMEDIAL_LABELS = {
            "repoint_lime": "Hydraulic Lime Repointing (NHL 2 / 3.5)",
            "helical_stitch": "Helical Stainless Steel Stitching (6mm ties)",
            "grout_injection": "Internal Core Void Grout Injection",
            "rebuild_section": "Localized Stone Dismantling & Rebuild Plumb",
            "drainage_relief": "Weep Hole Core-Drilling & Hydrostatic Relief",
            "biocide_root": "Controlled Biocide & Woody Root Extraction",
            "underpin_base": "Differential Foundation Underpinning",
            "monitor_gauge": "Calibrated Tell-Tale Crack Gauge Monitoring"
        }

        ARCHETYPE_LABELS = {
            "brick_cavity": "Brick Cavity",
            "dry_stone": "Dry Stone",
            "lime_mortar": "Historic Lime",
            "ashlar": "Ashlar Stone",
            "retaining_wall": "Retaining Wall",
            "cob_earth": "Cob & Earth",
            "flint_knapped": "Knapped Flint",
            "terracotta_faience": "Terracotta & Faience",
            "concrete_block": "Concrete Block",
            "boulder_fieldstone": "Field Boulder",
            "granite_quoin": "Granite Quoin"
        }

        DEFECT_DETAILS = {
            "efflorescence": {
                "severity": "moderate", "action": "repoint_lime",
                "explanation": "Soluble salts dissolve in migrating ground or rain water and crystallize on the masonry face as moisture evaporates. Causes surface powdering and indicates ongoing moisture ingress.",
                "mechanics": "Capillary moisture transport + surface salt evaporation (subflorescence / crypto-efflorescence)."
            },
            "spalling": {
                "severity": "critical", "action": "rebuild_section",
                "explanation": "Trapped pore water expands by 9% upon freezing, exerting tensile hydraulic pressure that shears the outer brick or stone skin.",
                "mechanics": "Freeze-thaw hydraulic burst exceeding masonry tensile capacity."
            },
            "mortar_erosion": {
                "severity": "moderate", "action": "repoint_lime",
                "explanation": "Wind-driven rain, acidic rainfall, and wind scour dissolve hydraulic lime binder, recessing joint profiles and exposing arrises.",
                "mechanics": "Chemical dissolution of calcium carbonate + mechanical scouring."
            },
            "stepped_crack": {
                "severity": "critical", "action": "helical_stitch",
                "explanation": "Diagonal stepped fracture tracing perpendicular head and bed joints, indicating differential foundation subsidence or lateral shear.",
                "mechanics": "Diagonal tension failure along weakest shear plane (joint matrix)."
            },
            "expansion_failure": {
                "severity": "moderate", "action": "helical_stitch",
                "explanation": "Continuous long masonry runs lack movement expansion joints, generating compressive thermal stress that buckles brickwork.",
                "mechanics": "Unaccommodated thermal/moisture irreversible expansion."
            },
            "coping_displacement": {
                "severity": "moderate", "action": "rebuild_section",
                "explanation": "Top capstone dislodged by wind, livestock, or frost heave, allowing water to penetrate directly into the dry stone hearting.",
                "mechanics": "Gravity unseating + exposure of inner core rubble."
            },
            "hearting_washout": {
                "severity": "critical", "action": "grout_injection",
                "explanation": "Loss of smaller core packing stones within a double-faced wall, leaving large internal voids that trigger inward structural collapse.",
                "mechanics": "Core cavity voiding and loss of frictional interlock."
            },
            "lateral_bulge": {
                "severity": "critical", "action": "rebuild_section",
                "explanation": "Outward barrel displacement of the wall face under internal core settlement or hydrostatic back pressure.",
                "mechanics": "Buckling of slender outer wythe under vertical and lateral load."
            },
            "through_stone_failure": {
                "severity": "critical", "action": "helical_stitch",
                "explanation": "Long tie-stones spanning the entire wall thickness have fractured or washed out, allowing independent wythe separation.",
                "mechanics": "Loss of transverse structural tie between opposing faces."
            },
            "base_subsidence": {
                "severity": "critical", "action": "underpin_base",
                "explanation": "Differential settlement of foundation subsoil under rain softening or sub-base washout.",
                "mechanics": "Soil bearing failure causing vertical angular distortion."
            },
            "vegetation_roots": {
                "severity": "moderate", "action": "biocide_root",
                "explanation": "Woody roots penetrate unmortared joints; secondary root thickening exerts hydraulic mechanical splitting force.",
                "mechanics": "Biological wedge expansion displacing adjacent stone units."
            },
            "lime_washout": {
                "severity": "critical", "action": "repoint_lime",
                "explanation": "Free calcium hydroxide in non-hydraulic or weak hydraulic lime leached away by water passage.",
                "mechanics": "Binder matrix exhaustion leading to crumbly joint collapse."
            },
            "render_delamination": {
                "severity": "moderate", "action": "repoint_lime",
                "explanation": "External lime render loses adhesive bond with substrate masonry due to salt crystallization or moisture freezing at the interface.",
                "mechanics": "Interfacial shear failure producing hollow acoustic response."
            },
            "ivy_penetration": {
                "severity": "moderate", "action": "biocide_root",
                "explanation": "Hedera helix aerial rootlets embed into lime joints, dissolving lime binder with organic acids and displacing core rubble.",
                "mechanics": "Acidic biochemical degradation + mechanical joint disruption."
            },
            "rubble_voiding": {
                "severity": "critical", "action": "grout_injection",
                "explanation": "Disappearance of core lime mortar leaving cavernous voids between random rubble packing.",
                "mechanics": "Subsurface matrix collapse threatening total wall settlement."
            },
            "ashlar_spall": {
                "severity": "critical", "action": "rebuild_section",
                "explanation": "Face delamination parallel to bedding plane; often caused by face-bedded stone installation or moisture crystallization.",
                "mechanics": "Delamination along natural sedimentary foliation planes."
            },
            "joint_separation": {
                "severity": "moderate", "action": "repoint_lime",
                "explanation": "Fine precision 2mm-3mm arrises separating under thermal expansion and foundation movement.",
                "mechanics": "Tensional arris separation admitting wind-driven rain."
            },
            "iron_cramp_burst": {
                "severity": "critical", "action": "helical_stitch",
                "explanation": "Concealed ferrous iron ties oxidize when exposed to moisture; rust oxide expands up to 7x original volume, splitting massive ashlar blocks.",
                "mechanics": "Rust jacking / oxidation expansive bursting pressure."
            },
            "hydrostatic_bulge": {
                "severity": "critical", "action": "drainage_relief",
                "explanation": "Trapped groundwater behind a retaining structure generates lateral hydrostatic thrust that pushes facing stones outward.",
                "mechanics": "Lateral soil/water surcharge exceeding wall frictional resistance."
            },
            "weep_blockage": {
                "severity": "moderate", "action": "drainage_relief",
                "explanation": "Silt, mineral salts, and biological growth clog drainage weep tubes, trapping water behind the wall.",
                "mechanics": "Drainage failure causing immediate rise in pore water pressure."
            },
            "shear_slip": {
                "severity": "critical", "action": "underpin_base",
                "explanation": "Base course sliding horizontally on foundation bedrock under excessive lateral slope load.",
                "mechanics": "Base shear failure along wet interface."
            },
            "basal_erosion": {
                "severity": "critical", "action": "repoint_lime",
                "explanation": "Rain splashing from ground level erodes the unprotected lower 600mm of mass cob earth walls.",
                "mechanics": "Slaking and dissolution of clay-silt binder matrix."
            },
            "shrinkage_fissure": {
                "severity": "moderate", "action": "repoint_lime",
                "explanation": "Dry spells induce clay shrinkage in cob walls, creating vertical stress relief fissures.",
                "mechanics": "Desiccation volumetric contraction."
            },
            "compressive_slump": {
                "severity": "critical", "action": "rebuild_section",
                "explanation": "Moisture saturation plasticizes the clay-earth binder, causing outward bulging under roof gravity loads.",
                "mechanics": "Plastic shear slump under vertical compressive stress."
            },
            "flint_unseating": {
                "severity": "moderate", "action": "repoint_lime",
                "explanation": "Smooth vitreous flint nodules pop out of weathered lime-chalk bedding mortar.",
                "mechanics": "Loss of mechanical keying between non-porous flint and mortar."
            },
            "matrix_washout": {
                "severity": "moderate", "action": "repoint_lime",
                "explanation": "Chalk-lime matrix holding knapped flint flakes dissolves under driving coastal rain.",
                "mechanics": "Erosion of sacrificial lime matrix exposing nodule perimeters."
            },
            "gallet_loss": {
                "severity": "minor", "action": "repoint_lime",
                "explanation": "Small flint chips (gallets) wedged into wide joints dislodge, accelerating moisture access to the core.",
                "mechanics": "Loss of protective secondary packing dressing."
            },
            "glaze_crazing": {
                "severity": "moderate", "action": "repoint_lime",
                "explanation": "Micro-network of fine hairline fractures in vitreous faience glaze due to differential thermal expansion between glaze and terracotta body.",
                "mechanics": "Thermal expansion coefficient mismatch."
            },
            "iron_bracket_heave": {
                "severity": "critical", "action": "helical_stitch",
                "explanation": "Hidden wrought iron anchors securing hollow faience blocks to structural frame corrode and heave the skin outward.",
                "mechanics": "Expansive iron oxide jacking of hollow architectural ceramics."
            },
            "web_shear": {
                "severity": "critical", "action": "rebuild_section",
                "explanation": "Internal ceramic structural webs of hollow blocks fracture under seismic or frame settlement loads.",
                "mechanics": "Diagonal shear across hollow ceramic core."
            },
            "block_bed_crack": {
                "severity": "moderate", "action": "helical_stitch",
                "explanation": "Horizontal fracture along bed joints of concrete block wall caused by foundation movement or drying shrinkage.",
                "mechanics": "Tensile rupture along weakest horizontal bond line."
            },
            "sulfate_crumble": {
                "severity": "critical", "action": "rebuild_section",
                "explanation": "Tricalcium aluminate in cement reacts with ground sulfates to form expansive ettringite, turning solid block into crumbly paste.",
                "mechanics": "Expansive chemical sulfate attack degrading binder cohesion."
            },
            "face_shell_spall": {
                "severity": "critical", "action": "rebuild_section",
                "explanation": "Outer face shell of hollow concrete unit shears away from internal cross webs.",
                "mechanics": "Frost wedging in core voids forcing face shell off."
            },
            "roll_out": {
                "severity": "critical", "action": "rebuild_section",
                "explanation": "Rounded basal glacial boulder slides out of alignment under slope creep or missing pin chinking.",
                "mechanics": "Loss of frictional equilibrium in unmortared boulder base."
            },
            "core_void": {
                "severity": "moderate", "action": "grout_injection",
                "explanation": "Small wedge chinking stones wash away from boulder interstices, allowing large boulders to shift.",
                "mechanics": "Interstice chinking loss destabilizing gravity packing."
            },
            "frost_heave": {
                "severity": "critical", "action": "rebuild_section",
                "explanation": "Subsoil moisture freezing beneath glacial boulders lifts and displaces foundation alignment.",
                "mechanics": "Cryogenic frost lens heave."
            },
            "arment_crushing": {
                "severity": "critical", "action": "rebuild_section",
                "explanation": "Extreme vertical compressive point loading at dressed corner arrises causing spalling and diagonal fracture.",
                "mechanics": "Compressive stress concentration exceeding granite compressive yield."
            },
            "lead_plug_heave": {
                "severity": "moderate", "action": "repoint_lime",
                "explanation": "Molten lead dowels securing vertical quoins expand under thermal cycling or trapped water ice, splitting stone socket.",
                "mechanics": "Dowel socket hydraulic bursting."
            },
            "relief_shear": {
                "severity": "critical", "action": "helical_stitch",
                "explanation": "Vertical shear displacement between heavy dressed quoin stones and adjacent rubble or brick panel.",
                "mechanics": "Differential settlement between rigid quoin tower and flexible panel."
            }
        }

        walls = Wall.query.filter_by(is_published=True).all()
        wall_by_type = {w.wall_type: w for w in walls}
        defects = Defect.query.all()
        defects_by_cat = {d.category: d for d in defects}

        deck = []
        archetypes = [archetype_filter] if archetype_filter != "all" and archetype_filter in TAXONOMY_BY_WALL_TYPE else list(TAXONOMY_BY_WALL_TYPE.keys())

        for atype in archetypes:
            items = TAXONOMY_BY_WALL_TYPE.get(atype, [])
            wall = wall_by_type.get(atype) or (walls[0] if walls else None)
            wall_dict = wall.to_dict() if wall else {}
            wall_img = wall_dict.get("image_url", "https://images.unsplash.com/photo-1541888946425-d0fbb186c5f8?auto=format&fit=crop&w=1200&q=80")

            for item in items:
                cat_id = item["id"]
                detail = DEFECT_DETAILS.get(cat_id, {
                    "severity": "moderate",
                    "action": "repoint_lime",
                    "explanation": f"Characteristic diagnostic defect observed on {atype.replace('_', ' ')} masonry.",
                    "mechanics": "Environmental weathering and loss of structural cohesion."
                })

                gt_defect = defects_by_cat.get(cat_id)
                crop_box = None
                img_url = wall_img
                if gt_defect:
                    crop_box = {
                        "x_min": gt_defect.x_min,
                        "y_min": gt_defect.y_min,
                        "x_max": gt_defect.x_max,
                        "y_max": gt_defect.y_max
                    }
                    w_gt = db.session.get(Wall, gt_defect.wall_id)
                    if w_gt:
                        img_url = w_gt.to_dict()["image_url"]

                action_key = detail.get("action", "repoint_lime")
                deck.append({
                    "id": f"card-{atype}-{cat_id}",
                    "archetype": atype,
                    "archetype_label": ARCHETYPE_LABELS.get(atype, atype.replace("_", " ").title()),
                    "defect_id": cat_id,
                    "defect_title": item["label"],
                    "severity": detail.get("severity", "moderate"),
                    "image_url": img_url,
                    "crop_box": crop_box,
                    "explanation": detail.get("explanation"),
                    "mechanics": detail.get("mechanics"),
                    "remedial_action": action_key,
                    "remedial_label": REMEDIAL_LABELS.get(action_key, action_key.replace("_", " ").title()),
                    "euro_cost_rate": REMEDIAL_COSTS_EURO.get(action_key, "€45 - €90 / unit")
                })

        return jsonify({"success": True, "count": len(deck), "deck": deck})

    # ==========================================
    # Printable Pocket Field Crib-Sheet & Guide
    # ==========================================
    FIELD_GUIDE_DATA = [
        {
            "id": "brick_cavity",
            "name": "Brick Cavity Masonry",
            "category": "Structural Masonry",
            "geology": "Carboniferous Coal Measures Fired Clay wythes with cavity ties",
            "description": "Twin brick/block wythe construction stabilized by metal cavity ties; vulnerable to moisture accumulation and thermal movement.",
            "defects": [
                {"name": "Efflorescence", "indicators": "White crystalline salt blooms and crypto-efflorescence", "action": "Dry brush; eliminate moisture ingress; point NHL 3.5"},
                {"name": "Frost-Thaw Spalling", "indicators": "Tensile shearing/blowing of outer brick faces", "action": "Cut out and replace damaged units with matching frost-resistant units"},
                {"name": "Mortar Erosion", "indicators": "Bed/perp joints eroded >10mm; exposed arrises", "action": "Rake back 25mm and repoint with hydraulic lime NHL 3.5"},
                {"name": "Stepped Shear Crack", "indicators": "Diagonal stepped fracture tracing perpendicular and bed joints", "action": "Install 6mm helical stainless steel crack stitches at 450mm centers"},
                {"name": "Thermal Expansion Fissure", "indicators": "Continuous vertical fractures near corners lacking movement joints", "action": "Saw-cut 10mm vertical expansion movement joint & seal with elastomeric mastic"}
            ],
            "tolerances": "Aperture < 1.5mm | Bed joint recession < 10mm | Movement joint spacing < 12m",
            "binder": "Hydraulic Lime NHL 3.5 (1:2.5 sharp sand) - vapor permeable",
            "euro_rates": "Repointing: €45–€75/m | Helical Stitching: €85–€160/m | Rebuild Section: €280–€550/m²",
            "standards": ["BRE Digest 251 (Cat 0–3)", "BRE Digest 361", "BS EN 771-1", "RICS Condition Rating 2/3"]
        },
        {
            "id": "dry_stone",
            "name": "Traditional Dry Stone Walling",
            "category": "Historic & Vernacular",
            "geology": "Carboniferous Karst Limestone / Sandstone fieldstone (unmortared)",
            "description": "Double-faced unmortared gravity walling stabilized entirely by friction, inward batter, and interlocking core hearting.",
            "defects": [
                {"name": "Coping Dislodgement", "indicators": "Top capstones knocked loose by livestock or wind", "action": "Relay heavy buck-and-doe or flat capstones tightly pinned"},
                {"name": "Hearting Washout", "indicators": "Loss of smaller core packing stones; hollow internal voids", "action": "Dismantle face course and repack dense interlocking stone hearting"},
                {"name": "Lateral Wythe Bulge", "indicators": "Outward belly displacement (>15mm) under internal thrust", "action": "Carefully take down bulged section and rebuild with 1:6 inward batter"},
                {"name": "Missing Through-Stone", "indicators": "Wythe separation; absence of transverse tie stones", "action": "Insert continuous tie through-stones every 1.0m horizontal and vertical"},
                {"name": "Base Subsidence", "indicators": "Basal course sinking into soft ground or subsoil washout", "action": "Excavate foundation trench to solid subsoil and bed heavy footing boulders"}
            ],
            "tolerances": "Inward batter ratio 1:6 | Lateral bulge tolerance < 15mm | Through-stones required every 1m²",
            "binder": "No Binder (Strictly dry gravity interlock with tightly wedged chinking pin stones)",
            "euro_rates": "Take down & rebuild plumb: €220–€480/m | Chinking pin restoration: €50–€90/m",
            "standards": ["Dry Stone Walling Association (DSWA) Master Craftsman Codes", "Irish Heritage Council Field Boundary Guidelines", "RICS CR2/CR3"]
        },
        {
            "id": "lime_mortar",
            "name": "Historic Lime Mortar Rubble Wall",
            "category": "Historic & Vernacular",
            "geology": "Ordovician Slate, Schist & Calcareous Sandstone rubble in hydraulic lime",
            "description": "Random rubble masonry bedded in porous, flexible hydraulic or non-hydraulic lime mortar.",
            "defects": [
                {"name": "Deep Lime Washout", "indicators": "Binder leached away by water passage leaving sandy hollows", "action": "Rake back 25mm-35mm and repoint with NHL 2.0 / coarse sand aggregate"},
                {"name": "Render Delamination", "indicators": "Hollow drummy acoustic response when gently tapped", "action": "Carefully remove detached render; re-apply breathable 3-coat lime render"},
                {"name": "Structural Ivy Penetration", "indicators": "Woody roots embedded deep into joints, prying stones apart", "action": "Sever rootstems at base, allow dieback, extract, and repoint with lime"},
                {"name": "Internal Core Voiding", "indicators": "Cavernous cavities behind outer facing stones", "action": "Low-pressure void consolidation grout injection (pure hydraulic lime slurry)"}
            ],
            "tolerances": "Joint raking depth < 25mm | Core void ratio < 10% | Delamination area < 0.5m²",
            "binder": "Hydraulic Lime NHL 2.0 (1:2.5 coarse sand + 5% crushed brick pozzolan)",
            "euro_rates": "Repointing: €45–€75/m | Core Grout Injection: €120–€240/m³ void | Biocide: €25–€45/m²",
            "standards": ["SPAB Technical Advice Note 1 (Breathing Buildings)", "Historic England Mortars & Renders", "BRE Digest 245"]
        },
        {
            "id": "ashlar",
            "name": "Georgian Dressed Ashlar Limestone",
            "category": "Civic & Classical",
            "geology": "Carboniferous Calp Limestone & Leinster Granite fine freestone",
            "description": "Precision finely dressed stone blocks with razor-thin arrises (2mm–3mm joints) and non-hydraulic lime putty bedding.",
            "defects": [
                {"name": "Bedding Plane Exfoliation", "indicators": "Face delamination flaking parallel to natural sedimentary bed", "action": "Pneumatic dressing back to sound matrix or localized stone indent repair"},
                {"name": "Fine Joint Separation", "indicators": "Tensional arris separation admitting wind-driven rain", "action": "Rake hairline joint with fine hacksaw blade; repoint with CL90 fat lime putty"},
                {"name": "Iron Cramp Fracture (Rust Jacking)", "indicators": "Spalling block fracture centered directly over hidden ferrous ties", "action": "Surgically extract oxidized iron cramps; replace with 316 stainless or phosphor bronze"}
            ],
            "tolerances": "Joint arris width 2.5mm ± 0.5mm | Out-of-plane face step < 1.0mm | Rust heave: 0mm",
            "binder": "Non-hydraulic Fat Lime Putty (CL90) with fine stone dust (1:1.5 mix ratio)",
            "euro_rates": "Stone indent repair: €280–€550/m² | Stainless cramp replacement: €85–€160/unit",
            "standards": ["Historic England Practical Conservation: Stone", "RICS Condition Rating 3 (Urgent)", "BS 8298 Design of Stone Cladding"]
        },
        {
            "id": "retaining_wall",
            "name": "Gravity Retaining Wall & Dyke",
            "category": "Structural Masonry",
            "geology": "Porphyritic Granite & Basalt igneous retention blocks",
            "description": "Mass masonry retaining structure holding back soil, rock, or backfill through deadweight gravity resistance.",
            "defects": [
                {"name": "Hydrostatic Outward Bulge", "indicators": "Forward rotation or mid-height belly bulge from water pressure", "action": "Relieve pore water; core-drill additional weep holes; reconstruct batter"},
                {"name": "Weep Hole Blockage", "indicators": "Silted or calcified drain ports; damp staining on wall face", "action": "High-pressure clean out weep tubes; install gravel-pack geotextile filters"},
                {"name": "Basal Shear Slip", "indicators": "Horizontal displacement of base stones relative to sub-base", "action": "Toe underpinning; concrete heel toe beam or geotechnical ground anchors"}
            ],
            "tolerances": "Out-of-plumb batter < 25mm/m | Hydrostatic pressure head 0mm (free-draining) | Basal slip: 0mm",
            "binder": "Unmortared dry backing with free-draining granular aggregate (or Class M4 at base)",
            "euro_rates": "Weep hole drilling: €65–€110/station | Underpinning: €480–€950/linear meter",
            "standards": ["CIRIA C760 Embedded Retaining Walls", "Eurocode 7 Geotechnical Design (EN 1997)", "BRE Digest 472"]
        },
        {
            "id": "cob_earth",
            "name": "Cob & Mass Earth Structure",
            "category": "Historic & Vernacular",
            "geology": "Subsoil clay, sharp sand, chopped wheat straw and water mass-earth",
            "description": "Mass monolithic unbaked subsoil earth walling built in lifts on a protective stone plinth footing.",
            "defects": [
                {"name": "Basal Splash Undercut", "indicators": "Severe recession at bottom 600mm from splashing rainwater", "action": "Underpin base with stone plinth course; apply breathable lime shelter coat"},
                {"name": "Vertical Shrinkage Fissures", "indicators": "Desiccation cracks running vertically through lift layers", "action": "Stitch with timber hazel ties; ram firmly with clay-straw-lime cob loaf"},
                {"name": "Plastic Compressive Slump", "indicators": "Bulging and shearing of lower wall under roof load when damp", "action": "Prop roof loads immediately; dry out wall core; cut out plasticized earth"}
            ],
            "tolerances": "Basal undercut depth < 40mm | Fissure aperture < 3.0mm | Load eccentricity < 10%",
            "binder": "Sacrificial hydraulic lime wash (NHL 2.0) with tallow & animal hair (No cement!)",
            "euro_rates": "Cob section rebuild: €280–€550/m² | Lime shelter wash: €25–€45/m²",
            "standards": ["Historic England Practical Conservation: Earth", "Devon Earth Building Association Standards", "SPAB Tech Q&A"]
        },
        {
            "id": "flint_knapped",
            "name": "Knapped Flint & Chalk Lime Wall",
            "category": "Historic & Vernacular",
            "geology": "Cretaceous Upper White Chalk nodules & cryptocrystalline silica flint flakes",
            "description": "Hand-knapped glass-hard flint nodules bedded in hydraulic chalk lime with decorative flint gallet dressings.",
            "defects": [
                {"name": "Flint Nodule Unseating", "indicators": "Smooth flint stones falling out of weathered joint pockets", "action": "Re-seat flints into deep hydraulic lime bed with mechanical keying"},
                {"name": "Chalk-Lime Matrix Washout", "indicators": "Erosion of bedding mortar exposing glassy perimeter of flints", "action": "Rake joints to 20mm; point flush with NHL 2.0 mortar and chalk aggregate"},
                {"name": "Flint Gallet Dressing Loss", "indicators": "Missing decorative secondary flint chips wedged in bed joints", "action": "Press matching sharp flint gallet chips into fresh lime joint before set"}
            ],
            "tolerances": "Matrix recession < 8mm | Zero unseated flint nodules | Gallet loss < 10%",
            "binder": "Fat lime chalk putty mortar NHL 2.0 with crushed chalk & sharp sand aggregate",
            "euro_rates": "Flint repointing & galleting: €55–€95/linear meter | Stone reset: €35–€60/stone",
            "standards": ["SPAB Technical Advice Note: Flint Walling", "Historic England Knapped Flint Guidelines", "RICS CR2"]
        },
        {
            "id": "terracotta_faience",
            "name": "Architectural Terracotta & Faience",
            "category": "Civic & Classical",
            "geology": "Triassic Mercia Mudstone & Etruria Marl fired vitrified fireclay",
            "description": "Hollow glazed architectural ceramic units anchored to structural steel or masonry backing with hidden cramps.",
            "defects": [
                {"name": "Surface Glaze Crazing", "indicators": "Fine hairline network in vitreous glaze allowing moisture intake", "action": "Micro-porous consolidation treatment; clear breathable siloxane sealer"},
                {"name": "Anchor Bracket Heave (Jacking)", "indicators": "Concealed ferrous bracket corroding, lifting ceramic units outward", "action": "Core access from rear or joint; replace iron brackets with 316 stainless ties"},
                {"name": "Hollow Web Fracture", "indicators": "Internal cross-webs sheared under frame settlement or thermal loads", "action": "Inject low-pressure non-staining lime grout into hollow cell cavities"}
            ],
            "tolerances": "Glaze craze width < 0.2mm | Anchor displacement: 0mm | Hollow web fracture: 0 units",
            "binder": "Non-staining pure lime grout injection with thixotropic modifier (or NHL 2.0 pointing)",
            "euro_rates": "Hollow cell grout injection: €120–€240/unit | Ceramic unit indent: €350–€750/unit",
            "standards": ["Tiles and Architectural Ceramics Society (TACS) Codes", "Historic England Terracotta & Faience", "BS 8298"]
        },
        {
            "id": "concrete_block",
            "name": "Modular Concrete Blockwork (CMU)",
            "category": "Modern & Engineered",
            "geology": "Dense aggregate aggregated concrete CMU with sand-cement binder",
            "description": "Standardized modular concrete masonry units with horizontal bed reinforcement and sand-cement mortar joints.",
            "defects": [
                {"name": "Longitudinal Bed Joint Crack", "indicators": "Continuous horizontal fracture tracing along bed joints", "action": "Rake bed joint; install retrofitted 6mm helical bed joint reinforcement bar"},
                {"name": "Expansive Sulfate Attack", "indicators": "Mortar softening into white crumbly paste; expansion and spalling", "action": "Rake out decayed mortar; repoint with sulfate-resisting cement mortar (Class M4)"},
                {"name": "Face Shell / Web Shear", "indicators": "Outer concrete skin shearing away from hollow central webs", "action": "Dismantle and rebuild damaged block courses; install core grouting"}
            ],
            "tolerances": "Bed crack width < 1.5mm | Sulfate softening depth < 5mm | Web shear: 0 units",
            "binder": "Sulfate-resisting hydraulic mortar Class M4 (1:4 cement:sand with plasticizer)",
            "euro_rates": "Helical bed reinforcement: €45–€80/linear meter | Block course rebuild: €190–€380/m²",
            "standards": ["BRE Digest 363 (Sulfate attack on concrete in ground)", "BS 8103-2 Masonry", "Eurocode 6 (EN 1996)"]
        },
        {
            "id": "boulder_fieldstone",
            "name": "Cyclopean Glacial Boulder Wall",
            "category": "Historic & Vernacular",
            "geology": "Dalradian Gneiss & Plutonic Granitic Glacial Erratics",
            "description": "Massive unworked glacial erratic boulders assembled with unmortared interstitial chinking stones.",
            "defects": [
                {"name": "Basal Boulder Roll-Out", "indicators": "Large rounded footing boulder displaced forward on slope", "action": "Jack boulder back to alignment; construct reinforced earth toe berm"},
                {"name": "Chinking Pin Stone Loss", "indicators": "Small wedge stones fallen from interstices, leaving loose packing", "action": "Drive hard angular granite pin chinking wedges tightly into voids"},
                {"name": "Cryogenic Frost Lens Heave", "indicators": "Ground frost freezing beneath boulders, uplifting base course", "action": "Improve subsoil drainage trench; install frost-free crushed stone footing pad"}
            ],
            "tolerances": "Pin stone loss < 5% | Basal boulder slide < 5mm | Out-of-plumb < 20mm/m",
            "binder": "Dry gravity interlock with tightly wedged chinking pin stones",
            "euro_rates": "Chinking pin restoration: €50–€90/m | Boulder resetting & rebuild: €260–€520/m",
            "standards": ["Irish Heritage Council Field Boundary Guidelines", "DSWA Master Standards", "RICS CR2"]
        },
        {
            "id": "granite_quoin",
            "name": "Dressed Granite Quoin Corners",
            "category": "Civic & Classical",
            "geology": "Coarse-Grained Leinster Igneous Granite Arris Blocks",
            "description": "Heavy finely dressed granite return corner stones providing vertical alignment and rigidity to rubble panels.",
            "defects": [
                {"name": "Quoin Compressive Crushing", "indicators": "Corner arrises fracturing diagonally under intense point loading", "action": "Relieve vertical stress; drill and epoxy stainless threaded rods; lime point"},
                {"name": "Lead Dowel Weather Split", "indicators": "Vertical splitting aligned with internal molten lead dowel sockets", "action": "Extract corroded iron/lead pin; repoint with hydraulic lime NHL 3.5"},
                {"name": "Panel-to-Quoin Relief Shear", "indicators": "Vertical separation crack between rigid quoin and flexible rubble", "action": "Install flexible helical stainless stitches bridging quoin to rubble panel"}
            ],
            "tolerances": "Arris compressive crushing: 0mm | Dowel heave < 1.0mm | Relief shear < 2.0mm",
            "binder": "Coarse hydraulic lime NHL 3.5 with crushed granite grit fines (1:2 mix)",
            "euro_rates": "Corner block redressing: €510–€980/stone | Stitch to rubble panel: €85–€160/m",
            "standards": ["RICS Building Pathology Guidelines", "CIRIA Rock Engineering in Conservation", "Historic England Stone"]
        }
    ]

    @app.route("/field-guide")
    @app.route("/cribsheet")
    def field_guide():
        return render_template("field_guide.html", guide_items=FIELD_GUIDE_DATA)

    @app.route("/api/field-guide/csv")
    def export_field_guide_csv():
        import csv
        import io
        from flask import Response

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Archetype ID", "Archetype Name", "Category", "Geology / Substrate",
            "Primary Defects", "Key Diagnostic Indicators", "Critical Tolerances",
            "Sacrificial Binder / Mortar", "Remedial Euro Benchmark Rates", "Industry Standards & Citations"
        ])

        for item in FIELD_GUIDE_DATA:
            defects_str = "; ".join([d["name"] for d in item["defects"]])
            indicators_str = "; ".join([f"{d['name']}: {d['indicators']}" for d in item["defects"]])
            standards_str = "; ".join(item["standards"])
            writer.writerow([
                item["id"], item["name"], item["category"], item["geology"],
                defects_str, indicators_str, item["tolerances"],
                item["binder"], item["euro_rates"], standards_str
            ])

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=Global_Wall_Inspector_Field_Crib_Sheet.csv"}
        )

    # ==========================================
    # 2. Dual-Wall Comparative Analysis Studio
    # ==========================================
    @app.route("/compare")
    def compare_studio():
        walls = Wall.query.filter_by(is_published=True).order_by(Wall.title).all()
        wall_a_slug = request.args.get("wall_a", walls[0].slug if walls else "")
        wall_b_slug = request.args.get("wall_b", walls[1].slug if len(walls) > 1 else (walls[0].slug if walls else ""))
        return render_template("compare.html", walls=walls, initial_a=wall_a_slug, initial_b=wall_b_slug)

    @app.route("/api/walls/compare")
    def api_walls_compare():
        a_param = request.args.get("wall_a", "").strip()
        b_param = request.args.get("wall_b", "").strip()

        wall_a = Wall.query.filter((Wall.slug == a_param) | (Wall.id == a_param)).first()
        wall_b = Wall.query.filter((Wall.slug == b_param) | (Wall.id == b_param)).first()

        walls = Wall.query.filter_by(is_published=True).all()
        if not wall_a:
            wall_a = walls[0] if walls else None
        if not wall_b:
            wall_b = walls[1] if len(walls) > 1 else wall_a

        def build_telemetry(wall):
            if not wall:
                return {}
            w_dict = wall.to_dict()
            defects = Defect.query.filter_by(wall_id=wall.id).all()

            critical = sum(1 for d in defects if d.severity == "critical")
            moderate = sum(1 for d in defects if d.severity == "moderate")
            minor = len(defects) - critical - moderate

            GEOLOGY_MAP = {
                "brick_cavity": "Carboniferous Coal Measures Fired Clay wythes with cavity ties",
                "dry_stone": "Carboniferous Karst Limestone fieldstone (unmortared)",
                "lime_mortar": "Calcareous Sandstone & Random Rubble in hydraulic lime NHL 2.0",
                "ashlar": "Precision-dressed Portland & Bath Freestone Limestone arrises",
                "retaining_wall": "Granite & Basalt igneous gravity retention boulders",
                "cob_earth": "Subsoil clay, sand, straw and uncalcined lime mass-earth",
                "flint_knapped": "Cretaceous Upper Chalk nodules & knapped silica glass",
                "terracotta_faience": "Hollow vitrified fireclay with glazed slip surface",
                "concrete_block": "Aggregated dense concrete CMU with sand-cement mortar",
                "boulder_fieldstone": "Glacial granitic erratics & metamorphic chinking stones",
                "granite_quoin": "Dressed Leinster Granite return angle blocks"
            }

            TOLERANCE_MAP = {
                "brick_cavity": "Bed joint: 10mm ± 2mm | Max shear crack: 2.0mm",
                "dry_stone": "Batter ratio: 1:6 | Lateral bulge tolerance: <15mm",
                "lime_mortar": "Joint raking: 25mm depth | Core void limit: <10%",
                "ashlar": "Joint arris: 2.5mm ± 0.5mm | Out-of-plane step: <1.0mm",
                "retaining_wall": "Out-of-plumb batter: <25mm/m | Hydrostatic head: 0mm",
                "cob_earth": "Basal undercut limit: <40mm | Vertical fissure: <3mm",
                "flint_knapped": "Matrix recession: <8mm | Nodule pull-out: 0 units",
                "terracotta_faience": "Glaze craze width: <0.2mm | Anchor jacking: 0mm",
                "concrete_block": "Longitudinal bed crack: <1.5mm | Web shear: 0mm",
                "boulder_fieldstone": "Pin stone loss: <5% | Basal slide displacement: <5mm",
                "granite_quoin": "Arris compressive crushing: 0mm | Dowel heave: <1.0mm"
            }

            BINDER_MAP = {
                "brick_cavity": "Hydraulic Lime NHL 3.5 (1:2.5 sharp sand) - vapor permeable",
                "dry_stone": "No Binder (Dry Gravity Interlock with tightly pinned chinking)",
                "lime_mortar": "Hydraulic Lime NHL 2.0 (1:2.5 coarse sand + 5% crushed brick pozzolan)",
                "ashlar": "Non-hydraulic Fat Lime Putty (CL90) with fine stone dust (1:1.5)",
                "retaining_wall": "Unmortared dry backing with free-draining granular drainage aggregate",
                "cob_earth": "Sacrificial hydraulic lime wash (NHL 2.0) with tallow & animal hair",
                "flint_knapped": "Fat lime chalk putty mortar NHL 2.0 with chalk aggregate fines",
                "terracotta_faience": "Non-staining pure lime grout injection with thixotropic modifier",
                "concrete_block": "Sulfate-resisting hydraulic mortar Class M4",
                "boulder_fieldstone": "Dry gravity interlock; lime grout hearting consolidation where voided",
                "granite_quoin": "Coarse hydraulic lime NHL 3.5 with crushed granite grit fines"
            }

            COST_PROFILES = {
                "brick_cavity": {"yr0": "€340", "yr5": "€2,850", "yr20": "€16,200", "roi": "47.6x"},
                "dry_stone": {"yr0": "€220", "yr5": "€1,950", "yr20": "€11,800", "roi": "53.6x"},
                "lime_mortar": {"yr0": "€380", "yr5": "€3,400", "yr20": "€18,500", "roi": "48.7x"},
                "ashlar": {"yr0": "€650", "yr5": "€5,200", "yr20": "€29,400", "roi": "45.2x"},
                "retaining_wall": {"yr0": "€480", "yr5": "€4,600", "yr20": "€26,000", "roi": "54.2x"},
                "cob_earth": {"yr0": "€280", "yr5": "€2,900", "yr20": "€15,200", "roi": "54.3x"},
                "flint_knapped": {"yr0": "€420", "yr5": "€3,600", "yr20": "€19,800", "roi": "47.1x"},
                "terracotta_faience": {"yr0": "€580", "yr5": "€4,900", "yr20": "€27,500", "roi": "47.4x"},
                "concrete_block": {"yr0": "€190", "yr5": "€1,650", "yr20": "€9,400", "roi": "49.5x"},
                "boulder_fieldstone": {"yr0": "€260", "yr5": "€2,400", "yr20": "€13,600", "roi": "52.3x"},
                "granite_quoin": {"yr0": "€510", "yr5": "€4,100", "yr20": "€22,900", "roi": "44.9x"}
            }

            cost = COST_PROFILES.get(wall.wall_type, {"yr0": "€340", "yr5": "€2,850", "yr20": "€16,200", "roi": "47.6x"})

            return {
                "id": wall.id,
                "slug": wall.slug,
                "title": wall.title,
                "wall_type": wall.wall_type,
                "wall_type_label": wall.wall_type.replace("_", " ").title(),
                "country": wall.country,
                "region": wall.region or "Regional",
                "difficulty": wall.difficulty,
                "image_url": w_dict["image_url"],
                "defects_count": len(defects),
                "critical_count": critical,
                "moderate_count": moderate,
                "minor_count": minor,
                "bedrock_geology": GEOLOGY_MAP.get(wall.wall_type, "Sedimentary & Metamorphic Bedrock"),
                "tolerance": TOLERANCE_MAP.get(wall.wall_type, "Aperture < 2mm | Bulge < 15mm"),
                "binder": BINDER_MAP.get(wall.wall_type, "Hydraulic Lime NHL 2.0 / NHL 3.5"),
                "costs": cost,
                "ground_truth": [d.to_dict() for d in defects]
            }

        return jsonify({
            "success": True,
            "specimen_a": build_telemetry(wall_a),
            "specimen_b": build_telemetry(wall_b)
        })

    # ==========================================
    # 3. Interactive Geospatial Masonry Atlas
    # ==========================================
    @app.route("/map")
    def map_atlas():
        carto_api_key = os.environ.get("CARTO_API_KEY", "").strip()
        return render_template("map.html", carto_api_key=carto_api_key)

    @app.route("/api/map/walls")
    def api_map_walls():
        walls = Wall.query.filter_by(is_published=True).all()

        GEOLOGY_AND_GEO_COORDS = {
            "industrial-brick-efflorescence": {
                "lat": 53.4808, "lng": -2.2426,
                "geology": "Coal Measures Carboniferous Mudstone (Fired Clay)",
                "rainfall": "Severe (880 mm/yr)",
                "freeze_thaw": "44 cycles / yr",
                "salt_spray": "Inland Industrial / Acidic SO2"
            },
            "historic-lime-mortar-rubble": {
                "lat": 52.9800, "lng": -6.0400,
                "geology": "Ordovician Slate, Schist & Calcareous Sandstone",
                "rainfall": "Very Severe (1,250 mm/yr)",
                "freeze_thaw": "52 cycles / yr",
                "salt_spray": "High Coastal Moist Atlantic"
            },
            "ashlar-dressed-limestone-facade": {
                "lat": 53.3498, "lng": -6.2603,
                "geology": "Carboniferous Calp Limestone & Leinster Granite",
                "rainfall": "Moderate (730 mm/yr)",
                "freeze_thaw": "36 cycles / yr",
                "salt_spray": "Urban Maritime Estuary"
            },
            "granite-retaining-wall-failure": {
                "lat": 53.2707, "lng": -9.0568,
                "geology": "Galway Porphyritic Igneous Granite Dyke",
                "rainfall": "Severe Atlantic (1,150 mm/yr)",
                "freeze_thaw": "41 cycles / yr",
                "salt_spray": "Extreme Marine Bay Aerosol"
            },
            "historic-cob-earth-structure": {
                "lat": 52.3369, "lng": -6.4633,
                "geology": "Cambrian Greywacke Bedrock & Glacial Marine Marl Clay",
                "rainfall": "Moderate-High (890 mm/yr)",
                "freeze_thaw": "28 cycles / yr",
                "salt_spray": "South-East Coastal Maritime"
            },
            "knapped-flint-lime-facade": {
                "lat": 52.6309, "lng": 1.2974,
                "geology": "Cretaceous Upper White Chalk & Cryptocrystalline Silica Flint",
                "rainfall": "Low-Moderate (640 mm/yr)",
                "freeze_thaw": "39 cycles / yr",
                "salt_spray": "North Sea Maritime Winds"
            },
            "glazed-architectural-terracotta": {
                "lat": 52.4862, "lng": -1.8904,
                "geology": "Triassic Mercia Mudstone & Etruria Marl Fireclay",
                "rainfall": "Moderate (720 mm/yr)",
                "freeze_thaw": "38 cycles / yr",
                "salt_spray": "Inland Urban Atmospheric Particulate"
            },
            "hollow-concrete-blockwork-pier": {
                "lat": 51.8985, "lng": -8.4756,
                "geology": "Devonian Old Red Sandstone & Carboniferous Limestone aggregate",
                "rainfall": "High (1,020 mm/yr)",
                "freeze_thaw": "32 cycles / yr",
                "salt_spray": "River Lee Estuary & Marine Mist"
            },
            "cyclopean-boulder-fieldstone-wall": {
                "lat": 54.6549, "lng": -8.1100,
                "geology": "Dalradian Gneiss & Glacial Plutonic Granite Erratics",
                "rainfall": "Extreme Hyper-Atlantic (1,450 mm/yr)",
                "freeze_thaw": "56 cycles / yr",
                "salt_spray": "Severe Atlantic Gale Salt Spray"
            },
            "granite-quoin-dressed-corner": {
                "lat": 53.3440, "lng": -6.2550,
                "geology": "Coarse-Grained Leinster Igneous Granite Arris Blocks",
                "rainfall": "Moderate (740 mm/yr)",
                "freeze_thaw": "35 cycles / yr",
                "salt_spray": "Urban Coastal Temperate"
            },
            "traditional-irish-dry-stone": {
                "lat": 53.1250, "lng": -9.6667,
                "geology": "Karst Carboniferous Limestone Pavements & Crag",
                "rainfall": "Very Severe (1,200 mm/yr)",
                "freeze_thaw": "46 cycles / yr",
                "salt_spray": "Extreme Ocean Sea Spray (Atlantic Edge)"
            }
        }

        results = []
        for w in walls:
            geo = GEOLOGY_AND_GEO_COORDS.get(w.slug, {
                "lat": 53.35, "lng": -6.26,
                "geology": "Regional Geological Bedrock Substrate",
                "rainfall": "Moderate (800 mm/yr)",
                "freeze_thaw": "40 cycles / yr",
                "salt_spray": "Temperate Exposure"
            })
            d_count = Defect.query.filter_by(wall_id=w.id).count()
            results.append({
                "id": w.id,
                "slug": w.slug,
                "title": w.title,
                "wall_type": w.wall_type,
                "wall_type_label": w.wall_type.replace("_", " ").title(),
                "country": w.country,
                "region": w.region or "Regional",
                "difficulty": w.difficulty,
                "image_url": w.to_dict()["image_url"],
                "lat": geo["lat"],
                "lng": geo["lng"],
                "geology": geo["geology"],
                "rainfall": geo["rainfall"],
                "freeze_thaw": geo["freeze_thaw"],
                "salt_spray": geo["salt_spray"],
                "defects_count": d_count,
                "inspect_url": f"/inspect/{w.slug}"
            })

        return jsonify({"success": True, "count": len(results), "walls": results})

    @app.route("/admin/export/attempts.csv")
    @admin_required
    def export_attempts_csv():
        import csv
        import io
        from flask import Response

        selected_cohort = request.args.get("cohort", "").strip().upper()
        selected_assignment = request.args.get("assignment", "").strip().upper()

        query = AssessmentAttempt.query
        if selected_cohort:
            query = query.filter_by(cohort_code=selected_cohort)
        if selected_assignment:
            query = query.filter(
                (AssessmentAttempt.cohort_code == selected_assignment) |
                (AssessmentAttempt.assignment_code == selected_assignment) |
                (AssessmentAttempt.student_session_id.like(f"%{selected_assignment}%"))
            )

        attempts = query.order_by(AssessmentAttempt.created_at.desc()).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Attempt ID", "Date/Time UTC", "Student Name", "Assignment PIN",
            "Cohort Code", "Wall ID", "Score %", "Status",
            "True Hits", "False Alarms", "False Negatives"
        ])
        for a in attempts:
            writer.writerow([
                a.id,
                a.created_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(a, 'created_at', None) else "",
                a.student_name,
                a.assignment_code or "",
                a.cohort_code or "GENERAL",
                a.wall_id,
                a.score_percentage,
                "PASSED" if a.passed else "REVISE",
                a.true_positives,
                a.false_positives,
                a.false_negatives
            ])

        filename = f"inspector_attempts_{selected_cohort or selected_assignment or 'ALL'}.csv"
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    # Progressive Web App (PWA) Manifest & Service Worker
    @app.route("/manifest.json")
    def serve_manifest():
        return send_from_directory("static", "manifest.json", mimetype="application/manifest+json")

    @app.route("/manifest-admin.json")
    def serve_manifest_admin():
        manifest = {
            "name": "Wall Capture Admin - Global Wall Inspector",
            "short_name": "WallCapture",
            "id": "/mobile/admin",
            "description": "On-site masonry wall photo capture and catalog publishing.",
            "start_url": "/mobile/admin",
            "scope": "/mobile/admin",
            "display": "standalone",
            "background_color": "#0b1329",
            "theme_color": "#0f172a",
            "orientation": "portrait-primary",
            "icons": [
                {
                    "src": "/static/icons/admin-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any"
                },
                {
                    "src": "/static/icons/admin-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any"
                },
                {
                    "src": "/static/icons/admin-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable"
                }
            ]
        }
        return jsonify(manifest), 200, {"Content-Type": "application/manifest+json"}

    @app.route("/manifest-student.json")
    def serve_manifest_student():
        manifest = {
            "name": "Student Stonework Portfolio - Global Wall Inspector",
            "short_name": "StonePortfolio",
            "id": "/mobile/student",
            "description": "Student masonry coursework photography and self-critique portfolio.",
            "start_url": "/mobile/student",
            "scope": "/mobile/student",
            "display": "standalone",
            "background_color": "#0b1329",
            "theme_color": "#0f172a",
            "orientation": "portrait-primary",
            "icons": [
                {
                    "src": "/static/icons/student-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any"
                },
                {
                    "src": "/static/icons/student-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any"
                },
                {
                    "src": "/static/icons/student-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable"
                }
            ]
        }
        return jsonify(manifest), 200, {"Content-Type": "application/manifest+json"}

    @app.route("/sw.js")
    def serve_sw():
        return send_from_directory("static", "sw.js", mimetype="application/javascript")

    # Mobile Field Capture (Admin)
    @app.route("/mobile/admin")
    @admin_required
    def mobile_admin_capture():
        return render_template("mobile_admin_capture.html", wall_types=list(TAXONOMY_BY_WALL_TYPE.keys()))

    @app.route("/mobile/admin/upload", methods=["POST"])
    @admin_required
    def mobile_admin_upload():
        try:
            file = request.files.get("wall_image")
            if not file or not file.filename:
                return jsonify({"success": False, "error": "No image file received from camera"}), 400

            title = request.form.get("title", "Field Wall Specimen").strip()
            slug = secure_filename(title.lower().replace(" ", "-")) + "-" + uuid.uuid4().hex[:6]
            image_url_direct = None
            filename = None

            c_url = os.getenv("CLOUDINARY_URL", "").strip()
            if c_url:
                try:
                    upload_result = cloudinary.uploader.upload(
                        file,
                        folder="wall_inspector",
                        public_id=slug,
                        overwrite=True,
                        resource_type="image"
                    )
                    image_url_direct = upload_result.get("secure_url")
                except Exception as cloud_err:
                    print(f"Cloudinary mobile upload fallback to local: {cloud_err}")
                    file.seek(0)
                    ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
                    filename = f"{slug}{ext}"
                    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            else:
                ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
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
            return jsonify({"success": True, "wall": wall.to_dict()})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": str(e)}), 500

    # Mobile Practical Portfolio & Self-Critique (Student)
    @app.route("/mobile/student")
    def mobile_student_portfolio():
        return render_template("mobile_student_portfolio.html", wall_types=list(TAXONOMY_BY_WALL_TYPE.keys()))

    @app.route("/mobile/student/upload", methods=["POST"])
    def mobile_student_upload():
        try:
            file = request.files.get("work_image")
            if not file or not file.filename:
                return jsonify({"success": False, "error": "No workpiece photo received"}), 400

            student_name = request.form.get("student_name", "Student Mason").strip()
            student_identifier = request.form.get("student_identifier", "STU-2026").strip().upper()
            cohort_code = request.form.get("cohort_code", "GENERAL").strip().upper()
            title = request.form.get("title", "Practical Masonry Workpiece").strip()
            wall_type = request.form.get("wall_type", "dry_stone")
            self_critique = request.form.get("self_critique", "")

            import json
            raw_rubric = request.form.get("rubric_scores", "{}")
            try:
                rubric_scores = json.loads(raw_rubric)
            except Exception:
                rubric_scores = {}

            sub_slug = f"student-{student_identifier.lower()}-{uuid.uuid4().hex[:6]}"
            image_url_direct = None
            filename = None

            c_url = os.getenv("CLOUDINARY_URL", "").strip()
            if c_url:
                try:
                    upload_result = cloudinary.uploader.upload(
                        file,
                        folder=f"wall_inspector/students/{student_identifier}",
                        public_id=sub_slug,
                        overwrite=True,
                        resource_type="image"
                    )
                    image_url_direct = upload_result.get("secure_url")
                except Exception as cloud_err:
                    print(f"Cloudinary student upload fallback: {cloud_err}")
                    file.seek(0)
                    ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
                    filename = f"{sub_slug}{ext}"
                    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            else:
                ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
                filename = f"{sub_slug}{ext}"
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

            raw_tilt = request.form.get("tilt_angle")
            try:
                tilt_angle = float(raw_tilt) if raw_tilt not in (None, "") else None
            except Exception:
                tilt_angle = None

            submission = StudentSubmission(
                student_name=student_name,
                student_identifier=student_identifier,
                cohort_code=cohort_code,
                title=title,
                wall_type=wall_type,
                image_filename=filename,
                image_url_direct=image_url_direct,
                rubric_scores=rubric_scores,
                self_critique=self_critique,
                tilt_angle=tilt_angle
            )
            db.session.add(submission)
            db.session.commit()
            return jsonify({"success": True, "submission": submission.to_dict()})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/student/submission/<sub_id>/review", methods=["POST"])
    @admin_required
    def api_review_student_submission(sub_id):
        try:
            submission = StudentSubmission.query.get(sub_id)
            if not submission:
                return jsonify({"success": False, "error": "Submission not found"}), 404

            feedback = ""
            badge = ""
            voice_url = ""

            if request.is_json:
                data = request.get_json() or {}
                feedback = data.get("instructor_feedback", "").strip()
                badge = data.get("instructor_badge", "").strip()
                voice_url = data.get("instructor_voice_url", "").strip()
            else:
                feedback = request.form.get("instructor_feedback", "").strip()
                badge = request.form.get("instructor_badge", "").strip()
                voice_url = request.form.get("instructor_voice_url", "").strip()

                voice_file = request.files.get("voice_audio")
                if voice_file and voice_file.filename:
                    voice_filename = f"voice-{sub_id}-{uuid.uuid4().hex[:6]}.webm"
                    c_url = os.getenv("CLOUDINARY_URL", "").strip()
                    if c_url:
                        try:
                            cloud_res = cloudinary.uploader.upload(
                                voice_file,
                                folder="wall_inspector/voice_critiques",
                                public_id=os.path.splitext(voice_filename)[0],
                                resource_type="auto"
                            )
                            voice_url = cloud_res.get("secure_url")
                        except Exception as ce:
                            print(f"Cloudinary audio fallback: {ce}")
                            voice_file.seek(0)
                            audio_path = os.path.join(app.root_path, "static", "audio")
                            os.makedirs(audio_path, exist_ok=True)
                            voice_file.save(os.path.join(audio_path, voice_filename))
                            voice_url = f"/static/audio/{voice_filename}"
                    else:
                        audio_path = os.path.join(app.root_path, "static", "audio")
                        os.makedirs(audio_path, exist_ok=True)
                        voice_file.save(os.path.join(audio_path, voice_filename))
                        voice_url = f"/static/audio/{voice_filename}"

            submission.instructor_feedback = feedback
            if badge:
                submission.instructor_badge = badge
            if voice_url:
                submission.instructor_voice_url = voice_url

            db.session.commit()
            return jsonify({"success": True, "submission": submission.to_dict()})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/student/portfolio/<student_id>")
    def api_student_portfolio(student_id):
        submissions = StudentSubmission.query.filter_by(
            student_identifier=student_id.strip().upper()
        ).order_by(StudentSubmission.created_at.desc()).all()
        return jsonify({"submissions": [s.to_dict() for s in submissions]})

    @app.route("/api/student/passport", methods=["GET"])
    def api_student_passport():
        query_name = request.args.get("name", "").strip()
        query_id = request.args.get("identifier", "").strip()

        ARCHETYPE_LABELS = {
            "brick_cavity": "Brick Cavity",
            "dry_stone": "Dry Stone",
            "lime_mortar": "Historic Lime",
            "ashlar": "Ashlar Stone",
            "retaining_wall": "Retaining Wall",
            "cob_earth": "Cob & Earth",
            "flint_knapped": "Knapped Flint",
            "terracotta_faience": "Terracotta & Faience",
            "concrete_block": "Concrete Block",
            "boulder_fieldstone": "Field Boulder",
            "granite_quoin": "Granite Quoin"
        }

        # Query attempts matching student name or session
        attempts = []
        submissions = []
        certs = []

        if query_name or query_id:
            name_term = query_name or query_id
            attempts = AssessmentAttempt.query.filter(
                (AssessmentAttempt.student_name.ilike(f"%{name_term}%")) |
                (AssessmentAttempt.student_session_id.ilike(f"%{name_term}%"))
            ).order_by(AssessmentAttempt.created_at.desc()).all()

            submissions = StudentSubmission.query.filter(
                (StudentSubmission.student_name.ilike(f"%{name_term}%")) |
                (StudentSubmission.student_identifier.ilike(f"%{name_term}%"))
            ).order_by(StudentSubmission.created_at.desc()).all()

            certs = Certificate.query.filter(
                Certificate.student_name.ilike(f"%{name_term}%")
            ).order_by(Certificate.issued_at.desc()).all()
        else:
            # General / most recent activity
            attempts = AssessmentAttempt.query.order_by(AssessmentAttempt.created_at.desc()).limit(20).all()
            submissions = StudentSubmission.query.order_by(StudentSubmission.created_at.desc()).limit(10).all()
            certs = Certificate.query.order_by(Certificate.issued_at.desc()).limit(5).all()

        # Build archetype score buckets
        archetype_scores = {k: [] for k in ARCHETYPE_LABELS.keys()}
        wall_cache = {}

        for att in attempts:
            if att.wall_id not in wall_cache:
                wall = Wall.query.get(att.wall_id)
                wall_cache[att.wall_id] = wall.wall_type if wall else "dry_stone"
            w_type = wall_cache[att.wall_id]
            if w_type in archetype_scores and att.score_percentage is not None:
                archetype_scores[w_type].append(att.score_percentage)

        for sub in submissions:
            w_type = sub.wall_type or "dry_stone"
            if w_type in archetype_scores:
                scores = list((sub.rubric_scores or {}).values())
                if scores:
                    pct = (sum(scores) / (len(scores) * 4.0)) * 100
                    archetype_scores[w_type].append(pct)

        # Calculate radar chart data points
        radar_data = []
        evaluated_count = 0
        all_scores = []

        for arc_key, arc_label in ARCHETYPE_LABELS.items():
            scores_list = archetype_scores[arc_key]
            if scores_list:
                avg_score = round(sum(scores_list) / len(scores_list), 1)
                evaluated_count += 1
                all_scores.append(avg_score)
            else:
                avg_score = 0.0

            radar_data.append({
                "archetype": arc_key,
                "label": arc_label,
                "score": avg_score,
                "evaluations": len(scores_list)
            })

        mean_score = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0.0
        cpd_hours = round((len(attempts) * 1.0) + (len(submissions) * 1.5) + (3.0 if certs else 0.5), 1)

        # Accreditation Tier Calculation
        if evaluated_count >= 7 and mean_score >= 80:
            tier_name = "Master Diagnostic Pathologist"
            tier_level = 3
            tier_badge = "🥇 LEVEL 3: MASTER PATHOLOGIST"
            tier_desc = "Accredited master-level proficiency across complex historic and modern masonry archetypes."
        elif (evaluated_count >= 4 and mean_score >= 70) or certs:
            tier_name = "Certified Conservation Inspector"
            tier_level = 2
            tier_badge = "🥈 LEVEL 2: CONSERVATION INSPECTOR"
            tier_desc = "Certified competency in pathology diagnostics, structural appraisal, and hydraulic lime repair specifications."
        elif evaluated_count >= 1:
            tier_name = "Field Masonry Technician"
            tier_level = 1
            tier_badge = "🥉 LEVEL 1: FIELD TECHNICIAN"
            tier_desc = "Foundational proficiency in visual defect identification and diagnostic marking."
        else:
            tier_name = "Apprentice Surveyor"
            tier_level = 0
            tier_badge = "🔰 APPRENTICE SURVEYOR"
            tier_desc = "Commenced diagnostic training. Complete assigned examinations to unlock certification tiers."

        resolved_name = query_name or (attempts[0].student_name if attempts else "Guest Inspector")

        return jsonify({
            "success": True,
            "student_name": resolved_name,
            "tier_name": tier_name,
            "tier_level": tier_level,
            "tier_badge": tier_badge,
            "tier_desc": tier_desc,
            "cpd_hours": cpd_hours,
            "mean_score": mean_score,
            "total_attempts": len(attempts),
            "total_submissions": len(submissions),
            "radar": radar_data,
            "certificates": [
                {
                    "code": c.certificate_code,
                    "tier": c.tier,
                    "score": c.average_score,
                    "issued_at": c.issued_at.strftime("%Y-%m-%d") if c.issued_at else ""
                } for c in certs
            ]
        })

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
