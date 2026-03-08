# MCPStackStudio

Local-first dashboard for teams to scan IDE/LLM tooling, manage MCP configs safely, and monitor MCP issues/drift with shareable reports.

![Python](https://img.shields.io/badge/python-3.9+-blue) ![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)

## Highlights

- FastAPI backend with typed Pydantic models
- SQLite persistence for scan snapshots, issues, drift, and MCP catalog cache
- MCP Studio in UI: add/edit/delete MCP servers directly from the dashboard
- Safe MCP writes: backup (`.bak.<timestamp>`) + atomic file replace
- MCP catalog aggregation:
  - Primary source: `https://github.com/mcp`
  - Supplement source: `https://registry.modelcontextprotocol.io/v0.1/servers`
  - Fallback: official registry only if GitHub source fails
- Live catalog image rendering (`icon_url`/avatar URLs with UI fallback marks)
- Issues + drift views
- Report exports (`Markdown`, `JSON`)
- Optional LAN mode with token auth (`X-DevDash-Token`)

## Install

```bash
python3 -m pip install -r requirements.txt
```

## Run

Default localhost mode:

```bash
python3 dashboard.py
```

Explicit serve mode:

```bash
python3 dashboard.py serve --host 127.0.0.1 --port 8420
```

Open:

```text
http://127.0.0.1:8420
```

## MCP Studio (Phase 2)

From the dashboard UI you can:

- View detected MCP config targets (project-first default)
- Add MCP server entries
- Edit existing MCP server entries
- Delete MCP server entries
- Prefill MCP add form from catalog items

After each MCP mutation, the app runs a new scan and refreshes summary/issues/drift.

## MCP Catalog Modes

Catalog API supports two modes:

- `mode=new`: updated-within-window view (uses `days`/`updated_since`)
- `mode=all`: full catalog aggregation (GitHub pages + official supplement)

UI currently uses `mode=all`.

## LAN Mode (team access)

For non-loopback host binding, token is required.

```bash
export MCPSTACKSTUDIO_TOKEN="your-shared-token"
python3 dashboard.py serve --host 0.0.0.0 --port 8420
```

Remote clients must send:

```text
X-DevDash-Token: your-shared-token
```

## CLI Commands

Run one scan:

```bash
python3 dashboard.py scan
```

Export reports:

```bash
python3 dashboard.py export --format md --output ./reports/latest.md
python3 dashboard.py export --format json --output ./reports/latest.json
```

Export specific scan:

```bash
python3 dashboard.py export --format md --scan-id 12 --output ./reports/scan-12.md
```

## API Endpoints

Core:

- `GET /api/all` - latest snapshot (`ides`, `llms`, `mcp`) + `issues_summary`, `drift`, `scan_id`
- `GET /api/scan` / `POST /api/scan` - trigger immediate scan
- `GET /api/issues?severity=&type=&source=&scan_id=` - issue list with filters
- `GET /api/history?limit=` - recent scan metadata
- `GET /api/report.md?scan_id=` - markdown report
- `GET /api/report.json?scan_id=` - json report

MCP Studio:

- `GET /api/mcp/targets` - writable MCP targets with scope/key/default
- `POST /api/mcp/servers` - add MCP server
- `PUT /api/mcp/servers` - update MCP server
- `DELETE /api/mcp/servers` - delete MCP server
- `GET /api/mcp/catalog/new?mode=all|new&days=&limit=&cursor=&refresh=` - MCP catalog feed

Backwards-compatible:

- `GET /api/ides`
- `GET /api/llms`
- `GET /api/mcp`

## Storage and Safety

- Default DB: `~/.mcpstackstudio/mcpstackstudio.sqlite3`
- Override DB with `--db-path`, `MCPSTACKSTUDIO_DB`, or `DEV_DASHBOARD_DB`
- MCP config edits create timestamped backup files beside target config

## Rule Engine

- Duplicate MCP server names with different commands/args
- Conflicts between global and project MCP definitions
- Missing command binaries for configured servers
- Invalid JSON/unreadable MCP config files
- Empty/invalid MCP command values

## Tests

Run all tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Project Structure

- `dashboard.py`: CLI entrypoint (`serve`, `scan`, `export`)
- `devdash/`: API, detector, MCP config manager, registry client, normalizer, rules, service, store
- `index.html`: single-page dashboard UI
- `tests/`: unit and API tests
