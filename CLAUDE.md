# CLAUDE.md - Projektkontext für Claude Code

## Projektübersicht

Dies ist eine Video-Konvertierungs-Pipeline für Meeting-Aufnahmen. Die Pipeline komprimiert Videos, transkribiert sie mit Whisper und erkennt Sprecher mit pyannote.audio.

## Architektur

```
video-converter/
├── convert.py          # Haupt-Pipeline (orchestriert alles)
├── convert-all.sh      # Batch-Verarbeitung aller Videos (auch global via ~/bin/convert-all)
├── transcribe.py       # Whisper + pyannote Transkription
├── rename_speakers.py  # Sprecher umbenennen Tool
├── summarize.py        # Claude API Zusammenfassung
├── run-pipeline.sh     # Wrapper (lädt .env)
├── run.sh              # Standalone Transkription
├── files/              # Input-Ordner für Videos
└── converted/          # Output-Ordner
    └── <video-name>/
        ├── video.mp4       # Komprimiertes Video
        ├── transcript.txt  # Transkript mit Timestamps
        └── speakers.json   # Sprecher-Zuordnung
```

## Technologie-Stack

- **Python 3.14** (via homebrew whisper installation)
- **ffmpeg** für Video/Audio-Verarbeitung
- **OpenAI Whisper** für Transkription (Modell: turbo)
- **pyannote.audio** für Sprecher-Diarisierung
- **Apple VideoToolbox** für Hardware-beschleunigte H.265 Komprimierung
- **MPS** (Metal Performance Shaders) für GPU-Beschleunigung auf Apple Silicon

## Wichtige Pfade

- Python Interpreter: `/opt/homebrew/Cellar/openai-whisper/20250625_3/libexec/bin/python`
- Input-Verzeichnis: `files/`
- Output-Verzeichnis: `converted/`
- Umgebungsvariablen: `.env` (HF_TOKEN, ANTHROPIC_API_KEY)

## Typische Aufgaben

### Video verarbeiten
```bash
./run-pipeline.sh "files/video.mov"
```

### Sprecher umbenennen
Nach der Verarbeitung können Sprecher-Namen angepasst werden:
```bash
python rename_speakers.py converted/<name>/transcript.txt -m "Speaker-1" "Reza" -m "Speaker-2" "Timur"
```

Oder manuell:
1. `speakers.json` bearbeiten
2. `transcript.txt` mit Suchen/Ersetzen anpassen

### Zusammenfassung erstellen
```bash
# Mit Claude API
python summarize.py converted/<name>/transcript.txt

# Oder in Claude Code direkt:
# "Fasse das Transkript in converted/<name>/transcript.txt zusammen"
```

## Transkript-Format

```
[00:00 - 00:01] [Sprecher-Name]
Text des Segments

[00:01 - 00:03]
Fortsetzung (gleicher Sprecher)

[00:03 - 00:05] [Anderer-Sprecher]
Neuer Sprecher
```

## Sprecher-Zuordnung (speakers.json)

```json
{
  "SPEAKER_02": "Reza",
  "SPEAKER_00": "Timur",
  "SPEAKER_01": "Florian"
}
```

Die Keys sind die internen pyannote IDs, die Values sind die angezeigten Namen.

## Häufige Befehle

```bash
# Pipeline starten
./run-pipeline.sh

# Alle Videos auf einmal (global verfügbar via ~/bin/convert-all)
convert-all --yes
convert-all --max -y              # Maximale Kompression
convert-all --no-diarize --yes    # Offline (ohne Sprecher-Erkennung)

# Mit Optionen
./run-pipeline.sh --scale 1080p --keep-originals

# Ohne Sprecher-Erkennung (Offline-Modus)
./run-pipeline.sh --no-diarize "files/video.mov"

# Sprecher-Erkennung nachträglich nachholen (einzeln)
./run-pipeline.sh --diarize-only "converted/2026-02-20_Donnerstag_14-00_Meeting"

# Sprecher-Erkennung für ALLE Ordner ohne speakers.json nachholen
convert-all --diarize-only

# Nur Transkription (ohne Komprimierung)
./run-pipeline.sh --transcribe-only "converted/video/video.mp4"

# Unterbrochene Verarbeitung fortsetzen
./run-pipeline.sh --resume "converted/Bildschirmaufnahme 2026-02-10 um 14.59.06"

# Status prüfen
ls -la converted/*/
```

## Resume-Logik

Die Pipeline kann an jeder Stelle unterbrochen und wieder aufgenommen werden. Jeder Schritt prüft vor Ausführung, ob sein Output bereits existiert und valide ist:

- **Komprimierung**: `video.mp4` vorhanden + ffprobe-Dauer > 0 → Skip
- **Transkription**: `transcript.txt` vorhanden + ≥100 Bytes → Skip
- **Zusammenfassung**: `summary.txt`/`.md` vorhanden + nicht leer → Skip
- **Umbenennung**: Idempotent (vergleicht aktuellen mit Ziel-Namen)
- **Cleanup**: Skip wenn Original bereits gelöscht

Zwei Wege zur Wiederaufnahme:
1. Originaldatei erneut angeben: `./run-pipeline.sh "files/video.mov"` — findet existierenden Output automatisch
2. `--resume` auf Output-Ordner: `./run-pipeline.sh --resume "converted/..."` — setzt `compress=False`, `delete_original=False`

## Offline-/Online-Hinweise

- **ffmpeg + Whisper** laufen komplett offline
- **pyannote.audio** (Sprecher-Diarisierung) braucht beim ersten Aufruf Internet (HuggingFace Model-Download), danach gecached
- **Claude API** (Zusammenfassung + Titel) braucht Internet
- **Offline-Modus**: `--no-diarize` überspringt die Sprecher-Erkennung → Pipeline läuft ohne Internet
- **Nachholen**: Diarisierung kann später einzeln nachgeholt werden: `./run-pipeline.sh --diarize-only "converted/..."`

## Fehlerbehandlung

- **Kein HF_TOKEN**: Sprecher-Erkennung wird übersprungen
- **Kein ANTHROPIC_API_KEY**: Zusammenfassung wird übersprungen
- **ffmpeg fehlt**: `brew install ffmpeg`

## Performance-Hinweise

- Hardware-Encoder (Standard): ~3-4x Echtzeit
- Software-Encoder (--max-compression): ~0.5x Echtzeit, aber ~50% kleinere Dateien
- Whisper turbo auf MPS: ~1x Echtzeit
- pyannote Diarisierung: ~0.5x Echtzeit

## Anmerkungen für Claude

- Die Pipeline ist für deutsche Meeting-Aufnahmen optimiert
- Sprecher werden automatisch als Speaker-1, Speaker-2 etc. benannt
- Nach der Verarbeitung sollte der User gefragt werden, ob die Sprecher umbenannt werden sollen
- Transkripte können sehr lang sein (>50KB für 30min Meetings)
- Bei Zusammenfassungen auf Token-Limits achten
