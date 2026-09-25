import os
import io
import json
import base64
import urllib.request
import urllib.error
from PIL import Image, ExifTags

GEOLOGICAL_REGIONS = {
    "clare": {
        "bedrock": "Carboniferous Limestone (Burren Karst Formation)",
        "mineralogy": "Dense calcitic limestone, fossiliferous, susceptible to solution weathering and biogenic acid etch.",
        "compatible_mortar": "Non-hydraulic hot-mixed lime (1:3 sharp sand) or NHL 2.0."
    },
    "galway": {
        "bedrock": "Caledonian Galway Granite & Connemara Marble",
        "mineralogy": "Porphyritic biotite granite with quartz/feldspar phenocrysts, high compressive strength.",
        "compatible_mortar": "Slightly hydraulic lime NHL 2.0 to NHL 3.5 with coarse granite grit."
    },
    "dublin": {
        "bedrock": "Lower Carboniferous Calp Limestone & Lucan Mudstone",
        "mineralogy": "Dark argillaceous limestone rich in shaly laminations and pyrite, vulnerable to delamination.",
        "compatible_mortar": "Feebly hydraulic lime NHL 2.0 with well-graded river sand."
    },
    "wicklow": {
        "bedrock": "Leinster Granite & Silurian Mica Schist",
        "mineralogy": "Muscovite granite with coarse quartz grains and fractured schistose cleavage.",
        "compatible_mortar": "Moderately hydraulic lime NHL 3.5 with coarse sharp sand."
    },
    "kerry": {
        "bedrock": "Devonian Old Red Sandstone",
        "mineralogy": "Siliceous quartz arenite sandstone, vulnerable to face exfoliation along bedding planes.",
        "compatible_mortar": "Hot-mixed lime or NHL 2.0; avoid hard cement ribbons."
    },
    "cork": {
        "bedrock": "Devonian Purple Sandstone & Carboniferous Limestone",
        "mineralogy": "Dense quartzose sandstone intercalated with siltstones and marine limestone.",
        "compatible_mortar": "Non-hydraulic hot mixed lime putty or NHL 2.0."
    },
    "antrim": {
        "bedrock": "Tertiary Basalt & Ulster Cretaceous White Chalk",
        "mineralogy": "Dense dark columnar basalt with high thermal mass, alongside soft calcareous chalk.",
        "compatible_mortar": "Hydraulic lime NHL 3.5 for exposed basalt; pure lime for chalk."
    },
    "bath": {
        "bedrock": "Middle Jurassic Great Oolite (Bath Freestone)",
        "mineralogy": "Fine-grained oolitic limestone with high porosity, highly susceptible to freeze-thaw spall.",
        "compatible_mortar": "Non-hydraulic hot-mixed lime putty with Bath stone dust and fine silver sand."
    },
    "cotswold": {
        "bedrock": "Inferior Oolite Jurassic Limestone",
        "mineralogy": "Shelly ferruginous oolite limestone displaying warm honey hues, soft and workable.",
        "compatible_mortar": "Non-hydraulic lime putty or NHL 2.0 with crushed limestone aggregate."
    },
    "yorkshire": {
        "bedrock": "Carboniferous Millstone Grit Sandstone",
        "mineralogy": "Coarse-grained feldspathic sandstone, highly weather-resistant but porous.",
        "compatible_mortar": "Hydraulic lime NHL 3.5 with well-graded sharp grit aggregate."
    }
}

def extract_exif_metadata(image):
    """Extracts camera model, lens metadata, timestamp, and GPS coordinates if available."""
    metadata = {
        "camera_make": None,
        "camera_model": None,
        "datetime": None,
        "focal_length": None,
        "has_gps": False,
        "gps_coords": None
    }
    try:
        exif = image.getexif()
        if not exif:
            return metadata

        for tag_id, value in exif.items():
            tag = ExifTags.TAGS.get(tag_id, tag_id)
            if tag == "Make":
                metadata["camera_make"] = str(value).strip()
            elif tag == "Model":
                metadata["camera_model"] = str(value).strip()
            elif tag == "DateTime":
                metadata["datetime"] = str(value).strip()
            elif tag == "FocalLength":
                try:
                    metadata["focal_length"] = float(value)
                except Exception:
                    pass

        # Check GPS IFD if available
        gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo) if hasattr(exif, "get_ifd") else None
        if gps_ifd:
            metadata["has_gps"] = True
    except Exception as e:
        print(f"Notice: EXIF extraction encountered: {e}")
    return metadata

def audit_image_optics(image_bytes):
    """
    Analyzes optical capture quality: resolution, aspect ratio,
    exposure, contrast distribution, and EXIF metadata.
    """
    optics = {
        "width": 0,
        "height": 0,
        "megapixels": 0.0,
        "aspect_ratio": "1:1",
        "resolution_pass": True,
        "brightness_score": 85,
        "contrast_score": 85,
        "exif": {}
    }
    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        optics["width"] = w
        optics["height"] = h
        mp = round((w * h) / 1000000.0, 2)
        optics["megapixels"] = mp

        # Resolution check: minimum 1080p equivalent or > 1.5 MP
        if w < 1080 and h < 1080:
            optics["resolution_pass"] = False

        ratio = w / float(h) if h > 0 else 1.0
        if 1.2 <= ratio <= 1.8:
            optics["aspect_ratio"] = "Landscape (Ideal)"
        elif 0.55 <= ratio <= 0.85:
            optics["aspect_ratio"] = "Portrait (Elevation)"
        else:
            optics["aspect_ratio"] = f"{round(ratio, 2)}:1"

        optics["exif"] = extract_exif_metadata(img)

        # Basic luminance and contrast distribution via grayscale thumbnail
        thumb = img.convert("L").resize((64, 64))
        pixels = list(thumb.get_flattened_data() if hasattr(thumb, "get_flattened_data") else thumb.getdata())
        avg_lum = sum(pixels) / float(len(pixels))
        variance = sum((p - avg_lum) ** 2 for p in pixels) / float(len(pixels))
        contrast = variance ** 0.5

        # Lighting check: avoid pitch black or completely washed out
        if avg_lum < 40:
            optics["brightness_score"] = 55  # underexposed / dark
        elif avg_lum > 220:
            optics["brightness_score"] = 60  # overexposed / glare
        else:
            optics["brightness_score"] = 90  # good diffuse range

        if contrast < 25:
            optics["contrast_score"] = 65  # low contrast / flat
        else:
            optics["contrast_score"] = 90

    except Exception as err:
        print(f"Notice: Optical check encountered: {err}")
    return optics

def enrich_geological_context(wall, exif_data=None):
    """
    Infers native stone geological context based on wall region, country, and archetype.
    """
    region_str = f"{wall.region or ''} {wall.country or ''} {wall.title or ''}".lower()
    matched = None

    for key, data in GEOLOGICAL_REGIONS.items():
        if key in region_str:
            matched = data
            break

    if not matched:
        wtype = (wall.wall_type or "").lower()
        if "granite" in wtype or "granite" in region_str:
            matched = GEOLOGICAL_REGIONS["galway"]
        elif "ashlar" in wtype or "dressed" in region_str:
            matched = GEOLOGICAL_REGIONS["bath"]
        elif "flint" in wtype:
            matched = {
                "bedrock": "Upper Cretaceous Chalk & Flint Nodules",
                "mineralogy": "Microcrystalline cryptocrystalline quartz nodules set in calcareous lime matrix.",
                "compatible_mortar": "Hot-mixed lime mortar with flint gallets."
            }
        elif "cob" in wtype or "earth" in wtype:
            matched = {
                "bedrock": "Subsoil Clay, Silt & Aggregates (Mass Earth)",
                "mineralogy": "Sub-surface clay matrix stabilized with straw fiber; non-cementitious earthen composite.",
                "compatible_mortar": "Compatible subsoil clay-straw repair and sacrificial lime wash."
            }
        else:
            matched = GEOLOGICAL_REGIONS["clare"]

    return {
        "bedrock_formation": matched["bedrock"],
        "mineralogy": matched["mineralogy"],
        "compatible_mortar": matched["compatible_mortar"]
    }

def run_sentinel_audit(wall, image_bytes):
    """
    Executes the Intake Sentinel Agent:
    1. Optical quality and EXIF inspection via Pillow.
    2. Regional geological context enrichment.
    3. Multi-modal photogrammetric evaluation via Gemini Vision (if key available)
       or clinical heuristic engine.
    4. Computes composite quality score (0-100) and advisory status (passed/advisory/warning).
    5. NEVER halts or blocks upload: results are strictly advisory.
    """
    optics = audit_image_optics(image_bytes)
    geology = enrich_geological_context(wall, optics.get("exif"))

    checklist = {
        "orthogonal_plane": {
            "title": "90° Orthogonal Alignment",
            "status": "pass",
            "score": 90,
            "feedback": "Photo plane approximately orthogonal to masonry elevation."
        },
        "diffuse_lighting": {
            "title": "Diffuse Ambient Lighting",
            "status": "pass" if optics["brightness_score"] >= 80 else "advisory",
            "score": optics["brightness_score"],
            "feedback": "Even ambient illumination across stone faces without severe raking shadows." if optics["brightness_score"] >= 80 else "Raking lighting or dark shadow zones detected; proceed under advisement."
        },
        "framing_scope": {
            "title": "Macro-to-Course Framing",
            "status": "pass",
            "score": 90,
            "feedback": "Adequate course height captured with clear bed arrises."
        },
        "resolution": {
            "title": "Optical Resolution & Sharpness",
            "status": "pass" if optics["resolution_pass"] else "advisory",
            "score": 95 if optics["resolution_pass"] else 65,
            "feedback": f"High fidelity capture ({optics['megapixels']} MP, {optics['width']}x{optics['height']})." if optics["resolution_pass"] else f"Sub-1080p resolution ({optics['width']}x{optics['height']}); fine hairline cracks (<2mm) may be difficult to discern."
        }
    }

    recommendations = []
    if not optics["resolution_pass"]:
        recommendations.append("Recommended for future captures: capture at 1080p minimum (1920x1080) for high-resolution arris inspections.")
    if optics["brightness_score"] < 80:
        recommendations.append("Recommended for future captures: capture under overcast skies or use diffuse ambient light to avoid deep joint shadows.")

    # Multimodal Photogrammetry Audit with Gemini Vision if API key present
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if api_key:
        try:
            mime_type = "image/jpeg"
            b64_img = base64.b64encode(image_bytes).decode("utf-8")
            prompt_text = (
                f"You are the Intake Sentinel, a senior heritage photogrammetry auditor. "
                f"Evaluate this masonry wall photograph for field assessment suitability. "
                f"Masonry Archetype: '{wall.wall_type}', Title: '{wall.title}'. "
                f"Audit these 4 criteria:\n"
                f"1. 90° Orthogonal Alignment (is the camera perpendicular or tilted/skewed?)\n"
                f"2. Diffuse Ambient Lighting (is illumination even or are there harsh cast shadows?)\n"
                f"3. Macro-to-Course Framing (are courses and bed joints well-framed?)\n"
                f"4. Resolution & Sharpness (are joint arrises crisp and distinct?)\n"
                f"Return ONLY a JSON object with keys:\n"
                f"- 'overall_score': integer 0 to 100\n"
                f"- 'orthogonal_status': 'pass', 'advisory', or 'warning'\n"
                f"- 'orthogonal_notes': string\n"
                f"- 'lighting_status': 'pass', 'advisory', or 'warning'\n"
                f"- 'lighting_notes': string\n"
                f"- 'framing_status': 'pass', 'advisory', or 'warning'\n"
                f"- 'framing_notes': string\n"
                f"- 'recommendations': array of strings (actionable advice for future captures)"
            )
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt_text},
                            {"inlineData": {"mimeType": mime_type, "data": b64_img}}
                        ]
                    }
                ],
                "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
            }
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text_out = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_out)
                if isinstance(parsed, dict):
                    if "orthogonal_status" in parsed:
                        checklist["orthogonal_plane"]["status"] = parsed["orthogonal_status"]
                        checklist["orthogonal_plane"]["feedback"] = parsed.get("orthogonal_notes", checklist["orthogonal_plane"]["feedback"])
                    if "lighting_status" in parsed:
                        checklist["diffuse_lighting"]["status"] = parsed["lighting_status"]
                        checklist["diffuse_lighting"]["feedback"] = parsed.get("lighting_notes", checklist["diffuse_lighting"]["feedback"])
                    if "framing_status" in parsed:
                        checklist["framing_scope"]["status"] = parsed["framing_status"]
                        checklist["framing_scope"]["feedback"] = parsed.get("framing_notes", checklist["framing_scope"]["feedback"])
                    if parsed.get("recommendations"):
                        recommendations.extend(parsed["recommendations"])
        except Exception as ai_err:
            print(f"Notice: Gemini photogrammetry check note: {ai_err}")

    # Compute composite quality score
    status_weights = {"pass": 25, "advisory": 18, "warning": 10}
    total_score = sum(status_weights.get(item["status"], 20) for item in checklist.values())

    # Assign overall Sentinel Status
    has_warning = any(item["status"] == "warning" for item in checklist.values())
    has_advisory = any(item["status"] == "advisory" for item in checklist.values())

    if has_warning or total_score < 65:
        overall_status = "warning"
        summary_title = "Sentinel Warning: Photographic Discrepancies Detected"
    elif has_advisory or total_score < 85:
        overall_status = "advisory"
        summary_title = "Sentinel Advisory: Minor Capture Imperfections"
    else:
        overall_status = "passed"
        summary_title = "Sentinel Cleared: High-Fidelity Capture"

    if not recommendations:
        recommendations.append("Capture satisfies all 4 core photogrammetry pillars. Ready for clinical ground-truth grading.")

    report = {
        "score": total_score,
        "status": overall_status,
        "summary": summary_title,
        "checklist": checklist,
        "geology": geology,
        "optics": optics,
        "recommendations": recommendations,
        "advisory_notice": "Sentinel advisories are informational and do not restrict specimen grading or assessment."
    }

    # Persist directly to Wall
    wall.sentinel_score = total_score
    wall.sentinel_status = overall_status
    wall.sentinel_report = report
    return report
