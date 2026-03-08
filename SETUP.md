# Setup Guide

This guide matches the current Phase 2 build (MCP Studio + catalog aggregation).

## Prerequisites

- macOS
- Python 3.9+

## 1. Open project directory

```bash
cd /Users/ketanparikh/Desktop/Rep/MCPStackStudio
```

## 2. Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

## 3. Start the dashboard

```bash
python3 dashboard.py
```

Open:

```text
http://127.0.0.1:8420
```

## 4. Use MCP Studio

Inside the dashboard:

- Open `MCP Studio`
- Use `Add MCP` to create a server entry
- Use `Edit` or `Delete` on existing server chips
- Use `All MCPs` catalog and click `Prefill Add` for quick add flows

Write safety:

- Every MCP config mutation creates a local backup file:
  - `<target-config>.bak.<timestamp>`
- Writes are done through atomic replace

## Optional CLI Commands

Run one scan and persist snapshot:

```bash
python3 dashboard.py scan
```

Export reports:

```bash
python3 dashboard.py export --format md --output ./reports/latest.md
python3 dashboard.py export --format json --output ./reports/latest.json
```

## LAN Mode (token protected)

For non-loopback host binding, set a token.

```bash
export MCPSTACKSTUDIO_TOKEN="your-shared-token"
python3 dashboard.py serve --host 0.0.0.0 --port 8420
```

Remote requests must include:

```text
X-DevDash-Token: your-shared-token
```

## Catalog Data Sources

Catalog endpoint uses:

1. `https://github.com/mcp` (primary)
2. `https://registry.modelcontextprotocol.io/v0.1/servers` (supplement and fallback)

UI defaults to `mode=all` so you can see broad MCP coverage.

## Useful API Checks

```bash
curl http://127.0.0.1:8420/health
curl "http://127.0.0.1:8420/api/mcp/catalog/new?mode=all&limit=50"
curl http://127.0.0.1:8420/api/mcp/targets
```

## Run Tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Stop the app

Press `Ctrl + C` in the terminal.

## Troubleshooting

Check Python version:

```bash
python3 --version
```

If port `8420` is in use:

```bash
lsof -i :8420
```

If imports fail:

```bash
python3 -m pip install -r requirements.txt --upgrade
```
