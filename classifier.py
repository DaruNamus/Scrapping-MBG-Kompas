#!/usr/bin/env python3
"""
MBG Log Formatter — Format classified articles into daily log entries.
Each entry: title, isi news (snippet/lead), and sentiment.
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from collections import Counter


def group_articles_by_date(articles):
    """Group articles by their date string."""
    grouped = {}
    for a in articles:
        dt = a.get("date", "unknown")
        if dt not in grouped:
            grouped[dt] = []
        grouped[dt].append(a)
    return grouped


def build_log_entry(date_str, articles_with_sentiment):
    """
    Build a markdown log entry for one day's articles.
    Format per artikel: title + isi news (snippet) + sentiment
    """
    lines = []

    # Count sentiments
    counts = Counter(a["sentiment"] for a in articles_with_sentiment)
    pos = counts.get("positif", 0)
    net = counts.get("netral", 0)
    neg = counts.get("negatif", 0)
    total = len(articles_with_sentiment)

    # Header
    try:
        dt = date.fromisoformat(date_str)
        display_date = dt.strftime("%d %B %Y")
    except:
        display_date = date_str

    lines.append("")
    lines.append(f"## {display_date} — {total} artikel")
    lines.append("")
    lines.append(f"🟢 Positif: {pos} | 🟡 Netral: {net} | 🔴 Negatif: {neg}")
    lines.append("")

    # Articles sorted: negatif first, then netral, then positif
    sentiment_order = {"negatif": 0, "netral": 1, "positif": 2}
    sorted_articles = sorted(
        articles_with_sentiment,
        key=lambda a: (sentiment_order.get(a.get("sentiment", "netral"), 1), a.get("title", ""))
    )

    for i, a in enumerate(sorted_articles, 1):
        title = a.get("title", "—")
        url = a.get("url", "")
        body = a.get("body", "") or a.get("snippet", "") or "—"
        sentiment = a.get("sentiment", "netral")

        emoji = {"positif": "🟢", "netral": "🟡", "negatif": "🔴"}.get(sentiment, "⚪")

        lines.append(f"### {emoji} {i}. [{title}]({url})")
        lines.append(f"**Sentiment:** {sentiment}")
        lines.append("")
        lines.append(f"> {body}")
        lines.append("")

    return "\n".join(lines)


def build_summary(articles_with_sentiment):
    """Build a brief Telegram-ready summary string."""
    counts = Counter(a["sentiment"] for a in articles_with_sentiment)
    pos = counts.get("positif", 0)
    net = counts.get("netral", 0)
    neg = counts.get("negatif", 0)
    total = len(articles_with_sentiment)

    # Latest 3 articles
    latest = sorted(articles_with_sentiment,
                    key=lambda x: x.get("date", ""), reverse=True)[:3]

    lines = [f"📊 *MBG Sentiment Report*"]
    lines.append(f"📅 {datetime.now().strftime('%d %B %Y')}")
    lines.append("")
    lines.append(f"Total: {total} artikel baru")
    lines.append(f"🟢 Positif: {pos} | 🟡 Netral: {net} | 🔴 Negatif: {neg}")
    lines.append("")
    lines.append("*Headlines:*")
    for a in latest:
        emoji = {"positif": "🟢", "netral": "🟡", "negatif": "🔴"}.get(
            a.get("sentiment", ""), "⚪")
        lines.append(f"{emoji} [{a['title'][:60]}]({a['url']})")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Format classified articles into log entries"
    )
    parser.add_argument("input", help="JSON file with classified articles")
    parser.add_argument("--log-dir", default="log",
                        help="Directory to write daily log files")
    parser.add_argument("--summary", action="store_true",
                        help="Output Telegram summary only")
    parser.add_argument("--stdout", action="store_true",
                        help="Print formatted log to stdout instead of writing files")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    articles = data.get("articles", [])
    if not articles:
        print("No articles to process.", file=sys.stderr)
        return 0

    if args.summary:
        print(build_summary(articles))
        return 0

    # Group by date
    grouped = group_articles_by_date(articles)

    if args.stdout:
        # Print to stdout — for piped usage or preview
        for date_str in sorted(grouped.keys(), reverse=True):
            day_articles = grouped[date_str]
            log_content = build_log_entry(date_str, day_articles)
            print(log_content)
        return 0

    log_dir = args.log_dir
    os.makedirs(log_dir, exist_ok=True)

    for date_str in sorted(grouped.keys(), reverse=True):
        day_articles = grouped[date_str]
        log_content = build_log_entry(date_str, day_articles)

        # Write to date file
        try:
            dt = date.fromisoformat(date_str)
            filename = f"{dt.isoformat()}.md"
        except:
            filename = f"{date_str}.md"

        filepath = os.path.join(log_dir, filename)

        # Append if file exists
        if os.path.exists(filepath):
            with open(filepath, "a") as f:
                f.write(log_content)
        else:
            with open(filepath, "w") as f:
                f.write(f"# MBG Sentiment Log — {date_str}\n")
                f.write(log_content)

        print(f"[LOGGER] Wrote {len(day_articles)} articles to {filepath}",
              file=sys.stderr)

    # Also build summary
    summary = build_summary(articles)
    summary_path = os.path.join(log_dir, "_summary.txt")
    with open(summary_path, "w") as f:
        f.write(summary)

    print(f"[LOGGER] Summary saved to {summary_path}", file=sys.stderr)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
