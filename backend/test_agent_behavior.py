# backend/tests/test_agent_behavior.py
import pytest
import asyncio
from app.agent.service import process_message
from app.agent.router import try_deterministic_route

@pytest.mark.asyncio
async def test_general_knowledge_no_tools():
    res = await process_message("What is the difference between RAM and ROM?")
    assert "RAM" in res["reply"] or "Read-Only Memory" in res["reply"]
    # Ensure it answered conversationally without throwing tool errors
    assert res["conversation_id"] is not None

@pytest.mark.asyncio
async def test_grammar_explanation():
    res = await process_message("Explain articles in English grammar.")
    assert "grammar" in res["reply"].lower() or "article" in res["reply"].lower()
    # Must produce explanation, not ask for files
    assert "file" not in res["reply"].lower() or "search" not in res["reply"].lower()

@pytest.mark.asyncio
async def test_greeting():
    res = await process_message("Hi Jarvis, how are you?")
    assert len(res["reply"]) > 5
    assert "file" not in res["reply"].lower()

def test_deterministic_router_listing():
    routed = try_deterministic_route("Show all files and folders inside Documents")
    assert routed is not None
    assert routed["routed_deterministically"] is True
    assert "Documents" in routed["reply"]

def test_deterministic_router_ignores_questions():
    routed = try_deterministic_route("How do I list files in Downloads?")
    assert routed is None  # Should pass through to Gemma for explanation