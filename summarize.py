#!/usr/bin/env python3
"""Generate summary and insights from transcript using Claude API."""

import argparse
import os
import re
import sys
from pathlib import Path

import anthropic


DEFAULT_MODEL = "claude-sonnet-4-20250514"


def load_transcript(transcript_path: Path) -> str:
    """Load and return transcript content."""
    return transcript_path.read_text(encoding="utf-8")


def extract_timestamps_and_text(content: str) -> list[dict]:
    """Parse transcript to extract timestamps with text for insights."""
    pattern = re.compile(
        r'\[(\d{2}:\d{2}(?::\d{2})?) - (\d{2}:\d{2}(?::\d{2})?)\]'
    )

    segments = []
    current_segment = None

    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue

        match = pattern.match(line)
        if match:
            if current_segment and current_segment['text']:
                segments.append(current_segment)
            current_segment = {
                'start': match.group(1),
                'end': match.group(2),
                'text': ''
            }
        elif current_segment and not line.startswith('['):
            current_segment['text'] += ' ' + line

    if current_segment and current_segment['text']:
        segments.append(current_segment)

    return segments


def generate_summary(
    transcript: str,
    client: anthropic.Anthropic,
    model: str = DEFAULT_MODEL,
    language: str = "de"
) -> str:
    """Generate a summary of the transcript."""

    lang_instruction = {
        "de": "Antworte auf Deutsch.",
        "en": "Respond in English."
    }.get(language, "Respond in the same language as the transcript.")

    prompt = f"""Analysiere das folgende Meeting-Transkript und erstelle:

1. **Zusammenfassung** (3-5 Saetze): Was war der Hauptzweck und die wichtigsten Ergebnisse des Meetings?

2. **Teilnehmer**: Liste die Sprecher und ihre Rollen/Beitraege auf (soweit erkennbar).

3. **Wichtigste Punkte**:
   - Hauptthemen, die besprochen wurden
   - Getroffene Entscheidungen
   - Offene Fragen oder Aktionspunkte

4. **Naechste Schritte**: Falls erwaehnt, liste die vereinbarten naechsten Schritte auf.

{lang_instruction}

---
TRANSKRIPT:
{transcript}
"""

    message = client.messages.create(
        model=model,
        max_tokens=2000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return message.content[0].text


def generate_insights_with_timestamps(
    transcript: str,
    segments: list[dict],
    client: anthropic.Anthropic,
    model: str = DEFAULT_MODEL,
    language: str = "de"
) -> str:
    """Generate key insights with timestamps."""

    # Create a condensed version with timestamps for reference
    timestamped_reference = "\n".join([
        f"[{seg['start']}] {seg['text'][:200]}..."
        for seg in segments[:50]  # Limit to avoid token overflow
    ])

    lang_instruction = {
        "de": "Antworte auf Deutsch.",
        "en": "Respond in English."
    }.get(language, "")

    prompt = f"""Analysiere das Meeting-Transkript und identifiziere die wichtigsten Themen und Erkenntnisse.

Fuer jedes wichtige Thema/Erkenntnis, gib an:
- Den Zeitstempel (im Format [MM:SS] oder [HH:MM:SS])
- Eine kurze Beschreibung des Themas/der Erkenntnis

Format:
[Zeitstempel] Thema/Erkenntnis

Beispiel:
[02:15] Projektvorstellung: Neue Bildungsplattform mit KI-Unterstuetzung
[05:30] Technische Architektur: React Frontend, Rails Backend, Python AI-Services
[12:45] Diskussion: Performance-Optimierung der Tree-Struktur

Identifiziere 5-10 der wichtigsten Punkte.

{lang_instruction}

---
TRANSKRIPT MIT ZEITSTEMPELN:
{timestamped_reference}

---
VOLLSTAENDIGES TRANSKRIPT (erste 15000 Zeichen):
{transcript[:15000]}
"""

    message = client.messages.create(
        model=model,
        max_tokens=1500,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return message.content[0].text


def main():
    parser = argparse.ArgumentParser(
        description="Generiere Zusammenfassung und Erkenntnisse aus einem Transkript"
    )
    parser.add_argument("transcript", help="Pfad zur Transkript-Datei")
    parser.add_argument("--output", "-o", help="Ausgabe-Verzeichnis (Standard: gleiches Verzeichnis wie Transkript)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Claude Modell (Standard: {DEFAULT_MODEL})")
    parser.add_argument("--language", "-l", default="de",
                        help="Ausgabe-Sprache: de, en (Standard: de)")
    parser.add_argument("--api-key", default=os.environ.get("ANTHROPIC_API_KEY"),
                        help="Anthropic API Key (oder ANTHROPIC_API_KEY setzen)")
    parser.add_argument("--insights-only", action="store_true",
                        help="Nur Erkenntnisse mit Timestamps generieren")
    parser.add_argument("--summary-only", action="store_true",
                        help="Nur Zusammenfassung generieren")
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("Anthropic API Key erforderlich. Setze ANTHROPIC_API_KEY oder nutze --api-key")

    transcript_path = Path(args.transcript)
    if not transcript_path.exists():
        sys.exit(f"Datei nicht gefunden: {transcript_path}")

    output_dir = Path(args.output) if args.output else transcript_path.parent

    print(f"Lade Transkript: {transcript_path}")
    transcript = load_transcript(transcript_path)
    segments = extract_timestamps_and_text(transcript)

    client = anthropic.Anthropic(api_key=args.api_key)

    output_parts = []

    # Generate summary
    if not args.insights_only:
        print("Generiere Zusammenfassung...")
        summary = generate_summary(transcript, client, args.model, args.language)
        output_parts.append("# Meeting-Zusammenfassung\n")
        output_parts.append(summary)
        output_parts.append("\n")

    # Generate insights with timestamps
    if not args.summary_only:
        print("Generiere Erkenntnisse mit Timestamps...")
        insights = generate_insights_with_timestamps(
            transcript, segments, client, args.model, args.language
        )
        output_parts.append("\n# Wichtige Punkte mit Zeitstempeln\n")
        output_parts.append(insights)

    # Write output
    summary_path = output_dir / "summary.txt"
    summary_path.write_text("\n".join(output_parts), encoding="utf-8")
    print(f"\nZusammenfassung gespeichert: {summary_path}")


if __name__ == "__main__":
    main()
