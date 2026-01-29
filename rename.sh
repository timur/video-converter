#!/bin/bash
# Rename speakers in a transcript file
# Usage: ./rename.sh <transcript-file> [options]

cd "$(dirname "$0")"
/opt/homebrew/Cellar/openai-whisper/20250625_3/libexec/bin/python rename_speakers.py "$@"
