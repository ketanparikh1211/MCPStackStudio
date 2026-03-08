import json
import unittest
from pathlib import Path

from devdash.normalize import normalize_mcp_locations
from devdash.rules import evaluate_issues

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(name: str):
    with open(FIXTURES / name, "r", encoding="utf-8") as handle:
        return json.load(handle)


class RegressionRuleTests(unittest.TestCase):
    def test_valid_single_config(self):
        payload = load_json("valid_single.json")
        raw_locations = [
            {
                "name": "Valid",
                "path": str(FIXTURES / "valid_single.json"),
                "exists": True,
                "scope": "global",
                "error": None,
                "servers": [
                    {
                        "name": "filesystem",
                        "command": payload["mcpServers"]["filesystem"]["command"],
                        "args": payload["mcpServers"]["filesystem"]["args"],
                        "env": {},
                        "scope": "global",
                    }
                ],
            }
        ]

        locations, servers = normalize_mcp_locations(raw_locations)
        issues = evaluate_issues(locations, servers)
        self.assertEqual(issues, [])

    def test_duplicate_and_conflict(self):
        g = load_json("global_conflict_global.json")
        p = load_json("global_conflict_project.json")

        raw_locations = [
            {
                "name": "Global",
                "path": str(FIXTURES / "global_conflict_global.json"),
                "exists": True,
                "scope": "global",
                "error": None,
                "servers": [{"name": "search", **g["mcpServers"]["search"], "env": {}, "scope": "global"}],
            },
            {
                "name": "Project",
                "path": str(FIXTURES / "global_conflict_project.json"),
                "exists": True,
                "scope": "project",
                "error": None,
                "servers": [
                    {
                        "name": "search",
                        **p["mcpServers"]["search"],
                        "env": {},
                        "scope": "project",
                        "project": "/tmp/project",
                    }
                ],
            },
        ]

        locations, servers = normalize_mcp_locations(raw_locations)
        issues = evaluate_issues(locations, servers)
        issue_types = {issue.issue_type for issue in issues}

        self.assertIn("duplicate_server_name", issue_types)
        self.assertIn("global_project_conflict", issue_types)

    def test_invalid_json_file(self):
        invalid_path = FIXTURES / "invalid_json.json"
        with open(invalid_path, "r", encoding="utf-8") as handle:
            try:
                json.load(handle)
                self.fail("Fixture should be invalid JSON")
            except json.JSONDecodeError as exc:
                parse_error = f"Invalid JSON: {exc}"

        raw_locations = [
            {
                "name": "Invalid",
                "path": str(invalid_path),
                "exists": True,
                "scope": "global",
                "error": parse_error,
                "servers": [],
            }
        ]
        locations, servers = normalize_mcp_locations(raw_locations)
        issues = evaluate_issues(locations, servers)
        self.assertTrue(any(issue.issue_type == "mcp_config_parse_error" for issue in issues))

    def test_missing_binary(self):
        payload = load_json("missing_binary.json")
        raw_locations = [
            {
                "name": "Missing",
                "path": str(FIXTURES / "missing_binary.json"),
                "exists": True,
                "scope": "global",
                "error": None,
                "servers": [
                    {
                        "name": "ghost",
                        "command": payload["mcpServers"]["ghost"]["command"],
                        "args": [],
                        "env": {},
                        "scope": "global",
                    }
                ],
            }
        ]

        locations, servers = normalize_mcp_locations(raw_locations)
        issues = evaluate_issues(locations, servers)
        self.assertTrue(any(issue.issue_type == "missing_command_binary" for issue in issues))

    def test_empty_command(self):
        payload = load_json("empty_command.json")
        raw_locations = [
            {
                "name": "Empty",
                "path": str(FIXTURES / "empty_command.json"),
                "exists": True,
                "scope": "global",
                "error": None,
                "servers": [
                    {
                        "name": "bad",
                        "command": payload["mcpServers"]["bad"]["command"],
                        "args": [],
                        "env": {},
                        "scope": "global",
                    }
                ],
            }
        ]

        locations, servers = normalize_mcp_locations(raw_locations)
        issues = evaluate_issues(locations, servers)
        self.assertTrue(any(issue.issue_type == "invalid_command" for issue in issues))


if __name__ == "__main__":
    unittest.main()
