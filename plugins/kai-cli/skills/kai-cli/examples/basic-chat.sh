#!/bin/bash
# Basic Kai CLI chat examples

# Ensure environment variables are set
# export STORAGE_API_TOKEN="your-token"
# export STORAGE_API_URL="https://connection.keboola.com"

# Or load from .env.local
# set -a && source .env.local && set +a

# Check server connectivity
echo "=== Checking server health ==="
kai ping

# Get server info
echo -e "\n=== Server information ==="
kai info

# Send a single message
echo -e "\n=== Sending a question ==="
kai chat -m "What tables do I have in my project?"

# Interactive chat (uncomment to use)
# echo -e "\n=== Starting interactive chat ==="
# kai chat

# View recent chat history
echo -e "\n=== Recent chat history ==="
kai history --limit 5
