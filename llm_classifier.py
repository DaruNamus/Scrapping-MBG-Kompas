#!/usr/bin/env python3
"""
MBG LLM Classifier — Classify articles as positif/netral/negatif using an LLM.
Two modes:
  1. Local LLM: configurable endpoint (Ollama, vLLM, etc.) via env vars
  2. Hermes LLM: calls Hermes agent CLI for classification

Interface identical to rules_classifier.py — just swap the script.
"""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime

import requests


# ── Local LLM config ─────────────────────────────────────────────────────

LOCAL_LLM_URL = os.environ.get("MBG_LLM_URL", "http://localhost:8000/v1/completions")
LOCAL_LLM_MODEL = os.environ.get("MBG_LLM_MODEL", "Qwen/Qwen3.5-35B-A3B-GPTQ-Int4")
LOCAL_LLM_TIMEOUT = int(os.environ.get("MBG_LLM_TIMEOUT", "120"))

# Hermes LLM config
HERMES_PROFILE = os.environ.get("MBG_HERMES_PROFILE", "")


# ── Shared prompt template ───────────────────────────────────────────────

SYSTEM_PROMPT = """You are a sentiment classifier for Indonesian news articles about the MBG (Makan Bergizi Gratis / Free Nutritious Meal) program in Indonesia.

Classify each article as one of:
- "positif" — supports/is positive toward the MBG program
- "netral" — neutral, factual reporting without clear stance
- "negatif" — criticizes/opposes or reports problems with the MBG program

Rules:
- Do NOT think step by step. Output ONLY valid JSON.
- Do NOT include any reasoning, thinking, or explanation.
- Do NOT use markdown code blocks.

Output a JSON array in the EXACT same order as the input articles:
[
  {"sentiment": "positif"},
  {"sentiment": "netral"},
  {"sentiment": "negatif"}
]

Output ONLY the JSON array — nothing else before or after it."""


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


# ── Local LLM mode ──────────────────────────────────────────────────────

def _detect_api_type(url):
    """Detect API type from URL path."""
    if "/chat/completions" in url:
        return "chat"
    elif "/completions" in url:
        return "completions"
    elif "/api/generate" in url:
        return "generate"
    elif "/api/chat" in url:
        return "chat"
    return "generate"  # default fallback


def classify_local_llm(articles):
    """Classify via local LLM endpoint.
    Supports:
      - Ollama /api/generate (default fallback)
      - OpenAI-compatible /v1/chat/completions (vLLM, LM Studio, etc.)
      - OpenAI-compatible /v1/completions (legacy)
    """
    prompt = build_user_prompt(articles)
    api_type = _detect_api_type(LOCAL_LLM_URL)

    # Build payload based on API type
    if api_type == "chat":
        payload = {
            "model": LOCAL_LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
            "stream": False,
        }
    elif api_type == "completions":
        full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}\n\nOutput ONLY a JSON array."
        payload = {
            "model": LOCAL_LLM_MODEL,
            "prompt": full_prompt,
            "temperature": 0.1,
            "max_tokens": 4096,
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

    try:
        resp = requests.post(
            LOCAL_LLM_URL,
            json=payload,
            timeout=LOCAL_LLM_TIMEOUT,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        # Flexible response extraction — try multiple paths
        raw = ""
        choices = data.get("choices", [])
        if choices:
            choice = choices[0]
            # Try message.content (chat format)
            msg = choice.get("message", {})
            if isinstance(msg, dict):
                raw = msg.get("content", "")
            # Try .text (completions format)
            if not raw:
                raw = choice.get("text", "")

        # Ollama fallback
        if not raw:
            raw = data.get("response", "")

        if not raw:
            raise ValueError(
                f"Could not extract response text. "
                f"Keys: {list(data.keys())}, "
                f"Choice keys: {list(choices[0].keys()) if choices else 'N/A'}"
            )

        # Try to parse JSON array directly
        try:
            results = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: find JSON array [...] in response (handles thinking/reasoning models)
            import re
            json_match = re.search(r'\[\s*\{.*?\}\s*\]', raw, re.DOTALL)
            if json_match:
                results = json.loads(json_match.group())
            else:
                raise

        if not isinstance(results, list):
            raise ValueError(f"Expected JSON array, got {type(results).__name__}")

        return results

    except requests.RequestException as e:
        print(f"[ERROR] Local LLM request failed: {e}", file=sys.stderr)
        return None
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
        print(f"[ERROR] Local LLM response parse failed: {e}", file=sys.stderr)
        print(f"  Raw response snippet: {raw[:500] if 'raw' in dir() else 'N/A'}", file=sys.stderr)
        # Debug: print full response for diagnosis
        if 'data' in dir():
            import pprint
            print(f"  Full response keys: {list(data.keys())}", file=sys.stderr)
            if 'choices' in data and data['choices']:
                c = data['choices'][0]
                print(f"  Choice[0] type: {type(c).__name__}, keys: {list(c.keys()) if isinstance(c, dict) else 'N/A'}", file=sys.stderr)
                if isinstance(c, dict) and 'logprobs' in c:
                    print(f"  Choice has logprobs", file=sys.stderr)
        return None


# ── Hermes LLM mode ─────────────────────────────────────────────────────

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

        # Parse JSON from output
        output = result.stdout.strip()
        # Try to find JSON array in output
        import re
        json_match = re.search(r'\[.*\]', output, re.DOTALL)
        if json_match:
            results = json.loads(json_match.group())
            if isinstance(results, list):
                return results

        raise ValueError("No valid JSON array found in Hermes output")

    except subprocess.TimeoutExpired:
        print(f"[ERROR] Hermes CLI timed out after {LOCAL_LLM_TIMEOUT}s", file=sys.stderr)
        return None
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[ERROR] Hermes response parse failed: {e}", file=sys.stderr)
        return None


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LLM-based MBG sentiment classifier")
    parser.add_argument("input", help="JSON file with scraped articles")
    parser.add_argument("--output", default=None, help="Output JSON file")
    parser.add_argument("--mode", choices=["local", "hermes"], default="local",
                        help="LLM mode: local (endpoint) or hermes (Hermes CLI)")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    articles = data.get("articles", [])
    if not articles:
        print("No articles to process.", file=sys.stderr)
        return 0

    print(f"[LLM] Classifying {len(articles)} articles via {args.mode} LLM...",
          file=sys.stderr)

    if args.mode == "local":
        results = classify_local_llm(articles)
    else:
        results = classify_hermes_llm(articles)

    if results is None:
        print("[LLM] Classification failed. No output written.", file=sys.stderr)
        return 1

    if len(results) != len(articles):
        print(f"[WARN] Expected {len(articles)} results, got {len(results)}. "
              f"Padding/truncating.", file=sys.stderr)
        # Pad or truncate to match
        while len(results) < len(articles):
            results.append({"sentiment": "netral"})
        results = results[:len(articles)]

    # Apply sentiments to articles
    for a, r in zip(articles, results):
        sentiment = r.get("sentiment", "netral")
        if sentiment not in ("positif", "netral", "negatif"):
            sentiment = "netral"
        a["sentiment"] = sentiment

    result = {
        "classified_at": datetime.now().isoformat(),
        "method": f"llm-{args.mode}",
        "model": LOCAL_LLM_MODEL if args.mode == "local" else "hermes",
        "total_articles": len(articles),
        "articles": articles,
    }

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Classified {len(articles)} articles -> {args.output}")
    else:
        print(json.dumps(result, indent=2))

    # Print summary
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
