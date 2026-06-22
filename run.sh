#!/bin/bash
# MBG Sentiment Pipeline — scrape → classify → log
# Usage:
#   ./run.sh                      # Incremental (latest page only)
#   ./run.sh --backfill           # Full backfill from Jan 1 to today

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRAPER="$PROJECT_DIR/scraper.py"
CLASSIFIER="$PROJECT_DIR/classifier.py"
RULES_CLASSIFIER="$PROJECT_DIR/rules_classifier.py"
LOG_DIR="$PROJECT_DIR/log"
TMP_DIR="$PROJECT_DIR/.tmp"

mkdir -p "$TMP_DIR" "$LOG_DIR"

BACKFILL=""
for arg in "$@"; do
    case "$arg" in
        --backfill) BACKFILL="--backfill" ;;
    esac
done

echo "=== MBG Sentiment Pipeline ==="
echo "Started at: $(date)"
echo "Mode: ${BACKFILL:-incremental}"
echo ""

# Step 1: Scrape
echo "--- Step 1: Scrape ---"
SCRAPE_OUT="$TMP_DIR/scrape_output.json"
python3 "$SCRAPER" $BACKFILL --output "$SCRAPE_OUT" || true
SCRAPE_COUNT=$(python3 -c "import json; data=json.load(open('$SCRAPE_OUT')); print(len(data['articles']))")
echo "Scraped $SCRAPE_COUNT articles"
echo ""

if [ "$SCRAPE_COUNT" -eq 0 ]; then
    echo "No new articles found. Skipping classification."
    rm -f "$SCRAPE_OUT"
    echo "=== Done ==="
    exit 0
fi

# Step 2: Classify (rule-based)
echo "--- Step 2: Classify ---"
CLASSIFIED_OUT="$TMP_DIR/classified.json"
python3 "$RULES_CLASSIFIER" "$SCRAPE_OUT" --output "$CLASSIFIED_OUT"
echo ""

# Step 3: Generate log + summary
echo "--- Step 3: Log ---"
python3 "$CLASSIFIER" "$CLASSIFIED_OUT" --log-dir "$LOG_DIR" 2>&1 | tee "$TMP_DIR/summary.txt"
echo ""

# Cleanup temp files
rm -f "$SCRAPE_OUT"

echo "=== Done ==="
echo "Logs: $LOG_DIR/"
echo "Summary: "
cat "$TMP_DIR/summary.txt"
