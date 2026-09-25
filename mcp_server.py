#!/usr/bin/env python3
"""
Global Wall Inspector — Model Context Protocol (MCP) Server
===========================================================
Exposes the platform's specialized AI agents and MLOps engines over the
standardized JSON-RPC 2.0 Model Context Protocol (MCP) so external LLM hosts
(Claude Desktop, Gemini CLI, Cursor, Antigravity) can invoke masonry diagnostics
and cohort curriculum analytics directly.

Exposed MCP Tools:
  1. sentinel_evaluate_image        — Runs IntakeSentinelAgent quality & sharpness checks
  2. curriculum_cohort_intelligence — Queries CurriculumDirectorAgent cohort pass rates & weaknesses
  3. list_skill_specimens           — Retrieves active masonry skill assessment specimens
  4. export_coco_dataset_stats      — Summarizes MLOps COCO 1.0 Computer Vision dataset metrics
"""

import io
import json
import sys
from typing import Dict, Any, List

from PIL import Image
from app import app, analyze_cohort_intelligence
from sentinel_agent import audit_image_optics, run_sentinel_audit
from models import Wall, Defect, AssessmentAttempt


class WallInspectorMCPServer:
    """JSON-RPC 2.0 Model Context Protocol (MCP) Server for Global Wall Inspector."""

    SERVER_INFO = {
        "name": "global-wall-inspector-mcp",
        "version": "1.0.0",
        "protocolVersion": "2024-11-05"
    }

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return MCP-compliant tool schemas."""
        return [
            {
                "name": "sentinel_evaluate_image",
                "description": (
                    "Runs the Intake Sentinel Agent on a masonry wall photograph to evaluate "
                    "resolution, Laplacian focus sharpness, luminance exposure, and geological context."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "width": {"type": "integer", "description": "Synthetic test image width (if no file path provided)", "default": 1600},
                        "height": {"type": "integer", "description": "Synthetic test image height (if no file path provided)", "default": 1200},
                        "file_path": {"type": "string", "description": "Optional local path to a JPEG/PNG masonry image"}
                    }
                }
            },
            {
                "name": "curriculum_cohort_intelligence",
                "description": (
                    "Invokes the Curriculum Director Agent to analyze student assessment attempts, "
                    "cohort pass rates, and top missed masonry defect categories."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "cohort_code": {"type": "string", "description": "Optional cohort code filter (e.g. GENERAL)"}
                    }
                }
            },
            {
                "name": "list_skill_specimens",
                "description": "Lists published masonry skill assessment specimens with wall type, difficulty, and ground-truth defect counts.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "difficulty": {"type": "string", "description": "Optional filter: beginner, intermediate, advanced"},
                        "limit": {"type": "integer", "default": 10}
                    }
                }
            },
            {
                "name": "export_coco_dataset_stats",
                "description": "Returns MLOps COCO 1.0 Computer Vision dataset readiness metrics (images, ground-truth bounding boxes, and student pins).",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]

    def call_tool(self, name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute an MCP tool by name and return structured content."""
        arguments = arguments or {}

        if name == "sentinel_evaluate_image":
            file_path = arguments.get("file_path")
            if file_path:
                with open(file_path, "rb") as f:
                    img_bytes = f.read()
            else:
                w = int(arguments.get("width", 1600))
                h = int(arguments.get("height", 1200))
                img = Image.new("RGB", (w, h), color=(128, 128, 128))
                pixels = img.load()
                for x in range(0, min(w, 200), 4):
                    for y in range(0, min(h, 200), 4):
                        pixels[x, y] = (220, 220, 220)
                buf = io.BytesIO()
                img.save(buf, format="JPEG")
                img_bytes = buf.getvalue()

            optics = audit_image_optics(img_bytes)
            overall_score = int((optics.get("brightness_score", 85) + optics.get("contrast_score", 85)) / 2)
            report = {
                "overall_score": overall_score,
                "status": "passed" if overall_score >= 75 else "advisory",
                "optics": optics
            }
            return {
                "content": [{"type": "text", "text": json.dumps(report, indent=2)}],
                "structuredContent": report,
                "isError": False
            }

        elif name == "curriculum_cohort_intelligence":
            with app.app_context():
                attempts = AssessmentAttempt.query.order_by(AssessmentAttempt.created_at.desc()).limit(200).all()
                specimens = Wall.query.filter_by(is_skill_assessment=True).all()
                walls_map = {s.id: s for s in specimens}
                intel = analyze_cohort_intelligence(attempts, walls_map)
                return {
                    "content": [{"type": "text", "text": json.dumps(intel, indent=2)}],
                    "structuredContent": intel,
                    "isError": False
                }

        elif name == "list_skill_specimens":
            with app.app_context():
                query = Wall.query.filter_by(is_skill_assessment=True, is_published=True)
                diff = arguments.get("difficulty")
                if diff:
                    query = query.filter_by(difficulty=diff.lower())
                limit = int(arguments.get("limit", 10))
                walls = query.limit(limit).all()
                items = []
                for w in walls:
                    d_count = Defect.query.filter_by(wall_id=w.id).count()
                    items.append({
                        "slug": w.slug,
                        "title": w.title,
                        "wall_type": w.wall_type,
                        "difficulty": w.difficulty,
                        "defect_count": d_count
                    })
                payload = {"count": len(items), "specimens": items}
                return {
                    "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
                    "structuredContent": payload,
                    "isError": False
                }

        elif name == "export_coco_dataset_stats":
            with app.app_context():
                total_specimens = Wall.query.filter_by(is_skill_assessment=True).count()
                total_defects = Defect.query.count()
                total_attempts = AssessmentAttempt.query.count()
                stats = {
                    "format": "COCO 1.0 JSON (CVAT / YOLOv8 Compatible)",
                    "total_annotated_images": total_specimens,
                    "expert_ground_truth_boxes": total_defects,
                    "crowdsourced_student_attempts": total_attempts,
                    "export_endpoint": "/api/skill-assessment/export-coco"
                }
                return {
                    "content": [{"type": "text", "text": json.dumps(stats, indent=2)}],
                    "structuredContent": stats,
                    "isError": False
                }

        return {
            "content": [{"type": "text", "text": f"Unknown MCP tool: {name}"}],
            "isError": True
        }

    def handle_jsonrpc(self, request_obj: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a single JSON-RPC 2.0 request message."""
        req_id = request_obj.get("id")
        method = request_obj.get("method", "")
        params = request_obj.get("params") or {}

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": self.SERVER_INFO["protocolVersion"],
                    "serverInfo": self.SERVER_INFO,
                    "capabilities": {"tools": {}}
                }
            }
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.list_tools()}
            }
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments") or {}
            result = self.call_tool(tool_name, tool_args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }


def run_self_test() -> int:
    """Verify MCP Server tool discovery and execution for CI/CD pipelines."""
    server = WallInspectorMCPServer()
    tools = server.list_tools()
    assert len(tools) == 4, f"Expected 4 MCP tools, got {len(tools)}"
    sentinel_res = server.call_tool("sentinel_evaluate_image", {"width": 1600, "height": 1200})
    assert not sentinel_res["isError"]
    intel_res = server.call_tool("curriculum_cohort_intelligence", {})
    assert not intel_res["isError"]
    print(f"✅ MCP Server Self-Test Passed ({len(tools)} tools verified: {[t['name'] for t in tools]})")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(run_self_test())

    # Standard MCP stdio JSON-RPC loop
    mcp_server = WallInspectorMCPServer()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = mcp_server.handle_jsonrpc(req)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as exc:
            err_resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()
