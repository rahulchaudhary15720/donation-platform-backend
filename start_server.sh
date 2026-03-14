#!/bin/bash
# Startup script that forces IPv4 connectivity for the application

# Set environment variable to prefer IPv4
export PYTHONUNBUFFERED=1

# Check if running with virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run uvicorn with IPv4 preference
# The --host 0.0.0.0 binds to IPv4
echo "Starting server with IPv4 preference..."
exec stdbuf -oL ./.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
