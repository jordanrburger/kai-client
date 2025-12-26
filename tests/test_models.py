"""Tests for Pydantic models."""

from datetime import datetime

from kai_client.models import (
    Chat,
    ChatDetail,
    ChatRequest,
    ErrorEvent,
    ErrorResponse,
    FinishEvent,
    HistoryResponse,
    InfoResponse,
    MessageMetadata,
    MessageRequest,
    PingResponse,
    RequestContext,
    StepStartEvent,
    TextEvent,
    TextPart,
    ToolCallEvent,
    ToolCallPart,
    ToolResultPart,
    Vote,
    VoteRequest,
)


class TestTextPart:
    """Tests for TextPart model."""

    def test_basic_creation(self):
        part = TextPart(type="text", text="Hello, world!")
        assert part.type == "text"
        assert part.text == "Hello, world!"
        assert part.state is None

    def test_with_state(self):
        part = TextPart(type="text", text="Done", state="done")
        assert part.state == "done"

    def test_serialization(self):
        part = TextPart(type="text", text="Test")
        data = part.model_dump()
        assert data["type"] == "text"
        assert data["text"] == "Test"


class TestToolResultPart:
    """Tests for ToolResultPart model."""

    def test_basic_creation(self):
        part = ToolResultPart(
            type="tool-result",
            toolCallId="call-123",
            toolName="get_tables",
            result={"tables": ["table1", "table2"]},
        )
        assert part.type == "tool-result"
        assert part.tool_call_id == "call-123"
        assert part.tool_name == "get_tables"
        assert part.result == {"tables": ["table1", "table2"]}

    def test_serialization_with_alias(self):
        part = ToolResultPart(
            type="tool-result",
            toolCallId="call-123",
            toolName="test_tool",
            result="success",
        )
        data = part.model_dump(by_alias=True)
        assert data["toolCallId"] == "call-123"
        assert data["toolName"] == "test_tool"


class TestToolCallPart:
    """Tests for ToolCallPart model."""

    def test_with_input(self):
        part = ToolCallPart(
            type="tool-get_tables",
            toolCallId="call-456",
            state="input-available",
            input={"bucket_id": "in.c-main"},
        )
        assert part.tool_call_id == "call-456"
        assert part.state == "input-available"
        assert part.input == {"bucket_id": "in.c-main"}
        assert part.output is None

    def test_with_output(self):
        part = ToolCallPart(
            type="tool-get_tables",
            toolCallId="call-456",
            state="output-available",
            output={"result": "success"},
        )
        assert part.state == "output-available"
        assert part.output == {"result": "success"}


class TestMessageRequest:
    """Tests for MessageRequest model."""

    def test_basic_creation(self):
        request = MessageRequest(
            id="msg-123",
            role="user",
            parts=[TextPart(type="text", text="Hello")],
        )
        assert request.id == "msg-123"
        assert request.role == "user"
        assert len(request.parts) == 1
        assert request.parts[0].text == "Hello"

    def test_with_metadata(self):
        request = MessageRequest(
            id="msg-123",
            role="user",
            parts=[TextPart(type="text", text="Test")],
            metadata=MessageMetadata(
                hidden=True,
                request_context=RequestContext(path="/test"),
            ),
        )
        assert request.metadata is not None
        assert request.metadata.hidden is True
        assert request.metadata.request_context.path == "/test"


class TestChatRequest:
    """Tests for ChatRequest model."""

    def test_basic_creation(self):
        request = ChatRequest(
            id="chat-123",
            message=MessageRequest(
                id="msg-456",
                role="user",
                parts=[TextPart(type="text", text="Hello")],
            ),
            selectedChatModel="chat-model",
            selectedVisibilityType="private",
        )
        assert request.id == "chat-123"
        assert request.selected_chat_model == "chat-model"
        assert request.selected_visibility_type == "private"
        assert request.branch_id is None

    def test_with_branch_id(self):
        request = ChatRequest(
            id="chat-123",
            message=MessageRequest(
                id="msg-456",
                role="user",
                parts=[TextPart(type="text", text="Test")],
            ),
            selectedChatModel="chat-model-reasoning",
            selectedVisibilityType="public",
            branchId=12345,
        )
        assert request.branch_id == 12345

    def test_serialization_with_aliases(self):
        request = ChatRequest(
            id="chat-123",
            message=MessageRequest(
                id="msg-456",
                role="user",
                parts=[TextPart(type="text", text="Test")],
            ),
            selectedChatModel="chat-model",
            selectedVisibilityType="private",
            branchId=999,
        )
        data = request.model_dump(by_alias=True)
        assert data["selectedChatModel"] == "chat-model"
        assert data["selectedVisibilityType"] == "private"
        assert data["branchId"] == 999


class TestPingResponse:
    """Tests for PingResponse model."""

    def test_parsing(self):
        response = PingResponse.model_validate(
            {"timestamp": "2025-12-24T16:24:10.641Z"}
        )
        assert isinstance(response.timestamp, datetime)


class TestInfoResponse:
    """Tests for InfoResponse model."""

    def test_parsing(self):
        data = {
            "timestamp": "2025-12-24T16:24:10.641Z",
            "uptime": 12345.67,
            "appName": "kai-backend",
            "appVersion": "1.0.0",
            "serverVersion": "2.0.0",
            "connectedMcp": [
                {"name": "keboola-mcp", "status": "connected"}
            ],
        }
        response = InfoResponse.model_validate(data)
        assert response.app_name == "kai-backend"
        assert response.app_version == "1.0.0"
        assert response.server_version == "2.0.0"
        assert len(response.connected_mcp) == 1
        # connected_mcp is typed as Any, so items are dicts
        assert response.connected_mcp[0]["name"] == "keboola-mcp"


class TestChatModels:
    """Tests for Chat and ChatDetail models."""

    def test_chat_basic(self):
        chat = Chat.model_validate({
            "id": "chat-123",
            "title": "Test Chat",
            "createdAt": "2025-12-24T10:00:00Z",
            "visibility": "private",
        })
        assert chat.id == "chat-123"
        assert chat.title == "Test Chat"
        assert chat.visibility == "private"

    def test_chat_detail_with_messages(self):
        data = {
            "id": "chat-123",
            "title": "Test Chat",
            "messages": [
                {
                    "id": "msg-1",
                    "role": "user",
                    "parts": [{"type": "text", "text": "Hello"}],
                },
                {
                    "id": "msg-2",
                    "role": "assistant",
                    "parts": [{"type": "text", "text": "Hi there!"}],
                },
            ],
        }
        detail = ChatDetail.model_validate(data)
        assert len(detail.messages) == 2
        assert detail.messages[0].role == "user"
        assert detail.messages[1].role == "assistant"


class TestHistoryResponse:
    """Tests for HistoryResponse model."""

    def test_parsing(self):
        data = {
            "chats": [
                {"id": "chat-1", "title": "Chat 1"},
                {"id": "chat-2", "title": "Chat 2"},
            ],
            "hasMore": True,
        }
        response = HistoryResponse.model_validate(data)
        assert len(response.chats) == 2
        assert response.has_more is True


class TestVoteModels:
    """Tests for Vote models."""

    def test_vote_request(self):
        request = VoteRequest(
            chatId="chat-123",
            messageId="msg-456",
            type="up",
        )
        assert request.chat_id == "chat-123"
        assert request.message_id == "msg-456"
        assert request.type == "up"

    def test_vote_response(self):
        vote = Vote.model_validate({
            "id": "vote-1",
            "chatId": "chat-123",
            "messageId": "msg-456",
            "type": "down",
        })
        assert vote.chat_id == "chat-123"
        assert vote.type == "down"


class TestSSEEventModels:
    """Tests for SSE event models."""

    def test_text_event(self):
        event = TextEvent(type="text", text="Hello", state="done")
        assert event.type == "text"
        assert event.text == "Hello"
        assert event.state == "done"

    def test_step_start_event(self):
        event = StepStartEvent(type="step-start")
        assert event.type == "step-start"

    def test_tool_call_event(self):
        event = ToolCallEvent(
            type="tool-call",
            toolCallId="call-123",
            toolName="get_tables",
            state="input-available",
            input={"bucket": "test"},
        )
        assert event.tool_call_id == "call-123"
        assert event.tool_name == "get_tables"
        assert event.state == "input-available"

    def test_finish_event(self):
        event = FinishEvent(type="finish", finishReason="stop")
        assert event.finish_reason == "stop"

    def test_error_event(self):
        event = ErrorEvent(
            type="error",
            message="Something went wrong",
            code="internal_error",
        )
        assert event.message == "Something went wrong"
        assert event.code == "internal_error"


class TestErrorResponse:
    """Tests for ErrorResponse model."""

    def test_basic_error(self):
        response = ErrorResponse.model_validate({
            "code": "unauthorized:chat",
            "message": "Invalid token",
        })
        assert response.code == "unauthorized:chat"
        assert response.message == "Invalid token"
        assert response.cause is None

    def test_error_with_cause(self):
        response = ErrorResponse.model_validate({
            "code": "bad_request:api",
            "message": "Validation failed",
            "cause": "Missing required field",
        })
        assert response.cause == "Missing required field"


