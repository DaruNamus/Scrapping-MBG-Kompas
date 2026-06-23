# Configuration

Semua konfigurasi pipeline — dari environment variables sampai parameter hardcoded di script.

## 1. Scraper Configuration

Parameters hardcoded di `scraper.py`:

| Parameter | Location | Default | Description |
|---|---|---|---|
| `TAGS` | Line 27-30 | `[{"slug": "MBG", ...}, {"slug": "makan-bergizi-gratis", ...}]` | Kompas tag slugs to scrape |
| `DATE_START` | Line 35 | `2026-01-01` | Earliest article date (backfill) |
| `DATE_END` | Line 36 | `2026-06-22` | Latest article date (backfill) |
| `USER_AGENT` | Line 19-22 | Chrome UA string | HTTP User-Agent header |
| `BODY_MAX_CHARS` | `fetch_article_body()` | 2000 | Max article body length |
| `REQUEST_DELAY` | Scrape tag pages | 0.5s | Delay between page fetches |
| `BODY_FETCH_DELAY` | Body fetcher | 0.3s | Delay between body fetches |

### Adjusting Date Range

Edit directly in `scraper.py`:

```python
DATE_START = date(2026, 1, 1)     # Earliest article
DATE_END   = date(2026, 12, 31)   # Latest article
```

### Adding Tag Sources

```python
TAGS = [
    {"slug": "MBG",                "label": "MBG"},
    {"slug": "makan-bergizi-gratis", "label": "makan-bergizi-gratis"},
    # Add more:
    {"slug": "gizi",               "label": "gizi"},
]
```

---

## 2. Environment Variables (`.env`)

Copy template dan edit:

```bash
cp .env.example .env
```

### 2a. HuggingFace Pipeline (`--classifier local-model`)

| Variable | Default | Description |
|---|---|---|
| `MBG_HF_MODEL` | `nahiar/sentiment-analysis-v2` | Model name from HuggingFace Hub |
| `MBG_HF_DEVICE` | `cuda` | `cuda` (GPU) or `cpu` |
| `MBG_HF_BATCH_SIZE` | `8` | Batch size for inference. Lower jika OOM (VRAM) |

### 2b. API-Based LLM (`--classifier local`)

| Variable | Default | Description |
|---|---|---|
| `MBG_LLM_URL` | `http://localhost:8000/v1/chat/completions` | Endpoint. Auto-detect: vLLM `/v1/chat/completions`, Ollama `/api/generate`, LM Studio `/v1/chat/completions` |
| `MBG_LLM_MODEL` | `Qwen/Qwen3.5-35B-A3B-GPTQ-Int4` | Model name used by the LLM server |
| `MBG_LLM_TIMEOUT` | `120` | Request timeout in seconds |
| `MBG_LLM_MAX_TOKENS` | `8192` | Max output tokens. Increase for reasoning models |

### 2c. Hermes (`--classifier hermes`)

| Variable | Default | Description |
|---|---|---|
| `MBG_HERMES_PROFILE` | *(empty)* | Hermes profile name. Empty = default profile |

### Full `.env.example`

```bash
# ── HuggingFace Pipeline (local-model mode) ────────────
MBG_HF_MODEL=nahiar/sentiment-analysis-v2
MBG_HF_DEVICE=cuda
MBG_HF_BATCH_SIZE=8

# ── API-based LLM (local mode) ─────────────────────────
# vLLM:
#   MBG_LLM_URL=http://localhost:8000/v1/chat/completions
# Ollama:
#   MBG_LLM_URL=http://localhost:11434/api/generate
#   MBG_LLM_MODEL=llama3.2
# LM Studio:
#   MBG_LLM_URL=http://localhost:1234/v1/chat/completions
MBG_LLM_URL=http://localhost:8000/v1/chat/completions
MBG_LLM_MODEL=Qwen/Qwen3.5-35B-A3B-GPTQ-Int4
MBG_LLM_TIMEOUT=120
MBG_LLM_MAX_TOKENS=8192

# ── Hermes ──────────────────────────────────────────────
# MBG_HERMES_PROFILE=my-profile
```

---

## 3. Run-time CLI Flags

### `scraper.py`

| Flag | Description |
|---|---|
| `--backfill` | Scrape from `DATE_START` to `DATE_END` |
| `--output <path>` | Output JSON path (default: auto temp) |

### `rules_classifier.py`

| Flag | Description |
|---|---|
| `--output <path>` | Output JSON path |

### `llm_classifier.py`

| Flag | Description |
|---|---|
| `--mode` | `local`, `local-model`, or `hermes` |
| `--output <path>` | Output JSON path |

### `classifier.py`

| Flag | Description |
|---|---|
| `--log-dir <dir>` | Output directory for daily logs |
| `--summary` | Print Telegram summary only (no file writes) |
| `--stdout` | Print formatted log to stdout (no file writes) |

### `run.sh`

| Flag | Description |
|---|---|
| `--backfill` | Full backfill mode |
| `--classifier <mode>` | `rule` (default), `local`, `local-model`, or `hermes` |
