"""FastAPI application wiring for MCPStackStudio."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from .mcp_config import McpConfigError
from .models import McpServerDeleteMutation, McpServerMutation, McpServerUpdateMutation
from .service import ScanService


LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def create_app(
    service: ScanService,
    index_path: Path,
    require_token_for_remote: bool = False,
    access_token: str = "",
) -> FastAPI:
    app = FastAPI(title="MCPStackStudio", version="2.0.0")

    @app.middleware("http")
    async def no_cache_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.middleware("http")
    async def token_guard(request: Request, call_next):
        if not require_token_for_remote:
            return await call_next(request)

        client_host = request.client.host if request.client else ""
        if client_host in LOOPBACK_HOSTS:
            return await call_next(request)

        provided = request.headers.get("X-DevDash-Token", "")
        if not access_token or provided != access_token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: missing or invalid X-DevDash-Token"},
            )

        return await call_next(request)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/")
    def root() -> FileResponse:
        if not index_path.exists():
            raise HTTPException(status_code=500, detail="index.html not found")
        return FileResponse(index_path)

    icons_dir = index_path.parent / "icons"

    @app.get("/icons/{name:path}")
    def get_icon(name: str) -> FileResponse:
        icon_file = icons_dir / name
        if not icon_file.exists() or not icon_file.suffix == ".svg":
            raise HTTPException(status_code=404, detail="Icon not found")
        # Resolve to prevent path traversal
        icon_file = icon_file.resolve()
        if not str(icon_file).startswith(str(icons_dir.resolve())):
            raise HTTPException(status_code=403, detail="Forbidden")
        return FileResponse(icon_file, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/api/all")
    def get_all(refresh: bool = False) -> dict:
        return service.get_all_payload(refresh=refresh)

    @app.get("/api/ides")
    def get_ides() -> list:
        payload = service.get_all_payload()
        return payload.get("ides", [])

    @app.get("/api/llms")
    def get_llms() -> list:
        payload = service.get_all_payload()
        return payload.get("llms", [])

    @app.get("/api/mcp")
    def get_mcp() -> list:
        payload = service.get_all_payload()
        return payload.get("mcp", [])

    @app.get("/api/mcp/targets")
    def get_mcp_targets() -> dict:
        return service.list_mcp_targets()

    @app.post("/api/mcp/servers")
    def add_mcp_server(mutation: McpServerMutation) -> dict:
        try:
            return service.add_mcp_server(mutation)
        except McpConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/api/mcp/servers")
    def update_mcp_server(mutation: McpServerUpdateMutation) -> dict:
        try:
            return service.update_mcp_server(mutation)
        except McpConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/mcp/servers")
    def delete_mcp_server(mutation: McpServerDeleteMutation) -> dict:
        try:
            return service.delete_mcp_server(mutation)
        except McpConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/mcp/catalog/new")
    def get_new_mcp_catalog(
        days: int = 14,
        limit: int = 30,
        cursor: str = "",
        refresh: bool = False,
        mode: str = "new",
    ) -> dict:
        try:
            return service.list_new_mcp_catalog(
                days=days,
                limit=limit,
                cursor=cursor,
                refresh=refresh,
                mode=mode,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to load registry catalog: {exc}") from exc

    def _scan_response() -> dict:
        snapshot = service.run_scan()
        return {
            "scan_id": snapshot.get("scan_id"),
            "timestamp": snapshot.get("created_at"),
            "issues_summary": snapshot.get("issues_summary", {}),
            "deduped": bool(snapshot.get("deduped", False)),
        }

    @app.get("/api/scan")
    def scan_now_get() -> dict:
        return _scan_response()

    @app.post("/api/scan")
    def scan_now_post() -> dict:
        return _scan_response()

    @app.get("/api/issues")
    def get_issues(
        scan_id: Optional[int] = None,
        severity: str = "",
        issue_type: str = Query(default="", alias="type"),
        source: str = "",
    ) -> dict:
        return service.list_issues(
            scan_id=scan_id,
            severity=severity,
            issue_type=issue_type,
            source=source,
        )

    @app.get("/api/history")
    def get_history(limit: int = 20) -> dict:
        return {"items": service.list_history(limit=limit)}

    @app.get("/api/report.md")
    def report_markdown(scan_id: Optional[int] = None) -> PlainTextResponse:
        report = service.export_markdown(scan_id=scan_id)
        return PlainTextResponse(report, media_type="text/markdown; charset=utf-8")

    @app.get("/api/report.json")
    def report_json(scan_id: Optional[int] = None) -> JSONResponse:
        report = service.export_json(scan_id=scan_id)
        return JSONResponse(content=json.loads(report))

    return app
