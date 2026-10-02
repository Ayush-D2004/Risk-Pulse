#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Credit-event data availability audit — plain-CSV variant.

Adapted from credit_event_data_audit.py to read already-extracted CSV files
directly, without requiring a zip archive.

Usage:
    python src/analysis/credit_event_data_audit_csv.py \
        --input data/processed/reduced_dataset-release.csv \
        --sample-limit 25

    python src/analysis/credit_event_data_audit_csv.py \
        --input data/processed/full_dataset-release.csv \
        --sample-limit 25
"""

import argparse
import csv
import re
import sys
from collections import Counter


STRONG_PATTERNS = {
    "default": [
        r"\bdefaulted\b",
        r"\bdefaults?\b",
        r"\bdefault\b",
    ],
    "bankruptcy": [
        r"\bfiled for bankruptcy\b",
        r"\bfiled bankruptcy\b",
        r"\bdeclared bankruptcy\b",
        r"\bentered bankruptcy\b",
        r"\bbankruptcy protection\b",
        r"\bchapter\s+(?:7|11|15)\b",
    ],
    "debt_restructuring": [
        r"\bdebt restructuring\b",
        r"\brestructuring (?:its |the )?debt\b",
        r"\brestructure (?:its |the )?debt\b",
    ],
    "insolvency": [
        r"\binsolvency\b",
        r"\binsolvent\b",
    ],
    "credit_rating": [
        r"\bcredit rating\b",
        r"\bcredit downgrade\b",
        r"\bcredit downgraded\b",
        r"\brating downgrade\b",
        r"\brating downgraded\b",
    ],
    "bond_default": [
        r"\bbond default\b",
        r"\bdefault(?:ed)? on .*bond\b",
        r"\bdefault(?:ed)? on .*debt\b",
        r"\bdefault(?:ed)? on .*loan\b",
    ],
    "missed_payment": [
        r"\bmissed (?:loan|debt|bond|interest) payments?\b",
        r"\bmissed payments?\b",
        r"\bmissed .*payment\b",
    ],
    "covenant": [
        r"\bcovenant breach\b",
        r"\bdebt covenant\b",
    ],
}

WEAK_CONTEXT = [
    r"\bdefault (?:ip|app|setting|password|browser|search)\b",
    r"\bdefault(?:ly)?\b",
    r"\bmorally bankrupt\b",
    r"\b(?:i|we|you|they|he|she) .*go bankrupt\b",
    r"\bboycott.*bankrupt",
    r"\b(?:car|house|personal|student) .*bankrupt",
    r"\bchapter 7.*eBay\b",
]

CORPORATE_ANCHORS = [
    r"\b(?:company|bank|lender|borrower|firm|corporation|corp|fund|issuer)\b",
    r"\b(?:debt|loan|bond|bonds|credit|rating|payment|financing)\b",
    r"\b(?:revenue|earnings|balance sheet|liabilities|capital)\b",
    r"\b(?:Reuters|Bloomberg|CNBC|WSJ)\b",
    r"@\b(?:GoldmanSachs|MorganStanley|DeutscheBank|JPMorgan|WellsFargo|Citi|BankofAmerica)\b",
]


def norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def match_categories(text):
    hits = []
    for category, patterns in STRONG_PATTERNS.items():
        if any(re.search(p, text, re.I) for p in patterns):
            hits.append(category)
    return hits


def is_weak_context(text):
    return any(re.search(p, text, re.I) for p in WEAK_CONTEXT)


def has_corporate_anchor(text):
    return any(re.search(p, text, re.I) for p in CORPORATE_ANCHORS)


def scan_csv(path, sample_limit):
    counts = Counter()
    strong_rows = []
    weak_rows = []
    all_hits = 0
    total_rows = 0

    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row_number, row in enumerate(reader, start=2):
            total_rows += 1
            text = norm(row.get("TWEET", ""))
            if not text:
                continue

            categories = match_categories(text)
            if not categories:
                continue

            all_hits += 1
            for c in categories:
                counts[c] += 1

            weak = is_weak_context(text)
            anchored = has_corporate_anchor(text)

            record = {
                "row_number": row_number,
                "stock":      str(row.get("STOCK") or ""),
                "date":       str(row.get("DATE") or ""),
                "text":       text,
                "categories": categories,
                "anchored":   anchored,
                "weak":       weak,
            }

            if anchored and not weak:
                if len(strong_rows) < sample_limit:
                    strong_rows.append(record)
            else:
                if len(weak_rows) < sample_limit:
                    weak_rows.append(record)

    return total_rows, counts, all_hits, strong_rows, weak_rows


def print_report(name, total_rows, counts, all_hits, strong_rows, weak_rows):
    print()
    print("=" * 80)
    print(f"DATASET: {name}")
    print("=" * 80)
    print(f"Total rows scanned            : {total_rows:,}")
    print(f"Total lexical credit-hit rows : {all_hits:,}")
    pct = 100 * all_hits / total_rows if total_rows else 0
    print(f"Coverage                      : {pct:.2f}%")

    print("\nHits by category:")
    if counts:
        for k, v in counts.most_common():
            print(f"  {k:25s} {v:>8,}")
    else:
        print("  None")

    strong_anchored = [r for r in strong_rows if r["anchored"] and not r["weak"]]
    print(f"\nStrong corporate-credit candidates (anchored, not weak): {len(strong_anchored)} shown")
    print("-" * 80)
    if strong_anchored:
        for r in strong_anchored:
            cats = ", ".join(r["categories"])
            print(f"  row={r['row_number']:>7}  stock={r['stock']:<20}  date={r['date']}  [{cats}]")
            print(f"    {r['text']}")
    else:
        print("  None found in sample")

    print(f"\nWeak / ambiguous lexical matches: {len(weak_rows)} shown")
    print("-" * 80)
    if weak_rows:
        for r in weak_rows:
            cats = ", ".join(r["categories"])
            print(f"  row={r['row_number']:>7}  stock={r['stock']:<20}  date={r['date']}  [{cats}]")
            print(f"    {r['text']}")
    else:
        print("  None found")


def parse_args():
    p = argparse.ArgumentParser(
        description="Credit-event data availability audit (plain CSV version)"
    )
    p.add_argument("--input", required=True, help="Path to the raw CSV dataset")
    p.add_argument("--sample-limit", type=int, default=25,
                   help="Max example rows to print per bucket (default: 25)")
    return p.parse_args()


def main():
    # Ensure clean Unicode output on Windows
    if hasattr(sys.stdout, "buffer"):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    args = parse_args()
    name = args.input.split("/")[-1].split("\\")[-1]

    print(f"Scanning: {args.input}")
    total_rows, counts, all_hits, strong_rows, weak_rows = scan_csv(
        args.input, args.sample_limit
    )
    print_report(name, total_rows, counts, all_hits, strong_rows, weak_rows)


if __name__ == "__main__":
    main()
