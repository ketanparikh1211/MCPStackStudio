"""Normalization from detector dictionaries into typed models."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .models import DetectedItem, McpConfigLocation, McpServer


def normalize_detected_items(raw_items: List[Dict[str, Any]], category: str) -> List[DetectedItem]:
    items: List[DetectedItem] = []
    for raw in raw_items:
        items.append(
            DetectedItem(
                category=category,
                name=str(raw.get("name", "")),
                path=str(raw.get("path", "") or ""),
                version=str(raw.get("version", "") or ""),
                icon=str(raw.get("icon", "default") or "default"),
                item_type=str(raw.get("type", "") or ""),
                running=bool(raw.get("running", False)),
                status=str(raw.get("status", "") or ""),
                host=str(raw.get("host", "") or ""),
            )
        )

    items.sort(key=lambda entry: (entry.name.lower(), entry.path.lower()))
    return items


def _normalize_args(raw_args: Any) -> List[str]:
    if isinstance(raw_args, list):
        return [str(arg) for arg in raw_args]
    if raw_args is None:
        return []
    return [str(raw_args)]


def _normalize_env(raw_env: Any) -> List[str]:
    if isinstance(raw_env, dict):
        return sorted(str(key) for key in raw_env.keys())
    if isinstance(raw_env, list):
        return sorted(str(key) for key in raw_env)
    return []


def normalize_mcp_locations(raw_locations: List[Dict[str, Any]]) -> Tuple[List[McpConfigLocation], List[McpServer]]:
    locations: List[McpConfigLocation] = []
    servers: List[McpServer] = []

    for raw_location in raw_locations:
        path = str(raw_location.get("path", "") or "")
        name = str(raw_location.get("name", "") or "")
        key = str(raw_location.get("key", "unknown") or "unknown")
        scope = str(raw_location.get("scope", "unknown") or "unknown")

        location_servers: List[McpServer] = []
        for raw_server in raw_location.get("servers", []) or []:
            if not isinstance(raw_server, dict):
                continue

            project_path = str(raw_server.get("project", "") or "")
            server_scope = str(raw_server.get("scope", scope) or scope)
            server = McpServer(
                name=str(raw_server.get("name", "") or ""),
                command=str(raw_server.get("command", "") or ""),
                args=_normalize_args(raw_server.get("args", [])),
                env_keys=_normalize_env(raw_server.get("env", [])),
                source_name=name,
                config_path=path,
                scope=server_scope if server_scope in {"global", "project", "unknown"} else "unknown",
                project_path=project_path,
            )
            location_servers.append(server)
            servers.append(server)

        location = McpConfigLocation(
            name=name,
            path=path,
            key=key if key in {"mcpServers", "servers", "context_servers", "unknown"} else "unknown",
            exists=bool(raw_location.get("exists", False)),
            server_count=int(raw_location.get("serverCount", len(location_servers)) or 0),
            error=raw_location.get("error"),
            scope=scope if scope in {"global", "project", "unknown"} else "unknown",
            servers=location_servers,
        )
        locations.append(location)

    locations.sort(key=lambda entry: (entry.scope, entry.name.lower(), entry.path.lower()))
    servers.sort(key=lambda entry: (entry.name.lower(), entry.source_name.lower(), entry.config_path.lower()))
    return locations, servers
