import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.database.connection import get_db_connection

def _get_utc_now() -> str:
    """Helper to get current ISO 8601 formatted UTC timestamp string."""
    return datetime.now(timezone.utc).isoformat()

def create_conversation(title: Optional[str] = None) -> str:
    conv_id = str(uuid.uuid4())
    now = _get_utc_now()

    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?);",
                (conv_id, title.strip() if title else None, now, now)
            )
        return conv_id
    finally:
        conn.close()

def add_message(conversation_id: str, role: str, content: str) -> str:
    if role not in ("user", "assistant"):
        raise ValueError(f"Invalid role '{role}'. Must be either 'user' or 'assistant'.")

    if not isinstance(content, str) or not content.strip():
        raise ValueError("Message content cannot be empty or contain only whitespace.")

    msg_id = str(uuid.uuid4())
    now = _get_utc_now()

    conn = get_db_connection()
    try:
        with conn:
            cursor = conn.execute("SELECT 1 FROM conversations WHERE id = ?;", (conversation_id,))
            if not cursor.fetchone():
                raise ValueError(f"Conversation with ID '{conversation_id}' does not exist.")

            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?);",
                (msg_id, conversation_id, role, content.strip(), now)
            )

            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?;",
                (now, conversation_id)
            )
        return msg_id
    finally:
        conn.close()

def get_messages(conversation_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Retrieves messages for a given conversation in chronological order.
    Optional limit restricts to the N most recent messages.
    """
    conn = get_db_connection()
    try:
        cursor = conn.execute("SELECT 1 FROM conversations WHERE id = ?;", (conversation_id,))
        if not cursor.fetchone():
            raise ValueError(f"Conversation with ID '{conversation_id}' does not exist.")

        if limit is not None and limit > 0:
            query = """
                SELECT id, conversation_id, role, content, created_at 
                FROM (
                    SELECT id, conversation_id, role, content, created_at 
                    FROM messages 
                    WHERE conversation_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ) ORDER BY created_at ASC;
            """
            cursor = conn.execute(query, (conversation_id, limit))
        else:
            query = """
                SELECT id, conversation_id, role, content, created_at 
                FROM messages 
                WHERE conversation_id = ? 
                ORDER BY created_at ASC;
            """
            cursor = conn.execute(query, (conversation_id,))

        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "conversation_id": row["conversation_id"],
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"]
            }
            for row in rows
        ]
    finally:
        conn.close()

def list_conversations() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            SELECT id, title, created_at, updated_at 
            FROM conversations 
            ORDER BY updated_at DESC, created_at DESC;
            """
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            }
            for row in rows
        ]
    finally:
        conn.close()

def search_conversations(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Searches conversation titles and message contents using parameterized SQL.
    
    Args:
        query: Search string.
        limit: Max results to return.
        
    Returns:
        List of matching conversation metadata and matching content snippets.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query cannot be empty or whitespace.")

    capped_limit = min(max(1, limit), 10)
    clean_query = query.strip()[:100]
    pattern = f"%{clean_query}%"

    conn = get_db_connection()
    try:
        sql = """
            SELECT DISTINCT c.id, c.title, c.updated_at
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
            WHERE c.title LIKE ? OR m.content LIKE ?
            ORDER BY c.updated_at DESC
            LIMIT ?;
        """
        cursor = conn.execute(sql, (pattern, pattern, capped_limit))
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "updated_at": row["updated_at"]
            }
            for row in rows
        ]
    finally:
        conn.close()