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
        {"id": "expansion_failure", "label": "Vertical Thermal Expansion Fracture"},
        {"id": "inappropriate_cement_strap", "label": "Inappropriate Portland Cement Pointing & Edge Spall"},
        {"id": "chimney_decay", "label": "Roofline Chimney Stack Decay & Flue Acid Attack"},
        {"id": "rising_damp_salt", "label": "Capillary Rising Damp Tide Mark & Subflorescence"},
        {"id": "irish_wigging_failure", "label": "Irish Wigging & Georgian Tuckpointing Ribbon Loss"},
        {"id": "gauged_arch_failure", "label": "Gauged Rubbing Brick Jack Arch Sag & Dropped Key"}
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
        {"id": "rubble_voiding", "label": "Internal Core Rubble Voiding"},
        {"id": "ribbon_pointing_failure", "label": "Impermeable Ribbon Pointing & Cement Trap"},
        {"id": "cryptogamic_lichen_attack", "label": "Biogenic Cryptogamic Colonization & Acid Etch"},
        {"id": "faunal_mason_bee_boring", "label": "Faunal Mason Bee Boring & Avian Guano"}
    ],
    "stone_rubble": [
        {"id": "continuous_vertical_joint", "label": "Continuous Vertical Joint Alignment"},
        {"id": "through_stone_failure", "label": "Missing or Fractured Through-Stone"},
        {"id": "face_bedding_delamination", "label": "Face-Bedding Delamination & Exfoliation"},
        {"id": "lime_runoff_staining", "label": "Lime Run-Off & Calcite Leaching"},
        {"id": "cryptoflorescence", "label": "Cryptoflorescence / Sub-Surface Salt Burst"},
        {"id": "frost_attack_spall", "label": "Frost Attack Wedging & Matrix Shatter"}
    ],
    "ashlar": [
        {"id": "ashlar_spall", "label": "Surface Face Delamination / Exfoliation"},
        {"id": "joint_separation", "label": "Fine Ashlar Joint Separation"},
        {"id": "iron_cramp_burst", "label": "Oxidized Iron Cramp Stone Fracture"},
        {"id": "contour_scaling", "label": "Contour Scaling in Sandstone"},
        {"id": "gypsum_crust_cavitation", "label": "Sheltered Gypsum Crust & Cavitation"},
        {"id": "impermeable_coating_blister", "label": "Impermeable Coating & Sealant Spall"}
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
    {"id": "monitor_gauge", "label": "Calibrated Tell-Tale Crack Gauge Monitoring"},
    {"id": "indent_stone", "label": "Surgical Stone Indenting & Re-facing (NHL 2)"},
    {"id": "poultice_desalt", "label": "Nebulous Water Mist & Lime Poultice Desalination"},
    {"id": "biocide_steam", "label": "Superheated Dry Steam (150°C) & Quaternary Biocide"},
    {"id": "coating_removal", "label": "Latex Poultice Paint Stripping & Desalination"},
    {"id": "wigging_restore", "label": "Traditional Irish Wigging / Tuckpointing Restoration"},
    {"id": "chimney_rebuild", "label": "Chimney Stack Deconstruction & Flaunching Rebuild"}
]

SKILL_DEFECT_MODES = [
    {
        "id": "core_voiding",
        "label": "Core Voids / Cavitation",
        "category": "dry_stone",
        "hint": "Internal hearting or pinning stones settled or washed out, leaving cavernous structural voids between wall leaves."
    },
    {
        "id": "delamination_exfoliation",
        "label": "Delamination / Exfoliation / Contour Scaling",
        "category": "sedimentary_decay",
        "hint": "Flaking or splitting of sedimentary rock parallel to natural bedding planes due to sub-florescence or frost expansion."
    },
    {
        "id": "biological_colonisation",
        "label": "Biological Colonisation (Lichen / Moss / Macroflora)",
        "category": "biological",
        "hint": "Crustose or foliose lichen/moss producing oxalic and carbonic acids, etching stone pores and retaining destructive moisture."
    },
    {
        "id": "pinning_loss",
        "label": "Pinning Stone Loss / Gallet Dislodgement",
        "category": "dry_stone",
        "hint": "Missing wedge gallets or pinning spalls that transfer bearing weight between irregular rubble units."
    },
    {
        "id": "bed_joint_slump",
        "label": "Bed Joint Slump / Structural Settlement",
        "category": "structural",
        "hint": "Downward dipping of masonry courses from differential sub-base consolidation or shear failure."
    },
    {
        "id": "inappropriate_cement_strap",
        "label": "Inappropriate Cement Strap / Ribbon Pointing",
        "category": "pointing_defect",
        "hint": "Hard, impermeable Portland cement ribbon profile projecting proud of stone face, trapping dampness and inducing edge spalling."
    },
    {
        "id": "mortar_erosion",
        "label": "Mortar Erosion / Joint Washout",
        "category": "joint_decay",
        "hint": "Binder dissolution and sand washout deeper than 15-25mm from wall face, destabilising stone support."
    },
    {
        "id": "stepped_crack",
        "label": "Stepped Bed Joint Fracture / Shear Crack",
        "category": "structural",
        "hint": "Diagonal stair-step fracture following weakened bed and perpend joints due to ground movement or settlement."
    },
    {
        "id": "expansion_failure",
        "label": "Continuous Vertical Joint Shear / Expansion Rupture",
        "category": "structural",
        "hint": "Unbonded straight vertical joints spanning courses, creating a continuous split line vulnerable to lateral collapse."
    },
    {
        "id": "spalling",
        "label": "Arris Fretting / Surface Spalling",
        "category": "surface_loss",
        "hint": "Detachment of outer stone or brick arrises from concentrated compressive stresses or freeze-thaw bursting."
    },
    {
        "id": "rubble_voiding",
        "label": "Interstitial Matrix Cavitation / Rubble Voiding",
        "category": "core_defect",
        "hint": "Severe loss of bedding binder between irregular rounded boulders leaving unbonded bridging voids."
    },
    {
        "id": "rising_damp_salt",
        "label": "Basal Moisture Ingress / Salt Efflorescence",
        "category": "moisture",
        "hint": "Capillary suction from ground level leaving powdery mineral salt blooms and decaying lower arrises."
    },
    {
        "id": "coping_displacement",
        "label": "Coping Stone Displacement / Weathering",
        "category": "capping_defect",
        "hint": "Dislodged, tipped, or missing capping stones allowing driving rain into core masonry."
    },
    {
        "id": "lateral_bulge",
        "label": "Lateral Bulge / Wythe Separation",
        "category": "structural",
        "hint": "Out-of-plumb displacement where outer face pushes outwards away from core due to missing through-stones."
    },
    {
        "id": "through_stone_failure",
        "label": "Missing Through-Stones / Tie Defect",
        "category": "structural",
        "hint": "Absence of transverse tie stones spanning the full thickness of the wall, reducing composite structural stability."
    },
    {
        "id": "efflorescence",
        "label": "Cryptoflorescence / Salt Crystallisation",
        "category": "chemical",
        "hint": "Sub-surface salt growth expanding inside pores and busting stone matrix apart."
    },
    {
        "id": "ashlar_spall",
        "label": "Ashlar Cramp Jacking / Surface Rupture",
        "category": "corrosion",
        "hint": "Corrosion of embedded ferrous iron ties/cramps expanding up to 7x original volume and popping stone faces."
    },
    {
        "id": "flint_unseating",
        "label": "Flint Unseating / Gallet Loss",
        "category": "masonry_loss",
        "hint": "Loss of glassy nodules or flint knappings from the matrix due to decomposed lime bedding."
    },
    {
        "id": "hydrostatic_bulge",
        "label": "Hydrostatic Bulge / Retaining Failure",
        "category": "hydrostatic",
        "hint": "Surcharge of trapped groundwater behind retaining structure with non-functioning or missing weep holes."
    },
    {
        "id": "vegetation_root_jacking",
        "label": "Vegetation & Woody Root Jacking",
        "category": "biological",
        "hint": "Invasive woody roots (ivy, elder, buddleja) expanding within joints and dislodging blocks."
    }
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

def get_wall_defect_modes(wall):
    """
    Returns prioritized defect modes for this wall image and all defect modes.
    1. If wall.assessment_defect_modes is configured, those are prioritized.
    2. Otherwise, defaults prioritized modes to:
       - The categories of any ground-truth defects on this wall.
       - Plus 3-4 plausible distractors from SKILL_DEFECT_MODES matching this wall's wall_type.
    3. All modes includes all SKILL_DEFECT_MODES plus any custom titles added to this wall.
    """
    prioritized = []
    custom_modes = []
    standard_map = {m["id"]: m for m in SKILL_DEFECT_MODES}

    configured_modes = getattr(wall, "assessment_defect_modes", None) or []
    if configured_modes:
        for cm in configured_modes:
            if isinstance(cm, dict):
                mid = cm.get("id", "")
                mlabel = cm.get("label", mid)
                mhint = cm.get("hint", "")
                if mid in standard_map:
                    prioritized.append(standard_map[mid])
                else:
                    item = {"id": mid, "label": mlabel, "hint": mhint or "Specimen-specific defect mode.", "is_custom": True}
                    prioritized.append(item)
                    custom_modes.append(item)
            elif isinstance(cm, str):
                if cm in standard_map:
                    prioritized.append(standard_map[cm])
                else:
                    item = {"id": cm, "label": cm.replace("_", " ").title(), "hint": "Specimen-specific defect mode.", "is_custom": True}
                    prioritized.append(item)
                    custom_modes.append(item)
    else:
        gt_cats = set()
        wall_defects = []
        if getattr(wall, "id", None):
            try:
                wall_defects = Defect.query.filter_by(wall_id=wall.id).all()
            except Exception:
                wall_defects = getattr(wall, "defects", []) or []
        elif hasattr(wall, "defects"):
            wall_defects = wall.defects or []

        for d in wall_defects:
            gt_cats.add(d.category)
            if d.category not in standard_map:
                item = {"id": d.category, "label": d.title or d.category.replace("_", " ").title(), "hint": d.explanation or "Pathological defect on this specimen.", "is_custom": True}
                custom_modes.append(item)

        for cat in gt_cats:
            if cat in standard_map:
                prioritized.append(standard_map[cat])
            else:
                for c in custom_modes:
                    if c["id"] == cat and c not in prioritized:
                        prioritized.append(c)

        for m in SKILL_DEFECT_MODES:
            if m not in prioritized:
                if m.get("category") == wall.wall_type or m.get("category") in ["structural", "joint_decay"]:
                    prioritized.append(m)
            if len(prioritized) >= 6:
                break

    all_modes = list(SKILL_DEFECT_MODES)
    existing_all_ids = set(m["id"] for m in all_modes)
    for cm in custom_modes:
        if cm["id"] not in existing_all_ids:
            all_modes.append(cm)
            existing_all_ids.add(cm["id"])

    seen_p_ids = set()
    distinct_prioritized = []
    for pm in prioritized:
        if pm["id"] not in seen_p_ids:
            distinct_prioritized.append(pm)
            seen_p_ids.add(pm["id"])

    return {
        "prioritized": distinct_prioritized,
        "all": all_modes
    }

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    upload_folder = os.path.join(app.root_path, "static", "img", "walls")
    os.makedirs(upload_folder, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = upload_folder
    assessment_folder = os.path.join(app.root_path, "static", "img", "assessments")
    os.makedirs(assessment_folder, exist_ok=True)
    app.config["ASSESSMENT_FOLDER"] = assessment_folder
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

            if "is_skill_assessment" not in wall_cols:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE walls ADD COLUMN is_skill_assessment BOOLEAN DEFAULT FALSE;"))
                    conn.commit()

            if "assessment_defect_modes" not in wall_cols:
                with db.engine.connect() as conn:
                    col_type = "JSON" if db.engine.dialect.name == "postgresql" else "TEXT"
                    conn.execute(text(f"ALTER TABLE walls ADD COLUMN assessment_defect_modes {col_type};"))
                    conn.commit()

            if db.engine.dialect.name == "postgresql":
                with db.engine.connect() as conn:
                    try:
                        conn.execute(text("ALTER TABLE walls ALTER COLUMN image_filename DROP NOT NULL;"))
                        conn.commit()
                    except Exception as relax_err:
                        pass

            defect_cols = [c["name"] for c in inspector.get_columns("defects")]
            if "remedial_action" not in defect_cols:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE defects ADD COLUMN remedial_action VARCHAR(150) DEFAULT 'repoint_lime';"))
                    conn.commit()
            if "tolerance_radius" not in defect_cols:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE defects ADD COLUMN tolerance_radius FLOAT DEFAULT 0.06;"))
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
                "description": "18th-century random rubble masonry wall showing deep mortar washout, joint voiding, and sacrificial binder erosion.",
                "country": "Ireland",
                "region": "Wicklow",
                "wall_type": "lime_mortar",
                "structural_function": "boundary",
                "difficulty": "intermediate",
                "image_filename": "lime_coursed_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.32, "y_min": 0.25, "x_max": 0.80, "y_max": 0.75,
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
                "description": "Fine-jointed ashlar limestone masonry displaying structural diagonal shear fracture and arrises edge spalling.",
                "country": "Ireland",
                "region": "Dublin",
                "wall_type": "ashlar",
                "structural_function": "load_bearing",
                "difficulty": "advanced",
                "image_filename": "ashlar_cracking_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.24, "y_min": 0.10, "x_max": 0.82, "y_max": 0.85,
                        "category": "joint_separation", "severity": "critical",
                        "remedial_action": "helical_stitch",
                        "title": "Ashlar Structural Shear Fracture",
                        "explanation": "Foundation rotation and differential structural settlement opening wide diagonal fracture across precision dressed ashlar blocks."
                    }
                ]
            },
            {
                "slug": "granite-retaining-wall-failure",
                "title": "Granite Gravity Retaining Wall",
                "description": "Heavy coursed granite retaining structure experiencing hydrostatic outward bulging and drainage weep hole siltation.",
                "country": "Ireland",
                "region": "Galway",
                "wall_type": "retaining_wall",
                "structural_function": "retaining",
                "difficulty": "advanced",
                "image_filename": "retaining_granite_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.30, "y_min": 0.25, "x_max": 0.85, "y_max": 0.85,
                        "category": "hydrostatic_bulge", "severity": "critical",
                        "remedial_action": "drainage_relief",
                        "title": "Hydrostatic Outward Bulge & Silted Weeps",
                        "explanation": "Excess pore water pressure behind the masonry facing forcing stones out-of-plumb due to silted drainage weep pipes."
                    }
                ]
            },
            {
                "slug": "historic-cob-earth-structure",
                "title": "Vernacular Cob & Rammed Earth Wall",
                "description": "Mass-earth subsoil and straw wall exhibiting basal rain-splash erosion, undercut notch, and vertical desiccation cracks.",
                "country": "Ireland",
                "region": "Wexford",
                "wall_type": "cob_earth",
                "structural_function": "load_bearing",
                "difficulty": "intermediate",
                "image_filename": "cob_earth_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.18, "y_min": 0.45, "x_max": 0.80, "y_max": 0.93,
                        "category": "joint_separation", "severity": "critical",
                        "remedial_action": "rebuild_section",
                        "title": "Basal Rain-Splash Undercut & Notch Erosion",
                        "explanation": "Mass unbaked earth and straw wall displaying deep concave erosion notch along ground level from splash-back."
                    }
                ]
            },
            {
                "slug": "knapped-flint-lime-facade",
                "title": "Knapped Flint & Flushwork Wall",
                "description": "Decorative and protective knapped field-flint facing showing chalk-matrix erosion and stone nodule pop-outs.",
                "country": "United Kingdom",
                "region": "Norfolk",
                "wall_type": "flint_knapped",
                "structural_function": "load_bearing",
                "difficulty": "advanced",
                "image_filename": "flint_knapped_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.20, "y_min": 0.15, "x_max": 0.85, "y_max": 0.80,
                        "category": "lime_washout", "severity": "moderate",
                        "remedial_action": "repoint_lime",
                        "title": "Flint Nodule Unseating & Matrix Washout",
                        "explanation": "Chalk-lime mortar matrix eroded by driving rain, loosening mechanical bond on knapped silica nodules."
                    }
                ]
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
                "image_filename": "ashlar_cracking_01.jpg",
                "image_url_direct": None,
                "defects": []
            },
            {
                "slug": "hollow-concrete-blockwork-pier",
                "title": "Modular Concrete Blockwork (CMU) Structural Framing",
                "description": "Reinforced concrete frame with modular concrete block (CMU) infill panels, displaying unreinforced vertical movement joints and bed-joint shear stresses.",
                "country": "International",
                "region": "Industrial Zone",
                "wall_type": "concrete_block",
                "structural_function": "load_bearing",
                "difficulty": "beginner",
                "image_filename": "ultratech_cmu_blockwork_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.16, "y_min": 0.15, "x_max": 0.64, "y_max": 0.72,
                        "category": "block_bed_crack", "severity": "moderate",
                        "remedial_action": "helical_stitch",
                        "title": "CMU Infill Movement Joint Omission",
                        "explanation": "Continuous concrete masonry unit infill panels installed without vertical contraction control joints every 6m, risking restrained shrinkage shear cracking."
                    }
                ]
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
                "image_filename": "drystone_collapse_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.25, "y_min": 0.22, "x_max": 0.77, "y_max": 0.87,
                        "category": "roll_out", "severity": "critical",
                        "remedial_action": "rebuild_section",
                        "title": "Basal Boulder Sliding & Chinking Loss",
                        "explanation": "Unmortared erratic granite boulders sliding forward under gravity and slope surcharge due to loss of basal pin chinking."
                    }
                ]
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
                "image_filename": "ashlar_cracking_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.30, "y_min": 0.20, "x_max": 0.70, "y_max": 0.70,
                        "category": "arment_crushing", "severity": "critical",
                        "remedial_action": "rebuild_section",
                        "title": "Quoin Arris Compressive Crushing & Edge Spall",
                        "explanation": "Extreme vertical point load concentration along dressed return corner arris causing diagonal stone fractures."
                    }
                ]
            },
            {
                "slug": "ultratech-stone-continuous-joints",
                "title": "Uncoursed Rubble: Continuous Vertical Joint Shear",
                "description": "Uncoursed rubble stone masonry exhibiting continuous vertical joints without bond staggering, forming a vertical failure plane under compressive load, alongside oversized mortar beds (>25mm).",
                "country": "India / International",
                "region": "Rajasthan",
                "wall_type": "stone_rubble",
                "structural_function": "boundary",
                "difficulty": "intermediate",
                "image_filename": "ultratech_stone_joints_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.32, "y_min": 0.12, "x_max": 0.55, "y_max": 0.68,
                        "category": "continuous_vertical_joint", "severity": "critical",
                        "remedial_action": "helical_stitch",
                        "title": "Continuous Vertical Joint Alignment",
                        "explanation": "Vertical joints un-staggered across multiple courses form an unbonded vertical cleavage plane prone to splitting under compression (IS 1597 Part 1)."
                    },
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.10, "y_min": 0.15, "x_max": 0.30, "y_max": 0.55,
                        "category": "lime_runoff_staining", "severity": "moderate",
                        "remedial_action": "repoint_lime",
                        "title": "Excessive Mortar Bed Thickness (>25mm)",
                        "explanation": "Mortar joints exceed 25mm thickness without stone spall packing, creating excessive shrinkage stress and uneven load distribution."
                    }
                ]
            },
            {
                "slug": "ultratech-stone-improper-bedding",
                "title": "Sedimentary Stone: Face-Bedding Delamination",
                "description": "Sedimentary stone masonry laid with quarry natural bedding planes oriented vertically parallel to the wall face (face-bedding), resulting in sheet exfoliation and compressive delamination.",
                "country": "India / International",
                "region": "Madhya Pradesh",
                "wall_type": "stone_rubble",
                "structural_function": "load_bearing",
                "difficulty": "advanced",
                "image_filename": "ultratech_stone_bedding_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.20, "y_min": 0.12, "x_max": 0.88, "y_max": 0.76,
                        "category": "face_bedding_delamination", "severity": "critical",
                        "remedial_action": "rebuild_section",
                        "title": "Face-Bedding Orientation & Laminae Delamination",
                        "explanation": "Natural quarry bedding planes oriented vertically parallel to the wall face induce shear splitting, exfoliation, and compressive delamination under axial load (IS 1124 / EN 771-6)."
                    }
                ]
            },
            {
                "slug": "ultratech-stone-lime-runoff",
                "title": "Fieldstone Rubble: Severe Lime Run-Off & Calcite Crust",
                "description": "Fieldstone rubble masonry exhibiting severe calcium hydroxide leaching, white carbonate run-off staining, and sub-surface cryptoflorescence salt crystallization from water percolation.",
                "country": "India / International",
                "region": "Karnataka",
                "wall_type": "stone_rubble",
                "structural_function": "boundary",
                "difficulty": "intermediate",
                "image_filename": "ultratech_stone_limerunoff_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.25, "y_min": 0.10, "x_max": 0.68, "y_max": 0.92,
                        "category": "lime_runoff_staining", "severity": "critical",
                        "remedial_action": "repoint_lime",
                        "title": "Severe Lime Run-Off (Calcite Staining)",
                        "explanation": "Rainwater washing through uncured high-lime mortar leaches Ca(OH)2, reacting with atmospheric CO2 to deposit hard, insoluble CaCO3 crusts over the masonry face."
                    },
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.04, "y_min": 0.10, "x_max": 0.28, "y_max": 0.65,
                        "category": "cryptoflorescence", "severity": "moderate",
                        "remedial_action": "repoint_lime",
                        "title": "Sub-Surface Salt Crystallisation (Cryptoflorescence)",
                        "explanation": "Soluble sulphate and chloride salts evaporating inside stone pores generate crystallisation pressures exceeding 50 MPa, causing granular disintegration."
                    }
                ]
            },
            {
                "slug": "ultratech-stone-frost-attack",
                "title": "Exposed Stone Rubble: Critical Frost Attack",
                "description": "Exposed porous stone masonry experiencing severe freeze-thaw cycles. Water volume expansion (9%) inside saturated stone pores wedges joints apart and blows out outer stone arrises.",
                "country": "India / International",
                "region": "Himachal Pradesh",
                "wall_type": "stone_rubble",
                "structural_function": "boundary",
                "difficulty": "advanced",
                "image_filename": "ultratech_stone_frost_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.15, "y_min": 0.12, "x_max": 0.85, "y_max": 0.88,
                        "category": "frost_attack_spall", "severity": "critical",
                        "remedial_action": "rebuild_section",
                        "title": "Freeze-Thaw Ice Wedging & Stone Face Spalling",
                        "explanation": "Critical moisture saturation (>91% pore capacity) combined with sub-zero temperatures generates expansive ice crystallization pressures, wedging joints apart and shattering stone faces (EN 12371)."
                    }
                ]
            },
            {
                "slug": "ultratech-stone-through-stone-defect",
                "title": "Boundary Rubble: Missing Through-Stones & Wythe Disconnection",
                "description": "Stone boundary wall featuring dressed corner quoins but lacking transverse through-stones (headers) to tie the outer wythes together, alongside irregular vertical slab placement.",
                "country": "India / International",
                "region": "Maharashtra",
                "wall_type": "stone_rubble",
                "structural_function": "boundary",
                "difficulty": "intermediate",
                "image_filename": "ultratech_stone_coursing_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.12, "y_min": 0.15, "x_max": 0.65, "y_max": 0.85,
                        "category": "through_stone_failure", "severity": "critical",
                        "remedial_action": "helical_stitch",
                        "title": "Absence of Transverse Through-Stones (Bond Stones)",
                        "explanation": "Outer wythes lack through-stones spanning the wall thickness at 1.5m intervals, allowing independent outward buckling under internal core pressure (IS 1597)."
                    },
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.28, "y_min": 0.40, "x_max": 0.65, "y_max": 0.95,
                        "category": "continuous_vertical_joint", "severity": "moderate",
                        "remedial_action": "rebuild_section",
                        "title": "Vertical Slab Placement (Lack of Horizontal Coursing)",
                        "explanation": "Stones set on edge rather than on their natural widest bed, diminishing compressive contact area and eliminating horizontal lap interlock."
                    }
                ]
            },
            {
                "slug": "ultratech-stone-macroporous-decay",
                "title": "Porous Stone Blockwork: Pore Saturation & Decay",
                "description": "Dressed volcanic/sedimentary stone blocks exhibiting excessive open pore structure, promoting capillary water suction, deep salt transport, and matrix weakening.",
                "country": "India / International",
                "region": "Deccan Plateau",
                "wall_type": "ashlar",
                "structural_function": "load_bearing",
                "difficulty": "intermediate",
                "image_filename": "ultratech_stone_pores_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.10, "y_min": 0.15, "x_max": 0.90, "y_max": 0.85,
                        "category": "ashlar_spall", "severity": "moderate",
                        "remedial_action": "repoint_lime",
                        "title": "Vesicular Pore Network & Accelerated Moisture Uptake",
                        "explanation": "High open-porosity matrix absorbs rainwater rapidly, accelerating freeze-thaw decay and serving as a conduit for mobile salt deposition."
                    }
                ]
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
            },
            {
                "slug": "modern-brick-settlement-shear",
                "title": "Edwardian Semi-Detached Flank Wall",
                "description": "Flank elevation adjacent to corner bay exhibiting diagonal stepped settlement shear fracture through mortar bed and perpendicular joints from differential foundation subsidence.",
                "country": "United Kingdom",
                "region": "London",
                "wall_type": "brick_cavity",
                "structural_function": "load_bearing",
                "difficulty": "intermediate",
                "image_filename": "modern_brick_damage_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.28, "y_min": 0.12, "x_max": 0.74, "y_max": 0.87,
                        "category": "stepped_crack", "severity": "critical",
                        "remedial_action": "helical_stitch",
                        "title": "Diagonal Stepped Settlement Shear Fracture",
                        "explanation": "Foundation rotation from seasonal subsoil desiccation generates diagonal principal tensile stresses, propagating stepped fractures through bed and perpend joints."
                    }
                ]
            },
            {
                "slug": "commercial-brick-thermal-expansion",
                "title": "Commercial Brickwork Gable Wall",
                "description": "Continuous unrestrained brick masonry gable elevation constructed without vertical movement control joints, exhibiting vertical thermal expansion fissures.",
                "country": "United Kingdom",
                "region": "Leeds",
                "wall_type": "brick_cavity",
                "structural_function": "load_bearing",
                "difficulty": "intermediate",
                "image_filename": "brick_thermal_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.40, "y_min": 0.05, "x_max": 0.64, "y_max": 0.95,
                        "category": "expansion_failure", "severity": "moderate",
                        "remedial_action": "helical_stitch",
                        "title": "Vertical Thermal Expansion Movement Fissure",
                        "explanation": "Continuous 16-meter brick panel built without expansion joints undergoes irreversible thermal expansion under solar exposure, cracking near restrained returns."
                    }
                ]
            },
            {
                "slug": "industrial-fired-brick-spalling",
                "title": "Industrial Fired Brick Pier",
                "description": "Exposed solid brick pier constructed of underburned, porous Victorian common bricks suffering severe cryo-hydraulic frost spalling and face shell detachment.",
                "country": "United Kingdom",
                "region": "Birmingham",
                "wall_type": "brick_cavity",
                "structural_function": "load_bearing",
                "difficulty": "advanced",
                "image_filename": "old_brick_decay_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.22, "y_min": 0.28, "x_max": 0.78, "y_max": 0.78,
                        "category": "spalling", "severity": "critical",
                        "remedial_action": "rebuild_section",
                        "title": "Severe Cryo-Hydraulic Frost Spalling",
                        "explanation": "High open porosity underburned bricks saturated by driving rain experience 9% volumetric water-to-ice expansion, shearing off vitreous face shells."
                    }
                ]
            },
            {
                "slug": "historic-sandstone-contour-scaling",
                "title": "Historic Sandstone: Contour Scaling",
                "description": "Carboniferous quartzose sandstone ashlar masonry exhibiting thick indurated crust detachment and planar contour scaling cutting across natural quarry bedding planes.",
                "country": "United Kingdom",
                "region": "West Yorkshire",
                "wall_type": "ashlar",
                "structural_function": "load_bearing",
                "difficulty": "advanced",
                "image_filename": "ultratech_stone_pores_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.18, "y_min": 0.22, "x_max": 0.82, "y_max": 0.78,
                        "category": "contour_scaling", "severity": "critical",
                        "remedial_action": "indent_stone",
                        "title": "Contour Scaling in Sandstone",
                        "explanation": "Pores blocked with atmospheric sulfates create differential hygrothermal movement stresses between indurated crust and core, shearing a 15-30mm shell away parallel to surface contours."
                    }
                ]
            },
            {
                "slug": "sheltered-limestone-gypsum-cavitation",
                "title": "Sheltered Limestone: Black Gypsum Crust & Cavitation",
                "description": "Oolitic limestone classical facade featuring rain-sheltered overhangs coated in impermeable black gypsum crusts with deep sub-crust cavernous cavitation (alveolar decay).",
                "country": "United Kingdom",
                "region": "London",
                "wall_type": "ashlar",
                "structural_function": "load_bearing",
                "difficulty": "advanced",
                "image_filename": "ashlar_cracking_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.22, "y_min": 0.18, "x_max": 0.80, "y_max": 0.76,
                        "category": "gypsum_crust_cavitation", "severity": "critical",
                        "remedial_action": "poultice_desalt",
                        "title": "Sheltered Gypsum Crust & Cavitation (Alveolar Decay)",
                        "explanation": "Atmospheric SO2 reacts with limestone in unwashed sheltered zones to form impermeable gypsum skins; sub-surface crypto-efflorescence hollows out cavernous honeycombs beneath."
                    }
                ]
            },
            {
                "slug": "rubble-wall-ribbon-pointing-trap",
                "title": "Rubble Wall: Inappropriate Ribbon Pointing",
                "description": "Historic fieldstone rubble masonry subjected to dense 1:3 Portland cement ribbon pointing standing proud of the wall, trapping moisture and accelerating stone crumbling.",
                "country": "United Kingdom",
                "region": "Wales",
                "wall_type": "lime_mortar",
                "structural_function": "boundary",
                "difficulty": "intermediate",
                "image_filename": "stone_rubble_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.16, "y_min": 0.20, "x_max": 0.82, "y_max": 0.80,
                        "category": "ribbon_pointing_failure", "severity": "critical",
                        "remedial_action": "repoint_lime",
                        "title": "Impermeable Ribbon Pointing & Cement Trap Decay",
                        "explanation": "Impermeable Portland cement ribbon joints trap capillary water behind proud mortar fillets, blocking evaporation and diverting moisture into softer stone arrises."
                    }
                ]
            },
            {
                "slug": "historic-masonry-cryptogamic-lichen",
                "title": "Historic Masonry: Biogenic Cryptogamic Colonization",
                "description": "Historic lime-coursed sandstone masonry displaying crustose lichen thalli and thick bryophyte moss cushions secreting chelating acids and harboring destructive pore moisture.",
                "country": "United Kingdom",
                "region": "Devon",
                "wall_type": "lime_mortar",
                "structural_function": "boundary",
                "difficulty": "intermediate",
                "image_filename": "lime_coursed_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.20, "y_min": 0.20, "x_max": 0.80, "y_max": 0.75,
                        "category": "cryptogamic_lichen_attack", "severity": "moderate",
                        "remedial_action": "biocide_steam",
                        "title": "Biogenic Cryptogamic Colonization & Acid Etching",
                        "explanation": "Crustose lichens exude chelating oxalic acids that pit calcareous binders, while moss cushions maintain 100% saturation, triggering winter freeze-thaw shatter."
                    }
                ]
            },
            {
                "slug": "faunal-mason-bee-boring-guano",
                "title": "Faunal Biodeterioration: Mason Bee Boring & Guano",
                "description": "Historic lime boundary wall honeycombed by solitary mason bee nesting tunnels in mortar perpends, accompanied by avian guano acid attack on coping stones.",
                "country": "United Kingdom",
                "region": "Cotswolds",
                "wall_type": "lime_mortar",
                "structural_function": "boundary",
                "difficulty": "intermediate",
                "image_filename": "drystone_02.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.22, "y_min": 0.24, "x_max": 0.78, "y_max": 0.76,
                        "category": "faunal_mason_bee_boring", "severity": "moderate",
                        "remedial_action": "repoint_lime",
                        "title": "Faunal Mason Bee Boring & Avian Guano Dissolution",
                        "explanation": "Solitary mason bees bore 6-10mm nesting galleries into soft lime joints, while bird guano releases uric and phosphoric acids that dissolve carbonate binders."
                    }
                ]
            },
            {
                "slug": "victorian-plinth-impermeable-coating",
                "title": "Victorian Plinth: Impermeable Coating & Sealant Spalling",
                "description": "Victorian dressed sandstone bay plinth treated with silicone water repellent and oil paint, trapping ground damp and generating explosive sub-film spalling.",
                "country": "United Kingdom",
                "region": "Edinburgh",
                "wall_type": "ashlar",
                "structural_function": "load_bearing",
                "difficulty": "advanced",
                "image_filename": "ultratech_stone_frost_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.18, "y_min": 0.20, "x_max": 0.82, "y_max": 0.80,
                        "category": "impermeable_coating_blister", "severity": "critical",
                        "remedial_action": "coating_removal",
                        "title": "Impermeable Synthetic Coating & Sealant Spalling",
                        "explanation": "Vapor-impermeable synthetic sealant traps rising damp and salts; sub-film crypto-efflorescence crystallization pressure shears outer stone skins off in explosive sheets."
                    }
                ]
            },
            {
                "slug": "dublin-georgian-cement-damage",
                "title": "Dublin Georgian Terrace: Inappropriate Cement Pointing",
                "description": "Late Georgian red brick façade in Dublin repaired with dense Portland cement strap pointing standing proud of joints, trapping rainwater and causing accelerated arrises spalling on soft Dublin Red Stock bricks.",
                "country": "Ireland",
                "region": "Dublin 2 (Fitzwilliam Square)",
                "wall_type": "brick_cavity",
                "structural_function": "load_bearing",
                "difficulty": "intermediate",
                "image_filename": "heritage_cement_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.18, "y_min": 0.22, "x_max": 0.82, "y_max": 0.82,
                        "category": "inappropriate_cement_strap", "severity": "critical",
                        "remedial_action": "repoint_lime",
                        "title": "Inappropriate Portland Cement Pointing & Edge Spall",
                        "explanation": "Rigid 1:3 Portland cement ribbon pointing traps capillary water against soft historic clay brick, blocking evaporation and forcing moisture through brick faces, accelerating cryo-hydraulic face shearing."
                    }
                ]
            },
            {
                "slug": "victorian-dublin-chimney-decay",
                "title": "Victorian Dublin Chimney Stack: Flue Acid & Weather Decay",
                "description": "Exposed multi-flue Victorian brick chimney stack suffering severe wind-driven rain saturation, crumbling lime mortar, fractured terracotta flue terminals, and asymmetric stack lean from coal soot sulfate expansion.",
                "country": "Ireland",
                "region": "Dublin 6 (Rathmines)",
                "wall_type": "brick_cavity",
                "structural_function": "load_bearing",
                "difficulty": "advanced",
                "image_filename": "heritage_chimney_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.20, "y_min": 0.15, "x_max": 0.80, "y_max": 0.85,
                        "category": "chimney_decay", "severity": "critical",
                        "remedial_action": "rebuild_section",
                        "title": "Roofline Chimney Stack Decay & Flue Acid Attack",
                        "explanation": "Severe weather exposure combined with flue condensates containing sulfurous acids leaches mortar binders, fractures clay chimney pots, and induces outward stack curvature."
                    }
                ]
            },
            {
                "slug": "period-irish-rising-damp",
                "title": "Period Irish Brick Villa: Capillary Rising Damp & Salt Bloom",
                "description": "Pre-1940s solid Dublin stock brick elevation lacking effective physical damp-proof course (DPC), exhibiting pronounced horizontal capillary tide mark 1m above ground and heavy subflorescence salt burst.",
                "country": "Ireland",
                "region": "Dublin 8 (Portobello)",
                "wall_type": "brick_cavity",
                "structural_function": "load_bearing",
                "difficulty": "intermediate",
                "image_filename": "heritage_damp_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.15, "y_min": 0.25, "x_max": 0.85, "y_max": 0.88,
                        "category": "rising_damp_salt", "severity": "critical",
                        "remedial_action": "poultice_desalt",
                        "title": "Capillary Rising Damp Tide Mark & Subflorescence",
                        "explanation": "Groundwater wicked up through porous handmade bricks carries dissolved nitrates and chlorides; evaporation at 1m height precipitates expansive salt crystals that disintegrate clay faces."
                    }
                ]
            },
            {
                "slug": "georgian-terrace-irish-wigging",
                "title": "Merrion Square Georgian Façade: Irish Wigging Failure",
                "description": "High-status Dublin Georgian brick façade exhibiting historic Irish wigging pointing with red-pigmented stopping mortar and fine white lime putty ribbon; severe coastal weathering has loosened the ribbon fillet.",
                "country": "Ireland",
                "region": "Dublin 2 (Merrion Square)",
                "wall_type": "brick_cavity",
                "structural_function": "load_bearing",
                "difficulty": "advanced",
                "image_filename": "heritage_wigging_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.20, "y_min": 0.20, "x_max": 0.80, "y_max": 0.80,
                        "category": "irish_wigging_failure", "severity": "moderate",
                        "remedial_action": "repoint_lime",
                        "title": "Irish Wigging & Georgian Tuckpointing Ribbon Loss",
                        "explanation": "Loss of adhesion between sacrificial white lime putty ribbon and red brick-dust stopping mortar allows water entry into weathered bed joints, compromising historic aesthetic geometry."
                    }
                ]
            },
            {
                "slug": "dublin-red-stock-pointing-erosion",
                "title": "Crumlin Artisan Dwelling: Dublin Red Stock Lime Washout",
                "description": "Late Victorian artisan dwelling built of local Dublin Red Stock clay bricks, exhibiting deep open mortar beds (15-25mm recession), joint voiding, and missing bedding mortar from continuous driving Atlantic rain.",
                "country": "Ireland",
                "region": "Dublin 12 (Crumlin)",
                "wall_type": "brick_cavity",
                "structural_function": "load_bearing",
                "difficulty": "intermediate",
                "image_filename": "heritage_pointing_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.16, "y_min": 0.18, "x_max": 0.84, "y_max": 0.82,
                        "category": "mortar_erosion", "severity": "moderate",
                        "remedial_action": "repoint_lime",
                        "title": "Severe Bed Joint Mortar Washout & Edge Recession",
                        "explanation": "Decades of driving rain have leached non-hydraulic lime binders from joint mouths, leaving recessed voids that admit water into the wall core and destabilize brick contact."
                    }
                ]
            },
            {
                "slug": "iveagh-trust-gauged-brick-arch",
                "title": "Iveagh Trust Edwardian Brick: Gauged Rubbing Brick Arch Sag",
                "description": "Historic decorative red brick tenement block (1901) featuring precision-gauged soft red rubbing brick flat jack arches over window openings, displaying dropped center keystones and fine lime putty joint shear.",
                "country": "Ireland",
                "region": "Dublin 8 (Bride Street)",
                "wall_type": "brick_cavity",
                "structural_function": "load_bearing",
                "difficulty": "advanced",
                "image_filename": "heritage_iveagh_01.jpg",
                "image_url_direct": None,
                "defects": [
                    {
                        "target_type": "bounding_box",
                        "x_min": 0.22, "y_min": 0.15, "x_max": 0.78, "y_max": 0.85,
                        "category": "gauged_arch_failure", "severity": "critical",
                        "remedial_action": "helical_stitch",
                        "title": "Gauged Rubbing Brick Jack Arch Sag & Dropped Key",
                        "explanation": "Micro-movement in window head lintels coupled with lime putty joint erosion causes tapered rubbing brick voussoirs to slide downward, creating diagonal compressive shear across window reveals."
                    }
                ]
            }
        ]

        for seed in seed_catalog:
            w = Wall.query.filter_by(slug=seed["slug"]).first()
            if not w:
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
            else:
                # Update existing wall if it was using placeholder or missing local image
                if seed.get("image_filename") and (w.image_filename != seed["image_filename"] or "placehold.co" in (w.image_url_direct or "")):
                    w.image_filename = seed["image_filename"]
                    w.image_url_direct = seed.get("image_url_direct")
                    w.title = seed["title"]
                    w.description = seed["description"]
                    db.session.commit()

            for d in seed.get("defects", []):
                existing_d = Defect.query.filter_by(wall_id=w.id, title=d["title"]).first()
                if not existing_d:
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

        # Seed initial 5 authentic Student Skill Assessment specimens
        skill_assessment_seeds = [
            {
                "slug": "skill-drystone-limestone-delamination",
                "title": "Limestone Dry-Stone Wall: Core Voiding & Lichen Encrustation",
                "description": "Rural Irish limestone dry-stone boundary wall exhibiting coping displacement, hearting matrix voiding, and extensive Xanthoria parietina lichen encrustation.",
                "country": "Ireland",
                "region": "Co. Galway (Burren / Connemara border)",
                "wall_type": "dry_stone",
                "structural_function": "boundary",
                "difficulty": "intermediate",
                "image_filename": "skill_specimen_01.jpg",
                "image_url_direct": None,
                "is_skill_assessment": True,
                "defects": [
                    {
                        "target_type": "pin",
                        "x_min": 0.52, "y_min": 0.38, "x_max": 0.52, "y_max": 0.38,
                        "tolerance_radius": 0.08,
                        "category": "hearting_washout", "severity": "moderate",
                        "remedial_action": "rebuild_drystone",
                        "title": "Core Stone Voiding & Cavitation",
                        "explanation": "Missing internal hearting pinning stones create hollow cavity between double wythes, reducing structural frictional interlock."
                    },
                    {
                        "target_type": "pin",
                        "x_min": 0.34, "y_min": 0.62, "x_max": 0.34, "y_max": 0.62,
                        "tolerance_radius": 0.08,
                        "category": "cryptogamic_lichen_attack", "severity": "minor",
                        "remedial_action": "monitor",
                        "title": "Biogenic Crustose Lichen Colonization",
                        "explanation": "Xanthoria parietina orange crustose lichens secreting oxalic acids that chemically pit limestone surface minerals."
                    },
                    {
                        "target_type": "pin",
                        "x_min": 0.66, "y_min": 0.72, "x_max": 0.66, "y_max": 0.72,
                        "tolerance_radius": 0.08,
                        "category": "lateral_bulge", "severity": "critical",
                        "remedial_action": "rebuild_drystone",
                        "title": "Face Wythe Delamination & Slump",
                        "explanation": "Outward movement of lower facing courses due to unarrested lateral soil pressure and lack of through-stones."
                    }
                ]
            },
            {
                "slug": "skill-drystone-field-boundary-slump",
                "title": "Limestone Field Boundary: Bedding Slump & Pinning Loss",
                "description": "Agricultural field wall with uneven stone bedding, loss of small chinking/pinning stones, and localized shear slump.",
                "country": "Ireland",
                "region": "Co. Clare",
                "wall_type": "dry_stone",
                "structural_function": "boundary",
                "difficulty": "beginner",
                "image_filename": "skill_specimen_02.jpg",
                "image_url_direct": None,
                "is_skill_assessment": True,
                "defects": [
                    {
                        "target_type": "pin",
                        "x_min": 0.65, "y_min": 0.38, "x_max": 0.65, "y_max": 0.38,
                        "tolerance_radius": 0.08,
                        "category": "hearting_washout", "severity": "moderate",
                        "remedial_action": "rebuild_drystone",
                        "title": "Loss of Chinking & Wedging Pinners",
                        "explanation": "Dislodged wedging stones permit unconstrained micro-rotation under live livestock loading."
                    },
                    {
                        "target_type": "pin",
                        "x_min": 0.56, "y_min": 0.52, "x_max": 0.56, "y_max": 0.52,
                        "tolerance_radius": 0.08,
                        "category": "coping_displacement", "severity": "moderate",
                        "remedial_action": "rebuild_drystone",
                        "title": "Bed Joint Slump & Unseated Facing Stone",
                        "explanation": "Uneven horizontal bedding angle causing stone arris shear and focal load concentration."
                    },
                    {
                        "target_type": "pin",
                        "x_min": 0.38, "y_min": 0.71, "x_max": 0.38, "y_max": 0.71,
                        "tolerance_radius": 0.08,
                        "category": "cryptogamic_lichen_attack", "severity": "minor",
                        "remedial_action": "monitor",
                        "title": "Crustose Lichen Colonization",
                        "explanation": "Superficial biological colonization across stone bedding arrises."
                    }
                ]
            },
            {
                "slug": "skill-sandstone-strap-pointing-trap",
                "title": "Coursed Sandstone Wall: Cement Strap Pointing Trap",
                "description": "Sandstone coursed rubble masonry suffering from impermeable hard Portland cement ribbon pointing, causing perimeter stone spalling and moisture trapping.",
                "country": "Ireland",
                "region": "Co. Wicklow",
                "wall_type": "lime_mortar",
                "structural_function": "retaining",
                "difficulty": "intermediate",
                "image_filename": "skill_specimen_03.jpg",
                "image_url_direct": None,
                "is_skill_assessment": True,
                "defects": [
                    {
                        "target_type": "pin",
                        "x_min": 0.48, "y_min": 0.46, "x_max": 0.48, "y_max": 0.46,
                        "tolerance_radius": 0.08,
                        "category": "inappropriate_cement_strap", "severity": "critical",
                        "remedial_action": "repoint_lime",
                        "title": "Impermeable Ribbon Pointing & Edge Water Trap",
                        "explanation": "Dense 1:3 Portland cement strap standing proud of stone face, preventing vapor breathability and driving moisture into softer sandstone arrises."
                    },
                    {
                        "target_type": "pin",
                        "x_min": 0.78, "y_min": 0.52, "x_max": 0.78, "y_max": 0.52,
                        "tolerance_radius": 0.08,
                        "category": "mortar_erosion", "severity": "moderate",
                        "remedial_action": "repoint_lime",
                        "title": "Bed Joint Recession & Binder Washout",
                        "explanation": "Lime mortar washout behind broken cement crusts exposing unbacked core matrix."
                    },
                    {
                        "target_type": "pin",
                        "x_min": 0.28, "y_min": 0.54, "x_max": 0.28, "y_max": 0.54,
                        "tolerance_radius": 0.08,
                        "category": "stepped_crack", "severity": "moderate",
                        "remedial_action": "helical_stitch",
                        "title": "Stepped Bed Joint Settlement Fracture",
                        "explanation": "Differential ground settlement creating diagonal stair-step shear along weakened joint planes."
                    }
                ]
            },
            {
                "slug": "skill-sandstone-continuous-vertical-joint",
                "title": "Sandstone Pier: Continuous Vertical Joint Shear",
                "description": "Detail of sandstone rubble coursing showing vertical joint alignment creating an unbonded vertical shear line, paired with arris fretting.",
                "country": "Ireland",
                "region": "Co. Cork",
                "wall_type": "lime_mortar",
                "structural_function": "load_bearing",
                "difficulty": "advanced",
                "image_filename": "skill_specimen_04.jpg",
                "image_url_direct": None,
                "is_skill_assessment": True,
                "defects": [
                    {
                        "target_type": "pin",
                        "x_min": 0.72, "y_min": 0.48, "x_max": 0.72, "y_max": 0.48,
                        "tolerance_radius": 0.08,
                        "category": "expansion_failure", "severity": "critical",
                        "remedial_action": "helical_stitch",
                        "title": "Continuous Vertical Joint Alignment",
                        "explanation": "Failure to stagger vertical joints across courses results in a continuous straight-line shear plane vulnerable to lateral splitting."
                    },
                    {
                        "target_type": "pin",
                        "x_min": 0.42, "y_min": 0.35, "x_max": 0.42, "y_max": 0.35,
                        "tolerance_radius": 0.08,
                        "category": "spalling", "severity": "moderate",
                        "remedial_action": "repoint_lime",
                        "title": "Granular Arris Fretting & Contour Scaling",
                        "explanation": "Frost-thaw crystal expansion along sedimentary bedding planes causing contour delamination."
                    },
                    {
                        "target_type": "pin",
                        "x_min": 0.52, "y_min": 0.72, "x_max": 0.52, "y_max": 0.72,
                        "tolerance_radius": 0.08,
                        "category": "mortar_erosion", "severity": "moderate",
                        "remedial_action": "repoint_lime",
                        "title": "Deep Bed Joint Mortar Washout",
                        "explanation": "Loss of hydraulic lime mortar exceeding 25mm depth requiring joint raking and deep repointing."
                    }
                ]
            },
            {
                "slug": "skill-rubble-boulder-matrix-voiding",
                "title": "Massive Boulder Rubble Wall: Core Cavitation & Joint Loss",
                "description": "Heavy field boulder and irregular rubble wall displaying extensive mortar loss, deep interstitial cavitation, and lack of through-stones.",
                "country": "Ireland",
                "region": "Co. Kerry",
                "wall_type": "rubble",
                "structural_function": "boundary",
                "difficulty": "intermediate",
                "image_filename": "skill_specimen_05.jpg",
                "image_url_direct": None,
                "is_skill_assessment": True,
                "defects": [
                    {
                        "target_type": "pin",
                        "x_min": 0.54, "y_min": 0.48, "x_max": 0.54, "y_max": 0.48,
                        "tolerance_radius": 0.08,
                        "category": "rubble_voiding", "severity": "critical",
                        "remedial_action": "grout_injection",
                        "title": "Core Void & Interstitial Matrix Cavitation",
                        "explanation": "Severe loss of bedding binder between irregular rounded glacial boulders leaving unstable bridging voids."
                    },
                    {
                        "target_type": "pin",
                        "x_min": 0.68, "y_min": 0.64, "x_max": 0.68, "y_max": 0.64,
                        "tolerance_radius": 0.08,
                        "category": "mortar_erosion", "severity": "moderate",
                        "remedial_action": "repoint_lime",
                        "title": "Extensive Mortar Joint Washout",
                        "explanation": "Leached mortar mouths allowing rainwater entry into wall core."
                    },
                    {
                        "target_type": "pin",
                        "x_min": 0.24, "y_min": 0.82, "x_max": 0.24, "y_max": 0.82,
                        "tolerance_radius": 0.08,
                        "category": "rising_damp_salt", "severity": "moderate",
                        "remedial_action": "repoint_lime",
                        "title": "Basal Moisture Ingress & Salt Staining",
                        "explanation": "Capillary suction from unsealed ground level leading to mineral crystallization and joint degradation."
                    }
                ]
            }
        ]

        for sseed in skill_assessment_seeds:
            sw = Wall.query.filter_by(slug=sseed["slug"]).first()
            if not sw:
                sw = Wall(
                    slug=sseed["slug"],
                    title=sseed["title"],
                    description=sseed["description"],
                    country=sseed["country"],
                    region=sseed["region"],
                    wall_type=sseed["wall_type"],
                    structural_function=sseed["structural_function"],
                    difficulty=sseed["difficulty"],
                    image_filename=sseed["image_filename"],
                    image_url_direct=sseed["image_url_direct"],
                    is_published=True,
                    is_skill_assessment=True
                )
                db.session.add(sw)
                db.session.commit()
            else:
                sw.is_skill_assessment = True
                sw.image_filename = sseed["image_filename"]
                db.session.commit()

            for sd in sseed.get("defects", []):
                existing_sd = Defect.query.filter_by(wall_id=sw.id, title=sd["title"]).first()
                if not existing_sd:
                    sgt = Defect(
                        wall_id=sw.id,
                        target_type=sd["target_type"],
                        x_min=sd["x_min"],
                        y_min=sd["y_min"],
                        x_max=sd["x_max"],
                        y_max=sd["y_max"],
                        tolerance_radius=sd.get("tolerance_radius", 0.08),
                        category=sd["category"],
                        severity=sd["severity"],
                        remedial_action=sd.get("remedial_action", "repoint_lime"),
                        title=sd["title"],
                        explanation=sd["explanation"]
                    )
                    db.session.add(sgt)
                else:
                    existing_sd.tolerance_radius = sd.get("tolerance_radius", 0.08)
            db.session.commit()

    def commit_with_retry(entity=None, max_retries=2):
        """
        Safely commits session with auto-retry and connection health recovery.
        Guards against cloud host idle TCP disconnects (Render PostgreSQL OperationalError).
        """
        for attempt in range(max_retries):
            try:
                if entity and entity not in db.session:
                    db.session.add(entity)
                db.session.commit()
                return True
            except Exception as err:
                db.session.rollback()
                if attempt < max_retries - 1:
                    import time
                    time.sleep(0.3)
                    continue
                raise err


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
                ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
                filename = f"{slug}{ext}"
                file_bytes = file.read()

                local_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                with open(local_path, "wb") as f_out:
                    f_out.write(file_bytes)
                wall.image_filename = filename

                db.session.remove()

                c_url = os.getenv("CLOUDINARY_URL", "").strip()
                if c_url:
                    try:
                        import io
                        upload_result = cloudinary.uploader.upload(
                            io.BytesIO(file_bytes),
                            folder="wall_inspector",
                            public_id=slug,
                            overwrite=True,
                            resource_type="image",
                            access_mode="public"
                        )
                        wall.image_url_direct = upload_result.get("secure_url")
                    except Exception as cloud_err:
                        print(f"Cloudinary upload error in edit (using local file): {cloud_err}")
                        wall.image_url_direct = None
                else:
                    wall.image_url_direct = None

            commit_with_retry(wall)
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
            ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
            filename = f"{slug}{ext}"
            file_bytes = file.read()

            # Always save local fallback copy on disk so image_filename is guaranteed valid
            local_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            with open(local_path, "wb") as f_out:
                f_out.write(file_bytes)

            # Prevent stale connection: detach any open DB session during external cloud upload
            db.session.remove()

            image_url_direct = None
            c_url = os.getenv("CLOUDINARY_URL", "").strip()
            if c_url:
                try:
                    import io
                    upload_result = cloudinary.uploader.upload(
                        io.BytesIO(file_bytes),
                        folder="wall_inspector",
                        public_id=slug,
                        overwrite=True,
                        resource_type="image",
                        access_mode="public"
                    )
                    image_url_direct = upload_result.get("secure_url")
                except Exception as cloud_err:
                    print(f"Cloudinary upload notice in admin create (using local file): {cloud_err}")

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
            commit_with_retry(wall)
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

        BOQ_RATES = {
            "repoint_lime": {"desc": "Rake out decayed joints to 25mm depth and repoint with St. Astier NHL 2 / 3.5 lime mortar", "spec": "EN 459-1 / BS 8221", "qty": "8.5 m²", "rate": 85.00, "total": 722.50},
            "helical_stitch": {"desc": "Install austenitic 316-grade helical stainless steel crack stitches (6mm x 1000mm)", "spec": "BRE Digest 329", "qty": "4 lin.m", "rate": 145.00, "total": 580.00},
            "grout_injection": {"desc": "Low-pressure void consolidation grouting with breathable hydraulic lime grout", "spec": "Historic England Guidance", "qty": "3.0 m²", "rate": 220.00, "total": 660.00},
            "rebuild_section": {"desc": "Careful numbered dismantling and rebuilding of unstable wall section plumb", "spec": "Eurocode 6 / BS EN 1996", "qty": "2.5 m²", "rate": 450.00, "total": 1125.00},
            "drainage_relief": {"desc": "Diamond core drill 65mm weep holes with geotextile filters and drainage relief pipe", "spec": "CIRIA C580", "qty": "4 No.", "rate": 120.00, "total": 480.00},
            "biocide_root": {"desc": "Application of enzymatic biocide and surgical extraction of invasive root systems", "spec": "Historic England Biological Decay", "qty": "5.0 m²", "rate": 65.00, "total": 325.00},
            "underpin_base": {"desc": "Sequential mass concrete underpin pins beneath distressed foundation footing", "spec": "ICE Manual of Geotechnical Engineering", "qty": "2.0 lin.m", "rate": 780.00, "total": 1560.00},
            "monitor_gauge": {"desc": "Install Avongard calibrated precision tell-tale crack motion gauges with log sheets", "spec": "BRE Defect Action Sheet 9", "qty": "2 Pairs", "rate": 90.00, "total": 180.00}
        }

        boq_items = []
        boq_subtotal = 0.0
        for d in defect_items:
            rem_id = d.get("remedial_action", "repoint_lime")
            cost_info = BOQ_RATES.get(rem_id, {
                "desc": f"Remedial conservation work: {d.get('remedial_label')}",
                "spec": "BS 8221",
                "qty": "1 Item",
                "rate": 250.00,
                "total": 250.00
            })
            boq_items.append({
                "description": cost_info["desc"],
                "specification": cost_info["spec"],
                "quantity": cost_info["qty"],
                "rate": cost_info["rate"],
                "total": cost_info["total"]
            })
            boq_subtotal += cost_info["total"]

        if not boq_items:
            boq_items.append({
                "description": "Cyclical hydraulic lime pointing maintenance and surface inspection",
                "specification": "BS 8221-1",
                "quantity": "5.0 m²",
                "rate": 75.00,
                "total": 375.00
            })
            boq_subtotal = 375.00

        boq_prelims = 650.00
        boq_contingency = round((boq_subtotal + boq_prelims) * 0.15, 2)
        boq_grand_total = round(boq_subtotal + boq_prelims + boq_contingency, 2)

        if has_critical or (attempt.score_percentage is not None and attempt.score_percentage < 70):
            rics_rating = 3
            rics_headline = "Condition Rating 3: Urgent Structural Remediation Required"
            rics_description = "Active structural defects or severe joint failure posing progressive stability risks. Immediate conservation intervention scheduled."
        elif has_moderate:
            rics_rating = 2
            rics_headline = "Condition Rating 2: Moderate Remedial Repairs Required"
            rics_description = "Localized masonry distress and weather erosion observed. Interventions scheduled within a 3 to 6-month conservation window."
        else:
            rics_rating = 1
            rics_headline = "Condition Rating 1: Routine Cyclical Maintenance Standard"
            rics_description = "Minor superficial weathering. Managed via standard cyclical lime pointing and non-destructive crack gauge monitoring."

        return render_template(
            "survey_report.html",
            attempt=attempt,
            wall=wall.to_dict(),
            defect_items=defect_items,
            boq_items=boq_items,
            boq_subtotal=boq_subtotal,
            boq_prelims=boq_prelims,
            boq_contingency=boq_contingency,
            boq_grand_total=boq_grand_total,
            rics_rating=rics_rating,
            rics_headline=rics_headline,
            rics_description=rics_description,
            report_ref=attempt.id[:8].upper(),
            survey_date=attempt.created_at.strftime("%Y-%m-%d") if attempt.created_at else datetime.now().strftime("%Y-%m-%d"),
            surveyor_name=attempt.student_name or "Candidate Surveyor"
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
    def generate_flashcards_deck(archetype_filter="all"):
        REMEDIAL_COSTS_EURO = {
            "repoint_lime": "€45 - €75 / linear meter",
            "helical_stitch": "€85 - €160 / linear meter",
            "grout_injection": "€120 - €240 / cubic meter void",
            "rebuild_section": "€280 - €550 / square meter",
            "drainage_relief": "€65 - €110 / weep station",
            "biocide_root": "€25 - €45 / square meter",
            "underpin_base": "€750 - €1,400 / linear meter",
            "monitor_gauge": "€35 - €60 / station",
            "indent_stone": "€320 - €620 / square meter",
            "poultice_desalt": "€180 - €380 / linear meter",
            "biocide_steam": "€35 - €65 / square meter",
            "coating_removal": "€95 - €210 / square meter",
            "wigging_restore": "€180 - €350 / square meter",
            "chimney_rebuild": "€450 - €1,200 / stack rebuild"
        }

        REMEDIAL_LABELS = {
            "repoint_lime": "Hydraulic Lime Repointing (NHL 2 / 3.5)",
            "helical_stitch": "Helical Stainless Steel Stitching (6mm ties)",
            "grout_injection": "Internal Core Void Grout Injection",
            "rebuild_section": "Localized Stone Dismantling & Rebuild Plumb",
            "drainage_relief": "Weep Hole Core-Drilling & Hydrostatic Relief",
            "biocide_root": "Controlled Biocide & Woody Root Extraction",
            "underpin_base": "Differential Foundation Underpinning",
            "monitor_gauge": "Calibrated Tell-Tale Crack Gauge Monitoring",
            "indent_stone": "Surgical Stone Indenting & Re-facing",
            "poultice_desalt": "Nebulous Mist Cleaning & Lime Poultice Desalting",
            "biocide_steam": "Superheated Dry Steam (150°C) & Biocide Wash",
            "coating_removal": "Latex Poultice Paint Stripping & Desalination",
            "wigging_restore": "Traditional Irish Wigging / Tuckpointing Restoration",
            "chimney_rebuild": "Chimney Stack Deconstruction & Flaunching Rebuild"
        }

        ARCHETYPE_LABELS = {
            "brick_cavity": "Brick Cavity",
            "dry_stone": "Dry Stone",
            "lime_mortar": "Historic Lime",
            "stone_rubble": "Stone Rubble",
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
            },
            "continuous_vertical_joint": {
                "severity": "critical", "action": "helical_stitch",
                "explanation": "Vertical joints aligned without proper overlap across consecutive courses, creating a continuous vertical shear plane prone to vertical splitting under compression.",
                "mechanics": "Bond failure along collinear vertical perpends under compressive shear (IS 1597 Part 1 / EN 1996-1-1)."
            },
            "face_bedding_delamination": {
                "severity": "critical", "action": "rebuild_section",
                "explanation": "Sedimentary stone installed with quarry bedding planes parallel to the wall face (face-bedded) rather than normal to compressive thrust. Compressive load causes shear splitting and exfoliation along laminar cleavage planes.",
                "mechanics": "Parallel load acting along anisotropic sedimentation laminae inducing buckling and spalling (IS 1124 / BS 8298)."
            },
            "lime_runoff_staining": {
                "severity": "critical", "action": "repoint_lime",
                "explanation": "Excess water migrating through high-calcium mortar beds dissolves free calcium hydroxide Ca(OH)2, leaching down the facade and carbonating into disfiguring, impermeable calcite (CaCO3) crusts.",
                "mechanics": "Chemical leaching of portlandite Ca(OH)2 + atmospheric carbonation to insoluble CaCO3 crusts."
            },
            "cryptoflorescence": {
                "severity": "moderate", "action": "repoint_lime",
                "explanation": "Soluble salts evaporating within the sub-surface pore network generate crystallization pressures exceeding stone tensile strength (50-100 MPa), disintegrating the stone face into crumbly powder.",
                "mechanics": "Sub-surface crystal expansion pressure exceeding stone tensile capacity (EN 12370)."
            },
            "frost_attack_spall": {
                "severity": "critical", "action": "rebuild_section",
                "explanation": "Critical moisture saturation (>91% pore capacity) combined with sub-zero temperatures generates expansive ice crystallization pressures, wedging joints apart and shattering outer stone arrises.",
                "mechanics": "9% volumetric water-to-ice phase expansion causing hydraulic fracturing in closed pore networks (IS 1121 / EN 12371)."
            },
            "contour_scaling": {
                "severity": "critical", "action": "indent_stone",
                "explanation": "Thick shell-like crust (15-30mm) spalling parallel to outer sandstone surface contours, irrespective of quarry bedding orientation.",
                "mechanics": "Pore blockage by calcium sulfate creates differential hygrothermal movement stresses between indurated crust and substrate sandstone."
            },
            "gypsum_crust_cavitation": {
                "severity": "critical", "action": "poultice_desalt",
                "explanation": "Impermeable black gypsum crust (CaSO4·2H2O) forming in rain-sheltered overhangs; sub-crust magnesium sulfate crystallization hollows out cavernous internal voids (alveolar decay).",
                "mechanics": "Atmospheric SO2 acid attack on CaCO3 in sheltered zones + sub-crust crypto-efflorescence cavitation."
            },
            "ribbon_pointing_failure": {
                "severity": "critical", "action": "repoint_lime",
                "explanation": "Dense 1:3 Portland cement ribbon pointing standing proud of stone face. Shrinkage cracks draw water in while impermeable mortar prevents joint evaporation, forcing all moisture into soft stone.",
                "mechanics": "Moisture diversion into soft stone arrises + capillary water entrapment behind rigid cement fillets."
            },
            "cryptogamic_lichen_attack": {
                "severity": "moderate", "action": "biocide_steam",
                "explanation": "Crustose lichens secrete chelating oxalic acids that chemically pit limestone, while thick moss cushions act as water sponges maintaining pore saturation and inducing freeze shatter.",
                "mechanics": "Oxalic biochemical etching + moisture retention inducing severe localized freeze-thaw bursting."
            },
            "faunal_mason_bee_boring": {
                "severity": "moderate", "action": "repoint_lime",
                "explanation": "Solitary mason bees (Osmia bicornis) bore 6-10mm cylindrical nesting tunnels into soft lime mortar joints; avian guano deposits acidic uric acid that dissolves calcite matrix.",
                "mechanics": "Mechanical honeycombing of mortar joint core + biochemical uric acid dissolution."
            },
            "impermeable_coating_blister": {
                "severity": "critical", "action": "coating_removal",
                "explanation": "Synthetic silicone sealers or bitumen paints trap rising damp and soluble salts beneath an impervious skin; sub-film crystallization pressure triggers catastrophic sheet spalling.",
                "mechanics": "Loss of masonry breathability + explosive sub-film salt crystallization pressure."
            },
            "inappropriate_cement_strap": {
                "severity": "critical", "action": "repoint_lime",
                "explanation": "Rigid 1:3 Portland cement ribbon or patch pointing applied over soft historic handmade brick. Traps capillary moisture and accelerates brick arrises spalling while cement breaks away in chunks.",
                "mechanics": "Modulus of elasticity mismatch + capillary water entrapment forcing moisture evaporation through soft clay brick arrises."
            },
            "chimney_decay": {
                "severity": "critical", "action": "chimney_rebuild",
                "explanation": "Exposed roofline chimney stacks suffering severe freeze-thaw weathering, crumbling lime joints, fractured terracotta flue pots, and asymmetric stack lean from coal soot sulfate expansion.",
                "mechanics": "Cryo-hydraulic saturation + ammonium sulfate chemical expansion from coal smoke flue deposits causing stack curvature."
            },
            "rising_damp_salt": {
                "severity": "critical", "action": "poultice_desalt",
                "explanation": "Groundwater capillary rise in solid historic brickwork lacking functional DPC, creating visible horizontal tide marks and expansive subflorescence salt crystals powdering the brick face.",
                "mechanics": "Continuous capillary wicking of soluble nitrates/chlorides + sub-surface crypto-efflorescence crystallization pressure."
            },
            "irish_wigging_failure": {
                "severity": "moderate", "action": "wigging_restore",
                "explanation": "Uniquely Irish Georgian pointing technique featuring red-pigmented brick-dust stopping mortar and an applied white lime putty ribbon; weathering or cement repairs cause ribbon detachment.",
                "mechanics": "Thermal and moisture shear failure along stopping mortar interface + loss of sacrificial decorative lime ribbon."
            },
            "gauged_arch_failure": {
                "severity": "critical", "action": "helical_stitch",
                "explanation": "Precision rubbing brick flat jack arches over window openings exhibiting dropped center keystones, slipped voussoirs, and joint crushing from lintel deflection.",
                "mechanics": "Loss of frictional wedge equilibrium along fine lime putty joints under superincumbent point loads."
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
            wall_img = wall_dict.get("image_url", "/static/img/walls/brick_efflorescence_01.jpg")

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
                        img_url = w_gt.to_dict().get("image_url", wall_img)

                img_url = img_url or "/static/img/walls/brick_efflorescence_01.jpg"
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

        return deck

    @app.route("/cards")
    def flashcards():
        archetype_filter = request.args.get("archetype", "all").strip()
        wall_types = list(TAXONOMY_BY_WALL_TYPE.keys())
        all_cards = generate_flashcards_deck("all")
        if archetype_filter != "all" and archetype_filter in TAXONOMY_BY_WALL_TYPE:
            initial_deck = [c for c in all_cards if c["archetype"] == archetype_filter]
        else:
            initial_deck = all_cards
            archetype_filter = "all"
        return render_template(
            "flashcards.html",
            wall_types=wall_types,
            all_cards=all_cards,
            initial_deck=initial_deck,
            selected_archetype=archetype_filter
        )

    @app.route("/api/cards/deck")
    def api_cards_deck():
        archetype_filter = request.args.get("archetype", "all").strip()
        deck = generate_flashcards_deck(archetype_filter)
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

    @app.route("/examples")
    @app.route("/worked-examples")
    def worked_examples_view():
        return render_template("worked_examples_catalog.html")

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
            },
            "ultratech-stone-continuous-joints": {
                "lat": 26.9124, "lng": 75.7873,
                "geology": "Vindhyan Supergroup Sandstone & Lime Rubble",
                "rainfall": "Monsoonal (650 mm/yr)",
                "freeze_thaw": "0 cycles / yr (Intense Thermal Shock)",
                "salt_spray": "Inland Arid Calcite/Sulfate Dust"
            },
            "ultratech-stone-improper-bedding": {
                "lat": 23.2599, "lng": 77.4126,
                "geology": "Bhander Stratified Sedimentary Sandstone",
                "rainfall": "High Monsoonal (1,100 mm/yr)",
                "freeze_thaw": "0 cycles / yr (Extreme Diurnal Expansion)",
                "salt_spray": "Sub-tropical Continental"
            },
            "ultratech-stone-lime-runoff": {
                "lat": 12.9716, "lng": 77.5946,
                "geology": "Peninsular Gneiss & Fieldstone Rubble",
                "rainfall": "Tropical High (970 mm/yr)",
                "freeze_thaw": "0 cycles / yr (High Leaching Factor)",
                "salt_spray": "Plateau Rainwash Calcite Leaching"
            },
            "ultratech-stone-frost-attack": {
                "lat": 31.1048, "lng": 77.1734,
                "geology": "Himalayan Quartzite & Porous Metamorphic Sandstone",
                "rainfall": "Severe Montane (1,500 mm/yr)",
                "freeze_thaw": "78 cycles / yr (Extreme Alpine)",
                "salt_spray": "Periglacial Freeze Wedging"
            },
            "ultratech-stone-through-stone-defect": {
                "lat": 19.0760, "lng": 72.8777,
                "geology": "Deccan Trap Igneous Basalt Rubble",
                "rainfall": "Severe Monsoonal (2,200 mm/yr)",
                "freeze_thaw": "0 cycles / yr (Surcharge Pore Pressure)",
                "salt_spray": "Arabian Sea Saline Humidity"
            },
            "ultratech-stone-macroporous-decay": {
                "lat": 17.3850, "lng": 78.4867,
                "geology": "Macroporous Volcanic Ashlar & Granitoid",
                "rainfall": "Moderate-High (820 mm/yr)",
                "freeze_thaw": "0 cycles / yr (Rapid Capillary Evaporation)",
                "salt_spray": "Semi-arid Interior Cryptoflorescence"
            },
            "modern-brick-settlement-shear": {
                "lat": 51.5074, "lng": -0.1278,
                "geology": "London Clay Shrinkable Formation & Fired Clay Brickwork",
                "rainfall": "Moderate (650 mm/yr)",
                "freeze_thaw": "32 cycles / yr",
                "salt_spray": "Urban Low-Saline Acid Rain"
            },
            "commercial-brick-thermal-expansion": {
                "lat": 53.8008, "lng": -1.5491,
                "geology": "Pennine Coal Measures Mudstone & Wirecut Brick",
                "rainfall": "Moderate-High (780 mm/yr)",
                "freeze_thaw": "42 cycles / yr",
                "salt_spray": "Inland Industrial Rain"
            },
            "industrial-fired-brick-spalling": {
                "lat": 52.4862, "lng": -1.8904,
                "geology": "Mercia Mudstone & Low-Fired Victorian Common Brick",
                "rainfall": "Moderate (730 mm/yr)",
                "freeze_thaw": "48 cycles / yr",
                "salt_spray": "Industrial Urban Cryo-Hydraulic"
            },
            "historic-sandstone-contour-scaling": {
                "lat": 53.7997, "lng": -1.7564,
                "geology": "Millstone Grit Carboniferous Quartzose Sandstone",
                "rainfall": "High (920 mm/yr)",
                "freeze_thaw": "50 cycles / yr",
                "salt_spray": "Pennine Industrial Sulfate Deposition"
            },
            "sheltered-limestone-gypsum-cavitation": {
                "lat": 51.5033, "lng": -0.1195,
                "geology": "Portland / Bath Jurassic Oolitic Limestone",
                "rainfall": "Moderate (640 mm/yr sheltered)",
                "freeze_thaw": "30 cycles / yr",
                "salt_spray": "Urban SO2 Gypsum Crust Encrustation"
            },
            "rubble-wall-ribbon-pointing-trap": {
                "lat": 51.4816, "lng": -3.1791,
                "geology": "Old Red Sandstone Rubble & Hard OPC Ribbon Mortar",
                "rainfall": "Severe (1,150 mm/yr)",
                "freeze_thaw": "38 cycles / yr",
                "salt_spray": "Severn Estuary Marine Mist"
            },
            "historic-masonry-cryptogamic-lichen": {
                "lat": 50.7184, "lng": -3.5339,
                "geology": "Permian Breccia / Sandstone & Calcareous Lime Matrix",
                "rainfall": "High (940 mm/yr)",
                "freeze_thaw": "26 cycles / yr",
                "salt_spray": "South-West Oceanic Moisture & Cryptogamic Sponge"
            },
            "faunal-mason-bee-boring-guano": {
                "lat": 51.7169, "lng": -1.7588,
                "geology": "Cotswold Oolitic Freestone & Non-Hydraulic Lime Mortar",
                "rainfall": "Moderate (760 mm/yr)",
                "freeze_thaw": "36 cycles / yr",
                "salt_spray": "Rural Organic Faunal Uric Acid Pitting"
            },
            "victorian-plinth-impermeable-coating": {
                "lat": 55.9533, "lng": -3.1883,
                "geology": "Craigleith Lower Carboniferous Sandstone with Synthetic Polymer Seal",
                "rainfall": "Severe Maritime (810 mm/yr)",
                "freeze_thaw": "54 cycles / yr",
                "salt_spray": "Firth of Forth Salt Wind & Sub-Film Cryo-Burst"
            },
            "dublin-georgian-cement-damage": {
                "lat": 53.3377, "lng": -6.2514,
                "geology": "Lower Carboniferous Calp Formation & Soft Dublin Red Stock Brick",
                "rainfall": "Moderate Atlantic (750 mm/yr)",
                "freeze_thaw": "34 cycles / yr",
                "salt_spray": "Urban Low-Saline Air & Acidic Sulfate"
            },
            "victorian-dublin-chimney-decay": {
                "lat": 53.3228, "lng": -6.2642,
                "geology": "Glacial Till Subsoil over Calp Limestone; Exposed Roofline Ridge",
                "rainfall": "Severe Driving Rain (820 mm/yr at roofline)",
                "freeze_thaw": "48 cycles / yr (Elevated Exposure)",
                "salt_spray": "Flue Soot Ammonium Sulfate Acid Condensation"
            },
            "period-irish-rising-damp": {
                "lat": 53.3312, "lng": -6.2678,
                "geology": "Grand Canal Alluvium & Soft Victorian Porous Mudstone Brick",
                "rainfall": "High Capillary Saturation (790 mm/yr)",
                "freeze_thaw": "28 cycles / yr",
                "salt_spray": "Ground Nitrate & Chloride Crystallization"
            },
            "georgian-terrace-irish-wigging": {
                "lat": 53.3398, "lng": -6.2494,
                "geology": "Merrion Alluvial Gravels & Hand-moulded Georgian Red Stock",
                "rainfall": "Moderate Maritime (735 mm/yr)",
                "freeze_thaw": "32 cycles / yr",
                "salt_spray": "Dublin Bay Coastal Damp Aerosol"
            },
            "dublin-red-stock-pointing-erosion": {
                "lat": 53.3245, "lng": -6.3110,
                "geology": "Crumlin Brickfield Yellow/Red Clay Bedrock & Dublin Stock Brick",
                "rainfall": "Severe Wind-Scour (860 mm/yr)",
                "freeze_thaw": "38 cycles / yr",
                "salt_spray": "Urban Atmospheric Runoff Matrix Leaching"
            },
            "iveagh-trust-gauged-brick-arch": {
                "lat": 53.3402, "lng": -6.2709,
                "geology": "Poddle River Alluvium & High-Grade Pressed/Gauged Rubbing Brick",
                "rainfall": "Moderate-High (760 mm/yr)",
                "freeze_thaw": "34 cycles / yr",
                "salt_spray": "Urban Microclimate & Soot Deposition"
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
            ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
            filename = f"{slug}{ext}"
            file_bytes = file.read()

            # Always save local fallback copy on disk so image_filename is guaranteed valid
            local_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            with open(local_path, "wb") as f_out:
                f_out.write(file_bytes)

            # Prevent stale connection: detach any open DB session during external cloud upload
            db.session.remove()

            image_url_direct = None
            c_url = os.getenv("CLOUDINARY_URL", "").strip()
            if c_url:
                try:
                    import io
                    upload_result = cloudinary.uploader.upload(
                        io.BytesIO(file_bytes),
                        folder="wall_inspector",
                        public_id=slug,
                        overwrite=True,
                        resource_type="image",
                        access_mode="public"
                    )
                    image_url_direct = upload_result.get("secure_url")
                except Exception as cloud_err:
                    print(f"Cloudinary mobile upload notice (using local file): {cloud_err}")

            is_skill_assessment = bool(request.form.get("is_skill_assessment") in ["1", "true", "True", True, "on"])
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
                is_published=True,
                is_skill_assessment=is_skill_assessment
            )
            commit_with_retry(wall)
            return jsonify({"success": True, "wall": wall.to_dict()})
        except Exception as e:
            db.session.rollback()
            print(f"Error in mobile_admin_upload: {e}")
            return jsonify({"success": False, "error": f"Database save error ({type(e).__name__}): please tap Retry"}), 500

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
            ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
            filename = f"{sub_slug}{ext}"
            file_bytes = file.read()

            # Always save local fallback copy on disk so image_filename is guaranteed valid
            local_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            with open(local_path, "wb") as f_out:
                f_out.write(file_bytes)

            # Prevent stale connection: detach any open DB session during external cloud upload
            db.session.remove()

            image_url_direct = None
            c_url = os.getenv("CLOUDINARY_URL", "").strip()
            if c_url:
                try:
                    import io
                    upload_result = cloudinary.uploader.upload(
                        io.BytesIO(file_bytes),
                        folder=f"wall_inspector/students/{student_identifier}",
                        public_id=sub_slug,
                        overwrite=True,
                        resource_type="image",
                        access_mode="public"
                    )
                    image_url_direct = upload_result.get("secure_url")
                except Exception as cloud_err:
                    print(f"Cloudinary student upload notice (using local file): {cloud_err}")

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
            commit_with_retry(submission)
            return jsonify({"success": True, "submission": submission.to_dict()})
        except Exception as e:
            db.session.rollback()
            print(f"Error in mobile_student_upload: {e}")
            return jsonify({"success": False, "error": f"Database save error ({type(e).__name__}): please tap Retry"}), 500

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
                                resource_type="auto",
                                access_mode="public"
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

            commit_with_retry(submission)
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

    # =========================================================================
    # TIMED STUDENT EXAMINATION & SPATIAL GRADING ENGINE
    # =========================================================================
    EXAM_SESSIONS = {}

    @app.route("/exam")
    def exam_console():
        return render_template(
            "exam.html",
            taxonomies=TAXONOMY_BY_WALL_TYPE,
            remedial_options=REMEDIAL_OPTIONS
        )

    @app.route("/api/exam/start", methods=["POST"])
    def api_exam_start():
        data = request.get_json() or {}
        student_name = data.get("student_name", "Candidate").strip() or "Candidate"
        mode = data.get("mode", "exam").strip()
        cohort_code = data.get("cohort_code", "GENERAL").strip().upper() or "GENERAL"

        assignment = Assignment.query.filter_by(code=cohort_code, is_active=True).first()
        all_walls = Wall.query.filter_by(is_published=True).all()

        if not all_walls:
            return jsonify({"success": False, "error": "No published specimen walls available."}), 404

        if assignment and assignment.walls:
            selected_walls = list(assignment.walls)
            time_limit = (assignment.time_limit_minutes or 5) * 60
        elif mode == "quiz":
            selected_walls = random.sample(all_walls, min(3, len(all_walls)))
            time_limit = 180
        elif mode == "master":
            selected_walls = random.sample(all_walls, min(10, len(all_walls)))
            time_limit = 600
        else:
            selected_walls = random.sample(all_walls, min(5, len(all_walls)))
            time_limit = 300

        exam_token = str(uuid.uuid4())
        EXAM_SESSIONS[exam_token] = {
            "exam_token": exam_token,
            "student_name": student_name,
            "cohort_code": cohort_code,
            "mode": mode,
            "start_time": datetime.now(timezone.utc),
            "time_limit_seconds": time_limit,
            "wall_ids": [w.id for w in selected_walls],
            "submissions": {}
        }

        # Candidate walls payload (ground truth defects omitted to prevent cheating)
        walls_payload = []
        for w in selected_walls:
            w_dict = w.to_dict()
            walls_payload.append({
                "id": w.id,
                "slug": w.slug,
                "title": w.title,
                "wall_type": w.wall_type,
                "structural_function": w.structural_function,
                "image_url": w_dict["image_url"]
            })

        return jsonify({
            "success": True,
            "exam_token": exam_token,
            "time_limit_seconds": time_limit,
            "walls": walls_payload
        })

    @app.route("/api/exam/submit-wall", methods=["POST"])
    def api_exam_submit_wall():
        data = request.get_json() or {}
        exam_token = data.get("exam_token")
        wall_id = data.get("wall_id")
        markers = data.get("markers", [])

        if not exam_token or exam_token not in EXAM_SESSIONS:
            return jsonify({"success": False, "error": "Invalid or expired exam session"}), 400

        EXAM_SESSIONS[exam_token]["submissions"][wall_id] = markers
        return jsonify({"success": True, "wall_id": wall_id})

    @app.route("/api/exam/finish", methods=["POST"])
    def api_exam_finish():
        data = request.get_json() or {}
        exam_token = data.get("exam_token")
        student_name = data.get("student_name", "Candidate").strip() or "Candidate"

        if not exam_token or exam_token not in EXAM_SESSIONS:
            return jsonify({"success": False, "error": "Exam session expired or not found"}), 400

        session_data = EXAM_SESSIONS[exam_token]
        student_name = session_data.get("student_name") or student_name
        cohort_code = session_data.get("cohort_code") or "GENERAL"
        wall_ids = session_data.get("wall_ids", [])
        submissions = session_data.get("submissions", {})

        total_tp = 0
        total_fp = 0
        total_fn = 0
        specimen_breakdowns = []
        specimen_scores = []

        for w_id in wall_ids:
            wall = db.session.get(Wall, w_id)
            if not wall:
                continue
            ground_truth = Defect.query.filter_by(wall_id=w_id).all()
            candidate_markers = submissions.get(w_id, [])

            matched_gt = set()
            matched_cand = set()
            wall_tp = 0
            wall_fp = 0

            for cand_idx, cand in enumerate(candidate_markers):
                best_iou = 0.0
                best_gt_idx = -1

                for gt_idx, gt in enumerate(ground_truth):
                    if gt_idx in matched_gt:
                        continue
                    iou = calculate_iou(cand, {
                        "x_min": gt.x_min, "y_min": gt.y_min,
                        "x_max": gt.x_max, "y_max": gt.y_max
                    })
                    dist = calculate_center_distance(cand, {
                        "x_min": gt.x_min, "y_min": gt.y_min,
                        "x_max": gt.x_max, "y_max": gt.y_max
                    })

                    if (iou >= 0.20 or dist <= 0.15) and iou >= best_iou:
                        best_iou = iou
                        best_gt_idx = gt_idx

                if best_gt_idx >= 0:
                    matched_gt.add(best_gt_idx)
                    matched_cand.add(cand_idx)
                    wall_tp += 1
                else:
                    wall_fp += 1

            wall_fn = len(ground_truth) - len(matched_gt)

            defects_details = []
            for gt_idx, gt in enumerate(ground_truth):
                is_hit = gt_idx in matched_gt
                cat_correct = False
                matched_iou = 0.0
                if is_hit:
                    for c_idx in matched_cand:
                        c_marker = candidate_markers[c_idx]
                        cat_correct = (c_marker.get("category") == gt.category)
                        matched_iou = calculate_iou(c_marker, {
                            "x_min": gt.x_min, "y_min": gt.y_min,
                            "x_max": gt.x_max, "y_max": gt.y_max
                        }) or 0.65
                        break

                defects_details.append({
                    "id": gt.id,
                    "title": gt.title,
                    "category": gt.category,
                    "severity": gt.severity,
                    "remedial_action": gt.remedial_action,
                    "matched": is_hit,
                    "iou": matched_iou,
                    "category_correct": cat_correct
                })

            total_tp += wall_tp
            total_fp += wall_fp
            total_fn += wall_fn

            denom = (wall_tp + wall_fp + wall_fn)
            spec_score = (wall_tp / denom * 100.0) if denom > 0 else (100.0 if not ground_truth else 0.0)
            specimen_scores.append(spec_score)

            specimen_breakdowns.append({
                "wall_id": wall.id,
                "wall_slug": wall.slug,
                "wall_title": wall.title,
                "wall_type": wall.wall_type,
                "image_url": wall.to_dict()["image_url"],
                "region": wall.region,
                "country": wall.country,
                "specimen_score": spec_score,
                "ground_truth": [g.to_dict() for g in ground_truth],
                "submitted_markers": candidate_markers,
                "defects_breakdown": defects_details
            })

        overall_denom = (total_tp + total_fp + total_fn)
        if overall_denom > 0:
            final_percentage = (total_tp / overall_denom) * 100.0
        else:
            final_percentage = 100.0 if sum(specimen_scores) > 0 else 0.0

        if specimen_scores:
            final_percentage = round((final_percentage * 0.5) + ((sum(specimen_scores) / len(specimen_scores)) * 0.5), 1)
        else:
            final_percentage = 0.0

        is_passed = final_percentage >= 70.0

        rep_wall_id = wall_ids[0] if wall_ids else (Wall.query.first().id if Wall.query.first() else None)
        master_attempt = AssessmentAttempt(
            wall_id=rep_wall_id,
            student_session_id=exam_token,
            cohort_code=cohort_code,
            student_name=student_name,
            submitted_markers={"specimens_count": len(wall_ids)},
            true_positives=total_tp,
            false_positives=total_fp,
            false_negatives=total_fn,
            score_percentage=final_percentage,
            passed=is_passed,
            feedback_notes={
                "exam_mode": session_data.get("mode", "exam"),
                "specimens": specimen_breakdowns
            }
        )
        db.session.add(master_attempt)

        cert = None
        if is_passed:
            tier_title = "Master Diagnostic Pathologist" if final_percentage >= 85.0 else "Certified Masonry Inspector"
            cert = Certificate(
                student_name=student_name,
                tier=tier_title,
                average_score=final_percentage,
                total_walls_evaluated=len(wall_ids)
            )
            db.session.add(cert)

        db.session.commit()

        if exam_token in EXAM_SESSIONS:
            del EXAM_SESSIONS[exam_token]

        return jsonify({
            "success": True,
            "attempt_id": master_attempt.id,
            "score_percentage": final_percentage,
            "passed": is_passed,
            "certificate_code": cert.certificate_code if cert else None,
            "redirect_url": f"/exam/result/{master_attempt.id}"
        })

    @app.route("/exam/result/<attempt_id>")
    def view_exam_result(attempt_id):
        attempt = AssessmentAttempt.query.get_or_404(attempt_id)
        cert = Certificate.query.filter_by(student_name=attempt.student_name).order_by(Certificate.issued_at.desc()).first()

        fb = attempt.feedback_notes or {}
        specimens_raw = fb.get("specimens", [])
        specimen_results = []

        for s in specimens_raw:
            specimen_results.append({
                "wall": {
                    "id": s.get("wall_id"),
                    "slug": s.get("wall_slug"),
                    "title": s.get("wall_title"),
                    "wall_type": s.get("wall_type", "dry_stone"),
                    "image_url": s.get("image_url", ""),
                    "region": s.get("region"),
                    "country": s.get("country", "Europe")
                },
                "specimen_score": s.get("specimen_score", 0.0),
                "ground_truth": s.get("ground_truth", []),
                "submitted_markers": s.get("submitted_markers", []),
                "defects_breakdown": s.get("defects_breakdown", [])
            })

        return render_template(
            "exam_result.html",
            attempt=attempt,
            certificate=cert,
            specimen_results=specimen_results
        )

    # =========================================================================
    # INSTRUCTOR COHORT MANAGEMENT & CLASS DIAGNOSTICS
    # =========================================================================
    @app.route("/admin/cohorts")
    def admin_cohorts_view():
        selected_cohort = request.args.get("cohort", "ALL").strip().upper()

        cohort_rows = db.session.query(AssessmentAttempt.cohort_code).distinct().all()
        assignment_rows = db.session.query(Assignment.code).distinct().all()
        all_codes = set()
        for r in cohort_rows:
            if r[0]:
                all_codes.add(r[0].strip().upper())
        for r in assignment_rows:
            if r[0]:
                all_codes.add(r[0].strip().upper())
        cohorts = sorted(list(all_codes)) if all_codes else ["GENERAL"]

        query = AssessmentAttempt.query
        if selected_cohort != "ALL":
            query = query.filter(AssessmentAttempt.cohort_code.ilike(selected_cohort))
        attempts = query.order_by(AssessmentAttempt.created_at.desc()).all()

        total_attempts = len(attempts)
        passed_attempts = [a for a in attempts if a.passed]
        class_pass_rate = (len(passed_attempts) / total_attempts * 100.0) if total_attempts > 0 else 0.0
        class_avg_score = (sum(a.score_percentage for a in attempts) / total_attempts) if total_attempts > 0 else 0.0

        CATEGORY_TIPS = {
            "efflorescence": "Emphasize dry brushing vs wet washing: wet washing drives soluble salts back into core pores.",
            "cryptoflorescence": "Teach sub-surface salt crystal pressure: look for friable stone decay beneath skin.",
            "through_stone_failure": "Highlight wythe bonding: dry stone walls without through-stones bulge laterally under core settle.",
            "lateral_bulge": "Check plumb deviation: outward bulges require dismantling and rebuild with through-stones.",
            "lime_washout": "Specify NHL 2 / 3.5 lime repointing: never point historic lime masonry with Portland cement.",
            "stepped_crack": "Differentiate foundation settlement (stepped along joints) from thermal shrinkage (straight vertical).",
            "hydrostatic_bulge": "Inspect weep holes: retained groundwater generates tremendous hydraulic pressure behind wall.",
            "flint_unseating": "Explain lime matrix weathering: flint gallets and nodules pop out when binder washes out."
        }

        category_miss_counts = {}
        category_tested_counts = {}

        for att in attempts:
            fb = att.feedback_notes or {}
            specs = fb.get("specimens", [])
            for s in specs:
                for d in s.get("defects_breakdown", []):
                    cat = d.get("category", "unspecified")
                    category_tested_counts[cat] = category_tested_counts.get(cat, 0) + 1
                    if not d.get("matched") or not d.get("category_correct"):
                        category_miss_counts[cat] = category_miss_counts.get(cat, 0) + 1

        error_heatmap = []
        for cat, tested in category_tested_counts.items():
            misses = category_miss_counts.get(cat, 0)
            miss_rate = (misses / tested * 100.0) if tested > 0 else 0.0
            error_heatmap.append({
                "category": cat,
                "title": cat.replace("_", " ").title(),
                "miss_count": misses,
                "total_tested": tested,
                "miss_rate": miss_rate,
                "teaching_tip": CATEGORY_TIPS.get(cat, "Review characteristic distress patterns and standard remedial actions.")
            })

        error_heatmap.sort(key=lambda x: x["miss_rate"], reverse=True)
        if not error_heatmap:
            error_heatmap = [
                {"category": "cryptoflorescence", "title": "Cryptoflorescence (Sub-Surface Salt Burst)", "miss_count": 8, "total_tested": 12, "miss_rate": 66.7, "teaching_tip": CATEGORY_TIPS["cryptoflorescence"]},
                {"category": "through_stone_failure", "title": "Missing Through-Stone (Wythe Instability)", "miss_count": 6, "total_tested": 11, "miss_rate": 54.5, "teaching_tip": CATEGORY_TIPS["through_stone_failure"]},
                {"category": "hydrostatic_bulge", "title": "Hydrostatic Retaining Bulge", "miss_count": 5, "total_tested": 10, "miss_rate": 50.0, "teaching_tip": CATEGORY_TIPS["hydrostatic_bulge"]},
                {"category": "stepped_crack", "title": "Stepped Settlement Shear Crack", "miss_count": 4, "total_tested": 12, "miss_rate": 33.3, "teaching_tip": CATEGORY_TIPS["stepped_crack"]},
                {"category": "lime_washout", "title": "Deep Joint Lime Mortar Washout", "miss_count": 3, "total_tested": 14, "miss_rate": 21.4, "teaching_tip": CATEGORY_TIPS["lime_washout"]}
            ]

        return render_template(
            "admin_cohorts.html",
            cohorts=cohorts,
            selected_cohort=selected_cohort,
            attempts=attempts,
            total_attempts=total_attempts,
            class_pass_rate=class_pass_rate,
            class_avg_score=class_avg_score,
            error_heatmap=error_heatmap[:6]
        )

    @app.route("/admin/cohorts/create", methods=["POST"])
    def admin_create_cohort():
        cohort_code = request.form.get("cohort_code", "").strip().upper()
        title = request.form.get("title", "").strip()
        exam_tier = request.form.get("exam_tier", "exam")

        if cohort_code and title:
            assignment = Assignment.query.filter_by(code=cohort_code).first()
            if not assignment:
                time_mins = 10 if exam_tier == "master" else (3 if exam_tier == "quiz" else 5)
                assignment = Assignment(
                    code=cohort_code,
                    title=title,
                    time_limit_minutes=time_mins,
                    mode=exam_tier
                )
                db.session.add(assignment)
                db.session.commit()

        return redirect(url_for("admin_cohorts_view", cohort=cohort_code))

    @app.route("/api/admin/cohorts/<code>/diagnostics")
    def api_cohort_diagnostics(code):
        query = AssessmentAttempt.query
        if code.upper() != "ALL":
            query = query.filter(AssessmentAttempt.cohort_code.ilike(code.strip()))
        attempts = query.all()

        total = len(attempts)
        passed = sum(1 for a in attempts if a.passed)
        avg = (sum(a.score_percentage for a in attempts) / total) if total > 0 else 0.0

        return jsonify({
            "success": True,
            "cohort_code": code.upper(),
            "total_students": total,
            "passed_students": passed,
            "pass_rate": round((passed / total * 100.0) if total > 0 else 0.0, 1),
            "average_score": round(avg, 1)
        })

    @app.route("/api/admin/cohorts/<code>/csv")
    def api_cohort_csv(code):
        import csv
        import io
        from flask import Response

        query = AssessmentAttempt.query
        if code.upper() != "ALL":
            query = query.filter(AssessmentAttempt.cohort_code.ilike(code.strip()))
        attempts = query.order_by(AssessmentAttempt.created_at.desc()).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Candidate Name",
            "Attempt ID",
            "Cohort PIN",
            "Date",
            "Score %",
            "Status",
            "True Positives",
            "False Positives",
            "False Negatives",
            "CPD Hours"
        ])

        for a in attempts:
            writer.writerow([
                a.student_name,
                a.id[:8].upper(),
                a.cohort_code or "GENERAL",
                a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
                f"{a.score_percentage:.1f}",
                "QUALIFIED" if a.passed else "REVISE",
                a.true_positives,
                a.false_positives,
                a.false_negatives,
                "2.0"
            ])

        csv_content = output.getvalue()
        filename = f"gradebook_{code.lower()}_{datetime.now().strftime('%Y%m%d')}.csv"
        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename={filename}"}
        )

    # =========================================================================
    # RICS SURVEY REPORT GENERATOR FOR ANY WALL
    # =========================================================================
    @app.route("/survey/report/<wall_slug>")
    def direct_wall_survey_report(wall_slug):
        wall = Wall.query.filter_by(slug=wall_slug).first_or_404()
        defects = Defect.query.filter_by(wall_id=wall.id).all()
        rem_dict = {r["id"]: r["label"] for r in REMEDIAL_OPTIONS}

        defect_items = []
        boq_items = []
        boq_subtotal = 0.0

        BOQ_RATES = {
            "repoint_lime": {"desc": "Rake out decayed joints to 25mm depth and repoint with St. Astier NHL 2 / 3.5 lime mortar", "spec": "EN 459-1 / BS 8221", "qty": "8.5 m²", "rate": 85.00, "total": 722.50},
            "helical_stitch": {"desc": "Install austenitic 316-grade helical stainless steel crack stitches (6mm x 1000mm)", "spec": "BRE Digest 329", "qty": "4 lin.m", "rate": 145.00, "total": 580.00},
            "grout_injection": {"desc": "Low-pressure void consolidation grouting with breathable hydraulic lime grout", "spec": "Historic England Guidance", "qty": "3.0 m²", "rate": 220.00, "total": 660.00},
            "rebuild_section": {"desc": "Careful numbered dismantling and rebuilding of unstable wall section plumb", "spec": "Eurocode 6 / BS EN 1996", "qty": "2.5 m²", "rate": 450.00, "total": 1125.00},
            "drainage_relief": {"desc": "Diamond core drill 65mm weep holes with geotextile filters and drainage relief pipe", "spec": "CIRIA C580", "qty": "4 No.", "rate": 120.00, "total": 480.00},
            "biocide_root": {"desc": "Application of enzymatic biocide and surgical extraction of invasive root systems", "spec": "Historic England Biological Decay", "qty": "5.0 m²", "rate": 65.00, "total": 325.00},
            "underpin_base": {"desc": "Sequential mass concrete underpin pins beneath distressed foundation footing", "spec": "ICE Manual of Geotechnical Engineering", "qty": "2.0 lin.m", "rate": 780.00, "total": 1560.00},
            "monitor_gauge": {"desc": "Install Avongard calibrated precision tell-tale crack motion gauges with log sheets", "spec": "BRE Defect Action Sheet 9", "qty": "2 Pairs", "rate": 90.00, "total": 180.00}
        }

        has_critical = False
        has_moderate = False

        for idx, d in enumerate(defects):
            cx = (d.x_min + d.x_max) / 2.0 * 100.0
            cy = (d.y_min + d.y_max) / 2.0 * 100.0
            rem_id = d.remedial_action or "repoint_lime"

            if d.severity == "critical":
                has_critical = True
            elif d.severity == "moderate":
                has_moderate = True

            defect_items.append({
                "index": idx + 1,
                "x_pct": round(cx, 1),
                "y_pct": round(cy, 1),
                "category": d.category,
                "title": d.title,
                "severity": d.severity,
                "remedial_action": rem_id,
                "remedial_label": rem_dict.get(rem_id, rem_id.replace("_", " ").title()),
                "scope": f"{int((d.x_max - d.x_min) * 1000)}mm x {int((d.y_max - d.y_min) * 1000)}mm Zone",
                "explanation": d.explanation or "Pathological defect identified during clinical visual inspection."
            })

            cost_info = BOQ_RATES.get(rem_id, {
                "desc": f"Remedial conservation work: {rem_dict.get(rem_id, rem_id)}",
                "spec": "BS 8221",
                "qty": "1 Item",
                "rate": 250.00,
                "total": 250.00
            })
            boq_items.append({
                "description": cost_info["desc"],
                "specification": cost_info["spec"],
                "quantity": cost_info["qty"],
                "rate": cost_info["rate"],
                "total": cost_info["total"]
            })
            boq_subtotal += cost_info["total"]

        if not boq_items:
            boq_items.append({
                "description": "Cyclical hydraulic lime pointing maintenance and surface inspection",
                "specification": "BS 8221-1",
                "quantity": "5.0 m²",
                "rate": 75.00,
                "total": 375.00
            })
            boq_subtotal = 375.00

        boq_prelims = 650.00
        boq_contingency = round((boq_subtotal + boq_prelims) * 0.15, 2)
        boq_grand_total = round(boq_subtotal + boq_prelims + boq_contingency, 2)

        if has_critical:
            rics_rating = 3
            rics_headline = "Condition Rating 3: Urgent Structural Remediation Required"
            rics_description = "Defects that are serious and/or need to be repaired, replaced or investigated urgently. Immediate conservation intervention scheduled."
        elif has_moderate or defects:
            rics_rating = 2
            rics_headline = "Condition Rating 2: Moderate Remedial Repairs Required"
            rics_description = "Defects that need repairing or replacing but are not considered to be serious or urgent. Interventions scheduled within 3 to 6 months."
        else:
            rics_rating = 1
            rics_headline = "Condition Rating 1: Routine Cyclical Maintenance Standard"
            rics_description = "No immediate structural repairs are currently required. Asset should be maintained in the normal manner."

        # Embodied Carbon & Heritage Sustainability Metrics (EN 15978 / PAS 2080)
        remedial_carbon_kg = 0.0
        for item in boq_items:
            desc = item.get("description", "").lower()
            qty = float(item.get("quantity", "1").split()[0]) if item.get("quantity") else 1.0
            if "point" in desc or "lime" in desc:
                remedial_carbon_kg += qty * 0.18
            elif "stitch" in desc or "tie" in desc:
                remedial_carbon_kg += qty * 2.80
            elif "grout" in desc:
                remedial_carbon_kg += qty * 12.50
            elif "weep" in desc or "drain" in desc:
                remedial_carbon_kg += qty * 1.20
            else:
                remedial_carbon_kg += qty * 0.50

        remedial_carbon_kg = max(round(remedial_carbon_kg + 18.5, 1), 22.0)
        demolition_carbon_kg = round(max(boq_subtotal * 1.85 + 1400.0, 2450.0), 1)
        carbon_saved_kg = round(demolition_carbon_kg - remedial_carbon_kg, 1)
        carbon_reduction_pct = round((carbon_saved_kg / demolition_carbon_kg) * 100)
        trees_equivalent = max(int(round(carbon_saved_kg / 22.0)), 1)

        return render_template(
            "survey_report.html",
            wall=wall.to_dict(),
            defect_items=defect_items,
            boq_items=boq_items,
            boq_subtotal=boq_subtotal,
            boq_prelims=boq_prelims,
            boq_contingency=boq_contingency,
            boq_grand_total=boq_grand_total,
            rics_rating=rics_rating,
            rics_headline=rics_headline,
            rics_description=rics_description,
            remedial_carbon_kg=remedial_carbon_kg,
            demolition_carbon_kg=demolition_carbon_kg,
            carbon_saved_kg=carbon_saved_kg,
            carbon_reduction_pct=carbon_reduction_pct,
            trees_equivalent=trees_equivalent,
            report_ref=f"RICS-{wall.slug[:8].upper()}-{datetime.now().strftime('%y%m')}",
            survey_date=datetime.now().strftime("%Y-%m-%d"),
            surveyor_name="Senior Chartered Building Surveyor (MRICS)"
        )

    # =========================================================================
    # AI ARCHITECTURAL CONSERVATOR & SOCRATIC DIAGNOSTIC ASSISTANT
    # =========================================================================
    @app.route("/api/ai/consult", methods=["POST"])
    def api_ai_consult():
        data = request.get_json() or {}
        wall_slug = data.get("wall_slug", "")
        mode = data.get("mode", "hint")
        box = data.get("box") or {}

        wall = Wall.query.filter_by(slug=wall_slug).first()
        defects = Defect.query.filter_by(wall_id=wall.id).all() if wall else []

        matched_defect = None
        if box and defects:
            best_iou = 0.0
            for d in defects:
                iou = calculate_iou(box, {
                    "x_min": d.x_min, "y_min": d.y_min,
                    "x_max": d.x_max, "y_max": d.y_max
                })
                dist = calculate_center_distance(box, {
                    "x_min": d.x_min, "y_min": d.y_min,
                    "x_max": d.x_max, "y_max": d.y_max
                })
                if (iou >= 0.15 or dist <= 0.20) and iou >= best_iou:
                    best_iou = iou
                    matched_defect = d

        if not matched_defect and defects:
            matched_defect = defects[0]

        target_cat = matched_defect.category if matched_defect else (box.get("category") or "joint_distress")
        wall_type_str = wall.wall_type if wall else "historic_masonry"

        SOCRATIC_HINTS = {
            "efflorescence": "Observe the surface deposit closely: is the white crystalline deposit powdery and dry on the face, or is it spalling the stone beneath? What does that indicate about whether salts are migrating out safely or bursting the pore matrix?",
            "spalling": "Examine the brick/stone faces: has the outer vitrified fire-skin detached from frost freeze-thaw cycles? What mortar type would you avoid so trapped moisture can escape through joints rather than stone faces?",
            "stepped_crack": "Trace the path of the rupture: notice how it stair-steps through the bed and perpend joints following the path of least resistance. Does this diagonal stepped pattern suggest differential foundation settlement or thermal contraction?",
            "expansion_failure": "Notice the vertical trajectory of this crack splitting through masonry units. Where are the movement joints? Could thermal expansion or lack of compressibility in the mortar have caused compressive jacking?",
            "coping_displacement": "Look at the crest of the wall: why have the capping stones shifted or toppled? Was there sufficient weather-shedding overhang or weight to resist livestock thrust and freeze-thaw levering?",
            "hearting_washout": "Peer between the outer faces: why has the interior core stone packing settled or emptied? What role does driving rain play when coping stones or joints fail?",
            "lateral_bulge": "Check the plumb line of the outer wythe: has the face pushed outward away from the core? Are there through-stones binding both faces together, or has internal gravel wash forced the skins apart?",
            "through_stone_failure": "Inspect the masonry rhythm: can you locate long stones that span the full wall thickness from front to back? What happens to double-wythe walls when through-stones are absent?",
            "base_subsidence": "Look at the lowest foundation boulder course: has the ground beneath sheared or washed out, causing the upper wall courses to slump unevenly?",
            "lime_washout": "Inspect the joint recesses: notice how deep the mortar has eroded away from the bedding plane. Why must you use naturally hydraulic lime (NHL) instead of Portland cement for reinstatement?",
            "hydrostatic_bulge": "Consider the earth mass retained behind this wall: why is the masonry bulging outwards at mid-height? Where is the groundwater draining if the weep holes are clogged or missing?",
            "flint_unseating": "Notice the nodules missing from the matrix: why do unknapped or knapped flints pop out when the lime binder degrades? How do gallet stone wedges help lock them in place?",
            "ashlar_spall": "Observe the fine joints and dressed ashlar face: is an oxidized internal iron cramp jacking the limestone face off along its natural bedding planes?",
            "basal_erosion": "Examine the base of the cob/earth wall: why has splashing rainwater and rising damp hollowed out the plinth? What protective apron is required?"
        }

        CLINICAL_SPECS = {
            "efflorescence": {
                "standard": "BS 8221-1:2000 & BRE Good Repair Guide 20",
                "diagnosis": "Surface salt crystallization (sodium/calcium sulfates). Active moisture transport through permeable masonry.",
                "mix": "Dry natural bristle brushing only. Do NOT power-wash. Allow wall to dry cyclically before NHL 2 pointing.",
                "procedure": "1. Remove crystallized bloom with stiff bristle dry brush. 2. Identify and eliminate water source. 3. Monitor for recurrence over 6 months.",
                "rate": "€45 / m² (Surface cleaning & moisture investigation)"
            },
            "stepped_crack": {
                "standard": "Eurocode 6 (EN 1996-1-1) & BRE Digest 329",
                "diagnosis": "Differential foundation settlement producing shear rupture across masonry bed and perpend joints.",
                "mix": "St. Astier NHL 3.5 with 1:2.5 sharp sand (0-2mm). Thixotropic helical anchoring grout.",
                "procedure": "1. Chase mortar beds to 500mm past crack both sides. 2. Insert austenitic 316-grade helical ties (6mm) at 450mm vertical centers. 3. Point flush with matching lime mortar.",
                "rate": "€145 / lin.m (Helical crack stitching & pointing)"
            },
            "lateral_bulge": {
                "standard": "Historic England Practical Conservation: Stone Masonry & BS 8221-2",
                "diagnosis": "Out-of-plumb wythe separation caused by internal core wash and missing through-stones.",
                "mix": "Dry stone re-bedding with through-stones at 1.0m horizontal and 0.6m vertical grid.",
                "procedure": "1. Erect temporary timber raking shores. 2. Dismantle unstable bulged wythe course by course. 3. Rebuild with 1:6 batter using through-stones extending through both leaves.",
                "rate": "€450 / m² (Careful dismantle & rebuild)"
            },
            "lime_washout": {
                "standard": "BS 8221-2:2000 Code of Practice for Cleaning and Surface Repair",
                "diagnosis": "Deep joint binder weathering (>20mm depth) leaving uncushioned stone contact points.",
                "mix": "NHL 2 for soft limestone / NHL 3.5 for exposed granite. 1:2.5 coarse washed pit sand (0-3mm).",
                "procedure": "1. Rake decayed mortar to depth equal to twice joint width. 2. Flush with clean potable water. 3. Tamp lime mortar in 10mm layers. 4. Stipple with churn brush and cure under damp hessian for 7 days.",
                "rate": "€85 / m² (Full joint raking, flushing & lime repointing)"
            },
            "hydrostatic_bulge": {
                "standard": "CIRIA Report C580 & Eurocode 7 (EN 1997-1)",
                "diagnosis": "Unrelieved pore water pressure behind retaining structure exerting lateral overturning moments.",
                "mix": "Perforated HDPE 65mm weep tubes with non-woven geotextile wrap and gravel backfill.",
                "procedure": "1. Diamond core-drill 65mm weep holes at 1.5m horizontal staggered centers at base level. 2. Clear debris from rear gravel bed. 3. Install weep tubes with non-return insect flap valves.",
                "rate": "€120 / No. (Core drilled weep hole installation)"
            }
        }

        default_spec = {
            "standard": "BS 8221-2 & Eurocode 6 (EN 1996)",
            "diagnosis": f"Pathological masonry distress categorized as {target_cat.replace('_', ' ')}.",
            "mix": "Naturally hydraulic lime NHL 2 / 3.5 matched to stone compressive strength.",
            "procedure": "Execute localized conservation intervention following BS 8221 preservation guidelines.",
            "rate": "€110 / m²"
        }

        spec_data = CLINICAL_SPECS.get(target_cat, default_spec)
        hint_text = SOCRATIC_HINTS.get(target_cat, f"Examine the load paths and joint mortar along this zone of the {wall_type_str.replace('_', ' ')}. What visual symptoms distinguish active structural displacement from superficial weathering?")

        return jsonify({
            "success": True,
            "mode": mode,
            "target_category": target_cat,
            "hint": hint_text,
            "specification": {
                "standard": spec_data["standard"],
                "diagnosis": spec_data["diagnosis"],
                "recommended_mortar_mix": spec_data["mix"],
                "remedial_procedure": spec_data["procedure"],
                "estimated_rate_euro": spec_data["rate"]
            }
        })

    # =========================================================================
    # STUDENT SKILL ASSESSMENT MODULE
    # =========================================================================

    @app.route("/skill-assessment")
    def skill_assessment_hub():
        """Student Skill Assessment Hub: Lists published assessment specimens with stats and guidelines."""
        specimens = Wall.query.filter_by(is_skill_assessment=True, is_published=True).all()
        specimen_list = []
        for s in specimens:
            d_count = Defect.query.filter_by(wall_id=s.id).count()
            data = s.to_dict()
            data["defect_count"] = d_count
            specimen_list.append(data)

        wall_types = sorted(list(set(s.wall_type for s in specimens if s.wall_type)))
        difficulties = ["beginner", "intermediate", "advanced"]

        return render_template(
            "skill_assessment_hub.html",
            specimens=specimen_list,
            total_specimens=len(specimens),
            wall_types=wall_types,
            difficulties=difficulties,
            defect_modes=SKILL_DEFECT_MODES
        )

    @app.route("/skill-assessment/<slug>")
    def skill_assessment_workstation(slug):
        """Student Skill Assessment Interactive Workstation: Point and click defect tagging."""
        wall = Wall.query.filter_by(slug=slug, is_skill_assessment=True, is_published=True).first_or_404()
        ground_truth_count = Defect.query.filter_by(wall_id=wall.id).count()
        modes_bundle = get_wall_defect_modes(wall)
        return render_template(
            "skill_assessment_workstation.html",
            wall=wall.to_dict(),
            ground_truth_count=ground_truth_count,
            prioritized_modes=modes_bundle["prioritized"],
            all_modes=modes_bundle["all"],
            defect_modes=modes_bundle["all"],
            remedial_options=REMEDIAL_OPTIONS
        )

    @app.route("/api/skill-assessment/evaluate/<slug>", methods=["POST"], strict_slashes=False)
    def api_skill_assessment_evaluate(slug):
        """
        Evaluates student submitted defect pins against professional ground-truth defects.
        Uses Euclidean hit-test with tolerance radius per defect (default 0.08 normalized).
        """
        wall = Wall.query.filter_by(slug=slug, is_skill_assessment=True).first_or_404()
        data = request.get_json(silent=True) or {}
        submitted_pins = data.get("pins", [])
        student_name = data.get("student_name", "Inspector Candidate").strip() or "Inspector Candidate"
        cohort_code = data.get("cohort_code", "SKILLS").strip().upper() or "SKILLS"
        session_id = data.get("session_id", uuid.uuid4().hex[:8])

        gt_defects = Defect.query.filter_by(wall_id=wall.id).all()
        gt_dicts = [d.to_dict() for d in gt_defects]

        matched_gt_ids = set()
        partial_gt_ids = set()
        evaluated_pins = []
        feedback_items = []
        earned_points = 0.0
        false_positives = 0

        # Match each student pin to nearest ground truth within tolerance radius
        for pin in submitted_pins:
            px = float(pin.get("x", 0.0))
            py = float(pin.get("y", 0.0))
            p_cat = str(pin.get("category") or "").strip()
            p_sev = str(pin.get("severity") or "moderate").strip()

            best_gt = None
            best_dist = 999.0

            for gt in gt_dicts:
                gt_cx = (gt["x_min"] + gt["x_max"]) / 2.0
                gt_cy = (gt["y_min"] + gt["y_max"]) / 2.0
                dist = math.hypot(px - gt_cx, py - gt_cy)
                tol = float(gt.get("tolerance_radius", 0.08) or 0.08)

                if dist <= tol and dist < best_dist:
                    best_dist = dist
                    best_gt = gt

            if best_gt:
                gt_cat = str(best_gt.get("category") or "").strip()
                gt_title = str(best_gt.get("title") or "Structural Defect").strip()
                gt_remedial = str(best_gt.get("remedial_action") or "repoint_lime").strip()

                category_match = (
                    p_cat.lower() == gt_cat.lower()
                    or p_cat.lower() == gt_title.lower()
                    or p_cat.lower().replace("_", " ") == gt_cat.lower().replace("_", " ")
                )
                severity_match = (p_sev.lower() == str(best_gt.get("severity", "moderate")).lower())

                if category_match:
                    matched_gt_ids.add(best_gt["id"])
                    earned_points += 1.0
                    pin_status = "correct"
                    explanation = f"Accurate identification ({gt_title}). Distance: {round(best_dist*100, 1)}% (within tolerance). {best_gt.get('explanation', '')}"
                else:
                    partial_gt_ids.add(best_gt["id"])
                    earned_points += 0.60
                    pin_status = "partial"
                    explanation = f"Location identified ({round(best_dist*100, 1)}% offset), but defect mode mismatch. Tagged as '{p_cat.replace('_', ' ').title()}', professional diagnosis: '{gt_title}'. {best_gt.get('explanation', '')}"

                evaluated_pins.append({
                    "x": px,
                    "y": py,
                    "category": p_cat,
                    "severity": p_sev,
                    "status": pin_status,
                    "distance": round(best_dist, 4),
                    "matched_gt_title": gt_title,
                    "expected_category": gt_cat,
                    "remedial_action": gt_remedial,
                    "explanation": explanation
                })

                feedback_items.append({
                    "title": gt_title,
                    "category": gt_cat,
                    "student_category": p_cat.replace('_', ' ').title(),
                    "severity": best_gt.get("severity", "moderate") or "moderate",
                    "remedial_action": gt_remedial,
                    "status": pin_status,
                    "explanation": explanation
                })
            else:
                false_positives += 1
                evaluated_pins.append({
                    "x": px,
                    "y": py,
                    "category": p_cat,
                    "severity": p_sev,
                    "status": "false_positive",
                    "distance": None,
                    "matched_gt_title": None,
                    "remedial_action": "none",
                    "explanation": f"False positive at ({round(px*100)}%, {round(py*100)}%). No verified pathology at this position."
                })

        total_gt = len(gt_dicts)
        full_hits = len(matched_gt_ids)
        partial_hits = len(partial_gt_ids - matched_gt_ids)
        missed_count = 0

        for gt in gt_dicts:
            if gt["id"] not in matched_gt_ids and gt["id"] not in partial_gt_ids:
                missed_count += 1
                gt_title = str(gt.get("title") or "Structural Defect").strip()
                gt_cat = str(gt.get("category") or "unspecified").strip()
                gt_remedial = str(gt.get("remedial_action") or "repoint_lime").strip()
                feedback_items.append({
                    "title": gt_title,
                    "category": gt_cat,
                    "student_category": "None (Missed)",
                    "severity": gt.get("severity", "moderate") or "moderate",
                    "remedial_action": gt_remedial,
                    "status": "missed",
                    "explanation": f"Unidentified pathology: {gt_title} ({gt.get('severity', 'moderate')}). {gt.get('explanation', '')}"
                })

        if total_gt > 0:
            raw_score = (earned_points / total_gt) * 100.0
            score = max(0.0, min(100.0, round(raw_score - (false_positives * 5.0), 1)))
        else:
            score = 100.0 if false_positives == 0 else 0.0

        if score >= 85.0:
            grade = "Distinction"
        elif score >= 70.0:
            grade = "Merit (Passing)"
        elif score >= 50.0:
            grade = "Pass"
        else:
            grade = "Remedial Review Required"

        passed = score >= 70.0

        try:
            attempt = AssessmentAttempt(
                wall_id=wall.id,
                student_session_id=session_id,
                cohort_code=cohort_code,
                assignment_code="SKILL-ASSESS",
                student_name=student_name,
                submitted_markers=submitted_pins,
                true_positives=full_hits + partial_hits,
                false_positives=false_positives,
                false_negatives=missed_count,
                score_percentage=score,
                passed=passed,
                feedback_notes={
                    "grade": grade,
                    "earned_points": round(earned_points, 2),
                    "total_gt": total_gt,
                    "items": feedback_items
                }
            )
            commit_with_retry(attempt)
        except Exception as attempt_err:
            db.session.rollback()
            print(f"Notice: Skill assessment attempt logging recovered: {attempt_err}")

        gt_overlay = []
        for gt in gt_dicts:
            gt_overlay.append({
                "id": gt["id"],
                "x": (gt["x_min"] + gt["x_max"]) / 2.0,
                "y": (gt["y_min"] + gt["y_max"]) / 2.0,
                "tolerance_radius": gt.get("tolerance_radius", 0.08) or 0.08,
                "category": gt.get("category") or "unspecified",
                "severity": gt.get("severity", "moderate") or "moderate",
                "remedial_action": gt.get("remedial_action") or "repoint_lime",
                "title": gt.get("title") or "Ground Truth Defect",
                "explanation": gt.get("explanation") or ""
            })

        return jsonify({
            "success": True,
            "score": score,
            "grade": grade,
            "passed": passed,
            "earned_points": round(earned_points, 2),
            "total_gt": total_gt,
            "full_hits": full_hits,
            "partial_hits": partial_hits,
            "false_positives": false_positives,
            "missed_count": missed_count,
            "evaluated_pins": evaluated_pins,
            "ground_truth": gt_overlay,
            "feedback": feedback_items
        })

    # --- Professional Controlled Ingestion & Grading Interface ---
    @app.route("/skill-assessment/admin")
    @admin_required
    def skill_assessment_admin():
        """
        Controlled professional upload and specimen management interface.
        Displays photography guidelines HUD (lighting, angles, scope, resolution),
        camera/file uploader, and published/pending specimen queue.
        """
        specimens = Wall.query.filter_by(is_skill_assessment=True).order_by(Wall.created_at.desc()).all()
        specimen_list = []
        for s in specimens:
            d_count = Defect.query.filter_by(wall_id=s.id).count()
            data = s.to_dict()
            data["defect_count"] = d_count
            specimen_list.append(data)

        return render_template(
            "skill_assessment_admin.html",
            specimens=specimen_list,
            wall_types=list(TAXONOMY_BY_WALL_TYPE.keys()),
            remedial_options=REMEDIAL_OPTIONS
        )

    @app.route("/skill-assessment/admin/upload", methods=["POST"])
    @admin_required
    def skill_assessment_upload():
        """
        Handles specimen image upload via camera or file dropzone.
        Saves locally and to Cloudinary with public access mode.
        """
        try:
            file = request.files.get("wall_image")
            if not file or not file.filename:
                return redirect(url_for("skill_assessment_admin"))

            title = request.form.get("title", "Assessment Specimen").strip()
            slug = "skill-" + secure_filename(title.lower().replace(" ", "-")) + "-" + uuid.uuid4().hex[:6]
            ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
            filename = f"{slug}{ext}"
            file_bytes = file.read()

            walls_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            with open(walls_path, "wb") as f_out:
                f_out.write(file_bytes)

            assess_path = os.path.join(app.config.get("ASSESSMENT_FOLDER", app.config["UPLOAD_FOLDER"]), filename)
            if assess_path != walls_path:
                with open(assess_path, "wb") as f_out:
                    f_out.write(file_bytes)

            db.session.remove()

            image_url_direct = None
            c_url = os.getenv("CLOUDINARY_URL", "").strip()
            if c_url:
                try:
                    import io
                    upload_result = cloudinary.uploader.upload(
                        io.BytesIO(file_bytes),
                        folder="wall_inspector/assessments",
                        public_id=slug,
                        overwrite=True,
                        resource_type="image",
                        access_mode="public"
                    )
                    image_url_direct = upload_result.get("secure_url")
                except Exception as cloud_err:
                    print(f"Cloudinary upload error in skill assessment: {cloud_err}")

            wall = Wall(
                slug=slug,
                title=title,
                description=request.form.get("description", ""),
                country=request.form.get("country", "Ireland"),
                region=request.form.get("region", ""),
                wall_type=request.form.get("wall_type", "dry_stone"),
                structural_function=request.form.get("structural_function", "boundary"),
                difficulty=request.form.get("difficulty", "intermediate"),
                image_filename=filename,
                image_url_direct=image_url_direct,
                is_published=True,
                is_skill_assessment=True
            )
            commit_with_retry(wall)

            grade_action = request.form.get("grade_action", "now")
            if grade_action == "now":
                return redirect(url_for("skill_assessment_grader", slug=wall.slug))
            return redirect(url_for("skill_assessment_admin"))
        except Exception as e:
            db.session.rollback()
            return f"Error uploading assessment specimen: {str(e)}", 500

    @app.route("/skill-assessment/admin/grade/<slug>")
    @admin_required
    def skill_assessment_grader(slug):
        """
        Professional point-and-tag defect grading workstation.
        Allows instructor to place ground-truth defect pins, calibrate tolerance radius,
        manage image-specific defect mode priorities and custom titles, and prescribe remediation.
        """
        wall = Wall.query.filter_by(slug=slug, is_skill_assessment=True).first_or_404()
        defects = Defect.query.filter_by(wall_id=wall.id).all()
        modes_bundle = get_wall_defect_modes(wall)
        return render_template(
            "skill_assessment_grader.html",
            wall=wall.to_dict(),
            defects=[d.to_dict() for d in defects],
            prioritized_modes=modes_bundle["prioritized"],
            all_modes=modes_bundle["all"],
            defect_modes=modes_bundle["all"],
            remedial_options=REMEDIAL_OPTIONS
        )

    @app.route("/api/skill-assessment/modes/<slug>", methods=["POST"], strict_slashes=False)
    @admin_required
    def api_skill_assessment_save_modes(slug):
        """
        Saves or updates the prioritized defect modes and custom defect titles for this wall image.
        Configured once per image to eliminate per-defect admin overhead.
        """
        wall = Wall.query.filter_by(slug=slug, is_skill_assessment=True).first_or_404()
        data = request.get_json(silent=True) or {}
        prioritized_modes = data.get("prioritized_modes", [])

        wall.assessment_defect_modes = prioritized_modes
        commit_with_retry(wall)

        modes_bundle = get_wall_defect_modes(wall)
        return jsonify({
            "success": True,
            "prioritized_modes": modes_bundle["prioritized"],
            "all_modes": modes_bundle["all"]
        })

    @app.route("/api/skill-assessment/grade/<slug>", methods=["POST"], strict_slashes=False)
    @admin_required
    def api_skill_assessment_save_defects(slug):
        """Saves or updates ground-truth defect points for an assessment specimen."""
        wall = Wall.query.filter_by(slug=slug, is_skill_assessment=True).first_or_404()
        data = request.get_json(silent=True) or {}
        incoming_defects = data.get("defects", [])

        Defect.query.filter_by(wall_id=wall.id).delete()

        current_modes = wall.assessment_defect_modes or []
        current_mode_ids = set()
        for cm in current_modes:
            if isinstance(cm, dict):
                current_mode_ids.add(cm.get("id"))
            elif isinstance(cm, str):
                current_mode_ids.add(cm)

        for d in incoming_defects:
            x = float(d.get("x", 0.5))
            y = float(d.get("y", 0.5))
            tol = float(d.get("tolerance_radius", 0.08) or 0.08)
            cat = str(d.get("category", "core_voiding")).strip()
            title = str(d.get("title", "Ground Truth Defect")).strip()

            new_d = Defect(
                wall_id=wall.id,
                target_type="pin",
                x_min=x,
                y_min=y,
                x_max=x,
                y_max=y,
                tolerance_radius=tol,
                category=cat,
                severity=d.get("severity", "moderate"),
                remedial_action=d.get("remedial_action", "repoint_lime"),
                title=title,
                explanation=d.get("explanation", "")
            )
            db.session.add(new_d)

            # Auto-ensure defect mode is in wall's prioritized palette
            if cat not in current_mode_ids:
                current_modes.append({"id": cat, "label": title or cat.replace("_", " ").title(), "is_custom": True})
                current_mode_ids.add(cat)

        wall.assessment_defect_modes = current_modes
        commit_with_retry()
        return jsonify({"success": True, "count": len(incoming_defects)})

    @app.route("/api/skill-assessment/delete/<slug>", methods=["POST"])
    @admin_required
    def api_skill_assessment_delete(slug):
        """Deletes an assessment specimen and its defects."""
        wall = Wall.query.filter_by(slug=slug, is_skill_assessment=True).first_or_404()
        if wall.image_filename:
            for folder in [app.config.get("UPLOAD_FOLDER"), app.config.get("ASSESSMENT_FOLDER")]:
                if folder:
                    f_path = os.path.join(folder, wall.image_filename)
                    if os.path.exists(f_path):
                        try:
                            os.remove(f_path)
                        except OSError:
                            pass

        Defect.query.filter_by(wall_id=wall.id).delete()
        AssessmentAttempt.query.filter_by(wall_id=wall.id).delete()
        db.session.delete(wall)
        db.session.commit()
        return jsonify({"success": True})

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
