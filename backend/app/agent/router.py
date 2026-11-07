import re
import datetime
import subprocess
from typing import Optional, Dict, Any, List
from app.tools import file_utils
from app.tools import system_utils
from app.tools import web_utils

# Patterns to exclude purely educational code syntax questions from web search
QUESTION_EXCLUSIONS = re.compile(
    r"\b(?:how to|how do i|how can i|why does|can you explain the code|what is the syntax|teach me to code|write a function|write code|in python|in c\+\+|in javascript)\b",
    re.IGNORECASE
)

LOCAL_ACTION_EXCLUSIONS = re.compile(
    r"\b(?:list|show|open|read|view|find|search|write|save|create|delete)\s+(?:files?|folders?|directories|notepad|calculator|chrome|code|app|directory)\b|"
    r"\b(?:open|launch|start|run|play|close|exit|terminate|kill|quit|shut down|stop)\s+(?:the\s+)?(?:application\s+|app\s+|game\s+|program\s+)?[a-zA-Z0-9\-_]+\b",
    re.IGNORECASE
)

NEWS_CATEGORIES = {
    "technology", "tech", "sports", "world", "world news", "business", 
    "politics", "entertainment", "science", "health", "crypto", "ai", 
    "cricket", "football", "finance", "market", "markets"
}

def extract_web_search_query(user_message: str, history: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
    """
    Intelligently detects if a user message is asking for live web facts, current news,
    weather, sports, stocks, or entity information, including conversational follow-ups.
    """
    clean_msg = user_message.strip()
    clean_lower = clean_msg.lower().rstrip("?!. ")

    # 1. Skip code syntax questions & local file actions
    if QUESTION_EXCLUSIONS.search(clean_lower) or LOCAL_ACTION_EXCLUSIONS.search(clean_lower):
        return None

    # 2. Single category shortcuts (e.g. 'technology', 'cricket', 'world news')
    if clean_lower in NEWS_CATEGORIES:
        return f"{clean_lower} news"

    # 3. Explicit web search requests
    match = re.match(
        r"^(?:search\s+(?:the\s+)?(?:web|online|internet|google)\s+(?:for\s+)?|search\s+(?:for\s+)?|google\s+|look\s+up\s+online\s+(?:for\s+)?)(.+)$", 
        clean_lower
    )
    if match:
        target = match.group(1).strip()
        if not any(w in target for w in ("file", "folder", "code", "directory")):
            return target

    # 4. Weather & temperature queries
    if re.search(r"\b(?:weather|temperature|forecast|temp)\s+(?:in|for|at|today)?\s*([a-zA-Z\s]+)?\b", clean_lower):
        return clean_msg

    # 5. Sports scores, match winners, election results
    if re.search(r"\b(?:who won|match score|cricket score|football score|who is winning|election results?|ipl score|score of)\b", clean_lower):
        return clean_msg

    # 6. Prices, stocks, cryptocurrencies, earnings, valuation
    if re.search(r"\b(?:price of|stock price|net worth of|earnings of|valuation of|market cap of|crypto price|bitcoin price|gold price)\b", clean_lower):
        return clean_msg

    # 7. News & current events patterns
    news_pattern = re.match(
        r"^(?:any\s+news\s+(?:about|on|in|regarding)|latest\s+news\s+(?:about|on|in|regarding)|what(?:\'s| is)\s+(?:happening|going on)\s+(?:with|in|about)|tell me (?:about )?the latest (?:news |updates? )?(?:about|on|in)?|updates?\s+(?:about|on|in)|is there any update on)\s+(.+)$",
        clean_lower
    )
    if news_pattern:
        return news_pattern.group(1).strip()

    # "what is happening right now", "what's the news", "what is happening today"
    if re.search(r"\b(?:what(?:\'s| is) (?:happening|going on) (?:right now|today|lately)|what(?:\'s| is) the (?:latest |breaking )?news|top headlines|breaking news)\b", clean_lower):
        return "top breaking news"

    # 8. Conversational Follow-up from previous assistant turn
    if history:
        recent_turns = history[-4:]
        last_asst = next((m.get("content", "").lower() for m in reversed(recent_turns) if m.get("role") == "assistant"), "")
        last_user = next((m.get("content", "").lower() for m in reversed(recent_turns[:-1]) if m.get("role") == "user"), "")

        if any(w in last_asst for w in ("news", "updates", "interested in", "clarify", "reports", "check")):
            if clean_lower in NEWS_CATEGORIES:
                return f"latest {clean_lower} news"

            clarify_match = re.match(r"^(?:i\s+meant|meaning|by\s+[a-z0-9]+\s+i\s+mean)\s+(.+)$", clean_lower)
            if clarify_match:
                term = clarify_match.group(1).strip()
                context_words = [w for w in ("genz", "protest", "protests", "india", "news", "cjp") if w in last_user]
                if context_words:
                    return f"{term} {' '.join(context_words)}"
                return f"{term} news"

    # 9. 'tell me about X latest earnings/news/updates'
    m_tell = re.match(r"^(?:tell me about|what do you know about)\s+(.+)$", clean_lower)
    if m_tell:
        target = m_tell.group(1).strip()
        if not any(w in target for w in ("your", "yourself", "jarvis", "my files", "my document")):
            return target

    # 10. Specific entity or concept queries ('who is X', 'what is X', 'who was X')
    entity_match = re.match(r"^(?:who is|who was|who are|what is|what was|what are)\s+([a-zA-Z0-9\s\.\-]+)$", clean_lower)
    if entity_match:
        cand = entity_match.group(1).strip()
        if not any(w in cand for w in ("time", "date", "today", "my name", "your name", "a variable", "a loop", "an array", "ram", "rom", "cpu")):
            return cand

    # 11. Queries with "news" or "protest" or "election"
    if any(k in clean_lower for k in ("news", "protest", "protests", "election", "scandal", "earthquake", "war", "headline")):
        clean_kw = re.sub(r"\b(?:any|latest|the|about|is|there|tell|me|what|how|show|in|give)\b", "", clean_lower).strip()
        if len(clean_kw) > 2:
            return clean_kw

    return None


def try_deterministic_route(user_message: str) -> Optional[Dict[str, Any]]:
    """
    Synchronous fast router matching direct actions like list, search, app open/close, 
    file read/write, time, and math. Returns immediately (<10ms).
    """
    clean_msg = user_message.strip()
    clean_lower = clean_msg.lower().rstrip(".?! ")

    # Skip educational or explanation questions
    if QUESTION_EXCLUSIONS.search(clean_lower):
        return None

    # 1. Date & Time
    if re.search(r"\b(?:what(?:\'s| is)? (?:the )?(?:current )?time|what time is it|tell me the time)\b", clean_lower):
        info = system_utils.get_current_datetime_info()
        return {
            "reply": f"The current time is **{info['time']}** ({info['date']}).",
            "routed_deterministically": True,
            "action": "time"
        }

    if re.search(r"\b(?:what(?:\'s| is)? (?:the )?(?:current )?date|what is today'?s date|today'?s date|what day is it)\b", clean_lower):
        info = system_utils.get_current_datetime_info()
        return {
            "reply": f"Today is **{info['date']}**.",
            "routed_deterministically": True,
            "action": "date"
        }

    # 2. Simple Math / Calculation
    math_match = re.match(r"^(?:calculate|compute|what is)\s+([\d\s\+\-\*\/\(\)\.\%]+)$", clean_lower)
    if math_match:
        expr = math_match.group(1).strip()
        if re.match(r"^[\d\s\+\-\*\/\(\)\.]+$", expr) and any(op in expr for op in "+-*/"):
            try:
                result = eval(expr, {"__builtins__": {}}, {})
                return {
                    "reply": f"**{expr}** = **{result}**",
                    "routed_deterministically": True,
                    "action": "math"
                }
            except Exception:
                pass

    # 3. Open New Browser Tab (e.g. 'can you open a new tab in chrome', 'open new tab in edge', 'open a new tab')
    new_tab_match = re.match(
        r"^(?:hey\s+)?(?:jarvis\s*[,:]?\s*)?"
        r"(?:can\s+you\s+|could\s+you\s+|would\s+you\s+|will\s+you\s+|please\s+|i\s+want\s+to\s+|i\s+want\s+you\s+to\s+|help\s+me\s+|go\s+ahead\s+and\s+|just\s+)*"
        r"(?:open|launch|create)\s+(?:a\s+)?new\s+tab(?:\s+in\s+([a-zA-Z0-9\s]+?))?(?:\s+(?:for\s+me|please|now|right\s+now))*\s*[\.?!]*$",
        clean_lower
    )
    if new_tab_match:
        browser_req = (new_tab_match.group(1) or "").strip().lower()
        if "edge" in browser_req:
            subprocess.Popen('start msedge "edge://newtab"', shell=True)
            b_name = "Microsoft Edge"
        elif "brave" in browser_req:
            subprocess.Popen('start brave "about:blank"', shell=True)
            b_name = "Brave"
        elif "firefox" in browser_req:
            subprocess.Popen('start firefox "about:blank"', shell=True)
            b_name = "Firefox"
        else:
            subprocess.Popen('start chrome "chrome://newtab"', shell=True)
            b_name = "Google Chrome"

        return {
            "reply": f"Opened a new tab in {b_name}.",
            "routed_deterministically": True,
            "action": "open_new_tab"
        }

    # 4. Open / Launch a File in a Specific Directory or Permitted Roots
    # Examples: 'launch Haider_CV file in Downloads directory', 'open the file Haider_CV in downloads directory',
    # 'open Haider_CV in downloads', 'open file notes.txt', 'open resume.pdf'
    is_file_open_query = (
        ("file" in clean_lower and any(w in clean_lower for w in ("open", "launch", "reveal", "view")))
        or bool(re.search(r"\b(?:open|launch|reveal|view)\s+.+?\s+(?:in|inside|from)\s+(?:the\s+)?(downloads|documents|desktop|onedrive|pictures|videos|music|[a-zA-Z0-9_\-\.]+)\b", clean_lower))
        or bool(re.search(r"\b(?:open|launch|reveal|view)\s+.+?\.[a-zA-Z0-9]{1,5}(?:\s|$)", clean_lower))
    )
    if is_file_open_query:
        file_open_match = re.match(
            r"^(?:hey\s+)?(?:jarvis\s*[,:]?\s*)?"
            r"(?:can\s+you\s+|could\s+you\s+|would\s+you\s+|will\s+you\s+|please\s+|i\s+want\s+to\s+|i\s+want\s+you\s+to\s+|help\s+me\s+|go\s+ahead\s+and\s+|just\s+)*"
            r"(?:open|launch|reveal|view)\s+"
            r"(?:the\s+)?(?:file\s+)?(.+?)"
            r"(?:\s+(?:for\s+me|please|now|right\s+now))*\s*[\.?!]*$",
            clean_msg,
            re.IGNORECASE
        )
        if file_open_match:
            raw_target_str = file_open_match.group(1).strip()
            # Extract directory if specified (e.g. 'in downloads directory')
            dir_match = re.search(
                r"\b(?:in|inside|from)\s+(?:the\s+)?(downloads|documents|desktop|onedrive|pictures|videos|music|[a-zA-Z0-9_\-\.]+)(?:\s+(?:folder|directory))?$",
                raw_target_str,
                re.IGNORECASE
            )
            target_dir = dir_match.group(1) if dir_match else None
            filename_part = raw_target_str
            if dir_match:
                filename_part = filename_part[:dir_match.start()].strip()
            filename_part = re.sub(r"^(?:the\s+)?(?:file\s+)?", "", filename_part, flags=re.I).strip()
            filename_part = re.sub(r"\s+file$", "", filename_part, flags=re.I).strip()

            if filename_part and filename_part.lower() not in ("the", "a", "an", "all", "my", "this", "that"):
                res = file_utils.find_and_open_file(filename_query=filename_part, directory=target_dir)
                return {
                    "reply": res["message"],
                    "routed_deterministically": True,
                    "action": "open_file"
                }

    # 5. Open Folder in File Explorer
    open_folder_match = re.match(
        r"^(?:open|reveal)\s+(?:the\s+)?(?:folder\s+|directory\s+)?(downloads|documents|desktop|pictures|videos|music|onedrive|[a-zA-Z0-9_\-\.]+)\s*(?:folder|directory)?\s*(?:in explorer|in file explorer)?$",
        clean_lower
    )
    if open_folder_match and "file" not in clean_lower and not any(w in clean_lower for w in ("app", "game", "program")):
        target = open_folder_match.group(1).strip()
        if target not in ("the", "a", "all", "my", "game", "app", "application", "program"):
            try:
                res = file_utils.open_file_or_folder(target)
                return {
                    "reply": res["message"],
                    "routed_deterministically": True,
                    "action": "open_folder"
                }
            except Exception:
                pass

    # 6. Universal Application & Game Launching / Closing (with conversational phrasing support)
    conv_app_match = re.match(
        r"^(?:hey\s+)?(?:jarvis\s*[,:]?\s*)?"
        r"(?:can\s+you\s+|could\s+you\s+|would\s+you\s+|will\s+you\s+|please\s+|i\s+want\s+to\s+|i\s+want\s+you\s+to\s+|help\s+me\s+|go\s+ahead\s+and\s+|just\s+)*"
        r"(?:please\s+)?"
        r"(open|launch|start|run|play|bring\s+up|fire\s+up|close|exit|terminate|kill|shut\s+down|quit|stop)"
        r"\s+(?:up\s+)?(?:the\s+)?(?:application\s+|app\s+|game\s+|program\s+)?"
        r"([a-zA-Z0-9\s\.\-_]+?)"
        r"(?:\s+(?:app|application|game|program))?"
        r"(?:\s+(?:for\s+me|please|now|right\s+now|on\s+my\s+pc|on\s+my\s+computer|thanks|thank\s+you))*\s*[\.?!]*$",
        clean_lower
    )
    if conv_app_match:
        action_verb = conv_app_match.group(1).lower().strip()
        app_name = conv_app_match.group(2).strip()

        # Ensure target is not a folder, file, question word, or empty filler
        is_folder = app_name in ("downloads", "documents", "desktop", "onedrive", "pictures", "videos", "music")
        is_file = bool(re.search(r"\.[a-zA-Z0-9]{1,5}$", app_name))
        is_filler = app_name in ("the", "a", "an", "all", "my", "this", "that", "it", "file", "folder", "directory", "web", "online", "internet", "window", "tab")
        is_question = any(app_name.startswith(q) for q in ("what", "how", "why", "when", "who"))

        if not is_folder and not is_file and not is_filler and not is_question:
            if action_verb in ("close", "exit", "terminate", "kill", "shut down", "shut_down", "quit", "stop"):
                # Only close if known app or running process exists
                if system_utils.find_app_target(app_name) or system_utils.find_running_process(app_name):
                    res = system_utils.close_application(app_name)
                    return {
                        "reply": res["message"],
                        "routed_deterministically": True,
                        "action": "close_app"
                    }
            else:
                # Check if the target is actually an installed app or alias
                target_app = system_utils.find_app_target(app_name)
                if target_app:
                    res = system_utils.open_application(app_name)
                    return {
                        "reply": res["message"],
                        "routed_deterministically": True,
                        "action": "open_app"
                    }
                else:
                    # Target is NOT in installed apps!
                    # Only return "not installed" if user EXPLICITLY requested an app/application/program/game!
                    if re.search(r"\b(?:app|application|program|game|software)\b", clean_lower):
                        res = system_utils.open_application(app_name)
                        return {
                            "reply": res["message"],
                            "routed_deterministically": True,
                            "action": "open_app_not_found"
                        }
                    # Otherwise, DO NOT say "not installed"! Fall through to other routers or LLM!

    # 6. Direct Directory Listing
    list_match = re.match(
        r"^(?:list|show|display|view)\s+(?:all\s+)?(?:files\s+and\s+folders|files|folders|contents?|everything)?\s*(?:in|inside|of)?\s*(?:the\s+)?(downloads|documents|desktop|pictures|videos|music|onedrive|[a-zA-Z0-9_\-\.]+)\s*(?:folder|directory)?$",
        clean_lower
    )
    if not list_match:
        list_match = re.match(
            r"^(?:what|whats|what is)\s+(?:inside|in)\s*(?:the\s+)?(downloads|documents|desktop|pictures|videos|music|onedrive|[a-zA-Z0-9_\-\.]+)\s*(?:folder|directory)?$",
            clean_lower
        )

    if list_match:
        target_dir = list_match.group(1).strip()
        if target_dir not in ("the", "a", "all", "my", "this", "that"):
            try:
                res = file_utils.list_directory(directory=target_dir, limit=100)
                entries = res.get("entries", [])
                dir_path = res.get("directory", target_dir)

                dirs = [e['name'] for e in entries if e['type'] == 'directory']
                files = [e['name'] for e in entries if e['type'] == 'file']

                lines = [f"Here is everything inside **{target_dir.capitalize()}** (`{dir_path}`):\n"]
                if dirs:
                    lines.append(f"**Folders ({len(dirs)}):**")
                    lines.extend(f"- 📁 `{d}`" for d in dirs)
                    lines.append("")
                if files:
                    lines.append(f"**Files ({len(files)}):**")
                    lines.extend(f"- 📄 `{f}`" for f in files)
                if not dirs and not files:
                    lines.append("*The directory is empty.*")

                return {
                    "reply": "\n".join(lines),
                    "routed_deterministically": True,
                    "action": "list_directory"
                }
            except Exception as e:
                return {
                    "reply": f"Could not list folder '{target_dir}': {e}",
                    "routed_deterministically": True,
                    "action": "list_directory_failed"
                }

    # 7. Direct File Search
    search_match = re.match(r"^(?:search|find|locate)\s+(?:for\s+)?(?:files?\s+|file\s+)?([a-zA-Z0-9_\-\.\*\s]+?)(?:\s+(?:in|inside)\s+([a-zA-Z0-9_\-\.]+))?$", clean_lower)
    if search_match:
        raw_query = search_match.group(1).strip()
        in_folder = search_match.group(2).strip() if search_match.group(2) else None
        
        if raw_query and not any(w in raw_query for w in ("how", "why", "meaning", "wikipedia", "web", "online", "internet")):
            ext_filter = None
            if "python" in raw_query:
                ext_filter = [".py"]
                raw_query = raw_query.replace("python", "").replace("files", "").strip()
            elif "pdf" in raw_query:
                ext_filter = [".pdf"]
                raw_query = raw_query.replace("pdf", "").replace("files", "").strip()
            elif "text" in raw_query or "txt" in raw_query:
                ext_filter = [".txt"]
                raw_query = raw_query.replace("text", "").replace("txt", "").replace("files", "").strip()

            try:
                results = file_utils.search_files(query=raw_query or None, extension_filter=ext_filter, directory=in_folder, limit=12)
                if not results:
                    loc_desc = f" in **{in_folder}**" if in_folder else ""
                    return {
                        "reply": f"No files matching `{raw_query or ext_filter}` were found{loc_desc}.",
                        "routed_deterministically": True,
                        "action": "search_files"
                    }

                lines = [f"Found **{len(results)}** matching file(s):\n"]
                for r in results:
                    size_kb = max(1, round(r.get("size_bytes", 0) / 1024))
                    lines.append(f"- 📄 **`{r['file_name']}`** ({size_kb} KB)\n  `{r['file_path']}`")

                return {
                    "reply": "\n".join(lines),
                    "routed_deterministically": True,
                    "action": "search_files"
                }
            except Exception as e:
                return {
                    "reply": f"File search error: {e}",
                    "routed_deterministically": True,
                    "action": "search_files_failed"
                }

    # 8. Direct File Reading
    read_match = re.match(r"^(?:read|view|show|display)\s+(?:the\s+)?(?:content\s+of\s+|file\s+)?([a-zA-Z0-9_\-\.\/\\:]+\.[a-zA-Z0-9]+)$", clean_lower)
    if read_match:
        target_file = read_match.group(1).strip()
        try:
            res = file_utils.read_file_content(target_file)
            content = res.get("content", "")
            ext = res.get("extension", "")
            lines = [f"### 📄 `{res.get('file_path', target_file)}`\n"]
            lang = ext.lstrip(".") if ext else ""
            lines.append(f"```{lang}\n{content}\n```")
            return {
                "reply": "\n".join(lines),
                "routed_deterministically": True,
                "action": "read_file"
            }
        except Exception as e:
            return {
                "reply": f"Could not read `{target_file}`: {e}",
                "routed_deterministically": True,
                "action": "read_file_failed"
            }

    # 9. Direct File Writing / Creating
    write_match = re.match(r"^(?:write|save)\s+(.+?)\s+(?:to|in)\s+([a-zA-Z0-9_\-\.\/\\:]+\.[a-zA-Z0-9]+)$", clean_msg, re.IGNORECASE)
    if not write_match:
        write_match = re.match(r"^create\s+(?:file\s+)?([a-zA-Z0-9_\-\.\/\\:]+\.[a-zA-Z0-9]+)\s+with\s+(.+)$", clean_msg, re.IGNORECASE)
        if write_match:
            target_file = write_match.group(1).strip()
            content = write_match.group(2).strip()
            write_match = None
            try:
                res = file_utils.write_file_content(target_file, content)
                return {
                    "reply": f"Successfully created `{res['file_path']}` ({res['bytes_written']} bytes).",
                    "routed_deterministically": True,
                    "action": "write_file"
                }
            except Exception as e:
                return {
                    "reply": f"Failed to write file: {e}",
                    "routed_deterministically": True,
                    "action": "write_file_failed"
                }

    if write_match:
        content = write_match.group(1).strip().strip("'\"")
        target_file = write_match.group(2).strip()
        try:
            res = file_utils.write_file_content(target_file, content)
            return {
                "reply": f"Successfully written to `{res['file_path']}` ({res['bytes_written']} bytes).",
                "routed_deterministically": True,
                "action": "write_file"
            }
        except Exception as e:
            return {
                "reply": f"Failed to write file: {e}",
                "routed_deterministically": True,
                "action": "write_file_failed"
            }

    return None


async def try_fast_route_async(user_message: str, history: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """
    Asynchronous fast router that checks synchronous deterministic fast-paths
    (time, date, math, app launch/close, directory listing, file search/read/write).
    Returns immediately (<10ms) if matched, or None to allow intelligent streaming.
    """
    return try_deterministic_route(user_message)