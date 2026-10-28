import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.core import config

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document
except ImportError:
    Document = None

# Directories that should NEVER be deeply crawled to guarantee blazing speed
EXCLUDED_DIR_NAMES = {
    "node_modules", ".git", ".venv", "venv", "env", "__pycache__",
    "dist", "build", ".next", ".nuxt", "appdata", "$recycle.bin",
    "site-packages", ".idea", ".vscode", "temp", "tmp", ".cache",
    ".pytest_cache", ".ruff_cache", "coverage", ".turbo"
}

def is_path_permitted(target_path: Path) -> bool:
    """
    Resolves the canonical path and verifies it falls inside 
    at least one permitted directory.
    """
    try:
        canonical_target = target_path.resolve()
    except Exception:
        return False

    permitted_dirs = config.get_permitted_directories()
    return _is_path_within_directories(canonical_target, permitted_dirs)


def _is_path_within_directories(target_path: Path, permitted_dirs: List[Path]) -> bool:
    for p_dir in permitted_dirs:
        try:
            if target_path == p_dir or p_dir in target_path.parents:
                return True
        except Exception:
            continue
    return False


def resolve_permitted_folder(directory_input: str) -> Path:
    """
    Resolves natural folder names (e.g., 'jarvis', 'Documents', 'Downloads', 'OneDrive')
    or path strings into a validated, permitted Path object.
    Supports deep subfolder lookups so project folders like 'jarvis' are found instantly.
    """
    clean_input = directory_input.strip().strip("'\"").rstrip("\\/")
    permitted_dirs = config.get_permitted_directories()
    clean_lower = clean_input.lower()

    # 1. Check if input is already a valid absolute or existing path
    try:
        p = Path(clean_input).expanduser().resolve()
        if p.exists() and p.is_dir() and is_path_permitted(p):
            return p
    except Exception:
        pass

    # 2. Standard Windows user profile locations as fast-path aliases
    user_home = Path.home()
    aliases = {
        "documents": [user_home / "OneDrive" / "Documents", user_home / "Documents"],
        "downloads": [user_home / "OneDrive" / "Downloads", user_home / "Downloads"],
        "desktop": [user_home / "OneDrive" / "Desktop", user_home / "Desktop"],
        "pictures": [user_home / "OneDrive" / "Pictures", user_home / "Pictures"],
        "videos": [user_home / "OneDrive" / "Videos", user_home / "Videos"],
        "music": [user_home / "OneDrive" / "Music", user_home / "Music"],
        "onedrive": [user_home / "OneDrive"]
    }

    if clean_lower in aliases:
        for candidate in aliases[clean_lower]:
            if candidate.exists() and candidate.is_dir() and is_path_permitted(candidate):
                return candidate

    # 3. Match directly against permitted directory root names
    for p_dir in permitted_dirs:
        if p_dir.name.lower() == clean_lower:
            return p_dir

    # 4. Match subfolders inside permitted directories (depth 1 to 3)
    for p_dir in permitted_dirs:
        candidate = p_dir / clean_input
        if candidate.exists() and candidate.is_dir() and is_path_permitted(candidate):
            return candidate

    # Fast shallow BFS scan across permitted directories to find folder by name (e.g. 'jarvis')
    for p_dir in permitted_dirs:
        try:
            for root, dirs, _ in os.walk(p_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in EXCLUDED_DIR_NAMES]
                rel_parts = Path(root).relative_to(p_dir).parts
                if len(rel_parts) > 3:
                    dirs.clear()
                    continue
                for d in dirs:
                    if d.lower() == clean_lower:
                        found_path = (Path(root) / d).resolve()
                        if found_path.is_dir() and is_path_permitted(found_path):
                            return found_path
        except Exception:
            continue

    raise NotADirectoryError(f"Directory '{directory_input}' could not be resolved or is outside permitted directories.")


def smart_find_file(file_name_or_path: str) -> Optional[Path]:
    """
    Given a file name or path (e.g. 'main.py', 'notes.txt', or full path),
    locates the actual file inside permitted directories using fast BFS.
    """
    clean_target = file_name_or_path.strip().strip("'\"")
    if not clean_target:
        return None

    # Check direct path
    try:
        p = Path(clean_target).expanduser().resolve()
        if p.exists() and p.is_file() and is_path_permitted(p):
            return p
    except Exception:
        pass

    target_name = Path(clean_target).name.lower()
    permitted_dirs = config.get_permitted_directories()

    # Search project workspace first for speed
    backend_dir = Path(__file__).resolve().parent.parent.parent
    project_root = backend_dir.parent
    search_roots = [project_root, backend_dir] + permitted_dirs

    seen_roots = set()
    for root_dir in search_roots:
        if not root_dir or not root_dir.exists() or root_dir in seen_roots:
            continue
        seen_roots.add(root_dir)

        try:
            for root, dirs, files in os.walk(root_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in EXCLUDED_DIR_NAMES]
                rel_parts = Path(root).relative_to(root_dir).parts
                if len(rel_parts) > 5:
                    dirs.clear()
                    continue

                for f in files:
                    if f.lower() == target_name:
                        cand = (Path(root) / f).resolve()
                        if cand.is_file() and is_path_permitted(cand):
                            return cand
        except Exception:
            continue

    return None


def search_files(
    query: Optional[str] = None, 
    extension_filter: Optional[List[str]] = None, 
    limit: int = 15,
    directory: Optional[str] = None,
    max_depth: int = 4,
    timeout_sec: float = 3.0
) -> List[Dict[str, Any]]:
    """
    Searches permitted directories with strict performance safeguards:
    - Excludes heavy libraries (node_modules, .venv, .git, dist, build, AppData)
    - Breadth-first shallow scan bounded by max_depth and timeout_sec
    - Returns fast results in under 0.2s
    """
    clean_query = query.strip().lower() if (query and query.strip() != "*") else ""
    capped_limit = min(max(1, limit), 100)

    # Process extension filters
    clean_filters = set()
    if extension_filter:
        for ext in extension_filter:
            if isinstance(ext, str) and ext.strip():
                e = ext.strip().lower()
                if not e.startswith("."):
                    e = "." + e
                clean_filters.add(e)

    permitted_dirs = config.get_permitted_directories()
    if not permitted_dirs:
        raise PermissionError("No permitted search directories are configured.")

    if directory:
        requested_dir = resolve_permitted_folder(directory)
        search_dirs = [requested_dir]
    else:
        # Prioritize key user folders before wide OneDrive search
        user_home = Path.home()
        high_pri = [
            user_home / "OneDrive" / "Documents",
            user_home / "OneDrive" / "Desktop",
            user_home / "OneDrive" / "Downloads",
            user_home / "Documents",
            user_home / "Desktop",
            user_home / "Downloads",
        ]
        search_dirs = [d for d in high_pri if d.exists() and is_path_permitted(d)]
        for p in permitted_dirs:
            if p not in search_dirs:
                search_dirs.append(p)

    results = []
    seen_paths = set()
    start_time = time.time()

    for p_dir in search_dirs:
        if len(results) >= capped_limit or (time.time() - start_time) > timeout_sec:
            break

        try:
            for root, dirs, files in os.walk(p_dir):
                if len(results) >= capped_limit or (time.time() - start_time) > timeout_sec:
                    break

                # Prune heavy junk directories
                dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in EXCLUDED_DIR_NAMES]
                
                try:
                    rel_parts = Path(root).relative_to(p_dir).parts
                    if len(rel_parts) > max_depth:
                        dirs.clear()
                        continue
                except Exception:
                    pass

                for file_name in files:
                    if len(results) >= capped_limit:
                        break

                    # Match query
                    if clean_query and clean_query not in file_name.lower():
                        continue

                    # Match extension
                    _, ext = os.path.splitext(file_name)
                    ext = ext.lower()
                    if clean_filters and ext not in clean_filters:
                        continue

                    full_path = os.path.join(root, file_name)
                    if full_path in seen_paths:
                        continue
                    seen_paths.add(full_path)

                    try:
                        stat = os.stat(full_path)
                        results.append({
                            "file_name": file_name,
                            "file_path": full_path,
                            "size_bytes": stat.st_size,
                            "extension": ext,
                            "supported": ext in config.ALL_SUPPORTED_EXTENSIONS
                        })
                    except Exception:
                        continue
        except Exception:
            continue

    return results


def list_directory(directory: str, limit: int = 100) -> Dict[str, Any]:
    """
    Lists immediate files and directories within one permitted directory or named folder.
    """
    requested_dir = resolve_permitted_folder(directory)
    capped_limit = min(max(1, limit), 100)

    entries = []
    try:
        with os.scandir(requested_dir) as it:
            for entry in it:
                # Skip hidden entries and excluded folders
                if entry.name.startswith(".") or entry.name.lower() in EXCLUDED_DIR_NAMES:
                    continue
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                    entries.append({
                        "name": entry.name,
                        "path": entry.path,
                        "type": "directory" if is_dir else "file",
                    })
                except OSError:
                    continue
    except Exception as e:
        raise RuntimeError(f"Failed to list directory '{requested_dir}': {e}")

    # Sort directories first, then files alphabetically
    entries.sort(key=lambda item: (item["type"] != "directory", item["name"].casefold()))

    return {
        "directory": str(requested_dir),
        "entries": entries[:capped_limit],
        "total": len(entries),
        "truncated": len(entries) > capped_limit,
    }


def read_file_content(file_path_str: str) -> Dict[str, Any]:
    """
    Reads text, PDF, or DOCX content from a permitted file path or natural filename.
    Automatically resolves relative file names (e.g. 'main.py' or 'notes.txt').
    """
    if not isinstance(file_path_str, str) or not file_path_str.strip():
        raise ValueError("File path cannot be empty.")

    clean_target = file_path_str.strip()
    target_path = smart_find_file(clean_target)

    if not target_path:
        # Fallback to direct check
        target_path = Path(clean_target)

    if not target_path.exists():
        raise FileNotFoundError(f"File not found: '{file_path_str}'")

    if not target_path.is_file():
        raise ValueError(f"Path is not a regular file: '{file_path_str}'")

    if not is_path_permitted(target_path):
        raise PermissionError(f"Access denied. Path is outside permitted directories: '{file_path_str}'")

    stat = target_path.stat()
    if stat.st_size > config.MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File size ({stat.st_size} bytes) exceeds maximum limit of {config.MAX_FILE_SIZE_BYTES} bytes.")

    ext = target_path.suffix.lower()
    if ext not in config.ALL_SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file extension '{ext}'. Supported: {sorted(list(config.ALL_SUPPORTED_EXTENSIONS))}")

    extracted_text = ""

    # Parse based on file type
    if ext in config.SUPPORTED_TEXT_EXTENSIONS:
        try:
            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                extracted_text = f.read(config.MAX_EXTRACTED_TEXT_CHARS)
        except Exception as e:
            raise RuntimeError(f"Failed to read text file: {e}")

    elif ext == ".pdf":
        if PdfReader is None:
            raise RuntimeError("pypdf is not installed in environment.")
        try:
            reader = PdfReader(target_path)
            if reader.is_encrypted:
                raise ValueError("PDF file is encrypted/password protected.")
            
            pages_text = []
            for page in reader.pages:
                txt = page.extract_text()
                if txt:
                    pages_text.append(txt)
                if sum(len(p) for p in pages_text) >= config.MAX_EXTRACTED_TEXT_CHARS:
                    break
            extracted_text = "\n".join(pages_text)[:config.MAX_EXTRACTED_TEXT_CHARS]
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to parse PDF file: {e}")

    elif ext == ".docx":
        if Document is None:
            raise RuntimeError("python-docx is not installed in environment.")
        try:
            doc = Document(target_path)
            full_text = [p.text for p in doc.paragraphs if p.text]
            extracted_text = "\n".join(full_text)[:config.MAX_EXTRACTED_TEXT_CHARS]
        except Exception as e:
            raise RuntimeError(f"Failed to parse DOCX file: {e}")

    if not extracted_text.strip():
        return {
            "status": "warning",
            "message": "File opened successfully, but no readable text content was extracted.",
            "file_path": str(target_path.resolve()),
            "content": ""
        }

    return {
        "status": "success",
        "file_path": str(target_path.resolve()),
        "extension": ext,
        "content": extracted_text
    }


def write_file_content(file_path_str: str, content: str, mode: str = "write") -> Dict[str, Any]:
    """
    Creates or appends text content to a file in a permitted directory.
    Supports natural names like 'notes.txt' by defaulting to Documents if no dir is given.
    """
    clean_path_str = file_path_str.strip().strip("'\"")
    if not clean_path_str:
        raise ValueError("File path cannot be empty.")

    p = Path(clean_path_str).expanduser()
    if not p.is_absolute():
        # Default relative files to user's Documents folder
        docs_dir = Path.home() / "OneDrive" / "Documents"
        if not docs_dir.exists():
            docs_dir = Path.home() / "Documents"
        p = docs_dir / clean_path_str

    # Ensure parent exists
    p.parent.mkdir(parents=True, exist_ok=True)

    if not is_path_permitted(p):
        raise PermissionError(f"Access denied. Path is outside permitted directories: '{p}'")

    write_mode = "a" if mode.lower() in ("append", "a") else "w"
    with open(p, write_mode, encoding="utf-8") as f:
        f.write(content)

    return {
        "status": "success",
        "file_path": str(p.resolve()),
        "action": "appended" if write_mode == "a" else "written",
        "bytes_written": len(content.encode("utf-8")),
    }


def open_file_or_folder(path_str: str) -> Dict[str, Any]:
    """
    Opens a file or folder in the Windows native default viewer or Explorer.
    """
    clean_input = path_str.strip().strip("'\"")
    # Try folder first
    try:
        resolved_folder = resolve_permitted_folder(clean_input)
        os.startfile(str(resolved_folder))
        return {"status": "success", "message": f"Opened folder '{resolved_folder}' in File Explorer."}
    except Exception:
        pass

    # Try file
    resolved_file = smart_find_file(clean_input)
    if resolved_file and resolved_file.exists():
        os.startfile(str(resolved_file))
        return {"status": "success", "message": f"Opened file '{resolved_file}'."}

    raise FileNotFoundError(f"Could not find file or folder '{path_str}' to open.")