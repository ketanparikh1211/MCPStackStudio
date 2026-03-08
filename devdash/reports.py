"""Report rendering for JSON and Markdown outputs."""

from __future__ import annotations

import json
from typing import Any, Dict, List


def build_markdown_report(snapshot: Dict[str, Any]) -> str:
    summary = snapshot.get("issues_summary", {})
    issues: List[Dict[str, Any]] = snapshot.get("issues", [])
    drift = snapshot.get("drift", {})
    lines: List[str] = []

    lines.append("# MCPStackStudio Scan Report")
    lines.append("")
    lines.append(f"- **Machine**: `{snapshot.get('machine_name', 'unknown')}`")
    lines.append(f"- **Timestamp (UTC)**: `{snapshot.get('created_at', '')}`")
    lines.append(f"- **Scan ID**: `{snapshot.get('scan_id', '')}`")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total issues: **{summary.get('total', 0)}**")
    lines.append(f"- Critical: **{summary.get('critical', 0)}**")
    lines.append(f"- High: **{summary.get('high', 0)}**")
    lines.append(f"- MCP configs scanned: **{summary.get('configs_scanned', 0)}**")
    lines.append(f"- MCP conflicts: **{summary.get('conflicts', 0)}**")
    lines.append("")

    lines.append("## Top Findings")
    lines.append("")
    if not issues:
        lines.append("No issues detected.")
    else:
        top_issues = issues[:20]
        for issue in top_issues:
            lines.append(
                f"- [{issue.get('severity', 'low').upper()}] "
                f"`{issue.get('issue_type', 'unknown')}` in **{issue.get('source', 'unknown')}**: "
                f"{issue.get('message', '')}"
            )

    lines.append("")
    lines.append("## Drift Since Previous Scan")
    lines.append("")
    drift_summary = drift.get("summary", {})
    if not drift_summary:
        lines.append("No prior scan to compare.")
    else:
        lines.append(f"- Added MCP servers: **{drift_summary.get('added_servers', 0)}**")
        lines.append(f"- Removed MCP servers: **{drift_summary.get('removed_servers', 0)}**")
        lines.append(f"- New issues: **{drift_summary.get('new_issues', 0)}**")
        lines.append(f"- Resolved issues: **{drift_summary.get('resolved_issues', 0)}**")

    return "\n".join(lines).strip() + "\n"


def build_json_report(snapshot: Dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=2)
