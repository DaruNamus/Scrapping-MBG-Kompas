# Classifier Parameters — Sentiment Classification

Penjelasan parameter yang menentukan output sentiment (`positif` / `netral` / `negatif`) di pipeline MBG Scraper.

## Pipeline Overview

```
Input (title + body) ──► [Classifier] ──► {id, sentiment}
                              │
                              ├── rule-based (keyword rules)
                              ├── local ...... (vLLM / Ollama / LM Studio)
                              ├── local-model  (HuggingFace transformers)
                              └── hermes ...... (Hermes agent CLI)
```

---

## Parameters per Mode

### 1. Rule-Based (`--classifier rule`)

| Parameter | Lokasi | Efek |
|---|---|---|
| `BAD_WORDS` | `rules_classifier.py` | Keywords → **negatif** |
| `GOOD_WORDS` | `rules_classifier.py` | Keywords → **positif** |
| `title` match priority | `rules_classifier.py` | Judul diperiksa duluan sebelum body |
| `body` fallback | `rules_classifier.py` | Body dicek hanya jika title netral |
| Case-insensitive matching | `rules_classifier.py` | Normalisasi huruf kapital |

**Karakteristik:** Deterministik, cepat, zero GPU, tapi rigid — cuma cocok buat keyword jelas.

---

### 2. LLM Local (`--classifier local`)

Input dikirim ke LLM via API (vLLM / Ollama / LM Studio). Hasil sepenuhnya tergantung prompt.

#### System Prompt

Ada di `llm_classifier.py` — variabel `SYSTEM_PROMPT`.

```python
"""Anda adalah asisten analisis sentimen. ...
Hanya balas dengan array JSON valid, contoh:
[
  {"id": 1, "sentiment": "positif"},
  {"id": 2, "sentiment": "netral"},
  {"id": 3, "sentiment": "negatif"}
]
HANYA 3 label yang valid: positif, netral, negatif.
"""
```

| Elemen Prompt | Efek |
|---|---|
| Instruksi "JSON only" | Mencegah penjelasan tambahan, output langsung parseable |
| 3 label (`positif`/`netral`/`negatif`) | Batasi ruang klasifikasi — LLM tidak bisa output label lain |
| Contoh format dengan `id` + `sentiment` | Menentukan struktur output yang diharapkan |
| "HANYA 3 label yang valid" | Redundansi untuk mencegah hallucination label baru |

#### User Prompt

Dibangun oleh fungsi `build_user_prompt()`:

```python
def build_user_prompt(articles):
    parts = []
    for i, a in enumerate(articles, 1):
        title = a.get("title", "—")
        body = (a.get("body", "") or a.get("snippet", "") or "")[:1000]
        parts.append(f"[{i}] Title: {title}")
        if body:
            parts.append(f"   Content: {body[:500]}")
    return "\n".join(parts)
```

| Parameter | Efek |
|---|---|
| **Body truncation** `[:1000]` / `[:500]` | Semakin panjang, semakin banyak konteks tapi token habis buat artikel lain |
| **Urutan Title → Content** | Bias — LLM cenderung kasih weight lebih ke informasi pertama |
| **`[i]` index** | LLM pake ini buat `id` di response JSON |

#### Engine Parameters

Dikirim ke vLLM/Ollama API:

| Parameter | Source `.env` | Efek |
|---|---|---|
| `model` | `MBG_LLM_MODEL` | Model size & quantisasi (GPTQ/GGUF) — model >7B umumnya lebih konsisten |
| `temperature` | hardcoded `0.1` | **Paling krusial.** 0.1 = hampir deterministic. >0.5 = variatif, kadang flip label |
| `max_tokens` | `MBG_LLM_MAX_TOKENS` (8192) | Kalau terlalu kecil, JSON bisa terpotong → parse error |
| `stop` sequences | hardcoded `["\n\n\n"]` | Mencegah LLM lanjut nulis commentary setelah JSON |

#### Post-Processing

```python
_JSON_PATTERN = re.compile(r'\[.*?\]', re.DOTALL)
match = _JSON_PATTERN.search(raw_text)
if match:
    results = json.loads(match.group(0))
```

| Parameter | Efek |
|---|---|
| Regex fallback `\[.*?\]` | Extract JSON dari response yang tercampur teks lain (misal "Thinking Process" dari Qwen reasoning model) |
| Safe default `{"sentiment": "netral"}` | Artikel yang gagal diparse dianggap netral |

---

### 3. Local Model (`--classifier local-model`)

Pakai HuggingFace `pipeline("text-classification", ...)` langsung.

| Parameter | Source `.env` | Efek |
|---|---|---|
| `model` | `MBG_HF_MODEL` | Arsitektur model (`distilbert`, `roberta`, dll) — menentukan label set native |
| `device` | `MBG_HF_DEVICE` (`cuda`/`cpu`) | GPU = cepat, CPU = lambat untuk model besar |
| `batch_size` | `MBG_HF_BATCH_SIZE` (8) | Semakin besar, semakin cepat tapi pakai lebih banyak VRAM |
| `truncation` | hardcoded `512` tokens | Artikel kepanjangan dipotong |

**Label mapping** — model HF punya label native sendiri:

| Native Label | MBG Label |
|---|---|
| `LABEL_0` | `negatif` |
| `LABEL_1` | `netral` |
| `LABEL_2` | `positif` |
| `NEGATIVE` | `negatif` |
| `NEUTRAL` | `netral` |
| `POSITIVE` | `positif` |

⚠️ Model seperti Qwen3.5-4B mungkin punya label set berbeda — cek `model.config.id2label` untuk konfirmasi.

---

### 4. Hermes (`--classifier hermes`)

Sama dengan mode `local` secara arsitektur, tapi request dikirim via Hermes agent CLI (`hermes run`) sebagai subprocess.

| Parameter | Effektivitas vs `local` |
|---|---|
| Prompt | Sama persis (system + user prompt) |
| Model | Tergantung profile Hermes yang aktif |
| Kecepatan | Lebih lambat (overhead subprocess + Hermes middleware) |
| Kelebihan | Bisa pake provider/model apapun yang terdaftar di Hermes |

---

## Decision Table: Mode Selection

| Mode | Akurasi | Kecepatan | GPU Required | Setup |
|---|---|---|---|---|
| `rule` | Medium (keyword-dependent) | ✅ Sangat cepat | ❌ Tidak | Zero config |
| `local` | High (tergantung model) | ⚠️ Sedang (network + inference) | ⚠️ Tergantung LLM server | LLM server running |
| `local-model` | High (tergantung model) | ✅ Cepat (GPU) / ❌ Lambat (CPU) | ✅ Disarankan | `pip install transformers torch` |
| `hermes` | High (tergantung model) | ❌ Lambat (overhead CLI) | Tergantung Hermes | Hermes CLI terinstall |

---

## Rekomendasi Tuning

1. **Temperature → 0.1** biar reproducible. Naikkan ke 0.3-0.5 kalau mau lebih nuanced.
2. **Body length** → 1000 chars cukup untuk artikel berita pendek. Naikkan ke 2000 untuk artikel feature/opini.
3. **System prompt → definisi label eksplisit**: tambahkan contoh artikel positif/netral/negatif langsung di prompt untuk konsistensi lebih tinggi.
4. **Model >7B** (Qwen 7B/14B, Llama 8B) — konsistensi label jauh lebih baik daripada model <3B.
5. **Coba mode `local` dulu** sebelum `local-model` — lebih fleksibel dan gampang debug.
