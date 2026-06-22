#!/usr/bin/env python3
"""
MBG LLM Classifier — Classify articles as positif/netral/negatif.
Three modes:
  1. local: any OpenAI-compatible API (vLLM, Ollama, LM Studio)
  2. local-model: direct HuggingFace transformers pipeline (pytorch)
  3. hermes: calls Hermes agent CLI

Interface identical to rules_classifier.py — just swap the script.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime

import requests


# ── Configuration via environment variables ──────────────────────────────

# API-based LLM config
LOCAL_LLM_URL = os.environ.get("MBG_LLM_URL", "http://localhost:8000/v1/completions")
LOCAL_LLM_MODEL = os.environ.get("MBG_LLM_MODEL", "Qwen/Qwen3.5-35B-A3B-GPTQ-Int4")
LOCAL_LLM_TIMEOUT = int(os.environ.get("MBG_LLM_TIMEOUT", "120"))
MAX_TOKENS = int(os.environ.get("MBG_LLM_MAX_TOKENS", "8192"))

# HuggingFace model config (for local-model mode)
HF_MODEL_NAME = os.environ.get("MBG_HF_MODEL", "nahiar/sentiment-analysis-v2")
HF_DEVICE = os.environ.get("MBG_HF_DEVICE", "cuda")      # "cuda" or "cpu"
HF_BATCH_SIZE = int(os.environ.get("MBG_HF_BATCH_SIZE", "8"))   # smaller default for large models
HF_FALLBACK_CPU = os.environ.get("MBG_HF_FALLBACK_CPU", "true").lower() in ("1", "true", "yes")

# Hermes LLM config
HERMES_PROFILE = os.environ.get("MBG_HERMES_PROFILE", "")


# ── Shared helpers ─────────────────────────────────────────────────────

def build_user_prompt(articles):
    """Build user prompt from list of article dicts."""
    parts = []
    for i, a in enumerate(articles, 1):
        title = a.get("title", "—")
        body = (a.get("body", "") or a.get("snippet", "") or "")[:1000]
        parts.append(f"[{i}] Title: {title}")
        if body:
            parts.append(f"    Content: {body}")
    return "\n".join(parts)


SYSTEM_PROMPT = "Classify sentiment (positif, netral, negatif) for MBG articles. Output JSON array: [{\"sentiment\": \"...\"}, ...]. No thinking, no markdown, no explanation. ONLY the JSON array."


def extract_json_array(text):
    """Try to find and parse a JSON array anywhere in text."""
    # Direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find [...] in text
    m = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
    if not m:
        m = re.search(r'\[.*?\]', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


def apply_sentiments(articles, results):
    """Apply sentiment labels from results list to articles list."""
    if len(results) != len(articles):
        print(f"[WARN] Expected {len(articles)} results, got {len(results)}. "
              f"Padding/truncating.", file=sys.stderr)
        while len(results) < len(articles):
            results.append({"sentiment": "netral"})
        results = results[:len(articles)]
    for a, r in zip(articles, results):
        sentiment = r.get("sentiment", "netral")
        if sentiment not in ("positif", "netral", "negatif"):
            sentiment = "netral"
        a["sentiment"] = sentiment
    return articles


def build_output(articles, method, model_name):
    return {
        "classified_at": datetime.now().isoformat(),
        "method": method,
        "model": model_name,
        "total_articles": len(articles),
        "articles": articles,
    }


# ── Mode 1: Local LLM via API (vLLM / Ollama / LM Studio) ───────────────

def _detect_api_type(url):
    if "/chat/completions" in url:
        return "chat"
    elif "/completions" in url:
        return "completions"
    elif "/api/generate" in url:
        return "generate"
    elif "/api/chat" in url:
        return "chat"
    return "generate"


def classify_local_llm(articles):
    """Classify via OpenAI-compatible API (vLLM, Ollama, LM Studio)."""
    prompt = build_user_prompt(articles)
    api_type = _detect_api_type(LOCAL_LLM_URL)

    if api_type == "chat":
        payload = {
            "model": LOCAL_LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": MAX_TOKENS,
            "stream": False,
        }
    elif api_type == "completions":
        full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}\n\nOutput ONLY a JSON array."
        payload = {
            "model": LOCAL_LLM_MODEL,
            "prompt": full_prompt,
            "temperature": 0.1,
            "max_tokens": MAX_TOKENS,
            "stream": False,
        }
    else:
        # Ollama /api/generate
        payload = {
            "model": LOCAL_LLM_MODEL,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        if "max_tokens" not in payload:
            payload["max_tokens"] = MAX_TOKENS

    try:
        resp = requests.post(
            LOCAL_LLM_URL,
            json=payload,
            timeout=LOCAL_LLM_TIMEOUT,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract text
        raw = ""
        choices = data.get("choices", [])
        if choices:
            c = choices[0]
            msg = c.get("message", {})
            if isinstance(msg, dict):
                raw = msg.get("content", "")
            if not raw:
                raw = c.get("text", "")
        if not raw:
            raw = data.get("response", "")

        if not raw:
            raise ValueError(f"Cannot extract response. Keys: {list(data.keys())}")

        results = extract_json_array(raw)
        if results is None or not isinstance(results, list):
            raise ValueError(f"No valid JSON array in response: {raw[:300]!r}")
        return results

    except requests.RequestException as e:
        print(f"[ERROR] API request failed: {e}", file=sys.stderr)
        return None
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
        print(f"[ERROR] API response parse failed: {e}", file=sys.stderr)
        print(f"  Raw: {raw[:500] if 'raw' in dir() else 'N/A'}", file=sys.stderr)
        return None


# ── Mode 2: Direct HuggingFace pipeline (local-model) ────────────────────

_hf_pipeline = None  # singleton cache


def classify_local_model(articles):
    """Classify via HuggingFace transformers pipeline (pytorch).
    Uses nahiar/sentiment-analysis-v2 or any HF sentiment model.
    """
    global _hf_pipeline

    print(f"[LOCAL-MODEL] Loading {HF_MODEL_NAME} on {HF_DEVICE}...",
          file=sys.stderr)

    try:
        from transformers import pipeline
    except ImportError:
        print("[ERROR] transformers not installed. Run: pip install transformers torch",
              file=sys.stderr)
        return None

    # Lazy-load pipeline (cached after first call)
    if _hf_pipeline is None:
        device = HF_DEVICE
        try:
            _hf_pipeline = pipeline(
                "text-classification",
                model=HF_MODEL_NAME,
                device=device,
            )
            print(f"[LOCAL-MODEL] Pipeline ready on {device}.", file=sys.stderr)
        except Exception as e:
            if HF_FALLBACK_CPU and device != "cpu":
                print(f"[WARN] GPU failed ({e}), falling back to cpu...",
                      file=sys.stderr)
                device = "cpu"
                try:
                    _hf_pipeline = pipeline(
                        "text-classification",
                        model=HF_MODEL_NAME,
                        device="cpu",
                    )
                    print(f"[LOCAL-MODEL] Pipeline ready on cpu (fallback).",
                          file=sys.stderr)
                except Exception as e2:
                    print(f"[ERROR] Failed to load model {HF_MODEL_NAME} on cpu too: {e2}",
                          file=sys.stderr)
                    return None
            else:
                print(f"[ERROR] Failed to load model {HF_MODEL_NAME}: {e}",
                      file=sys.stderr)
                return None

    # Build text inputs: "Title: ... Content: ..."
    texts = []
    for a in articles:
        title = a.get("title", "")
        body = (a.get("body", "") or a.get("snippet", "") or "")[:500]
        texts.append(f"{title}. {body}".strip())

    print(f"[LOCAL-MODEL] Classifying {len(texts)} articles in batches of {HF_BATCH_SIZE}...",
          file=sys.stderr)

    results = []
    try:
        for i in range(0, len(texts), HF_BATCH_SIZE):
            batch = texts[i:i + HF_BATCH_SIZE]
            outputs = _hf_pipeline(
                batch,
                truncation=True,
                max_length=512,
            )
            results.extend(outputs)

            if (i + len(batch)) % (HF_BATCH_SIZE * 2) == 0 or (i + len(batch)) >= len(texts):
                print(f"  [{i + len(batch)}/{len(texts)}] classified",
                      file=sys.stderr)

    except Exception as e:
        print(f"[ERROR] Classification failed: {e}", file=sys.stderr)
        return None

    # Map HF labels to MBG labels
    # nahiar/sentiment-analysis-v2 returns: LABEL_0 = negative, LABEL_1 = neutral, LABEL_2 = positive
    # But custom models may differ — use dictionary config
    label_map = {
        "LABEL_0": "negatif",
        "LABEL_1": "netral",
        "LABEL_2": "positif",
        "NEGATIVE": "negatif",
        "NEUTRAL": "netral",
        "POSITIVE": "positif",
        "negative": "negatif",
        "neutral": "netral",
        "positive": "positif",
    }

    formatted = []
    for r in results:
        label = r.get("label", "neutral").upper()
        if label.startswith("LABEL_"):
            sent = label_map.get(label, "netral")
        else:
            sent = label_map.get(label.upper(), "netral")
        formatted.append({"sentiment": sent})

    print(f"[LOCAL-MODEL] Done. {len(formatted)} articles classified.",
          file=sys.stderr)
    return formatted


# ── Mode 3: Hermes CLI ──────────────────────────────────────────────────

def classify_hermes_llm(articles):
    """Classify via Hermes agent CLI (hermes run)."""
    prompt = build_user_prompt(articles)
    full_prompt = f"{SYSTEM_PROMPT}\n\n{USER_PROMPT_PREFIX}\n{prompt}"

    cmd = ["hermes", "run", "--prompt", full_prompt]
    if HERMES_PROFILE:
        cmd.extend(["--profile", HERMES_PROFILE])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=LOCAL_LLM_TIMEOUT,
        )
        if result.returncode != 0:
            print(f"[ERROR] Hermes CLI failed (exit {result.returncode}): {result.stderr[:500]}", file=sys.stderr)
            return None

        output = result.stdout.strip()
        results = extract_json_array(output)
        if results is None or not isinstance(results, list):
            raise ValueError("No valid JSON array found in Hermes output")
        return results

    except subprocess.TimeoutExpired:
        print(f"[ERROR] Hermes CLI timed out after {LOCAL_LLM_TIMEOUT}s", file=sys.stderr)
        return None
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[ERROR] Hermes response parse failed: {e}", file=sys.stderr)
        return None


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MBG sentiment classifier")
    parser.add_argument("input", help="JSON file with scraped articles")
    parser.add_argument("--output", default=None, help="Output JSON file")
    parser.add_argument("--mode", choices=["local", "local-model", "hermes"],
                        default="local",
                        help="Classifier mode: local (API), local-model (HF pipeline), hermes")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    articles = data.get("articles", [])
    if not articles:
        print("No articles to process.", file=sys.stderr)
        return 0

    print(f"[CLASSIFIER] Classifying {len(articles)} articles via {args.mode}...",
          file=sys.stderr)

    if args.mode == "local":
        results = classify_local_llm(articles)
        method = "llm-api"
        model = LOCAL_LLM_MODEL
    elif args.mode == "local-model":
        results = classify_local_model(articles)
        method = "hf-pipeline"
        model = HF_MODEL_NAME
    else:
        results = classify_hermes_llm(articles)
        method = "hermes"
        model = "hermes"

    if results is None:
        print("[CLASSIFIER] Classification failed. No output written.", file=sys.stderr)
        return 1

    articles = apply_sentiments(articles, results)
    output = build_output(articles, method, model)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2)
        print(f"Classified {len(articles)} articles -> {args.output}")
    else:
        print(json.dumps(output, indent=2))

    counts = Counter(a["sentiment"] for a in articles)
    print(f"\nSentiment distribution: Positif={counts.get('positif', 0)}, "
          f"Netral={counts.get('netral', 0)}, Negatif={counts.get('negatif', 0)}",
          file=sys.stderr)
    return 0


USER_PROMPT_PREFIX = """Classify the sentiment of each article about the MBG program in Indonesia.

Articles:
"""


if __name__ == "__main__":
    sys.exit(main())
