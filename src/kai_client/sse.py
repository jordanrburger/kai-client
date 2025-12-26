"""Server-Sent Events (SSE) stream parser for the Kai client."""

import json
from typing import Any, AsyncIterator

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

    # Text events - handle both local ("text") and production ("text-delta") formats
    if event_type == "text":
        return TextEvent(
            type="text",
            text=data.get("text", ""),
            state=data.get("state"),
        )

    if event_type == "text-delta":
        # Production format: uses "delta" instead of "text"
        return TextEvent(
            type="text",
            text=data.get("delta", ""),
            state=data.get("state"),
        )

    # Step start - handle both "step-start" (local) and "start-step" (production)
    if event_type in ("step-start", "start-step"):
        return StepStartEvent(type="step-start")

    # Tool call events - handle both local and production formats
    if event_type == "tool-call":
        return ToolCallEvent(
            type="tool-call",
            toolCallId=data.get("toolCallId", ""),
            toolName=data.get("toolName"),
            state=data.get("state", ""),
            input=data.get("input"),
            output=data.get("output"),
        )

    # Production format: tool-input-start (tool call begins)
    if event_type == "tool-input-start":
        return ToolCallEvent(
            type="tool-call",
            toolCallId=data.get("toolCallId", ""),
            toolName=data.get("toolName"),
            state="started",
            input=None,
            output=None,
        )

    # Production format: tool-input-available (full input ready)
    if event_type == "tool-input-available":
        return ToolCallEvent(
            type="tool-call",
            toolCallId=data.get("toolCallId", ""),
            toolName=data.get("toolName"),
            state="input-available",
            input=data.get("input"),
            output=None,
        )

    # Production format: tool-output-available (tool completed)
    if event_type == "tool-output-available":
        return ToolCallEvent(
            type="tool-call",
            toolCallId=data.get("toolCallId", ""),
            toolName=data.get("toolName"),
            state="output-available",
            input=None,
            output=data.get("output"),
        )

    # Finish events - handle both "finish" and "finish-step"
    if event_type in ("finish", "finish-step"):
        return FinishEvent(
            type="finish",
            finishReason=data.get("finishReason", "stop"),
        )

    if event_type == "error":
        return ErrorEvent(
            type="error",
            message=data.get("message", "Unknown error"),
            code=data.get("code"),
        )

    # Production-specific events that we can safely ignore or return as unknown
    # - "start": message start (contains messageId)
    # - "text-start": text block start (contains id)
    # - "text-end": text block end
    # - "step-end": step end

    # Unknown event type - return with raw data
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


