#!/usr/bin/env python3
"""Rename speakers in an existing transcript file."""

import argparse
import re
import sys
from pathlib import Path

# Regex patterns for parsing transcript
# New format: [00:05:12 - 00:05:30] [Speaker-1]
TIMESTAMPED_HEADER = re.compile(
    r'\[(\d{2}:\d{2}(?::\d{2})?) - (\d{2}:\d{2}(?::\d{2})?)\]\s*\[([^\]]+)\]'
)
# Timestamp only: [00:05:12 - 00:05:30]
TIMESTAMP_ONLY = re.compile(
    r'\[(\d{2}:\d{2}(?::\d{2})?) - (\d{2}:\d{2}(?::\d{2})?)\]$'
)
# Legacy format: [Speaker-1]
SPEAKER_ONLY = re.compile(r'^\[([^\]]+)\]$')


def parse_transcript(content: str) -> list[dict]:
    """Parse transcript into structured segments."""
    segments = []
    current_segment = None

    for line in content.split('\n'):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Check for timestamped header with speaker
        match = TIMESTAMPED_HEADER.match(line_stripped)
        if match:
            if current_segment:
                segments.append(current_segment)
            current_segment = {
                'start': match.group(1),
                'end': match.group(2),
                'speaker': match.group(3),
                'text': []
            }
            continue

        # Check for timestamp only (no speaker change)
        match = TIMESTAMP_ONLY.match(line_stripped)
        if match:
            if current_segment:
                segments.append(current_segment)
            current_segment = {
                'start': match.group(1),
                'end': match.group(2),
                'speaker': current_segment.get('speaker') if current_segment else 'Unknown',
                'text': []
            }
            continue

        # Check for speaker-only header (legacy format)
        match = SPEAKER_ONLY.match(line_stripped)
        if match:
            if current_segment:
                segments.append(current_segment)
            current_segment = {
                'speaker': match.group(1),
                'text': []
            }
            continue

        # Regular text line
        if current_segment:
            current_segment['text'].append(line_stripped)

    if current_segment:
        segments.append(current_segment)

    return segments


def collect_speaker_samples(segments: list[dict]) -> dict[str, str]:
    """Get first substantial quote from each speaker."""
    samples = {}
    for seg in segments:
        speaker = seg.get('speaker', 'Unknown')
        if speaker not in samples:
            text = ' '.join(seg['text'])
            if len(text) > 10:
                samples[speaker] = text[:150]
    return samples


def prompt_rename(samples: dict[str, str]) -> dict[str, str]:
    """Interactive prompt to rename speakers."""
    print("\n--- Speaker Umbenennung ---")
    print("Gib einen neuen Namen fuer jeden Speaker ein (oder Enter zum Ueberspringen).\n")

    name_map = {}
    for speaker, sample in sorted(samples.items()):
        print(f'  {speaker}: "{sample}..."')
        try:
            new_name = input(f"  Neuer Name fuer {speaker}: ").strip()
        except EOFError:
            break
        if new_name:
            name_map[speaker] = new_name

    return name_map


def apply_rename(segments: list[dict], name_map: dict[str, str]) -> None:
    """Apply name mappings to segments."""
    for seg in segments:
        old_name = seg.get('speaker')
        if old_name in name_map:
            seg['speaker'] = name_map[old_name]


def format_transcript(segments: list[dict]) -> str:
    """Reconstruct transcript from segments."""
    lines = []
    current_speaker = None

    for seg in segments:
        header_parts = []

        if 'start' in seg and 'end' in seg:
            header_parts.append(f"[{seg['start']} - {seg['end']}]")

        speaker = seg.get('speaker')
        if speaker and speaker != current_speaker:
            current_speaker = speaker
            header_parts.append(f"[{speaker}]")

        if header_parts:
            lines.append("\n" + " ".join(header_parts))

        for text_line in seg['text']:
            lines.append(text_line)

    return "\n".join(lines).strip()


def main():
    parser = argparse.ArgumentParser(
        description="Umbenennung von Speakern in einem Transkript",
        epilog="""
Beispiele:
  # Interaktiv umbenennen
  python rename_speakers.py converted/meeting/transcript.txt

  # Direkte Zuordnung
  python rename_speakers.py transcript.txt -m "Speaker-1" "Reza" -m "Speaker-2" "Florian"

  # In andere Datei schreiben
  python rename_speakers.py transcript.txt -o transcript_renamed.txt
        """
    )
    parser.add_argument("transcript", help="Pfad zur Transkript-Datei")
    parser.add_argument("--output", "-o", help="Ausgabe-Datei (Standard: Eingabe ueberschreiben)")
    parser.add_argument("--mapping", "-m", nargs=2, action="append",
                        metavar=("ALT", "NEU"),
                        help="Direkte Zuordnung: -m 'Speaker-1' 'Reza'")
    args = parser.parse_args()

    transcript_path = Path(args.transcript)
    if not transcript_path.exists():
        sys.exit(f"Datei nicht gefunden: {transcript_path}")

    content = transcript_path.read_text(encoding="utf-8")
    segments = parse_transcript(content)

    if not segments:
        sys.exit("Keine Segmente im Transkript gefunden")

    # Get unique speakers
    speakers = set(seg.get('speaker') for seg in segments if seg.get('speaker'))
    print(f"Gefundene Speaker: {', '.join(sorted(speakers))}")

    # Get name mappings
    if args.mapping:
        name_map = dict(args.mapping)
    else:
        samples = collect_speaker_samples(segments)
        name_map = prompt_rename(samples)

    if not name_map:
        print("Keine Aenderungen vorgenommen.")
        return

    # Apply and save
    apply_rename(segments, name_map)
    output_path = Path(args.output) if args.output else transcript_path

    new_content = format_transcript(segments)
    output_path.write_text(new_content, encoding="utf-8")

    print(f"\nTranskript aktualisiert: {output_path}")
    for old, new in name_map.items():
        print(f"  {old} -> {new}")


if __name__ == "__main__":
    main()
