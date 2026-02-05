#!/usr/bin/env python3
"""Video processing pipeline: compress, transcribe, and organize meeting recordings."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Configuration
SCRIPT_DIR = Path(__file__).parent
INPUT_DIR = SCRIPT_DIR / "files"
OUTPUT_DIR = SCRIPT_DIR / "converted"
VIDEO_EXTENSIONS = {".mov", ".mp4", ".mkv", ".avi", ".webm", ".m4v"}


WEEKDAYS_DE = {
    0: "Montag",
    1: "Dienstag",
    2: "Mittwoch",
    3: "Donnerstag",
    4: "Freitag",
    5: "Samstag",
    6: "Sonntag"
}


def get_recording_name(video_path: Path) -> str:
    """Extract recording name from filename (without extension)."""
    return video_path.stem


def parse_recording_datetime(filename: str) -> datetime | None:
    """Parse datetime from filename like 'Bildschirmaufnahme 2026-01-28 um 09.47.24'."""
    # Pattern: "Bildschirmaufnahme YYYY-MM-DD um HH.MM.SS"
    pattern = r'(\d{4})-(\d{2})-(\d{2}) um (\d{2})\.(\d{2})\.(\d{2})'
    match = re.search(pattern, filename)
    if match:
        year, month, day, hour, minute, second = map(int, match.groups())
        return datetime(year, month, day, hour, minute, second)
    return None


def extract_title_from_transcript(transcript_path: Path, api_key: str = None) -> str | None:
    """Extract a meaningful title from the transcript."""
    if not transcript_path.exists():
        return None

    content = transcript_path.read_text(encoding="utf-8")

    # If we have an API key, use Claude to generate a title
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)

            # Use first 8000 chars to stay within limits
            excerpt = content[:8000]

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                messages=[{
                    "role": "user",
                    "content": f"""Analysiere dieses Meeting-Transkript und gib einen kurzen, prägnanten Titel zurück (2-5 Wörter, auf Deutsch).
Der Titel sollte das Hauptthema des Meetings beschreiben.
Antworte NUR mit dem Titel, ohne Anführungszeichen oder zusätzlichen Text.

Transkript:
{excerpt}"""
                }]
            )
            title = message.content[0].text.strip()
            # Clean up: remove quotes, limit length
            title = title.strip('"\'')
            if len(title) > 50:
                title = title[:50]
            return title
        except Exception as e:
            print(f"  ⚠️  Titel-Generierung fehlgeschlagen: {e}")

    # Fallback: Try to extract from content heuristically
    # Look for common patterns like "sprechen über", "Thema", etc.
    lines = [l.strip() for l in content.split('\n') if l.strip() and not l.startswith('[')]

    # Skip very short segments, look for substantive content
    for line in lines[5:30]:  # Skip first few lines (usually greetings)
        if len(line) > 20:
            # Look for topic indicators
            topic_patterns = [
                r'(?:sprechen|reden) (?:über|wir über) (.+?)(?:\.|,|$)',
                r'(?:Thema|Aufgabe|Projekt)[:\s]+(.+?)(?:\.|,|$)',
                r'(?:geht es um|geht um) (.+?)(?:\.|,|$)',
            ]
            for pattern in topic_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    topic = match.group(1).strip()
                    if 5 < len(topic) < 50:
                        return topic.title()

    return None


def sanitize_filename(name: str) -> str:
    """Remove or replace characters that are problematic in filenames."""
    # Replace problematic characters
    replacements = {
        '/': '-',
        '\\': '-',
        ':': '-',
        '*': '',
        '?': '',
        '"': '',
        '<': '',
        '>': '',
        '|': '-',
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    # Remove multiple spaces/dashes
    name = re.sub(r'[-\s]+', '-', name)
    return name.strip('-')


def generate_folder_name(recording_name: str, transcript_path: Path = None, api_key: str = None) -> str:
    """Generate a descriptive folder name with date, weekday, time and title."""
    dt = parse_recording_datetime(recording_name)

    if dt:
        weekday = WEEKDAYS_DE[dt.weekday()]
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H-%M")

        # Try to get a title
        title = None
        if transcript_path:
            title = extract_title_from_transcript(transcript_path, api_key)

        if title:
            title_clean = sanitize_filename(title)
            return f"{date_str}_{weekday}_{time_str}_{title_clean}"
        else:
            return f"{date_str}_{weekday}_{time_str}_Meeting"

    # Fallback: return original name
    return recording_name


def rename_output_folder(old_path: Path, new_name: str) -> Path:
    """Rename the output folder to a more descriptive name."""
    new_path = old_path.parent / new_name

    # Handle collision
    if new_path.exists() and new_path != old_path:
        counter = 2
        base_name = new_name
        while new_path.exists():
            new_name = f"{base_name}_{counter}"
            new_path = old_path.parent / new_name
            counter += 1

    if old_path != new_path:
        old_path.rename(new_path)

    return new_path


def get_video_info(input_path: Path) -> dict:
    """Get video duration and resolution using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration:stream=width,height",
        "-of", "json", str(input_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        import json
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        streams = data.get("streams", [{}])
        width = streams[0].get("width", 0) if streams else 0
        height = streams[0].get("height", 0) if streams else 0
        return {"duration": duration, "width": width, "height": height}
    return {"duration": 0, "width": 0, "height": 0}


def format_duration(seconds: float) -> str:
    """Format seconds as HH:MM:SS or MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def compress_video(
    input_path: Path,
    output_path: Path,
    quality: int = 50,
    scale: str = None,
    max_compression: bool = False
) -> bool:
    """Compress video using H.265 encoder.

    Args:
        input_path: Source video file
        output_path: Destination file
        quality: Quality setting (0-100 for HW, ignored for max_compression)
        scale: Resolution preset ("1080p", "720p") or None for original
        max_compression: Use software encoder (libx265) for maximum compression
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Get video info for progress display
    info = get_video_info(input_path)
    duration_str = format_duration(info["duration"]) if info["duration"] else "unbekannt"
    resolution_str = f"{info['width']}x{info['height']}" if info["width"] else "unbekannt"

    # Build ffmpeg command
    cmd = ["ffmpeg", "-i", str(input_path)]

    # Video filters (scaling)
    vf_filters = []
    if scale:
        scale_map = {
            "1080p": "1920:-2",  # 1920 width, height proportional (divisible by 2)
            "720p": "1280:-2",
        }
        if scale in scale_map:
            vf_filters.append(f"scale={scale_map[scale]}")
        else:
            print(f"  Warnung: Unbekannte Skalierung '{scale}', überspringe")

    if vf_filters:
        cmd.extend(["-vf", ",".join(vf_filters)])

    # Video codec
    if max_compression:
        # Software encoder: slower but better compression
        cmd.extend([
            "-c:v", "libx265",
            "-crf", "28",
            "-preset", "medium",
        ])
        mode_info = "Software (libx265, CRF 28)"
    else:
        # Hardware encoder: fast
        cmd.extend([
            "-c:v", "hevc_videotoolbox",
            "-q:v", str(quality),
        ])
        mode_info = f"Hardware (VideoToolbox, q={quality})"

    # Common settings
    cmd.extend([
        "-tag:v", "hvc1",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-y",
        str(output_path)
    ])

    print(f"\n📹 KOMPRIMIERUNG")
    print(f"  Eingabe:    {input_path.name}")
    print(f"  Dauer:      {duration_str}")
    print(f"  Auflösung:  {resolution_str}")
    print(f"  Größe:      {input_path.stat().st_size / 1e9:.2f} GB")
    print(f"  Modus:      {mode_info}")
    if scale:
        print(f"  Skalierung: {scale}")
    print(f"  Ziel:       {output_path}")
    print(f"  ⏳ Starte ffmpeg...")

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"  ❌ FEHLER bei der Komprimierung")
        return False

    in_size = input_path.stat().st_size
    out_size = output_path.stat().st_size
    ratio = in_size / out_size
    print(f"  ✅ Komprimierung abgeschlossen")
    print(f"     {in_size/1e9:.2f} GB → {out_size/1e6:.0f} MB ({ratio:.1f}x Reduktion)")
    return True


def transcribe_video(video_path: Path, output_dir: Path, hf_token: str = None, interactive: bool = False) -> bool:
    """Run transcription with speaker diarization on video."""
    # Import from transcribe module
    sys.path.insert(0, str(SCRIPT_DIR))
    from transcribe import (
        extract_audio, transcribe, diarize, assign_speakers,
        prompt_speaker_names, apply_speaker_names, format_output,
        auto_name_speakers
    )

    transcript_path = output_dir / "transcript.txt"

    print(f"\n🎙️ TRANSKRIPTION")
    print(f"  Eingabe: {video_path.name}")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_audio = Path(tmp.name)

    try:
        print("  ⏳ Audio extrahieren...")
        extract_audio(video_path, tmp_audio)
        print("  ✅ Audio extrahiert")

        print("  ⏳ Whisper Transkription (Modell: turbo, Sprache: de)...")
        result = transcribe(tmp_audio, model_name="turbo", language="de")
        print(f"  ✅ Transkription abgeschlossen ({len(result['segments'])} Segmente)")

        if hf_token:
            print("  ⏳ Sprecher-Diarisierung (pyannote)...")
            speaker_turns = diarize(tmp_audio, hf_token)
            assign_speakers(result["segments"], speaker_turns)
            print("  ✅ Sprecher-Erkennung abgeschlossen")

            if interactive:
                # Interactive speaker naming
                name_map = prompt_speaker_names(result["segments"])
            else:
                # Auto-name speakers as Speaker-1, Speaker-2, etc.
                name_map = auto_name_speakers(result["segments"])
                if name_map:
                    print(f"  Auto-benannt: {', '.join(name_map.values())}")

            if name_map:
                apply_speaker_names(result["segments"], name_map)
                # Save speaker mapping to this recording's directory
                speaker_file = output_dir / "speakers.json"
                speaker_file.write_text(json.dumps(name_map, indent=2, ensure_ascii=False))
                print(f"     Sprecher: {', '.join(name_map.values())}")
                print(f"     Gespeichert: {speaker_file.name}")
        else:
            print("  ⚠️  Kein HF_TOKEN - Sprecher-Erkennung übersprungen")

        # Save transcript with timestamps
        text = format_output(result["segments"], with_speakers=bool(hf_token), with_timestamps=True)
        transcript_path.write_text(text, encoding="utf-8")
        print(f"  📝 Transkript gespeichert: {transcript_path.name}")

        return True

    except Exception as e:
        print(f"  ❌ FEHLER bei Transkription: {e}")
        return False
    finally:
        tmp_audio.unlink(missing_ok=True)


def summarize_transcript(transcript_path: Path, output_dir: Path, api_key: str = None) -> bool:
    """Generate summary from transcript using Claude API."""
    if not api_key:
        # Still ohne Meldung - Benutzer kann manuell mit Claude Code zusammenfassen
        return False

    try:
        import anthropic
    except ImportError:
        # anthropic nicht installiert - still überspringen
        return False

    # Import from summarize module
    sys.path.insert(0, str(SCRIPT_DIR))
    from summarize import (
        load_transcript, extract_timestamps_and_text,
        generate_summary, generate_insights_with_timestamps
    )

    print("  Zusammenfassung generieren...")

    try:
        transcript = load_transcript(transcript_path)
        segments = extract_timestamps_and_text(transcript)
        client = anthropic.Anthropic(api_key=api_key)

        output_parts = []

        # Generate summary
        summary = generate_summary(transcript, client, language="de")
        output_parts.append("# Meeting-Zusammenfassung\n")
        output_parts.append(summary)
        output_parts.append("\n")

        # Generate insights with timestamps
        insights = generate_insights_with_timestamps(transcript, segments, client, language="de")
        output_parts.append("\n# Wichtige Punkte mit Zeitstempeln\n")
        output_parts.append(insights)

        # Write output
        summary_path = output_dir / "summary.txt"
        summary_path.write_text("\n".join(output_parts), encoding="utf-8")
        print(f"  Zusammenfassung gespeichert: {summary_path}")

        return True

    except Exception as e:
        print(f"  FEHLER bei Zusammenfassung: {e}")
        return False


def find_videos(input_dir: Path) -> list:
    """Find all video files in input directory."""
    videos = []
    if not input_dir.exists():
        return videos
    for ext in VIDEO_EXTENSIONS:
        videos.extend(input_dir.glob(f"*{ext}"))
        videos.extend(input_dir.glob(f"*{ext.upper()}"))
    return sorted(videos)


def is_already_processed(video_path: Path) -> bool:
    """Check if video has already been processed."""
    recording_name = get_recording_name(video_path)
    output_dir = OUTPUT_DIR / recording_name
    output_video = output_dir / "video.mp4"
    return output_video.exists()


def process_video(
    input_path: Path,
    compress: bool = True,
    do_transcribe: bool = True,
    do_summarize: bool = True,
    quality: int = 50,
    scale: str = None,
    max_compression: bool = False,
    delete_original: bool = True,
    interactive: bool = False
) -> bool:
    """Process a single video through the pipeline."""
    # If video is already in converted/ (transcribe-only mode), use its parent dir
    input_path_resolved = input_path.resolve()
    if not compress and OUTPUT_DIR in input_path_resolved.parents:
        output_dir = input_path_resolved.parent
        recording_name = output_dir.name
        output_video = input_path_resolved
    else:
        recording_name = get_recording_name(input_path)
        output_dir = OUTPUT_DIR / recording_name
        output_video = output_dir / "video.mp4"

    print(f"\n{'='*60}")
    print(f"🎬 VERARBEITE: {recording_name}")
    print(f"{'='*60}")

    steps = []
    if compress:
        steps.append("Komprimierung")
    if do_transcribe:
        steps.append("Transkription")
        if os.environ.get("HF_TOKEN"):
            steps.append("Sprecher-Erkennung")
    if do_summarize and os.environ.get("ANTHROPIC_API_KEY"):
        steps.append("Zusammenfassung")
    steps.append("Umbenennung")
    if delete_original and compress:
        steps.append("Aufräumen")

    print(f"  Schritte: {' → '.join(steps)}")

    # Step 1: Compress
    if compress:
        if not compress_video(input_path, output_video, quality, scale, max_compression):
            return False

    # Step 2: Transcribe
    if do_transcribe:
        video_to_transcribe = output_video if compress else input_path
        hf_token = os.environ.get("HF_TOKEN")
        if not transcribe_video(video_to_transcribe, output_dir, hf_token, interactive):
            return False

    # Step 3: Summarize (optional - nur wenn ANTHROPIC_API_KEY gesetzt)
    summary_generated = False
    if do_summarize and do_transcribe:
        transcript_path = output_dir / "transcript.txt"
        if transcript_path.exists():
            anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
            if anthropic_key:
                summary_generated = summarize_transcript(transcript_path, output_dir, anthropic_key)

    # Step 4: Rename folder with descriptive name
    print(f"\n📁 UMBENENNUNG")
    transcript_path = output_dir / "transcript.txt"
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    new_folder_name = generate_folder_name(recording_name, transcript_path, anthropic_key)

    if new_folder_name != output_dir.name:
        print(f"  Alt: {output_dir.name}")
        print(f"  Neu: {new_folder_name}")
        output_dir = rename_output_folder(output_dir, new_folder_name)
        print(f"  ✅ Umbenannt")
    else:
        print(f"  Name: {output_dir.name}")
        print(f"  ✅ Kein Umbenennen nötig")

    # Step 5: Delete original
    if delete_original and compress:
        print(f"\n🗑️ AUFRÄUMEN")
        print(f"  Lösche Original: {input_path.name}")
        input_path.unlink()
        print(f"  ✅ Gelöscht")

    print(f"\n{'─'*60}")
    print(f"✅ FERTIG: {output_dir}")
    print(f"{'─'*60}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Video-Verarbeitungs-Pipeline: Komprimierung, Transkription, Sprecher-Erkennung, Zusammenfassung"
    )
    parser.add_argument("input", nargs="?", help="Spezifische Video-Datei")
    parser.add_argument("--compress-only", action="store_true",
                        help="Nur komprimieren, keine Transkription")
    parser.add_argument("--transcribe-only", action="store_true",
                        help="Nur transkribieren (bereits komprimierte Dateien)")
    parser.add_argument("--quality", type=int, default=50,
                        help="Komprimierungs-Qualität (0-100, Standard: 50)")
    parser.add_argument("--scale", choices=["1080p", "720p"],
                        help="Auflösung reduzieren (1080p=Full HD, 720p=HD)")
    parser.add_argument("--max-compression", action="store_true",
                        help="Software-Encoder (libx265) für maximale Kompression (langsamer)")
    parser.add_argument("--keep-originals", action="store_true",
                        help="Originale behalten (Standard: löschen)")
    parser.add_argument("--skip-processed", action="store_true",
                        help="Bereits verarbeitete Videos überspringen")
    parser.add_argument("--no-summary", action="store_true",
                        help="Zusammenfassung überspringen")
    parser.add_argument("--interactive", action="store_true",
                        help="Interaktiv Sprecher-Namen eingeben (Standard: automatisch)")
    args = parser.parse_args()

    # Determine what to process
    if args.input:
        videos = [Path(args.input)]
        if not videos[0].exists():
            sys.exit(f"Datei nicht gefunden: {args.input}")
    else:
        videos = find_videos(INPUT_DIR)

    if not videos:
        print("Keine Video-Dateien gefunden.")
        print(f"Lege Videos in: {INPUT_DIR}")
        return

    # Filter already processed
    if args.skip_processed:
        original_count = len(videos)
        videos = [v for v in videos if not is_already_processed(v)]
        skipped = original_count - len(videos)
        if skipped > 0:
            print(f"Überspringe {skipped} bereits verarbeitete Video(s)")

    if not videos:
        print("Alle Videos bereits verarbeitet.")
        return

    print(f"\n{'='*60}")
    print(f"🎥 VIDEO-KONVERTIERUNGS-PIPELINE")
    print(f"{'='*60}")
    print(f"\nGefunden: {len(videos)} Video(s)")
    total_size = 0
    for v in videos:
        size_gb = v.stat().st_size / 1e9
        total_size += size_gb
        print(f"  • {v.name} ({size_gb:.1f} GB)")
    if len(videos) > 1:
        print(f"  ─────────────────────────")
        print(f"  Gesamt: {total_size:.1f} GB")

    compress = not args.transcribe_only
    do_transcribe = not args.compress_only
    do_summarize = not args.no_summary
    delete_original = not args.keep_originals

    success = 0
    failed = 0

    for video in videos:
        if process_video(
            video,
            compress=compress,
            do_transcribe=do_transcribe,
            do_summarize=do_summarize,
            quality=args.quality,
            scale=args.scale,
            max_compression=args.max_compression,
            delete_original=delete_original,
            interactive=args.interactive
        ):
            success += 1
        else:
            failed += 1

    print(f"\n{'='*60}")
    if failed == 0:
        print(f"✅ ABGESCHLOSSEN: {success} Video(s) erfolgreich verarbeitet")
    else:
        print(f"⚠️  ERGEBNIS: {success} erfolgreich, {failed} fehlgeschlagen")
    print(f"{'='*60}")

    # Hinweis für manuelle Zusammenfassung
    if do_transcribe and not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n💡 Tipp: Für Zusammenfassung mit Claude Code:")
        print('   "Fasse das Transkript in converted/<name>/transcript.txt zusammen"')


if __name__ == "__main__":
    main()
