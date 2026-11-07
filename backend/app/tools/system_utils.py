import os
import re
import json
import shutil
import logging
import threading
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger("jarvis.system")

# Pre-defined mapping of common applications, utilities, and URI protocols
COMMON_APPS = {
    # Text & Code Editors
    "notepad": {"name": "Notepad", "target": "notepad.exe", "type": "executable"},
    "notes": {"name": "Notepad", "target": "notepad.exe", "type": "executable"},
    "vscode": {"name": "Visual Studio Code", "target": "code.cmd", "type": "executable"},
    "vs code": {"name": "Visual Studio Code", "target": "code.cmd", "type": "executable"},
    "code": {"name": "Visual Studio Code", "target": "code.cmd", "type": "executable"},
    "visual studio code": {"name": "Visual Studio Code", "target": "code.cmd", "type": "executable"},
    "sublime": {"name": "Sublime Text", "target": "sublime_text.exe", "type": "executable"},

    # Terminals & Command Lines
    "terminal": {"name": "Terminal", "target": "wt.exe", "type": "executable"},
    "wt": {"name": "Terminal", "target": "wt.exe", "type": "executable"},
    "windows terminal": {"name": "Terminal", "target": "wt.exe", "type": "executable"},
    "cmd": {"name": "Command Prompt", "target": "cmd.exe", "type": "executable"},
    "command prompt": {"name": "Command Prompt", "target": "cmd.exe", "type": "executable"},
    "powershell": {"name": "PowerShell", "target": "powershell.exe", "type": "executable"},

    # Utilities & System Tools
    "calculator": {"name": "Calculator", "target": "calc.exe", "type": "executable"},
    "calc": {"name": "Calculator", "target": "calc.exe", "type": "executable"},
    "paint": {"name": "Paint", "target": "mspaint.exe", "type": "executable"},
    "mspaint": {"name": "Paint", "target": "mspaint.exe", "type": "executable"},
    "task manager": {"name": "Task Manager", "target": "taskmgr.exe", "type": "executable"},
    "taskmgr": {"name": "Task Manager", "target": "taskmgr.exe", "type": "executable"},
    "settings": {"name": "Settings", "target": "ms-settings:", "type": "protocol"},
    "control panel": {"name": "Control Panel", "target": "control.exe", "type": "executable"},
    "snipping tool": {"name": "Snipping Tool", "target": "snippingtool.exe", "type": "executable"},
    "camera": {"name": "Camera", "target": "microsoft.windows.camera:", "type": "protocol"},
    "clock": {"name": "Clock", "target": "ms-clock:", "type": "protocol"},

    # File Explorer
    "explorer": {"name": "File Explorer", "target": "explorer.exe", "type": "executable"},
    "file explorer": {"name": "File Explorer", "target": "explorer.exe", "type": "executable"},
    "files": {"name": "File Explorer", "target": "explorer.exe", "type": "executable"},

    # Web Browsers
    "chrome": {"name": "Google Chrome", "target": "chrome.exe", "type": "executable"},
    "google chrome": {"name": "Google Chrome", "target": "chrome.exe", "type": "executable"},
    "edge": {"name": "Microsoft Edge", "target": "msedge.exe", "type": "executable"},
    "microsoft edge": {"name": "Microsoft Edge", "target": "msedge.exe", "type": "executable"},
    "browser": {"name": "Microsoft Edge", "target": "msedge.exe", "type": "executable"},
    "brave": {"name": "Brave Browser", "target": "brave.exe", "type": "executable"},
    "firefox": {"name": "Mozilla Firefox", "target": "firefox.exe", "type": "executable"},
    "opera": {"name": "Opera", "target": "opera.exe", "type": "executable"},

    # Social & Media
    "spotify": {"name": "Spotify", "target": "spotify:", "type": "protocol"},
    "discord": {"name": "Discord", "target": "discord.exe", "type": "executable"},
    "vlc": {"name": "VLC Media Player", "target": "vlc.exe", "type": "executable"},
    "telegram": {"name": "Telegram", "target": "telegram.exe", "type": "executable"},
    "whatsapp": {"name": "WhatsApp", "target": "whatsapp:", "type": "protocol"},
    "slack": {"name": "Slack", "target": "slack:", "type": "protocol"},
    "zoom": {"name": "Zoom", "target": "zoom.exe", "type": "executable"},

    # Creative & Productivity
    "word": {"name": "Microsoft Word", "target": "winword.exe", "type": "executable"},
    "excel": {"name": "Microsoft Excel", "target": "excel.exe", "type": "executable"},
    "powerpoint": {"name": "PowerPoint", "target": "powerpnt.exe", "type": "executable"},
    "onenote": {"name": "OneNote", "target": "onenote.exe", "type": "executable"},
    "obs": {"name": "OBS Studio", "target": "obs64.exe", "type": "executable"},
    "obs studio": {"name": "OBS Studio", "target": "obs64.exe", "type": "executable"},
    "blender": {"name": "Blender", "target": "blender.exe", "type": "executable"},
}

APP_ALIASES = {
    "insta": "instagram",
    "ig": "instagram",
    "wa": "whatsapp",
    "wp": "whatsapp",
    "yt": "youtube",
    "calc": "calculator",
    "code": "visual studio code",
    "vscode": "visual studio code",
    "vs code": "visual studio code",
    "term": "terminal",
    "wt": "terminal",
    "cmd": "command prompt",
    "notes": "notepad",
    "browser": "chrome",
    "gta": "playgtav",
    "gta 5": "playgtav",
    "gta v": "playgtav",
    "epic": "epic games launcher",
    "creative cloud": "adobe creative cloud",
}

APP_PROCESS_NAMES = {
    "notepad": "notepad.exe",
    "calculator": "CalculatorApp.exe",
    "calc": "CalculatorApp.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "browser": "msedge.exe",
    "vscode": "Code.exe",
    "vs code": "Code.exe",
    "code": "Code.exe",
    "visual studio code": "Code.exe",
    "paint": "mspaint.exe",
    "spotify": "Spotify.exe",
    "discord": "Discord.exe",
    "steam": "steam.exe",
    "vlc": "vlc.exe",
    "telegram": "Telegram.exe",
    "whatsapp": "WhatsApp.exe",
    "slack": "slack.exe",
    "zoom": "Zoom.exe",
    "teams": "ms-teams.exe",
    "word": "WINWORD.EXE",
    "excel": "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE",
    "acrobat": "Acrobat.exe",
    "obs": "obs64.exe",
    "blender": "blender.exe",
    "task manager": "Taskmgr.exe",
    "taskmgr": "Taskmgr.exe",
    "terminal": "WindowsTerminal.exe",
    "wt": "WindowsTerminal.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "instagram": "Instagram.exe",
    "canva": "Canva.exe",
    "capcut": "CapCut.exe",
}

# In-memory application registry cache
_INSTALLED_APPS_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "installed_apps.json"
_APP_SHORTCUT_CACHE: Dict[str, str] = {}
_LAST_SHORTCUT_TIME: float = 0


def load_installed_apps_cache() -> Dict[str, Dict[str, Any]]:
    """Loads the installed applications index from memory or disk in < 1ms."""
    global _INSTALLED_APPS_CACHE
    with _CACHE_LOCK:
        if _INSTALLED_APPS_CACHE:
            return _INSTALLED_APPS_CACHE

        if _CACHE_FILE.exists():
            try:
                with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                    _INSTALLED_APPS_CACHE = json.load(f)
                    return _INSTALLED_APPS_CACHE
            except Exception as e:
                logger.warning(f"Failed to read apps cache: {e}")

        return {}


def refresh_installed_apps_cache() -> Dict[str, Dict[str, Any]]:
    """
    Scans Windows via PowerShell Get-StartApps and Start Menu shortcuts,
    indexing all Win32, UWP, and Windows Store apps. Saves to disk.
    """
    global _INSTALLED_APPS_CACHE
    apps_map: Dict[str, Dict[str, Any]] = {}

    # 1. Query Windows StartApps (Store apps + Desktop apps)
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=10.0)
        if res.returncode == 0 and res.stdout.strip():
            raw_data = json.loads(res.stdout)
            if isinstance(raw_data, dict):
                raw_data = [raw_data]
            for item in raw_data:
                name = item.get("Name", "").strip()
                appid = item.get("AppID", "").strip()
                if name and appid:
                    key = name.lower()
                    is_store = "!" in appid or "microsoft.autogenerated" not in appid.lower()
                    apps_map[key] = {
                        "name": name,
                        "appid": appid,
                        "type": "store" if is_store else "desktop"
                    }
    except Exception as e:
        logger.warning(f"Error querying Get-StartApps: {e}")

    # 2. Merge with Desktop / Start Menu .lnk shortcuts
    try:
        shortcuts = get_installed_shortcuts()
        for s_name, s_path in shortcuts.items():
            if s_name not in apps_map:
                apps_map[s_name] = {
                    "name": s_name.title(),
                    "path": s_path,
                    "type": "shortcut"
                }
    except Exception as e:
        logger.warning(f"Error merging shortcuts: {e}")

    with _CACHE_LOCK:
        _INSTALLED_APPS_CACHE = apps_map

    # Persist cache to disk
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(apps_map, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to persist apps cache: {e}")

    return apps_map


def ensure_apps_indexed_background() -> None:
    """Launches a background daemon thread to refresh the apps cache without blocking."""
    # Load whatever we already have on disk first
    load_installed_apps_cache()
    # Refresh in background
    thread = threading.Thread(target=refresh_installed_apps_cache, daemon=True)
    thread.start()


def get_installed_shortcuts() -> Dict[str, str]:
    """Scans Desktop and Start Menu folders for installed .lnk and .url shortcuts."""
    global _APP_SHORTCUT_CACHE, _LAST_SHORTCUT_TIME
    now = time.time()
    if _APP_SHORTCUT_CACHE and (now - _LAST_SHORTCUT_TIME) < 300:
        return _APP_SHORTCUT_CACHE

    shortcuts: Dict[str, str] = {}
    user_home = Path.home()
    scan_dirs = [
        user_home / "Desktop",
        user_home / "OneDrive" / "Desktop",
        Path("C:/Users/Public/Desktop"),
        user_home / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs",
        Path("C:/ProgramData/Microsoft/Windows/Start Menu/Programs")
    ]

    for d in scan_dirs:
        try:
            if d.exists():
                for root, _, files in os.walk(d):
                    for f in files:
                        lower = f.lower()
                        if lower.endswith(".lnk") or lower.endswith(".url"):
                            name = f.rsplit(".", 1)[0].lower().strip()
                            if name not in shortcuts:
                                shortcuts[name] = str(Path(root) / f)
        except Exception:
            continue

    _APP_SHORTCUT_CACHE = shortcuts
    _LAST_SHORTCUT_TIME = now
    return _APP_SHORTCUT_CACHE


def clean_app_query(raw_name: str) -> str:
    """Cleans punctuation, conversational fillers, and generic suffixes ('app', 'application')."""
    clean = raw_name.strip().lower()
    # Remove surrounding quotes or punctuation
    clean = re.sub(r"^['\"]+|['\"]+$", "", clean).strip()
    # Remove generic filler words
    clean = re.sub(r"\b(?:application|app|game|program|software)\b", "", clean).strip()
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def find_app_target(app_name: str) -> Optional[Dict[str, Any]]:
    """
    Resolves an application name to an executable path, Store AppID, or URI.
    Returns structured dict or None if the application is not installed on the system.
    """
    clean = clean_app_query(app_name)
    if not clean:
        return None

    # Resolve alias if present (e.g. 'insta' -> 'instagram')
    lookup_name = APP_ALIASES.get(clean, clean)

    # 1. Check COMMON_APPS dictionary
    if lookup_name in COMMON_APPS:
        return COMMON_APPS[lookup_name]

    # 2. Check Installed Apps Index (Fast O(1) in-memory lookup)
    apps_cache = load_installed_apps_cache()
    if not apps_cache:
        # If cache was never loaded, try to load or refresh synchronously
        apps_cache = refresh_installed_apps_cache()

    # 2a. Exact match in installed apps
    if lookup_name in apps_cache:
        entry = apps_cache[lookup_name]
        return {
            "name": entry.get("name", lookup_name.title()),
            "target": entry.get("appid") or entry.get("path"),
            "type": entry.get("type", "store")
        }

    # 2b. Substring / Token match in installed apps
    for k, entry in apps_cache.items():
        if lookup_name == k or f" {lookup_name} " in f" {k} " or k.startswith(lookup_name):
            return {
                "name": entry.get("name", k.title()),
                "target": entry.get("appid") or entry.get("path"),
                "type": entry.get("type", "store")
            }

    # 2c. Reverse substring (e.g., 'chrome' matches 'google chrome')
    for k, entry in apps_cache.items():
        if lookup_name in k:
            return {
                "name": entry.get("name", k.title()),
                "target": entry.get("appid") or entry.get("path"),
                "type": entry.get("type", "store")
            }

    # 3. Match in desktop & start menu shortcuts
    shortcuts = get_installed_shortcuts()
    if lookup_name in shortcuts:
        return {
            "name": lookup_name.title(),
            "target": shortcuts[lookup_name],
            "type": "shortcut"
        }
    for s_name, s_path in shortcuts.items():
        if lookup_name in s_name or s_name in lookup_name:
            return {
                "name": s_name.title(),
                "target": s_path,
                "type": "shortcut"
            }

    # 4. Check system PATH via shutil.which
    which_path = shutil.which(lookup_name) or shutil.which(f"{lookup_name}.exe")
    if which_path:
        return {
            "name": lookup_name.title(),
            "target": which_path,
            "type": "executable"
        }

    # 5. Check common program directories
    program_dirs = [
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
        Path.home() / "AppData/Local/Programs",
        Path("C:/Riot Games"),
    ]
    for pdir in program_dirs:
        if pdir.exists():
            for candidate in [pdir / lookup_name, pdir / f"{lookup_name}.exe", pdir / lookup_name.title()]:
                if candidate.exists() and candidate.is_file():
                    return {
                        "name": candidate.stem,
                        "target": str(candidate),
                        "type": "executable"
                    }

    # 6. Protocol URI scheme if name looks like a protocol
    if ":" in lookup_name:
        return {
            "name": lookup_name,
            "target": lookup_name,
            "type": "protocol"
        }

    # Not found anywhere
    return None


def open_application(app_name: str) -> Dict[str, Any]:
    """
    Opens an installed Windows application, game, or system utility in < 50ms.
    If the application is not present, returns a clear 'not_found' status without errors.
    """
    clean_name = clean_app_query(app_name)
    if not clean_name:
        return {
            "status": "error",
            "message": "Please specify an application name."
        }

    app_info = find_app_target(clean_name)
    if not app_info:
        return {
            "status": "not_found",
            "app_name": clean_name,
            "message": f"'{clean_name}' is not installed on your PC. Please check the spelling or ensure it is installed."
        }

    display_name = app_info.get("name", clean_name.title())
    target = app_info.get("target")
    app_type = app_info.get("type", "executable")

    try:
        # A. Windows Store / UWP / AppX Package
        if app_type == "store" or ("!" in str(target) and not str(target).endswith(".exe")):
            # Use Windows Shell COM interface to activate via the running Desktop shell
            # This avoids spawning explorer.exe as a child process (which triggers 360 Security / AV alerts)
            ps_cmd = f"(New-Object -ComObject Shell.Application).Open('shell:AppsFolder\\{target}')"
            try:
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                )
            except Exception:
                # Fallback to start command if powershell fails
                subprocess.Popen(f'start "" "shell:AppsFolder\\{target}"', shell=True)

            return {
                "status": "success",
                "app_name": display_name,
                "target": str(target),
                "message": f"Successfully launched {display_name}."
            }

        # B. URL / Protocol Scheme (e.g. spotify:, ms-settings:)
        if app_type == "protocol" or str(target).endswith(":"):
            try:
                os.startfile(target)
            except Exception:
                subprocess.Popen(f'start "" "{target}"', shell=True)
            return {
                "status": "success",
                "app_name": display_name,
                "target": str(target),
                "message": f"Successfully launched {display_name}."
            }

        # C. Win32 Desktop Executable or Shortcut
        try:
            os.startfile(target)
        except Exception:
            subprocess.Popen(f'start "" "{target}"', shell=True)

        return {
            "status": "success",
            "app_name": display_name,
            "target": str(target),
            "message": f"Successfully launched {display_name}."
        }

    except Exception as e:
        logger.error(f"Error launching {clean_name}: {e}")
        return {
            "status": "error",
            "app_name": display_name,
            "message": f"Could not launch '{display_name}'. Please ensure it is installed on your PC."
        }


def find_running_process(app_name: str) -> Optional[str]:
    """Inspects currently running Windows processes to locate matching .exe name."""
    clean = clean_app_query(app_name)
    if clean.endswith(".exe"):
        clean = clean[:-4]

    target_exe = APP_PROCESS_NAMES.get(clean, f"{clean}.exe").lower()

    try:
        res = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=2.0)
        running_exes = set()
        for line in res.stdout.strip().splitlines():
            if line.strip():
                parts = line.split(",")
                if parts:
                    exe_name = parts[0].strip('"').strip()
                    if exe_name:
                        running_exes.add(exe_name)

        # 1. Exact match with target_exe
        for exe in running_exes:
            if exe.lower() == target_exe:
                return exe

        # 2. Exact match with clean name
        for exe in running_exes:
            base = exe.lower().replace(".exe", "")
            if base == clean:
                return exe

        # 3. Substring match
        for exe in running_exes:
            base = exe.lower().replace(".exe", "")
            if clean in base or base in clean:
                return exe
    except Exception:
        pass

    return None


def close_application(app_name: str) -> Dict[str, Any]:
    """Terminates a running Windows application by process name in < 50ms."""
    clean_name = clean_app_query(app_name)
    if not clean_name:
        return {"status": "error", "message": "Please specify an application to close."}

    proc_name = find_running_process(clean_name)
    if not proc_name:
        return {
            "status": "warning",
            "app_name": clean_name,
            "message": f"{clean_name} is not currently running."
        }

    try:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", proc_name],
            capture_output=True,
            text=True,
            timeout=3.0
        )
        if result.returncode == 0:
            return {
                "status": "success",
                "app_name": clean_name,
                "process": proc_name,
                "message": f"Successfully closed {clean_name}."
            }
        elif "not found" in result.stderr.lower() or "not found" in result.stdout.lower():
            return {
                "status": "warning",
                "app_name": clean_name,
                "message": f"{clean_name} is not currently running."
            }
        else:
            return {
                "status": "error",
                "app_name": clean_name,
                "message": f"Could not close {clean_name}: {result.stderr.strip()}"
            }
    except Exception as e:
        return {
            "status": "error",
            "app_name": clean_name,
            "message": f"Failed to close {clean_name}: {e}"
        }


def get_current_datetime_info() -> Dict[str, str]:
    """Returns current local time and date for instant time queries."""
    import datetime
    now = datetime.datetime.now()
    return {
        "time": now.strftime("%I:%M %p"),
        "date": now.strftime("%A, %B %d, %Y"),
        "full": now.strftime("%A, %B %d, %Y at %I:%M %p")
    }
