# Dev Dashboard

A local web dashboard that scans your macOS system and displays all installed **IDEs**, **LLMs & coding agents**, and **MCP configurations** in a clean, dark-themed UI.

![Python](https://img.shields.io/badge/python-3.6+-blue) ![macOS](https://img.shields.io/badge/platform-macOS-lightgrey) ![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)

## Features

- **IDE Detection** — Finds all installed IDEs and editors (VS Code, Cursor, Xcode, JetBrains, Zed, Windsurf, etc.) with version info and running status
- **LLM & Agent Detection** — Discovers CLI tools (Claude, Ollama, Aider), IDE extensions (Copilot, Claude Code, ChatGPT), local models, and running AI processes
- **MCP Configuration Scanner** — Reads MCP server configs from Claude Desktop, Claude Code, Cursor, VS Code, Windsurf, and Cline
- **Zero Dependencies** — Uses only Python standard library
- **Auto-Refresh** — Dashboard updates every 30 seconds
- **Dark Theme** — Developer-friendly card-based UI

## Quick Start

```bash
python3 dashboard.py
```

Opens `http://localhost:8420` in your default browser.

## How It Works

The dashboard is two files:

| File | Purpose |
|------|---------|
| `dashboard.py` | Python HTTP server with system detection logic |
| `index.html` | Single-page dashboard with inline CSS/JS |

### API Endpoints

| Route | Description |
|-------|-------------|
| `GET /` | Serves the dashboard UI |
| `GET /api/all` | All detection data + timestamp |
| `GET /api/ides` | IDEs and editors only |
| `GET /api/llms` | LLMs and coding agents only |
| `GET /api/mcp` | MCP configurations only |

### Detection Methods

**IDEs**: Scans `/Applications/` for known app bundles, checks versions via `mdls`/`defaults read`, detects running status via `pgrep`, finds terminal editors via `which`.

**LLMs**: Checks for CLI tools (`claude`, `ollama`, `aider`, etc.), scans VS Code and Cursor extension directories for AI extensions, monitors running AI processes, lists local models from Ollama and LM Studio.

**MCP Configs**: Reads configuration files from all known locations:
- Claude Desktop: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Claude Code: `~/.claude.json`
- Cursor: `~/.cursor/mcp.json`
- VS Code: `.vscode/mcp.json`
- Windsurf: `~/.codeium/windsurf/mcp_config.json`
- Cline: `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
- Project-level configs in common directories

## Requirements

- macOS
- Python 3.6+ (included with Xcode Command Line Tools)

## License

MIT
