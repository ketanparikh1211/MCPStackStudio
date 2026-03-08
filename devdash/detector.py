"""System detectors for IDEs, LLM tooling, and MCP configuration files."""

from __future__ import annotations

import glob
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

HOME = str(Path.home())


def _run_cmd(cmd: str, timeout: int = 5) -> str:
    """Run a shell command and return stdout, or an empty string on failure."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _cmd_exists(cmd: str) -> bool:
    return bool(_run_cmd(f"which {cmd} 2>/dev/null"))


def _get_app_version(app_path: str) -> str:
    ver = _run_cmd(f'mdls -name kMDItemVersion -raw "{app_path}" 2>/dev/null')
    if ver and ver != "(null)":
        return ver
    plist = f"{app_path}/Contents/Info.plist"
    ver = _run_cmd(f'defaults read "{plist}" CFBundleShortVersionString 2>/dev/null')
    return ver or "unknown"


def _is_app_running(app_name: str) -> bool:
    bundle = app_name.replace(".app", "")
    if _run_cmd(f'pgrep -xi "{bundle}" 2>/dev/null'):
        return True
    ps_output = _run_cmd("ps aux")
    return f"{app_name}/Contents" in ps_output


KNOWN_IDES = {
    "Visual Studio Code.app": {"name": "VS Code", "icon": "vscode"},
    "Cursor.app": {"name": "Cursor", "icon": "cursor"},
    "Xcode.app": {"name": "Xcode", "icon": "xcode"},
    "Sublime Text.app": {"name": "Sublime Text", "icon": "sublime"},
    "WebStorm.app": {"name": "WebStorm", "icon": "jetbrains"},
    "IntelliJ IDEA.app": {"name": "IntelliJ IDEA", "icon": "jetbrains"},
    "IntelliJ IDEA CE.app": {"name": "IntelliJ IDEA CE", "icon": "jetbrains"},
    "PyCharm.app": {"name": "PyCharm", "icon": "jetbrains"},
    "PyCharm CE.app": {"name": "PyCharm CE", "icon": "jetbrains"},
    "GoLand.app": {"name": "GoLand", "icon": "jetbrains"},
    "CLion.app": {"name": "CLion", "icon": "jetbrains"},
    "Rider.app": {"name": "Rider", "icon": "jetbrains"},
    "DataGrip.app": {"name": "DataGrip", "icon": "jetbrains"},
    "Zed.app": {"name": "Zed", "icon": "zed"},
    "Nova.app": {"name": "Nova", "icon": "nova"},
    "Fleet.app": {"name": "Fleet", "icon": "jetbrains"},
    "Android Studio.app": {"name": "Android Studio", "icon": "android"},
    "Windsurf.app": {"name": "Windsurf", "icon": "windsurf"},
    "Trae.app": {"name": "Trae", "icon": "trae"},
    "PearAI.app": {"name": "PearAI", "icon": "pearai"},
    "Void.app": {"name": "Void", "icon": "void"},
    "Warp.app": {"name": "Warp", "icon": "warp"},
    "Atom.app": {"name": "Atom", "icon": "atom"},
    "RustRover.app": {"name": "RustRover", "icon": "jetbrains"},
}

KNOWN_AI_APPS = {
    "Claude.app": {"name": "Claude Desktop", "icon": "claude"},
    "ChatGPT.app": {"name": "ChatGPT Desktop", "icon": "chatgpt"},
    "Gemini.app": {"name": "Gemini Desktop", "icon": "gemini"},
    "Codex.app": {"name": "Codex Desktop", "icon": "codex"},
    "LM Studio.app": {"name": "LM Studio", "icon": "lmstudio"},
    "Pieces.app": {"name": "Pieces Desktop", "icon": "pieces"},
    "Jan.app": {"name": "Jan", "icon": "jan"},
    "Msty.app": {"name": "Msty", "icon": "default"},
}

CLI_TOOLS = [
    ("claude", "Claude CLI", "claude"),
    ("gemini", "Gemini CLI", "gemini"),
    ("codex", "Codex CLI", "codex"),
    ("ollama", "Ollama", "ollama"),
    ("aider", "Aider", "aider"),
    ("antigravity", "Antigravity", "antigravity"),
    ("opencode", "OpenCode", "opencode"),
    ("goose", "Goose", "goose"),
    ("amp", "Amp (Sourcegraph)", "amp"),
    ("cody", "Cody CLI", "cody"),
    ("lms", "LM Studio CLI", "lmstudio"),
    ("sgpt", "ShellGPT", "openai"),
    ("trae", "Trae CLI", "trae"),
    ("pieces", "Pieces CLI", "pieces"),
    ("tabby", "Tabby", "tabby"),
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
    "supermaven.supermaven",
    "augment.",
    "pieces.",
    "google.gemini",
    "codium.",
    "blackboxapp.",
    "cursor.",
]

MCP_LOCATIONS = [
    {
        "name": "Claude Desktop",
        "path": os.path.join(HOME, "Library", "Application Support", "Claude", "claude_desktop_config.json"),
        "key": "mcpServers",
        "scope": "global",
    },
    {
        "name": "Claude Code (global)",
        "path": os.path.join(HOME, ".claude.json"),
        "key": "mcpServers",
        "scope": "global",
    },
    {
        "name": "Cursor (global)",
        "path": os.path.join(HOME, ".cursor", "mcp.json"),
        "key": "mcpServers",
        "scope": "global",
    },
    {
        "name": "VS Code (global)",
        "path": os.path.join(HOME, ".vscode", "mcp.json"),
        "key": "servers",
        "scope": "global",
    },
    {
        "name": "Windsurf",
        "path": os.path.join(HOME, ".codeium", "windsurf", "mcp_config.json"),
        "key": "mcpServers",
        "scope": "global",
    },
    {
        "name": "Zed",
        "path": os.path.join(HOME, ".config", "zed", "settings.json"),
        "key": "context_servers",
        "scope": "global",
    },
    {
        "name": "Trae",
        "path": os.path.join(HOME, ".trae", "mcp.json"),
        "key": "mcpServers",
        "scope": "global",
    },
    {
        "name": "Cline (VS Code)",
        "path": os.path.join(
            HOME,
            "Library",
            "Application Support",
            "Code",
            "User",
            "globalStorage",
            "saoudrizwan.claude-dev",
            "settings",
            "cline_mcp_settings.json",
        ),
        "key": "mcpServers",
        "scope": "global",
    },
    {
        "name": "Roo Code (VS Code)",
        "path": os.path.join(
            HOME,
            "Library",
            "Application Support",
            "Code",
            "User",
            "globalStorage",
            "rooveterinaryinc.roo-cline",
            "settings",
            "mcp_settings.json",
        ),
        "key": "mcpServers",
        "scope": "global",
    },
    {
        "name": "Continue",
        "path": os.path.join(HOME, ".continue", "config.json"),
        "key": "mcpServers",
        "scope": "global",
    },
]


def detect_ides() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    for app_name, info in KNOWN_IDES.items():
        app_path = f"/Applications/{app_name}"
        if os.path.exists(app_path):
            results.append(
                {
                    "name": info["name"],
                    "path": app_path,
                    "version": _get_app_version(app_path),
                    "running": _is_app_running(app_name),
                    "icon": info["icon"],
                    "type": "ide",
                }
            )

    xcode_path = _run_cmd("xcode-select -p 2>/dev/null")
    if xcode_path:
        results.append(
            {
                "name": "Xcode CLI Tools",
                "path": xcode_path,
                "version": _run_cmd(
                    "pkgutil --pkg-info=com.apple.pkg.CLTools_Executables 2>/dev/null | grep version | awk '{print $2}'"
                )
                or "installed",
                "running": False,
                "icon": "xcode",
                "type": "cli-tool",
            }
        )

    for cmd, name, icon in [
        ("vim", "Vim", "vim"),
        ("nvim", "Neovim", "neovim"),
        ("emacs", "Emacs", "emacs"),
    ]:
        path = _run_cmd(f"which {cmd} 2>/dev/null")
        if path:
            ver = _run_cmd(f"{cmd} --version 2>/dev/null | head -1")
            results.append(
                {
                    "name": name,
                    "path": path,
                    "version": ver[:100],
                    "running": False,
                    "icon": icon,
                    "type": "terminal-editor",
                }
            )

    return results


def detect_llms() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    for app_name, info in KNOWN_AI_APPS.items():
        app_path = f"/Applications/{app_name}"
        if os.path.exists(app_path):
            results.append(
                {
                    "name": info["name"],
                    "path": app_path,
                    "version": _get_app_version(app_path),
                    "status": "installed",
                    "icon": info["icon"],
                    "type": "desktop-app",
                }
            )

    for cmd, name, icon in CLI_TOOLS:
        path = _run_cmd(f"which {cmd} 2>/dev/null")
        if path:
            ver = _run_cmd(f"{cmd} --version 2>/dev/null")
            results.append(
                {
                    "name": name,
                    "path": path,
                    "version": (ver.split("\n")[0] if ver else "")[:100],
                    "status": "installed",
                    "icon": icon,
                    "type": "cli",
                }
            )

    gh_copilot = _run_cmd("gh copilot --version 2>/dev/null")
    if gh_copilot:
        results.append(
            {
                "name": "GitHub Copilot CLI",
                "path": _run_cmd("which gh 2>/dev/null") or "gh",
                "version": gh_copilot.split("\n")[0][:100],
                "status": "installed",
                "icon": "github",
                "type": "cli",
            }
        )

    ps_output = _run_cmd("ps aux")
    for pattern in ["ollama serve", "lmstudio", "LM Studio", "Copilot"]:
        if pattern.lower() in ps_output.lower():
            results.append(
                {
                    "name": pattern,
                    "path": "",
                    "version": "",
                    "status": "running",
                    "icon": "process",
                    "type": "process",
                }
            )

    ext_dirs = [
        (os.path.join(HOME, ".vscode", "extensions"), "VS Code"),
        (os.path.join(HOME, ".cursor", "extensions"), "Cursor"),
        (os.path.join(HOME, ".windsurf", "extensions"), "Windsurf"),
        (os.path.join(HOME, ".trae", "extensions"), "Trae"),
    ]
    for ext_dir, ide_name in ext_dirs:
        if not os.path.isdir(ext_dir):
            continue
        try:
            for entry in os.listdir(ext_dir):
                lowered = entry.lower()
                for prefix in AI_EXTENSION_PREFIXES:
                    if lowered.startswith(prefix.lower()):
                        parts = entry.rsplit("-", 1)
                        ext_name = parts[0]
                        ext_ver = parts[1] if len(parts) > 1 else ""
                        results.append(
                            {
                                "name": ext_name,
                                "path": os.path.join(ext_dir, entry),
                                "version": ext_ver,
                                "status": "installed",
                                "host": ide_name,
                                "icon": "extension",
                                "type": "extension",
                            }
                        )
                        break
        except OSError:
            pass

    if _cmd_exists("ollama"):
        models = _run_cmd("ollama list 2>/dev/null")
        if models:
            for line in models.split("\n")[1:]:
                parts = line.split()
                if parts:
                    results.append(
                        {
                            "name": parts[0],
                            "path": "",
                            "version": parts[1] if len(parts) > 1 else "",
                            "status": "available",
                            "icon": "model",
                            "type": "local-model",
                        }
                    )

    lm_dir = os.path.join(HOME, ".cache", "lm-studio", "models")
    if os.path.isdir(lm_dir):
        try:
            for entry in os.listdir(lm_dir):
                if not entry.startswith("."):
                    results.append(
                        {
                            "name": entry,
                            "path": os.path.join(lm_dir, entry),
                            "version": "",
                            "status": "downloaded",
                            "icon": "model",
                            "type": "local-model",
                        }
                    )
        except OSError:
            pass

    return results


def _extract_servers(data: Dict[str, Any], key: str) -> Dict[str, Any]:
    if key in data and isinstance(data.get(key), dict):
        return data.get(key, {})

    # Some tools place servers under nested keys.
    if key == "context_servers" and isinstance(data.get("context_servers"), dict):
        return data.get("context_servers", {})

    if isinstance(data.get("mcp"), dict):
        nested = data["mcp"]
        for nested_key in ["servers", "mcpServers", "context_servers"]:
            if isinstance(nested.get(nested_key), dict):
                return nested[nested_key]

    return {}


def _project_key_from_path(path: str, data: Dict[str, Any]) -> str:
    if isinstance(data.get("mcpServers"), dict):
        return "mcpServers"
    if isinstance(data.get("servers"), dict):
        return "servers"
    if isinstance(data.get("context_servers"), dict):
        return "context_servers"
    if "/.vscode/" in path:
        return "servers"
    return "mcpServers"


def detect_mcp() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    for location in MCP_LOCATIONS:
        entry: Dict[str, Any] = {
            "name": location["name"],
            "path": location["path"],
            "key": location.get("key", "mcpServers"),
            "exists": os.path.exists(location["path"]),
            "servers": [],
            "serverCount": 0,
            "error": None,
            "scope": location.get("scope", "unknown"),
        }

        if entry["exists"]:
            try:
                with open(location["path"], "r", encoding="utf-8") as handle:
                    data = json.load(handle)

                servers_data = _extract_servers(data, location["key"])

                if location["name"] == "Claude Code (global)" and not servers_data:
                    projects = data.get("projects", {}) if isinstance(data, dict) else {}
                    if isinstance(projects, dict):
                        for proj_path, proj_conf in projects.items():
                            if not isinstance(proj_conf, dict):
                                continue
                            proj_servers = proj_conf.get("mcpServers", {})
                            if isinstance(proj_servers, dict):
                                for s_name, s_conf in proj_servers.items():
                                    if not isinstance(s_conf, dict):
                                        continue
                                    entry["servers"].append(
                                        {
                                            "name": s_name,
                                            "command": s_conf.get("command", ""),
                                            "args": s_conf.get("args", []),
                                            "env": list((s_conf.get("env", {}) or {}).keys()),
                                            "project": proj_path,
                                            "scope": "project",
                                        }
                                    )

                if isinstance(servers_data, dict):
                    for s_name, s_conf in servers_data.items():
                        if isinstance(s_conf, dict):
                            entry["servers"].append(
                                {
                                    "name": s_name,
                                    "command": s_conf.get("command", ""),
                                    "args": s_conf.get("args", []),
                                    "env": list((s_conf.get("env", {}) or {}).keys()),
                                    "scope": entry["scope"],
                                }
                            )

                entry["serverCount"] = len(entry["servers"])
            except json.JSONDecodeError as exc:
                entry["error"] = f"Invalid JSON: {exc}"
            except OSError as exc:
                entry["error"] = f"Unreadable file: {exc}"
            except Exception as exc:
                entry["error"] = str(exc)

        results.append(entry)

    scan_dirs = ["", "Developer", "Projects", "Desktop", "repos", "code", "src", "work"]
    project_patterns: List[str] = []
    for directory in scan_dirs:
        base = os.path.join(HOME, directory, "*") if directory else os.path.join(HOME, "*")
        project_patterns.append(os.path.join(base, ".cursor", "mcp.json"))
        project_patterns.append(os.path.join(base, ".vscode", "mcp.json"))

    for pattern in project_patterns:
        for match in glob.glob(pattern):
            try:
                with open(match, "r", encoding="utf-8") as handle:
                    data = json.load(handle)

                servers = {}
                if isinstance(data, dict):
                    servers = data.get("mcpServers", data.get("servers", {}))
                project_key = _project_key_from_path(match, data if isinstance(data, dict) else {})

                if isinstance(servers, dict):
                    short_path = match.replace(HOME, "~")
                    results.append(
                        {
                            "name": f"Project: {short_path}",
                            "path": match,
                            "key": project_key,
                            "exists": True,
                            "servers": [
                                {
                                    "name": key,
                                    "command": value.get("command", "") if isinstance(value, dict) else "",
                                    "args": value.get("args", []) if isinstance(value, dict) else [],
                                    "env": list((value.get("env", {}) or {}).keys()) if isinstance(value, dict) else [],
                                    "scope": "project",
                                    "project": os.path.dirname(os.path.dirname(match)),
                                }
                                for key, value in servers.items()
                            ],
                            "serverCount": len(servers),
                            "error": None,
                            "scope": "project",
                        }
                    )
            except json.JSONDecodeError as exc:
                results.append(
                    {
                            "name": f"Project: {match.replace(HOME, '~')}",
                            "path": match,
                            "key": "servers" if "/.vscode/" in match else "mcpServers",
                            "exists": True,
                            "servers": [],
                        "serverCount": 0,
                        "error": f"Invalid JSON: {exc}",
                        "scope": "project",
                    }
                )
            except OSError as exc:
                results.append(
                    {
                            "name": f"Project: {match.replace(HOME, '~')}",
                            "path": match,
                            "key": "servers" if "/.vscode/" in match else "mcpServers",
                            "exists": True,
                        "servers": [],
                        "serverCount": 0,
                        "error": f"Unreadable file: {exc}",
                        "scope": "project",
                    }
                )

    return results
