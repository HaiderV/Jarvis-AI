import os
import json
import asyncio
import httpx
from typing import List, Dict, Any, AsyncGenerator, Optional

OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
MODEL_NAME = os.getenv("JARVIS_MODEL", "qwen2.5:3b")
KEEP_ALIVE = "1h"
CPU_THREADS = min(8, os.cpu_count() or 8)

# Connection pool keyed by active event loop to guarantee safety across server & test runs
_ollama_clients: Dict[Any, httpx.AsyncClient] = {}

def get_ollama_http_client() -> httpx.AsyncClient:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop:
        client = _ollama_clients.get(loop)
        if client is None or client.is_closed:
            client = httpx.AsyncClient(timeout=60.0)
            _ollama_clients[loop] = client
        return client
    return httpx.AsyncClient(timeout=60.0)


async def generate_chat_completion(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Non-streaming generation used for tool selection rounds."""
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "num_thread": CPU_THREADS,
            "temperature": 0.3,
            "top_p": 0.9,
        }
    }
    if tools:
        payload["tools"] = tools

    client = get_ollama_http_client()
    response = await client.post(OLLAMA_CHAT_URL, json=payload)
    response.raise_for_status()
    data = response.json()
    return data.get("message", {})


async def stream_chat_completion(messages: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
    """Streams generated text tokens incrementally for the final response pass."""
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "num_thread": CPU_THREADS,
            "temperature": 0.3,
            "top_p": 0.9,
        }
    }

    client = get_ollama_http_client()
    async with client.stream("POST", OLLAMA_CHAT_URL, json=payload) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
                delta = chunk.get("message", {}).get("content", "")
                if delta:
                    yield delta
            except json.JSONDecodeError:
                continue
