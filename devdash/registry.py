"""MCP catalog client with GitHub-first source and official API fallback."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .utils import utc_now_iso

REGISTRY_BASE_URL = "https://registry.modelcontextprotocol.io"
GITHUB_MCP_URL = "https://github.com/mcp"


class RegistryClient:
    def __init__(self, base_url: str = REGISTRY_BASE_URL, timeout_seconds: float = 12.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _updated_since(days: int) -> str:
        safe_days = max(1, min(days, 90))
        dt = datetime.now(timezone.utc) - timedelta(days=safe_days)
        return dt.isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse_iso(value: str) -> datetime:
        if not value:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _is_recent(cls, updated_at: str, updated_since: str) -> bool:
        try:
            return cls._parse_iso(updated_at) >= cls._parse_iso(updated_since)
        except Exception:
            return False

    @staticmethod
    def _dedupe_latest(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        latest_by_name: Dict[str, Dict[str, Any]] = {}

        for item in items:
            name = str(item.get("server_name", "") or "")
            if not name:
                continue

            existing = latest_by_name.get(name)
            if not existing:
                latest_by_name[name] = item
                continue

            if str(item.get("updated_at", "")) > str(existing.get("updated_at", "")):
                latest_by_name[name] = item

        return sorted(
            latest_by_name.values(),
            key=lambda entry: str(entry.get("updated_at", "")),
            reverse=True,
        )

    @staticmethod
    def _repo_slug_from_url(url: str) -> str:
        value = str(url or "").strip()
        if not value:
            return ""
        match = re.search(r"github\\.com/([^/]+)/([^/#?]+)", value, flags=re.IGNORECASE)
        if not match:
            return ""
        return f"{match.group(1)}/{match.group(2)}".lower()

    @classmethod
    def _canonical_server_key(cls, item: Dict[str, Any]) -> str:
        server_name = str(item.get("server_name", "") or "").strip()
        repo_slug = cls._repo_slug_from_url(str(item.get("repo_url", "") or ""))
        if repo_slug:
            return repo_slug

        lowered = server_name.lower()
        if lowered.startswith("io.github.") and "/" in server_name:
            owner_part, repo_part = server_name.split("/", 1)
            owner = owner_part[len("io.github.") :]
            if owner and repo_part:
                return f"{owner}/{repo_part}".lower()

        return lowered

    @classmethod
    def _merge_catalog_items(
        cls,
        primary: List[Dict[str, Any]],
        secondary: List[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}

        for item in primary:
            key = cls._canonical_server_key(item)
            if not key:
                continue
            merged[key] = dict(item)

        for item in secondary:
            key = cls._canonical_server_key(item)
            if not key:
                continue
            if key not in merged:
                merged[key] = dict(item)
                continue

            current = merged[key]
            for field in ["title", "description", "repo_url", "website_url", "icon_url", "status"]:
                if not current.get(field) and item.get(field):
                    current[field] = item[field]

            if str(item.get("updated_at", "")) > str(current.get("updated_at", "")):
                current["updated_at"] = item.get("updated_at", current.get("updated_at", ""))
                if item.get("description"):
                    current["description"] = item["description"]

        ranked = sorted(
            merged.values(),
            key=lambda entry: str(entry.get("updated_at", "")),
            reverse=True,
        )
        return ranked[: max(1, min(limit, 300))]

    @staticmethod
    def _extract_github_embedded_payload(html: str) -> Dict[str, Any]:
        marker = 'data-target="react-app.embeddedData">'
        start = html.find(marker)
        if start < 0:
            raise ValueError("Embedded MCP payload marker not found on GitHub page")

        start += len(marker)
        end = html.find("</script>", start)
        if end < 0:
            raise ValueError("Embedded MCP payload script closing tag not found")

        raw = html[start:end].strip()
        if not raw:
            raise ValueError("Embedded MCP payload is empty")
        return json.loads(raw)

    @staticmethod
    def _normalize_github_item(entry: Dict[str, Any]) -> Dict[str, Any]:
        name = str(entry.get("name", "") or "")
        title = str(entry.get("display_name", "") or "")
        if not title:
            title = name.split("/")[-1] if name else ""

        return {
            "server_name": name,
            "title": title,
            "description": str(entry.get("description", "") or ""),
            "repo_url": str(entry.get("url", "") or ""),
            "website_url": "",
            "icon_url": str(entry.get("owner_avatar_url", "") or ""),
            "updated_at": str(entry.get("updated_at", "") or str(entry.get("pushed_at", "") or "")),
            "status": "active",
        }

    @staticmethod
    def _normalize_official_item(entry: Dict[str, Any]) -> Dict[str, Any]:
        server = entry.get("server", {}) if isinstance(entry, dict) else {}
        if not isinstance(server, dict):
            server = {}

        meta_root = entry.get("_meta", {}) if isinstance(entry, dict) else {}
        official_meta = {}
        if isinstance(meta_root, dict):
            official_meta = meta_root.get("io.modelcontextprotocol.registry/official", {})
        if not isinstance(official_meta, dict):
            official_meta = {}

        name = str(server.get("name", "") or "")
        title = str(server.get("title", "") or "")
        if not title:
            title = name.split("/")[-1] if name else ""

        repository = server.get("repository", {}) if isinstance(server.get("repository"), dict) else {}
        icons = server.get("icons", []) if isinstance(server.get("icons"), list) else []
        icon_url = ""
        for icon in icons:
            if isinstance(icon, dict) and icon.get("src"):
                icon_url = str(icon.get("src"))
                break

        updated_at = str(
            official_meta.get("updatedAt")
            or official_meta.get("publishedAt")
            or official_meta.get("statusChangedAt")
            or ""
        )

        return {
            "server_name": name,
            "title": title,
            "description": str(server.get("description", "") or ""),
            "repo_url": str(repository.get("url", "") or ""),
            "website_url": str(server.get("websiteUrl", "") or ""),
            "icon_url": icon_url,
            "updated_at": updated_at,
            "status": str(official_meta.get("status", "") or ""),
        }

    def _fetch_github_page(self, client: httpx.Client, page: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        response = client.get(
            GITHUB_MCP_URL,
            params={"page": page},
            headers={
                "Accept": "text/html",
                "User-Agent": "mcpstackstudio/2.0",
            },
        )
        response.raise_for_status()
        payload = self._extract_github_embedded_payload(response.text)

        route = payload.get("payload", {}).get("mcpRegistryRoute", {})
        servers_data = route.get("serversData", {}) if isinstance(route, dict) else {}
        metadata = servers_data.get("metadata", {}) if isinstance(servers_data, dict) else {}
        raw_servers = servers_data.get("servers", []) if isinstance(servers_data, dict) else []
        return [entry for entry in raw_servers if isinstance(entry, dict)], (metadata if isinstance(metadata, dict) else {})

    def _fetch_from_github(self, days: int, limit: int, cursor: str, mode: str) -> Dict[str, Any]:
        safe_limit = max(1, min(limit, 300))
        safe_days = max(1, min(days, 90))
        updated_since = self._updated_since(safe_days)

        page = 1
        if cursor:
            try:
                page = max(1, int(cursor))
            except ValueError:
                page = 1

        total_pages = 1
        total = 0
        collected: List[Dict[str, Any]] = []
        current_page = page

        with httpx.Client(timeout=self.timeout_seconds) as client:
            while len(collected) < safe_limit:
                raw_servers, metadata = self._fetch_github_page(client, current_page)

                try:
                    total_pages = int(metadata.get("total_pages", total_pages) or total_pages)
                except (TypeError, ValueError):
                    pass
                try:
                    total = int(metadata.get("total", total) or total)
                except (TypeError, ValueError):
                    pass

                normalized = [self._normalize_github_item(entry) for entry in raw_servers]
                if mode == "new":
                    normalized = [
                        item for item in normalized if self._is_recent(str(item.get("updated_at", "")), updated_since)
                    ]

                collected.extend(normalized)

                if mode == "new":
                    break
                if current_page >= total_pages:
                    break
                current_page += 1

        deduped = self._dedupe_latest(collected)[:safe_limit]
        next_cursor = str(current_page + 1) if current_page < total_pages else ""

        return {
            "source": "github-mcp",
            "mode": mode,
            "days": safe_days,
            "updated_since": updated_since,
            "items": deduped,
            "count": len(deduped),
            "total": total,
            "next_cursor": next_cursor,
            "fetched_at": utc_now_iso(),
        }

    def _fetch_from_official(self, days: int, limit: int, cursor: str, mode: str) -> Dict[str, Any]:
        safe_limit = max(1, min(limit, 300))
        safe_days = max(1, min(days, 90))
        updated_since = self._updated_since(safe_days)

        params: Dict[str, Any] = {"limit": safe_limit, "version": "latest"}
        if mode == "new":
            params["updated_since"] = updated_since
        if cursor:
            params["cursor"] = cursor

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.get(
                f"{self.base_url}/v0.1/servers",
                params=params,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()

        raw_servers = payload.get("servers", []) if isinstance(payload, dict) else []
        normalized = [
            self._normalize_official_item(entry)
            for entry in raw_servers
            if isinstance(entry, dict)
        ]
        deduped = self._dedupe_latest(normalized)[:safe_limit]

        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        next_cursor = ""
        if isinstance(metadata, dict):
            next_cursor = str(metadata.get("nextCursor", "") or "")

        return {
            "source": "official-registry",
            "mode": mode,
            "days": safe_days,
            "updated_since": updated_since,
            "items": deduped,
            "count": len(deduped),
            "next_cursor": next_cursor,
            "fetched_at": utc_now_iso(),
        }

    def fetch_new_servers(self, days: int = 14, limit: int = 30, cursor: str = "", mode: str = "new") -> Dict[str, Any]:
        safe_mode = "all" if str(mode).lower() == "all" else "new"
        safe_limit = max(1, min(limit, 300))
        github_error: Optional[Exception] = None
        try:
            github_payload = self._fetch_from_github(days=days, limit=safe_limit, cursor=cursor, mode=safe_mode)
        except Exception as exc:
            github_error = exc
            payload = self._fetch_from_official(days=days, limit=safe_limit, cursor=cursor, mode=safe_mode)
            payload["fallback_used"] = True
            payload["warning"] = f"GitHub MCP source failed, used official registry fallback: {github_error}"
            payload["official_included"] = True
            return payload

        try:
            official_payload = self._fetch_from_official(days=days, limit=safe_limit, cursor=cursor, mode=safe_mode)
            merged_items = self._merge_catalog_items(
                github_payload.get("items", []),
                official_payload.get("items", []),
                limit=safe_limit,
            )
            github_payload["items"] = merged_items
            github_payload["count"] = len(merged_items)
            github_payload["source"] = "github-mcp+official-registry"
            github_payload["fallback_used"] = False
            github_payload["official_included"] = True
            return github_payload
        except Exception as exc:
            github_payload["fallback_used"] = False
            github_payload["official_included"] = False
            github_payload["warning"] = f"Official registry supplement failed, using GitHub MCP only: {exc}"
            return github_payload
