"""Main Kai client implementation."""

import uuid
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Any, AsyncIterator, Optional

import httpx

from kai_client.exceptions import (
    KaiConnectionError,
    KaiError,
    KaiTimeoutError,
    raise_for_error_response,
)
from kai_client.models import (
    Chat,
    ChatDetail,
    ChatRequest,
    HistoryResponse,
    InfoResponse,
    MessageMetadata,
    MessageRequest,
    PingResponse,
    RequestContext,
    SSEEvent,
    TextPart,
    ToolResultPart,
    Vote,
    VoteRequest,
)
from kai_client.sse import parse_sse_stream
from kai_client.types import VisibilityType, VoteType


class KaiClient:
    """
    Async client for the Keboola AI Assistant Backend API.

    This client provides methods for interacting with all API endpoints,
    including chat creation, message streaming, history management, and voting.

    Example:
        ```python
        # Local development
        async with KaiClient(
            storage_api_token="your-token",
            storage_api_url="https://connection.canary-orion.keboola.dev"
        ) as client:
            # Start a new chat
            chat_id = client.new_chat_id()

            # Send a message and stream the response
            async for event in client.send_message(chat_id, "Hello!"):
                if event.type == "text":
                    print(event.text, end="", flush=True)

        # Production (auto-discovers kai-assistant URL)
        client = await KaiClient.from_storage_api(
            storage_api_token="your-token",
            storage_api_url="https://connection.keboola.com"
        )
        async with client:
            chat_id, response = await client.chat("Hello!")
        ```
    """

    @classmethod
    async def from_storage_api(
        cls,
        storage_api_token: str,
        storage_api_url: str,
        timeout: float = 300.0,
        stream_timeout: float = 600.0,
    ) -> "KaiClient":
        """
        Auto-discover the kai-assistant URL from the Keboola Storage API.

        This factory method queries the Storage API to find the kai-assistant
        service URL for your stack, then creates a client configured for production.

        Args:
            storage_api_token: Keboola Storage API token for authentication.
            storage_api_url: Keboola Storage API URL (e.g., https://connection.keboola.com).
            timeout: Default timeout for non-streaming requests in seconds.
            stream_timeout: Timeout for streaming requests in seconds.

        Returns:
            A configured KaiClient instance.

        Raises:
            KaiError: If the kai-assistant service is not found or discovery fails.

        Example:
            ```python
            client = await KaiClient.from_storage_api(
                storage_api_token="your-token",
                storage_api_url="https://connection.us-east4.gcp.keboola.com"
            )
            ```
        """
        async with httpx.AsyncClient() as http_client:
            try:
                response = await http_client.get(
                    f"{storage_api_url.rstrip('/')}/v2/storage",
                    headers={"x-storageapi-token": storage_api_token},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as e:
                raise KaiError(
                    message=f"Failed to discover kai-assistant URL: HTTP {e.response.status_code}",
                    code="discovery:http_error",
                ) from e
            except httpx.RequestError as e:
                raise KaiConnectionError(
                    message=f"Failed to connect to Storage API: {storage_api_url}",
                    cause=str(e),
                ) from e

        services = data.get("services", [])
        kai_service = next(
            (s for s in services if s.get("id") == "kai-assistant"),
            None,
        )

        if not kai_service:
            available = [s.get("id") for s in services]
            raise KaiError(
                message=f"kai-assistant service not found. Available services: {available}",
                code="discovery:service_not_found",
            )

        kai_url = kai_service.get("url")
        if not kai_url:
            raise KaiError(
                message="kai-assistant service has no URL",
                code="discovery:no_url",
            )

        return cls(
            storage_api_token=storage_api_token,
            storage_api_url=storage_api_url,
            base_url=kai_url,
            timeout=timeout,
            stream_timeout=stream_timeout,
        )

    def __init__(
        self,
        storage_api_token: str,
        storage_api_url: str,
        base_url: str = "http://localhost:3000",
        timeout: float = 300.0,
        stream_timeout: float = 600.0,
    ) -> None:
        """
        Initialize the Kai client.

        Args:
            storage_api_token: Keboola Storage API token for authentication.
            storage_api_url: Keboola Storage API URL (e.g., https://connection.keboola.com).
            base_url: Base URL for the Kai API (default: http://localhost:3000).
            timeout: Default timeout for non-streaming requests in seconds.
            stream_timeout: Timeout for streaming requests in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.storage_api_token = storage_api_token
        self.storage_api_url = storage_api_url
        self.timeout = timeout
        self.stream_timeout = stream_timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers for API requests."""
        return {
            "x-storageapi-token": self.storage_api_token,
            "x-storageapi-url": self.storage_api_url,
        }

    def _get_client(self) -> httpx.AsyncClient:
        """Get the HTTP client, creating it if necessary."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def __aenter__(self) -> "KaiClient":
        """Enter the async context manager."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
        )
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Exit the async context manager and close the client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        auth: bool = True,
    ) -> httpx.Response:
        """
        Make an HTTP request.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            path: API endpoint path.
            json: JSON body for the request.
            params: Query parameters.
            auth: Whether to include authentication headers.

        Returns:
            The HTTP response.

        Raises:
            KaiError: If the request fails.
        """
        client = self._get_client()
        headers = self._get_auth_headers() if auth else {}

        try:
            response = await client.request(
                method=method,
                url=path,
                json=json,
                params=params,
                headers=headers,
            )

            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    raise_for_error_response(error_data)
                except KaiError:
                    raise
                except Exception:
                    raise KaiError(
                        message=f"HTTP {response.status_code}: {response.text}",
                        code=f"http:{response.status_code}",
                    )

            return response

        except httpx.ConnectError as e:
            raise KaiConnectionError(
                message=f"Failed to connect to {self.base_url}",
                cause=str(e),
            ) from e
        except httpx.TimeoutException as e:
            raise KaiTimeoutError(
                message="Request timed out",
                cause=str(e),
            ) from e

    @staticmethod
    def new_chat_id() -> str:
        """
        Generate a new unique chat ID.

        Returns:
            A UUID string for the chat session.
        """
        return str(uuid.uuid4())

    @staticmethod
    def new_message_id() -> str:
        """
        Generate a new unique message ID.

        Returns:
            A UUID string for the message.
        """
        return str(uuid.uuid4())

    # =========================================================================
    # Health & Info Endpoints (No Auth Required)
    # =========================================================================

    async def ping(self) -> PingResponse:
        """
        Check if the server is alive.

        Returns:
            PingResponse with the server timestamp.
        """
        response = await self._request("GET", "/ping", auth=False)
        return PingResponse.model_validate(response.json())

    async def info(self) -> InfoResponse:
        """
        Get server information including MCP connection status.

        Returns:
            InfoResponse with server details.
        """
        response = await self._request("GET", "/api", auth=False)
        return InfoResponse.model_validate(response.json())

    # =========================================================================
    # Chat Endpoints
    # =========================================================================

    @asynccontextmanager
    async def _stream_request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> AsyncIterator[httpx.Response]:
        """
        Make a streaming HTTP request.

        Args:
            method: HTTP method.
            path: API endpoint path.
            json: JSON body for the request.
            params: Query parameters.

        Yields:
            The HTTP response for streaming.
        """
        client = self._get_client()
        headers = self._get_auth_headers()

        async with client.stream(
            method=method,
            url=path,
            json=json,
            params=params,
            headers=headers,
            timeout=httpx.Timeout(self.stream_timeout),
        ) as response:
            if response.status_code >= 400:
                # Read the error body for non-streaming errors
                await response.aread()
                content = response.content.decode("utf-8", errors="replace").strip()

                # Try to parse as JSON error response
                if content.startswith("{"):
                    try:
                        error_data = response.json()
                        raise_for_error_response(error_data)
                    except KaiError:
                        raise
                    except Exception:
                        pass  # Fall through to generic error

                # Generic error with text content or reason phrase
                error_msg = content if content else response.reason_phrase
                raise KaiError(
                    message=f"HTTP {response.status_code}: {error_msg}",
                    code=f"http:{response.status_code}",
                )
            yield response

    async def send_message(
        self,
        chat_id: str,
        text: str,
        *,
        visibility: str | VisibilityType = VisibilityType.PRIVATE,
        branch_id: Optional[int] = None,
        hidden: bool = False,
        request_path: Optional[str] = None,
    ) -> AsyncIterator[SSEEvent]:
        """
        Send a message and stream the response.

        This method sends a user message to an existing or new chat and yields
        SSE events as they arrive from the server.

        Args:
            chat_id: The chat session ID (use new_chat_id() to create one).
            text: The message text to send.
            visibility: Chat visibility (default: private).
            branch_id: Optional Keboola branch ID.
            hidden: Whether the message should be hidden.
            request_path: Optional path context for the request.

        Yields:
            SSE events from the response stream.

        Example:
            ```python
            chat_id = client.new_chat_id()
            async for event in client.send_message(chat_id, "Hello!"):
                if event.type == "text":
                    print(event.text, end="")
            ```
        """
        # Build metadata if needed
        metadata: Optional[MessageMetadata] = None
        if hidden or request_path:
            metadata = MessageMetadata(
                hidden=hidden,
                request_context=RequestContext(path=request_path) if request_path else None,
            )

        # Build the request
        request = ChatRequest(
            id=chat_id,
            message=MessageRequest(
                id=self.new_message_id(),
                role="user",
                parts=[TextPart(type="text", text=text)],
                metadata=metadata,
            ),
            selected_chat_model="chat-model",
            selected_visibility_type=str(
                visibility.value if isinstance(visibility, VisibilityType) else visibility
            ),
            branch_id=branch_id,
        )

        # Serialize with aliases
        payload = request.model_dump(by_alias=True, exclude_none=True)

        async with self._stream_request("POST", "/api/chat", json=payload) as response:
            async for event in parse_sse_stream(response):
                yield event

    async def send_tool_result(
        self,
        chat_id: str,
        tool_call_id: str,
        tool_name: str,
        result: str,
        *,
        visibility: str | VisibilityType = VisibilityType.PRIVATE,
        branch_id: Optional[int] = None,
    ) -> AsyncIterator[SSEEvent]:
        """
        Send a tool result to confirm or deny a pending tool call.

        When the AI requests to execute a tool that requires approval (like
        write operations), the stream will pause with a tool-call event in
        "input-available" state. Use this method to approve or deny the tool
        execution and continue the stream.

        Args:
            chat_id: The chat session ID.
            tool_call_id: The ID of the tool call to respond to (from the event).
            tool_name: The name of the tool (from the event).
            result: The result to send - typically "confirmed" or "denied".
            visibility: Chat visibility (should match the original request).
            branch_id: Optional Keboola branch ID.

        Yields:
            SSE events from the continued response stream.

        Example:
            ```python
            chat_id = client.new_chat_id()
            async for event in client.send_message(chat_id, "Create a new bucket"):
                if event.type == "tool-call" and event.state == "input-available":
                    # Tool requires approval - confirm it
                    async for result_event in client.confirm_tool(
                        chat_id=chat_id,
                        tool_call_id=event.tool_call_id,
                        tool_name=event.tool_name,
                    ):
                        if result_event.type == "text":
                            print(result_event.text, end="")
                elif event.type == "text":
                    print(event.text, end="")
            ```
        """
        # Build the request with a tool-result part
        request = ChatRequest(
            id=chat_id,
            message=MessageRequest(
                id=self.new_message_id(),
                role="user",
                parts=[
                    ToolResultPart(
                        type="tool-result",
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                        result=result,
                    )
                ],
            ),
            selected_chat_model="chat-model",
            selected_visibility_type=str(
                visibility.value if isinstance(visibility, VisibilityType) else visibility
            ),
            branch_id=branch_id,
        )

        # Serialize with aliases
        payload = request.model_dump(by_alias=True, exclude_none=True)

        async with self._stream_request("POST", "/api/chat", json=payload) as response:
            async for event in parse_sse_stream(response):
                yield event

    async def confirm_tool(
        self,
        chat_id: str,
        tool_call_id: str,
        tool_name: str,
        *,
        visibility: str | VisibilityType = VisibilityType.PRIVATE,
        branch_id: Optional[int] = None,
    ) -> AsyncIterator[SSEEvent]:
        """
        Confirm a pending tool call and continue the stream.

        This is a convenience method that calls send_tool_result with "confirmed".

        Args:
            chat_id: The chat session ID.
            tool_call_id: The ID of the tool call to confirm.
            tool_name: The name of the tool.
            visibility: Chat visibility.
            branch_id: Optional Keboola branch ID.

        Yields:
            SSE events from the continued response stream.
        """
        async for event in self.send_tool_result(
            chat_id=chat_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            result="confirmed",
            visibility=visibility,
            branch_id=branch_id,
        ):
            yield event

    async def deny_tool(
        self,
        chat_id: str,
        tool_call_id: str,
        tool_name: str,
        *,
        visibility: str | VisibilityType = VisibilityType.PRIVATE,
        branch_id: Optional[int] = None,
    ) -> AsyncIterator[SSEEvent]:
        """
        Deny a pending tool call and continue the stream.

        This is a convenience method that calls send_tool_result with "denied".
        The AI will typically acknowledge the denial and may suggest alternatives.

        Args:
            chat_id: The chat session ID.
            tool_call_id: The ID of the tool call to deny.
            tool_name: The name of the tool.
            visibility: Chat visibility.
            branch_id: Optional Keboola branch ID.

        Yields:
            SSE events from the continued response stream.
        """
        async for event in self.send_tool_result(
            chat_id=chat_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            result="denied",
            visibility=visibility,
            branch_id=branch_id,
        ):
            yield event

    async def get_chat(self, chat_id: str) -> ChatDetail:
        """
        Get detailed information about a chat including message history.

        Args:
            chat_id: The chat session ID.

        Returns:
            ChatDetail with full message history.
        """
        response = await self._request("GET", f"/api/chat/{chat_id}")
        return ChatDetail.model_validate(response.json())

    async def resume_stream(self, chat_id: str) -> AsyncIterator[SSEEvent]:
        """
        Resume a chat stream if one is available.

        This can be used to reconnect to an ongoing stream after a disconnect.

        Args:
            chat_id: The chat session ID.

        Yields:
            SSE events from the resumed stream.

        Note:
            Returns nothing if no stream is available (server returns 204).
        """
        async with self._stream_request("GET", f"/api/chat/{chat_id}/stream") as response:
            if response.status_code == 204:
                return
            async for event in parse_sse_stream(response):
                yield event

    async def delete_chat(self, chat_id: str) -> None:
        """
        Delete a chat.

        Args:
            chat_id: The chat session ID to delete.
        """
        await self._request("DELETE", "/api/chat", params={"id": chat_id})

    # =========================================================================
    # History Endpoint
    # =========================================================================

    async def get_history(
        self,
        limit: int = 10,
        starting_after: Optional[str] = None,
        ending_before: Optional[str] = None,
    ) -> HistoryResponse:
        """
        Get the user's chat history.

        Args:
            limit: Maximum number of chats to return (default: 10).
            starting_after: Cursor for forward pagination (chat ID).
            ending_before: Cursor for backward pagination (chat ID).

        Returns:
            HistoryResponse with list of chats and pagination info.
        """
        params: dict[str, Any] = {"limit": limit}
        if starting_after:
            params["starting_after"] = starting_after
        if ending_before:
            params["ending_before"] = ending_before

        response = await self._request("GET", "/api/history", params=params)
        return HistoryResponse.model_validate(response.json())

    async def get_all_history(self, batch_size: int = 100) -> AsyncIterator[Chat]:
        """
        Iterate through all chat history.

        This is a convenience method that handles pagination automatically.

        Args:
            batch_size: Number of chats to fetch per request.

        Yields:
            Chat objects from the history.
        """
        starting_after: Optional[str] = None
        while True:
            history = await self.get_history(limit=batch_size, starting_after=starting_after)
            for chat in history.chats:
                yield chat

            if not history.has_more or not history.chats:
                break
            starting_after = history.chats[-1].id

    # =========================================================================
    # Vote Endpoints
    # =========================================================================

    async def get_votes(self, chat_id: str) -> list[Vote]:
        """
        Get all votes for a chat.

        Args:
            chat_id: The chat session ID.

        Returns:
            List of votes on messages in the chat.
        """
        response = await self._request("GET", "/api/vote", params={"chatId": chat_id})
        data = response.json()
        # Response might be a list or an object with a votes field
        if isinstance(data, list):
            return [Vote.model_validate(v) for v in data]
        return [Vote.model_validate(v) for v in data.get("votes", [])]

    async def vote(
        self,
        chat_id: str,
        message_id: str,
        vote_type: str | VoteType,
    ) -> Vote:
        """
        Vote on a message.

        Args:
            chat_id: The chat session ID.
            message_id: The message ID to vote on.
            vote_type: The vote type ("up" or "down").

        Returns:
            The created/updated vote.
        """
        request = VoteRequest(
            chat_id=chat_id,
            message_id=message_id,
            type=vote_type.value if isinstance(vote_type, VoteType) else vote_type,  # type: ignore
        )
        payload = request.model_dump(by_alias=True)

        response = await self._request("PATCH", "/api/vote", json=payload)
        return Vote.model_validate(response.json())

    async def upvote(self, chat_id: str, message_id: str) -> Vote:
        """
        Upvote a message.

        Args:
            chat_id: The chat session ID.
            message_id: The message ID to upvote.

        Returns:
            The created/updated vote.
        """
        return await self.vote(chat_id, message_id, VoteType.UP)

    async def downvote(self, chat_id: str, message_id: str) -> Vote:
        """
        Downvote a message.

        Args:
            chat_id: The chat session ID.
            message_id: The message ID to downvote.

        Returns:
            The created/updated vote.
        """
        return await self.vote(chat_id, message_id, VoteType.DOWN)

    # =========================================================================
    # Convenience Methods
    # =========================================================================

    async def chat(
        self,
        text: str,
        *,
        chat_id: Optional[str] = None,
        visibility: str | VisibilityType = VisibilityType.PRIVATE,
        branch_id: Optional[int] = None,
    ) -> tuple[str, str]:
        """
        Send a message and collect the full text response.

        This is a convenience method that collects all text events into
        a single response string.

        Args:
            text: The message text to send.
            chat_id: Optional chat ID (generates new one if not provided).
            visibility: Chat visibility.
            branch_id: Optional Keboola branch ID.

        Returns:
            Tuple of (chat_id, response_text).

        Example:
            ```python
            chat_id, response = await client.chat("What is 2+2?")
            print(response)
            ```
        """
        if chat_id is None:
            chat_id = self.new_chat_id()

        response_parts: list[str] = []

        async for event in self.send_message(
            chat_id=chat_id,
            text=text,
            visibility=visibility,
            branch_id=branch_id,
        ):
            if event.type == "text":
                response_parts.append(event.text)  # type: ignore

        return chat_id, "".join(response_parts)

