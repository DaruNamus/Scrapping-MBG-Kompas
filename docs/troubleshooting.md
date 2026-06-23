# Troubleshooting

Common errors dan solusinya.

---

## 1. ROCm / MIOpen GPU Errors

**Error:**
```
MIOpen(HIP): Warning [ParseAndLoadDb] File is unreadable: ".../miopen/db/gfx1201_32.HIP.fdb.txt"
MIOpen Error: Failed to get function: naive_conv_ab_nonpacked_fwd_nchw_ushort_double_ushort_0: an illegal memory access was encountered
terminate called after throwing an instance of 'c10::AcceleratorError'
```

**Penyebab:**  
Model (misal Qwen3.5-4B) butuh MIOpen convolution kernel yang belum tercompile untuk GPU `gfx1201` (RDNA 4 / RX 9070 series). PyTorch ROCm nightly belum fully baked untuk GPU tersebut.

**Solusi:**
1. **Pakai mode `local` via vLLM** — vLLM punya ROCm support lebih matang
2. **Pakai model kecil** — `nahiar/sentiment-analysis-v2` (distilbert) works karena arsitekturnya attention-only, no convolution
3. **Set `MBG_HF_DEVICE=cpu`** di `.env` — inferensi lebih lambat tapi works
4. **Tunggu update ROCm** — kernel support untuk `gfx1201` akan lengkap di release berikutnya

**Quick check GPU support:**
```bash
python3 -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

---

## 2. Missing Module: `requests`

**Error:**
```
ModuleNotFoundError: No module named 'requests'
```

**Solusi:**
```bash
pip install requests
```

Atau install semua dependency:
```bash
pip install -r requirements.txt
```

---

## 3. Missing Module: `transformers`

**Error:**
```
ModuleNotFoundError: No module named 'transformers'
```

**Solusi:**
```bash
pip install transformers torch
```

---

## 4. `FileNotFoundError: .tmp/scrape_output.json`

**Error:**
```
FileNotFoundError: /home/.../.tmp/scrape_output.json
```

**Penyebab:** Langkah scrape gagal atau tidak menghasilkan output (biasanya karena missing module, jaringan, atau cache corrupt).

**Solusi:**
1. Hapus cache:
   ```bash
   rm -rf .tmp/ known_urls.json state.json
   ```
2. Cek koneksi internet ke kompas.com
3. Jalankan ulang

---

## 5. Qwen / LLM Output "Thinking Process" Instead of JSON

**Error:**
```
[ERROR] Local LLM response parse failed: Expecting value: line 1 column 1 (char 0)
Raw response snippet: Thinking Process:
1. Analyze the Request: ...
```

**Penyebab:** Model reasoning (Qwen, DeepSeek-R1, dll) mengeluarkan chain-of-thought sebelum JSON.

**Solusi:**
1. **Sudah di-handle otomatis** — `llm_classifier.py` punya regex fallback `\[.*?\]` yang extract JSON dari response campuran
2. Kalau tetap gagal:
   - Cek apakah model benar-benar mengeluarkan JSON array di akhir
   - Untuk vLLM: pastikan `--enable-reasoning` dinonaktifkan untuk model non-reasoning
3. **Workaround:** pakai mode `local-model` atau `rule`

---

## 6. `ModuleNotFoundError: No module named 'torch'`

**Error saat pake `--classifier local-model`.**

**Solusi untuk efison-kristo (ROCm):**
```bash
pip install --pre torch torchvision torchaudio --index-url https://rocm.nightlies.amd.com/v2/gfx120X-all/
```

**Solusi untuk CUDA (NVIDIA):**
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

**Solusi CPU-only:**
```bash
pip install torch torchvision torchaudio
```

---

## 7. Scraper Returns "0 Artikel" / Nothing New

**Log:**
```
[SCRAPER] New: 0, Deduped total: 0, Skipped (known): 30, Out of range: 0
[SCRAPER] Fetching 0 article bodies...
[SCRAPER] Saved 0 articles to ...
```

**Penyebab:** Semua artikel sudah di-cache di `known_urls.json`. Pipeline dalam mode incremental.

**Solusi:**
- **Backfill** untuk paksa scrape dari awal:
  ```bash
  ./run.sh --backfill
  ```
- **Hapus cache** untuk reset:
  ```bash
  rm -f known_urls.json state.json
  ```

---

## 8. Error Saat Git Pull

**Error:**
```
error: Your local changes to the following files would be overwritten by merge
```

**Solusi:**
```bash
# Simpan perubahan lokal dulu
git stash

# Pull
git pull

# Kembalikan perubahan lokal
git stash pop
```
