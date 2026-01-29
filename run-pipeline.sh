#!/bin/bash
# Video-Konvertierungs-Pipeline Wrapper
# Lädt .env und verwendet den korrekten Python-Interpreter

set -a
source "$(dirname "$0")/.env"
set +a

PYTHON="/opt/homebrew/Cellar/openai-whisper/20250625_3/libexec/bin/python"
SCRIPT="$(dirname "$0")/convert.py"

exec "$PYTHON" "$SCRIPT" "$@"
