#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baseline Real-Data Impact Scoring Evaluation
=============================================
Integrates the frozen Deterministic Impact Scorer with the 5,000-row
historical validation dataset (event_materiality4.csv + FinBERT predictions).

Executes comprehensive distributional diagnostics:
1. Overall impact score distribution & tier breakdown
2. Impact distribution across EVENT_TYPE categories
3. Impact distribution across MATERIALITY gates
4. Impact correlation with FinBERT sentiment polarity
5. Impact correlation with classifier confidence
6. Inspection of the Top 25 highest-impact signals
7. Noise/Junk audit: verifying no gated noise leaks into high tiers
8. Major canonical event audit: verifying true financial events receive appropriate scores

Usage:
------
python src/risk/evaluate_impact_on_baseline.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from src.risk.impact_scorer import ImpactScorer
from src.risk.risk_signal import MaterialityLevel, RiskSignal


DEFAULT_MATERIALITY_PATH = Path("data/processed/event_materiality4.csv")
DEFAULT_FINBERT_PATH = Path("data/processed/finbert_reduced_predictions.csv")
DEFAULT_OUTPUT_PATH = Path("data/processed/impact_scored_baseline.csv")


def load_and_merge_data(
    materiality_path: Path, finbert_path: Path
) -> pd.DataFrame:
    """Load materiality and sentiment data, merging on row_id."""
    if not materiality_path.exists():
        raise FileNotFoundError(f"Materiality file not found: {materiality_path}")
    if not finbert_path.exists():
        raise FileNotFoundError(f"FinBERT file not found: {finbert_path}")

    df_mat = pd.read_csv(materiality_path, on_bad_lines="skip")
    df_fin = pd.read_csv(finbert_path, on_bad_lines="skip")

    # Validate row_id
    if "row_id" not in df_mat.columns or "row_id" not in df_fin.columns:
        raise KeyError("Both input files must contain 'row_id' column.")

    merged = pd.merge(df_mat, df_fin, on="row_id", suffixes=("", "_fin"))
    print(f"Loaded {len(df_mat):,} materiality rows and {len(df_fin):,} FinBERT rows.")
    print(f"Merged successfully on 'row_id': {len(merged):,} rows.")
    return merged


def run_baseline_scoring(
    df: pd.DataFrame,
    source_credibility: float = 1.0,
    novelty: float = 1.0,
) -> pd.DataFrame:
    """
    Score each row of the historical dataset using ImpactScorer.
    """
    scorer = ImpactScorer()

    scores: List[float] = []
    tiers: List[str] = []
    reasons: List[str] = []
    raw_composites: List[float] = []
    conf_mods: List[float] = []
    sent_mods: List[float] = []
    is_gated_list: List[bool] = []

    for _, row in df.iterrows():
        # Determine canonical event type for severity lookup:
        # If FINAL_EVENT_TYPE is a recognized category, use it.
        # Otherwise fallback to upstream EVENT_TYPE for non-material content.
        final_type = str(row.get("FINAL_EVENT_TYPE", "")).strip()
        orig_type = str(row.get("EVENT_TYPE", "")).strip()

        if final_type and final_type != "NO_EVENT":
            eval_event_type = final_type
        elif orig_type and orig_type != "NO_EVENT":
            eval_event_type = orig_type
        else:
            eval_event_type = "NO_EVENT"

        materiality = str(row.get("EVENT_MATERIALITY", "NO_EVENT")).strip()
        confidence = float(row.get("EVENT_CONFIDENCE", 0.5))
        sentiment = float(row.get("FINBERT_SCORE", 0.0))

        # Direct row evaluation through the scorer
        score, reason, tier = scorer.score_dataframe_row(
            event_type=eval_event_type,
            materiality=materiality,
            event_confidence=confidence,
            sentiment_score=sentiment,
            source_credibility=source_credibility,
            novelty=novelty,
            market_context=None,
        )

        conf_mod = scorer.compute_confidence_modifier(confidence)
        sent_mod = scorer.compute_sentiment_modifier(sentiment)
        base_sev = scorer.get_base_severity(eval_event_type)
        raw_comp = base_sev * conf_mod * source_credibility * 1.0 * sent_mod * 1.0

        scores.append(score)
        tiers.append(tier)
        reasons.append(reason)
        raw_composites.append(round(raw_comp, 4))
        conf_mods.append(conf_mod)
        sent_mods.append(sent_mod)
        is_gated_list.append(materiality != MaterialityLevel.MATERIAL_EVENT.value)

    df["IMPACT_SCORE"] = scores
    df["IMPACT_TIER"] = tiers
    df["IMPACT_REASON"] = reasons
    df["RAW_COMPOSITE"] = raw_composites
    df["CONFIDENCE_MODIFIER"] = conf_mods
    df["SENTIMENT_MODIFIER"] = sent_mods
    df["IS_GATED"] = is_gated_list

    return df


def print_evaluation_report(df: pd.DataFrame) -> None:
    """Generate and print the 8 comprehensive baseline analyses."""
    print("\n" + "=" * 115)
    print("5,000-ROW REAL HISTORICAL BASELINE IMPACT SCORING EVALUATION")
    print("=" * 115)

    # -----------------------------------------------------------------------
    # Analysis 1: Overall Impact Score Distribution
    # -----------------------------------------------------------------------
    print("\n" + "-" * 115)
    print("ANALYSIS 1: OVERALL IMPACT SCORE DISTRIBUTION & TIER BREAKDOWN")
    print("-" * 115)
    scores = df["IMPACT_SCORE"]
    print(f"Total signals scored: {len(df):,}")
    print(f"Mean Impact Score:    {scores.mean():.2f} ± {scores.std():.2f}")
    print(f"Median Impact Score:  {scores.median():.2f}")
    print(f"Min / Max:            {scores.min():.2f} / {scores.max():.2f}")
    print(f"Percentiles [25%, 50%, 75%, 90%, 95%, 99%]:")
    p = np.percentile(scores, [25, 50, 75, 90, 95, 99])
    print(f"  P25: {p[0]:.2f} | P50: {p[1]:.2f} | P75: {p[2]:.2f} | P90: {p[3]:.2f} | P95: {p[4]:.2f} | P99: {p[5]:.2f}")

    print("\nImpact Tier Counts:")
    tier_counts = df["IMPACT_TIER"].value_counts()
    for tier, count in tier_counts.items():
        pct = (count / len(df)) * 100
        print(f"  {tier:<16}: {count:5d} ({pct:5.1f}%)")

    # Binned distribution
    bins = [0.99, 1.00, 2.00, 3.00, 5.00, 7.00, 8.50, 10.01]
    labels = ["1.00 (NO_EVENT baseline)", "1.01 - 2.00 (Gated non-material)", "2.01 - 3.00", "3.01 - 5.00 (Low)", "5.01 - 7.00 (Moderate)", "7.01 - 8.50 (High)", "8.51 - 10.00 (Critical)"]
    binned = pd.cut(df["IMPACT_SCORE"], bins=bins, labels=labels)
    print("\nDetailed Score Bins:")
    for b_label, count in binned.value_counts(sort=False).items():
        pct = (count / len(df)) * 100
        print(f"  {b_label:<32}: {count:5d} ({pct:5.1f}%)")

    # -----------------------------------------------------------------------
    # Analysis 2: Impact by EVENT_TYPE
    # -----------------------------------------------------------------------
    print("\n" + "-" * 115)
    print("ANALYSIS 2: IMPACT SCORES BY EVENT TYPE (MATERIAL EVENTS)")
    print("-" * 115)
    mat_df = df[df["EVENT_MATERIALITY"] == "MATERIAL_EVENT"]
    print(f"Total Material Events: {len(mat_df):,}")
    print(f"{'Final Event Type':<26} {'Count':>6} {'Mean':>6} {'Std':>6} {'Median':>7} {'Min':>6} {'Max':>6}")
    print("-" * 67)
    for ev_type, grp in mat_df.groupby("FINAL_EVENT_TYPE"):
        s = grp["IMPACT_SCORE"]
        print(f"{ev_type:<26} {len(grp):6d} {s.mean():6.2f} {s.std():6.2f} {s.median():7.2f} {s.min():6.2f} {s.max():6.2f}")

    # -----------------------------------------------------------------------
    # Analysis 3: Impact by MATERIALITY Gate
    # -----------------------------------------------------------------------
    print("\n" + "-" * 115)
    print("ANALYSIS 3: IMPACT SCORES BY MATERIALITY LEVEL (GATING VERIFICATION)")
    print("-" * 115)
    print(f"{'Materiality Level':<32} {'Count':>6} {'Mean':>6} {'Median':>7} {'Min':>6} {'Max':>6} {'Leakage >= 3.0':>15}")
    print("-" * 84)
    for mat, grp in df.groupby("EVENT_MATERIALITY"):
        s = grp["IMPACT_SCORE"]
        leakage = (s >= 3.0).sum() if mat != "MATERIAL_EVENT" else 0
        print(f"{mat:<32} {len(grp):6d} {s.mean():6.2f} {s.median():7.2f} {s.min():6.2f} {s.max():6.2f} {leakage:15d}")

    # -----------------------------------------------------------------------
    # Analysis 4: Impact by FINBERT Sentiment
    # -----------------------------------------------------------------------
    print("\n" + "-" * 115)
    print("ANALYSIS 4: IMPACT SCORES BY FINBERT SENTIMENT POLARITY")
    print("-" * 115)
    corr_all = df["IMPACT_SCORE"].corr(df["FINBERT_SCORE"])
    corr_mat = mat_df["IMPACT_SCORE"].corr(mat_df["FINBERT_SCORE"])
    print(f"Pearson Correlation (IMPACT_SCORE vs FINBERT_SCORE across all rows): {corr_all:+.4f}")
    print(f"Pearson Correlation (IMPACT_SCORE vs FINBERT_SCORE in Material subset): {corr_mat:+.4f}")

    print("\nMaterial Events Breakdown by FinBERT Sentiment Label:")
    print(f"{'FinBERT Label':<16} {'Count':>6} {'Mean Impact':>12} {'Median':>8} {'Min':>6} {'Max':>6}")
    print("-" * 52)
    for label, grp in mat_df.groupby("FINBERT_LABEL"):
        s = grp["IMPACT_SCORE"]
        print(f"{label:<16} {len(grp):6d} {s.mean():12.2f} {s.median():8.2f} {s.min():6.2f} {s.max():6.2f}")

    # -----------------------------------------------------------------------
    # Analysis 5: Impact by Event Confidence
    # -----------------------------------------------------------------------
    print("\n" + "-" * 115)
    print("ANALYSIS 5: IMPACT SCORES BY EVENT CLASSIFIER CONFIDENCE")
    print("-" * 115)
    conf_bins = [0.0, 0.40, 0.60, 0.80, 1.01]
    conf_labels = ["< 0.40", "0.40 - 0.60", "0.60 - 0.80", "0.80 - 1.00"]
    mat_df_copy = mat_df.copy()
    mat_df_copy["CONF_BRACKET"] = pd.cut(mat_df["EVENT_CONFIDENCE"], bins=conf_bins, labels=conf_labels)

    print(f"{'Confidence Bracket':<22} {'Count':>6} {'Mean Impact':>12} {'Median':>8} {'Min':>6} {'Max':>6}")
    print("-" * 58)
    for b, grp in mat_df_copy.groupby("CONF_BRACKET", observed=False):
        if len(grp) > 0:
            s = grp["IMPACT_SCORE"]
            print(f"{b:<22} {len(grp):6d} {s.mean():12.2f} {s.median():8.2f} {s.min():6.2f} {s.max():6.2f}")
        else:
            print(f"{b:<22} {0:6d} {'N/A':>12} {'N/A':>8} {'N/A':>6} {'N/A':>6}")

    # -----------------------------------------------------------------------
    # Analysis 6: Top 25 Highest-Impact Signals
    # -----------------------------------------------------------------------
    print("\n" + "-" * 115)
    print("ANALYSIS 6: TOP 25 HIGHEST-IMPACT HISTORICAL SIGNALS")
    print("-" * 115)
    top25 = df.sort_values(by=["IMPACT_SCORE", "RAW_COMPOSITE"], ascending=[False, False]).head(25)

    for rank, (_, row) in enumerate(top25.iterrows(), 1):
        clean_text = str(row["TWEET"]).replace("\n", " ")[:90]
        print(f"#{rank:<2} [Row {row['row_id']:<4}] Score: {row['IMPACT_SCORE']:4.2f} ({row['IMPACT_TIER']:<15}) | Stock: {row['STOCK']:<12} | Event: {row['FINAL_EVENT_TYPE']}")
        print(f"    Conf: {row['EVENT_CONFIDENCE']:.2f} | Sent: {row['FINBERT_SCORE']:+.2f} ({row['FINBERT_LABEL']}) | Reason: {row['IMPACT_REASON']}")
        print(f"    Text: \"{clean_text}...\"\n")

    # -----------------------------------------------------------------------
    # Analysis 7: Junk / Noise Gating Audit
    # -----------------------------------------------------------------------
    print("-" * 115)
    print("ANALYSIS 7: JUNK & NOISE GATING INTEGRITY AUDIT")
    print("-" * 115)
    no_ev_leakage = df[(df["EVENT_MATERIALITY"] == "NO_EVENT") & (df["IMPACT_SCORE"] > 1.0)]
    non_mat_leakage = df[(df["EVENT_MATERIALITY"] == "NON_MATERIAL_FINANCIAL_CONTENT") & (df["IMPACT_SCORE"] > 2.0)]
    print(f"1. NO_EVENT rows with Impact Score > 1.00:              {len(no_ev_leakage)} (Expected: 0)")
    print(f"2. NON_MATERIAL rows with Impact Score > 2.00:          {len(non_mat_leakage)} (Expected: 0)")

    # Check high-scoring signals for non-materiality
    high_impact_signals = df[df["IMPACT_SCORE"] >= 7.0]
    high_non_mat = high_impact_signals[high_impact_signals["EVENT_MATERIALITY"] != "MATERIAL_EVENT"]
    print(f"3. High/Critical Impact (>= 7.0) non-material leakage:  {len(high_non_mat)} (Expected: 0)")

    if len(no_ev_leakage) == 0 and len(non_mat_leakage) == 0:
        print("  -> PASSED: Materiality gate is 100% airtight across all 5,000 real rows.")
    else:
        print("  -> FAILED: Leakage detected!")

    # -----------------------------------------------------------------------
    # Analysis 8: Obvious Major Event Verification
    # -----------------------------------------------------------------------
    print("\n" + "-" * 115)
    print("ANALYSIS 8: REAL HISTORICAL MAJOR CORPORATE EVENT TRACE")
    print("-" * 115)

    test_queries = [
        ("Buffett $12B Buy", r"buffett|12\s*billion|12b"),
        ("Bayer / Monsanto Merger", r"monsanto|mergerfromhell"),
        ("Rosneft Stake / Deal", r"rosneft"),
        ("Oracle Buys Apiary", r"apiary|oracle"),
        ("Samsung Foldable / Battery", r"foldable|battery|galaxy"),
    ]

    for name, pattern in test_queries:
        matches = df[df["TWEET"].str.contains(pattern, case=False, na=False)]
        print(f"\nQuery: {name} (Matches found: {len(matches)})")
        if len(matches) > 0:
            for _, m in matches.head(3).iterrows():
                short_txt = str(m["TWEET"]).replace("\n", " ")[:85]
                print(f"  [Row {m['row_id']:<4}] Score: {m['IMPACT_SCORE']:4.2f} ({m['IMPACT_TIER']:<15}) | Materiality: {m['EVENT_MATERIALITY']:<28} | Event: {m['FINAL_EVENT_TYPE']}")
                print(f"         Text: \"{short_txt}...\"")
        else:
            print("  No occurrences found in this 5k slice.")


def main():
    parser = argparse.ArgumentParser(description="Evaluate ImpactScorer on baseline dataset.")
    parser.add_argument("--materiality-input", type=Path, default=DEFAULT_MATERIALITY_PATH, help="Path to event_materiality4.csv")
    parser.add_argument("--finbert-input", type=Path, default=DEFAULT_FINBERT_PATH, help="Path to finbert_reduced_predictions.csv")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Path to save scored CSV output")
    parser.add_argument("--source-credibility", type=float, default=1.0, help="Source credibility weight")
    args = parser.parse_args()

    merged_df = load_and_merge_data(args.materiality_input, args.finbert_input)
    scored_df = run_baseline_scoring(merged_df, source_credibility=args.source_credibility)

    # Save output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scored_df.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"\nSaved scored baseline output to: {args.output}")

    # Generate analytical report
    print_evaluation_report(scored_df)


if __name__ == "__main__":
    main()
