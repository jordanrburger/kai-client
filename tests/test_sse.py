"""Tests for SSE stream parser."""


from kai_client.models import (
    ErrorEvent,
    FinishEvent,
    StepStartEvent,
    TextEvent,
    ToolCallEvent,
    UnknownEvent,
)
from kai_client.sse import SSEStreamParser, parse_sse_event


class TestParseSSEEvent:
    """Tests for parse_sse_event function."""

    def test_parse_text_event(self):
        data = {"type": "text", "text": "Hello, world!"}
        event = parse_sse_event(data)
        assert isinstance(event, TextEvent)
        assert event.text == "Hello, world!"
        assert event.state is None

    def test_parse_text_event_with_state(self):
        data = {"type": "text", "text": "Done", "state": "done"}
        event = parse_sse_event(data)
        assert isinstance(event, TextEvent)
        assert event.state == "done"

    def test_parse_step_start_event(self):
        data = {"type": "step-start"}
        event = parse_sse_event(data)
        assert isinstance(event, StepStartEvent)
        assert event.type == "step-start"

    def test_parse_tool_call_input_available(self):
        data = {
            "type": "tool-call",
            "toolCallId": "call-123",
            "toolName": "get_tables",
            "state": "input-available",
            "input": {"bucket_id": "in.c-main"},
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.tool_call_id == "call-123"
        assert event.tool_name == "get_tables"
        assert event.state == "input-available"
        assert event.input == {"bucket_id": "in.c-main"}
        assert event.output is None

    def test_parse_tool_call_output_available(self):
        data = {
            "type": "tool-call",
            "toolCallId": "call-123",
            "toolName": "get_tables",
            "state": "output-available",
            "output": {"tables": ["table1", "table2"]},
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.state == "output-available"
        assert event.output == {"tables": ["table1", "table2"]}

    def test_parse_finish_event_stop(self):
        data = {"type": "finish", "finishReason": "stop"}
        event = parse_sse_event(data)
        assert isinstance(event, FinishEvent)
        assert event.finish_reason == "stop"

    def test_parse_finish_event_length(self):
        data = {"type": "finish", "finishReason": "length"}
        event = parse_sse_event(data)
        assert isinstance(event, FinishEvent)
        assert event.finish_reason == "length"

    def test_parse_error_event(self):
        data = {
            "type": "error",
            "message": "Something went wrong",
            "code": "internal_error",
        }
        event = parse_sse_event(data)
        assert isinstance(event, ErrorEvent)
        assert event.message == "Something went wrong"
        assert event.code == "internal_error"

    def test_parse_error_event_without_code(self):
        data = {"type": "error", "message": "Error occurred"}
        event = parse_sse_event(data)
        assert isinstance(event, ErrorEvent)
        assert event.code is None

    def test_parse_unknown_event(self):
        data = {"type": "custom-event", "foo": "bar", "count": 42}
        event = parse_sse_event(data)
        assert isinstance(event, UnknownEvent)
        assert event.type == "custom-event"
        assert event.data == data

    def test_parse_empty_type(self):
        data = {"foo": "bar"}
        event = parse_sse_event(data)
        assert isinstance(event, UnknownEvent)
        assert event.type == ""


class TestProductionSSEFormats:
    """Tests for production SSE event formats."""

    def test_parse_text_delta_event(self):
        """Test parsing production text-delta event."""
        data = {"type": "text-delta", "delta": "Hello from production!"}
        event = parse_sse_event(data)
        assert isinstance(event, TextEvent)
        assert event.type == "text"
        assert event.text == "Hello from production!"

    def test_parse_text_delta_with_state(self):
        """Test parsing production text-delta event with state."""
        data = {"type": "text-delta", "delta": "Done", "state": "done"}
        event = parse_sse_event(data)
        assert isinstance(event, TextEvent)
        assert event.text == "Done"
        assert event.state == "done"

    def test_parse_start_step_event(self):
        """Test parsing production start-step event (alternate name)."""
        data = {"type": "start-step"}
        event = parse_sse_event(data)
        assert isinstance(event, StepStartEvent)
        assert event.type == "step-start"

    def test_parse_tool_input_start_event(self):
        """Test parsing production tool-input-start event."""
        data = {
            "type": "tool-input-start",
            "toolCallId": "call-123",
            "toolName": "create_bucket",
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.type == "tool-call"
        assert event.tool_call_id == "call-123"
        assert event.tool_name == "create_bucket"
        assert event.state == "started"
        assert event.input is None
        assert event.output is None

    def test_parse_tool_input_available_event(self):
        """Test parsing production tool-input-available event."""
        data = {
            "type": "tool-input-available",
            "toolCallId": "call-123",
            "toolName": "create_bucket",
            "input": {"name": "test-bucket", "stage": "in"},
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.type == "tool-call"
        assert event.tool_call_id == "call-123"
        assert event.state == "input-available"
        assert event.input == {"name": "test-bucket", "stage": "in"}
        assert event.output is None

    def test_parse_tool_output_available_event(self):
        """Test parsing production tool-output-available event."""
        data = {
            "type": "tool-output-available",
            "toolCallId": "call-123",
            "toolName": "create_bucket",
            "output": {"success": True, "bucket_id": "in.c-test"},
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.type == "tool-call"
        assert event.tool_call_id == "call-123"
        assert event.state == "output-available"
        assert event.output == {"success": True, "bucket_id": "in.c-test"}
        assert event.input is None

    def test_parse_finish_step_event(self):
        """Test parsing production finish-step event."""
        data = {"type": "finish-step", "finishReason": "stop"}
        event = parse_sse_event(data)
        assert isinstance(event, FinishEvent)
        assert event.type == "finish"
        assert event.finish_reason == "stop"

    def test_parse_finish_event_default_reason(self):
        """Test parsing finish event with missing finishReason."""
        data = {"type": "finish"}
        event = parse_sse_event(data)
        assert isinstance(event, FinishEvent)
        assert event.finish_reason == "stop"  # Default

    def test_production_unknown_events_passthrough(self):
        """Test that production-specific events we don't handle are returned as unknown."""
        # These are intentionally not handled but shouldn't cause errors
        for event_type in ["start", "text-start", "text-end", "step-end"]:
            data = {"type": event_type, "id": "some-id"}
            event = parse_sse_event(data)
            assert isinstance(event, UnknownEvent)
            assert event.type == event_type


class TestSSEStreamParser:
    """Tests for SSEStreamParser class."""

    def test_initial_state(self):
        parser = SSEStreamParser()
        assert parser.text == ""
        assert parser.tool_calls == {}
        assert parser.finished is False
        assert parser.finish_reason is None

    def test_accumulate_text(self):
        parser = SSEStreamParser()

        parser.process_event(TextEvent(type="text", text="Hello"))
        assert parser.text == "Hello"

        parser.process_event(TextEvent(type="text", text=" world"))
        assert parser.text == "Hello world"

        parser.process_event(TextEvent(type="text", text="!"))
        assert parser.text == "Hello world!"

    def test_track_tool_calls(self):
        parser = SSEStreamParser()

        # Tool call starts
        event1 = ToolCallEvent(
            type="tool-call",
            toolCallId="call-1",
            toolName="get_tables",
            state="input-available",
            input={"bucket": "test"},
        )
        parser.process_event(event1)

        assert "call-1" in parser.tool_calls
        assert parser.tool_calls["call-1"].state == "input-available"

        # Tool call completes
        event2 = ToolCallEvent(
            type="tool-call",
            toolCallId="call-1",
            toolName="get_tables",
            state="output-available",
            output={"result": "success"},
        )
        parser.process_event(event2)

        assert parser.tool_calls["call-1"].state == "output-available"
        assert parser.tool_calls["call-1"].output == {"result": "success"}

    def test_multiple_tool_calls(self):
        parser = SSEStreamParser()

        parser.process_event(ToolCallEvent(
            type="tool-call",
            toolCallId="call-1",
            toolName="tool_a",
            state="done",
        ))
        parser.process_event(ToolCallEvent(
            type="tool-call",
            toolCallId="call-2",
            toolName="tool_b",
            state="done",
        ))

        assert len(parser.tool_calls) == 2
        assert "call-1" in parser.tool_calls
        assert "call-2" in parser.tool_calls

    def test_finish_event(self):
        parser = SSEStreamParser()

        assert parser.finished is False
        assert parser.finish_reason is None

        parser.process_event(FinishEvent(type="finish", finishReason="stop"))

        assert parser.finished is True
        assert parser.finish_reason == "stop"

    def test_reset(self):
        parser = SSEStreamParser()

        # Add some data
        parser.process_event(TextEvent(type="text", text="Hello"))
        parser.process_event(ToolCallEvent(
            type="tool-call",
            toolCallId="call-1",
            toolName="test",
            state="done",
        ))
        parser.process_event(FinishEvent(type="finish", finishReason="stop"))

        # Verify data was added
        assert parser.text == "Hello"
        assert len(parser.tool_calls) == 1
        assert parser.finished is True

        # Reset
        parser.reset()

        # Verify reset worked
        assert parser.text == ""
        assert parser.tool_calls == {}
        assert parser.finished is False
        assert parser.finish_reason is None

    def test_tool_calls_returns_copy(self):
        parser = SSEStreamParser()

        parser.process_event(ToolCallEvent(
            type="tool-call",
            toolCallId="call-1",
            toolName="test",
            state="done",
        ))

        # Get tool calls and modify the returned dict
        calls = parser.tool_calls
        calls["call-2"] = None  # type: ignore

        # Original should be unchanged
        assert len(parser.tool_calls) == 1
        assert "call-2" not in parser.tool_calls

    def test_ignores_other_events(self):
        parser = SSEStreamParser()

        # These should not raise errors
        parser.process_event(StepStartEvent(type="step-start"))
        parser.process_event(ErrorEvent(type="error", message="test"))
        parser.process_event(UnknownEvent(type="custom", data={}))

        # State should be unchanged
        assert parser.text == ""
        assert parser.tool_calls == {}
        assert parser.finished is False

    def test_complex_conversation(self):
        """Test a realistic conversation flow."""
        parser = SSEStreamParser()

        # Simulated stream of events
        events = [
            StepStartEvent(type="step-start"),
            TextEvent(type="text", text="Let me check "),
            TextEvent(type="text", text="the tables."),
            ToolCallEvent(
                type="tool-call",
                toolCallId="call-1",
                toolName="list_tables",
                state="input-available",
                input={},
            ),
            ToolCallEvent(
                type="tool-call",
                toolCallId="call-1",
                toolName="list_tables",
                state="output-available",
                output={"tables": ["users", "orders"]},
            ),
            TextEvent(type="text", text="\n\nI found 2 tables: "),
            TextEvent(type="text", text="users and orders."),
            FinishEvent(type="finish", finishReason="stop"),
        ]

        for event in events:
            parser.process_event(event)

        assert parser.text == "Let me check the tables.\n\nI found 2 tables: users and orders."
        assert len(parser.tool_calls) == 1
        assert parser.tool_calls["call-1"].output == {"tables": ["users", "orders"]}
        assert parser.finished is True
        assert parser.finish_reason == "stop"


