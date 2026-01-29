#!/bin/bash
set -a
source "$(dirname "$0")/.env"
set +a
PYTHON="/opt/homebrew/Cellar/openai-whisper/20250625_3/libexec/bin/python"
SCRIPT="$(dirname "$0")/transcribe.py"
exec "$PYTHON" "$SCRIPT" "$@"
