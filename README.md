# Video Converter Pipeline

Automatisierte Pipeline für Meeting-Aufnahmen: **Komprimierung → Transkription → Sprecher-Erkennung**

## Features

- **Video-Komprimierung** mit H.265 (Hardware-beschleunigt auf Apple Silicon)
- **Whisper Transkription** (OpenAI Whisper, deutsch)
- **Sprecher-Diarisierung** mit pyannote.audio
- **Automatische Ordnerstruktur** für jede Aufnahme
- **Optionale Skalierung** auf Full HD / HD

## Installation

### Voraussetzungen

- Python 3.10+
- ffmpeg (`brew install ffmpeg`)
- HuggingFace Account für Sprecher-Erkennung

### Setup

1. `.env` Datei erstellen:
```bash
cp .env.example .env
# HF_TOKEN eintragen (von huggingface.co)
```

2. Dependencies installieren:
```bash
pip install -r requirements.txt
```

## Verwendung

### Vollständige Pipeline

```bash
# Alle Videos in files/ verarbeiten
./run-pipeline.sh

# Einzelne Datei verarbeiten
./run-pipeline.sh "files/MeinVideo.mov"
```

### Nur Komprimierung

```bash
./run-pipeline.sh --compress-only
```

### Nur Transkription

```bash
./run-pipeline.sh --transcribe-only "converted/MeinVideo/video.mp4"
```

### Komprimierungsoptionen

| Option | Beschreibung |
|--------|-------------|
| `--scale 1080p` | Auf Full HD (1920x1080) skalieren |
| `--scale 720p` | Auf HD (1280x720) skalieren |
| `--max-compression` | Software-Encoder (libx265) für maximale Kompression |
| `--quality N` | Hardware-Encoder Qualität (0-100, Standard: 50) |

#### Beispiele

```bash
# Kleinste Dateien (Full HD + Software-Encoder)
./run-pipeline.sh --scale 1080p --max-compression

# Schnelle HW-Kompression auf Full HD
./run-pipeline.sh --scale 1080p

# Höhere Qualität (größere Dateien)
./run-pipeline.sh --quality 30
```

### Weitere Optionen

| Option | Beschreibung |
|--------|-------------|
| `--keep-originals` | Original-Dateien behalten (Standard: löschen) |
| `--skip-processed` | Bereits verarbeitete Videos überspringen |

## Output-Struktur

```
converted/
└── Bildschirmaufnahme 2026-01-28 um 12.18.36/
    ├── video.mp4           # Komprimiertes Video
    ├── transcript.txt      # Transkript mit Sprecher-Labels
    └── speakers.json       # Sprecher-Zuordnung (falls diarisiert)
```

## Erwartete Kompression

| Original | Mit HW-Encoder | Mit --scale 1080p --max-compression |
|----------|---------------|-------------------------------------|
| 1.9 GB   | ~400 MB (4.7x) | ~100-150 MB (~15x) |
| 5.8 GB   | ~600 MB (10x) | ~200-300 MB (~25x) |

## Standalone Transkription

Für einzelne Dateien ohne Komprimierung:

```bash
./run.sh "files/video.mov"
./run.sh "files/video.mov" --no-diarize  # Ohne Sprecher-Erkennung
```

## Troubleshooting

### "Kein HF_TOKEN"
Sprecher-Erkennung benötigt einen HuggingFace Token. In `.env` eintragen:
```
HF_TOKEN=hf_xxxxxxxxxxxxx
```

### Langsame Komprimierung
Mit `--max-compression` wird der Software-Encoder verwendet (langsamer, aber kleinere Dateien). Ohne diese Option wird der Hardware-Encoder verwendet (schneller).

## Lizenz

Private Nutzung
