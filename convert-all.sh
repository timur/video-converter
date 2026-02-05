#!/bin/bash
# Globales Skript zur Konvertierung aller Videos in files/
# Kann von überall ausgeführt werden

set -e

# Video-Converter Verzeichnis (hier anpassen falls nötig)
VIDEO_CONVERTER_DIR="$HOME/code/MYPROJECTS/video-converter"

cd "$VIDEO_CONVERTER_DIR"

# .env laden
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

PYTHON="/opt/homebrew/Cellar/openai-whisper/20250625_3/libexec/bin/python"
INPUT_DIR="$VIDEO_CONVERTER_DIR/files"

# Standardwerte
MODE="normal"
SCALE=""
KEEP_ORIGINALS=""
SKIP_PROCESSED=""
NO_SUMMARY=""
CONFIRM="yes"

# Hilfe anzeigen
show_help() {
    echo "Verwendung: $(basename "$0") [OPTIONEN]"
    echo ""
    echo "Konvertiert alle Videos im files/ Ordner."
    echo ""
    echo "Modi (wähle einen):"
    echo "  --fast         Schnelle Konvertierung (Hardware-Encoder, Standard-Qualität)"
    echo "  --max          Maximale Kompression (Software-Encoder, 1080p) [langsam]"
    echo "  --transcribe   Nur Transkription (keine Komprimierung)"
    echo ""
    echo "Optionen:"
    echo "  --scale 1080p|720p    Auflösung reduzieren"
    echo "  --keep                Originale behalten (Standard: löschen)"
    echo "  --skip-processed      Bereits verarbeitete überspringen"
    echo "  --no-summary          Keine Zusammenfassung generieren"
    echo "  --yes, -y             Ohne Bestätigung starten"
    echo "  --help, -h            Diese Hilfe anzeigen"
    echo ""
    echo "Beispiele:"
    echo "  $(basename "$0")              # Normale Konvertierung"
    echo "  $(basename "$0") --max        # Maximale Kompression"
    echo "  $(basename "$0") --fast -y    # Schnell, ohne Nachfrage"
    echo ""
    echo "Video-Converter Verzeichnis: $VIDEO_CONVERTER_DIR"
    echo ""
}

# Argumente parsen
while [[ $# -gt 0 ]]; do
    case $1 in
        --fast)
            MODE="fast"
            shift
            ;;
        --max)
            MODE="max"
            SCALE="1080p"
            shift
            ;;
        --transcribe)
            MODE="transcribe"
            shift
            ;;
        --scale)
            SCALE="$2"
            shift 2
            ;;
        --keep)
            KEEP_ORIGINALS="--keep-originals"
            shift
            ;;
        --skip-processed)
            SKIP_PROCESSED="--skip-processed"
            shift
            ;;
        --no-summary)
            NO_SUMMARY="--no-summary"
            shift
            ;;
        --yes|-y)
            CONFIRM="no"
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            echo "Unbekannte Option: $1"
            echo "Verwende --help für Hilfe"
            exit 1
            ;;
    esac
done

# Header
echo "============================================================"
echo "🎥 VIDEO-KONVERTIERUNG"
echo "============================================================"
echo ""

# Modus anzeigen
case $MODE in
    fast)
        echo "Modus: ⚡ Schnell (Hardware-Encoder)"
        EXTRA_ARGS=""
        ;;
    max)
        echo "Modus: 🗜️  Maximale Kompression (Software-Encoder)"
        EXTRA_ARGS="--max-compression"
        ;;
    transcribe)
        echo "Modus: 🎙️  Nur Transkription"
        EXTRA_ARGS="--transcribe-only"
        ;;
    *)
        echo "Modus: 📹 Normal (Hardware-Encoder)"
        EXTRA_ARGS=""
        ;;
esac

if [ -n "$SCALE" ]; then
    echo "Skalierung: $SCALE"
    EXTRA_ARGS="$EXTRA_ARGS --scale $SCALE"
fi

if [ -n "$KEEP_ORIGINALS" ]; then
    echo "Originale: behalten"
fi

if [ -n "$SKIP_PROCESSED" ]; then
    echo "Bereits verarbeitet: überspringen"
fi

echo ""

# Videos finden
shopt -s nullglob nocaseglob
videos=("$INPUT_DIR"/*.{mov,mp4,mkv,avi,webm,m4v})
shopt -u nullglob nocaseglob

if [ ${#videos[@]} -eq 0 ]; then
    echo "❌ Keine Videos in $INPUT_DIR gefunden"
    exit 1
fi

echo "Gefunden: ${#videos[@]} Video(s)"
total_size=0
for video in "${videos[@]}"; do
    size=$(stat -f%z "$video" 2>/dev/null || stat -c%s "$video" 2>/dev/null)
    size_gb=$(echo "scale=2; $size / 1000000000" | bc)
    total_size=$(echo "$total_size + $size_gb" | bc)
    echo "  • $(basename "$video") ($size_gb GB)"
done
echo "  ─────────────────────────"
echo "  Gesamt: $total_size GB"
echo ""

# Bestätigung (außer bei --yes)
if [ "$CONFIRM" = "yes" ]; then
    read -p "Starten? (j/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Jj]$ ]]; then
        echo "Abgebrochen."
        exit 0
    fi
    echo ""
fi

# Zähler
success=0
failed=0
start_time=$(date +%s)

# Videos verarbeiten
for video in "${videos[@]}"; do
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📹 $(basename "$video")"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # shellcheck disable=SC2086
    if "$PYTHON" "$VIDEO_CONVERTER_DIR/convert.py" "$video" $EXTRA_ARGS $KEEP_ORIGINALS $SKIP_PROCESSED $NO_SUMMARY; then
        ((success++))
    else
        ((failed++))
        echo "❌ Fehler bei: $(basename "$video")"
    fi
done

# Zusammenfassung
end_time=$(date +%s)
duration=$((end_time - start_time))
duration_min=$((duration / 60))
duration_sec=$((duration % 60))

echo ""
echo "============================================================"
echo "📊 ZUSAMMENFASSUNG"
echo "============================================================"
echo ""
echo "  ✅ Erfolgreich: $success"
if [ $failed -gt 0 ]; then
    echo "  ❌ Fehlgeschlagen: $failed"
fi
echo "  ⏱️  Dauer: ${duration_min}m ${duration_sec}s"
echo ""

# Speicherplatz-Ersparnis anzeigen
if [ -d "$VIDEO_CONVERTER_DIR/converted" ]; then
    output_size=$(du -sh "$VIDEO_CONVERTER_DIR/converted" 2>/dev/null | cut -f1)
    echo "  📁 Output-Größe: $output_size"
fi

echo ""
echo "============================================================"
if [ $failed -eq 0 ]; then
    echo "✅ Alle Videos erfolgreich konvertiert!"
else
    echo "⚠️  $failed Video(s) fehlgeschlagen"
fi
echo "============================================================"
