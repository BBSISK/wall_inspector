#!/usr/bin/env python3
"""
promote_wall_to_skill.py
CLI tool to promote catalog masonry specimens to the Ground-Truth Grading Repository.

Usage:
    python3 promote_wall_to_skill.py --list
    python3 promote_wall_to_skill.py --latest
    python3 promote_wall_to_skill.py <slug_or_title_or_id>
    python3 promote_wall_to_skill.py --all
"""

import os
import sys

# Ensure application root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import Wall


def list_non_skill_walls():
    with app.app_context():
        walls = Wall.query.filter_by(is_skill_assessment=False).order_by(Wall.created_at.desc()).all()
        print(f"\nFound {len(walls)} wall(s) currently in the General Catalog (not in Grading Repository):\n")
        print(f"{'SLUG':<45} | {'TITLE':<40} | {'CREATED AT'}")
        print("-" * 110)
        for w in walls:
            created = w.created_at.strftime("%Y-%m-%d %H:%M:%S") if w.created_at else "Unknown"
            print(f"{w.slug:<45} | {w.title[:38]:<40} | {created}")
        print("\nTo promote a wall, run:\n  python3 promote_wall_to_skill.py <slug_or_title>\n  python3 promote_wall_to_skill.py --latest\n")


def promote_wall(wall):
    wall.is_skill_assessment = True
    if not wall.grading_status:
        wall.grading_status = "auto_suggested"

    # 1. Run Intake Sentinel photogrammetry audit if image exists locally
    try:
        from sentinel_agent import run_sentinel_audit
        img_path = os.path.join(app.config["UPLOAD_FOLDER"], wall.image_filename)
        if os.path.exists(img_path):
            with open(img_path, "rb") as f_img:
                run_sentinel_audit(wall, f_img.read())
            print(f"  ✓ Intake Sentinel QA audit complete (Score: {wall.sentinel_score}/100, Status: {wall.sentinel_status})")
    except Exception as s_err:
        print(f"  Notice (Sentinel Audit): {s_err}")

    # 2. Pre-generate Gemini Vision defect proposals
    try:
        from app import generate_ai_defect_suggestions
        generate_ai_defect_suggestions(wall)
        print("  ✓ AI defect proposal pins generated")
    except Exception as ai_err:
        print(f"  Notice (AI Proposals): {ai_err}")

    db.session.commit()
    print(f"\n🎉 Successfully promoted '{wall.title}' to Skill Assessment Specimen Bank!")
    print(f"  → Grade here: http://localhost:5000/skill-assessment/admin/grade/{wall.slug}")
    print(f"  → Specimen Queue: http://localhost:5000/skill-assessment/admin\n")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ["-h", "--help"]:
        print(__doc__)
        return

    arg = sys.argv[1].strip()

    with app.app_context():
        if arg in ["-l", "--list"]:
            list_non_skill_walls()
            return

        if arg == "--latest":
            wall = Wall.query.filter_by(is_skill_assessment=False).order_by(Wall.created_at.desc()).first()
            if not wall:
                print("No non-skill walls found in catalog.")
                return
            print(f"Promoting most recent wall: '{wall.title}' ({wall.slug})...")
            promote_wall(wall)
            return

        if arg == "--all":
            walls = Wall.query.filter_by(is_skill_assessment=False).all()
            if not walls:
                print("No non-skill walls found in catalog.")
                return
            print(f"Promoting all {len(walls)} non-skill walls...")
            for w in walls:
                promote_wall(w)
            return

        # Target by slug, id, or partial title match
        wall = Wall.query.filter(
            (Wall.slug == arg) | (Wall.id == arg) | (Wall.title.ilike(f"%{arg}%"))
        ).first()

        if not wall:
            print(f"Error: Wall matching '{arg}' not found.")
            print("Run 'python3 promote_wall_to_skill.py --list' to see available walls.")
            sys.exit(1)

        print(f"Promoting wall: '{wall.title}' ({wall.slug})...")
        promote_wall(wall)


if __name__ == "__main__":
    main()

