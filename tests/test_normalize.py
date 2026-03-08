import unittest

from devdash.normalize import normalize_detected_items, normalize_mcp_locations


class NormalizeTests(unittest.TestCase):
    def test_normalize_detected_items_sorts_and_maps(self):
        raw = [
            {"name": "Zed", "path": "/Applications/Zed.app", "version": "1.0", "icon": "zed", "type": "ide"},
            {"name": "Cursor", "path": "/Applications/Cursor.app", "version": "2.0", "icon": "cursor", "type": "ide"},
        ]

        items = normalize_detected_items(raw, category="ide")

        self.assertEqual(items[0].name, "Cursor")
        self.assertEqual(items[1].name, "Zed")
        self.assertEqual(items[0].category, "ide")
        self.assertEqual(items[0].item_type, "ide")

    def test_normalize_mcp_locations_flattens_servers(self):
        raw = [
            {
                "name": "Cursor",
                "path": "/tmp/mcp.json",
                "exists": True,
                "serverCount": 1,
                "error": None,
                "scope": "global",
                "servers": [
                    {
                        "name": "filesystem",
                        "command": "python3",
                        "args": ["-m", "http.server"],
                        "env": {"API_KEY": "x"},
                    }
                ],
            }
        ]

        locations, servers = normalize_mcp_locations(raw)

        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0].server_count, 1)
        self.assertEqual(len(servers), 1)
        self.assertEqual(servers[0].name, "filesystem")
        self.assertEqual(servers[0].env_keys, ["API_KEY"])
        self.assertEqual(servers[0].scope, "global")


if __name__ == "__main__":
    unittest.main()
