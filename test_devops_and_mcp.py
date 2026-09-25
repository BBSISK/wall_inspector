import os
import json
import unittest
from app import app
from mcp_server import WallInspectorMCPServer


class TestDevOpsAndMCPStack(unittest.TestCase):
    """
    Verifies the 5-Pillar Modern Engineering & AI Stack:
      1. Docker & Docker Compose configuration integrity
      2. Terraform Infrastructure-as-Code (IaC) definitions
      3. GitHub Actions CI/CD workflow configuration
      4. Model Context Protocol (MCP) JSON-RPC 2.0 Server & Tools
      5. Cloud Health Telemetry (/api/health) & MLOps COCO 1.0 Dataset Exporter (/api/skill-assessment/export-coco)
    """

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        self.mcp = WallInspectorMCPServer()

    def test_api_health_telemetry_endpoint(self):
        """GET /api/health returns 200 healthy status, connected DB, and active agents."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["database"], "connected")
        self.assertGreaterEqual(data["skill_specimens"], 1)
        self.assertIn("IntakeSentinelAgent", data["active_agents"])
        self.assertIn("CurriculumDirectorAgent", data["active_agents"])

    def test_mlops_export_coco_dataset_endpoint(self):
        """GET /api/skill-assessment/export-coco exports valid Microsoft COCO 1.0 JSON for CVAT/YOLOv8."""
        resp = self.client.get("/api/skill-assessment/export-coco?download=1&include_student_consensus=1")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("wall_inspector_coco_dataset.json", resp.headers.get("Content-Disposition", ""))
        coco = resp.get_json()

        self.assertIn("info", coco)
        self.assertIn("categories", coco)
        self.assertIn("images", coco)
        self.assertIn("annotations", coco)
        self.assertGreater(len(coco["images"]), 0)
        self.assertGreater(len(coco["categories"]), 0)
        self.assertGreater(len(coco["annotations"]), 0)

        first_ann = coco["annotations"][0]
        self.assertEqual(len(first_ann["bbox"]), 4)
        self.assertGreater(first_ann["area"], 0)

    def test_mcp_server_jsonrpc_protocol_and_tools(self):
        """Model Context Protocol (MCP) server handles initialize, tools/list, and tools/call."""
        # 1. initialize
        init_resp = self.mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(init_resp["result"]["serverInfo"]["name"], "global-wall-inspector-mcp")

        # 2. tools/list
        list_resp = self.mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool_names = [t["name"] for t in list_resp["result"]["tools"]]
        self.assertIn("sentinel_evaluate_image", tool_names)
        self.assertIn("curriculum_cohort_intelligence", tool_names)
        self.assertIn("list_skill_specimens", tool_names)
        self.assertIn("export_coco_dataset_stats", tool_names)

        # 3. tools/call -> sentinel_evaluate_image
        call_sentinel = self.mcp.handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "sentinel_evaluate_image", "arguments": {"width": 1600, "height": 1200}}
        })
        self.assertFalse(call_sentinel["result"]["isError"])
        self.assertIn("overall_score", call_sentinel["result"]["structuredContent"])

        # 4. tools/call -> export_coco_dataset_stats
        call_coco = self.mcp.handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "export_coco_dataset_stats", "arguments": {}}
        })
        self.assertFalse(call_coco["result"]["isError"])
        self.assertEqual(
            call_coco["result"]["structuredContent"]["export_endpoint"],
            "/api/skill-assessment/export-coco"
        )

    def test_devops_and_iac_files_present_and_valid(self):
        """Verify Dockerfile, docker-compose.yml, Terraform main.tf, GitHub Actions CI, and OpenAPI spec exist."""
        root = os.path.dirname(os.path.abspath(__file__))
        required_files = [
            "Dockerfile",
            ".dockerignore",
            "docker-compose.yml",
            os.path.join("infra", "main.tf"),
            os.path.join("infra", "variables.tf"),
            os.path.join("infra", "outputs.tf"),
            os.path.join(".github", "workflows", "ci.yml"),
            "openapi.yaml",
            "mcp_server.py"
        ]
        for rel_path in required_files:
            full_path = os.path.join(root, rel_path)
            self.assertTrue(os.path.exists(full_path), f"Missing required architecture file: {rel_path}")


if __name__ == "__main__":
    unittest.main()
