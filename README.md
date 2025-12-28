# Kai Client

A Python client library for interacting with the Keboola AI Assistant Backend API. This library provides async support, SSE streaming, and comprehensive type safety through Pydantic models.

## Features

- **Command-line interface** for quick interactions without writing code
- **Async/await support** using `httpx`
- **Server-Sent Events (SSE) streaming** for real-time chat responses
- **Type-safe models** with Pydantic v2
- **Comprehensive error handling** with custom exception classes
- **Session management** for chat conversations
- **Full API coverage** including chat, history, and voting endpoints

## Installation

### Using uv (recommended)

```bash
uv add kai-client
```

### Using pip

```bash
pip install kai-client
```

### From source

```bash
git clone https://github.com/keboola/kai-client.git
cd kai-client
uv sync
```

## Quick Start

```python
import asyncio
from kai_client import KaiClient

async def main():
    # Production: Auto-discover the kai-assistant URL from your Keboola stack
    client = await KaiClient.from_storage_api(
        storage_api_token="your-keboola-token",
        storage_api_url="https://connection.keboola.com"  # Your stack URL
    )

    async with client:
        # Check server health
        ping = await client.ping()
        print(f"Server time: {ping.timestamp}")

        # Start a new chat
        chat_id = client.new_chat_id()

        # Send a message and stream the response
        async for event in client.send_message(chat_id, "What can you help me with?"):
            if event.type == "text":
                print(event.text, end="", flush=True)
            elif event.type == "tool-call":
                print(f"\n[Calling tool: {event.tool_name}]")
            elif event.type == "finish":
                print(f"\n[Finished: {event.finish_reason}]")

asyncio.run(main())
```

## Command-Line Interface

The package includes a `kai` CLI for quick interactions without writing code.

### Setup

Set your credentials as environment variables:

```bash
export STORAGE_API_TOKEN="your-keboola-token"
export STORAGE_API_URL="https://connection.keboola.com"
```

### Basic Commands

```bash
# Check server health
kai ping

# Get server info
kai info

# Start an interactive chat
kai chat

# Send a single message
kai chat -m "What tables do I have?"

# View chat history
kai history

# Get details of a specific chat
kai get-chat <chat-id>

# Delete a chat
kai delete-chat <chat-id>

# Vote on a message
kai vote <chat-id> <message-id> up
```

### Chat Options

```bash
# Auto-approve tool calls (for automation)
kai chat --auto-approve -m "Create a bucket called test-bucket"

# Continue an existing conversation
kai chat --chat-id abc-123 -m "Tell me more about that"

# Output raw JSON events (for scripting)
kai chat --json-output -m "List my tables"
```

### Local Development

For local development, specify a custom base URL:

```bash
kai --base-url http://localhost:3000 chat -m "Hello"
```

### Help

```bash
# General help
kai --help

# Command-specific help
kai chat --help
kai history --help
```

### Local Development vs Production

| Setting | Local Dev | Production |
|---------|-----------|------------|
| Base URL | `http://localhost:3000` | Auto-discovered |
| Setup | Manual `base_url` parameter | Use `from_storage_api()` |

```python
# Local development (explicit base_url)
client = KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com",
    base_url="http://localhost:3000"
)

# Production (auto-discovers kai-assistant URL)
client = await KaiClient.from_storage_api(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
)
```

## Usage Examples

### Simple Chat (Non-Streaming)

```python
async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    # Simple one-shot conversation
    chat_id, response = await client.chat("What is 2 + 2?")
    print(response)
```

### Continuing a Conversation

```python
async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    # Create a chat session
    chat_id = client.new_chat_id()

    # First message
    async for event in client.send_message(chat_id, "Hello!"):
        if event.type == "text":
            print(event.text, end="")
    print()

    # Continue the conversation (reuse same chat_id)
    async for event in client.send_message(chat_id, "What did I just say?"):
        if event.type == "text":
            print(event.text, end="")
    print()
```

### Handling Tool Calls

```python
async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    chat_id = client.new_chat_id()

    async for event in client.send_message(chat_id, "List my Keboola tables"):
        match event.type:
            case "text":
                print(event.text, end="")
            case "step-start":
                print("\n--- New step ---")
            case "tool-call":
                if event.state == "input-available":
                    print(f"\n[Calling {event.tool_name} with {event.input}]")
                elif event.state == "output-available":
                    print(f"\n[{event.tool_name} returned: {event.output}]")
            case "finish":
                print(f"\n[Done: {event.finish_reason}]")
```

### Chat History

```python
async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    # Get recent chats
    history = await client.get_history(limit=20)
    for chat in history.chats:
        print(f"Chat {chat.id}: {chat.title}")

    # Iterate through all history
    async for chat in client.get_all_history():
        print(f"Chat: {chat.title}")

    # Get full chat details with messages
    chat_detail = await client.get_chat(chat_id="some-chat-id")
    for message in chat_detail.messages:
        print(f"{message.role}: {message.parts}")
```

### Voting on Messages

```python
async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    # Upvote a helpful response
    await client.upvote(chat_id="chat-uuid", message_id="message-uuid")

    # Or downvote
    await client.downvote(chat_id="chat-uuid", message_id="message-uuid")

    # Get all votes for a chat
    votes = await client.get_votes(chat_id="chat-uuid")
```

### Tool Approval for Write Operations

Some tools (like `create_config`, `run_job`, `create_flow`) require explicit approval before execution:

```python
async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    chat_id = client.new_chat_id()
    pending_approval = None

    async for event in client.send_message(chat_id, "Create a new bucket"):
        if event.type == "text":
            print(event.text, end="")
        elif event.type == "tool-call":
            if event.state == "input-available":
                # Tool is waiting for approval
                print(f"\nTool {event.tool_name} needs approval")
                pending_approval = event
            elif event.state == "output-available":
                print(f"\nTool {event.tool_name} completed")

    # Approve the pending tool call
    if pending_approval:
        async for event in client.confirm_tool(
            chat_id=chat_id,
            tool_call_id=pending_approval.tool_call_id,
            tool_name=pending_approval.tool_name,
        ):
            if event.type == "text":
                print(event.text, end="")

    # Or deny it
    # async for event in client.deny_tool(chat_id, tool_call_id, tool_name):
    #     ...
```

### Using SSE Stream Parser

```python
from kai_client import KaiClient, SSEStreamParser

async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    parser = SSEStreamParser()
    chat_id = client.new_chat_id()

    async for event in client.send_message(chat_id, "Hello!"):
        parser.process_event(event)

    # Access accumulated data
    print(f"Full response: {parser.text}")
    print(f"Tool calls: {parser.tool_calls}")
    print(f"Finished: {parser.finished}")
```

### Error Handling

```python
from kai_client import (
    KaiClient,
    KaiError,
    KaiAuthenticationError,
    KaiRateLimitError,
    KaiNotFoundError,
)

async with KaiClient(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com"
) as client:
    try:
        async for event in client.send_message("chat-id", "Hello"):
            print(event)
    except KaiAuthenticationError as e:
        print(f"Authentication failed: {e}")
    except KaiRateLimitError as e:
        print(f"Rate limited, try again later: {e}")
    except KaiNotFoundError as e:
        print(f"Chat not found: {e}")
    except KaiError as e:
        print(f"API error: {e.code} - {e.message}")
```

## API Reference

### KaiClient

The main client class for interacting with the Kai API.

#### Factory Method (Recommended for Production)

```python
client = await KaiClient.from_storage_api(
    storage_api_token: str,      # Keboola Storage API token
    storage_api_url: str,        # Keboola connection URL (e.g., https://connection.keboola.com)
    timeout: float = 300.0,      # Request timeout in seconds
    stream_timeout: float = 600.0  # Streaming timeout in seconds
)
```

This method auto-discovers the kai-assistant service URL from your Keboola stack.

#### Constructor (For Local Development)

```python
KaiClient(
    storage_api_token: str,      # Keboola Storage API token
    storage_api_url: str,        # Keboola connection URL
    base_url: str = "http://localhost:3000",  # Kai API base URL
    timeout: float = 300.0,      # Request timeout in seconds
    stream_timeout: float = 600.0  # Streaming timeout in seconds
)
```

#### Methods

| Method | Description |
|--------|-------------|
| `from_storage_api(...)` | **[Class method]** Create client with auto-discovered URL |
| `ping()` | Check server health |
| `info()` | Get server information |
| `send_message(chat_id, text, ...)` | Send a message and stream response |
| `send_tool_result(chat_id, tool_call_id, ...)` | Send tool approval/denial result |
| `confirm_tool(chat_id, tool_call_id, ...)` | Approve a pending tool call |
| `deny_tool(chat_id, tool_call_id, ...)` | Deny a pending tool call |
| `chat(text, ...)` | Simple non-streaming chat |
| `get_chat(chat_id)` | Get chat details with messages |
| `get_history(limit, ...)` | Get chat history |
| `get_all_history()` | Iterate through all history |
| `delete_chat(chat_id)` | Delete a chat |
| `vote(chat_id, message_id, type)` | Vote on a message |
| `upvote(chat_id, message_id)` | Upvote a message |
| `downvote(chat_id, message_id)` | Downvote a message |
| `get_votes(chat_id)` | Get votes for a chat |

### SSE Event Types

| Event Type | Description | Fields |
|------------|-------------|--------|
| `text` | Text content | `text`, `state` |
| `step-start` | Processing step started | - |
| `tool-call` | Tool being called | `tool_call_id`, `tool_name`, `state`, `input`, `output` |
| `finish` | Stream completed | `finish_reason` |
| `error` | Error occurred | `message`, `code` |

### Exceptions

| Exception | Error Code | Description |
|-----------|------------|-------------|
| `KaiError` | - | Base exception |
| `KaiAuthenticationError` | `unauthorized:chat` | Invalid credentials |
| `KaiForbiddenError` | `forbidden:chat` | Access denied |
| `KaiNotFoundError` | `not_found:chat` | Resource not found |
| `KaiRateLimitError` | `rate_limit:chat` | Rate limit exceeded |
| `KaiBadRequestError` | `bad_request:api` | Invalid request |
| `KaiStreamError` | - | SSE stream error |
| `KaiConnectionError` | - | Connection failed |
| `KaiTimeoutError` | - | Request timed out |

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/keboola/kai-client.git
cd kai-client

# Install with dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Run linting
uv run ruff check .
```

### Running Tests

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=kai_client

# Specific test file
uv run pytest tests/test_client.py
```

## License

MIT License - see [LICENSE](LICENSE) for details.


