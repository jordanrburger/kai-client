"""Server-Sent Events (SSE) stream parser for the Kai client."""

import json
from typing import Any, AsyncIterator, Callable

import httpx

from kai_client.exceptions import KaiStreamError
from kai_client.models import (
    ErrorEvent,
    FinishEvent,
    SSEEvent,
    StepStartEvent,
    TextEvent,
    ToolCallEvent,
    UnknownEvent,
)


# =============================================================================
# Individual Event Parsers
# =============================================================================


def _parse_text_event(data: dict[str, Any]) -> TextEvent:
    """Parse a text event (local format)."""
    return TextEvent(
        type="text",
        text=data.get("text", ""),
        state=data.get("state"),
    )


def _parse_text_delta_event(data: dict[str, Any]) -> TextEvent:
    """Parse a text-delta event (production format)."""
    return TextEvent(
        type="text",
        text=data.get("delta", ""),
        state=data.get("state"),
    )


def _parse_step_start_event(data: dict[str, Any]) -> StepStartEvent:
    """Parse a step-start or start-step event."""
    return StepStartEvent(type="step-start")


def _parse_tool_call_event(data: dict[str, Any]) -> ToolCallEvent:
    """Parse a tool-call event (local format)."""
    return ToolCallEvent(
        type="tool-call",
        toolCallId=data.get("toolCallId", ""),
        toolName=data.get("toolName"),
        state=data.get("state", ""),
        input=data.get("input"),
        output=data.get("output"),
    )


def _parse_tool_input_start_event(data: dict[str, Any]) -> ToolCallEvent:
    """Parse a tool-input-start event (production format: tool call begins)."""
    return ToolCallEvent(
        type="tool-call",
        toolCallId=data.get("toolCallId", ""),
        toolName=data.get("toolName"),
        state="started",
        input=None,
        output=None,
    )


def _parse_tool_input_available_event(data: dict[str, Any]) -> ToolCallEvent:
    """Parse a tool-input-available event (production format: full input ready)."""
    return ToolCallEvent(
        type="tool-call",
        toolCallId=data.get("toolCallId", ""),
        toolName=data.get("toolName"),
        state="input-available",
        input=data.get("input"),
        output=None,
    )


def _parse_tool_output_available_event(data: dict[str, Any]) -> ToolCallEvent:
    """Parse a tool-output-available event (production format: tool completed)."""
    return ToolCallEvent(
        type="tool-call",
        toolCallId=data.get("toolCallId", ""),
        toolName=data.get("toolName"),
        state="output-available",
        input=None,
        output=data.get("output"),
    )


def _parse_finish_event(data: dict[str, Any]) -> FinishEvent:
    """Parse a finish or finish-step event."""
    return FinishEvent(
        type="finish",
        finishReason=data.get("finishReason", "stop"),
    )


def _parse_error_event(data: dict[str, Any]) -> ErrorEvent:
    """Parse an error event."""
    return ErrorEvent(
        type="error",
        message=data.get("message", "Unknown error"),
        code=data.get("code"),
    )


# =============================================================================
# Event Parser Dispatch Table
# =============================================================================

EVENT_PARSERS: dict[str, Callable[[dict[str, Any]], SSEEvent]] = {
    "text": _parse_text_event,
    "text-delta": _parse_text_delta_event,
    "step-start": _parse_step_start_event,
    "start-step": _parse_step_start_event,
    "tool-call": _parse_tool_call_event,
    "tool-input-start": _parse_tool_input_start_event,
    "tool-input-available": _parse_tool_input_available_event,
    "tool-output-available": _parse_tool_output_available_event,
    "finish": _parse_finish_event,
    "finish-step": _parse_finish_event,
    "error": _parse_error_event,
}


def parse_sse_event(data: dict[str, Any]) -> SSEEvent:
    """
    Parse a raw SSE event dictionary into a typed event model.

    Handles both local development format and production format:
    - Local: type="text" with "text" field
    - Production: type="text-delta" with "delta" field

    Args:
        data: The raw event data from the SSE stream.

    Returns:
        A typed SSE event model.
    """
    event_type = data.get("type", "")
    parser = EVENT_PARSERS.get(event_type)

    if parser:
        return parser(data)

    # Unknown event type - return with raw data
    # Production-specific events that we can safely ignore:
    # - "start": message start (contains messageId)
    # - "text-start": text block start (contains id)
    # - "text-end": text block end
    # - "step-end": step end
    return UnknownEvent(type=event_type, data=data)


async def parse_sse_stream(response: httpx.Response) -> AsyncIterator[SSEEvent]:
    """
    Parse an SSE stream from an httpx response.

    The SSE format consists of lines prefixed with "data: " followed by JSON.
    Empty lines and lines starting with ":" (comments) are ignored.

    Args:
        response: The httpx response object with streaming content.

    Yields:
        Parsed SSE events.

    Raises:
        KaiStreamError: If there's an error parsing the stream.
    """
    try:
        async for line in response.aiter_lines():
            # Skip empty lines and comments
            if not line or line.startswith(":"):
                continue

            # Parse data lines
            if line.startswith("data: "):
                try:
                    json_str = line[6:]  # Remove "data: " prefix
                    stripped = json_str.strip()
                    if not stripped:  # Skip empty data
                        continue
                    # Handle [DONE] termination marker (OpenAI-style)
                    if stripped == "[DONE]":
                        continue
                    data = json.loads(json_str)
                    yield parse_sse_event(data)
                except json.JSONDecodeError as e:
                    raise KaiStreamError(
                        message=f"Failed to parse SSE event: {e}",
                        cause=str(e),
                    ) from e

            # Handle other SSE fields (event:, id:, retry:) if needed
            elif line.startswith("event: "):
                # Event type hint - usually followed by data:
                pass
            elif line.startswith("id: "):
                # Event ID - can be used for resumption
                pass
            elif line.startswith("retry: "):
                # Retry interval hint
                pass

    except httpx.StreamClosed:
        # Stream ended normally
        pass
    except httpx.RemoteProtocolError as e:
        raise KaiStreamError(
            message="Connection error during streaming",
            cause=str(e),
        ) from e


class SSEStreamParser:
    """
    A stateful SSE stream parser that can accumulate text events.

    This class provides utilities for working with SSE streams,
    including accumulating text content and tracking tool calls.
    """

    def __init__(self) -> None:
        self._accumulated_text: list[str] = []
        self._tool_calls: dict[str, ToolCallEvent] = {}
        self._finished = False
        self._finish_reason: str | None = None

    @property
    def text(self) -> str:
        """Get all accumulated text content."""
        return "".join(self._accumulated_text)

    @property
    def tool_calls(self) -> dict[str, ToolCallEvent]:
        """Get all tool calls by their IDs."""
        return self._tool_calls.copy()

    @property
    def finished(self) -> bool:
        """Check if the stream has finished."""
        return self._finished

    @property
    def finish_reason(self) -> str | None:
        """Get the reason for stream completion."""
        return self._finish_reason

    def process_event(self, event: SSEEvent) -> None:
        """
        Process an SSE event and update internal state.

        Args:
            event: The SSE event to process.
        """
        if isinstance(event, TextEvent):
            self._accumulated_text.append(event.text)
        elif isinstance(event, ToolCallEvent):
            self._tool_calls[event.tool_call_id] = event
        elif isinstance(event, FinishEvent):
            self._finished = True
            self._finish_reason = event.finish_reason

    def reset(self) -> None:
        """Reset the parser state."""
        self._accumulated_text.clear()
        self._tool_calls.clear()
        self._finished = False
        self._finish_reason = None

    async def consume_stream(
        self,
        response: httpx.Response,
        yield_events: bool = True,
    ) -> AsyncIterator[SSEEvent]:
        """
        Consume an SSE stream, processing and optionally yielding events.

        Args:
            response: The httpx response to consume.
            yield_events: Whether to yield events as they are processed.

        Yields:
            SSE events if yield_events is True.
        """
        async for event in parse_sse_stream(response):
            self.process_event(event)
            if yield_events:
                yield event


