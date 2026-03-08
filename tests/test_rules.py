import unittest

from devdash.models import McpConfigLocation, McpServer
from devdash.rules import evaluate_issues


class RuleEngineTests(unittest.TestCase):
    def test_detects_duplicate_and_global_project_conflicts(self):
        locations = [
            McpConfigLocation(name="Global", path="/tmp/g.json", exists=True, scope="global"),
            McpConfigLocation(name="Project", path="/tmp/p.json", exists=True, scope="project"),
        ]

        servers = [
            McpServer(
                name="search",
                command="python3",
                args=["-m", "http.server"],
                env_keys=[],
                source_name="Global",
                config_path="/tmp/g.json",
                scope="global",
            ),
            McpServer(
                name="search",
                command="node",
                args=["server.js"],
                env_keys=[],
                source_name="Project",
                config_path="/tmp/p.json",
                scope="project",
                project_path="/tmp/project",
            ),
        ]

        issues = evaluate_issues(locations, servers)
        issue_types = {issue.issue_type for issue in issues}

        self.assertIn("duplicate_server_name", issue_types)
        self.assertIn("global_project_conflict", issue_types)

    def test_detects_parse_error_missing_binary_and_empty_command(self):
        locations = [
            McpConfigLocation(
                name="Broken",
                path="/tmp/broken.json",
                exists=True,
                scope="global",
                error="Invalid JSON",
            )
        ]

        servers = [
            McpServer(
                name="ghost",
                command="/definitely/missing/binary",
                args=[],
                env_keys=[],
                source_name="Broken",
                config_path="/tmp/broken.json",
                scope="global",
            ),
            McpServer(
                name="bad",
                command="",
                args=[],
                env_keys=[],
                source_name="Broken",
                config_path="/tmp/broken.json",
                scope="global",
            ),
        ]

        issues = evaluate_issues(locations, servers)
        issue_types = {issue.issue_type for issue in issues}

        self.assertIn("mcp_config_parse_error", issue_types)
        self.assertIn("missing_command_binary", issue_types)
        self.assertIn("invalid_command", issue_types)


if __name__ == "__main__":
    unittest.main()
