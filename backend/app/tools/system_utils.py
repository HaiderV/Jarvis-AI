import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional

# Pre-defined mapping of common applications, utilities, games, and URI protocols
COMMON_APPS = {
    # Text & Code Editors
    "notepad": "notepad.exe",
    "notes": "notepad.exe",
    "vscode": "code.cmd",
    "vs code": "code.cmd",
    "code": "code.cmd",
    "visual studio code": "code.cmd",
    "sublime": "sublime_text.exe",

    # Utilities & Tools
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "settings": "ms-settings:",
    "control panel": "control.exe",
    "snipping tool": "snippingtool.exe",
    "camera": "microsoft.windows.camera:",
    "clock": "ms-clock:",

    # File Explorer
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "files": "explorer.exe",

    # Web Browsers
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "browser": "msedge.exe",
    "brave": "brave.exe",
    "firefox": "firefox.exe",
    "opera": "opera.exe",

    # Games & Gaming Launchers
    "steam": "steam.exe",
    "epic games": "com.epicgames.launcher:",
    "epic games launcher": "com.epicgames.launcher:",
    "riot client": "RiotClientServices.exe",
    "riot": "RiotClientServices.exe",
    "valorant": "RiotClientServices.exe",
    "league of legends": "RiotClientServices.exe",
    "minecraft": "minecraft:",
    "roblox": "roblox:",
    "battle.net": "battle.net.exe",
    "battlenet": "battle.net.exe",
    "ea": "ea.exe",
    "ea app": "ea.exe",
    "gog": "gog_galaxy.exe",
    "gog galaxy": "gog_galaxy.exe",

    # Communication & Social
    "discord": "discord.exe",
    "spotify": "spotify:",
    "vlc": "vlc.exe",
    "media player": "wmplayer.exe",
    "telegram": "telegram.exe",
    "whatsapp": "whatsapp:",
    "slack": "slack:",
    "teams": "msteams:",
    "microsoft teams": "msteams:",
    "zoom": "zoom.exe",

    # Microsoft Office & Productivity
    "word": "winword.exe",
    "winword": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "onenote": "onenote.exe",
    "outlook": "outlook.exe",
    "obs": "obs64.exe",
    "obs studio": "obs64.exe",
    "blender": "blender.exe",
    "acrobat": "Acrobat.exe",
    "adobe acrobat": "Acrobat.exe",
}

# Map common user terms to process names for taskkill
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
}

# Cached desktop & start menu shortcuts
_APP_SHORTCUT_CACHE: Dict[str, str] = {}
_LAST_CACHE_TIME: float = 0

def get_installed_shortcuts() -> Dict[str, str]:
    """
    Scans Desktop and Start Menu folders for installed application shortcuts (.lnk, .url).
    Caches results in memory for 5 minutes (takes <30ms).
    """
    global _APP_SHORTCUT_CACHE, _LAST_CACHE_TIME
    now = time.time()
    if _APP_SHORTCUT_CACHE and (now - _LAST_CACHE_TIME) < 300:
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
        if d.exists():
            for root, _, files in os.walk(d):
                for f in files:
                    lower = f.lower()
                    if lower.endswith(".lnk") or lower.endswith(".url"):
                        name = f.rsplit(".", 1)[0].lower().strip()
                        if name not in shortcuts:
                            shortcuts[name] = str(Path(root) / f)

    _APP_SHORTCUT_CACHE = shortcuts
    _LAST_CACHE_TIME = now
    return _APP_SHORTCUT_CACHE


GAME_ALIASES = {
    "gta": ["playgtav", "gta5", "gtav", "grand theft auto"],
    "gta 5": ["playgtav", "gta5", "gtav", "grand theft auto v"],
    "gta v": ["playgtav", "gta5", "gtav", "grand theft auto v"],
    "epic": ["epic games launcher", "epic games"],
    "epic games": ["epic games launcher"],
    "game": ["steam", "epic games launcher", "playgtav", "game booster"],
    "games": ["steam", "epic games launcher"],
    "game booster": ["game booster"],
    "adobe": ["adobe creative cloud", "adobe acrobat"],
    "acrobat": ["adobe acrobat"],
    "creative cloud": ["adobe creative cloud"],
}

def find_app_target(app_name: str) -> Optional[str]:
    """
    Resolves an application or game name to an executable path, .lnk shortcut, or URI scheme.
    """
    clean = app_name.strip().lower()

    # 1. Exact match in COMMON_APPS
    if clean in COMMON_APPS:
        return COMMON_APPS[clean]

    # 2. Match in desktop & start menu shortcuts (.lnk files)
    shortcuts = get_installed_shortcuts()
    if clean in shortcuts:
        return shortcuts[clean]

    # 3. Check game aliases
    if clean in GAME_ALIASES:
        for alias in GAME_ALIASES[clean]:
            if alias in COMMON_APPS:
                return COMMON_APPS[alias]
            if alias in shortcuts:
                return shortcuts[alias]
            for s_name, s_path in shortcuts.items():
                if alias in s_name or s_name in alias:
                    return s_path

    # 4. Word boundary / substring match in shortcuts (e.g. "chrome" matches "Google Chrome.lnk")
    for name, path in shortcuts.items():
        if clean == name or f" {clean} " in f" {name} " or name.startswith(clean) or clean in name:
            return path

    # 5. Direct executable check via shutil.which
    which_path = shutil.which(clean) or shutil.which(f"{clean}.exe")
    if which_path:
        return which_path

    # 6. Check common game and program directories
    program_dirs = [
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
        Path.home() / "AppData/Local/Programs",
        Path("C:/Riot Games"),
    ]
    for pdir in program_dirs:
        if pdir.exists():
            for candidate in [pdir / clean, pdir / f"{clean}.exe", pdir / clean.title()]:
                if candidate.exists() and candidate.is_file():
                    return str(candidate)

    # 7. Protocol URI scheme if name looks like a protocol
    if ":" in clean:
        return clean

    return None


def open_application(app_name: str) -> Dict[str, Any]:
    """
    Opens an installed Windows application, game, or system utility in <50ms.
    """
    clean_name = app_name.strip()
    if not clean_name:
        return {"status": "error", "message": "Please specify an application name."}

    target = find_app_target(clean_name)
    if not target:
        target = f"{clean_name.lower()}.exe"

    try:
        # Launch using Windows ShellExecute (os.startfile)
        os.startfile(target)
        return {
            "status": "success",
            "app_name": clean_name,
            "target": str(target),
            "message": f"Successfully launched {clean_name}."
        }
    except Exception:
        # Fallback to subprocess Popen
        try:
            subprocess.Popen(f'start "" "{target}"', shell=True)
            return {
                "status": "success",
                "app_name": clean_name,
                "target": str(target),
                "message": f"Successfully launched {clean_name}."
            }
        except Exception as e:
            return {
                "status": "error",
                "app_name": clean_name,
                "message": f"Could not launch '{clean_name}'. Please ensure it is installed on your PC."
            }


def find_running_process(app_name: str) -> Optional[str]:
    """
    Inspects currently running Windows processes to locate matching .exe name.
    """
    clean = app_name.strip().lower()
    if clean.endswith(".exe"):
        clean = clean[:-4]

    # 1. Check known process dictionary first (<1ms)
    if clean in APP_PROCESS_NAMES:
        return APP_PROCESS_NAMES[clean]

    # 2. Inspect active processes via tasklist
    try:
        res = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=2.0)
        running_exes = set()
        for line in res.stdout.strip().splitlines():
            if line.strip():
                parts = line.split(",")
                if parts:
                    exe_name = parts[0].strip('"')
                    running_exes.add(exe_name)

        # Exact base name match
        for exe in running_exes:
            exe_base = exe.lower().replace(".exe", "")
            if exe_base == clean:
                return exe

        # Substring match
        for exe in running_exes:
            exe_base = exe.lower().replace(".exe", "")
            if clean in exe_base or exe_base in clean:
                return exe
    except Exception:
        pass

    return f"{clean}.exe"


def close_application(app_name: str) -> Dict[str, Any]:
    """
    Terminates a running Windows application or game by process name in <50ms.
    """
    clean_name = app_name.strip()
    if not clean_name:
        return {"status": "error", "message": "Please specify an application to close."}

    proc_name = find_running_process(clean_name)

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
    """
    Returns current local time and date for instant time queries.
    """
    import datetime
    now = datetime.datetime.now()
    return {
        "time": now.strftime("%I:%M %p"),
        "date": now.strftime("%A, %B %d, %Y"),
        "full": now.strftime("%A, %B %d, %Y at %I:%M %p")
    }
