# MBG Scraper — Sentiment Analysis Pipeline

Scrape artikel Kompas.com tentang program **Makan Bergizi Gratis (MBG)** dari dua tag source, klasifikasi sentimen, dan output ke daily log markdown.

Tersedia **4 classifier mode** yang bisa dipilih sesuai kebutuhan:
- **`rule`** — berbasis keyword (cepat, offline, tanpa GPU)
- **`local`** — LLM via API (vLLM, Ollama, LM Studio) — configurable endpoint + model
- **`local-model`** — HuggingFace pipeline langsung via PyTorch (GPU/CPU)
- **`hermes`** — via Hermes agent CLI

---

## Quick Start

```bash
# 1. Clone & install
git clone <your-repo-url> mbg-scraper
cd mbg-scraper
pip install -r requirements.txt

# 2. Jalankan pipeline (rule-based default)
./run.sh

# 3. Atau pake classifier lain
./run.sh --classifier local-model
```

---

## Classifier Selection

| Mode | Accuracy | Speed | Requirements |
|---|---|---|---|
| `rule` | Moderate (keyword) | ⚡ Instant | None |
| `local` | High (LLM) | 🐢 Network + GPU | vLLM / Ollama / LM Studio running |
| `local-model` | High (fine-tuned) | ⚡ Fast (GPU) | PyTorch + transformers |
| `hermes` | High (LLM) | 🐢 Overhead CLI | Hermes CLI installed |

📖 [Detailed parameter reference](docs/classifier-parameters.md) — system prompt, engine params, post-processing per mode.

---

## Pipeline

```
Input (Kompas tags) → [scraper.py] → [classifier (4 modes)] → [classifier.py] → log/YYYY-MM-DD.md + _summary.txt
```

📖 [Full architecture & design decisions](docs/architecture.md)

---

## Configuration

| Area | File | Docs |
|---|---|---|
| Scraper params | `scraper.py` (hardcoded) | [configuration.md](docs/configuration.md#1-scraper-configuration) |
| LLM / HF env vars | `.env` | [configuration.md](docs/configuration.md#2-environment-variables-env) |
| CLI flags | run-time | [configuration.md](docs/configuration.md#3-run-time-cli-flags) |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No module named 'requests'` | `pip install requests` |
| MIOpen/HIP illegal memory access | Pakai model kecil atau mode `local` via vLLM |
| `FileNotFoundError: .tmp/scrape_output.json` | `rm -rf .tmp/ known_urls.json` lalu run ulang |
| LLM output "Thinking Process..." | Regex fallback sudah handle, cek [troubleshooting](docs/troubleshooting.md#5-qwen--llm-output-thinking-process-instead-of-json) |

📖 [Full troubleshooting guide](docs/troubleshooting.md) — ROCm errors, missing modules, cache issues, reasoning models.

---

## Project Structure

```
mbg-scraper/
├── scraper.py              # Scraper — fetch tag pages + article bodies
├── rules_classifier.py     # Rule-based sentiment classifier (default)
├── llm_classifier.py       # LLM-based classifier (3 modes)
├── classifier.py           # Log formatter — markdown + summary
├── run.sh                  # Pipeline orchestrator
├── requirements.txt        # Python dependencies
├── .env.example            # LLM configuration template
├── README.md               # This file
│
├── docs/                   # 📚 Documentation
│   ├── architecture.md           # Pipeline flow, design decisions, output format
│   ├── classifier-parameters.md  # Sentiment parameter breakdown per mode
│   ├── configuration.md          # All config: scraper params, env vars, CLI flags
│   └── troubleshooting.md        # Common errors & fixes
│
├── log/                    # Daily sentiment log output
├── state.json              # Last run timestamp
├── known_urls.json         # URL cache (deduplication)
├── .tmp/                   # Temporary pipeline artifacts
└── scripts/                # Reserved
```

## License

—
