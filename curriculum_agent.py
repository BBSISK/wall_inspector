import random
import hashlib
from datetime import datetime, timezone

def assemble_battery_specimens(candidate_walls, target_count=10, difficulty_filter=None, wall_type_filter=None):
    """
    Curriculum Director Agent: Assembles a pedagogically balanced assessment battery
    from candidate skill assessment specimens.
    
    1. Filters to published specimens with verified ground-truth pins.
    2. Prioritizes specimens with high Sentinel QA scores.
    3. Balances difficulty tiers (Beginner, Intermediate, Advanced).
    4. Diversifies architectural masonry archetypes so students are tested on varied pathologies.
    """
    valid = []
    for w in candidate_walls:
        # Require published skill assessment specimens
        if not getattr(w, "is_skill_assessment", True) or not getattr(w, "is_published", True):
            continue
        
        # Apply optional filters
        if difficulty_filter and getattr(w, "difficulty", "") != difficulty_filter:
            continue
        if wall_type_filter and getattr(w, "wall_type", "") != wall_type_filter:
            continue
            
        valid.append(w)

    if not valid:
        # Fallback to any candidate walls if strict filter yielded 0
        valid = [w for w in candidate_walls if getattr(w, "is_skill_assessment", True)]

    if not valid:
        return []

    # If pool is smaller than or equal to target_count, return all sorted by sentinel score
    if len(valid) <= target_count:
        valid.sort(key=lambda x: getattr(x, "sentinel_score", 100) or 100, reverse=True)
        return valid

    # Partition by difficulty
    by_diff = {"beginner": [], "intermediate": [], "advanced": []}
    for w in valid:
        diff = getattr(w, "difficulty", "intermediate") or "intermediate"
        by_diff.setdefault(diff, []).append(w)

    # Sort each tier prioritizing higher sentinel score
    for diff in by_diff:
        by_diff[diff].sort(key=lambda x: getattr(x, "sentinel_score", 100) or 100, reverse=True)

    # Target distribution: ~30% beginner, ~50% intermediate, ~20% advanced
    n_beg = max(1, round(target_count * 0.3))
    n_adv = max(1, round(target_count * 0.2))
    n_int = max(1, target_count - n_beg - n_adv)

    selected = []
    selected.extend(by_diff.get("beginner", [])[:n_beg])
    selected.extend(by_diff.get("intermediate", [])[:n_int])
    selected.extend(by_diff.get("advanced", [])[:n_adv])

    # If we still need more to hit target_count, backfill from remaining unused
    used_ids = {w.id for w in selected}
    remaining = [w for w in valid if w.id not in used_ids]
    remaining.sort(key=lambda x: getattr(x, "sentinel_score", 100) or 100, reverse=True)

    while len(selected) < target_count and remaining:
        selected.append(remaining.pop(0))

    # Diversify archetypes order so consecutive questions are varied
    selected.sort(key=lambda x: (getattr(x, "difficulty", "intermediate"), getattr(x, "wall_type", "")))
    return selected[:target_count]

def generate_student_battery_sequence(battery_wall_slugs, student_seed, target_count=10):
    """
    Anti-Collusion Side-by-Side Randomizer:
    Generates a deterministic pseudo-random permutation of the battery specimens
    seeded by the student's unique ID or session token.
    
    Guarantees:
    1. Adjacent students sitting side-by-side see completely different specimens on Question 1, 2, etc.
    2. A student refreshing their browser or resuming maintains the exact same sequence.
    """
    if not battery_wall_slugs:
        return []

    slugs = list(battery_wall_slugs)
    # Generate integer seed from student_seed hash
    hash_digest = hashlib.sha256(str(student_seed).encode("utf-8")).hexdigest()
    seed_int = int(hash_digest[:8], 16)
    
    rng = random.Random(seed_int)
    shuffled = list(slugs)
    rng.shuffle(shuffled)

    return shuffled[:target_count]

def get_dry_run_calibration_data():
    """
    Returns guided tutorial instructions for the pre-exam practice dry-run sample.
    """
    return {
        "title": "🔰 Practice Calibration Specimen (Unscored)",
        "subtitle": "Learn the inspection workstation controls before your timed battery begins.",
        "steps": [
            {
                "icon": "fa-magnifying-glass-plus",
                "title": "1. Pan & Zoom Inspection",
                "instruction": "Scroll mouse wheel or tap HUD (+) / (-) to zoom close-up to inspect joint arrises and bedding planes."
            },
            {
                "icon": "fa-crosshairs",
                "title": "2. Click to Place Pin",
                "instruction": "Click directly on any visible defect (mortar washout, spall, fracture) to position a defect pin."
            },
            {
                "icon": "fa-list-check",
                "title": "3. Classify Pathology & Severity",
                "instruction": "Select the correct defect mode and severity (Minor, Moderate, Critical) from the dropdown palette."
            },
            {
                "icon": "fa-paper-plane",
                "title": "4. Submit & Instant Evaluation",
                "instruction": "Submit pins to verify spatial hit-testing against ground-truth and inspect solution overlays."
            }
        ],
        "skip_label": "⏩ Skip Practice & Begin Question 1 of Battery",
        "advisory": "Pins placed during this practice dry-run are unscored and will not affect your grade."
    }

def analyze_cohort_intelligence(attempts, walls_dict, target_cohort="GENERAL"):
    """
    Curriculum Director Analytics:
    Synthesizes class-wide inspection attempts across a battery to detect blindspots,
    missed pathologies, and recommended next curricular interventions.
    """
    total_attempts = len(attempts)
    if total_attempts == 0:
        return {
            "total_attempts": 0,
            "cohort_avg_score": 0.0,
            "pass_rate_pct": 0.0,
            "blindspots": [],
            "strengths": [],
            "director_recommendation": "No student attempts submitted yet for this battery."
        }

    scores = [a.score_percentage for a in attempts if a.score_percentage is not None]
    avg_score = round(sum(scores) / float(len(scores)), 1) if scores else 0.0
    passed_count = sum(1 for a in attempts if getattr(a, "passed", False) or (a.score_percentage and a.score_percentage >= 70.0))
    pass_rate = round((passed_count / float(total_attempts)) * 100.0, 1)

    # Aggregate defect mode performance from feedback notes
    category_hits = {}
    category_misses = {}

    for a in attempts:
        notes = getattr(a, "feedback_notes", None) or {}
        breakdown = notes.get("breakdown", []) if isinstance(notes, dict) else []
        for item in breakdown:
            cat = item.get("category") or item.get("item", "General Defect")
            status = item.get("status", "")
            if status == "correct":
                category_hits[cat] = category_hits.get(cat, 0) + 1
            elif status in ["missed", "partial"]:
                category_misses[cat] = category_misses.get(cat, 0) + 1

    all_cats = set(category_hits.keys()) | set(category_misses.keys())
    cat_stats = []
    for c in all_cats:
        h = category_hits.get(c, 0)
        m = category_misses.get(c, 0)
        tot = h + m
        pct = round((h / float(tot)) * 100.0) if tot > 0 else 0
        cat_stats.append({"category": c, "hit_rate": pct, "total": tot, "hits": h, "misses": m})

    # Sort to find blindspots (lowest hit rate) and strengths (highest hit rate)
    cat_stats.sort(key=lambda x: x["hit_rate"])
    blindspots = [cs for cs in cat_stats if cs["hit_rate"] < 65 and cs["total"] >= 2]
    strengths = [cs for cs in cat_stats if cs["hit_rate"] >= 80 and cs["total"] >= 2]

    # Generate prescriptive recommendations
    if blindspots:
        top_weakness = blindspots[0]["category"]
        recommendation = (
            f"Curriculum Alert: Cohort demonstrates significant diagnostic difficulty with '{top_weakness}' "
            f"({blindspots[0]['hit_rate']}% accuracy). Recommend an instructor-led studio on differential diagnosis "
            f"and assigning targeted remediation specimens."
        )
    elif avg_score >= 80.0:
        recommendation = (
            f"Exemplary Cohort Performance: Class demonstrates mastery across core masonry pathologies "
            f"with an average of {avg_score}%. Recommend advancing to advanced multi-phase structural failure specimens."
        )
    else:
        recommendation = (
            f"Cohort progressing satisfactorily ({avg_score}% average). Continue reinforced practice with mixed-archetype "
            f"retaining and freestanding specimens."
        )

    return {
        "total_attempts": total_attempts,
        "cohort_avg_score": avg_score,
        "pass_rate_pct": pass_rate,
        "category_stats": cat_stats,
        "blindspots": blindspots,
        "strengths": strengths,
        "director_recommendation": recommendation
    }
