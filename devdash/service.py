"""Scan pipeline: detect -> normalize -> rule engine -> persist."""

from __future__ import annotations

import socket
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import detector
from .mcp_config import McpConfigManager
from .models import (
    DetectedItem,
    Issue,
    McpCatalogItem,
    McpConfigLocation,
    McpServer,
    McpServerDeleteMutation,
    McpServerMutation,
    McpServerUpdateMutation,
    McpTarget,
)
from .normalize import normalize_detected_items, normalize_mcp_locations
from .registry import RegistryClient
from .reports import build_json_report, build_markdown_report
from .rules import evaluate_issues, summarize_issues
from .store import SnapshotStore
from .utils import model_to_dict, stable_hash, utc_now_iso


class ScanService:
    REGISTRY_CACHE_TTL_SECONDS = 15 * 60

    def __init__(
        self,
        store: SnapshotStore,
        config_manager: Optional[McpConfigManager] = None,
        registry_client: Optional[RegistryClient] = None,
    ) -> None:
        self.store = store
        self.config_manager = config_manager or McpConfigManager()
        self.registry_client = registry_client or RegistryClient()

    @staticmethod
    def _detected_to_api(item: DetectedItem) -> Dict[str, Any]:
        return {
            "name": item.name,
            "path": item.path,
            "version": item.version,
            "icon": item.icon,
            "type": item.item_type,
            "running": item.running,
            "status": item.status,
            "host": item.host,
        }

    @staticmethod
    def _server_to_api(server: McpServer) -> Dict[str, Any]:
        return {
            "name": server.name,
            "command": server.command,
            "args": list(server.args),
            "env": list(server.env_keys),
            "source": server.source_name,
            "path": server.config_path,
            "scope": server.scope,
            "project": server.project_path,
            "signature": server.signature,
        }

    @classmethod
    def _location_to_api(cls, location: McpConfigLocation) -> Dict[str, Any]:
        return {
            "name": location.name,
            "path": location.path,
            "key": location.key,
            "exists": location.exists,
            "serverCount": location.server_count,
            "error": location.error,
            "scope": location.scope,
            "servers": [cls._server_to_api(server) for server in location.servers],
        }

    @staticmethod
    def _prepare_hash_payload(
        ides: List[DetectedItem],
        llms: List[DetectedItem],
        locations: List[McpConfigLocation],
        servers: List[McpServer],
    ) -> Dict[str, Any]:
        return {
            "ides": [model_to_dict(item) for item in ides],
            "llms": [model_to_dict(item) for item in llms],
            "mcp_locations": [model_to_dict(location) for location in locations],
            "mcp_servers": [model_to_dict(server) for server in servers],
        }

    @staticmethod
    def _issue_to_api(issue: Issue) -> Dict[str, Any]:
        return {
            "issue_id": issue.issue_id,
            "severity": issue.severity,
            "issue_type": issue.issue_type,
            "source": issue.source,
            "message": issue.message,
            "details": model_to_dict(issue.details),
        }

    @staticmethod
    def _server_key(server: Dict[str, Any]) -> str:
        return "|".join(
            [
                str(server.get("name", "")),
                str(server.get("scope", "")),
                str(server.get("signature", "")),
                str(server.get("source", "")),
                str(server.get("project", "")),
            ]
        )

    @staticmethod
    def _issue_key(issue: Dict[str, Any]) -> str:
        return str(issue.get("issue_id", ""))

    @staticmethod
    def _coerce_mcp_key(raw_key: str) -> str:
        if raw_key in {"mcpServers", "servers", "context_servers"}:
            return raw_key
        return "mcpServers"

    @staticmethod
    def _project_path_from_location(location: Dict[str, Any]) -> str:
        for server in location.get("servers", []) or []:
            if isinstance(server, dict) and server.get("project"):
                return str(server.get("project"))
        path = str(location.get("path", "") or "")
        for marker in ["/.cursor/mcp.json", "/.vscode/mcp.json"]:
            if marker in path:
                return path.split(marker)[0]
        return ""

    @staticmethod
    def _cache_age_seconds(fetched_at: str) -> int:
        if not fetched_at:
            return 10**9
        try:
            parsed = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        except ValueError:
            return 10**9
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int((datetime.now(timezone.utc) - parsed).total_seconds())

    def _calculate_drift(
        self,
        previous: Optional[Dict[str, Any]],
        current: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not previous:
            return {}

        prev_servers = {self._server_key(server): server for server in previous.get("mcp_servers", [])}
        curr_servers = {self._server_key(server): server for server in current.get("mcp_servers", [])}

        added_keys = sorted(set(curr_servers) - set(prev_servers))
        removed_keys = sorted(set(prev_servers) - set(curr_servers))

        prev_issues = {self._issue_key(issue): issue for issue in previous.get("issues", [])}
        curr_issues = {self._issue_key(issue): issue for issue in current.get("issues", [])}

        new_issue_keys = sorted(set(curr_issues) - set(prev_issues))
        resolved_issue_keys = sorted(set(prev_issues) - set(curr_issues))

        changes: List[Dict[str, Any]] = []
        for key in added_keys:
            server = curr_servers[key]
            changes.append(
                {
                    "category": "mcp_server",
                    "change": "added",
                    "name": server.get("name"),
                    "source": server.get("source"),
                    "signature": server.get("signature"),
                }
            )

        for key in removed_keys:
            server = prev_servers[key]
            changes.append(
                {
                    "category": "mcp_server",
                    "change": "removed",
                    "name": server.get("name"),
                    "source": server.get("source"),
                    "signature": server.get("signature"),
                }
            )

        for key in new_issue_keys:
            issue = curr_issues[key]
            changes.append(
                {
                    "category": "issue",
                    "change": "new",
                    "name": issue.get("issue_type"),
                    "source": issue.get("source"),
                    "message": issue.get("message"),
                    "severity": issue.get("severity"),
                }
            )

        for key in resolved_issue_keys:
            issue = prev_issues[key]
            changes.append(
                {
                    "category": "issue",
                    "change": "resolved",
                    "name": issue.get("issue_type"),
                    "source": issue.get("source"),
                    "message": issue.get("message"),
                    "severity": issue.get("severity"),
                }
            )

        return {
            "from_scan_id": previous.get("scan_id"),
            "to_scan_id": current.get("scan_id"),
            "summary": {
                "added_servers": len(added_keys),
                "removed_servers": len(removed_keys),
                "new_issues": len(new_issue_keys),
                "resolved_issues": len(resolved_issue_keys),
            },
            "changes": changes[:200],
        }

    def _build_snapshot_payload(self) -> Tuple[Dict[str, Any], List[Issue]]:
        raw_ides = detector.detect_ides()
        raw_llms = detector.detect_llms()
        raw_mcp_locations = detector.detect_mcp()

        ides = normalize_detected_items(raw_ides, category="ide")
        llms = normalize_detected_items(raw_llms, category="llm")
        mcp_locations, mcp_servers = normalize_mcp_locations(raw_mcp_locations)

        issues = evaluate_issues(mcp_locations, mcp_servers)

        issues_summary = summarize_issues(issues, config_count=len(mcp_locations))

        payload = {
            "created_at": utc_now_iso(),
            "machine_name": socket.gethostname(),
            "ides": [self._detected_to_api(item) for item in ides],
            "llms": [self._detected_to_api(item) for item in llms],
            "mcp_locations": [self._location_to_api(location) for location in mcp_locations],
            "mcp_servers": [self._server_to_api(server) for server in mcp_servers],
            "issues": [self._issue_to_api(issue) for issue in issues],
            "issues_summary": issues_summary,
            "payload_hash": stable_hash(self._prepare_hash_payload(ides, llms, mcp_locations, mcp_servers)),
        }

        return payload, issues

    def run_scan(self) -> Dict[str, Any]:
        payload, issues_models = self._build_snapshot_payload()

        latest = self.store.get_latest_hash()
        if latest and latest[1] == payload["payload_hash"]:
            existing = self.store.get_snapshot(latest[0])
            if existing:
                existing["deduped"] = True
                return existing

        scan_id = self.store.insert_snapshot(
            created_at=payload["created_at"],
            machine_name=payload["machine_name"],
            payload_hash=payload["payload_hash"],
            ides=payload["ides"],
            llms=payload["llms"],
            mcp_locations=payload["mcp_locations"],
            mcp_servers=payload["mcp_servers"],
            issues_summary=payload["issues_summary"],
            drift={},
        )

        self.store.replace_issues(scan_id, issues_models)

        current = self.store.get_snapshot(scan_id)
        previous = self.store.get_previous_snapshot(scan_id)
        if not current:
            raise RuntimeError("Failed to load newly inserted scan snapshot")

        drift = self._calculate_drift(previous, current)
        self.store.update_drift(scan_id, drift)

        current["drift"] = drift
        current["deduped"] = False
        return current

    def get_latest_or_scan(self) -> Dict[str, Any]:
        latest = self.store.get_latest_snapshot()
        if latest:
            latest["deduped"] = False
            return latest
        return self.run_scan()

    def get_snapshot_or_latest(self, scan_id: Optional[int]) -> Dict[str, Any]:
        if scan_id is not None:
            snapshot = self.store.get_snapshot(scan_id)
            if snapshot:
                return snapshot
        return self.get_latest_or_scan()

    def get_all_payload(self, refresh: bool = False) -> Dict[str, Any]:
        snapshot = self.run_scan() if refresh else self.get_latest_or_scan()
        return {
            "scan_id": snapshot["scan_id"],
            "timestamp": snapshot["created_at"],
            "machine_name": snapshot["machine_name"],
            "ides": snapshot.get("ides", []),
            "llms": snapshot.get("llms", []),
            "mcp": snapshot.get("mcp_locations", []),
            "issues": snapshot.get("issues", []),
            "issues_summary": snapshot.get("issues_summary", {}),
            "drift": snapshot.get("drift", {}),
            "deduped": bool(snapshot.get("deduped", False)),
        }

    def list_issues(
        self,
        scan_id: Optional[int] = None,
        severity: str = "",
        issue_type: str = "",
        source: str = "",
    ) -> Dict[str, Any]:
        snapshot = self.get_snapshot_or_latest(scan_id)
        target_scan_id = int(snapshot["scan_id"])

        issues = self.store.list_issues(
            scan_id=target_scan_id,
            severity=severity,
            issue_type=issue_type,
            source=source,
        )

        return {
            "scan_id": target_scan_id,
            "filters": {
                "severity": severity,
                "type": issue_type,
                "source": source,
            },
            "issues": issues,
            "count": len(issues),
        }

    def list_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.store.list_history(limit=limit)

    def list_mcp_targets(self) -> Dict[str, Any]:
        snapshot = self.run_scan()
        locations = snapshot.get("mcp_locations", [])
        targets: List[McpTarget] = []
        seen_paths = set()

        for location in locations:
            path = str(location.get("path", "") or "")
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)

            key = self._coerce_mcp_key(str(location.get("key", "mcpServers") or "mcpServers"))
            target = McpTarget(
                name=str(location.get("name", "") or ""),
                path=path,
                key=key,  # type: ignore[arg-type]
                scope=(
                    str(location.get("scope", "unknown") or "unknown")
                    if str(location.get("scope", "unknown") or "unknown") in {"global", "project", "unknown"}
                    else "unknown"
                ),
                exists=bool(location.get("exists", False)),
                writable=True,
                project_path=self._project_path_from_location(location),
                is_default=False,
            )
            targets.append(target)

        targets.sort(key=lambda target: (0 if target.scope == "project" else 1, target.name.lower(), target.path))

        default_idx = 0
        for idx, target in enumerate(targets):
            if target.scope == "project":
                default_idx = idx
                break
        if targets:
            targets[default_idx].is_default = True

        return {
            "targets": [model_to_dict(target) for target in targets],
            "default_target_path": targets[default_idx].path if targets else "",
        }

    def add_mcp_server(self, mutation: McpServerMutation) -> Dict[str, Any]:
        result = self.config_manager.add_server(
            target_path=mutation.target_path,
            target_key=mutation.target_key,
            name=mutation.name,
            command=mutation.command,
            args=list(mutation.args),
            env=dict(mutation.env),
        )
        snapshot = self.run_scan()
        return {
            "ok": True,
            "target_path": result.target_path,
            "target_key": result.target_key,
            "server_name": result.server_name,
            "backup_path": result.backup_path,
            "scan_id": snapshot.get("scan_id"),
            "issues_summary": snapshot.get("issues_summary", {}),
        }

    def update_mcp_server(self, mutation: McpServerUpdateMutation) -> Dict[str, Any]:
        result = self.config_manager.update_server(
            target_path=mutation.target_path,
            target_key=mutation.target_key,
            old_name=mutation.old_name,
            name=mutation.name,
            command=mutation.command,
            args=list(mutation.args),
            env=dict(mutation.env),
        )
        snapshot = self.run_scan()
        return {
            "ok": True,
            "target_path": result.target_path,
            "target_key": result.target_key,
            "server_name": result.server_name,
            "backup_path": result.backup_path,
            "scan_id": snapshot.get("scan_id"),
            "issues_summary": snapshot.get("issues_summary", {}),
        }

    def delete_mcp_server(self, mutation: McpServerDeleteMutation) -> Dict[str, Any]:
        result = self.config_manager.delete_server(
            target_path=mutation.target_path,
            target_key=mutation.target_key,
            name=mutation.name,
        )
        snapshot = self.run_scan()
        return {
            "ok": True,
            "target_path": result.target_path,
            "target_key": result.target_key,
            "server_name": result.server_name,
            "backup_path": result.backup_path,
            "scan_id": snapshot.get("scan_id"),
            "issues_summary": snapshot.get("issues_summary", {}),
        }

    def list_new_mcp_catalog(
        self,
        days: int = 14,
        limit: int = 30,
        cursor: str = "",
        refresh: bool = False,
        mode: str = "new",
    ) -> Dict[str, Any]:
        safe_days = max(1, min(days, 90))
        safe_limit = max(1, min(limit, 300))
        safe_mode = "all" if str(mode).lower() == "all" else "new"
        cache_key = f"catalog:{safe_mode}:{safe_days}:{safe_limit}:{cursor or '-'}"

        cached = self.store.get_registry_cache(cache_key)
        if cached and not refresh:
            age = self._cache_age_seconds(cached.get("fetched_at", ""))
            if age <= self.REGISTRY_CACHE_TTL_SECONDS:
                payload = dict(cached.get("payload", {}))
                payload["cache"] = "hit"
                return payload

        try:
            payload = self.registry_client.fetch_new_servers(
                days=safe_days,
                limit=safe_limit,
                cursor=cursor,
                mode=safe_mode,
            )
            payload["items"] = [model_to_dict(McpCatalogItem(**item)) for item in payload.get("items", [])]
            payload["fetched_at"] = utc_now_iso()
            self.store.put_registry_cache(cache_key, payload["fetched_at"], payload)
            payload["cache"] = "miss"
            return payload
        except Exception as exc:
            if cached:
                payload = dict(cached.get("payload", {}))
                payload["cache"] = "stale"
                payload["warning"] = f"Registry fetch failed; using cached data: {exc}"
                return payload
            raise

    def export_markdown(self, scan_id: Optional[int] = None) -> str:
        snapshot = self.get_snapshot_or_latest(scan_id)
        return build_markdown_report(snapshot)

    def export_json(self, scan_id: Optional[int] = None) -> str:
        snapshot = self.get_snapshot_or_latest(scan_id)
        return build_json_report(snapshot)
