"""Tests for the KaiClient."""

import json
import uuid

import httpx
import pytest
from pytest_httpx import HTTPXMock

from kai_client import (
    KaiAuthenticationError,
    KaiBadRequestError,
    KaiClient,
    KaiConnectionError,
    KaiError,
    KaiForbiddenError,
    KaiNotFoundError,
    KaiRateLimitError,
)


@pytest.fixture
def client():
    """Create a KaiClient instance for testing."""
    return KaiClient(
        storage_api_token="test-token",
        storage_api_url="https://connection.test.keboola.com",
        base_url="http://localhost:3000",
    )


class TestKaiClientInit:
    """Tests for KaiClient initialization."""

    def test_default_base_url(self):
        client = KaiClient(
            storage_api_token="token",
            storage_api_url="https://connection.keboola.com",
        )
        assert client.base_url == "http://localhost:3000"

    def test_custom_base_url(self):
        client = KaiClient(
            storage_api_token="token",
            storage_api_url="https://connection.keboola.com",
            base_url="https://kai.example.com/",
        )
        assert client.base_url == "https://kai.example.com"

    def test_custom_timeouts(self):
        client = KaiClient(
            storage_api_token="token",
            storage_api_url="https://connection.keboola.com",
            timeout=60.0,
            stream_timeout=120.0,
        )
        assert client.timeout == 60.0
        assert client.stream_timeout == 120.0


class TestUUIDGeneration:
    """Tests for UUID generation methods."""

    def test_new_chat_id_format(self):
        chat_id = KaiClient.new_chat_id()
        # Should be a valid UUID
        uuid.UUID(chat_id)

    def test_new_chat_id_unique(self):
        ids = [KaiClient.new_chat_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_new_message_id_format(self):
        message_id = KaiClient.new_message_id()
        uuid.UUID(message_id)

    def test_new_message_id_unique(self):
        ids = [KaiClient.new_message_id() for _ in range(100)]
        assert len(set(ids)) == 100


class TestPing:
    """Tests for the ping endpoint."""

    @pytest.mark.asyncio
    async def test_ping_success(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/ping",
            json={"timestamp": "2025-12-24T16:24:10.641Z"},
        )

        async with client:
            response = await client.ping()

        assert response.timestamp.year == 2025
        assert response.timestamp.month == 12

    @pytest.mark.asyncio
    async def test_ping_no_auth_headers(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Ping should not send auth headers."""
        httpx_mock.add_response(
            url="http://localhost:3000/ping",
            json={"timestamp": "2025-12-24T16:24:10.641Z"},
        )

        async with client:
            await client.ping()

        request = httpx_mock.get_request()
        assert "x-storageapi-token" not in request.headers
        assert "x-storageapi-url" not in request.headers


class TestInfo:
    """Tests for the info endpoint."""

    @pytest.mark.asyncio
    async def test_info_success(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api",
            json={
                "timestamp": "2025-12-24T16:24:10.641Z",
                "uptime": 12345.67,
                "appName": "kai-backend",
                "appVersion": "1.0.0",
                "serverVersion": "2.0.0",
                "connectedMcp": [
                    {"name": "keboola-mcp", "status": "connected"}
                ],
            },
        )

        async with client:
            response = await client.info()

        assert response.app_name == "kai-backend"
        assert response.app_version == "1.0.0"
        assert len(response.connected_mcp) == 1


class TestGetChat:
    """Tests for get_chat endpoint."""

    @pytest.mark.asyncio
    async def test_get_chat_success(self, client: KaiClient, httpx_mock: HTTPXMock):
        chat_id = "chat-123"
        httpx_mock.add_response(
            url=f"http://localhost:3000/api/chat/{chat_id}",
            json={
                "id": chat_id,
                "title": "Test Chat",
                "messages": [
                    {"id": "msg-1", "role": "user", "parts": []},
                    {"id": "msg-2", "role": "assistant", "parts": []},
                ],
            },
        )

        async with client:
            chat = await client.get_chat(chat_id)

        assert chat.id == chat_id
        assert chat.title == "Test Chat"
        assert len(chat.messages) == 2

    @pytest.mark.asyncio
    async def test_get_chat_includes_auth(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            json={"id": "chat-123", "messages": []},
        )

        async with client:
            await client.get_chat("chat-123")

        request = httpx_mock.get_request()
        assert request.headers["x-storageapi-token"] == "test-token"
        assert request.headers["x-storageapi-url"] == "https://connection.test.keboola.com"


class TestDeleteChat:
    """Tests for delete_chat endpoint."""

    @pytest.mark.asyncio
    async def test_delete_chat_success(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat?id=chat-123",
            method="DELETE",
            status_code=200,
            json={},
        )

        async with client:
            await client.delete_chat("chat-123")

        request = httpx_mock.get_request()
        assert request.method == "DELETE"


class TestGetHistory:
    """Tests for get_history endpoint."""

    @pytest.mark.asyncio
    async def test_get_history_success(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/history?limit=10",
            json={
                "chats": [
                    {"id": "chat-1", "title": "Chat 1"},
                    {"id": "chat-2", "title": "Chat 2"},
                ],
                "hasMore": True,
            },
        )

        async with client:
            history = await client.get_history(limit=10)

        assert len(history.chats) == 2
        assert history.has_more is True

    @pytest.mark.asyncio
    async def test_get_history_with_pagination(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/history?limit=20&starting_after=chat-5",
            json={"chats": [], "hasMore": False},
        )

        async with client:
            await client.get_history(limit=20, starting_after="chat-5")

        request = httpx_mock.get_request()
        assert "starting_after=chat-5" in str(request.url)


class TestVoting:
    """Tests for voting endpoints."""

    @pytest.mark.asyncio
    async def test_get_votes(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/vote?chatId=chat-123",
            json=[
                {"chatId": "chat-123", "messageId": "msg-1", "type": "up"},
            ],
        )

        async with client:
            votes = await client.get_votes("chat-123")

        assert len(votes) == 1
        assert votes[0].type == "up"

    @pytest.mark.asyncio
    async def test_vote(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/vote",
            method="PATCH",
            json={
                "chatId": "chat-123",
                "messageId": "msg-456",
                "type": "up",
            },
        )

        async with client:
            vote = await client.vote("chat-123", "msg-456", "up")

        assert vote.chat_id == "chat-123"
        assert vote.message_id == "msg-456"
        assert vote.type == "up"

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["chatId"] == "chat-123"
        assert body["messageId"] == "msg-456"
        assert body["type"] == "up"

    @pytest.mark.asyncio
    async def test_upvote(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/vote",
            method="PATCH",
            json={
                "chatId": "chat-123",
                "messageId": "msg-456",
                "type": "up",
            },
        )

        async with client:
            vote = await client.upvote("chat-123", "msg-456")

        assert vote.type == "up"

    @pytest.mark.asyncio
    async def test_downvote(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/vote",
            method="PATCH",
            json={
                "chatId": "chat-123",
                "messageId": "msg-456",
                "type": "down",
            },
        )

        async with client:
            vote = await client.downvote("chat-123", "msg-456")

        assert vote.type == "down"


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_authentication_error(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            status_code=401,
            json={
                "code": "unauthorized:chat",
                "message": "Invalid token",
            },
        )

        async with client:
            with pytest.raises(KaiAuthenticationError) as exc_info:
                await client.get_chat("chat-123")

        assert exc_info.value.code == "unauthorized:chat"
        assert "Invalid token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_forbidden_error(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            status_code=403,
            json={
                "code": "forbidden:chat",
                "message": "Access denied",
            },
        )

        async with client:
            with pytest.raises(KaiForbiddenError):
                await client.get_chat("chat-123")

    @pytest.mark.asyncio
    async def test_not_found_error(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            status_code=404,
            json={
                "code": "not_found:chat",
                "message": "Chat not found",
            },
        )

        async with client:
            with pytest.raises(KaiNotFoundError):
                await client.get_chat("chat-123")

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            status_code=429,
            json={
                "code": "rate_limit:chat",
                "message": "Too many requests",
            },
        )

        async with client:
            with pytest.raises(KaiRateLimitError):
                await client.get_chat("chat-123")

    @pytest.mark.asyncio
    async def test_bad_request_error(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            status_code=400,
            json={
                "code": "bad_request:api",
                "message": "Invalid request",
            },
        )

        async with client:
            with pytest.raises(KaiBadRequestError):
                await client.get_chat("chat-123")

    @pytest.mark.asyncio
    async def test_generic_error(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            status_code=500,
            json={
                "code": "internal_error",
                "message": "Server error",
            },
        )

        async with client:
            with pytest.raises(KaiError):
                await client.get_chat("chat-123")

    @pytest.mark.asyncio
    async def test_error_with_cause(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            status_code=400,
            json={
                "code": "bad_request:api",
                "message": "Validation failed",
                "cause": "Missing required field: message",
            },
        )

        async with client:
            with pytest.raises(KaiBadRequestError) as exc_info:
                await client.get_chat("chat-123")

        assert exc_info.value.cause == "Missing required field: message"


class TestContextManager:
    """Tests for async context manager functionality."""

    @pytest.mark.asyncio
    async def test_context_manager(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/ping",
            json={"timestamp": "2025-12-24T16:24:10.641Z"},
        )

        client = KaiClient(
            storage_api_token="token",
            storage_api_url="https://connection.keboola.com",
        )

        async with client:
            await client.ping()

        # Client should be closed after context
        assert client._client is None

    @pytest.mark.asyncio
    async def test_manual_close(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/ping",
            json={"timestamp": "2025-12-24T16:24:10.641Z"},
        )

        client = KaiClient(
            storage_api_token="token",
            storage_api_url="https://connection.keboola.com",
        )

        async with client:
            await client.ping()
            await client.close()

        assert client._client is None


class TestSendMessage:
    """Tests for send_message endpoint."""

    @pytest.mark.asyncio
    async def test_send_message_request_format(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test that send_message sends correctly formatted request."""
        sse_response = (
            'data: {"type":"text","text":"Hello"}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            events = []
            async for event in client.send_message("chat-123", "Hi there"):
                events.append(event)

        # Verify request format
        request = httpx_mock.get_request()
        body = json.loads(request.content)

        assert body["id"] == "chat-123"
        assert body["message"]["role"] == "user"
        assert body["message"]["parts"][0]["type"] == "text"
        assert body["message"]["parts"][0]["text"] == "Hi there"
        assert body["selectedChatModel"] == "chat-model"
        assert body["selectedVisibilityType"] == "private"

    @pytest.mark.asyncio
    async def test_send_message_streams_events(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test that events are properly streamed."""
        sse_response = (
            'data: {"type":"step-start"}\n'
            'data: {"type":"text","text":"Hello "}\n'
            'data: {"type":"text","text":"world!"}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            events = []
            async for event in client.send_message("chat-123", "Test"):
                events.append(event)

        assert len(events) == 4
        assert events[0].type == "step-start"
        assert events[1].type == "text"
        assert events[1].text == "Hello "
        assert events[2].text == "world!"
        assert events[3].type == "finish"


class TestChat:
    """Tests for the convenience chat method."""

    @pytest.mark.asyncio
    async def test_chat_returns_full_response(self, client: KaiClient, httpx_mock: HTTPXMock):
        sse_response = (
            'data: {"type":"text","text":"The answer "}\n'
            'data: {"type":"text","text":"is 42."}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            chat_id, response = await client.chat("What is the answer?")

        assert response == "The answer is 42."
        # Chat ID should be a valid UUID
        uuid.UUID(chat_id)

    @pytest.mark.asyncio
    async def test_chat_with_existing_id(self, client: KaiClient, httpx_mock: HTTPXMock):
        sse_response = 'data: {"type":"finish","finishReason":"stop"}\n'

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            chat_id, _ = await client.chat("Test", chat_id="existing-chat-id")

        assert chat_id == "existing-chat-id"

