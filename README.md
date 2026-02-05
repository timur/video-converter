# Video Converter Pipeline

Automatisierte Pipeline für Meeting-Aufnahmen: **Komprimierung → Transkription → Sprecher-Erkennung**

## Features

- **Video-Komprimierung** mit H.265 (Hardware-beschleunigt auf Apple Silicon)
- **Whisper Transkription** (OpenAI Whisper, deutsch)
- **Sprecher-Diarisierung** mit pyannote.audio
- **Automatische Ordnerstruktur** für jede Aufnahme
- **Optionale Skalierung** auf Full HD / HD
- **Detaillierte Progress-Anzeige** im Terminal

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
| `--interactive` | Sprecher-Namen interaktiv eingeben |
| `--no-summary` | Zusammenfassung überspringen |

## Output-Struktur

Nach der Verarbeitung wird der Ordner automatisch umbenannt:

```
converted/
└── 2026-01-28_Dienstag_12-18_Content-Factory-Meeting/
    ├── video.mp4           # Komprimiertes Video
    ├── transcript.txt      # Transkript mit Sprecher-Labels
    └── speakers.json       # Sprecher-Zuordnung
```

### Ordner-Namensformat

Der Ordnername enthält:
- **Datum**: `2026-01-28`
- **Wochentag**: `Montag`, `Dienstag`, etc.
- **Uhrzeit**: `12-18` (HH-MM)
- **Titel**: Automatisch aus dem Transkript extrahiert (mit Claude API) oder "Meeting"

Beispiele:
- `2026-01-28_Dienstag_09-47_Projektplanung`
- `2026-01-28_Dienstag_11-16_Sprint-Review`
- `2026-01-28_Dienstag_12-18_Meeting`

## Erwartete Kompression

| Original | Mit HW-Encoder | Mit --scale 1080p --max-compression |
|----------|---------------|-------------------------------------|
| 1.9 GB   | ~400 MB (4.7x) | ~100-150 MB (~15x) |
| 5.8 GB   | ~600 MB (10x) | ~200-300 MB (~25x) |

## Skripte

### Haupt-Pipeline

| Skript | Beschreibung |
|--------|-------------|
| `run-pipeline.sh` | Wrapper-Skript, lädt `.env` und startet Pipeline |
| `convert.py` | Haupt-Pipeline: Komprimierung + Transkription |

### Einzelne Tools

| Skript | Beschreibung |
|--------|-------------|
| `transcribe.py` | Standalone Transkription mit Whisper |
| `rename_speakers.py` | Sprecher umbenennen in bestehendem Transkript |
| `summarize.py` | Zusammenfassung mit Claude API generieren |
| `run.sh` | Standalone Transkription ohne Komprimierung |

### Sprecher umbenennen

```bash
# Interaktiv
python rename_speakers.py converted/meeting/transcript.txt

# Direkte Zuordnung
python rename_speakers.py transcript.txt -m "Speaker-1" "Reza" -m "Speaker-2" "Florian"
```

### Zusammenfassung generieren

```bash
# Mit Claude API (ANTHROPIC_API_KEY muss gesetzt sein)
python summarize.py converted/meeting/transcript.txt
```

## Standalone Transkription

Für einzelne Dateien ohne Komprimierung:

```bash
./run.sh "files/video.mov"
./run.sh "files/video.mov" --no-diarize  # Ohne Sprecher-Erkennung
```

## Terminal-Ausgabe

Die Pipeline zeigt detaillierte Progress-Informationen:

```
============================================================
🎥 VIDEO-KONVERTIERUNGS-PIPELINE
============================================================

Gefunden: 1 Video(s)
  • Bildschirmaufnahme 2026-01-29 um 12.54.41.mov (1.8 GB)

============================================================
🎬 VERARBEITE: Bildschirmaufnahme 2026-01-29 um 12.54.41
============================================================
  Schritte: Komprimierung → Transkription → Sprecher-Erkennung → Umbenennung → Aufräumen

📹 KOMPRIMIERUNG
  Eingabe:    Bildschirmaufnahme 2026-01-29 um 12.54.41.mov
  Dauer:      32:10
  Auflösung:  3024x1964
  Größe:      1.75 GB
  Modus:      Hardware (VideoToolbox, q=50)
  ⏳ Starte ffmpeg...
  ✅ Komprimierung abgeschlossen
     1.75 GB → 312 MB (5.6x Reduktion)

🎙️ TRANSKRIPTION
  Eingabe: video.mp4
  ⏳ Audio extrahieren...
  ✅ Audio extrahiert
  ⏳ Whisper Transkription (Modell: turbo, Sprache: de)...
  [100.0%] 598s elapsed — 1928s-1928s
  ✅ Transkription abgeschlossen (847 Segmente)
  ⏳ Sprecher-Diarisierung (pyannote)...
  ✅ Sprecher-Erkennung abgeschlossen
     Sprecher: Speaker-1, Speaker-2, Speaker-3
  📝 Transkript gespeichert: transcript.txt

📁 UMBENENNUNG
  Alt: Bildschirmaufnahme 2026-01-29 um 12.54.41
  Neu: 2026-01-29_Mittwoch_12-54_Content-Factory-Onboarding
  ✅ Umbenannt

🗑️ AUFRÄUMEN
  Lösche Original: Bildschirmaufnahme 2026-01-29 um 12.54.41.mov
  ✅ Gelöscht

────────────────────────────────────────────────────────────
✅ FERTIG: converted/2026-01-29_Mittwoch_12-54_Content-Factory-Onboarding
────────────────────────────────────────────────────────────

============================================================
✅ ABGESCHLOSSEN: 1 Video(s) erfolgreich verarbeitet
============================================================
```

## Troubleshooting

### "Kein HF_TOKEN"
Sprecher-Erkennung benötigt einen HuggingFace Token. In `.env` eintragen:
```
HF_TOKEN=hf_xxxxxxxxxxxxx
```

### Langsame Komprimierung
Mit `--max-compression` wird der Software-Encoder verwendet (langsamer, aber kleinere Dateien). Ohne diese Option wird der Hardware-Encoder verwendet (schneller).

### Sprecher falsch zugeordnet
Nach der Verarbeitung können Sprecher umbenannt werden:
```bash
python rename_speakers.py converted/meeting/transcript.txt
```

## Umgebungsvariablen

| Variable | Beschreibung |
|----------|-------------|
| `HF_TOKEN` | HuggingFace Token für Sprecher-Diarisierung |
| `ANTHROPIC_API_KEY` | Anthropic API Key für Zusammenfassungen (optional) |

## Lizenz

Private Nutzung
