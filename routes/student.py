from flask import Blueprint, render_template, request, jsonify
from models import db, Wall, Defect, AssessmentAttempt

student_bp = Blueprint("student", __name__, url_prefix="/inspect")


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


@student_bp.route("/<wall_slug>")
def inspect_wall(wall_slug):
    wall = Wall.query.filter_by(slug=wall_slug, is_published=True).first_or_404()
    return render_template("inspect.html", wall=wall)


@student_bp.route("/<wall_slug>/submit", methods=["POST"])
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

    # Match each student marker against ground truth boxes (IoU threshold 0.25)
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

    # Simple rubric: proportion of found defects with false positive deduction
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