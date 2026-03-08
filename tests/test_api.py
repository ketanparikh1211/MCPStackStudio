import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from devdash.api import create_app
from devdash.service import ScanService
from devdash.store import SnapshotStore

SAMPLE_IDES = [
    {
        "name": "VS Code",
        "path": "/Applications/Visual Studio Code.app",
        "version": "1.99.0",
        "running": True,
        "icon": "vscode",
        "type": "ide",
    }
]

SAMPLE_LLMS = [
    {
        "name": "Claude CLI",
        "path": "/usr/local/bin/claude",
        "version": "0.9.1",
        "status": "installed",
        "icon": "claude",
        "type": "cli",
    }
]

SAMPLE_MCP = [
    {
        "name": "Global",
        "path": "/tmp/global.json",
        "key": "mcpServers",
        "exists": True,
        "scope": "global",
        "error": None,
        "serverCount": 1,
        "servers": [
            {
                "name": "search",
                "command": "python3",
                "args": ["-m", "http.server"],
                "env": [],
                "scope": "global",
            }
        ],
    },
    {
        "name": "Project",
        "path": "/tmp/project/.cursor/mcp.json",
        "key": "mcpServers",
        "exists": True,
        "scope": "project",
        "error": None,
        "serverCount": 1,
        "servers": [
            {
                "name": "search",
                "command": "/definitely/missing/binary",
                "args": [],
                "env": [],
                "scope": "project",
                "project": "/tmp/project",
            }
        ],
    },
    {
        "name": "Broken",
        "path": "/tmp/broken.json",
        "key": "mcpServers",
        "exists": True,
        "scope": "global",
        "error": "Invalid JSON: expected '}'",
        "serverCount": 0,
        "servers": [],
    },
    {
        "name": "BadCommand",
        "path": "/tmp/empty.json",
        "key": "mcpServers",
        "exists": True,
        "scope": "global",
        "error": None,
        "serverCount": 1,
        "servers": [
            {
                "name": "bad",
                "command": "",
                "args": [],
                "env": [],
                "scope": "global",
            }
        ],
    },
]


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tempdir.name) / "dashboard.sqlite3"
        self.service = ScanService(SnapshotStore(str(db_path)))
        self.index_path = Path(__file__).resolve().parent.parent / "index.html"
        self.project_mcp_path = Path(self.tempdir.name) / "project" / ".cursor" / "mcp.json"
        self.project_mcp_path.parent.mkdir(parents=True, exist_ok=True)
        self.project_mcp_path.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "alpha": {
                            "command": "node",
                            "args": ["server.js"],
                            "env": {"TOKEN": "secret"},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def _client(self, require_token=False, token=""):
        app = create_app(
            service=self.service,
            index_path=self.index_path,
            require_token_for_remote=require_token,
            access_token=token,
        )
        return TestClient(app)

    def _patched_detectors(self):
        stack = ExitStack()
        stack.enter_context(patch("devdash.detector.detect_ides", return_value=SAMPLE_IDES))
        stack.enter_context(patch("devdash.detector.detect_llms", return_value=SAMPLE_LLMS))
        stack.enter_context(patch("devdash.detector.detect_mcp", return_value=SAMPLE_MCP))
        return stack

    def _patched_detectors_with_local_mcp(self):
        local_mcp = [
            {
                "name": "Project Local",
                "path": str(self.project_mcp_path),
                "key": "mcpServers",
                "exists": True,
                "scope": "project",
                "error": None,
                "serverCount": 1,
                "servers": [
                    {
                        "name": "alpha",
                        "command": "node",
                        "args": ["server.js"],
                        "env": ["TOKEN"],
                        "scope": "project",
                        "project": str(self.project_mcp_path.parent.parent),
                    }
                ],
            }
        ]
        stack = ExitStack()
        stack.enter_context(patch("devdash.detector.detect_ides", return_value=SAMPLE_IDES))
        stack.enter_context(patch("devdash.detector.detect_llms", return_value=SAMPLE_LLMS))
        stack.enter_context(patch("devdash.detector.detect_mcp", return_value=local_mcp))
        return stack

    def test_all_scan_issues_history_and_reports(self):
        with self._patched_detectors():
            with self._client() as client:
                scan_resp = client.get("/api/scan")
                self.assertEqual(scan_resp.status_code, 200)
                scan_id = scan_resp.json()["scan_id"]

                all_resp = client.get("/api/all")
                self.assertEqual(all_resp.status_code, 200)
                all_payload = all_resp.json()
                self.assertEqual(all_payload["scan_id"], scan_id)
                self.assertIn("issues", all_payload)
                self.assertIn("issues_summary", all_payload)
                self.assertIn("drift", all_payload)

                issues_resp = client.get("/api/issues", params={"severity": "critical"})
                self.assertEqual(issues_resp.status_code, 200)
                issues_payload = issues_resp.json()
                self.assertGreaterEqual(issues_payload["count"], 1)
                self.assertTrue(
                    all(issue["severity"] == "critical" for issue in issues_payload["issues"])
                )

                history_resp = client.get("/api/history", params={"limit": 10})
                self.assertEqual(history_resp.status_code, 200)
                history_items = history_resp.json()["items"]
                self.assertEqual(len(history_items), 1)

                md_resp = client.get("/api/report.md", params={"scan_id": scan_id})
                self.assertEqual(md_resp.status_code, 200)
                self.assertIn("# MCPStackStudio Scan Report", md_resp.text)

                json_resp = client.get("/api/report.json", params={"scan_id": scan_id})
                self.assertEqual(json_resp.status_code, 200)
                self.assertEqual(json_resp.json()["scan_id"], scan_id)

    def test_refresh_query_forces_scan(self):
        with self._patched_detectors():
            with self._client() as client:
                first = client.get("/api/all", params={"refresh": True})
                second = client.get("/api/all", params={"refresh": True})

                self.assertEqual(first.status_code, 200)
                self.assertEqual(second.status_code, 200)
                self.assertGreaterEqual(second.json()["scan_id"], first.json()["scan_id"])

    def test_remote_access_requires_token(self):
        with self._client(require_token=True, token="secret-token") as client:
            unauthorized = client.get("/health")
            self.assertEqual(unauthorized.status_code, 401)

            authorized = client.get("/health", headers={"X-DevDash-Token": "secret-token"})
            self.assertEqual(authorized.status_code, 200)
            self.assertEqual(authorized.json()["status"], "ok")

    def test_mcp_targets_and_crud_endpoints(self):
        with self._patched_detectors_with_local_mcp():
            with self._client() as client:
                targets_resp = client.get("/api/mcp/targets")
                self.assertEqual(targets_resp.status_code, 200)
                targets_payload = targets_resp.json()
                self.assertEqual(len(targets_payload["targets"]), 1)
                self.assertEqual(targets_payload["targets"][0]["scope"], "project")
                self.assertTrue(targets_payload["targets"][0]["is_default"])

                add_resp = client.post(
                    "/api/mcp/servers",
                    json={
                        "target_path": str(self.project_mcp_path),
                        "target_key": "mcpServers",
                        "name": "beta",
                        "command": "npx",
                        "args": ["beta-server"],
                        "env": {"API_KEY": "k"},
                    },
                )
                self.assertEqual(add_resp.status_code, 200)
                self.assertTrue(add_resp.json()["ok"])
                self.assertIn("scan_id", add_resp.json())

                update_resp = client.put(
                    "/api/mcp/servers",
                    json={
                        "target_path": str(self.project_mcp_path),
                        "target_key": "mcpServers",
                        "old_name": "beta",
                        "name": "beta2",
                        "command": "node",
                        "args": ["runner.js"],
                        "env": {},
                    },
                )
                self.assertEqual(update_resp.status_code, 200)
                self.assertEqual(update_resp.json()["server_name"], "beta2")

                delete_resp = client.request(
                    "DELETE",
                    "/api/mcp/servers",
                    json={
                        "target_path": str(self.project_mcp_path),
                        "target_key": "mcpServers",
                        "name": "beta2",
                    },
                )
                self.assertEqual(delete_resp.status_code, 200)
                self.assertTrue(delete_resp.json()["ok"])

                final_data = json.loads(self.project_mcp_path.read_text(encoding="utf-8"))
                self.assertIn("alpha", final_data["mcpServers"])
                self.assertNotIn("beta2", final_data["mcpServers"])

    def test_catalog_endpoint_uses_cache_and_refresh(self):
        payload = {
            "source": "official-registry",
            "days": 14,
            "updated_since": "2026-02-20T00:00:00Z",
            "items": [
                {
                    "server_name": "io.github.acme/demo",
                    "title": "Demo",
                    "description": "Demo server",
                    "repo_url": "https://github.com/acme/demo",
                    "website_url": "",
                    "icon_url": "",
                    "updated_at": "2026-03-07T00:00:00Z",
                    "status": "active",
                }
            ],
            "count": 1,
            "next_cursor": "",
            "fetched_at": "2026-03-08T00:00:00+00:00",
        }

        with patch.object(self.service.registry_client, "fetch_new_servers", return_value=payload) as fetch_mock:
            with self._client() as client:
                first = client.get("/api/mcp/catalog/new")
                self.assertEqual(first.status_code, 200)
                self.assertEqual(first.json()["count"], 1)
                self.assertEqual(fetch_mock.call_count, 1)

                second = client.get("/api/mcp/catalog/new")
                self.assertEqual(second.status_code, 200)
                self.assertEqual(second.json()["cache"], "hit")
                self.assertEqual(fetch_mock.call_count, 1)

                third = client.get("/api/mcp/catalog/new", params={"refresh": True})
                self.assertEqual(third.status_code, 200)
                self.assertEqual(fetch_mock.call_count, 2)

                fourth = client.get("/api/mcp/catalog/new", params={"mode": "all", "limit": 100})
                self.assertEqual(fourth.status_code, 200)
                self.assertEqual(fourth.json()["count"], 1)


if __name__ == "__main__":
    unittest.main()
