import json
import tempfile
import unittest
from pathlib import Path

from devdash.mcp_config import McpConfigError, McpConfigManager


class McpConfigManagerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.manager = McpConfigManager()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_add_preserves_key_shape_for_supported_variants(self):
        for key in ("mcpServers", "servers", "context_servers"):
            config_path = self.base / f"{key}.json"
            config_path.write_text(
                json.dumps(
                    {
                        key: {
                            "existing": {
                                "command": "node",
                                "args": ["existing.js"],
                            }
                        },
                        "keep": {"foo": "bar"},
                    }
                ),
                encoding="utf-8",
            )

            result = self.manager.add_server(
                target_path=str(config_path),
                target_key=None,
                name="new-server",
                command="python3",
                args=["-m", "http.server"],
                env={"TOKEN": "abc"},
            )

            self.assertEqual(result.target_key, key)
            self.assertTrue(result.backup_path)
            self.assertTrue(Path(result.backup_path).exists())

            payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertIn("existing", payload[key])
            self.assertIn("new-server", payload[key])
            self.assertEqual(payload["keep"]["foo"], "bar")

    def test_create_new_file_uses_preferred_key(self):
        config_path = self.base / "project" / ".vscode" / "mcp.json"

        result = self.manager.add_server(
            target_path=str(config_path),
            target_key="servers",
            name="demo",
            command="npx",
            args=["demo-mcp"],
            env={},
        )

        self.assertEqual(result.target_key, "servers")
        self.assertEqual(result.backup_path, "")
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertIn("demo", payload["servers"])

    def test_update_preserves_existing_env_when_new_env_is_empty(self):
        config_path = self.base / "mcp.json"
        config_path.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "alpha": {
                            "command": "node",
                            "args": ["alpha.js"],
                            "env": {"API_KEY": "keep-me"},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        self.manager.update_server(
            target_path=str(config_path),
            target_key="mcpServers",
            old_name="alpha",
            name="alpha",
            command="node",
            args=["runner.js"],
            env={},
        )

        payload = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["mcpServers"]["alpha"]["args"], ["runner.js"])
        self.assertEqual(payload["mcpServers"]["alpha"]["env"]["API_KEY"], "keep-me")

    def test_invalid_json_and_delete_missing_raise_errors(self):
        broken = self.base / "broken.json"
        broken.write_text("{ bad json", encoding="utf-8")

        with self.assertRaises(McpConfigError):
            self.manager.add_server(
                target_path=str(broken),
                target_key="mcpServers",
                name="demo",
                command="python3",
                args=[],
                env={},
            )

        empty = self.base / "empty.json"
        empty.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
        with self.assertRaises(McpConfigError):
            self.manager.delete_server(
                target_path=str(empty),
                target_key="mcpServers",
                name="ghost",
            )


if __name__ == "__main__":
    unittest.main()
