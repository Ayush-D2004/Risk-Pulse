#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Event Materiality Classifier v4
================================
Second-stage filter for the financial-event pipeline.

Input:
    event_baseline.csv produced by event_classifier_v2.py

Output columns added:
    EVENT_MATERIALITY        - MATERIAL_EVENT | NON_MATERIAL_FINANCIAL_CONTENT | NO_EVENT
    FINAL_EVENT_TYPE         - Canonical event type for downstream risk scoring, or NO_EVENT
    EVENT_MATERIALITY_REASON - Auditable trace of the classification decision

Design goals (lessons learned from v1/v2/v3):
    - FINANCIAL_RELEVANCE gate is authoritative; rows not labelled FINANCIAL_EVENT
      are always NO_EVENT without entering any rule logic (critical v3 bug fix).
    - NON_MATERIAL rows always carry FINAL_EVENT_TYPE = "NO_EVENT" (v3 bug fix).
    - Hard context suppressions run before positive rules and are scalpel-tight;
      every entry is justified by a real false-positive seen in the baseline data.
    - Positive rules cover the paraphrase gaps that v2/v3 missed: Buffett $12B
      stock buy, Bayer/Monsanto #mergerfromhell hashtag, Rosneft 19.5% stake,
      Oracle buys Apiary.
    - Cross-type scan rescues rows labelled "Other / Unclear" upstream and rows
      mislabelled by the event classifier (the single largest v3 false-negative
      source).
    - EVENT_CONFIDENCE score is used as a low-confidence guard: very weak hits
      below the threshold are not promoted to MATERIAL.
"""

import argparse
import re
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Tuning knob
# ---------------------------------------------------------------------------

LOW_CONF_THRESHOLD = 0.20   # Below this, short/weak pattern hits are suppressed.


# ---------------------------------------------------------------------------
# Hard global suppression lists
# Applied before any positive rule; every entry is grounded in a real FP.
# ---------------------------------------------------------------------------

# Consumer product listings (eBay / Amazon / Etsy)
LISTING_SUPPRESS = [
    r"\bcheck out\b.{0,60}\b(?:ebay|amazon|etsy)\b",
    r"\bvia @?(?:ebay|amazon|etsy)\b",
    r"\b(?:ebay|etsy)\b.{0,40}\bfor sale\b",
    r"\bjust saw this on amazon\b",
]

# Personal finance — repair bills, personal debt, personal purchases
PERSONAL_FINANCE_SUPPRESS = [
    r"\bmy (?:loan|debt|payment|bill|car|house|phone)\b",
    r"\$[\d,]+\b.{0,30}\bto fix\b",
    r"\bcosts?\b.{0,20}\$[\d,]+\b.{0,20}\bto fix\b",
    r"\bstill paying (?:it|them) off\b",
]

# First-person intent statements that are NOT corporate actions
PERSONAL_INTENT_SUPPRESS = [
    r"\bmy plan is\b.{0,40}\bnot\b.{0,20}\bbuy\b",
    r"\bi (?:will be |am going to |plan to )?(?:picking up|pick up) my copy\b",
    r"\bwill not bow\b",
    r"\bwe will not bow\b",
    r"\bi won't be buying\b",
    r"\bnot (?:not )?buy any company who\b",  # row 4423: "not not buy any company who discriminates"
    r"\bwho discriminates\b",
]

# Boycott / consumer activism — contains financial keywords but is not an event
BOYCOTT_SUPPRESS = [
    r"\bboycott\w*\b",
    r"\bdivest\b.{0,40}\bpipeline\b",
    r"\btell @?\w+ to (?:stop|divest|pull)\b",
    r"\bsign the petition\b",
    r"\btake action\b.{0,40}\btell @?\w+\b",
]

# Personal credit complaints — informal use of "bankrupt", "default" etc.
PERSONAL_CREDIT_SUPPRESS = [
    r"\b(?:i|we|you|he|she|they) (?:might|may|could|will|would) go bankrupt\b",
    r"\bmight go bankrupt because of shoddy\b",
    r"\bboycott\w*\b.{0,40}\bbankruptcy\b",  # "boycott Starbucks into bankruptcy" (row 156)
    r"\bshoddy workmanship\b",
    r"\bcustomer (?:complaint|service|support)\b",
    r"\brepay\b.{0,20}\$[\d,]+\b",
]

# Opinion / prediction framing — not an observed event
OPINION_SUPPRESS = [
    r"\b(?:i think|i believe|in my opinion|imo|imho)\b",
    r"\b(?:will|might|could|may|should|probably) (?:rise|fall|drop|surge|crash|go up|go down)\b",
    r"\bbetting on\b",
    r"\bmade bets?\b",
    r"\b(?:buy|sell) (?:this|the) stock\b",
    r"\bhow low .{0,30}stock will drop\b",
]


# ---------------------------------------------------------------------------
# Positive materiality rules — one list per event type.
# Each pattern asserts a concrete corporate / market event.
# ---------------------------------------------------------------------------

RULES = {
    "Merger & Acquisition": [
        r"\b(?:plans? to |agrees? to |agreed to |has )?acquire[sd]?\b",
        r"\bacquisition\b",
        r"\bmerger\b",
        r"\b#merger\w*",                                        # hashtag form (row 4307)
        r"\bmerge[sd]?\b",
        r"\btakeover\b",
        r"\bbid (?:for|to acquire)\b",
        r"\bmakes? .{0,20}bid\b",                               # "PAG makes $616M bid" (row 4153)
        r"\b(?:offers?|offered) (?:to )?(?:buy|acquire)\b",
        r"\basset deal\b",                                      # "DuPont in asset deal" (row 4886)
        r"\bdeal (?:to acquire|to buy)\b",
        r"\b(?:purchase|purchased) (?:of|stake in)\b",
        r"\b\d+(?:\.\d+)?[\s]*%[\s]*stake\b",                  # "19.5% stake" (row 503)
        r"\bstake in [A-Z][A-Za-z0-9&.\- ]{1,60}\b",
        r"\bplans to acquire\b",                                # "PayPal plans to acquire TIONetworks" (row 3191)
        r"\bbuys\b.{0,80}\b(?:to (?:create|build|expand)|cloud|platform|service|api)\b",  # "Oracle buys Apiary" (row 521)
        # Large-scale personal investment reported as news (Buffett $12B, rows 838-1827)
        r"\bbought \$\d+(?:\.\d+)?\s*(?:billion|million|bn|m)\b.{0,40}(?:stock|shares?)\b",
        r"\b\$\d+(?:\.\d+)?\s*(?:billion|million|bn|m)\b.{0,40}\b(?:acquisition|stake|bid|deal|merger)\b",
    ],
    "Regulatory / Legal": [
        r"\bfined\b",
        r"\bfine of\b",
        r"\bpenalt(?:y|ies)\b",
        r"\bregulatory (?:action|approval|probe|investigation|fine|block|reject)\b",
        r"\bregulator(?:y|s)?\b.{0,40}\b(?:probe|investigat|fine|penalt|approv|reject|block)\b",
        r"\b(?:SEC|FTC|DOJ|FCA|CFTC|FINRA|OCC|CFPB|FAA|NTSB|DOT|EPA|FDA)\b",
        r"\bground(?:ing|ed|s)?\b",
        r"\bantitrust\b",
        r"\blawsuit\b",
        r"\bclass[- ]action\b",
        r"\bsued\b",
        r"\bsues\b",
        r"\bsettlement\b",
        r"\bsettled with\b",
        r"\bcharged with\b",
        r"\bAML controls? failings?\b",
        r"\bpay \$[\d,]+\w*\b.{0,40}\bregulator\b",            # "pay $425m to N.Y. regulator" (row 63)
    ],
    "Corporate / Earnings": [
        r"\bearnings?\b",
        r"\bquarterly results?\b",
        r"\bannual results?\b",
        r"\brevenue (?:rose|fell|grew|declined|missed|beat)\b",
        r"\bprofit (?:rose|fell|grew|declined|missed|beat)\b",
        r"\b(?:sales|revenue|profit|earnings) (?:beat|missed) (?:estimates?|expectations?)\b",
        r"\bguidance\b",
        r"\bprofit warning\b",
        r"\breports? (?:record|quarterly|annual) (?:sales|revenue|profit|loss)\b",
        r"\bIPO\b",
        r"\binitial public offering\b",
        r"\blayoffs?\b",
        r"\bjob cuts?\b",
        r"\bgrowing faster than @?\w+\b",                       # "Mastercard growing faster than Visa" (row 180)
    ],
    "Macroeconomic": [
        r"\binflation\b",
        r"\binterest rates?\b",
        r"\brate (?:hike|cut|decision|change)\b",
        r"\bcentral bank\b",
        r"\bfederal reserve\b",
        r"\bthe Fed\b",
        r"\bGDP\b",
        r"\bunemployment\b",
        r"\bjobs? report\b",
        r"\bconsumer price index\b",
        r"\bCPI\b",
        r"\bproducer price index\b",
        r"\bPPI\b",
        r"\bmonetary policy\b",
        r"\bfiscal policy\b",
        r"\btax reform\b",
        r"\btariffs?\b",
        r"\btrade war\b",
        r"\brecession\b",
        r"\bkeep rates steady\b",                               # "Fed likely to keep rates steady" (row 82)
        r"\bawaits? .{0,30}economic plan\b",
    ],
    "Commodity / Supply Chain": [
        r"\bOPEC\b",
        r"\bcrude oil\b",
        r"\boil prices?\b",
        r"\boil output\b",
        r"\bnatural gas prices?\b",
        r"\bcommodity prices?\b",
        r"\bcommodity market\b",
        r"\bcrop (?:shortage|failure|production)\b",
        r"\bgrain prices?\b",
        r"\bsupply chain disruption\b",
        r"\bsupply disruption\b",
        r"\bshipping disruption\b",
        r"\bport disruption\b",
        r"\bproduction halt\b",
        r"\braw material shortage\b",
        r"\bsemiconductor shortage\b",
        r"\boutput cuts?\b",
    ],
    "Product / Technology": [
        r"\b(?:new )?product launch\b",
        r"\bunveiled\b",
        r"\brecall(?:ed)?\b",
        r"\bservice outage\b",
        r"\bsystem outage\b",
        r"\bnetwork outage\b",
        r"\boutage\b",
        r"\bservice disruption\b",
        r"\btechnology disruption\b",
        r"\bcyberattack\b",
        r"\bcyber attack\b",
        r"\bdata breach\b",
        r"\bsecurity breach\b",
        r"\blaunched\b.{0,40}\b(?:platform|service|product|solution|cloud|app)\b",
        r"\bplans to release\b.{0,40}\b(?:headset|device|platform|product)\b",
    ],
    "Market / Liquidity": [
        r"\btrading halt\b",
        r"\bshares? (?:fell|rose|surged|plunged|rallied|slumped|tumbled)\b",
        r"\bstock (?:fell|rose|surged|plunged|rallied|slumped|tumbled)\b",
        r"\bmarket (?:selloff|rally|crash|plunge)\b",
        r"\bwall street (?:falls?|rises?)\b",                   # "Wall Street falls the most" (row 210)
        r"\bliquidity crisis\b",
        r"\bvaluation (?:cut|reduced|raised|slashed)\b",
        r"\bprice target (?:cut|raised|lowered)\b",
        r"\bshares? (?:halted|suspended)\b",
        r"\bcredit spreads?\b",
        r"\bfighting back against .{0,30}tax\b",
        r"\bborder tax\b",
    ],
    "Credit Event": [
        r"\bfiled for bankruptcy\b",
        r"\bfiled bankruptcy\b",
        r"\bdeclared bankruptcy\b",
        r"\bentered bankruptcy(?: protection)?\b",
        r"\bbankruptcy protection\b",
        r"\bchapter\s+(?:7|11|15)\b",
        r"\bdefault(?:ed|s)? on (?:its |the )?(?:debt|loan|bond|payment)\b",
        r"\bmissed (?:a |its |the )?(?:debt|loan|bond|interest) payment\b",
        r"\bdebt restructuring\b",
        r"\brestructur(?:e|ing|ed) (?:its |the )?(?:debt|loans?)\b",
        r"\bcovenant breach\b",
        r"\bbond default\b",
        r"\bcredit (?:downgrade|rating (?:cut|lowered))\b",
        r"\bdowngrad(?:ed|e) (?:its |the )?credit\b",
        r"\binsolvency\b",
        r"\binsolvent\b",
    ],
    "Geopolitical": [
        r"\bmissiles?\b",
        r"\bairstrike\b",
        r"\bair strike\b",
        r"\binvasion\b",
        r"\bmilitary (?:attack|strike|action|operation|conflict)\b",
        r"\barmed conflict\b",
        r"\bceasefire\b",
        r"\bsanctions?\b",
        r"\bdiplomatic (?:crisis|dispute|tensions?)\b",
        r"\bembargo\b",
        r"\bgeopolitical tensions?\b",
        r"\bcoup\b",
        r"\bsafe zones?\b",
        r"\btravel ban\b",
        r"\bimmigration order\b",
        r"\bexecutive order\b",
        r"\bappoints? .{0,40}director\b",
    ],
}

# Type-specific suppression applied inside each branch before positive rules.

MA_SUPPRESS = [
    r"\beasy acquisition\b",
    r"\b(?:knowledge|skill|language|habit|taste) acquisition\b",
    r"\bacquired a (?:taste|skill|habit|love)\b",
    r"\b(?:car|vehicle|house|home|property) acquisition\b",
    r"\bbuying a (?:car|house|home|ring|watch)\b",
    r"\bnot (?:not )?buy any company who\b",
]

CREDIT_TYPE_SUPPRESS = [
    r"\b(?:i|we|you|he|she|they) (?:might|may|could|will|would) go bankrupt\b",
    r"\bboycott\w*\b.{0,40}\bbankruptcy\b",
    r"\bshoddy workmanship\b",
    r"\bcustomer (?:complaint|service|support)\b",
    r"\brepay\b.{0,20}\$[\d,]+\b",
]

COMMODITY_TYPE_SUPPRESS = [
    r"\b(?:gold|silver)\s+(?:ring|necklace|earrings?|bracelet|jewelry)\b",
    r"\bjewelry\b",
    r"\bcollectible\b",
]

PRODUCT_TYPE_SUPPRESS = [
    r"\bcustomer (?:complaint|service|support)\b",
    r"\b(?:coupon|discount|sale price|buy now|shopping cart)\b",
]

MARKET_TYPE_SUPPRESS = [
    r"\b(?:will|might|could|may) (?:rise|fall|drop|surge|break out|crash)\b",
    r"\bbetting on\b",
    r"\bmade bets?\b",
    r"\b(?:buy|sell) (?:this|the) stock\b",
    r"\bhow low .{0,30}stock will drop\b",
]

GEO_TYPE_SUPPRESS = [
    r"\byour hatred\b",
    r"\b2 great nations embracing\b",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean_text(x):
    if pd.isna(x):
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()


def matches_any(text, patterns):
    return any(re.search(p, text, flags=re.I) for p in patterns)


def first_match(text, patterns):
    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            return m.group(0)
    return None


def canonical_type(event_type):
    """Normalise variant spellings of event-type labels to the RULES key."""
    mapping = {
        "merger & acquisition":        "Merger & Acquisition",
        "merger &amp; acquisition":    "Merger & Acquisition",
        "regulatory / legal":          "Regulatory / Legal",
        "regulatory/legal":            "Regulatory / Legal",
        "corporate / earnings":        "Corporate / Earnings",
        "corporate/earnings":          "Corporate / Earnings",
        "commodity / supply chain":    "Commodity / Supply Chain",
        "commodity/supply chain":      "Commodity / Supply Chain",
        "market / liquidity":          "Market / Liquidity",
        "market/liquidity":            "Market / Liquidity",
        "product / technology":        "Product / Technology",
        "product/technology":          "Product / Technology",
        "credit event":                "Credit Event",
        "geopolitical":                "Geopolitical",
        "macroeconomic":               "Macroeconomic",
    }
    return mapping.get(str(event_type).lower().strip(), event_type)


# ---------------------------------------------------------------------------
# Per-type rule evaluation with type-specific suppressions
# ---------------------------------------------------------------------------

def _check_type(text, etype, confidence):
    """
    Returns (material: bool, phrase: str) after applying type-specific
    suppression and then scanning positive rules.
    """
    # --- Merger & Acquisition ---
    if etype == "Merger & Acquisition":
        if matches_any(text, MA_SUPPRESS):
            return False, "ma_suppressed"
        # Suppress bare "if X goes ahead" speculation unless there is a concrete
        # deal signal (dollar amount, % stake, or merger hashtag) in the tweet.
        if re.match(r"^if\b", text, flags=re.I):
            has_signal = (
                re.search(r"\$[\d,.]+\s*(?:billion|million|bn|m)\b", text, re.I)
                or re.search(r"\b\d+(?:\.\d+)?[\s]*%[\s]*(?:stake|share)", text, re.I)
                or re.search(r"#merger\w*", text, re.I)
            )
            if not has_signal:
                return False, "conditional_framing"

    # --- Credit Event ---
    elif etype == "Credit Event":
        if matches_any(text, CREDIT_TYPE_SUPPRESS):
            return False, "credit_suppressed"

    # --- Commodity / Supply Chain ---
    elif etype == "Commodity / Supply Chain":
        if matches_any(text, COMMODITY_TYPE_SUPPRESS):
            return False, "commodity_suppressed"

    # --- Product / Technology ---
    elif etype == "Product / Technology":
        if matches_any(text, PRODUCT_TYPE_SUPPRESS):
            return False, "product_suppressed"

    # --- Market / Liquidity ---
    elif etype == "Market / Liquidity":
        if matches_any(text, MARKET_TYPE_SUPPRESS):
            return False, "market_suppressed"

    # --- Geopolitical ---
    elif etype == "Geopolitical":
        if matches_any(text, GEO_TYPE_SUPPRESS):
            return False, "geo_suppressed"

    # Positive rule scan
    hit = first_match(text, RULES.get(etype, []))
    if hit:
        # Low-confidence guard: a very short, generic hit below the threshold
        # is not strong enough to declare materiality on its own.
        if confidence < LOW_CONF_THRESHOLD and len(hit) < 9 and not re.search(r"\d", hit):
            return False, f"low_confidence_weak_hit:{hit}"
        return True, hit

    return False, "no_pattern_match"


# ---------------------------------------------------------------------------
# Main classification function  (mirrors v3's classify_text signature style)
# ---------------------------------------------------------------------------

def classify_text(text, original_type, relevance, confidence):
    """
    Returns (materiality, final_event_type, reason).

    Evaluation order
    ----------------
    1. FINANCIAL_RELEVANCE gate — authoritative; non-events exit immediately.
    2. Empty text guard.
    3. Hard global suppressions (listings, personal finance, personal intent,
       boycott/activism, personal credit, opinion/prediction).
    4. Personal credit special case: suppress unless a formal credit-event
       phrase is present (prevents "#BoycottStarbucks into bankruptcy" FP).
    5. Try the upstream-declared event type with its type-specific guards.
    6. Cross-type scan for mislabelled rows and "Other / Unclear" rows.
    7. Default: NON_MATERIAL_FINANCIAL_CONTENT.
    """
    t = clean_text(text)

    # Gate 1 — relevance
    if relevance != "FINANCIAL_EVENT":
        return "NO_EVENT", "NO_EVENT", "relevance_gate"

    # Gate 2 — empty
    if not t:
        return "NON_MATERIAL_FINANCIAL_CONTENT", "NO_EVENT", "empty_text"

    # Gate 3 — hard global suppressions
    if matches_any(t, LISTING_SUPPRESS):
        return "NON_MATERIAL_FINANCIAL_CONTENT", "NO_EVENT", "consumer_listing_context"

    if matches_any(t, PERSONAL_FINANCE_SUPPRESS):
        return "NON_MATERIAL_FINANCIAL_CONTENT", "NO_EVENT", "personal_finance_context"

    if matches_any(t, PERSONAL_INTENT_SUPPRESS):
        return "NON_MATERIAL_FINANCIAL_CONTENT", "NO_EVENT", "personal_intent_statement"

    if matches_any(t, OPINION_SUPPRESS):
        # Don't suppress if the upstream type has a concrete rule hit —
        # an observed event described alongside an opinion is still material.
        ctype = canonical_type(original_type)
        concrete = first_match(t, RULES.get(ctype, []))
        if not concrete:
            return "NON_MATERIAL_FINANCIAL_CONTENT", "NO_EVENT", "opinion_or_prediction_framing"

    # Gate 4 — boycott/activism: suppress unless a hard regulatory/legal
    # signal is also present (e.g. a petition is not a fining action).
    if matches_any(t, BOYCOTT_SUPPRESS):
        if not first_match(t, RULES["Regulatory / Legal"]):
            return "NON_MATERIAL_FINANCIAL_CONTENT", "NO_EVENT", "boycott_or_activism_framing"

    # Gate 5 — personal credit: suppress unless a formal corporate-credit
    # phrase is explicitly present (prevents "boycott into bankruptcy" FP).
    if matches_any(t, PERSONAL_CREDIT_SUPPRESS):
        if not first_match(t, RULES["Credit Event"]):
            return "NON_MATERIAL_FINANCIAL_CONTENT", "NO_EVENT", "personal_credit_complaint"

    # Step 5 — try upstream-declared event type first
    ctype = canonical_type(original_type)
    if ctype in RULES:
        material, hit = _check_type(t, ctype, confidence)
        if material:
            return "MATERIAL_EVENT", ctype, f"upstream_type_confirmed:{hit}"
        # If it was explicitly suppressed (not just "no_pattern_match"), skip
        # cross-type scan to avoid introducing a different false positive.
        if hit.endswith("_suppressed") or hit == "conditional_framing":
            return "NON_MATERIAL_FINANCIAL_CONTENT", "NO_EVENT", hit

    # Step 6 — cross-type scan
    # Rescues:  (a) "Other / Unclear" rows (no upstream rule set)
    #           (b) mislabelled rows (upstream classifier wrong)
    for etype in RULES:
        if etype == ctype:
            continue
        material, hit = _check_type(t, etype, confidence)
        if material:
            return "MATERIAL_EVENT", etype, f"rescued_cross_type:{etype}:{hit}"

    # Step 7 — default
    return "NON_MATERIAL_FINANCIAL_CONTENT", "NO_EVENT", "no_sufficient_event_evidence"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# Output is always written here; --output supplies only the filename.
OUTPUT_DIR = Path("data/processed")


def parse_args():
    p = argparse.ArgumentParser(
        description="Event materiality classifier v4"
    )
    p.add_argument(
        "--input",
        required=True,
        help="Path to the input CSV (e.g. data/processed/event_baseline.csv)",
    )
    p.add_argument(
        "--output",
        required=True,
        help="Output filename only (e.g. event_materiality4.csv). "
             f"Saved automatically to {OUTPUT_DIR}/",
    )
    p.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Limit number of rows processed (for testing)",
    )
    p.add_argument(
        "--chunk-size",
        type=int,
        default=50_000,
        help="Rows per processing chunk (default: 50,000 — deterministic, no model, fast).",
    )
    p.add_argument(
        "--checkpoint-dir",
        default=None,
        help="Directory for checkpoint manifests (default: <output_dir>/checkpoints/).",
    )
    return p.parse_args()


def classify_chunked(
    input_path: Path,
    output_path: Path,
    chunk_size: int = 50_000,
    max_rows: int | None = None,
    checkpoint_dir: Path | None = None,
) -> None:
    """
    Chunked, checkpointed execution of the materiality classifier.

    The classify_text() function is deterministic and purely CPU-bound,
    so chunk_size can be large (50k+) without GPU memory concerns.
    """
    import time
    try:
        from src.pipeline.checkpoint import (
            CheckpointManager, build_chunk_id, sha256_of_file,
        )
        from src.pipeline.manifest import RunManifest, get_code_version
        _has_pipeline = True
    except ImportError:
        _has_pipeline = False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if checkpoint_dir is None:
        checkpoint_dir = output_path.parent / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    stage_name = "materiality_v4"
    first_write = not output_path.exists() or output_path.stat().st_size == 0
    total_written = 0
    chunks_skipped = 0

    if _has_pipeline:
        mgr = CheckpointManager(checkpoint_dir / f"{stage_name}_manifest.json")
        input_sha256 = sha256_of_file(input_path)
        run_manifest = RunManifest(
            stage_name=stage_name,
            input_path=input_path,
            output_dir=output_path.parent,
            chunk_size=chunk_size,
            batch_size=1,
            device="cpu",
            model_identifiers={"materiality": "v4_deterministic"},
            config_version="v1",
        )
        checkpoint = mgr.load_or_create(
            run_id=run_manifest.run_id,
            stage_name=stage_name,
            input_path=str(input_path),
            input_sha256=input_sha256,
            input_row_count=0,
            output_dir=str(output_path.parent),
            code_version=get_code_version(),
            config_version="v1",
            model_identifiers={"materiality": "v4_deterministic"},
            device="cpu",
            batch_size=1,
            chunk_size=chunk_size,
        )
        completed_ids = set(checkpoint.completed_chunk_ids())
    else:
        mgr = None
        checkpoint = None
        completed_ids = set()
        run_manifest = None

    required = {"TWEET", "FINANCIAL_RELEVANCE", "EVENT_TYPE", "EVENT_CONFIDENCE"}
    run_start = time.time()
    total_rows = 0
    ci = 0

    reader = pd.read_csv(
        input_path,
        chunksize=chunk_size,
        on_bad_lines="skip",
        low_memory=False,
    )

    for ci, chunk in enumerate(reader):
        n = len(chunk)
        if max_rows is not None and total_rows >= max_rows:
            break
        if max_rows is not None and total_rows + n > max_rows:
            chunk = chunk.head(max_rows - total_rows).copy()
            n = len(chunk)

        chunk_id = build_chunk_id(stage_name, ci) if _has_pipeline else f"{stage_name}_chunk_{ci:06d}"

        if chunk_id in completed_ids:
            print(f"[materiality] Skipping completed chunk {chunk_id}")
            chunks_skipped += 1
            total_rows += n
            continue

        missing = required - set(chunk.columns)
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")

        chunk_start = time.time()
        if mgr:
            record = mgr.mark_in_progress(checkpoint, chunk_id, total_rows, total_rows + n)

        results = [
            classify_text(
                text=row["TWEET"],
                original_type=row["EVENT_TYPE"],
                relevance=row["FINANCIAL_RELEVANCE"],
                confidence=float(row["EVENT_CONFIDENCE"]),
            )
            for _, row in chunk.iterrows()
        ]

        chunk["EVENT_MATERIALITY"]        = [r[0] for r in results]
        chunk["FINAL_EVENT_TYPE"]         = [r[1] for r in results]
        chunk["EVENT_MATERIALITY_REASON"] = [r[2] for r in results]

        chunk.to_csv(
            output_path,
            mode="a",
            header=first_write,
            index=False,
            encoding="utf-8-sig",
        )
        first_write = False

        duration = time.time() - chunk_start
        if mgr:
            mgr.mark_complete(
                checkpoint, record,
                output_row_count=n,
                output_path=str(output_path),
                duration_seconds=duration,
            )

        total_written += n
        total_rows += n
        rps = n / max(duration, 0.001)
        print(f"[materiality] chunk={chunk_id} rows={n:,} speed={rps:.0f} rows/s total={total_written:,}")

    # Finalize
    run_duration = time.time() - run_start
    if run_manifest:
        run_manifest.finalize(total_rows, total_written, run_duration)
        run_manifest.save(checkpoint_dir / f"{stage_name}_run_manifest.json")

    print(f"\n[materiality] Done: {total_written:,} rows written to {output_path}")
    if checkpoint:
        print(checkpoint.summary())


def main():
    args = parse_args()

    # Resolve the output path: always under OUTPUT_DIR, using the given filename.
    output_filename = Path(args.output).name   # strip any accidental path prefix
    output_path = OUTPUT_DIR / output_filename
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    checkpoint_dir = (
        Path(args.checkpoint_dir)
        if args.checkpoint_dir
        else output_path.parent / "checkpoints"
    )

    classify_chunked(
        input_path=Path(args.input),
        output_path=output_path,
        chunk_size=args.chunk_size,
        max_rows=args.max_rows,
        checkpoint_dir=checkpoint_dir,
    )

    # Summary statistics (load the output for reporting)
    try:
        df = pd.read_csv(output_path, on_bad_lines="skip")
        print("\nMateriality:")
        print(df["EVENT_MATERIALITY"].value_counts(dropna=False).to_string())
        print("\nFinal event type:")
        print(df["FINAL_EVENT_TYPE"].value_counts(dropna=False).to_string())
        material = df[df["EVENT_MATERIALITY"] == "MATERIAL_EVENT"]
        print("\nMaterial events by final type:")
        if len(material):
            print(material["FINAL_EVENT_TYPE"].value_counts().to_string())
        else:
            print("None")
    except Exception as exc:
        print(f"[WARN] Could not load output for summary: {exc}")

    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
