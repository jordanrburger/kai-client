"""Custom exception classes for the Kai client library."""

from typing import Any, Optional


class KaiError(Exception):
    """Base exception for all Kai client errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        cause: Optional[str] = None,
        response_data: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.cause = cause
        self.response_data = response_data

    def __str__(self) -> str:
        parts = [self.message]
        if self.code:
            parts.insert(0, f"[{self.code}]")
        if self.cause:
            parts.append(f"(cause: {self.cause})")
        return " ".join(parts)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, code={self.code!r})"


class KaiAuthenticationError(KaiError):
    """Raised when authentication fails (unauthorized:chat)."""

    pass


class KaiForbiddenError(KaiError):
    """Raised when access is forbidden (forbidden:chat)."""

    pass


class KaiNotFoundError(KaiError):
    """Raised when a resource is not found (not_found:chat)."""

    pass


class KaiRateLimitError(KaiError):
    """Raised when rate limit is exceeded (rate_limit:chat)."""

    pass


class KaiBadRequestError(KaiError):
    """Raised when the request is malformed (bad_request:api)."""

    pass


class KaiStreamError(KaiError):
    """Raised when there's an error during SSE streaming."""

    pass


class KaiConnectionError(KaiError):
    """Raised when connection to the server fails."""

    pass


class KaiTimeoutError(KaiError):
    """Raised when a request times out."""

    pass


# Mapping of API error codes to exception classes
ERROR_CODE_MAP: dict[str, type[KaiError]] = {
    "unauthorized:chat": KaiAuthenticationError,
    "forbidden:chat": KaiForbiddenError,
    "not_found:chat": KaiNotFoundError,
    "rate_limit:chat": KaiRateLimitError,
    "bad_request:api": KaiBadRequestError,
}


def raise_for_error_response(response_data: dict[str, Any]) -> None:
    """
    Raise the appropriate exception based on the error response.

    Args:
        response_data: The error response from the API.

    Raises:
        KaiError: The appropriate exception subclass based on the error code.
    """
    code = response_data.get("code", "")
    message = response_data.get("message", "Unknown error")
    cause = response_data.get("cause")

    # Try exact match first
    exception_class = ERROR_CODE_MAP.get(code)

    # Try prefix match if no exact match
    if exception_class is None:
        for prefix, exc_class in ERROR_CODE_MAP.items():
            if code.startswith(prefix.split(":")[0]):
                exception_class = exc_class
                break

    # Default to base KaiError
    if exception_class is None:
        exception_class = KaiError

    raise exception_class(
        message=message,
        code=code,
        cause=cause,
        response_data=response_data,
    )


