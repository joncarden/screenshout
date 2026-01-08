#!/bin/bash

# Screenshot Renamer Toggle Script
# Double-click to start/stop the screenshot renamer

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/.renamer.pid"
PYTHON="$SCRIPT_DIR/venv/bin/python"
RENAMER="$SCRIPT_DIR/renamer.py"
SCREENSHOTS_FOLDER="$HOME/Documents/Screenshots"

# Load API Key from .env file if it exists
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
fi

# Check for API Key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY not set."
    echo "Please create a .env file in the script directory with your key:"
    echo "OPENAI_API_KEY=your-key-here"
    exit 1
fi

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        # Running - stop it
        echo "Stopping Screenshot Renamer..."
        kill "$PID"
        rm "$PID_FILE"
        echo "Stopped."
        sleep 2
        exit 0
    else
        # Stale PID file
        rm "$PID_FILE"
    fi
fi

# Not running - start it
echo "Starting Screenshot Renamer..."
echo "Watching: $SCREENSHOTS_FOLDER"
echo ""
echo "Keep this window open. Close it or double-click again to stop."
echo ""

"$PYTHON" "$RENAMER" --watch "$SCREENSHOTS_FOLDER" &
echo $! > "$PID_FILE"

# Wait for the process
wait

# Cleanup
rm -f "$PID_FILE"
