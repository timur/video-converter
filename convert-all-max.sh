#!/bin/bash
# Konvertiert alle Videos in files/ mit maximaler Kompression
# Verwendet: 1080p Skalierung + Software-Encoder (libx265)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# .env laden
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

PYTHON="/opt/homebrew/Cellar/openai-whisper/20250625_3/libexec/bin/python"
INPUT_DIR="$SCRIPT_DIR/files"

echo "============================================================"
echo "🎥 BATCH-KONVERTIERUNG (Maximale Kompression)"
echo "============================================================"
echo ""
echo "Einstellungen:"
echo "  • Skalierung: 1080p (Full HD)"
echo "  • Encoder:    libx265 (Software)"
echo "  • Qualität:   CRF 28"
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

# Bestätigung
read -p "Starten? (j/N) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Jj]$ ]]; then
    echo "Abgebrochen."
    exit 0
fi

echo ""

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

    if "$PYTHON" "$SCRIPT_DIR/convert.py" "$video" --scale 1080p --max-compression; then
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
if [ -d "$SCRIPT_DIR/converted" ]; then
    output_size=$(du -sh "$SCRIPT_DIR/converted" 2>/dev/null | cut -f1)
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
