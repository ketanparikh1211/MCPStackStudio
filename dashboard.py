#!/usr/bin/env python3
"""MCPStackStudio CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

import uvicorn

from devdash.api import create_app
from devdash.service import ScanService
from devdash.store import SnapshotStore

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8420
DEFAULT_DB_PATH = os.path.expanduser(
    os.getenv("MCPSTACKSTUDIO_DB")
    or os.getenv("DEV_DASHBOARD_DB")
    or str(Path(__file__).resolve().parent / ".mcpstackstudio" / "mcpstackstudio.sqlite3")
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dashboard.py",
        description="MCPStackStudio: team-ready local IDE/LLM/MCP insights.",
    )
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help="SQLite database path (default: %(default)s)",
    )

    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="Run the FastAPI web server")
    serve.add_argument(
        "--db-path",
        dest="db_path_override",
        default=None,
        help="SQLite database path override",
    )
    serve.add_argument("--host", default=DEFAULT_HOST, help="Bind host (default: %(default)s)")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port (default: %(default)s)")
    serve.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open the dashboard in a browser",
    )

    scan = subparsers.add_parser("scan", help="Run one scan and persist snapshot")
    scan.add_argument(
        "--db-path",
        dest="db_path_override",
        default=None,
        help="SQLite database path override",
    )

    export = subparsers.add_parser("export", help="Export latest or specific scan report")
    export.add_argument(
        "--db-path",
        dest="db_path_override",
        default=None,
        help="SQLite database path override",
    )
    export.add_argument("--format", choices=["md", "json"], required=True)
    export.add_argument("--output", required=True, help="Output file path")
    export.add_argument("--scan-id", type=int, default=None, help="Optional scan ID to export")

    return parser


def _build_service(db_path: str) -> ScanService:
    store = SnapshotStore(db_path)
    return ScanService(store)


def _is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def _command_serve(args: argparse.Namespace, service: ScanService) -> int:
    host = args.host
    port = args.port

    require_token = not _is_loopback(host)
    access_token = os.getenv("MCPSTACKSTUDIO_TOKEN", "") or os.getenv("DEV_DASHBOARD_TOKEN", "")

    if require_token and not access_token:
        print(
            "Set MCPSTACKSTUDIO_TOKEN (or DEV_DASHBOARD_TOKEN) when running on non-loopback hosts.",
            file=sys.stderr,
        )
        return 2

    index_path = Path(__file__).resolve().parent / "index.html"
    app = create_app(
        service=service,
        index_path=index_path,
        require_token_for_remote=require_token,
        access_token=access_token,
    )

    url = f"http://{host}:{port}"
    print(f"\nMCPStackStudio running at {url}")
    if require_token:
        print("Remote clients must send header: X-DevDash-Token")

    if not args.no_browser and _is_loopback(host):
        webbrowser.open(url)

    uvicorn.run(app, host=host, port=port)
    return 0


def _command_scan(service: ScanService) -> int:
    snapshot = service.run_scan()
    output = {
        "scan_id": snapshot.get("scan_id"),
        "timestamp": snapshot.get("created_at"),
        "machine_name": snapshot.get("machine_name"),
        "deduped": bool(snapshot.get("deduped", False)),
        "issues_summary": snapshot.get("issues_summary", {}),
    }
    print(json.dumps(output, indent=2))
    return 0


def _command_export(args: argparse.Namespace, service: ScanService) -> int:
    scan_id = args.scan_id
    if args.format == "md":
        content = service.export_markdown(scan_id=scan_id)
    else:
        content = service.export_json(scan_id=scan_id)

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    print(f"Wrote {args.format.upper()} report to {output_path}")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        args.command = "serve"
        args.host = DEFAULT_HOST
        args.port = DEFAULT_PORT
        args.no_browser = False

    db_path = getattr(args, "db_path_override", None) or args.db_path
    service = _build_service(db_path)

    if args.command == "serve":
        return _command_serve(args, service)
    if args.command == "scan":
        return _command_scan(service)
    if args.command == "export":
        return _command_export(args, service)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
