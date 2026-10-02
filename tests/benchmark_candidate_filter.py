#!/usr/bin/env python3
"""
Candidate Filter Benchmark
===========================

Compares the baseline keyword-only filter against the new four-signal
OR-gate candidate funnel.

Methodology
-----------
1.  Fetch or generate a benchmark dataset of GDELT-like documents.
2.  Run the authoritative relevance classifier on ALL documents
    (not just those passing the candidate filter) to establish
    reference labels.
3.  Run both the baseline (keyword-only) and new (four-signal) filters.
4.  Compare recall, precision, candidate rate, and false negatives.

Reference classifier
--------------------
Uses the existing ZeroShotEventClassifier (event_classifier_v2.py)
Stage 1 relevance gate as the authoritative label:
    FINANCIAL_EVENT  → reference positive
    NO_MATERIAL_EVENT → reference negative

Usage
-----
    python src/ingestion/benchmark_candidate_filter.py

The script will attempt to fetch live GDELT data first. If the API
is unavailable or rate-limited, it falls back to a curated benchmark
dataset designed to exercise the vocabulary-gap failure mode.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.models import NewsDocument
from src.ingestion.entity_registry import EntityRegistry
from src.ingestion.processor import IngestionProcessor, CandidateResult
from src.ingestion.gdelt_client import GDELTClient


# ======================================================================
# 1. BENCHMARK DATASET CONSTRUCTION
# ======================================================================

def create_benchmark_registry() -> EntityRegistry:
    """
    Create an EntityRegistry with enough tracked entities to exercise
    the entity signal across diverse financial scenarios.
    """
    registry = EntityRegistry()
    entities = [
        {"entity_id": "ent_001", "canonical_name": "Apple Inc.", "ticker": "AAPL",
         "aliases": ["Apple", "the iPhone maker"]},
        {"entity_id": "ent_002", "canonical_name": "Microsoft Corporation", "ticker": "MSFT",
         "aliases": ["Microsoft", "the software giant"]},
        {"entity_id": "ent_003", "canonical_name": "Tesla Inc.", "ticker": "TSLA",
         "aliases": ["Tesla", "the EV maker"]},
        {"entity_id": "ent_004", "canonical_name": "Boeing Company", "ticker": "BA",
         "aliases": ["Boeing"]},
        {"entity_id": "ent_005", "canonical_name": "JPMorgan Chase", "ticker": "JPM",
         "aliases": ["JPMorgan", "JP Morgan", "Chase"]},
        {"entity_id": "ent_006", "canonical_name": "Goldman Sachs", "ticker": "GS",
         "aliases": ["Goldman"]},
        {"entity_id": "ent_007", "canonical_name": "Meta Platforms", "ticker": "META",
         "aliases": ["Meta", "Facebook"]},
        {"entity_id": "ent_008", "canonical_name": "Amazon.com Inc.", "ticker": "AMZN",
         "aliases": ["Amazon"]},
        {"entity_id": "ent_009", "canonical_name": "Alphabet Inc.", "ticker": "GOOGL",
         "aliases": ["Alphabet", "Google"]},
        {"entity_id": "ent_010", "canonical_name": "NVIDIA Corporation", "ticker": "NVDA",
         "aliases": ["Nvidia", "NVIDIA"]},
        {"entity_id": "ent_011", "canonical_name": "FTX Trading", "ticker": "FTX",
         "aliases": ["FTX"]},
        {"entity_id": "ent_012", "canonical_name": "Colonial Pipeline", "ticker": None,
         "aliases": ["Colonial Pipeline"]},
        {"entity_id": "ent_013", "canonical_name": "Moody's Corporation", "ticker": "MCO",
         "aliases": ["Moody's", "Moodys"]},
        {"entity_id": "ent_014", "canonical_name": "Deutsche Bank", "ticker": "DB",
         "aliases": ["Deutsche Bank"]},
        {"entity_id": "ent_015", "canonical_name": "Samsung Electronics", "ticker": "005930.KS",
         "aliases": ["Samsung"]},
        {"entity_id": "ent_016", "canonical_name": "Toyota Motor", "ticker": "TM",
         "aliases": ["Toyota"]},
        {"entity_id": "ent_017", "canonical_name": "Pfizer Inc.", "ticker": "PFE",
         "aliases": ["Pfizer"]},
        {"entity_id": "ent_018", "canonical_name": "Citigroup Inc.", "ticker": "C",
         "aliases": ["Citigroup", "Citi"]},
        {"entity_id": "ent_019", "canonical_name": "Wells Fargo", "ticker": "WFC",
         "aliases": ["Wells Fargo"]},
        {"entity_id": "ent_020", "canonical_name": "Intel Corporation", "ticker": "INTC",
         "aliases": ["Intel"]},
        {"entity_id": "ent_021", "canonical_name": "Berkshire Hathaway", "ticker": "BRK.B",
         "aliases": ["Berkshire Hathaway", "Berkshire"]},
        {"entity_id": "ent_022", "canonical_name": "Johnson & Johnson", "ticker": "JNJ",
         "aliases": ["Johnson & Johnson", "J&J"]},
        {"entity_id": "ent_023", "canonical_name": "ExxonMobil", "ticker": "XOM",
         "aliases": ["ExxonMobil", "Exxon Mobil", "Exxon"]},
        {"entity_id": "ent_024", "canonical_name": "Chevron Corporation", "ticker": "CVX",
         "aliases": ["Chevron"]},
        {"entity_id": "ent_025", "canonical_name": "Visa Inc.", "ticker": "V",
         "aliases": ["Visa"]},
    ]
    for ent in entities:
        registry.add_entity(ent)
    return registry


def _make_doc(title: str, domain: str = "news.example.com",
              url_suffix: str = "", body: Optional[str] = None,
              raw_metadata: Optional[Dict] = None) -> NewsDocument:
    """Helper to construct a NewsDocument for benchmarking."""
    url = f"https://{domain}/article/{url_suffix or hashlib.md5(title.encode()).hexdigest()}"
    doc_id = hashlib.sha256((url + title).encode("utf-8")).hexdigest()
    return NewsDocument(
        document_id=doc_id,
        source="GDELT",
        publisher=domain,
        title=title,
        body=body,
        url=url,
        published_at=datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        language="english",
        country="US",
        domain=domain,
        raw_metadata=raw_metadata or {"url": url, "title": title, "domain": domain,
                                       "seendate": "20240615120000", "language": "English"},
    )


def build_curated_benchmark() -> Tuple[List[NewsDocument], Dict[str, bool]]:
    """
    Build a curated dataset of documents designed to exercise the
    vocabulary-gap failure mode. Each document is labeled with the
    expected reference classification (True = financially relevant).

    This is used when live GDELT data cannot be fetched.
    The labels here serve as proxy reference labels. The actual benchmark
    will use the authoritative classifier for real GDELT data.
    """
    # Category 1: Financial events WITH keywords (both filters should keep)
    keyword_financial = [
        ("Major bank announces merger with regional lender", True),
        ("Tech company reports record earnings and raises guidance", True),
        ("Oil giant acquisition of shale producer valued at $20 billion", True),
        ("Federal Reserve raises interest rate by 25 basis points", True),
        ("Company files for bankruptcy protection after fraud scandal", True),
        ("Hedge fund takes activist stake in struggling retailer", True),
        ("FDA approves new cancer drug from pharmaceutical company", True),
        ("Class action lawsuit filed against social media platform", True),
        ("Company announces massive layoff of 10,000 employees", True),
        ("Antitrust regulators block proposed merger of airline companies", True),
        ("Government bond yield surges to 15-year high", True),
        ("Oil company earnings miss expectations by wide margin", True),
        ("Mining company restructuring plan includes asset sales", True),
        ("Shareholders approve dividend increase at annual meeting", True),
        ("Buyout firm targets struggling department store chain", True),
    ]

    # Category 2: Financial events WITHOUT keywords (baseline should drop, new should keep)
    # These are the critical vocabulary-gap cases
    no_keyword_financial = [
        ("FTX halts customer withdrawals amid liquidity crisis", True),
        ("Colonial Pipeline shuts down after ransomware attack", True),
        ("Tesla CFO resigns unexpectedly citing personal reasons", True),
        ("Boeing aircraft grounded worldwide after safety concerns", True),
        ("Moody's cuts company rating to junk status", True),
        ("Goldman warns of severe recession risk in next quarter", True),
        ("Amazon warehouse workers vote to form first union", True),
        ("Silicon Valley Bank collapses in largest failure since 2008", True),
        ("Credit Suisse emergency rescue by UBS announced overnight", True),
        ("NVIDIA chip export ban to China expands significantly", True),
        ("Samsung factory explosion disrupts global memory chip supply", True),
        ("Deutsche Bank faces $14 billion penalty from US regulators", True),
        ("Toyota recalls 3 million vehicles over safety defect", True),
        ("Apple supplier Foxconn halts production at major plant", True),
        ("Pfizer COVID vaccine trial data shows unexpected side effects", True),
        ("Google faces antitrust breakup threat from DOJ", True),
        ("JPMorgan suspends lending program for small businesses", True),
        ("Intel delays next-generation chip by 12 months", True),
        ("Wells Fargo employees caught opening fake accounts", True),
        ("Oil pipeline leak forces evacuation of coastal community", True),
        ("Central bank governor fired after policy disagreement", True),
        ("Shipping container shortage paralyzes global trade routes", True),
        ("Major airline cancels 2,000 flights during peak travel season", True),
        ("Country defaults on sovereign debt for first time", True),
        ("Insurance company denies claims after catastrophic hurricane", True),
        ("Crypto exchange CEO arrested for money laundering", True),
        ("Power grid failure leaves 10 million without electricity", True),
        ("Nuclear plant emergency shutdown triggers energy crisis", True),
        ("Commodity trading firm Trafigura reports record metals losses", True),
        ("OPEC slashes oil output by 2 million barrels per day", True),
    ]

    # Category 3: Financial events from trusted domains, no keywords
    trusted_domain_financial = [
        _make_doc("New tariffs spark trade tensions between major economies",
                  domain="reuters.com"),
        _make_doc("Regulators probe trading platform for market manipulation",
                  domain="bloomberg.com"),
        _make_doc("Private equity group completes take-private deal worth $8B",
                  domain="wsj.com"),
        _make_doc("Rating agency places country on negative outlook",
                  domain="ft.com"),
        _make_doc("Trading halted on exchange after technical glitch",
                  domain="cnbc.com"),
    ]
    trusted_domain_labels = {doc.document_id: True for doc in trusted_domain_financial}

    # Category 4: Non-financial articles (should be dropped by both filters)
    non_financial = [
        ("Local high school football team wins state championship", False),
        ("Celebrity couple announces wedding plans for summer", False),
        ("New recipe for chocolate cake goes viral on social media", False),
        ("Astronomers discover new exoplanet in habitable zone", False),
        ("City council approves new park renovation project", False),
        ("Film festival announces lineup for upcoming season", False),
        ("Weather forecast predicts sunny skies for the weekend", False),
        ("Museum opens new exhibition of ancient Egyptian artifacts", False),
        ("Popular TV show renewed for another season", False),
        ("Fashion week highlights new trends for spring collection", False),
        ("Marathon runner breaks personal record at city event", False),
        ("Book club discusses bestselling novel by debut author", False),
        ("Music festival announces headliner lineup for summer", False),
        ("Local bakery wins award for best sourdough bread", False),
        ("Cat video goes viral with 50 million views overnight", False),
        ("Travel blog recommends top 10 beaches for vacation", False),
        ("Cooking competition crowns new champion after intense finale", False),
        ("Community volunteers clean up local river on Saturday", False),
        ("New yoga studio opens downtown with free trial classes", False),
        ("Gardening tips for growing tomatoes in small spaces", False),
        ("Dog rescue organization finds homes for 100 animals", False),
        ("Art gallery features work of emerging local artists", False),
        ("Children's hospital hosts annual charity fundraiser gala", False),
        ("Olympic swimmer announces retirement after 20 years", False),
        ("Historical documentary wins award at film festival", False),
        ("New bike lane opens on busy downtown street", False),
        ("Science fair showcases student inventions at convention", False),
        ("Community theater presents classic Shakespeare play", False),
        ("Farmer's market adds new vendors for autumn season", False),
        ("Library hosts free coding workshop for teenagers", False),
    ]

    # Category 5: Ambiguous/edge cases from non-trusted domains, no keywords,
    # but with entity mentions
    entity_edge_cases = [
        ("Apple reportedly in talks with automakers for vehicle project", True),
        ("Microsoft outage affects cloud services worldwide", True),
        ("Tesla Cybertruck deliveries begin at Texas factory", True),
        ("Google launches new AI model competing with OpenAI", True),
        ("Amazon Prime Day breaks previous sales records", True),
    ]

    # Build the full dataset
    docs = []
    labels: Dict[str, bool] = {}

    for title, is_financial in (keyword_financial + no_keyword_financial
                                 + non_financial + entity_edge_cases):
        doc = _make_doc(title)
        docs.append(doc)
        labels[doc.document_id] = is_financial

    # Add trusted domain docs
    docs.extend(trusted_domain_financial)
    labels.update(trusted_domain_labels)

    return docs, labels


def try_fetch_gdelt_data(target_count: int = 5000) -> Optional[List[Dict[str, Any]]]:
    """
    Attempt to fetch live GDELT data for the benchmark.
    Returns None if the API is unavailable or rate-limited.
    """
    client = GDELTClient()

    queries = [
        "economy OR market OR trade",
        "company OR business OR corporate",
        "government OR policy OR regulation",
        "technology OR science OR health",
        "sports OR entertainment OR culture",
        "weather OR environment OR climate",
        "crime OR security OR conflict",
    ]

    all_articles = []
    seen_urls = set()
    per_query = max(250, target_count // len(queries))

    for query in queries:
        if len(all_articles) >= target_count:
            break
        try:
            print(f"  Fetching GDELT: query='{query}', max={per_query}...")
            articles = client.fetch_live(query=query, max_records=per_query)
            for art in articles:
                url = art.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_articles.append(art)
            print(f"    Got {len(articles)} articles, total unique: {len(all_articles)}")
            time.sleep(5)  # Respect rate limits
        except Exception as e:
            print(f"    GDELT fetch failed: {e}")
            if len(all_articles) == 0:
                return None

    if len(all_articles) < 50:
        return None

    return all_articles[:target_count]


# ======================================================================
# 2. AUTHORITATIVE REFERENCE CLASSIFIER
# ======================================================================

def classify_financial_relevance_batch(
    docs: List[NewsDocument],
    batch_size: int = 32,
    device: Optional[str] = None,
) -> Dict[str, bool]:
    """
    Run the authoritative financial relevance classifier on ALL documents.

    Uses the two-stage zero-shot classifier from event_classifier_v2.py
    Stage 1 relevance gate:
        FINANCIAL_EVENT → True
        NO_MATERIAL_EVENT → False

    This MUST run on all documents, not just those passing the candidate
    filter, otherwise we cannot measure false negatives.

    Returns:
        dict mapping document_id → is_financially_relevant
    """
    try:
        import torch
        from transformers import pipeline

        RELEVANCE_DESCRIPTIONS = [
            "The text contains a concrete, potentially material financial, economic, corporate, "
            "market, regulatory, geopolitical, commodity, credit, product, or technology event "
            "that could affect a company, asset, sector, market, or portfolio.",
            "The text is primarily casual conversation, personal opinion, entertainment, "
            "advertising, shopping, customer service, fandom, generic social media chatter, "
            "or other content without a concrete material financial or economic event.",
        ]

        torch_device = device
        if torch_device is None:
            torch_device = 0 if torch.cuda.is_available() else -1
        else:
            torch_device = int(torch_device) if torch_device.lstrip("-").isdigit() else -1

        torch_dtype = (
            torch.float16
            if (torch.cuda.is_available() and torch_device != -1)
            else torch.float32
        )

        print(f"\n[Classifier] Loading MoritzLaurer/deberta-v3-base-zeroshot-v2.0...")
        print(f"[Classifier] device={torch_device}, dtype={torch_dtype}")

        classifier = pipeline(
            "zero-shot-classification",
            model="MoritzLaurer/deberta-v3-base-zeroshot-v2.0",
            device=torch_device,
            torch_dtype=torch_dtype,
        )

        texts = [f"{doc.title} {doc.body or ''}".strip() for doc in docs]
        labels = {}

        chunk_size = 200
        for start in range(0, len(texts), chunk_size):
            chunk_texts = texts[start:start + chunk_size]
            chunk_docs = docs[start:start + chunk_size]

            results = classifier(
                chunk_texts,
                candidate_labels=RELEVANCE_DESCRIPTIONS,
                hypothesis_template="This text is about {}.",
                multi_label=False,
                batch_size=batch_size,
            )

            # Single result is not wrapped in a list
            if isinstance(results, dict):
                results = [results]

            for doc, result in zip(chunk_docs, results):
                top_label = result["labels"][0]
                is_financial = (top_label == RELEVANCE_DESCRIPTIONS[0])
                labels[doc.document_id] = is_financial

            print(f"  Classified {min(start + chunk_size, len(docs))}/{len(docs)} documents")

        return labels

    except Exception as e:
        print(f"\n[Classifier] FAILED to load authoritative classifier: {e}")
        print("[Classifier] Falling back to curated labels.")
        return {}


# ======================================================================
# 3. BENCHMARK EXECUTION
# ======================================================================

@dataclass
class BenchmarkMetrics:
    total_documents: int = 0
    reference_financial_documents: int = 0
    reference_nonfinancial_documents: int = 0

    baseline_keyword_kept: int = 0
    baseline_keyword_dropped: int = 0
    new_filter_kept: int = 0
    new_filter_dropped: int = 0

    baseline_recall: float = 0.0
    new_filter_recall: float = 0.0
    baseline_precision: float = 0.0
    new_filter_precision: float = 0.0
    baseline_candidate_rate: float = 0.0
    new_filter_candidate_rate: float = 0.0

    false_negatives_baseline: int = 0
    false_negatives_new_filter: int = 0
    false_positives_baseline: int = 0
    false_positives_new_filter: int = 0


def run_benchmark():
    print("=" * 72)
    print("CANDIDATE FILTER BENCHMARK")
    print("=" * 72)

    # ------------------------------------------------------------------
    # Step 1: Obtain benchmark data
    # ------------------------------------------------------------------
    print("\n--- Step 1: Obtain benchmark data ---")

    use_curated = True
    gdelt_articles = None

    print("Attempting to fetch live GDELT data (target: 5000 documents)...")
    gdelt_articles = try_fetch_gdelt_data(target_count=5000)

    if gdelt_articles and len(gdelt_articles) >= 50:
        print(f"\nFetched {len(gdelt_articles)} live GDELT articles.")
        use_curated = False
    else:
        print("\nGDELT API unavailable or insufficient data. Using curated benchmark dataset.")
        use_curated = True

    # ------------------------------------------------------------------
    # Step 2: Build registry and processor
    # ------------------------------------------------------------------
    print("\n--- Step 2: Initialize components ---")
    registry = create_benchmark_registry()
    processor = IngestionProcessor(registry=registry)

    # ------------------------------------------------------------------
    # Step 3: Normalize and prepare documents
    # ------------------------------------------------------------------
    print("\n--- Step 3: Prepare documents ---")

    if use_curated:
        docs, curated_labels = build_curated_benchmark()
        print(f"Curated benchmark: {len(docs)} documents")
        print(f"  Financial (curated label): {sum(1 for v in curated_labels.values() if v)}")
        print(f"  Non-financial (curated label): {sum(1 for v in curated_labels.values() if not v)}")
    else:
        client = GDELTClient()
        docs = client.normalize(gdelt_articles)
        curated_labels = {}
        print(f"Normalized {len(docs)} GDELT documents")

    if len(docs) == 0:
        print("ERROR: No documents to benchmark. Aborting.")
        return

    # ------------------------------------------------------------------
    # Step 4: Run authoritative classifier on ALL documents
    # ------------------------------------------------------------------
    print("\n--- Step 4: Authoritative relevance classification ---")
    print(f"Running classifier on ALL {len(docs)} documents...")
    print("(This is required to measure false negatives correctly.)")

    classifier_labels = classify_financial_relevance_batch(docs, batch_size=32)

    # Merge: prefer classifier labels; fall back to curated labels
    reference_labels: Dict[str, bool] = {}
    if classifier_labels:
        reference_labels = classifier_labels
        label_source = "authoritative_classifier"
        print(f"\nUsing authoritative classifier labels for {len(classifier_labels)} documents")
    else:
        reference_labels = curated_labels
        label_source = "curated_proxy"
        print(f"\nUsing curated proxy labels for {len(curated_labels)} documents")

    n_ref_financial = sum(1 for v in reference_labels.values() if v)
    n_ref_non = sum(1 for v in reference_labels.values() if not v)
    print(f"  Reference financial: {n_ref_financial}")
    print(f"  Reference non-financial: {n_ref_non}")

    if n_ref_financial == 0:
        print("WARNING: Zero reference financial documents. Recall is undefined.")

    # ------------------------------------------------------------------
    # Step 5: Run baseline keyword-only filter
    # ------------------------------------------------------------------
    print("\n--- Step 5: Baseline keyword-only filter ---")
    t_baseline_start = time.time()
    baseline_kept_docs = processor.financial_relevance_filter(docs)
    t_baseline_end = time.time()

    baseline_kept_ids = {d.document_id for d in baseline_kept_docs}
    baseline_time = t_baseline_end - t_baseline_start

    print(f"  Kept: {len(baseline_kept_ids)} / {len(docs)}")
    print(f"  Time: {baseline_time:.4f}s")

    # ------------------------------------------------------------------
    # Step 6: Run new four-signal filter
    # ------------------------------------------------------------------
    print("\n--- Step 6: New four-signal candidate filter ---")
    t_new_start = time.time()
    candidate_results = processor.candidate_filter(docs)
    t_new_end = time.time()

    new_kept = [cr for cr in candidate_results if cr.kept]
    new_dropped = [cr for cr in candidate_results if not cr.kept]
    new_kept_ids = {cr.document.document_id for cr in new_kept}
    new_time = t_new_end - t_new_start

    print(f"  Kept: {len(new_kept)} / {len(docs)}")
    print(f"  Time: {new_time:.4f}s")

    # ------------------------------------------------------------------
    # Step 7: Compute metrics
    # ------------------------------------------------------------------
    print("\n--- Step 7: Compute metrics ---")

    metrics = BenchmarkMetrics()
    metrics.total_documents = len(docs)
    metrics.reference_financial_documents = n_ref_financial
    metrics.reference_nonfinancial_documents = n_ref_non

    metrics.baseline_keyword_kept = len(baseline_kept_ids)
    metrics.baseline_keyword_dropped = len(docs) - len(baseline_kept_ids)
    metrics.new_filter_kept = len(new_kept)
    metrics.new_filter_dropped = len(new_dropped)

    # True positives / false negatives for baseline
    baseline_tp = sum(1 for did, is_fin in reference_labels.items()
                      if is_fin and did in baseline_kept_ids)
    baseline_fn = sum(1 for did, is_fin in reference_labels.items()
                      if is_fin and did not in baseline_kept_ids)
    baseline_fp = sum(1 for did, is_fin in reference_labels.items()
                      if not is_fin and did in baseline_kept_ids)

    # True positives / false negatives for new filter
    new_tp = sum(1 for did, is_fin in reference_labels.items()
                 if is_fin and did in new_kept_ids)
    new_fn = sum(1 for did, is_fin in reference_labels.items()
                 if is_fin and did not in new_kept_ids)
    new_fp = sum(1 for did, is_fin in reference_labels.items()
                 if not is_fin and did in new_kept_ids)

    metrics.false_negatives_baseline = baseline_fn
    metrics.false_negatives_new_filter = new_fn
    metrics.false_positives_baseline = baseline_fp
    metrics.false_positives_new_filter = new_fp

    # Recall
    if n_ref_financial > 0:
        metrics.baseline_recall = baseline_tp / n_ref_financial
        metrics.new_filter_recall = new_tp / n_ref_financial
    else:
        metrics.baseline_recall = 0.0
        metrics.new_filter_recall = 0.0

    # Precision
    if metrics.baseline_keyword_kept > 0:
        metrics.baseline_precision = baseline_tp / metrics.baseline_keyword_kept
    if metrics.new_filter_kept > 0:
        metrics.new_filter_precision = new_tp / metrics.new_filter_kept

    # Candidate rate
    if metrics.total_documents > 0:
        metrics.baseline_candidate_rate = metrics.baseline_keyword_kept / metrics.total_documents
        metrics.new_filter_candidate_rate = metrics.new_filter_kept / metrics.total_documents

    # ------------------------------------------------------------------
    # Step 8: Report metrics
    # ------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("BENCHMARK RESULTS")
    print("=" * 72)
    print(f"Label source: {label_source}")
    print()

    report_lines = [
        f"total_documents:              {metrics.total_documents}",
        f"reference_financial_documents:{metrics.reference_financial_documents}",
        f"reference_nonfinancial_documents:{metrics.reference_nonfinancial_documents}",
        "",
        f"baseline_keyword_kept:        {metrics.baseline_keyword_kept}",
        f"baseline_keyword_dropped:     {metrics.baseline_keyword_dropped}",
        f"new_filter_kept:              {metrics.new_filter_kept}",
        f"new_filter_dropped:           {metrics.new_filter_dropped}",
        "",
        f"baseline_recall:              {metrics.baseline_recall:.4f}",
        f"new_filter_recall:            {metrics.new_filter_recall:.4f}",
        f"baseline_precision:           {metrics.baseline_precision:.4f}",
        f"new_filter_precision:         {metrics.new_filter_precision:.4f}",
        "",
        f"baseline_candidate_rate:      {metrics.baseline_candidate_rate:.4f}",
        f"new_filter_candidate_rate:    {metrics.new_filter_candidate_rate:.4f}",
        "",
        f"false_negatives_baseline:     {metrics.false_negatives_baseline}",
        f"false_negatives_new_filter:   {metrics.false_negatives_new_filter}",
        f"false_positives_baseline:     {metrics.false_positives_baseline}",
        f"false_positives_new_filter:   {metrics.false_positives_new_filter}",
    ]
    for line in report_lines:
        print(f"  {line}")

    # ------------------------------------------------------------------
    # Step 9: Success criteria check
    # ------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("SUCCESS CRITERIA")
    print("=" * 72)

    recall_improved = metrics.new_filter_recall > metrics.baseline_recall
    print(f"  NEW FILTER RECALL > BASELINE RECALL: "
          f"{metrics.new_filter_recall:.4f} > {metrics.baseline_recall:.4f} -> "
          f"{'PASS [YES]' if recall_improved else 'FAIL [NO]'}")

    candidate_rate_useful = metrics.new_filter_candidate_rate < 1.0
    print(f"  Candidate rate < 100%: "
          f"{metrics.new_filter_candidate_rate:.4f} -> "
          f"{'PASS [YES]' if candidate_rate_useful else 'WARNING: filter not saving compute'}")

    if metrics.new_filter_candidate_rate > 0.95:
        print(f"  WARNING: Candidate rate is {metrics.new_filter_candidate_rate:.1%}. "
              f"Filter may not be saving enough downstream compute.")

    # ------------------------------------------------------------------
    # Step 10: False-negative audit
    # ------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("FALSE-NEGATIVE AUDIT")
    print("=" * 72)

    # Documents rescued by the new filter
    rescued = []
    for cr in candidate_results:
        did = cr.document.document_id
        ref = reference_labels.get(did)
        if ref and cr.kept and did not in baseline_kept_ids:
            rescued.append(cr)

    print(f"\n--- RESCUED: REFERENCE=FINANCIAL, BASELINE=DROPPED, NEW=KEPT ---")
    print(f"(Documents rescued by the new funnel: {len(rescued)})")
    for i, cr in enumerate(rescued[:20], 1):
        reasons = " + ".join(sorted(cr.reasons))
        print(f"  {i:2d}. [{reasons:20s}] {cr.document.title[:80]}")
        if cr.resolved_entity_ids:
            print(f"      Entities: {', '.join(cr.resolved_entity_ids)}")

    if len(rescued) > 20:
        print(f"  ... and {len(rescued) - 20} more rescued documents")

    # Documents still dropped by the new filter
    still_dropped = []
    for cr in candidate_results:
        did = cr.document.document_id
        ref = reference_labels.get(did)
        if ref and not cr.kept:
            still_dropped.append(cr)

    print(f"\n--- REMAINING FAILURES: REFERENCE=FINANCIAL, NEW FILTER=DROPPED ---")
    print(f"(These are the most important failures: {len(still_dropped)})")
    for i, cr in enumerate(still_dropped[:20], 1):
        print(f"  {i:2d}. {cr.document.title[:90]}")
        print(f"      domain={cr.document.domain}, entity_signal={cr.entity_signal}, "
              f"keyword_signal={cr.keyword_signal}")

    if len(still_dropped) == 0:
        print("  None — all reference-financial documents were retained.")
    elif len(still_dropped) > 20:
        print(f"  ... and {len(still_dropped) - 20} more dropped financial documents")

    if still_dropped:
        print("\n  [!]  WARNING: New filter still drops financial events.")
        print("  Inspect the failure cases above before proceeding.")

    # ------------------------------------------------------------------
    # Step 11: Signal attribution
    # ------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("SIGNAL ATTRIBUTION (kept documents)")
    print("=" * 72)

    reason_combos = Counter()
    single_signal_counts = Counter()

    for cr in new_kept:
        combo_key = " + ".join(sorted(cr.reasons))
        reason_combos[combo_key] += 1
        for r in cr.reasons:
            single_signal_counts[r] += 1

    print("\n  Individual signal contribution (how many kept docs each signal fired for):")
    for signal, count in single_signal_counts.most_common():
        pct = count / len(new_kept) * 100 if new_kept else 0
        print(f"    {signal:15s} : {count:5d} ({pct:5.1f}%)")

    print(f"\n  Reason combinations (how documents were retained):")
    for combo, count in reason_combos.most_common():
        pct = count / len(new_kept) * 100 if new_kept else 0
        print(f"    {combo:30s} : {count:5d} ({pct:5.1f}%)")

    # ------------------------------------------------------------------
    # Step 12: Performance benchmark
    # ------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("PERFORMANCE BENCHMARK")
    print("=" * 72)

    # Measure candidate filter throughput on a larger batch
    perf_docs = docs * max(1, 1000 // len(docs))  # Scale up for timing
    perf_docs = perf_docs[:5000]  # Cap at 5000

    print(f"\n  Timing candidate_filter on {len(perf_docs)} documents...")

    t0 = time.time()
    _ = processor.candidate_filter(perf_docs)
    t1 = time.time()

    filter_seconds = t1 - t0
    docs_per_sec = len(perf_docs) / filter_seconds if filter_seconds > 0 else 0

    # Separately measure entity extraction cost
    t2 = time.time()
    for doc in perf_docs[:500]:
        _ = processor.extract_entities(doc)
    t3 = time.time()
    entity_extraction_seconds = t3 - t2
    entity_per_sec = 500 / entity_extraction_seconds if entity_extraction_seconds > 0 else 0

    print(f"  candidate_filter_seconds:   {filter_seconds:.4f}")
    print(f"  documents_per_second:        {docs_per_sec:.1f}")
    print(f"  ms_per_document:             {(filter_seconds / len(perf_docs) * 1000):.2f}")
    print()
    print(f"  Entity extraction (500 docs):")
    print(f"    total_seconds:             {entity_extraction_seconds:.4f}")
    print(f"    entities_per_second:       {entity_per_sec:.1f}")
    print(f"    ms_per_entity_extraction:  {(entity_extraction_seconds / 500 * 1000):.2f}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"  Recall improvement:  {metrics.baseline_recall:.4f} -> {metrics.new_filter_recall:.4f} "
          f"({'UP' if recall_improved else 'FLAT/DOWN'} "
          f"{(metrics.new_filter_recall - metrics.baseline_recall) * 100:+.1f}pp)")
    print(f"  Precision change:    {metrics.baseline_precision:.4f} -> {metrics.new_filter_precision:.4f}")
    print(f"  Candidate rate:      {metrics.baseline_candidate_rate:.4f} -> {metrics.new_filter_candidate_rate:.4f}")
    print(f"  False negatives:     {metrics.false_negatives_baseline} -> {metrics.false_negatives_new_filter}")
    print(f"  Rescued documents:   {len(rescued)}")
    print(f"  Remaining failures:  {len(still_dropped)}")
    print(f"  Throughput:          {docs_per_sec:.0f} docs/sec")

    if recall_improved:
        print(f"\n  [SUCCESS]: New filter recall ({metrics.new_filter_recall:.4f}) > "
              f"baseline recall ({metrics.baseline_recall:.4f})")
    else:
        print(f"\n  [FAILURE]: New filter recall did not improve over baseline.")

    print("\n" + "=" * 72)
    print("BENCHMARK COMPLETE — STOP")
    print("=" * 72)


if __name__ == "__main__":
    run_benchmark()
