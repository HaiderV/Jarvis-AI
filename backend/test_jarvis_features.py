import pytest
import asyncio
from pathlib import Path
from app.tools import file_utils
from app.tools import system_utils
from app.tools import web_utils
from app.agent.router import try_deterministic_route, try_fast_route_async, extract_web_search_query

@pytest.mark.asyncio
async def test_router_web_search():
    query = extract_web_search_query("search web for Python FastAPI")
    assert query is not None
    assert "fastapi" in query.lower()
    res = await web_utils.search_web(query, max_results=3)
    assert res.get("status") == "success"
    assert len(res.get("results", [])) > 0

def test_resolve_jarvis_directory():
    folder = file_utils.resolve_permitted_folder("jarvis")
    assert folder.exists()
    assert "jarvis" in str(folder).lower()

def test_fast_file_search():
    res = file_utils.search_files(query="main.py", limit=5)
    assert len(res) > 0
    assert any("main.py" in r["file_name"] for r in res)

def test_smart_read_file():
    res = file_utils.read_file_content("main.py")
    assert res["status"] == "success"
    assert "FastAPI" in res["content"]

def test_write_and_read_temporary_file(tmp_path):
    # Test file writing in user documents / permitted
    res = file_utils.write_file_content("test_jarvis_note.txt", "Jarvis assistant verified!")
    assert res["status"] == "success"
    written_path = Path(res["file_path"])
    assert written_path.exists()
    
    # Read it back
    read_res = file_utils.read_file_content(str(written_path))
    assert "Jarvis assistant verified!" in read_res["content"]
    
    # Clean up
    try:
        written_path.unlink()
    except Exception:
        pass

def test_router_time_and_date():
    t_res = try_deterministic_route("What time is it?")
    assert t_res is not None
    assert "current time is" in t_res["reply"]

    d_res = try_deterministic_route("What is today's date?")
    assert d_res is not None
    assert "Today is" in d_res["reply"]

def test_router_math():
    m_res = try_deterministic_route("calculate 25 * 4")
    assert m_res is not None
    assert "100" in m_res["reply"]

def test_router_app_control():
    # Test open command detection
    app_res = try_deterministic_route("open notepad")
    assert app_res is not None
    assert app_res["action"] == "open_app"

    # Test close command detection
    close_res = try_deterministic_route("close notepad")
    assert close_res is not None
    assert close_res["action"] == "close_app"

