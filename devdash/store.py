"""SQLite persistence for scan snapshots and issue history."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import Issue
from .utils import model_to_dict


class SnapshotStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = os.path.expanduser(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    machine_name TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    ides_json TEXT NOT NULL,
                    llms_json TEXT NOT NULL,
                    mcp_locations_json TEXT NOT NULL,
                    mcp_servers_json TEXT NOT NULL,
                    issues_summary_json TEXT NOT NULL,
                    drift_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id INTEGER NOT NULL,
                    issue_id TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    issue_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    FOREIGN KEY(scan_id) REFERENCES snapshots(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS registry_cache (
                    cache_key TEXT PRIMARY KEY,
                    fetched_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON snapshots(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_snapshots_payload_hash ON snapshots(payload_hash);
                CREATE INDEX IF NOT EXISTS idx_issues_scan_id ON issues(scan_id);
                CREATE INDEX IF NOT EXISTS idx_issues_filters ON issues(scan_id, severity, issue_type, source);
                """
            )
            conn.commit()

    def get_latest_hash(self) -> Optional[Tuple[int, str]]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id, payload_hash FROM snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return int(row["id"]), str(row["payload_hash"])

    def insert_snapshot(
        self,
        created_at: str,
        machine_name: str,
        payload_hash: str,
        ides: List[Dict[str, Any]],
        llms: List[Dict[str, Any]],
        mcp_locations: List[Dict[str, Any]],
        mcp_servers: List[Dict[str, Any]],
        issues_summary: Dict[str, int],
        drift: Dict[str, Any],
    ) -> int:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                INSERT INTO snapshots (
                    created_at, machine_name, payload_hash, ides_json, llms_json,
                    mcp_locations_json, mcp_servers_json, issues_summary_json, drift_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    machine_name,
                    payload_hash,
                    json.dumps(ides),
                    json.dumps(llms),
                    json.dumps(mcp_locations),
                    json.dumps(mcp_servers),
                    json.dumps(issues_summary),
                    json.dumps(drift),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_drift(self, scan_id: int, drift: Dict[str, Any]) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE snapshots SET drift_json = ? WHERE id = ?",
                (json.dumps(drift), scan_id),
            )
            conn.commit()

    def replace_issues(self, scan_id: int, issues: List[Issue]) -> None:
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM issues WHERE scan_id = ?", (scan_id,))
            conn.executemany(
                """
                INSERT INTO issues (scan_id, issue_id, severity, issue_type, source, message, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        scan_id,
                        issue.issue_id,
                        issue.severity,
                        issue.issue_type,
                        issue.source,
                        issue.message,
                        json.dumps(model_to_dict(issue.details)),
                    )
                    for issue in issues
                ],
            )
            conn.commit()

    def _decode_snapshot_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "scan_id": int(row["id"]),
            "created_at": str(row["created_at"]),
            "machine_name": str(row["machine_name"]),
            "payload_hash": str(row["payload_hash"]),
            "ides": json.loads(row["ides_json"]),
            "llms": json.loads(row["llms_json"]),
            "mcp_locations": json.loads(row["mcp_locations_json"]),
            "mcp_servers": json.loads(row["mcp_servers_json"]),
            "issues_summary": json.loads(row["issues_summary_json"]),
            "drift": json.loads(row["drift_json"]),
        }

    def get_snapshot(self, scan_id: int) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM snapshots WHERE id = ?", (scan_id,)).fetchone()
            if not row:
                return None
            snapshot = self._decode_snapshot_row(row)
            snapshot["issues"] = self.list_issues(scan_id)
            return snapshot

    def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return None
            snapshot = self._decode_snapshot_row(row)
            snapshot["issues"] = self.list_issues(snapshot["scan_id"])
            return snapshot

    def get_previous_snapshot(self, current_scan_id: int) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM snapshots WHERE id < ? ORDER BY id DESC LIMIT 1",
                (current_scan_id,),
            ).fetchone()
            if not row:
                return None
            snapshot = self._decode_snapshot_row(row)
            snapshot["issues"] = self.list_issues(snapshot["scan_id"])
            return snapshot

    def list_issues(
        self,
        scan_id: int,
        severity: str = "",
        issue_type: str = "",
        source: str = "",
    ) -> List[Dict[str, Any]]:
        conditions = ["scan_id = ?"]
        params: List[Any] = [scan_id]

        if severity:
            conditions.append("severity = ?")
            params.append(severity)
        if issue_type:
            conditions.append("issue_type = ?")
            params.append(issue_type)
        if source:
            conditions.append("source = ?")
            params.append(source)

        sql = (
            "SELECT issue_id, severity, issue_type, source, message, details_json "
            f"FROM issues WHERE {' AND '.join(conditions)} ORDER BY severity, issue_type, source"
        )

        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()

        return [
            {
                "issue_id": str(row["issue_id"]),
                "severity": str(row["severity"]),
                "issue_type": str(row["issue_type"]),
                "source": str(row["source"]),
                "message": str(row["message"]),
                "details": json.loads(row["details_json"]),
            }
            for row in rows
        ]

    def list_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, machine_name, payload_hash, issues_summary_json
                FROM snapshots
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        history: List[Dict[str, Any]] = []
        for row in rows:
            summary = json.loads(row["issues_summary_json"])
            history.append(
                {
                    "scan_id": int(row["id"]),
                    "created_at": str(row["created_at"]),
                    "machine_name": str(row["machine_name"]),
                    "payload_hash": str(row["payload_hash"]),
                    "issues_summary": summary,
                    "issue_count": int(summary.get("total", 0)),
                    "critical_count": int(summary.get("critical", 0)),
                }
            )

        return history

    def get_registry_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT cache_key, fetched_at, payload_json FROM registry_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()

        if not row:
            return None

        return {
            "cache_key": str(row["cache_key"]),
            "fetched_at": str(row["fetched_at"]),
            "payload": json.loads(row["payload_json"]),
        }

    def put_registry_cache(self, cache_key: str, fetched_at: str, payload: Dict[str, Any]) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO registry_cache (cache_key, fetched_at, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    fetched_at = excluded.fetched_at,
                    payload_json = excluded.payload_json
                """,
                (cache_key, fetched_at, json.dumps(payload)),
            )
            conn.commit()
