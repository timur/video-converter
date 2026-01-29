#!/usr/bin/env python3
"""Video processing pipeline: compress, transcribe, and organize meeting recordings."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Configuration
SCRIPT_DIR = Path(__file__).parent
INPUT_DIR = SCRIPT_DIR / "files"
OUTPUT_DIR = SCRIPT_DIR / "converted"
VIDEO_EXTENSIONS = {".mov", ".mp4", ".mkv", ".avi", ".webm", ".m4v"}


def get_recording_name(video_path: Path) -> str:
    """Extract recording name from filename (without extension)."""
    return video_path.stem


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

    print(f"Komprimiere: {input_path.name}")
    print(f"  Modus: {mode_info}")
    if scale:
        print(f"  Skalierung: {scale}")
    print(f"  Ziel: {output_path}")

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"  FEHLER bei der Komprimierung")
        return False

    in_size = input_path.stat().st_size
    out_size = output_path.stat().st_size
    ratio = in_size / out_size
    print(f"  Komprimiert: {in_size/1e9:.2f}GB -> {out_size/1e6:.0f}MB ({ratio:.1f}x Reduktion)")
    return True


def transcribe_video(video_path: Path, output_dir: Path, hf_token: str = None) -> bool:
    """Run transcription with speaker diarization on video."""
    # Import from transcribe module
    sys.path.insert(0, str(SCRIPT_DIR))
    from transcribe import (
        extract_audio, transcribe, diarize, assign_speakers,
        prompt_speaker_names, apply_speaker_names, format_output,
        load_speaker_map
    )

    transcript_path = output_dir / "transcript.txt"

    print(f"Transkribiere: {video_path.name}")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_audio = Path(tmp.name)

    try:
        print("  Audio extrahieren...")
        extract_audio(video_path, tmp_audio)

        print("  Whisper Transkription...")
        result = transcribe(tmp_audio, model_name="turbo", language="de")

        if hf_token:
            print("  Sprecher-Erkennung...")
            speaker_turns = diarize(tmp_audio, hf_token)
            assign_speakers(result["segments"], speaker_turns)

            # Interactive speaker naming
            name_map = prompt_speaker_names(result["segments"])
            if name_map:
                apply_speaker_names(result["segments"], name_map)
                # Save speaker mapping to this recording's directory
                speaker_file = output_dir / "speakers.json"
                speaker_file.write_text(json.dumps(name_map, indent=2, ensure_ascii=False))
                print(f"  Sprecher-Zuordnung gespeichert: {speaker_file}")
        else:
            print("  Kein HF_TOKEN - Sprecher-Erkennung übersprungen")

        # Save transcript
        text = format_output(result["segments"], with_speakers=bool(hf_token))
        transcript_path.write_text(text, encoding="utf-8")
        print(f"  Transkript gespeichert: {transcript_path}")

        return True

    except Exception as e:
        print(f"  FEHLER bei Transkription: {e}")
        return False
    finally:
        tmp_audio.unlink(missing_ok=True)


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
    quality: int = 50,
    scale: str = None,
    max_compression: bool = False,
    delete_original: bool = True
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
    print(f"Verarbeite: {recording_name}")
    print(f"{'='*60}")

    # Step 1: Compress
    if compress:
        if not compress_video(input_path, output_video, quality, scale, max_compression):
            return False

    # Step 2: Transcribe
    if do_transcribe:
        video_to_transcribe = output_video if compress else input_path
        hf_token = os.environ.get("HF_TOKEN")
        if not transcribe_video(video_to_transcribe, output_dir, hf_token):
            return False

    # Step 3: Delete original
    if delete_original and compress:
        print(f"  Original löschen: {input_path.name}")
        input_path.unlink()
        print(f"  Gelöscht.")

    print(f"\n  Fertig: {output_dir}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Video-Verarbeitungs-Pipeline: Komprimierung, Transkription, Sprecher-Erkennung"
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

    print(f"Gefunden: {len(videos)} Video(s)")
    for v in videos:
        size_gb = v.stat().st_size / 1e9
        print(f"  - {v.name} ({size_gb:.1f}GB)")

    compress = not args.transcribe_only
    do_transcribe = not args.compress_only
    delete_original = not args.keep_originals

    success = 0
    failed = 0

    for video in videos:
        if process_video(
            video,
            compress=compress,
            do_transcribe=do_transcribe,
            quality=args.quality,
            scale=args.scale,
            max_compression=args.max_compression,
            delete_original=delete_original
        ):
            success += 1
        else:
            failed += 1

    print(f"\n{'='*60}")
    print(f"Zusammenfassung: {success} erfolgreich, {failed} fehlgeschlagen")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
