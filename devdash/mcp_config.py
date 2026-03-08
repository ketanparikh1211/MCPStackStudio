"""MCP configuration target discovery and safe write operations."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SUPPORTED_KEYS = {"mcpServers", "servers", "context_servers"}


class McpConfigError(ValueError):
    """Raised when MCP configuration changes cannot be applied safely."""


@dataclass
class McpMutationResult:
    target_path: str
    target_key: str
    server_name: str
    backup_path: str


class McpConfigManager:
    def infer_key(self, path: str, data: Dict[str, Any], preferred: Optional[str] = None) -> str:
        if preferred in SUPPORTED_KEYS:
            return str(preferred)

        for key in ("mcpServers", "servers", "context_servers"):
            if isinstance(data.get(key), dict):
                return key

        lowered = path.lower()
        if "/.vscode/" in lowered:
            return "servers"
        if "/zed/" in lowered and lowered.endswith("settings.json"):
            return "context_servers"
        return "mcpServers"

    @staticmethod
    def _normalize_args(args: Iterable[Any]) -> List[str]:
        return [str(part) for part in args]

    @staticmethod
    def _normalize_env(env: Dict[str, Any]) -> Dict[str, str]:
        return {str(k): str(v) for k, v in (env or {}).items()}

    def _read_config(self, target_path: Path) -> Dict[str, Any]:
        if not target_path.exists():
            return {}

        try:
            data = json.loads(target_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise McpConfigError(f"Invalid JSON in {target_path}: {exc}") from exc
        except OSError as exc:
            raise McpConfigError(f"Unreadable file {target_path}: {exc}") from exc

        if not isinstance(data, dict):
            raise McpConfigError(f"Config root in {target_path} must be a JSON object")
        return data

    def _write_config_atomic(self, target_path: Path, data: Dict[str, Any]) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = ""
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if target_path.exists():
            backup = Path(f"{target_path}.bak.{stamp}")
            try:
                shutil.copy2(target_path, backup)
            except OSError as exc:
                raise McpConfigError(f"Failed to create backup for {target_path}: {exc}") from exc
            backup_path = str(backup)

        tmp = target_path.with_name(f".{target_path.name}.tmp.{os.getpid()}.{stamp}")
        content = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
        try:
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, target_path)
        except OSError as exc:
            raise McpConfigError(f"Failed writing config {target_path}: {exc}") from exc
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

        return backup_path

    def _servers_block(self, data: Dict[str, Any], key: str) -> Dict[str, Any]:
        existing = data.get(key)
        if existing is None:
            data[key] = {}
            return data[key]
        if not isinstance(existing, dict):
            raise McpConfigError(f"Field '{key}' exists but is not an object")
        return existing

    @staticmethod
    def _validate_name(value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise McpConfigError("MCP server name is required")
        return normalized

    @staticmethod
    def _validate_command(value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise McpConfigError("MCP command is required")
        return normalized

    def _build_server_entry(
        self,
        command: str,
        args: List[str],
        env: Dict[str, str],
        seed: Optional[Dict[str, Any]] = None,
        preserve_env_if_empty: bool = False,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = dict(seed or {})
        payload["command"] = self._validate_command(command)
        payload["args"] = self._normalize_args(args)

        normalized_env = self._normalize_env(env)
        if normalized_env:
            payload["env"] = normalized_env
        elif "env" in payload and not preserve_env_if_empty:
            payload.pop("env", None)

        return payload

    def add_server(
        self,
        target_path: str,
        target_key: Optional[str],
        name: str,
        command: str,
        args: List[str],
        env: Dict[str, str],
    ) -> McpMutationResult:
        normalized_name = self._validate_name(name)
        path = Path(os.path.expanduser(target_path)).resolve()
        data = self._read_config(path)
        key = self.infer_key(str(path), data, preferred=target_key)
        servers = self._servers_block(data, key)

        if normalized_name in servers:
            raise McpConfigError(f"Server '{normalized_name}' already exists in {path}")

        servers[normalized_name] = self._build_server_entry(command, args, env)
        backup_path = self._write_config_atomic(path, data)
        return McpMutationResult(str(path), key, normalized_name, backup_path)

    def update_server(
        self,
        target_path: str,
        target_key: Optional[str],
        old_name: str,
        name: str,
        command: str,
        args: List[str],
        env: Dict[str, str],
    ) -> McpMutationResult:
        normalized_old_name = self._validate_name(old_name)
        normalized_name = self._validate_name(name)

        path = Path(os.path.expanduser(target_path)).resolve()
        data = self._read_config(path)
        key = self.infer_key(str(path), data, preferred=target_key)
        servers = self._servers_block(data, key)

        if normalized_old_name not in servers:
            raise McpConfigError(f"Server '{normalized_old_name}' was not found in {path}")

        if normalized_name != normalized_old_name and normalized_name in servers:
            raise McpConfigError(f"Server '{normalized_name}' already exists in {path}")

        seed = servers.get(normalized_old_name)
        seed_payload = seed if isinstance(seed, dict) else {}
        updated = self._build_server_entry(
            command,
            args,
            env,
            seed=seed_payload,
            preserve_env_if_empty=True,
        )

        if normalized_name != normalized_old_name:
            servers.pop(normalized_old_name, None)
        servers[normalized_name] = updated

        backup_path = self._write_config_atomic(path, data)
        return McpMutationResult(str(path), key, normalized_name, backup_path)

    def delete_server(self, target_path: str, target_key: Optional[str], name: str) -> McpMutationResult:
        normalized_name = self._validate_name(name)
        path = Path(os.path.expanduser(target_path)).resolve()
        data = self._read_config(path)
        key = self.infer_key(str(path), data, preferred=target_key)
        servers = self._servers_block(data, key)

        if normalized_name not in servers:
            raise McpConfigError(f"Server '{normalized_name}' was not found in {path}")

        servers.pop(normalized_name, None)
        backup_path = self._write_config_atomic(path, data)
        return McpMutationResult(str(path), key, normalized_name, backup_path)
