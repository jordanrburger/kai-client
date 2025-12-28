"""Type aliases and enums for the Kai client library."""

from enum import Enum
from typing import Union


class VisibilityType(str, Enum):
    """Chat visibility types."""

    PRIVATE = "private"
    PUBLIC = "public"


class VoteType(str, Enum):
    """Vote types for messages."""

    UP = "up"
    DOWN = "down"


class JobStatus(str, Enum):
    """Job processing status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MessageRole(str, Enum):
    """Message sender role."""

    USER = "user"
    ASSISTANT = "assistant"


class SSEEventType(str, Enum):
    """Server-Sent Event types."""

    TEXT = "text"
    STEP_START = "step-start"
    TOOL_CALL = "tool-call"
    TOOL_RESULT = "tool-result"
    FINISH = "finish"
    ERROR = "error"


class FinishReason(str, Enum):
    """Reasons for stream completion."""

    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    ERROR = "error"


class ToolCallState(str, Enum):
    """State of a tool call."""

    INPUT_AVAILABLE = "input-available"
    OUTPUT_AVAILABLE = "output-available"
    STREAMING = "streaming"
    DONE = "done"


# Type aliases for common patterns
ChatId = str
MessageId = str
ToolCallId = str

# Union types for discriminated unions
PartType = Union["TextPart", "ToolResultPart", "ToolCallPart", "StepStartPart"]

# Forward references for circular imports
if False:  # TYPE_CHECKING alternative that works at runtime
    from kai_client.models import StepStartPart, TextPart, ToolCallPart, ToolResultPart


