#!/usr/bin/env python3
"""Extract audio from video files and transcribe using Whisper with speaker diarization."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import torch
import whisper
from pyannote.audio import Pipeline


def extract_audio(video_path: Path, audio_path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-i", str(video_path), "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", str(audio_path), "-y"],
        check=True,
        capture_output=True,
    )


def get_audio_duration(audio_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(audio_path)],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def diarize(audio_path: Path, hf_token: str) -> list[tuple[float, float, str]]:
    print("Running speaker diarization...")
    # pyannote checkpoints require weights_only=False with PyTorch 2.6+
    _orig_load = torch.load
    torch.load = lambda *a, **kw: _orig_load(*a, **{**kw, "weights_only": False})
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )
    torch.load = _orig_load
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    pipeline.to(torch.device(device))

    result = pipeline(str(audio_path))

    turns = []
    annotation = result.speaker_diarization if hasattr(result, 'speaker_diarization') else result
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        turns.append((turn.start, turn.end, speaker))
    print(f"  Found {len(set(t[2] for t in turns))} speakers")
    return turns


def assign_speakers(segments: list[dict], speaker_turns: list[tuple[float, float, str]]) -> list[dict]:
    for seg in segments:
        seg_mid = (seg["start"] + seg["end"]) / 2
        best_speaker = "Unknown"
        for start, end, speaker in speaker_turns:
            if start <= seg_mid <= end:
                best_speaker = speaker
                break
        seg["speaker"] = best_speaker
    return segments


def transcribe(audio_path: Path, model_name: str, language: str) -> dict:
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using device: {device}")

    model = whisper.load_model(model_name, device=device)

    duration = get_audio_duration(audio_path)
    print(f"Audio duration: {duration / 60:.1f} minutes")

    start = time.time()

    result = model.transcribe(
        str(audio_path),
        language=language,
        verbose=False,
    )

    for seg in result["segments"]:
        pct = min(100, seg["end"] / duration * 100)
        elapsed = time.time() - start
        print(f"\r  [{pct:5.1f}%] {elapsed:.0f}s elapsed — {seg['start']:.0f}s-{seg['end']:.0f}s", end="", flush=True)

    print()
    return result


SPEAKER_MAP_FILE = Path(__file__).parent / "speakers.json"


def load_speaker_map() -> dict[str, str]:
    if SPEAKER_MAP_FILE.exists():
        return json.loads(SPEAKER_MAP_FILE.read_text())
    return {}


def save_speaker_map(name_map: dict[str, str]) -> None:
    existing = load_speaker_map()
    existing.update(name_map)
    SPEAKER_MAP_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    print(f"Speaker names saved to {SPEAKER_MAP_FILE}")


def collect_speaker_samples(segments: list[dict]) -> dict[str, str]:
    """Collect the first quote from each speaker for identification."""
    samples = {}
    for seg in segments:
        speaker = seg.get("speaker", "Unknown")
        if speaker not in samples:
            text = seg["text"].strip()
            if len(text) > 10:
                samples[speaker] = text[:120]
    return samples


def prompt_speaker_names(segments: list[dict]) -> dict[str, str]:
    """Show speaker samples and ask user to assign real names."""
    samples = collect_speaker_samples(segments)
    if not samples:
        return {}

    saved = load_speaker_map()

    print("\n--- Speaker Identification ---")
    print("Enter a name for each speaker (or press Enter to keep as-is).")
    if saved:
        print(f"Known names from previous runs: {', '.join(saved.values())}")
    print()

    name_map = {}
    for speaker, sample in sorted(samples.items()):
        default = saved.get(speaker, "")
        hint = f" [{default}]" if default else ""
        print(f'  {speaker}: "{sample}..."')
        try:
            name = input(f"  Name for {speaker}{hint}: ").strip()
        except EOFError:
            return name_map
        if name:
            name_map[speaker] = name
        elif default:
            name_map[speaker] = default

    return name_map


def apply_speaker_names(segments: list[dict], name_map: dict[str, str]) -> None:
    for seg in segments:
        speaker = seg.get("speaker", "Unknown")
        if speaker in name_map:
            seg["speaker"] = name_map[speaker]


def format_output(segments: list[dict], with_speakers: bool) -> str:
    lines = []
    current_speaker = None
    for seg in segments:
        if with_speakers:
            speaker = seg.get("speaker", "Unknown")
            if speaker != current_speaker:
                current_speaker = speaker
                lines.append(f"\n[{speaker}]")
            lines.append(seg["text"].strip())
        else:
            lines.append(seg["text"])

    if with_speakers:
        return "\n".join(lines).strip()
    return "".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Transcribe audio from video files")
    parser.add_argument("input", help="Path to video or audio file")
    parser.add_argument("--model", default="turbo", help="Whisper model (default: turbo)")
    parser.add_argument("--language", default="de", help="Language code (default: de)")
    parser.add_argument("--output", help="Output text file path")
    parser.add_argument("--hf-token", default=os.environ.get("HF_TOKEN"),
                        help="HuggingFace token for speaker diarization (or set HF_TOKEN env var)")
    parser.add_argument("--no-diarize", action="store_true", help="Skip speaker diarization")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        sys.exit(f"File not found: {input_path}")

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found. Install with: brew install ffmpeg")

    do_diarize = not args.no_diarize and args.hf_token is not None
    if not args.no_diarize and args.hf_token is None:
        print("No HF token provided, skipping speaker diarization. Use --hf-token or set HF_TOKEN.")

    output_path = Path(args.output) if args.output else input_path.with_suffix(".txt")
    video_extensions = {".mov", ".mp4", ".mkv", ".avi", ".webm", ".m4v"}

    if input_path.suffix.lower() in video_extensions:
        print(f"Extracting audio from {input_path.name}...")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            extract_audio(input_path, tmp_path)
            print(f"Transcribing with model '{args.model}' (language: {args.language})...")
            result = transcribe(tmp_path, args.model, args.language)
            if do_diarize:
                speaker_turns = diarize(tmp_path, args.hf_token)
                assign_speakers(result["segments"], speaker_turns)
        finally:
            tmp_path.unlink(missing_ok=True)
    else:
        print(f"Transcribing {input_path.name} with model '{args.model}' (language: {args.language})...")
        result = transcribe(input_path, args.model, args.language)
        if do_diarize:
            speaker_turns = diarize(input_path, args.hf_token)
            assign_speakers(result["segments"], speaker_turns)

    if do_diarize:
        name_map = prompt_speaker_names(result["segments"])
        if name_map:
            apply_speaker_names(result["segments"], name_map)
            save_speaker_map(name_map)

    text = format_output(result["segments"], with_speakers=do_diarize)
    output_path.write_text(text, encoding="utf-8")
    print(f"Transcript saved to {output_path}")


if __name__ == "__main__":
    main()
