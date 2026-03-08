import json
import unittest
from unittest.mock import patch

import httpx

from devdash.registry import RegistryClient


class _FakeResponse:
    def __init__(self, json_payload=None, text_payload="", raise_error=None):
        self._json_payload = json_payload
        self.text = text_payload
        self._raise_error = raise_error

    def raise_for_status(self):
        if self._raise_error:
            raise self._raise_error

    def json(self):
        if self._json_payload is None:
            raise ValueError("No JSON payload")
        return self._json_payload


class _FakeHttpxClient:
    def __init__(self, handler, calls):
        self._handler = handler
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, params=None, headers=None):
        entry = {
            "url": url,
            "params": dict(params or {}),
            "headers": dict(headers or {}),
        }
        self._calls.append(entry)
        return self._handler(url, dict(params or {}), dict(headers or {}))


class RegistryClientTests(unittest.TestCase):
    def _github_html(self, metadata, servers):
        embedded = {
            "payload": {
                "mcpRegistryRoute": {
                    "serversData": {
                        "metadata": metadata,
                        "servers": servers,
                    }
                }
            }
        }
        return (
            '<html><body><script type="application/json" data-target="react-app.embeddedData">'
            + json.dumps(embedded)
            + "</script></body></html>"
        )

    def test_fetch_new_servers_prefers_github_source(self):
        html = self._github_html(
            {"total_pages": 3, "total": 81},
            [
                {
                    "name": "io.github.acme/demo",
                    "display_name": "Demo Server",
                    "description": "Demo description",
                    "url": "https://github.com/acme/demo",
                    "owner_avatar_url": "https://avatars.githubusercontent.com/u/1?v=4",
                    "updated_at": "2999-01-01T00:00:00Z",
                }
            ],
        )

        calls = []
        official_payload = {
            "servers": [
                {
                    "server": {
                        "name": "io.github.acme/extra",
                        "title": "Extra",
                        "description": "Extra official server",
                        "repository": {"url": "https://github.com/acme/extra"},
                        "icons": [{"src": "https://img.example/extra.png"}],
                    },
                    "_meta": {
                        "io.modelcontextprotocol.registry/official": {
                            "status": "active",
                            "updatedAt": "2998-01-01T00:00:00Z",
                        }
                    },
                }
            ],
            "metadata": {"nextCursor": ""},
        }

        def _handler(url, params, headers):
            if "github.com/mcp" in url:
                return _FakeResponse(text_payload=html)
            if "registry.modelcontextprotocol.io" in url:
                return _FakeResponse(json_payload=official_payload)
            raise AssertionError(f"Unexpected URL: {url}")

        with patch("devdash.registry.httpx.Client", side_effect=lambda *a, **k: _FakeHttpxClient(_handler, calls)):
            result = RegistryClient().fetch_new_servers(days=14, limit=30)

        self.assertEqual(result["source"], "github-mcp+official-registry")
        self.assertFalse(result["fallback_used"])
        self.assertTrue(result["official_included"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["items"][0]["server_name"], "io.github.acme/demo")
        self.assertEqual(result["items"][1]["server_name"], "io.github.acme/extra")
        self.assertTrue(result["items"][0]["icon_url"].startswith("https://avatars.githubusercontent.com/"))
        self.assertEqual(result["next_cursor"], "2")
        self.assertEqual(len(calls), 2)
        self.assertIn("page", calls[0]["params"])

    def test_fetch_all_mode_paginates_github_pages(self):
        page1 = self._github_html(
            {"total_pages": 3, "total": 81},
            [
                {
                    "name": "io.github.acme/a",
                    "display_name": "A",
                    "description": "A",
                    "url": "https://github.com/acme/a",
                    "owner_avatar_url": "https://avatars.githubusercontent.com/u/1?v=4",
                    "updated_at": "2020-01-01T00:00:00Z",
                }
            ],
        )
        page2 = self._github_html(
            {"total_pages": 3, "total": 81},
            [
                {
                    "name": "io.github.acme/b",
                    "display_name": "B",
                    "description": "B",
                    "url": "https://github.com/acme/b",
                    "owner_avatar_url": "https://avatars.githubusercontent.com/u/2?v=4",
                    "updated_at": "2020-01-02T00:00:00Z",
                }
            ],
        )

        calls = []
        official_payload = {
            "servers": [
                {
                    "server": {
                        "name": "io.github.acme/older",
                        "title": "Older",
                        "description": "Older fallback entry",
                        "repository": {"url": "https://github.com/acme/older"},
                        "icons": [{"src": "https://img.example/older.png"}],
                    },
                    "_meta": {
                        "io.modelcontextprotocol.registry/official": {
                            "status": "active",
                            "updatedAt": "2010-01-01T00:00:00Z",
                        }
                    },
                }
            ],
            "metadata": {"nextCursor": ""},
        }

        def _handler(url, params, headers):
            if "github.com/mcp" in url:
                page = int(params.get("page", 1) or 1)
                if page == 1:
                    return _FakeResponse(text_payload=page1)
                if page == 2:
                    return _FakeResponse(text_payload=page2)
                return _FakeResponse(text_payload=self._github_html({"total_pages": 3, "total": 81}, []))
            if "registry.modelcontextprotocol.io" in url:
                return _FakeResponse(json_payload=official_payload)
            raise AssertionError(f"Unexpected URL: {url}")

        with patch("devdash.registry.httpx.Client", side_effect=lambda *a, **k: _FakeHttpxClient(_handler, calls)):
            result = RegistryClient().fetch_new_servers(days=14, limit=2, mode="all")

        self.assertEqual(result["source"], "github-mcp+official-registry")
        self.assertEqual(result["mode"], "all")
        self.assertTrue(result["official_included"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["total"], 81)
        self.assertEqual(result["items"][0]["server_name"], "io.github.acme/b")
        self.assertEqual(result["items"][1]["server_name"], "io.github.acme/a")
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0]["params"].get("page"), 1)
        self.assertEqual(calls[1]["params"].get("page"), 2)

    def test_fetch_new_servers_falls_back_to_official_registry(self):
        official_payload = {
            "servers": [
                {
                    "server": {
                        "name": "io.github.acme/official",
                        "title": "Official",
                        "description": "From official",
                        "repository": {"url": "https://github.com/acme/official"},
                        "icons": [{"src": "https://img.example/icon.png"}],
                    },
                    "_meta": {
                        "io.modelcontextprotocol.registry/official": {
                            "status": "active",
                            "updatedAt": "2999-01-02T00:00:00Z",
                        }
                    },
                }
            ],
            "metadata": {"nextCursor": "cursor123"},
        }

        calls = []

        def _handler(url, params, headers):
            if "github.com/mcp" in url:
                return _FakeResponse(raise_error=httpx.HTTPError("github down"))
            if "registry.modelcontextprotocol.io" in url:
                return _FakeResponse(json_payload=official_payload)
            raise AssertionError(f"Unexpected URL: {url}")

        with patch("devdash.registry.httpx.Client", side_effect=lambda *a, **k: _FakeHttpxClient(_handler, calls)):
            result = RegistryClient().fetch_new_servers(days=14, limit=30)

        self.assertEqual(result["source"], "official-registry")
        self.assertTrue(result["fallback_used"])
        self.assertIn("GitHub MCP source failed", result.get("warning", ""))
        self.assertTrue(result["official_included"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["server_name"], "io.github.acme/official")
        self.assertEqual(result["next_cursor"], "cursor123")
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
