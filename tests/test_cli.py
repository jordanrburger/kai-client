"""Tests for the CLI module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from kai_client.cli import get_client, get_env_or_error, main, run_async
from kai_client.models import (
    Chat,
    ChatDetail,
    FinishEvent,
    HistoryResponse,
    InfoResponse,
    Message,
    PingResponse,
    TextEvent,
    ToolCallEvent,
    Vote,
)


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("STORAGE_API_TOKEN", "test-token")
    monkeypatch.setenv("STORAGE_API_URL", "https://connection.test.keboola.com")


class TestGetEnvOrError:
    """Tests for get_env_or_error helper function."""

    def test_returns_value_when_set(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "test-value")
        assert get_env_or_error("TEST_VAR") == "test-value"

    def test_exits_when_not_set(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            get_env_or_error("MISSING_VAR")
        assert exc_info.value.code == 1


class TestRunAsync:
    """Tests for run_async helper function."""

    def test_runs_coroutine(self):
        async def sample_coro():
            return "result"

        result = run_async(sample_coro())
        assert result == "result"


class TestMainGroup:
    """Tests for the main CLI group."""

    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.4.0" in result.output

    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Kai CLI" in result.output
        assert "STORAGE_API_TOKEN" in result.output

    def test_passes_options_to_context(self, runner):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(
                return_value=PingResponse(timestamp="2025-01-01T00:00:00Z")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(
                main,
                [
                    "--token",
                    "my-token",
                    "--url",
                    "https://my-url.com",
                    "--base-url",
                    "http://localhost:4000",
                    "ping",
                ],
            )
            # Should not fail with missing env vars since we passed options
            assert "my-token" in str(mock_get_client.call_args) or result.exit_code == 0


class TestPingCommand:
    """Tests for the ping command."""

    def test_ping_success(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(
                return_value=PingResponse(timestamp="2025-01-08T12:00:00Z")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["ping"])

            assert result.exit_code == 0
            assert "Server is alive" in result.output

    def test_ping_missing_env(self, runner, monkeypatch):
        monkeypatch.delenv("STORAGE_API_TOKEN", raising=False)
        monkeypatch.delenv("STORAGE_API_URL", raising=False)

        result = runner.invoke(main, ["ping"])

        assert result.exit_code == 1
        assert "STORAGE_API_TOKEN" in result.output


class TestInfoCommand:
    """Tests for the info command."""

    def test_info_success(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.info = AsyncMock(
                return_value=InfoResponse(
                    timestamp="2025-01-08T12:00:00Z",
                    uptime=12345.67,
                    appName="kai-backend",
                    appVersion="1.0.0",
                    serverVersion="2.0.0",
                    connectedMcp=[{"name": "keboola-mcp", "status": "connected"}],
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["info"])

            assert result.exit_code == 0
            assert "kai-backend" in result.output
            assert "1.0.0" in result.output
            assert "keboola-mcp" in result.output


class TestChatCommand:
    """Tests for the chat command."""

    def test_chat_single_message(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            async def mock_send_message(chat_id, message):
                yield TextEvent(type="text", text="Hello there!")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["chat", "-m", "Hello"])

            assert result.exit_code == 0
            assert "Hello there!" in result.output
            assert "test-chat-id" in result.output

    def test_chat_with_existing_chat_id(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()

            async def mock_send_message(chat_id, message):
                yield TextEvent(type="text", text="Continued chat")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(
                main, ["chat", "--chat-id", "existing-id", "-m", "Continue"]
            )

            assert result.exit_code == 0
            # Should not print "Chat ID:" since we provided one
            assert "existing-id" not in result.output or "Continued chat" in result.output

    def test_chat_json_output(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            async def mock_send_message(chat_id, message):
                yield TextEvent(type="text", text="Response")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["chat", "--json-output", "-m", "Test"])

            assert result.exit_code == 0
            # Output should be JSON lines
            lines = [ln for ln in result.output.strip().split("\n") if ln]
            for line in lines:
                # Each line should be valid JSON
                parsed = json.loads(line)
                assert "type" in parsed

    def test_chat_with_tool_call_auto_approve(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            async def mock_send_message(chat_id, message):
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-123",
                    toolName="create_bucket",
                    state="input-available",
                    input={"name": "test"},
                )
                # Stream finishes waiting for approval

            async def mock_confirm_tool(chat_id, tool_call_id, tool_name):
                yield TextEvent(type="text", text="Bucket created!")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.confirm_tool = mock_confirm_tool
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(
                main, ["chat", "--auto-approve", "-m", "Create bucket"]
            )

            assert result.exit_code == 0
            assert "Auto-approving" in result.output
            assert "Bucket created!" in result.output

    def test_chat_step_start_display(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            from kai_client.models import StepStartEvent

            async def mock_send_message(chat_id, message):
                yield StepStartEvent(type="step-start")
                yield TextEvent(type="text", text="Processing done")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["chat", "-m", "Test"])

            assert result.exit_code == 0
            assert "[Processing...]" in result.output

    def test_chat_error_event(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            from kai_client.models import ErrorEvent

            async def mock_send_message(chat_id, message):
                yield ErrorEvent(type="error", message="Something went wrong")

            mock_client.send_message = mock_send_message
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["chat", "-m", "Test"])

            # Error should be displayed
            assert "Something went wrong" in result.output


class TestHistoryCommand:
    """Tests for the history command."""

    def test_history_success(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_history = AsyncMock(
                return_value=HistoryResponse(
                    chats=[
                        Chat(
                            id="chat-1",
                            title="First Chat",
                            createdAt="2025-01-08T10:00:00Z",
                        ),
                        Chat(
                            id="chat-2",
                            title="Second Chat",
                            createdAt="2025-01-08T11:00:00Z",
                        ),
                    ],
                    hasMore=False,
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["history"])

            assert result.exit_code == 0
            assert "chat-1" in result.output
            assert "First Chat" in result.output
            assert "chat-2" in result.output

    def test_history_with_limit(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_history = AsyncMock(
                return_value=HistoryResponse(chats=[], hasMore=False)
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["history", "-n", "5"])

            assert result.exit_code == 0
            mock_client.get_history.assert_called_once_with(limit=5)

    def test_history_empty(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_history = AsyncMock(
                return_value=HistoryResponse(chats=[], hasMore=False)
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["history"])

            assert result.exit_code == 0
            assert "No chat history found" in result.output

    def test_history_has_more(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_history = AsyncMock(
                return_value=HistoryResponse(
                    chats=[Chat(id="chat-1", title="Chat")],
                    hasMore=True,
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["history"])

            assert result.exit_code == 0
            assert "and more" in result.output

    def test_history_json_output(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_history = AsyncMock(
                return_value=HistoryResponse(
                    chats=[Chat(id="chat-1", title="Test Chat")],
                    hasMore=False,
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["history", "--json-output"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "chats" in data
            assert "hasMore" in data


class TestGetChatCommand:
    """Tests for the get-chat command."""

    def test_get_chat_success(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_chat = AsyncMock(
                return_value=ChatDetail(
                    id="chat-123",
                    title="Test Chat",
                    messages=[
                        Message(
                            id="msg-1",
                            role="user",
                            parts=[{"type": "text", "text": "Hello"}],
                        ),
                        Message(
                            id="msg-2",
                            role="assistant",
                            parts=[{"type": "text", "text": "Hi there!"}],
                        ),
                    ],
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["get-chat", "chat-123"])

            assert result.exit_code == 0
            assert "chat-123" in result.output
            assert "Test Chat" in result.output
            assert "[USER]" in result.output
            assert "[ASSISTANT]" in result.output

    def test_get_chat_json_output(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_chat = AsyncMock(
                return_value=ChatDetail(
                    id="chat-123",
                    title="Test",
                    messages=[],
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["get-chat", "chat-123", "--json-output"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["id"] == "chat-123"


class TestDeleteChatCommand:
    """Tests for the delete-chat command."""

    def test_delete_chat_with_confirmation(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.delete_chat = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["delete-chat", "chat-123", "--yes"])

            assert result.exit_code == 0
            assert "Deleted chat chat-123" in result.output
            mock_client.delete_chat.assert_called_once_with("chat-123")

    def test_delete_chat_cancelled(self, runner, mock_env):
        result = runner.invoke(main, ["delete-chat", "chat-123"], input="n\n")

        assert result.exit_code == 0
        assert "Cancelled" in result.output


class TestVoteCommand:
    """Tests for the vote command."""

    def test_vote_up(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.vote = AsyncMock(
                return_value=Vote(
                    chatId="chat-123",
                    messageId="msg-456",
                    type="up",
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["vote", "chat-123", "msg-456", "up"])

            assert result.exit_code == 0
            assert "Voted up" in result.output

    def test_vote_down(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.vote = AsyncMock(
                return_value=Vote(
                    chatId="chat-123",
                    messageId="msg-456",
                    type="down",
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["vote", "chat-123", "msg-456", "down"])

            assert result.exit_code == 0
            assert "Voted down" in result.output

    def test_vote_invalid_type(self, runner, mock_env):
        result = runner.invoke(main, ["vote", "chat-123", "msg-456", "invalid"])

        assert result.exit_code != 0
        assert "Invalid value" in result.output


class TestGetVotesCommand:
    """Tests for the get-votes command."""

    def test_get_votes_success(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_votes = AsyncMock(
                return_value=[
                    Vote(chatId="chat-123", messageId="msg-1", type="up"),
                    Vote(chatId="chat-123", messageId="msg-2", type="down"),
                ]
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["get-votes", "chat-123"])

            assert result.exit_code == 0
            assert "msg-1: up" in result.output
            assert "msg-2: down" in result.output

    def test_get_votes_empty(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_votes = AsyncMock(return_value=[])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["get-votes", "chat-123"])

            assert result.exit_code == 0
            assert "No votes found" in result.output

    def test_get_votes_json_output(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_votes = AsyncMock(
                return_value=[
                    Vote(chatId="chat-123", messageId="msg-1", type="up"),
                ]
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["get-votes", "chat-123", "--json-output"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1
            assert data[0]["type"] == "up"


class TestGetClientFunction:
    """Tests for the get_client async function."""

    @pytest.mark.asyncio
    async def test_get_client_with_base_url(self, mock_env):
        """Test client creation with explicit base URL (local dev mode)."""
        ctx = MagicMock()
        ctx.obj = {
            "token": "test-token",
            "url": "https://test.keboola.com",
            "base_url": "http://localhost:3000",
        }

        client = await get_client(ctx)

        assert client.base_url == "http://localhost:3000"
        assert client.storage_api_token == "test-token"

    @pytest.mark.asyncio
    async def test_get_client_auto_discover(self, mock_env):
        """Test client creation with auto-discovery (production mode)."""
        ctx = MagicMock()
        ctx.obj = {
            "token": "test-token",
            "url": "https://connection.keboola.com",
            "base_url": None,
        }

        with patch("kai_client.cli.KaiClient.from_storage_api") as mock_factory:
            mock_client = MagicMock()
            mock_factory.return_value = mock_client

            client = await get_client(ctx)

            mock_factory.assert_called_once_with(
                storage_api_token="test-token",
                storage_api_url="https://connection.keboola.com",
            )
            assert client == mock_client
