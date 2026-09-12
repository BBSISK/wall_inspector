from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from models import db, Wall, Defect

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.route("/walls/<wall_id>/tagger")
def tagger_view(wall_id):
    wall = Wall.query.get_or_404(wall_id)
    return render_template("tagger.html", wall=wall)

@admin_bp.route("/walls/<wall_id>/defects", methods=["GET"])
def get_defects(wall_id):
    defects = Defect.query.filter_by(wall_id=wall_id).all()
    return jsonify([d.to_dict() for d in defects])

@admin_bp.route("/walls/<wall_id>/defects", methods=["POST"])
def add_defect(wall_id):
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
        remedial_action=data.get("remedial_action", "repoint_lime"),
        title=data.get("title", "Untitled Defect"),
        explanation=data.get("explanation", "")
    )
    db.session.add(defect)
    db.session.commit()
    return jsonify(defect.to_dict()), 201

@admin_bp.route("/defects/<defect_id>", methods=["DELETE"])
def delete_defect(defect_id):
    defect = Defect.query.get_or_404(defect_id)
    db.session.delete(defect)
    db.session.commit()
    return jsonify({"status": "deleted", "id": defect_id})