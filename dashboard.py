#!/usr/bin/env python3
"""Developer Dashboard — Local system scanner for IDEs, LLMs, and MCP configs."""

import http.server
import json
import subprocess
import os
import glob
import webbrowser
from pathlib import Path
from datetime import datetime

PORT = 8420
HOME = str(Path.home())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_cmd(cmd, timeout=5):
    """Run a shell command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _cmd_exists(cmd):
    return _run_cmd(f"which {cmd} 2>/dev/null") is not None


def _get_app_version(app_path):
    """Get version from a macOS .app bundle."""
    ver = _run_cmd(f'mdls -name kMDItemVersion -raw "{app_path}" 2>/dev/null')
    if ver and ver != "(null)":
        return ver
    plist = f"{app_path}/Contents/Info.plist"
    ver = _run_cmd(f'defaults read "{plist}" CFBundleShortVersionString 2>/dev/null')
    return ver or "unknown"


def _is_app_running(app_name):
    """Check if an app process is running."""
    bundle = app_name.replace(".app", "")
    # Try pgrep first
    result = _run_cmd(f'pgrep -xi "{bundle}" 2>/dev/null')
    if result:
        return True
    # Fallback: check ps for the .app path
    ps = _run_cmd("ps aux") or ""
    return f"{app_name}/Contents" in ps


# ---------------------------------------------------------------------------
# Detection: IDEs & Editors
# ---------------------------------------------------------------------------

KNOWN_IDES = {
    "Visual Studio Code.app": {"name": "VS Code", "icon": "vscode"},
    "Cursor.app": {"name": "Cursor", "icon": "cursor"},
    "Codex.app": {"name": "Codex", "icon": "codex"},
    "Claude.app": {"name": "Claude Desktop", "icon": "claude"},
    "Xcode.app": {"name": "Xcode", "icon": "xcode"},
    "Sublime Text.app": {"name": "Sublime Text", "icon": "sublime"},
    "WebStorm.app": {"name": "WebStorm", "icon": "jetbrains"},
    "IntelliJ IDEA.app": {"name": "IntelliJ IDEA", "icon": "jetbrains"},
    "IntelliJ IDEA CE.app": {"name": "IntelliJ IDEA CE", "icon": "jetbrains"},
    "PyCharm.app": {"name": "PyCharm", "icon": "jetbrains"},
    "PyCharm CE.app": {"name": "PyCharm CE", "icon": "jetbrains"},
    "GoLand.app": {"name": "GoLand", "icon": "jetbrains"},
    "Zed.app": {"name": "Zed", "icon": "zed"},
    "Nova.app": {"name": "Nova", "icon": "nova"},
    "Fleet.app": {"name": "Fleet", "icon": "jetbrains"},
    "Android Studio.app": {"name": "Android Studio", "icon": "android"},
    "Windsurf.app": {"name": "Windsurf", "icon": "windsurf"},
    "LM Studio.app": {"name": "LM Studio", "icon": "lmstudio"},
    "Atom.app": {"name": "Atom", "icon": "atom"},
    "RustRover.app": {"name": "RustRover", "icon": "jetbrains"},
}


def detect_ides():
    results = []

    # Scan /Applications for known IDE bundles
    for app_name, info in KNOWN_IDES.items():
        app_path = f"/Applications/{app_name}"
        if os.path.exists(app_path):
            results.append({
                "name": info["name"],
                "path": app_path,
                "version": _get_app_version(app_path),
                "running": _is_app_running(app_name),
                "icon": info["icon"],
                "type": "ide",
            })

    # Xcode CLI tools
    xcode_path = _run_cmd("xcode-select -p 2>/dev/null")
    if xcode_path:
        results.append({
            "name": "Xcode CLI Tools",
            "path": xcode_path,
            "version": _run_cmd("pkgutil --pkg-info=com.apple.pkg.CLTools_Executables 2>/dev/null | grep version | awk '{print $2}'") or "installed",
            "running": False,
            "icon": "xcode",
            "type": "cli-tool",
        })

    # Terminal editors
    for cmd, name, icon in [("vim", "Vim", "terminal"), ("nvim", "Neovim", "terminal"), ("emacs", "Emacs", "terminal")]:
        path = _run_cmd(f"which {cmd} 2>/dev/null")
        if path:
            ver = _run_cmd(f"{cmd} --version 2>/dev/null | head -1") or ""
            results.append({
                "name": name,
                "path": path,
                "version": ver[:80],
                "running": False,
                "icon": icon,
                "type": "terminal-editor",
            })

    return results


# ---------------------------------------------------------------------------
# Detection: LLMs & Coding Agents
# ---------------------------------------------------------------------------

CLI_TOOLS = [
    ("claude", "Claude CLI", "claude"),
    ("ollama", "Ollama", "ollama"),
    ("aider", "Aider", "aider"),
    ("lms", "LM Studio CLI", "lmstudio"),
    ("sgpt", "ShellGPT", "openai"),
    ("opencode", "OpenCode", "opencode"),
    ("goose", "Goose", "goose"),
]

AI_EXTENSION_PREFIXES = [
    "anthropic.claude",
    "github.copilot",
    "openai.chatgpt",
    "continue.continue",
    "saoudrizwan.claude-dev",
    "sourcegraph.cody",
    "codeium.",
    "tabnine.",
    "amazonwebservices.amazon-q",
    "rooveterinaryinc.roo",
]


def detect_llms():
    results = []

    # CLI tools
    for cmd, name, icon in CLI_TOOLS:
        path = _run_cmd(f"which {cmd} 2>/dev/null")
        if path:
            ver = _run_cmd(f"{cmd} --version 2>/dev/null") or ""
            # Some tools output multi-line version; take first line
            ver = ver.split("\n")[0][:100]
            results.append({
                "name": name,
                "path": path,
                "version": ver,
                "status": "installed",
                "icon": icon,
                "type": "cli",
            })

    # Running AI processes
    ps_output = _run_cmd("ps aux") or ""
    ai_procs = ["ollama serve", "lmstudio", "LM Studio", "Copilot"]
    for pattern in ai_procs:
        if pattern.lower() in ps_output.lower():
            results.append({
                "name": f"{pattern}",
                "path": "",
                "version": "",
                "status": "running",
                "icon": "process",
                "type": "process",
            })

    # IDE extensions
    ext_dirs = [
        (os.path.join(HOME, ".vscode", "extensions"), "VS Code"),
        (os.path.join(HOME, ".cursor", "extensions"), "Cursor"),
    ]
    for ext_dir, ide_name in ext_dirs:
        if not os.path.isdir(ext_dir):
            continue
        try:
            for entry in os.listdir(ext_dir):
                entry_lower = entry.lower()
                for prefix in AI_EXTENSION_PREFIXES:
                    if entry_lower.startswith(prefix.lower()):
                        parts = entry.rsplit("-", 1)
                        ext_name = parts[0]
                        ext_ver = parts[1] if len(parts) > 1 else ""
                        results.append({
                            "name": ext_name,
                            "path": os.path.join(ext_dir, entry),
                            "version": ext_ver,
                            "status": "installed",
                            "host": ide_name,
                            "icon": "extension",
                            "type": "extension",
                        })
                        break
        except OSError:
            pass

    # Ollama models
    if _cmd_exists("ollama"):
        models = _run_cmd("ollama list 2>/dev/null")
        if models:
            for line in models.strip().split("\n")[1:]:
                parts = line.split()
                if parts:
                    results.append({
                        "name": parts[0],
                        "path": "",
                        "version": parts[1] if len(parts) > 1 else "",
                        "status": "available",
                        "icon": "model",
                        "type": "local-model",
                    })

    # LM Studio models
    lm_dir = os.path.join(HOME, ".cache", "lm-studio", "models")
    if os.path.isdir(lm_dir):
        try:
            for d in os.listdir(lm_dir):
                if not d.startswith("."):
                    results.append({
                        "name": d,
                        "path": os.path.join(lm_dir, d),
                        "version": "",
                        "status": "downloaded",
                        "icon": "model",
                        "type": "local-model",
                    })
        except OSError:
            pass

    return results


# ---------------------------------------------------------------------------
# Detection: MCP Configurations
# ---------------------------------------------------------------------------

MCP_LOCATIONS = [
    {
        "name": "Claude Desktop",
        "path": os.path.join(HOME, "Library", "Application Support", "Claude", "claude_desktop_config.json"),
        "key": "mcpServers",
    },
    {
        "name": "Claude Code (global)",
        "path": os.path.join(HOME, ".claude.json"),
        "key": "mcpServers",
    },
    {
        "name": "Cursor (global)",
        "path": os.path.join(HOME, ".cursor", "mcp.json"),
        "key": "mcpServers",
    },
    {
        "name": "VS Code (workspace)",
        "path": os.path.join(HOME, ".vscode", "mcp.json"),
        "key": "servers",
    },
    {
        "name": "Windsurf",
        "path": os.path.join(HOME, ".codeium", "windsurf", "mcp_config.json"),
        "key": "mcpServers",
    },
    {
        "name": "Cline (VS Code)",
        "path": os.path.join(
            HOME, "Library", "Application Support", "Code", "User",
            "globalStorage", "saoudrizwan.claude-dev", "settings",
            "cline_mcp_settings.json"
        ),
        "key": "mcpServers",
    },
]


def detect_mcp():
    results = []

    for loc in MCP_LOCATIONS:
        entry = {
            "name": loc["name"],
            "path": loc["path"],
            "exists": os.path.exists(loc["path"]),
            "servers": [],
            "serverCount": 0,
            "error": None,
        }

        if entry["exists"]:
            try:
                with open(loc["path"], "r") as f:
                    data = json.load(f)

                # Navigate nested keys for Claude Code (.claude.json has projects -> path -> mcpServers)
                servers_data = data.get(loc["key"], {})

                # For .claude.json, also check inside projects
                if loc["name"] == "Claude Code (global)" and not servers_data:
                    projects = data.get("projects", {})
                    for proj_path, proj_conf in projects.items():
                        proj_servers = proj_conf.get("mcpServers", {})
                        if proj_servers:
                            for sname, sconf in proj_servers.items():
                                entry["servers"].append({
                                    "name": sname,
                                    "command": sconf.get("command", ""),
                                    "args": sconf.get("args", []),
                                    "env": list(sconf.get("env", {}).keys()),
                                    "project": proj_path,
                                })

                if isinstance(servers_data, dict):
                    for sname, sconf in servers_data.items():
                        if isinstance(sconf, dict):
                            entry["servers"].append({
                                "name": sname,
                                "command": sconf.get("command", ""),
                                "args": sconf.get("args", []),
                                "env": list(sconf.get("env", {}).keys()),
                            })

                entry["serverCount"] = len(entry["servers"])
            except json.JSONDecodeError as e:
                entry["error"] = f"Invalid JSON: {e}"
            except Exception as e:
                entry["error"] = str(e)

        results.append(entry)

    # Scan for project-level MCP configs
    project_patterns = [
        os.path.join(HOME, "*", ".cursor", "mcp.json"),
        os.path.join(HOME, "*", ".vscode", "mcp.json"),
        os.path.join(HOME, "Developer", "*", ".cursor", "mcp.json"),
        os.path.join(HOME, "Developer", "*", ".vscode", "mcp.json"),
        os.path.join(HOME, "Projects", "*", ".cursor", "mcp.json"),
        os.path.join(HOME, "Projects", "*", ".vscode", "mcp.json"),
    ]

    for pattern in project_patterns:
        for match in glob.glob(pattern):
            try:
                with open(match, "r") as f:
                    data = json.load(f)
                servers = data.get("mcpServers", data.get("servers", {}))
                if servers and isinstance(servers, dict):
                    short = match.replace(HOME, "~")
                    results.append({
                        "name": f"Project: {short}",
                        "path": match,
                        "exists": True,
                        "servers": [
                            {
                                "name": k,
                                "command": v.get("command", "") if isinstance(v, dict) else "",
                                "args": v.get("args", []) if isinstance(v, dict) else [],
                                "env": list(v.get("env", {}).keys()) if isinstance(v, dict) else [],
                            }
                            for k, v in servers.items()
                        ],
                        "serverCount": len(servers),
                        "error": None,
                    })
            except Exception:
                pass

    return results


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self._serve_html()
        elif self.path == "/api/all":
            self._json_response({
                "ides": detect_ides(),
                "llms": detect_llms(),
                "mcp": detect_mcp(),
                "timestamp": datetime.now().isoformat(),
            })
        elif self.path == "/api/ides":
            self._json_response(detect_ides())
        elif self.path == "/api/llms":
            self._json_response(detect_llms())
        elif self.path == "/api/mcp":
            self._json_response(detect_mcp())
        else:
            self.send_error(404)

    def _serve_html(self):
        html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
        try:
            with open(html_path, "r") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content.encode())
        except FileNotFoundError:
            self.send_error(500, "index.html not found")

    def _json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def log_message(self, format, *args):
        # Quieter logging
        pass


def main():
    server = http.server.HTTPServer(("localhost", PORT), DashboardHandler)
    url = f"http://localhost:{PORT}"
    print(f"\n  Developer Dashboard running at {url}\n")
    print("  Press Ctrl+C to stop.\n")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
