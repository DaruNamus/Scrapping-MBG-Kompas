#!/bin/bash
# MBG Sentiment Pipeline — scrape → classify → log
# Usage:
#   ./run.sh                               # Incremental, rule-based classifier
#   ./run.sh --backfill                     # Full backfill, rule-based
#   ./run.sh --classifier local             # Incremental, local LLM
#   ./run.sh --classifier hermes            # Incremental, Hermes LLM
#   ./run.sh --backfill --classifier hermes # Backfill, Hermes LLM

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRAPER="$PROJECT_DIR/scraper.py"
CLASSIFIER_SCRIPT="$PROJECT_DIR/classifier.py"
RULES_CLASSIFIER="$PROJECT_DIR/rules_classifier.py"
LLM_CLASSIFIER="$PROJECT_DIR/llm_classifier.py"
LOG_DIR="$PROJECT_DIR/log"
TMP_DIR="$PROJECT_DIR/.tmp"
ENV_FILE="$PROJECT_DIR/.env"

mkdir -p "$TMP_DIR" "$LOG_DIR"

# ── Parse arguments ──────────────────────────────────────────────────────

BACKFILL=""
CLASSIFIER_MODE="rule"  # rule | local | hermes

for arg in "$@"; do
    case "$arg" in
        --backfill) BACKFILL="--backfill" ;;
        --classifier=*) CLASSIFIER_MODE="${arg#*=}" ;;
        --classifier) ;;
    esac
done

# Detect --classifier <value> pattern
prev=""
for arg in "$@"; do
    if [ "$prev" = "--classifier" ]; then
        CLASSIFIER_MODE="$arg"
    fi
    prev="$arg"
done

# Load .env if exists
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

echo "=== MBG Sentiment Pipeline ==="
echo "Started at: $(date)"
echo "Mode: ${BACKFILL:-incremental} | Classifier: $CLASSIFIER_MODE"
echo ""

# ── Step 1: Scrape ───────────────────────────────────────────────────────

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

# ── Step 2: Classify ─────────────────────────────────────────────────────

echo "--- Step 2: Classify ($CLASSIFIER_MODE) ---"
CLASSIFIED_OUT="$TMP_DIR/classified.json"

case "$CLASSIFIER_MODE" in
    rule)
        python3 "$RULES_CLASSIFIER" "$SCRAPE_OUT" --output "$CLASSIFIED_OUT"
        ;;
    local|hermes)
        python3 "$LLM_CLASSIFIER" "$SCRAPE_OUT" --mode "$CLASSIFIER_MODE" --output "$CLASSIFIED_OUT"
        ;;
    *)
        echo "[ERROR] Unknown classifier mode: $CLASSIFIER_MODE"
        echo "  Valid: rule | local | hermes"
        exit 1
        ;;
esac

echo ""

# ── Step 3: Generate log + summary ───────────────────────────────────────

echo "--- Step 3: Log ---"
python3 "$CLASSIFIER_SCRIPT" "$CLASSIFIED_OUT" --log-dir "$LOG_DIR" 2>&1 | tee "$TMP_DIR/summary.txt"
echo ""

# Cleanup temp files
rm -f "$SCRAPE_OUT"

echo "=== Done ==="
echo "Logs: $LOG_DIR/"
echo "Summary: "
cat "$TMP_DIR/summary.txt"
