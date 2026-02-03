#!/bin/bash
# Automated workflow example with Kai CLI

# This script demonstrates automating Keboola operations with Kai
# using the --auto-approve flag for write operations

set -e

# Load environment
if [ -f .env.local ]; then
    set -a && source .env.local && set +a
fi

# Verify connectivity
echo "Checking Kai server..."
kai ping || { echo "Server not reachable"; exit 1; }

# Example: Automated data exploration
echo -e "\n=== Exploring project data ==="
kai chat -m "Give me a summary of all tables in my project" --json-output > /tmp/tables.json

# Extract chat ID for follow-up
CHAT_ID=$(jq -r '.chat_id // empty' /tmp/tables.json | head -1)

if [ -n "$CHAT_ID" ]; then
    echo "Chat ID: $CHAT_ID"

    # Continue the conversation
    echo -e "\n=== Follow-up question ==="
    kai chat --chat-id "$CHAT_ID" -m "Which table has the most rows?"
fi

# Example: Automated write operation (use with caution!)
# Uncomment to enable auto-approval of write operations
# echo -e "\n=== Creating bucket with auto-approve ==="
# kai chat --auto-approve -m "Create a bucket called automated-test-bucket in the in stage"

# Example: Get operation result as JSON for scripting
echo -e "\n=== Getting JSON output for scripting ==="
kai chat --json-output -m "List all configurations" | jq '.data.text // empty' | head -20

echo -e "\nWorkflow complete!"
