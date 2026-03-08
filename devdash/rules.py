"""Rule engine for actionable MCP insights and conflicts."""

from __future__ import annotations

import os
import shlex
import shutil
from collections import defaultdict
from typing import Dict, Iterable, List

from .models import Issue, McpConfigLocation, McpServer
from .utils import stable_hash

CONFLICT_TYPES = {"duplicate_server_name", "global_project_conflict"}


def _build_issue(
    severity: str,
    issue_type: str,
    source: str,
    message: str,
    details: Dict[str, object],
) -> Issue:
    fingerprint = stable_hash(
        {
            "severity": severity,
            "issue_type": issue_type,
            "source": source,
            "message": message,
            "details": details,
        }
    )[:16]

    return Issue(
        issue_id=fingerprint,
        severity=severity,
        issue_type=issue_type,
        source=source,
        message=message,
        details=details,
    )


def _resolve_binary(command: str) -> str:
    cmd = command.strip()
    if not cmd:
        return ""

    try:
        parts = shlex.split(cmd)
    except ValueError:
        parts = [cmd]

    if not parts:
        return ""

    executable = parts[0]
    if executable.startswith("/"):
        return executable if os.path.exists(executable) else ""

    resolved = shutil.which(executable)
    return resolved or ""


def evaluate_issues(
    mcp_locations: List[McpConfigLocation],
    mcp_servers: List[McpServer],
) -> List[Issue]:
    issues: List[Issue] = []

    for location in mcp_locations:
        if location.error:
            issues.append(
                _build_issue(
                    severity="high",
                    issue_type="mcp_config_parse_error",
                    source=location.name,
                    message=f"Failed to parse MCP config: {location.path}",
                    details={
                        "path": location.path,
                        "error": location.error,
                        "scope": location.scope,
                    },
                )
            )

    for server in mcp_servers:
        command = server.command.strip()
        if not command:
            issues.append(
                _build_issue(
                    severity="critical",
                    issue_type="invalid_command",
                    source=server.source_name,
                    message=f"MCP server '{server.name}' has an empty command",
                    details={
                        "server": server.name,
                        "path": server.config_path,
                        "scope": server.scope,
                        "project": server.project_path,
                    },
                )
            )
            continue

        resolved = _resolve_binary(command)
        if not resolved:
            issues.append(
                _build_issue(
                    severity="high",
                    issue_type="missing_command_binary",
                    source=server.source_name,
                    message=f"MCP server '{server.name}' command is not available on PATH",
                    details={
                        "server": server.name,
                        "command": server.command,
                        "path": server.config_path,
                        "scope": server.scope,
                        "project": server.project_path,
                    },
                )
            )

    grouped: Dict[str, List[McpServer]] = defaultdict(list)
    for server in mcp_servers:
        grouped[server.name.lower()].append(server)

    for group in grouped.values():
        signatures = sorted({entry.signature for entry in group if entry.signature})
        if len(signatures) > 1:
            issues.append(
                _build_issue(
                    severity="high",
                    issue_type="duplicate_server_name",
                    source=group[0].name,
                    message=f"Server name '{group[0].name}' maps to multiple command definitions",
                    details={
                        "server": group[0].name,
                        "variants": [
                            {
                                "signature": entry.signature,
                                "source": entry.source_name,
                                "scope": entry.scope,
                                "path": entry.config_path,
                            }
                            for entry in group
                        ],
                    },
                )
            )

        global_signatures = {entry.signature for entry in group if entry.scope == "global" and entry.signature}
        project_signatures = {entry.signature for entry in group if entry.scope == "project" and entry.signature}

        if global_signatures and project_signatures and not project_signatures.issubset(global_signatures):
            issues.append(
                _build_issue(
                    severity="high",
                    issue_type="global_project_conflict",
                    source=group[0].name,
                    message=f"Server '{group[0].name}' differs between global and project configs",
                    details={
                        "server": group[0].name,
                        "global_signatures": sorted(global_signatures),
                        "project_signatures": sorted(project_signatures),
                    },
                )
            )

    unique: Dict[str, Issue] = {}
    for issue in issues:
        unique[issue.issue_id] = issue

    ordered = sorted(unique.values(), key=lambda issue: (issue.severity, issue.issue_type, issue.source))
    return ordered


def summarize_issues(issues: Iterable[Issue], config_count: int) -> Dict[str, int]:
    summary = {
        "total": 0,
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "conflicts": 0,
        "configs_scanned": config_count,
    }

    for issue in issues:
        summary["total"] += 1
        summary[issue.severity] += 1
        if issue.issue_type in CONFLICT_TYPES:
            summary["conflicts"] += 1

    return summary
