#!/usr/bin/env python3
"""Comprehensive live test of KaiClient functionality."""

import asyncio
import os
import sys
import time
import traceback
from pathlib import Path

# Load .env.local manually
env_file = Path(__file__).parent.parent / ".env.local"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip()

from kai_client import KaiClient  # noqa: E402


class TestResult:
    def __init__(self, name: str, passed: bool, duration: float, details: str = ""):
        self.name = name
        self.passed = passed
        self.duration = duration
        self.details = details


results: list[TestResult] = []


def record(name: str, passed: bool, duration: float, details: str = ""):
    results.append(TestResult(name, passed, duration, details))
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name} ({duration:.1f}s)")
    if details and not passed:
        for line in details.splitlines()[:5]:
            print(f"         {line}")


async def main():
    token = os.environ.get("STORAGE_API_TOKEN")
    url = os.environ.get("STORAGE_API_URL")

    if not token or not url:
        print("Error: STORAGE_API_TOKEN and STORAGE_API_URL must be set")
        sys.exit(1)

    print("=" * 70)
    print("KaiClient Comprehensive Live Test")
    print("=" * 70)
    print(f"Storage API URL: {url}")
    print()

    # =========================================================================
    # TEST 1: Service Discovery
    # =========================================================================
    print("[1/12] Service Discovery (from_storage_api)")
    t0 = time.time()
    try:
        client = await KaiClient.from_storage_api(
            storage_api_token=token,
            storage_api_url=url,
        )
        dur = time.time() - t0
        record("Service Discovery", True, dur, f"Discovered URL: {client.base_url}")
        print(f"         Kai URL: {client.base_url}")
    except Exception as e:
        dur = time.time() - t0
        record("Service Discovery", False, dur, str(e))
        print(f"FATAL: Cannot continue without service discovery. Error: {e}")
        sys.exit(1)

    async with client:
        # =====================================================================
        # TEST 2: Ping
        # =====================================================================
        print("\n[2/12] Ping (Health Check)")
        t0 = time.time()
        try:
            ping = await client.ping()
            dur = time.time() - t0
            record("Ping", True, dur, f"Timestamp: {ping.timestamp}")
            print(f"         Timestamp: {ping.timestamp}")
        except Exception as e:
            dur = time.time() - t0
            record("Ping", False, dur, str(e))

        # =====================================================================
        # TEST 3: Server Info
        # =====================================================================
        print("\n[3/12] Server Info")
        t0 = time.time()
        try:
            info = await client.info()
            dur = time.time() - t0
            details = f"App: {info.app_name} v{info.app_version}, MCP servers: {len(info.connected_mcp)}"
            record("Server Info", True, dur, details)
            print(f"         {details}")
        except Exception as e:
            dur = time.time() - t0
            record("Server Info", False, dur, str(e))

        # =====================================================================
        # TEST 4: Simple Chat (streaming) - General Knowledge
        # =====================================================================
        print("\n[4/12] Streaming Chat - General Knowledge Question")
        t0 = time.time()
        chat_id_1 = client.new_chat_id()
        response_text = []
        event_types_seen = set()
        try:
            async for event in client.send_message(
                chat_id_1,
                "What is Keboola? Answer in 2 sentences max.",
            ):
                event_types_seen.add(event.type)
                if event.type == "text":
                    response_text.append(event.text)
            dur = time.time() - t0
            full_response = "".join(response_text)
            passed = len(full_response) > 10 and "text" in event_types_seen
            record(
                "Streaming Chat - General Knowledge",
                passed,
                dur,
                f"Events: {event_types_seen}, Response length: {len(full_response)} chars",
            )
            print(f"         Events seen: {event_types_seen}")
            print(f"         Response preview: {full_response[:120]}...")
        except Exception as e:
            dur = time.time() - t0
            record("Streaming Chat - General Knowledge", False, dur, traceback.format_exc())

        # =====================================================================
        # TEST 5: Non-streaming Chat Convenience Method
        # =====================================================================
        print("\n[5/12] Non-Streaming Chat (convenience method)")
        t0 = time.time()
        try:
            chat_id_2, response = await client.chat(
                "What are Keboola transformations? One sentence only."
            )
            dur = time.time() - t0
            passed = len(response) > 10 and isinstance(chat_id_2, str)
            record(
                "Non-Streaming Chat",
                passed,
                dur,
                f"Chat ID: {chat_id_2[:8]}..., Response: {len(response)} chars",
            )
            print(f"         Response preview: {response[:120]}...")
        except Exception as e:
            dur = time.time() - t0
            record("Non-Streaming Chat", False, dur, traceback.format_exc())

        # =====================================================================
        # TEST 6: Multi-turn Conversation (continue a chat)
        # =====================================================================
        print("\n[6/12] Multi-turn Conversation")
        t0 = time.time()
        chat_id_3 = client.new_chat_id()
        try:
            # First message
            _, first_response = await client.chat(
                "My name is TestBot. Remember that for the conversation.",
                chat_id=chat_id_3,
            )
            # Follow-up message in same chat
            follow_up_text = []
            async for event in client.send_message(
                chat_id_3,
                "What is my name? Just say the name, nothing else.",
            ):
                if event.type == "text":
                    follow_up_text.append(event.text)
            dur = time.time() - t0
            follow_up = "".join(follow_up_text).strip().lower()
            passed = "testbot" in follow_up
            record(
                "Multi-turn Conversation",
                passed,
                dur,
                f"Follow-up response: '{follow_up[:80]}'",
            )
            print(f"         Follow-up: {follow_up[:80]}")
        except Exception as e:
            dur = time.time() - t0
            record("Multi-turn Conversation", False, dur, traceback.format_exc())

        # =====================================================================
        # TEST 7: Get Chat Details
        # =====================================================================
        print("\n[7/12] Get Chat Details")
        t0 = time.time()
        try:
            chat_detail = await client.get_chat(chat_id_3)
            dur = time.time() - t0
            msg_count = len(chat_detail.messages) if chat_detail.messages else 0
            passed = chat_detail.id == chat_id_3 and msg_count >= 2
            record(
                "Get Chat Details",
                passed,
                dur,
                f"Chat ID matches: {chat_detail.id == chat_id_3}, Messages: {msg_count}",
            )
            print(f"         Messages in chat: {msg_count}")
        except Exception as e:
            dur = time.time() - t0
            record("Get Chat Details", False, dur, traceback.format_exc())

        # =====================================================================
        # TEST 8: Chat History
        # =====================================================================
        print("\n[8/12] Chat History")
        t0 = time.time()
        try:
            history = await client.get_history(limit=5)
            dur = time.time() - t0
            passed = isinstance(history.chats, list) and len(history.chats) > 0
            record(
                "Chat History",
                passed,
                dur,
                f"Chats returned: {len(history.chats)}, has_more: {history.has_more}",
            )
            print(f"         Chats returned: {len(history.chats)}, has_more: {history.has_more}")
        except Exception as e:
            dur = time.time() - t0
            record("Chat History", False, dur, traceback.format_exc())

        # =====================================================================
        # TEST 9: Data/SQL Question (tests Kai's domain expertise)
        # =====================================================================
        print("\n[9/12] Domain-Specific Question (SQL/Data)")
        t0 = time.time()
        try:
            _, sql_response = await client.chat(
                "Write a simple SQL query that selects all columns from a table called 'orders' where the amount is greater than 100. Just the SQL, no explanation."
            )
            dur = time.time() - t0
            passed = "select" in sql_response.lower() and "orders" in sql_response.lower()
            record(
                "Domain-Specific Question (SQL)",
                passed,
                dur,
                f"Response: {sql_response[:120]}",
            )
            print(f"         Response: {sql_response[:120]}")
        except Exception as e:
            dur = time.time() - t0
            record("Domain-Specific Question (SQL)", False, dur, traceback.format_exc())

        # =====================================================================
        # TEST 10: Tool-triggering question (list tables - read-only)
        # =====================================================================
        print("\n[10/12] Tool-Triggering Question (list project info)")
        t0 = time.time()
        chat_id_tools = client.new_chat_id()
        tool_events = []
        text_parts = []
        try:
            async for event in client.send_message(
                chat_id_tools,
                "What tables do I have in my Keboola project? Just list the first 5 table names.",
            ):
                if event.type == "text":
                    text_parts.append(event.text)
                elif event.type == "tool-call":
                    tool_events.append(
                        f"{event.tool_name} (state={event.state})"
                    )
                elif event.type == "step-start":
                    pass  # Normal
                elif event.type == "finish":
                    pass  # Normal
            dur = time.time() - t0
            full_text = "".join(text_parts)
            passed = len(full_text) > 0 or len(tool_events) > 0
            record(
                "Tool-Triggering Question",
                passed,
                dur,
                f"Tool calls: {tool_events[:5]}, Text length: {len(full_text)}",
            )
            print(f"         Tool calls: {tool_events[:3]}")
            print(f"         Response preview: {full_text[:120]}...")
        except Exception as e:
            dur = time.time() - t0
            record("Tool-Triggering Question", False, dur, traceback.format_exc())

        # =====================================================================
        # TEST 11: SSE Event Type Coverage
        # =====================================================================
        print("\n[11/12] SSE Event Type Coverage")
        t0 = time.time()
        chat_id_sse = client.new_chat_id()
        all_event_types = set()
        all_events_count = 0
        try:
            async for event in client.send_message(
                chat_id_sse,
                "List the buckets in my Keboola project.",
            ):
                all_event_types.add(event.type)
                all_events_count += 1
            dur = time.time() - t0
            # We expect at minimum text and finish events
            passed = "text" in all_event_types and "finish" in all_event_types
            record(
                "SSE Event Type Coverage",
                passed,
                dur,
                f"Event types: {all_event_types}, Total events: {all_events_count}",
            )
            print(f"         Event types: {all_event_types}")
            print(f"         Total events: {all_events_count}")
        except Exception as e:
            dur = time.time() - t0
            record("SSE Event Type Coverage", False, dur, traceback.format_exc())

        # =====================================================================
        # TEST 12: Delete Chat
        # =====================================================================
        print("\n[12/12] Delete Chat")
        t0 = time.time()
        try:
            await client.delete_chat(chat_id_1)
            dur = time.time() - t0
            # Verify deletion by trying to fetch it
            try:
                await client.get_chat(chat_id_1)
                record("Delete Chat", False, dur, "Chat still accessible after deletion")
            except Exception:
                record("Delete Chat", True, dur, f"Chat {chat_id_1[:8]}... deleted successfully")
                print(f"         Deleted chat {chat_id_1[:8]}...")
        except Exception as e:
            dur = time.time() - t0
            record("Delete Chat", False, dur, traceback.format_exc())

    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    passed_count = sum(1 for r in results if r.passed)
    total_count = len(results)
    total_time = sum(r.duration for r in results)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.name} ({r.duration:.1f}s)")

    print(f"\n  {passed_count}/{total_count} tests passed in {total_time:.1f}s total")

    if passed_count < total_count:
        print("\n  Failed tests:")
        for r in results:
            if not r.passed:
                print(f"    - {r.name}: {r.details[:100]}")

    print("=" * 70)
    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
