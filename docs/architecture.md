# Architecture

Pipeline arsitektur MBG Scraper — alur data, design decisions, dan output format.

## Pipeline Flow

```
┌─────────────────────┐
│     Input Sources    │
│  kompas.com/tag/MBG  │
│  kompas.com/tag/     │
│  makan-bergizi-gratis│
└─────────┬───────────┘
          │
          ▼
┌──────────────────────────────────────────┐
│  Step 1: Scrape (scraper.py)             │
│                                          │
│  scrape_tag_page()                       │
│    → Parse HTML articleItem              │
│    → Extract title, url, date            │
│                                          │
│  fetch_article_body()                    │
│    → Full body (capped 2000 chars)       │
│    → Strip inline JS widget (Kompas.id)  │
│                                          │
│  Deduplicate across tags                 │
│    → known_urls.json cache               │
└──────────────────┬───────────────────────┘
                   │
                   ▼
        ┌──────────────────┐
        │  articles.json   │
        └──────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│  Step 2: Classify                        │
│                                          │
│  ┌─ rule-based (rules_classifier.py)     │
│  ├─ vLLM/Ollama (llm_classifier.py)      │
│  ├─ HF Pipeline (llm_classifier.py)      │
│  └─ Hermes CLI (llm_classifier.py)       │
│                                          │
│  Output: articles + sentiment field      │
└──────────────────┬───────────────────────┘
                   │
                   ▼
        ┌──────────────────┐
        │ classified.json  │
        └──────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│  Step 3: Format Log (classifier.py)      │
│                                          │
│  Group by date                           │
│  Sort: negatif → netral → positif        │
│                                          │
│  Outputs:                                │
│    log/YYYY-MM-DD.md  (daily markdown)   │
│    log/_summary.txt   (Telegram summary)  │
└──────────────────────────────────────────┘
```

## Key Design Decisions

### 1. Empat Classifier Mode

Masing-masing punya use case:

| Mode | Kapan Dipakai |
|---|---|
| `rule` | Fast prototyping, zero setup, no GPU |
| `local` | Punya vLLM/Ollama server running — akurasi tinggi |
| `local-model` | Punya GPU, mau inference langsung via PyTorch |
| `hermes` | Mau integrasi dengan Hermes agent ecosystem |

Pisah script (`rules_classifier.py` vs `llm_classifier.py`) karena dependency berbeda — `llm_classifier.py` butuh `requests` & `transformers`, `rules_classifier.py` zero dependency.

### 2. Body Fetch is Default

Kompas tag pages tidak menyediakan `lead` / `snippet` text — hanya category labels. Jadi fetch full body adalah kebutuhan, bukan opsi.

### 3. JS Widget Cleanup

Kompas.id menyisipkan inline recommender widget via JavaScript di dalam `read__content`. Regex strip:

```
var endpoint = ... xhr.send()
```

Tanpa cleanup, body artikel terkontaminasi kode JS.

### 4. Unknown URL Tracking

`known_urls.json` menyimpan semua URL yang pernah diproses. Mekanisme incremental:
- Scrape pertama: simpan semua URL ke `known_urls.json`
- Scrape kedua: skip URL yang sudah ada → hanya proses artikel baru
- Backfill: proses semua, update `known_urls.json`

### 5. Exit-Safe Pipeline

`run.sh` menggunakan `|| true` pada langkah scraper untuk mencegah `set -e` abort ketika scraper mengembalikan exit code non-zero (yang sebenarnya adalah return value, bukan error).

## Output Format

### Daily Log (`log/YYYY-MM-DD.md`)

```markdown
# MBG Sentiment Log — 2026-06-22

## 22 June 2026 — 9 artikel

🟢 Positif: 0 | 🟡 Netral: 1 | 🔴 Negatif: 8

### 🔴 1. [Judul Artikel](https://...)
**Sentiment:** negatif

> Full article body text (2000 chars max)...
```

Setiap artikel: judul (link), sentiment, body.
Urutan: negatif → netral → positif.

### Telegram Summary (`log/_summary.txt`)

```
📊 *MBG Sentiment Report*
📅 22 June 2026

Total: 26 artikel baru
🟢 Positif: 7 | 🟡 Netral: 10 | 🔴 Negatif: 9

*Headlines:*
🟡 [Belajar dari Nepal dan Bolivia...](https://...)
🔴 [Korupsi Selalu Dekat dengan Kekuasaan](https://...)
```

Format ini siap dikirim ke Telegram tanpa editing tambahan.

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
├── docs/                   # Documentation
│   ├── architecture.md          # This file
│   ├── classifier-parameters.md # Sentiment parameter reference
│   ├── configuration.md         # Configuration reference
│   └── troubleshooting.md       # Common errors & fixes
│
├── log/                    # Daily sentiment log output
├── state.json              # Last run timestamp
├── known_urls.json         # URL cache (deduplication)
├── .tmp/                   # Temporary pipeline artifacts
└── scripts/                # Reserved
```
