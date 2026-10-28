import sys
import asyncio
from unittest.mock import patch, AsyncMock
from app.database.connection import init_db, get_db_connection
from app.database import repository
from app.agent.service import process_message

async def test_automatic_conversation_recall():
    print("Initializing Automatic Conversation Recall Regression Test...")
    init_db()

    test_conv_ids = []

    try:
        # Step 1: Pre-populate an earlier isolated conversation in SQLite
        past_conv_id = repository.create_conversation(title="Naming Jarvis Origin")
        test_conv_ids.append(past_conv_id)
        
        repository.add_message(
            past_conv_id, 
            "user", 
            "I named you Jarvis because my friend Chaitanya loves Tony Stark from Marvel Avengers, and Tony Stark's AI assistant was named Jarvis."
        )
        repository.add_message(
            past_conv_id, 
            "assistant", 
            "That's awesome! I'm honored to be named after Tony Stark's AI assistant."
        )
        print("[PASS] Pre-populated historic conversation record.")

        # Step 2: Test automatic tool invocation on "do you remember" query
        with patch("app.agent.service.generate_chat_completion", new_callable=AsyncMock) as mock_llm:
            # Simulate Ollama automatically triggering search_conversations, then get_conversation_history, then giving final answer
            mock_llm.side_effect = [
                # Turn 1: Model automatically requests search_conversations
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "search_conversations",
                                "arguments": {"query": "Jarvis"}
                            }
                        }
                    ]
                },
                # Turn 2: Model requests get_conversation_history for found ID
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "get_conversation_history",
                                "arguments": {"conversation_id": past_conv_id}
                            }
                        }
                    ]
                },
                # Turn 3: Model returns direct answer grounded in retrieved history
                "You named me Jarvis because your friend Chaitanya loves Tony Stark from Marvel Avengers, and Tony Stark's AI assistant was named Jarvis!"
            ]

            res = await process_message("Bro, do you remember why I named you Jarvis?")
            test_conv_ids.append(res["conversation_id"])

            assert res["reply"] == "You named me Jarvis because your friend Chaitanya loves Tony Stark from Marvel Avengers, and Tony Stark's AI assistant was named Jarvis!"
            assert mock_llm.call_count == 3
            print("[PASS] Automatic search & recall successfully executed and answered from evidence.")

        # Step 3: Test that an ordinary question does NOT trigger recall tools
        with patch("app.agent.service.generate_chat_completion", new_callable=AsyncMock) as mock_llm_ordinary:
            mock_llm_ordinary.return_value = {
                "content": "Paris is the capital of France.",
                "tool_calls": []
            }

            ord_res = await process_message("What is the capital of France?")
            test_conv_ids.append(ord_res["conversation_id"])

            assert ord_res["reply"] == "Paris is the capital of France."
            assert mock_llm_ordinary.call_count == 1
            print("[PASS] Ordinary non-recall query answered directly without tool calls.")

        print("\nAutomatic Conversation Recall regression tests completed successfully!")

    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        sys.exit(1)
    finally:
        if test_conv_ids:
            conn = get_db_connection()
            try:
                with conn:
                    placeholders = ",".join(["?"] * len(test_conv_ids))
                    conn.execute(f"DELETE FROM conversations WHERE id IN ({placeholders});", test_conv_ids)
                print(f"Cleaned up {len(test_conv_ids)} test conversation(s).")
            finally:
                conn.close()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_automatic_conversation_recall())