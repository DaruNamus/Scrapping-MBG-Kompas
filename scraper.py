#!/usr/bin/env python3
"""
MBG Scraper — Scrape Kompas.com articles tentang MBG (Makan Bergizi Gratis).
Sources: kompas.com/tag/MBG + kompas.com/tag/makan-bergizi-gratis
Output: JSON array of {title, url, date, snippet, source_tag}
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, date
from urllib.parse import urljoin

import requests

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}
BASE_URL = "https://www.kompas.com"

# Tag sources to scrape
TAGS = [
    {"slug": "MBG", "label": "MBG"},
    {"slug": "makan-bergizi-gratis", "label": "makan-bergizi-gratis"},
]

STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")
KNOWN_URLS_FILE = os.path.join(os.path.dirname(__file__), "known_urls.json")

DATE_START = date(2026, 1, 1)
DATE_END = date(2026, 6, 22)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_run": None, "processed_pages": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_known_urls():
    if os.path.exists(KNOWN_URLS_FILE):
        with open(KNOWN_URLS_FILE) as f:
            return set(json.load(f))
    return set()


def save_known_urls(urls):
    with open(KNOWN_URLS_FILE, "w") as f:
        json.dump(sorted(urls), f, indent=2)


def parse_article_date(date_str):
    """Parse '22 Juni 2026' to date object."""
    months_id = {
        "januari": 1, "februari": 2, "maret": 3, "april": 4,
        "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
        "september": 9, "oktober": 10, "november": 11, "desember": 12,
    }
    parts = date_str.strip().split()
    if len(parts) == 3:
        day = int(parts[0])
        month = months_id.get(parts[1].lower(), 1)
        year = int(parts[2])
        return date(year, month, day)
    return None


def extract_date_from_url(url):
    """Extract date from URL like /2026/06/22/..."""
    m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def scrape_tag_page(tag_slug, page=1):
    """Scrape a single tag page and return list of articles."""
    url = f"{BASE_URL}/tag/{tag_slug}"
    if page > 1:
        url += f"?page={page}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [ERROR] Failed to fetch {url}: {e}", file=sys.stderr)
        return [], False

    html = resp.text
    articles = []

    # Extract article items
    # Try multiple patterns for article items (different layouts)
    items = re.findall(
        r'<div class="articleItem[^"]*">(.*?)</div>\s*</div>\s*</div>',
        html, re.DOTALL
    )
    if not items:
        # Fallback pattern
        items = re.findall(
            r'<div class="articleItem">.*?</a>\s*</div>\s*</div>',
            html, re.DOTALL
        )

    for item in items:
        url_m = re.search(r'href="([^"]+)"', item)
        title_m = re.search(r'<h2 class="articleTitle">([^<]+)</h2>', item)

        if not (url_m and title_m):
            continue

        article_url = url_m.group(1)
        article_title = title_m.group(1).strip()

        # Date extraction: try articlePost-date first, then articleItem-date
        date_m = re.search(
            r'<div class="article(?:Post|Item)-date">([^<]+)</div>', item
        )
        article_date_str = date_m.group(1).strip() if date_m else ""
        article_date = parse_article_date(article_date_str)

        # Fallback: extract date from URL
        if not article_date:
            article_date = extract_date_from_url(article_url)

        # Lead/snippet: try articlePost-subtitle first, then fallback
        lead_m = re.search(r'<div class="articlePost-subtitle">([^<]+)</div>', item)
        if not lead_m:
            lead_m = re.search(r'<p class="articleItem-lead">([^<]+)</p>', item)

        articles.append({
            "title": article_title,
            "url": article_url,
            "date": article_date.isoformat() if article_date else None,
            "date_str": article_date_str,
            "snippet": lead_m.group(1).strip() if lead_m else "",
            "source_tag": tag_slug,
        })

    # Check if there's a next page
    has_next = bool(re.search(
        rf'href="[^"]*tag/{re.escape(tag_slug)}\?page={page + 1}"',
        html
    ))

    return articles, has_next


def fetch_article_body(url):
    """Fetch full article body text from <div class=\"read__content\">."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException:
        return ""

    html = resp.text
    body_m = re.search(
        r'<div class="read__content">(.*?)</div>\s*</div>\s*</div>\s*</div>',
        html, re.DOTALL
    )
    if body_m:
        text = re.sub(r'<[^>]+>', ' ', body_m.group(1))
        text = re.sub(r'\s+', ' ', text).strip()
        # Remove JS widget inline scripts (Kompas.id recommender)
        text = re.sub(r'var endpoint.*?xhr\.send\(\)[^;]*;', '', text, flags=re.DOTALL)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:2000]  # Cap at 2000 chars
    return ""


def get_max_pages(tag_slug, html):
    """Extract max page number from first page HTML."""
    pages = re.findall(
        r'data-ci-pagination-page="(\d+)"',
        html
    )
    if pages:
        return max(int(p) for p in pages)
    return 1


def main():
    parser = argparse.ArgumentParser(description="Scrape Kompas MBG articles")
    parser.add_argument("--backfill", action="store_true",
                        help="Full backfill from Jan 1 to today")
    parser.add_argument("--output", default=None,
                        help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    state = load_state()
    known_urls = load_known_urls()
    all_articles = []
    new_count = 0
    skipped_count = 0
    out_of_range_count = 0

    today = date.today()

    for tag in TAGS:
        slug = tag["slug"]
        label = tag["label"]
        print(f"[SCRAPER] Scraping tag/{slug}...", file=sys.stderr)

        if args.backfill:
            # First, get page 1 to find max pages
            print(f"  Fetching page 1 to discover total pages...", file=sys.stderr)
            articles, _ = scrape_tag_page(slug, page=1)
            for a in articles:
                if a["url"] not in known_urls:
                    known_urls.add(a["url"])
                    date_obj = date.fromisoformat(a["date"]) if a["date"] else None
                    if date_obj and DATE_START <= date_obj <= DATE_END:
                        all_articles.append(a)
                        new_count += 1
                    elif date_obj:
                        out_of_range_count += 1

            # Get max pages from first page HTML
            try:
                resp = requests.get(
                    f"{BASE_URL}/tag/{slug}", headers=HEADERS, timeout=30
                )
                max_pages = get_max_pages(slug, resp.text)
            except:
                max_pages = 1

            print(f"  Total pages for {slug}: {max_pages}", file=sys.stderr)

            # Scrape remaining pages
            for page in range(2, min(max_pages + 1, 500)):  # Safety cap at 500
                print(f"  Page {page}/{max_pages}...", file=sys.stderr)
                articles, _ = scrape_tag_page(slug, page=page)
                if not articles:
                    break

                for a in articles:
                    if a["url"] not in known_urls:
                        known_urls.add(a["url"])
                        date_obj = date.fromisoformat(a["date"]) if a["date"] else None
                        if date_obj and DATE_START <= date_obj <= DATE_END:
                            all_articles.append(a)
                            new_count += 1
                        elif date_obj:
                            out_of_range_count += 1

                time.sleep(0.5)  # Rate limiting

        else:
            # Incremental: only page 1
            articles, _ = scrape_tag_page(slug, page=1)
            for a in articles:
                if a["url"] not in known_urls:
                    known_urls.add(a["url"])
                    date_obj = date.fromisoformat(a["date"]) if a["date"] else None
                    if date_obj and DATE_START <= date_obj <= DATE_END:
                        all_articles.append(a)
                        new_count += 1
                    elif date_obj:
                        out_of_range_count += 1
                else:
                    skipped_count += 1

    # Deduplicate across tags (prefer MBG tag)
    seen_urls = set()
    deduped = []
    for a in sorted(all_articles, key=lambda x: x["date"] or "", reverse=True):
        if a["url"] not in seen_urls:
            seen_urls.add(a["url"])
            deduped.append(a)

    print(f"[SCRAPER] New: {new_count}, Deduped total: {len(deduped)}, "
          f"Skipped (known): {skipped_count}, Out of range: {out_of_range_count}",
          file=sys.stderr)

    # Fetch article bodies
    print(f"[SCRAPER] Fetching {len(deduped)} article bodies...", file=sys.stderr)
    for i, a in enumerate(deduped):
        print(f"  [{i+1}/{len(deduped)}] {a['title'][:50]}...", file=sys.stderr)
        a["body"] = fetch_article_body(a["url"])
        time.sleep(0.3)

    # Save state
    state["last_run"] = datetime.now().isoformat()
    save_state(state)
    save_known_urls(known_urls)

    # Output
    result = {
        "scraped_at": datetime.now().isoformat(),
        "total_articles": len(deduped),
        "articles": deduped,
    }

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"[SCRAPER] Saved {len(deduped)} articles to {args.output}",
              file=sys.stderr)
    else:
        print(json.dumps(result, indent=2))

    return len(deduped)


if __name__ == "__main__":
    sys.exit(main())
