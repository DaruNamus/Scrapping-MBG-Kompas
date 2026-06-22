#!/usr/bin/env python3
"""
Classify articles using a simple rule-based approach when run outside the cron.
This is the fallback/standalone classifier. 
For cron jobs, classification is done by the Hermes LLM (see cron prompt).
"""

import json
import re
import sys

# Indonesian sentiment indicators for MBG context
POSITIF_WORDS = [
    "berhasil", "sukses", "tepat sasaran", "membantu", "bermanfaat",
    "dukung", "mendukung", "apresiasi", "pujian", "positif", "baik",
    "lancar", "manfaat", "sejahtera", "cerdas", "sehat", "gizi baik",
    "tepat waktu", "transparan", "efektif", "memadai", "cukup",
    "tepat guna", "solusi", "kemajuan", "peningkatan", "berdampak baik",
    "patut dicontoh", "berjalan baik", "sukses", "berdaya guna",
    "mengapresiasi", "bangga", "puas", "senang", "terbantu",
    "layak", "penting", "progres", "perbaikan", "optimal",
]

NETRAL_WORDS = [
    "rencana", "kebijakan", "program", "pemerintah", "anggaran",
    "target", "evaluasi", "data", "laporan", "sosialisasi",
    "diresmikan", "diluncurkan", "disosialisasikan", "berjalan",
    "proses", "tahap", "persiapan", "realisasi", "penyaluran",
    "penerima", "penerima manfaat", "siswa", "sekolah",
    "satuan pendidikan", "bgn", "badan gizi nasional",
    "sppg", "dapur", "menu", "kabupaten", "kota",
    "provinsi", "anggaran", "alokasi", "implementasi",
]

NEGATIF_WORDS = [
    "korupsi", "gagal", "kritik", "polemik", "kontroversi",
    "masalah", "kendala", "hambatan", "buruk", "jelek",
    "penolakan", "demo", "protes", "tuntut", "menuntut",
    "keluhan", "kesulitan", "terhambat", "mangkrak", "stagnan",
    "dana mengendap", "mark up", "mark-up", "markup",
    "tidak tepat", "salah sasaran", "bocor", " diselewengkan",
    "merugikan", "mencemaskan", "khawatir", "resah",
    "kekhawatiran", "keterbatasan", "minim", "belum optimal",
    "terkendala", "ditunda", "dihentikan", "bermasalah",
    "dana membengkak", "tidak efektif", "tidak efisien",
    "mengkhawatirkan", "ancaman", "darurat", "krisis",
    "carut-marut", "amburadul", "rawan", "problematik",
]


def classify_article(title, snippet, body=""):
    """Simple rule-based classifier. Returns one of: positif, netral, negatif."""
    text = (title + " " + snippet + " " + body).lower()
    
    # Count sentiment indicators
    pos_score = sum(1 for w in POSITIF_WORDS if w in text)
    neg_score = sum(1 for w in NEGATIF_WORDS if w in text)
    net_score = sum(1 for w in NETRAL_WORDS if w in text)
    
    if neg_score > pos_score and neg_score >= 2:
        return "negatif"
    elif pos_score > neg_score and pos_score >= 2:
        return "positif"
    else:
        return "netral"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Rule-based MBG sentiment classifier")
    parser.add_argument("input", help="JSON file with scraped articles")
    parser.add_argument("--output", default=None, help="Output JSON file")
    args = parser.parse_args()
    
    with open(args.input) as f:
        data = json.load(f)
    
    articles = data.get("articles", [])
    for a in articles:
        a["sentiment"] = classify_article(
            a.get("title", ""),
            a.get("snippet", ""),
            a.get("body", "")
        )
    
    result = {
        "classified_at": __import__("datetime").datetime.now().isoformat(),
        "method": "rule-based",
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
    from collections import Counter
    counts = Counter(a["sentiment"] for a in articles)
    print(f"\nSentiment distribution: Positif={counts.get('positif', 0)}, "
          f"Netral={counts.get('netral', 0)}, Negatif={counts.get('negatif', 0)}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
