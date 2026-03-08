"""Pydantic models for scan results, MCP configs, and issues."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal["critical", "high", "medium", "low"]


class DetectedItem(BaseModel):
    category: Literal["ide", "llm"]
    name: str
    path: str = ""
    version: str = ""
    icon: str = "default"
    item_type: str = ""
    running: bool = False
    status: str = ""
    host: str = ""


class McpServer(BaseModel):
    name: str
    command: str = ""
    args: List[str] = Field(default_factory=list)
    env_keys: List[str] = Field(default_factory=list)
    source_name: str
    config_path: str
    scope: Literal["global", "project", "unknown"] = "unknown"
    project_path: str = ""

    @property
    def signature(self) -> str:
        arg_block = " ".join(self.args)
        return f"{self.command} {arg_block}".strip()


class McpConfigLocation(BaseModel):
    name: str
    path: str
    key: Literal["mcpServers", "servers", "context_servers", "unknown"] = "unknown"
    exists: bool = False
    server_count: int = 0
    error: Optional[str] = None
    scope: Literal["global", "project", "unknown"] = "unknown"
    servers: List[McpServer] = Field(default_factory=list)


class Issue(BaseModel):
    issue_id: str
    severity: Severity
    issue_type: str
    source: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ScanSnapshot(BaseModel):
    scan_id: Optional[int] = None
    created_at: str
    machine_name: str
    deduped: bool = False
    payload_hash: str
    ides: List[DetectedItem] = Field(default_factory=list)
    llms: List[DetectedItem] = Field(default_factory=list)
    mcp_locations: List[McpConfigLocation] = Field(default_factory=list)
    mcp_servers: List[McpServer] = Field(default_factory=list)
    issues: List[Issue] = Field(default_factory=list)
    issues_summary: Dict[str, int] = Field(default_factory=dict)
    drift: Dict[str, Any] = Field(default_factory=dict)


class McpTarget(BaseModel):
    name: str
    path: str
    key: Literal["mcpServers", "servers", "context_servers"]
    scope: Literal["global", "project", "unknown"] = "unknown"
    exists: bool = False
    writable: bool = True
    project_path: str = ""
    is_default: bool = False


class McpServerMutation(BaseModel):
    target_path: str
    target_key: Optional[Literal["mcpServers", "servers", "context_servers"]] = None
    name: str
    command: str
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)


class McpServerUpdateMutation(BaseModel):
    target_path: str
    target_key: Optional[Literal["mcpServers", "servers", "context_servers"]] = None
    old_name: str
    name: str
    command: str
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)


class McpServerDeleteMutation(BaseModel):
    target_path: str
    target_key: Optional[Literal["mcpServers", "servers", "context_servers"]] = None
    name: str


class McpCatalogItem(BaseModel):
    server_name: str
    title: str = ""
    description: str = ""
    repo_url: str = ""
    website_url: str = ""
    icon_url: str = ""
    updated_at: str = ""
    status: str = ""
