import json
import re
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncGenerator
from app.llm.ollama_client import generate_chat_completion, stream_chat_completion
from app.database import repository
from app.core import config
from app.tools import file_utils
from app.tools import system_utils
from app.tools import web_utils
from app.agent.router import try_deterministic_route, try_fast_route_async, extract_web_search_query

SYSTEM_PROMPT = (
    "You are Jarvis, a fast, intelligent, voice-ready personal AI assistant.\n\n"
    "CONVERSATIONAL STYLE:\n"
    "- Speak in natural, spoken English. Sound like a helpful, smart human partner.\n"
    "- Keep everyday answers concise, direct, and under 3-4 sentences when possible.\n"
    "- Use natural contractions ('I'm', 'it's', 'you'll', 'don't').\n"
    "- Provide direct answers without robotic preamble or repeating the user's question.\n"
    "- Break complex topics into structured, clear points.\n\n"
    "ACCURACY & FACTUALITY:\n"
    "- Ground all real-time news and factual answers strictly on verified evidence.\n"
    "- Mention specific sources, organizations, and dates when reporting news or events.\n"
    "- Never pretend to search or say 'I am checking' if evidence is provided—state the facts directly.\n"
    "- If no reports or evidence are found for a topic, state clearly that no matching reports exist."
)

MAX_HISTORY_MESSAGES = 8  # Bounded context window to keep inference quick
MAX_TOOL_ROUNDS = 2
MAX_CALLS_PER_ROUND = 3

FILE_TOOL_ACTION_PATTERN = re.compile(
    r"\b(?:list|show|display|find|search|read|open|locate|look|check|inspect|scan|write|save|create)\b",
    re.IGNORECASE,
)
FILE_TOOL_TARGET_PATTERN = re.compile(
    r"\b(?:files?|folders?|directories|documents?|downloads?|desktop|onedrive|"
    r"pictures|videos|music|paths?|pdfs?|assignments?|notes?)\b",
    re.IGNORECASE,
)
CONVERSATION_RECALL_PATTERN = re.compile(
    r"\b(?:past|previous|earlier|last)\s+(?:conversation|chat|discussion)s?\b|"
    r"\b(?:conversation history|search conversations|history|"
    r"what did i (?:say|ask|tell you)|what were we discussing|"
    r"remember|recall)\b",
    re.IGNORECASE,
)
CONTEXTUAL_FOLLOWUP_PATTERN = re.compile(
    r"\b(?:it|them|those|these|that|there|ones|first|second|third|last|"
    r"same|inside|within|subfolders?|subdirectories|contents?|"
    r"did you (?:find|found)|have you found|any luck|what about|also|specifically)\b",
    re.IGNORECASE,
)
FILE_CONTEXT_PATTERN = re.compile(
    r"\b(?:files?|folders?|directories|paths?|found files|contents of|"
    r"directory is empty|folder is empty)\b",
    re.IGNORECASE,
)

CONVERSATION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lists immediate files and subfolders in a permitted directory or folder name like 'jarvis', 'Downloads', 'Documents', 'OneDrive'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Folder name or path (e.g. 'jarvis', 'Downloads', 'Documents', 'OneDrive')."
                    },
                    "limit": {"type": "integer", "description": "Max items to return (default 100)."}
                },
                "required": ["directory"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Quickly searches files matching keyword or extension in permitted directories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Filename keyword or '' / '*' for all files."},
                    "directory": {"type": "string", "description": "Optional specific directory path or folder name."},
                    "extension_filter": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File extensions (e.g. ['.pdf', '.docx', '.txt', '.py'])."
                    },
                    "limit": {"type": "integer", "description": "Max results (default 10)."}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_content",
            "description": "Reads text, code, PDF, or DOCX content from a file path or natural filename.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "File path or file name (e.g. 'main.py', 'notes.txt')."}
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file_content",
            "description": "Writes or creates a local text file with given content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "File name or target path."},
                    "content": {"type": "string", "description": "Text content to write."},
                    "mode": {"type": "string", "enum": ["write", "append"], "description": "Write mode (default: write)."}
                },
                "required": ["file_path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Opens a Windows application like Notepad, Calculator, Chrome, VS Code, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Application name (e.g. 'notepad', 'calculator', 'chrome', 'vscode')."}
                },
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_application",
            "description": "Closes a running Windows application by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Application name to close (e.g. 'notepad', 'calculator', 'chrome')."}
                },
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Searches the live internet for news, facts, current events, or answers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query keywords."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_conversation_history",
            "description": "Retrieves past conversation message transcripts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string", "description": "Target conversation UUID."},
                    "limit": {"type": "integer", "description": "Max recent messages."}
                },
                "required": ["conversation_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_conversations",
            "description": "Searches past user conversation transcripts for keywords or topics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword to search across past chats."},
                    "limit": {"type": "integer", "description": "Max matching turns to return (default 5)."}
                },
                "required": ["query"]
            }
        }
    },
]

def _generate_title(first_message: str) -> str:
    clean_msg = first_message.strip()
    return clean_msg[:30].strip() + "..." if len(clean_msg) > 30 else clean_msg

def _build_system_prompt() -> str:
    permitted_dirs = config.get_permitted_directories()
    if not permitted_dirs:
        return SYSTEM_PROMPT + "\nPermitted local folders: User Home & OneDrive"
    roots = "\n".join(f"- {path}" for path in permitted_dirs[:3])
    return f"{SYSTEM_PROMPT}\nPermitted local folders:\n{roots}"

def _should_check_tools(user_message: str, messages: List[Dict[str, Any]]) -> bool:
    clean = user_message.lower()

    # Never trigger tool check for questions asking for explanations or programming concepts
    if re.search(r"\b(?:how to|how do i|how can i|why|explain|teach me|tutorial|what is the syntax|in python|in c\+\+|in javascript)\b", clean):
        return False

    if CONVERSATION_RECALL_PATTERN.search(user_message):
        return True

    if (
        FILE_TOOL_ACTION_PATTERN.search(user_message)
        and FILE_TOOL_TARGET_PATTERN.search(user_message)
    ):
        return True

    # App open/close (Universal Desktop Apps, Tools & Games)
    if re.search(r"\b(?:open|launch|start|run|play|close|exit|terminate|kill|quit|shut down|stop)\s+(?:the\s+)?(?:application\s+|app\s+|game\s+|program\s+)?[a-zA-Z0-9\-_]+\b", clean):
        return True

    recent_messages = messages[:-1]
    recent_file_task = any(
        message.get("role") == "user"
        and FILE_TOOL_ACTION_PATTERN.search(message.get("content", ""))
        and FILE_TOOL_TARGET_PATTERN.search(message.get("content", ""))
        for message in recent_messages[-8:]
    )
    recent_file_result = any(
        message.get("role") == "assistant"
        and FILE_CONTEXT_PATTERN.search(message.get("content", ""))
        for message in recent_messages[-6:]
    )
    return bool(
        CONTEXTUAL_FOLLOWUP_PATTERN.search(user_message)
        and (recent_file_task or recent_file_result)
    )

async def _execute_registered_tool_async(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if tool_name == "list_directory":
        raw_dir = arguments.get("directory", "")
        if not raw_dir or not isinstance(raw_dir, str) or not raw_dir.strip():
            return {"status": "error", "message": "Argument 'directory' must be a non-empty string."}
        
        limit = int(arguments.get("limit", 100))
        try:
            res = file_utils.list_directory(directory=raw_dir, limit=limit)
            return {
                "status": "success", 
                "directory": raw_dir,
                "entries": res.get("entries", []), 
                "total": res.get("total", 0),
                "truncated": res.get("truncated", False),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif tool_name == "search_files":
        query = arguments.get("query", "")
        ext_filter = arguments.get("extension_filter")
        limit = int(arguments.get("limit", 10))
        try:
            results = file_utils.search_files(
                query=query,
                extension_filter=ext_filter,
                limit=limit,
                directory=arguments.get("directory"),
            )
            return {"status": "success", "results": results}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif tool_name == "read_file_content":
        file_path = arguments.get("file_path")
        if not file_path or not isinstance(file_path, str) or not file_path.strip():
            return {"status": "error", "message": "Argument 'file_path' must be a non-empty string."}
        try:
            return file_utils.read_file_content(file_path_str=file_path)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif tool_name == "write_file_content":
        file_path = arguments.get("file_path", "")
        content = arguments.get("content", "")
        mode = arguments.get("mode", "write")
        try:
            return file_utils.write_file_content(file_path, content, mode)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif tool_name == "open_application":
        app_name = arguments.get("app_name", "")
        return system_utils.open_application(app_name)

    elif tool_name == "close_application":
        app_name = arguments.get("app_name", "")
        return system_utils.close_application(app_name)

    elif tool_name == "search_web":
        query = arguments.get("query", "")
        return await web_utils.search_web(query)

    elif tool_name == "get_conversation_history":
        conv_id = arguments.get("conversation_id")
        if not conv_id or not isinstance(conv_id, str) or not conv_id.strip():
            return {"status": "error", "message": "Argument 'conversation_id' must be a non-empty string."}
        raw_limit = arguments.get("limit", 20)
        limit = int(raw_limit)
        try:
            messages = repository.get_messages(conversation_id=conv_id.strip(), limit=min(max(1, limit), 50))
            bounded_messages = [
                {"role": m["role"], "content": m["content"][:500], "created_at": m["created_at"]}
                for m in messages
            ]
            return {"status": "success", "conversation_id": conv_id, "messages": bounded_messages}
        except Exception as e:
            return {"status": "error", "message": f"Failed to retrieve history: {e}"}

    elif tool_name == "search_conversations":
        query = arguments.get("query", "").strip()
        if not query:
            return {"status": "error", "message": "Query cannot be empty."}
        try:
            results = repository.search_conversations(query=query, limit=arguments.get("limit", 5))
            return {"status": "success", "results": results}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    else:
        return {"status": "error", "message": f"Tool '{tool_name}' is not allowed or registered."}


def _execute_registered_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronous adapter for tool execution where required."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            if tool_name == "search_web":
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    return executor.submit(asyncio.run, _execute_registered_tool_async(tool_name, arguments)).result()
            else:
                return asyncio.run(_execute_registered_tool_async(tool_name, arguments))
        else:
            return loop.run_until_complete(_execute_registered_tool_async(tool_name, arguments))
    except Exception:
        if tool_name == "list_directory":
            return file_utils.list_directory(arguments.get("directory", ""))
        elif tool_name == "search_files":
            return {"status": "success", "results": file_utils.search_files(arguments.get("query", ""))}
        elif tool_name == "read_file_content":
            return file_utils.read_file_content(arguments.get("file_path", ""))
        elif tool_name == "open_application":
            return system_utils.open_application(arguments.get("app_name", ""))
        elif tool_name == "close_application":
            return system_utils.close_application(arguments.get("app_name", ""))
        elif tool_name == "write_file_content":
            return file_utils.write_file_content(arguments.get("file_path", ""), arguments.get("content", ""))
        elif tool_name == "search_conversations":
            return {"status": "success", "results": repository.search_conversations(arguments.get("query", ""))}
        elif tool_name == "get_conversation_history":
            msgs = repository.get_messages(arguments.get("conversation_id", ""))
            return {"status": "success", "messages": msgs}
        return {"status": "error", "message": f"Tool execution failed for {tool_name}"}


async def process_message(
    user_message: str,
    conversation_id: Optional[str] = None
) -> Dict[str, Any]:
    from app.core.telemetry import PerformanceTracker
    tracker = PerformanceTracker()

    if not isinstance(user_message, str) or not user_message.strip():
        raise ValueError("User message cannot be empty.")

    trimmed_message = user_message.strip()

    # Active conversation setup
    if conversation_id:
        active_conv_id = conversation_id
    else:
        title = _generate_title(trimmed_message)
        active_conv_id = repository.create_conversation(title=title)

    repository.add_message(conversation_id=active_conv_id, role="user", content=trimmed_message)

    # 1. Deterministic Fast-Path Check (Instant response < 20ms)
    t_route_start = time.perf_counter()
    routed_res = await try_fast_route_async(trimmed_message)
    tracker.record("deterministic_routing_ms", (time.perf_counter() - t_route_start) * 1000)

    if routed_res is not None:
        reply_text = routed_res["reply"]
        repository.add_message(conversation_id=active_conv_id, role="assistant", content=reply_text)
        return {
            "reply": reply_text,
            "conversation_id": active_conv_id,
            "metrics": tracker.get_summary()
        }

    # 2. General Conversation Flow via Ollama with smart live grounding
    db_messages = repository.get_messages(active_conv_id)
    bounded_messages = db_messages[-MAX_HISTORY_MESSAGES:]

    # Check for live web/news search intent
    web_query = extract_web_search_query(trimmed_message, bounded_messages)
    injected_web_context = ""
    if web_query:
        t_web_start = time.perf_counter()
        search_res = await web_utils.search_web(web_query, max_results=4)
        tracker.record("web_search_prefetch_ms", (time.perf_counter() - t_web_start) * 1000)
        results = search_res.get("results", [])
        if results:
            lines = [f"\n[LIVE WEB EVIDENCE FOR: '{web_query}']"]
            for r in results[:3]:
                src = r.get("source", "Web")
                date = r.get("pub_date", "")
                date_str = f" ({date})" if date else ""
                snip = r.get("snippet", "")[:140].strip()
                lines.append(f"- {src}{date_str}: {r.get('title')}. {snip}")
            lines.append("[END EVIDENCE]\n")
            lines.append(
                "CRITICAL VOICE ASSISTANT INSTRUCTION:\n"
                "- You are Jarvis speaking aloud to the user right now.\n"
                "- Summarize the key facts, numbers, dates, and sources clearly in 2 to 3 natural spoken sentences.\n"
                "- Cite publishers naturally (e.g., 'According to Reuters...', 'As reported by The Verge...').\n"
                "- Never say 'I am checking' or 'I will search' because the search is already complete.\n"
                "- Avoid bullet points, URLs, or markdown tables because your words will be spoken by text-to-speech.\n"
            )
            injected_web_context = "\n".join(lines)

    # Check for local file mention
    file_mention = re.search(r"\b([a-zA-Z0-9_\-\.\/\\:]+\.(?:py|txt|md|json|csv|html|css|js|ts|tsx|docx|pdf))\b", trimmed_message)
    injected_file_context = ""
    if file_mention and not injected_web_context:
        candidate_file = file_mention.group(1)
        found = file_utils.smart_find_file(candidate_file)
        if found:
            try:
                res = file_utils.read_file_content(str(found))
                content_snip = res.get("content", "")[:6000]
                injected_file_context = f"\n[Referenced File Content of '{found.name}']:\n{content_snip}\n[End of File Content]\n"
            except Exception:
                pass

    sys_prompt = _build_system_prompt()
    if injected_web_context:
        sys_prompt += "\n" + injected_web_context
    elif injected_file_context:
        sys_prompt += "\n" + injected_file_context

    model_payload = [{"role": "system", "content": sys_prompt}]
    for msg in bounded_messages:
        model_payload.append({"role": msg["role"], "content": msg["content"]})

    needs_tool_check = _should_check_tools(trimmed_message, bounded_messages) and not injected_web_context and not injected_file_context
    final_reply = ""
    tool_round = 0

    while tool_round < MAX_TOOL_ROUNDS:
        t_llm_start = time.perf_counter()
        res = await generate_chat_completion(
            messages=model_payload,
            tools=CONVERSATION_TOOLS if needs_tool_check else None,
        )
        tracker.record("ollama_llm_ms", (time.perf_counter() - t_llm_start) * 1000)

        if isinstance(res, dict):
            content = res.get("content", "")
            tool_calls = res.get("tool_calls", [])
        else:
            content = str(res)
            tool_calls = []

        if not tool_calls:
            final_reply = content
            break

        tool_round += 1
        model_payload.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
        for tc in tool_calls[:MAX_CALLS_PER_ROUND]:
            func_obj = tc.get("function", {})
            func_name = func_obj.get("name", "")
            func_args = func_obj.get("arguments", {})
            if isinstance(func_args, str):
                try:
                    func_args = json.loads(func_args)
                except Exception:
                    func_args = {}

            t_tool_start = time.perf_counter()
            tool_result = await _execute_registered_tool_async(func_name, func_args)
            tracker.record(f"tool_{func_name}_ms", (time.perf_counter() - t_tool_start) * 1000)

            model_payload.append({
                "role": "tool",
                "name": func_name,
                "content": json.dumps(tool_result)
            })

    if not final_reply and tool_round > 0:
        t_pass2_start = time.perf_counter()
        fallback_res = await generate_chat_completion(messages=model_payload, tools=None)
        tracker.record("ollama_pass2_ms", (time.perf_counter() - t_pass2_start) * 1000)
        final_reply = fallback_res.get("content", "") if isinstance(fallback_res, dict) else str(fallback_res)

    if not final_reply.strip():
        final_reply = "I completed the request."

    repository.add_message(conversation_id=active_conv_id, role="assistant", content=final_reply)

    return {
        "reply": final_reply,
        "conversation_id": active_conv_id,
        "metrics": tracker.get_summary()
    }


async def process_message_stream(
    user_message: str,
    conversation_id: Optional[str] = None
) -> AsyncGenerator[str, None]:
    from app.core.telemetry import PerformanceTracker
    tracker = PerformanceTracker()

    if not isinstance(user_message, str) or not user_message.strip():
        raise ValueError("User message cannot be empty.")

    trimmed_message = user_message.strip()
    if conversation_id:
        active_conv_id = conversation_id
    else:
        active_conv_id = repository.create_conversation(title=_generate_title(trimmed_message))

    repository.add_message(
        conversation_id=active_conv_id,
        role="user",
        content=trimmed_message
    )

    db_messages = repository.get_messages(active_conv_id)[-MAX_HISTORY_MESSAGES:]

    # 1. Deterministic Fast Route: Answers immediately in <20ms
    t_route_start = time.perf_counter()
    deterministic_res = await try_fast_route_async(trimmed_message, db_messages)
    tracker.record("deterministic_routing_ms", (time.perf_counter() - t_route_start) * 1000)

    if deterministic_res is not None:
        reply = deterministic_res["reply"]
        repository.add_message(
            conversation_id=active_conv_id,
            role="assistant",
            content=reply
        )
        yield f"event: chunk\ndata: {json.dumps({'text': reply})}\n\n"
        yield f"event: meta\ndata: {json.dumps({'conversation_id': active_conv_id, 'metrics': tracker.get_summary()})}\n\n"
        yield "event: done\ndata: [DONE]\n\n"
        return

    # 2. Smart Live Web / News Pre-Fetching (Factual Grounding)
    web_query = extract_web_search_query(trimmed_message, db_messages)
    injected_web_context = ""
    if web_query:
        t_web_start = time.perf_counter()
        search_res = await web_utils.search_web(web_query, max_results=4)
        tracker.record("web_search_prefetch_ms", (time.perf_counter() - t_web_start) * 1000)
        results = search_res.get("results", [])
        if results:
            lines = [f"\n[LIVE WEB EVIDENCE FOR: '{web_query}']"]
            for r in results[:3]:
                src = r.get("source", "Web")
                date = r.get("pub_date", "")
                date_str = f" ({date})" if date else ""
                snip = r.get("snippet", "")[:140].strip()
                lines.append(f"- {src}{date_str}: {r.get('title')}. {snip}")
            lines.append("[END EVIDENCE]\n")
            lines.append(
                "CRITICAL VOICE ASSISTANT INSTRUCTION:\n"
                "- You are Jarvis speaking aloud to the user right now.\n"
                "- Summarize the key facts, numbers, dates, and sources clearly in 2 to 3 natural spoken sentences.\n"
                "- Cite publishers naturally (e.g., 'According to Reuters...', 'As reported by The Verge...').\n"
                "- Never say 'I am checking' or 'I will search' because the search is already complete.\n"
                "- Avoid bullet points, URLs, or markdown tables because your words will be spoken by text-to-speech.\n"
            )
            injected_web_context = "\n".join(lines)

    # 3. Smart Local File Pre-Fetching:
    file_mention = re.search(r"\b([a-zA-Z0-9_\-\.\/\\:]+\.(?:py|txt|md|json|csv|html|css|js|ts|tsx|docx|pdf))\b", trimmed_message)
    injected_file_context = ""
    if file_mention and not injected_web_context:
        candidate_file = file_mention.group(1)
        found = file_utils.smart_find_file(candidate_file)
        if found:
            try:
                res = file_utils.read_file_content(str(found))
                content_snip = res.get("content", "")[:6000]
                injected_file_context = f"\n[Referenced File Content of '{found.name}']:\n{content_snip}\n[End of File Content]\n"
            except Exception:
                pass

    sys_prompt = _build_system_prompt()
    if injected_web_context:
        sys_prompt += "\n" + injected_web_context
    elif injected_file_context:
        sys_prompt += "\n" + injected_file_context

    model_payload = [{"role": "system", "content": sys_prompt}]
    model_payload.extend(
        {"role": message["role"], "content": message["content"]}
        for message in db_messages
    )

    needs_tool_check = _should_check_tools(trimmed_message, db_messages) and not injected_web_context and not injected_file_context
    tool_round = 0
    while needs_tool_check and tool_round < MAX_TOOL_ROUNDS:
        t_llm_start = time.perf_counter()
        res = await generate_chat_completion(
            messages=model_payload,
            tools=CONVERSATION_TOOLS,
        )
        tracker.record("ollama_llm_ms", (time.perf_counter() - t_llm_start) * 1000)

        tool_calls = res.get("tool_calls", []) if isinstance(res, dict) else []
        if not tool_calls:
            break

        tool_round += 1
        content = res.get("content", "")
        model_payload.append({
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls
        })

        for tool_call in tool_calls[:MAX_CALLS_PER_ROUND]:
            function = tool_call.get("function", {})
            tool_name = function.get("name", "")
            tool_arguments = function.get("arguments", {})
            if isinstance(tool_arguments, str):
                try:
                    tool_arguments = json.loads(tool_arguments)
                except json.JSONDecodeError:
                    tool_arguments = {}

            t_tool_start = time.perf_counter()
            tool_result = await _execute_registered_tool_async(tool_name, tool_arguments)
            tracker.record(
                f"tool_{tool_name}_ms",
                (time.perf_counter() - t_tool_start) * 1000
            )
            model_payload.append({
                "role": "tool",
                "name": tool_name,
                "content": json.dumps(tool_result)
            })

    # 4. Stream tokens directly to client
    full_text_acc = []
    t_stream_start = time.perf_counter()
    async for text_chunk in stream_chat_completion(model_payload):
        full_text_acc.append(text_chunk)
        yield f"event: chunk\ndata: {json.dumps({'text': text_chunk})}\n\n"
    tracker.record("ollama_stream_ms", (time.perf_counter() - t_stream_start) * 1000)

    full_reply = "".join(full_text_acc).strip()
    if not full_reply:
        full_reply = "Done."
        yield f"event: chunk\ndata: {json.dumps({'text': full_reply})}\n\n"

    repository.add_message(
        conversation_id=active_conv_id,
        role="assistant",
        content=full_reply
    )

    yield f"event: meta\ndata: {json.dumps({'conversation_id': active_conv_id, 'metrics': tracker.get_summary()})}\n\n"
    yield "event: done\ndata: [DONE]\n\n"
