# MBG Scraper — Sentiment Analysis Pipeline

Scrape artikel Kompas.com tentang program **Makan Bergizi Gratis (MBG)** dari dua tag source, klasifikasi sentimen, dan output ke daily log markdown.

Tersedia **4 classifier mode** yang bisa dipilih sesuai kebutuhan:
- **`rule`** — berbasis keyword (cepat, offline, tanpa GPU)
- **`local`** — LLM via API (vLLM, Ollama, LM Studio) — configurable endpoint + model
- **`local-model`** — HuggingFace pipeline langsung via PyTorch (GPU/CPU)
- **`hermes`** — via Hermes agent CLI

---

## Pipeline Diagram

```mermaid
graph TD
    subgraph Input["📥 Input Sources"]
        A1["kompas.com/tag/MBG"]
        A2["kompas.com/tag/makan-bergizi-gratis"]
    end

    subgraph Step1["1️⃣ Scrape (scraper.py)"]
        B["scrape_tag_page()"]
        B1["Parse HTML articleItem<br>→ title, url, date"]
        B2["fetch_article_body()<br>→ body (capped 2000 chars, JS-stripped)"]
        B3["Deduplicate across tags<br>→ known_urls.json"]
        B --> B1
        B1 --> B2
        B2 --> B3
    end

    subgraph Step2["2️⃣ Classify"]
        direction LR
        C1["rules_classifier.py<br>keyword matching"]
        C2["llm_classifier.py --mode local<br>LLM API (vLLM/Ollama)"]
        C3["llm_classifier.py --mode local-model<br>HF pipeline (PyTorch)"]
        C4["llm_classifier.py --mode hermes<br>Hermes agent CLI"]
    end

    subgraph Step3["3️⃣ Format Log (classifier.py)"]
        D["build_log_entry()"]
        D1["Group by date"]
        D2["Sort: negatif → netral → positif"]
        D3["Write daily markdown<br>→ log/YYYY-MM-DD.md"]
        D4["Generate Telegram summary<br>→ log/_summary.txt"]
        D --> D1
        D1 --> D2
        D2 --> D3
        D2 --> D4
    end

    subgraph Output["📤 Output Artifacts"]
        E1["log/YYYY-MM-DD.md<br>title + body + sentiment per artikel"]
        E2["log/_summary.txt<br>Headlines + sentiment counts"]
        E3["known_urls.json<br>URL cache for incremental runs"]
    end

    A1 --> B
    A2 --> B
    B3 --> Step2
    Step2 --> D
    D3 --> E1
    D4 --> E2
    B3 -.-> E3
```

---

## Project Structure

```
mbg-scraper/
├── scraper.py              # Scraper — fetch tag pages + article bodies
├── rules_classifier.py     # Rule-based sentiment classifier (default)
├── llm_classifier.py       # LLM-based classifier (local / Hermes modes)
├── classifier.py           # Log formatter — markdown output + summary
├── run.sh                  # Pipeline orchestrator
├── requirements.txt        # Python dependencies
├── .env.example            # LLM configuration template
├── README.md               # This file
│
├── log/                    # Daily sentiment log output
│   ├── 2026-06-22.md
│   ├── 2026-06-21.md
│   ├── _summary.txt
│   └── ...
│
├── state.json              # Last run timestamp
├── known_urls.json         # Known URL cache (deduplication)
│
├── .tmp/                   # Temporary pipeline artifacts
│   ├── scrape_output.json
│   ├── classified.json
│   └── summary.txt
│
└── scripts/                # Reserved for additional scripts
```

---

## File Descriptions

### `scraper.py` — Scraper

Scrapes Kompas.com tag pages and fetches article body text.

| Function | Description |
|----------|-------------|
| `scrape_tag_page(tag_slug, page)` | Parse HTML article listing → `[{title, url, date, snippet}]` |
| `fetch_article_body(url)` | Fetch individual article page, extract `<div class="read__content">` text (2000 chars max); strips Kompas.id JS recommender widget |
| `parse_article_date(date_str)` | Parse Indonesian date format (`"22 Juni 2026"`) → `date` object |
| `extract_date_from_url(url)` | Fallback: extract `YYYY/MM/DD` from article URL |
| `get_max_pages(tag_slug, html)` | Find pagination count from first page (backfill mode) |
| `load_state()` / `save_state()` | Persist last run timestamp |
| `load_known_urls()` / `save_known_urls()` | Persist URL cache for incremental dedup |

**CLI:**
```bash
# Incremental (latest page only)
python3 scraper.py --output articles.json

# Full backfill from Jan 1 to today
python3 scraper.py --backfill --output articles.json
```

**Output:** JSON array per artikel — `{title, url, date, date_str, snippet, source_tag, body}`

---

### `rules_classifier.py` — Sentinel Classifier

Rule-based sentiment classification using Indonesian keyword lexicons tailored for MBG context.

Three keyword lists:
- **`POSITIF_WORDS`** — `berhasil`, `dukung`, `apresiasi`, `manfaat`, `tepat sasaran`, dll.
- **`NEGATIF_WORDS`** — `korupsi`, `gagal`, `kritik`, `demo`, `polemik`, `kendala`, dll.
- **`NETRAL_WORDS`** — `rencana`, `kebijakan`, `program`, `anggaran`, `data`, dll.

| Function | Description |
|----------|-------------|
| `classify_article(title, snippet, body)` | Count keyword matches per category → return `"positif"` / `"netral"` / `"negatif"` |

Heuristic:
- `neg_score > pos_score` AND `neg_score >= 2` → **negatif**
- `pos_score > neg_score` AND `pos_score >= 2` → **positif**
- Otherwise → **netral**

**CLI:**
```bash
python3 rules_classifier.py articles.json --output classified.json
```

**Output:** Same JSON with added `sentiment` field per article.

---

### `llm_classifier.py` — LLM Classifier

Classifies articles using an LLM instead of keyword rules. Three modes:

| Mode | Description | Configuration |
|------|-------------|---------------|
| `local` | Calls any OpenAI-compatible LLM API (vLLM, Ollama, LM Studio) | `MBG_LLM_URL`, `MBG_LLM_MODEL` env vars |
| `local-model` | Runs HuggingFace pipeline directly via PyTorch (GPU/CPU) | `MBG_HF_MODEL`, `MBG_HF_DEVICE` env vars |
| `hermes` | Calls Hermes agent CLI (`hermes run`) | `MBG_HERMES_PROFILE` env var (optional) |

**CLI:**
```bash
# Local LLM via API (vLLM/Ollama)
python3 llm_classifier.py articles.json --mode local --output classified.json

# HuggingFace pipeline (pytorch) — uses nahiar/sentiment-analysis-v2 by default
python3 llm_classifier.py articles.json --mode local-model --output classified.json

# Hermes agent CLI
python3 llm_classifier.py articles.json --mode hermes --output classified.json
```

**Configuration via `.env`:**
```bash
# Copy template and edit
cp .env.example .env

# ── HuggingFace Pipeline (local-model) ──
MBG_HF_MODEL=nahiar/sentiment-analysis-v2
MBG_HF_DEVICE=cuda         # "cuda" or "cpu"
MBG_HF_BATCH_SIZE=32

# ── API-based LLM (local) ──
MBG_LLM_URL=http://localhost:8000/v1/chat/completions
MBG_LLM_MODEL=Qwen/Qwen3.5-35B-A3B-GPTQ-Int4
MBG_LLM_TIMEOUT=120
MBG_LLM_MAX_TOKENS=8192

# ── Hermes ──
# MBG_HERMES_PROFILE=my-profile
```

**Mode details:**

- **`local`** — Sends articles as a batch prompt to an OpenAI-compatible API. Auto-detects API type (`/v1/chat/completions`, `/v1/completions`, Ollama `/api/generate`). Handles reasoning models with JSON array fallback extraction.
- **`local-model`** — Loads a HuggingFace `text-classification` pipeline. Supports any HF sentiment model. Pipeline is cached after first load. Batch inference with configurable batch size. Runs on GPU (`cuda`) or CPU.
- **`hermes`** — Delegates classification to Hermes agent CLI. Useful when running within the Hermes ecosystem.

---

### `classifier.py` — Log Formatter

Formats classified articles into daily markdown log files and generates a Telegram-ready summary.

| Function | Description |
|----------|-------------|
| `group_articles_by_date(articles)` | Group articles by their date string |
| `build_log_entry(date_str, articles)` | Build markdown block for one day: header → sentiment counts → articles sorted negatif→netral→positif |
| `build_summary(articles)` | Generate short Telegram summary (headlines + counts) |

**CLI:**
```bash
# Write daily logs + summary
python3 classifier.py classified.json --log-dir log/

# Telegram summary only (no file writes)
python3 classifier.py classified.json --summary

# Preview formatted log to stdout (no file writes)
python3 classifier.py classified.json --stdout
```

**Log format per artikel:**
```markdown
### 🔴 1. [Judul Artikel](https://...)
**Sentiment:** negatif

> Full article body text (2000 chars max)...
```

---

### `run.sh` — Pipeline Orchestrator

Runs the full pipeline: **scrape → classify → log** sequentially.

```bash
# Incremental, rule-based classifier (default)
./run.sh

# Full backfill from Jan 1, rule-based
./run.sh --backfill

# Use vLLM/Ollama API — configure via .env
./run.sh --classifier local

# Use HuggingFace pipeline (nahiar/sentiment-analysis-v2 + PyTorch)
./run.sh --classifier local-model

# Backfill + HF pipeline
./run.sh --backfill --classifier local-model

# Use Hermes agent CLI
./run.sh --classifier hermes
```

The Telegram-formatted summary is automatically printed to stdout at the end.

---

## Setup

### Prerequisites
- Python 3.8+
- `pip` (Python package manager)

### Installation

```bash
# 1. Clone repo
git clone <your-repo-url> mbg-scraper
cd mbg-scraper

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run pipeline
./run.sh
```

### Requirements

Create `requirements.txt`:

```txt
# Core
requests>=2.28.0

# HuggingFace pipeline (for --classifier local-model)
transformers>=4.44.0
torch>=2.0.0
```

---

## Configuration

Key parameters configurable in `scraper.py`:

| Parameter | Location | Default | Description |
|-----------|----------|---------|-------------|
| `TAGS` | Line 27-30 | `["MBG", "makan-bergizi-gratis"]` | Kompas tag slugs to scrape |
| `DATE_START` | Line 35 | `2026-01-01` | Earliest article date to include (backfill) |
| `DATE_END` | Line 36 | `2026-06-22` | Latest article date to include (backfill) |
| `USER_AGENT` | Line 19-22 | Chrome UA string | HTTP User-Agent header |
| Body cap | `fetch_article_body()` line 179 | 2000 chars | Max article body length |
| Rate limit | `scraper.py` line 292 | 0.3s | Delay between body fetches |
| Backfill rate limit | `scraper.py` line 258 | 0.5s | Delay between tag page fetches |

To adjust date range, edit the `DATE_START` and `DATE_END` variables:

```python
DATE_START = date(2026, 1, 1)    # Earliest article
DATE_END = date(2026, 12, 31)    # Latest article
```

To add more tag sources:

```python
TAGS = [
    {"slug": "MBG", "label": "MBG"},
    {"slug": "makan-bergizi-gratis", "label": "makan-bergizi-gratis"},
    # Add more:
    {"slug": "gizi", "label": "gizi"},
]
```

---

## Classifier Selection Guide

| Mode | Accuracy | Speed | Requirements |
|------|----------|-------|-------------|
| `rule` | Moderate (keyword-based) | ⚡ Instant | None |
| `local` | High (LLM) | 🐢 Depends on GPU | vLLM / Ollama / LM Studio running |
| `local-model` | High (fine-tuned model) | ⚡ Fast (GPU) | PyTorch + transformers |
| `hermes` | High (LLM) | 🐢 Depends on provider | Hermes CLI installed |

## Key Design Decisions

- **4 classifier modes** — `rule` (keyword), `local` (API endpoint), `local-model` (HF pipeline), `hermes` (Hermes CLI). Pick what fits your compute
- **Body fetch is default** — Kompas tag pages don't provide article lead/snippet text; only category labels
- **JS widget cleanup** — Kompas.id inline recommender JS (`var endpoint ... xhr.send()`) stripped from body text
- **Unknown URL tracking** — `known_urls.json` enables incremental runs without re-fetching known articles
- **Exit-safe pipeline** — `run.sh` uses `|| true` on scraper step to prevent `set -e` failures from exit-code-as-return-value pattern

---

## Example Output

**`log/2026-06-22.md`:**
```markdown
# MBG Sentiment Log — 2026-06-22

## 22 June 2026 — 9 artikel

🟢 Positif: 0 | 🟡 Netral: 1 | 🔴 Negatif: 8

### 🔴 1. [Khawatir Nasib Gizi Pelajar, Paguyuban Relawan Bojonegoro Tuntut Program MBG Dilanjutkan](https://surabaya.kompas.com/read/2026/06/22/110028278/...)
**Sentiment:** negatif

> BOJONEGORO, KOMPAS.com – Ribuan orang yang tergabung dalam Paguyuban Relawan Makan Bergizi Gratis (MBG) Kabupaten Bojonegoro...
```

**`log/_summary.txt`:**
```
📊 *MBG Sentiment Report*
📅 22 June 2026

Total: 26 artikel baru
🟢 Positif: 7 | 🟡 Netral: 10 | 🔴 Negatif: 9

*Headlines:*
🟡 [Belajar dari Nepal dan Bolivia...](https://...)
🔴 [Korupsi Selalu Dekat dengan Kekuasaan](https://...)
🔴 [Khawatir Nasib Gizi Pelajar...](https://...)
```
