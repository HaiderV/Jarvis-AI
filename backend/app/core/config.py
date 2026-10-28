import os
from pathlib import Path
from typing import List

def get_permitted_directories() -> List[Path]:
    """
    Returns explicit permitted directories from the JARVIS_PERMITTED_DIRS environment variable.
    Format: Semicolon-separated or comma-separated absolute paths.
    Example: JARVIS_PERMITTED_DIRS="C:\\Users\\Username\\Documents;C:\\Users\\Username\\Projects"
    
    Defaults to User Home (covering OneDrive, Documents, Downloads, Desktop) and current workspace
    so local file access works seamlessly out of the box without strict permission roadblocks.
    """
    raw_env = os.getenv("JARVIS_PERMITTED_DIRS", "")
    permitted = []
    
    if raw_env.strip():
        # Handle semicolon or comma separation
        delimiters = [";", ","]
        path_strs = [raw_env]
        for delim in delimiters:
            new_strs = []
            for p_str in path_strs:
                new_strs.extend(p_str.split(delim))
            path_strs = new_strs

        for p_str in path_strs:
            clean = p_str.strip()
            if clean:
                try:
                    resolved = Path(clean).resolve()
                    if resolved.exists() and resolved.is_dir():
                        permitted.append(resolved)
                except Exception:
                    continue
        if permitted:
            return permitted

    # Sensible defaults for personal assistant access:
    # 1. User Home (e.g., C:\Users\haide)
    user_home = Path.home().resolve()
    if user_home.exists():
        permitted.append(user_home)

    # 2. OneDrive if present
    onedrive = user_home / "OneDrive"
    if onedrive.exists() and onedrive not in permitted:
        permitted.append(onedrive.resolve())

    # 3. Project / Workspace root
    try:
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        if project_root.exists() and project_root not in permitted:
            permitted.append(project_root.resolve())
    except Exception:
        pass

    return permitted

# File constraints
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_EXTRACTED_TEXT_CHARS = 10_000  # Capped to prevent context overflow

# Allowed text & code extensions
SUPPORTED_TEXT_EXTENSIONS = {
    ".txt", ".md", ".json", ".csv", ".yaml", ".yml", ".xml", ".log",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".cpp", ".c", ".h", ".rs", ".go"
}
SUPPORTED_DOC_EXTENSIONS = {".pdf", ".docx"}
ALL_SUPPORTED_EXTENSIONS = SUPPORTED_TEXT_EXTENSIONS.union(SUPPORTED_DOC_EXTENSIONS)