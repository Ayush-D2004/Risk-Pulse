#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Canonical Validation Suite for ImpactScorer
===========================================
Executes the deterministic ImpactScorer on a curated set of canonical benchmark
cases representing all major dimensions of the scoring model:

1. NO_EVENT gating
2. NON_MATERIAL_FINANCIAL_CONTENT gating
3. Minor product launch vs major earnings miss
4. Major acquisition vs sovereign credit default
5. High-confidence vs low-confidence versions of the same event
6. Breaking first-occurrence vs duplicate / zero-novelty occurrence
7. Unconfirmed vs strong market reaction

This script prints a formatted inspection table and diagnostic analysis
highlighting modeling sensitivities (e.g. multiplicative dampening, novelty=0).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pandas as pd

from src.risk.impact_scorer import ImpactScoreResult, ImpactScorer
from src.risk.risk_signal import MarketContext, RiskSignal


CANONICAL_CASES: List[Dict[str, Any]] = [
    {
        "case_id": "01_no_event",
        "category": "Materiality Gate",
        "description": "NO_EVENT (Angry personal complaint with credit buzzwords)",
        "entity": "Starbucks",
        "source": "twitter",
        "source_credibility": 0.50,
        "sentiment_score": -0.85,
        "event_type": "Other / Unclear",
        "event_confidence": 0.20,
        "materiality": "NO_EVENT",
        "novelty": 1.0,
        "market_context": None,
        "text": "Boycott Starbucks into bankruptcy for terrible service!",
    },
    {
        "case_id": "02_non_material",
        "category": "Materiality Gate",
        "description": "NON_MATERIAL (Routine retail product listing with positive tone)",
        "entity": "Amazon",
        "source": "twitter",
        "source_credibility": 0.60,
        "sentiment_score": 0.40,
        "event_type": "Product / Technology",
        "event_confidence": 0.35,
        "materiality": "NON_MATERIAL_FINANCIAL_CONTENT",
        "novelty": 1.0,
        "market_context": None,
        "text": "Check out this awesome vintage watch for sale on Amazon ebay!",
    },
    {
        "case_id": "03_minor_product",
        "category": "Event Types",
        "description": "Minor product launch (Positive tone, low structural severity)",
        "entity": "Spotify",
        "source": "news",
        "source_credibility": 0.85,
        "sentiment_score": 0.80,
        "event_type": "Product / Technology",
        "event_confidence": 0.70,
        "materiality": "MATERIAL_EVENT",
        "novelty": 1.0,
        "market_context": None,
        "text": "Spotify rolls out minor UI redesign for desktop playlist controls.",
    },
    {
        "case_id": "04_earnings_miss",
        "category": "Event Types",
        "description": "Major corporate earnings miss & profit warning",
        "entity": "Intel",
        "source": "official",
        "source_credibility": 1.00,
        "sentiment_score": -0.70,
        "event_type": "Corporate / Earnings",
        "event_confidence": 0.95,
        "materiality": "MATERIAL_EVENT",
        "novelty": 1.0,
        "market_context": None,
        "text": "Intel misses Q3 EPS by 45%, cuts full-year revenue outlook by $4B.",
    },
    {
        "case_id": "05_major_acquisition",
        "category": "Event Types",
        "description": "Major definitive acquisition announced (Mild positive sentiment)",
        "entity": "Microsoft",
        "source": "news",
        "source_credibility": 0.95,
        "sentiment_score": 0.20,
        "event_type": "Merger & Acquisition",
        "event_confidence": 0.90,
        "materiality": "MATERIAL_EVENT",
        "novelty": 1.0,
        "market_context": None,
        "text": "Microsoft agrees to acquire major studio for $20B in all-cash transaction.",
    },
    {
        "case_id": "06_geopolitical",
        "category": "Event Types",
        "description": "Geopolitical sanctions on oil exports",
        "entity": "Rosneft",
        "source": "news",
        "source_credibility": 0.90,
        "sentiment_score": -0.60,
        "event_type": "Geopolitical",
        "event_confidence": 0.88,
        "materiality": "MATERIAL_EVENT",
        "novelty": 1.0,
        "market_context": None,
        "text": "EU imposes immediate embargo and export restrictions on Rosneft oil shipments.",
    },
    {
        "case_id": "07_sovereign_default",
        "category": "Event Types",
        "description": "Sovereign / corporate bond default (Catastrophic credit)",
        "entity": "Evergrande",
        "source": "official",
        "source_credibility": 1.00,
        "sentiment_score": -0.90,
        "event_type": "Credit Event",
        "event_confidence": 0.98,
        "materiality": "MATERIAL_EVENT",
        "novelty": 1.0,
        "market_context": None,
        "text": "Evergrande officially declared in cross-default on offshore dollar bonds.",
    },
    {
        "case_id": "08a_credit_high_conf",
        "category": "Confidence Sensitivity",
        "description": "Credit Event with HIGH classifier confidence (0.95)",
        "entity": "RetailDebtCo",
        "source": "news",
        "source_credibility": 0.85,
        "sentiment_score": -0.75,
        "event_type": "Credit Event",
        "event_confidence": 0.95,
        "materiality": "MATERIAL_EVENT",
        "novelty": 1.0,
        "market_context": None,
        "text": "RetailDebtCo misses interest payment on $500M senior secured notes.",
    },
    {
        "case_id": "08b_credit_low_conf",
        "category": "Confidence Sensitivity",
        "description": "Credit Event with MODERATE/LOW classifier confidence (0.65)",
        "entity": "RetailDebtCo",
        "source": "news",
        "source_credibility": 0.85,
        "sentiment_score": -0.75,
        "event_type": "Credit Event",
        "event_confidence": 0.65,
        "materiality": "MATERIAL_EVENT",
        "novelty": 1.0,
        "market_context": None,
        "text": "RetailDebtCo misses interest payment on $500M senior secured notes.",
    },
    {
        "case_id": "09a_acq_novelty_1_0",
        "category": "Novelty Sensitivity",
        "description": "Major acquisition: Breaking first report (novelty = 1.0)",
        "entity": "BioPharm",
        "source": "news",
        "source_credibility": 0.90,
        "sentiment_score": 0.15,
        "event_type": "Merger & Acquisition",
        "event_confidence": 0.88,
        "materiality": "MATERIAL_EVENT",
        "novelty": 1.0,
        "market_context": None,
        "text": "BioPharm to be acquired by MegaPharma for $15B.",
    },
    {
        "case_id": "09b_acq_novelty_0_2",
        "category": "Novelty Sensitivity",
        "description": "Major acquisition: Repetitive / syndicated coverage (novelty = 0.2)",
        "entity": "BioPharm",
        "source": "news",
        "source_credibility": 0.90,
        "sentiment_score": 0.15,
        "event_type": "Merger & Acquisition",
        "event_confidence": 0.88,
        "materiality": "MATERIAL_EVENT",
        "novelty": 0.20,
        "market_context": None,
        "text": "BioPharm to be acquired by MegaPharma for $15B.",
    },
    {
        "case_id": "09c_acq_novelty_0_0",
        "category": "Novelty Sensitivity",
        "description": "Major acquisition: Zero novelty duplicate coverage (novelty = 0.0)",
        "entity": "BioPharm",
        "source": "news",
        "source_credibility": 0.90,
        "sentiment_score": 0.15,
        "event_type": "Merger & Acquisition",
        "event_confidence": 0.88,
        "materiality": "MATERIAL_EVENT",
        "novelty": 0.0,
        "market_context": None,
        "text": "BioPharm to be acquired by MegaPharma for $15B.",
    },
    {
        "case_id": "10a_mkt_unconfirmed",
        "category": "Market Context",
        "description": "Earnings miss with NO market reaction / no market data",
        "entity": "AutoCo",
        "source": "official",
        "source_credibility": 1.00,
        "sentiment_score": -0.65,
        "event_type": "Corporate / Earnings",
        "event_confidence": 0.92,
        "materiality": "MATERIAL_EVENT",
        "novelty": 1.0,
        "market_context": None,
        "text": "AutoCo reports Q2 net profit fell 35% on supply chain bottlenecks.",
    },
    {
        "case_id": "10b_mkt_confirmed",
        "category": "Market Context",
        "description": "Earnings miss CONFIRMED by heavy market reaction (CAR -7.2%, Vol 3.4x)",
        "entity": "AutoCo",
        "source": "official",
        "source_credibility": 1.00,
        "sentiment_score": -0.65,
        "event_type": "Corporate / Earnings",
        "event_confidence": 0.92,
        "materiality": "MATERIAL_EVENT",
        "novelty": 1.0,
        "market_context": {
            "abnormal_return": -0.072,
            "volume_ratio": 3.4,
            "volatility": 2.8,
        },
        "text": "AutoCo reports Q2 net profit fell 35% on supply chain bottlenecks.",
    },
]


def run_canonical_validation(verbose: bool = True) -> pd.DataFrame:
    """
    Execute all canonical cases through the current ImpactScorer and
    return a structured comparison DataFrame.
    """
    scorer = ImpactScorer()
    records = []

    for c in CANONICAL_CASES:
        sig = RiskSignal(
            event_id=c["case_id"],
            entity=c["entity"],
            source=c["source"],
            source_credibility=c["source_credibility"],
            sentiment_score=c["sentiment_score"],
            event_type=c["event_type"],
            event_confidence=c["event_confidence"],
            materiality=c["materiality"],
            novelty=c["novelty"],
            market_context=c["market_context"],
            evidence=c["text"],
        )

        res: ImpactScoreResult = scorer.calculate(sig)

        records.append({
            "case_id": c["case_id"],
            "category": c["category"],
            "event_type": c["event_type"],
            "materiality": c["materiality"],
            "conf": c["event_confidence"],
            "conf_mod": res.confidence_modifier,
            "cred": c["source_credibility"],
            "nov": c["novelty"],
            "nov_mod": res.novelty_modifier,
            "sent": c["sentiment_score"],
            "impact_score": res.impact_score,
            "tier": res.impact_tier,
            "is_gated": res.is_gated,
            "raw_composite": round(res.raw_composite, 4),
            "reason": res.impact_reason,
            "description": c["description"],
        })

    df = pd.DataFrame(records)

    if verbose:
        print("=" * 125)
        print("CANONICAL IMPACT SCORER VALIDATION RESULTS (Bounded Confidence & Novelty Modifiers)")
        print("=" * 125)
        cols_to_print = [
            "case_id",
            "event_type",
            "materiality",
            "conf",
            "conf_mod",
            "cred",
            "nov",
            "nov_mod",
            "sent",
            "impact_score",
            "tier",
            "is_gated",
        ]
        print(df[cols_to_print].to_string(index=False))
        print("\n" + "=" * 125)
        print("DETAILED EXPLANATIONS & DIAGNOSTIC OBSERVATIONS")
        print("=" * 125)

        for _, r in df.iterrows():
            print(f"\n[{r['case_id']}] {r['description']}")
            print(f"  -> Score: {r['impact_score']} ({r['tier']}) | Raw: {r['raw_composite']} | Gated: {r['is_gated']}")
            print(f"  -> Reason: {r['reason']}")

        print("\n" + "=" * 125)
        print("SPECIFIC DIAGNOSTIC FINDINGS (Bounded Modifiers Validation):")
        print("=" * 125)

        # Issue 1 Diagnostic: Confidence Sensitivity
        c_high = df[df["case_id"] == "08a_credit_high_conf"].iloc[0]
        c_low = df[df["case_id"] == "08b_credit_low_conf"].iloc[0]
        conf_drop = c_high["impact_score"] - c_low["impact_score"]
        print(f"\n[Issue 1 - Confidence Modifier (0.70 + 0.30 * conf)]:")
        print(f"  Credit event at 0.95 confidence: {c_high['impact_score']} ({c_high['tier']}) [conf_mod: {c_high['conf_mod']}]")
        print(f"  Credit event at 0.65 confidence: {c_low['impact_score']} ({c_low['tier']}) [conf_mod: {c_low['conf_mod']}]")
        print(f"  Delta: -{conf_drop:.2f} points drop. (Previously was -2.27 drop down to 5.92 Moderate Impact).")

        # Issue 2 Diagnostic: Novelty Sensitivity
        acq_1 = df[df["case_id"] == "09a_acq_novelty_1_0"].iloc[0]
        acq_02 = df[df["case_id"] == "09b_acq_novelty_0_2"].iloc[0]
        acq_0 = df[df["case_id"] == "09c_acq_novelty_0_0"].iloc[0]
        print(f"\n[Issue 2 - Novelty Modifier (0.75 + 0.25 * nov) with constant 0.90 credibility]:")
        print(f"  Major $15B Acquisition (novelty = 1.0): {acq_1['impact_score']} ({acq_1['tier']}) [nov_mod: {acq_1['nov_mod']}]")
        print(f"  Major $15B Acquisition (novelty = 0.2): {acq_02['impact_score']} ({acq_02['tier']}) [nov_mod: {acq_02['nov_mod']}]")
        print(f"  Major $15B Acquisition (novelty = 0.0): {acq_0['impact_score']} ({acq_0['tier']}) [nov_mod: {acq_0['nov_mod']}]")
        print(f"  Retained severity: Even at novelty = 0.0, the acquisition still scores {acq_0['impact_score']} ({acq_0['tier']}) instead of being destroyed to 1.0!")

        # Market Context Diagnostic
        m_none = df[df["case_id"] == "10a_mkt_unconfirmed"].iloc[0]
        m_heavy = df[df["case_id"] == "10b_mkt_confirmed"].iloc[0]
        print(f"\n[Market Context Confirmation Effect]:")
        print(f"  Earnings miss without market data: {m_none['impact_score']} ({m_none['tier']})")
        print(f"  Earnings miss with CAR -7.2% / Vol 3.4x: {m_heavy['impact_score']} ({m_heavy['tier']})")
        print(f"  Uplift from market reaction: +{m_heavy['impact_score'] - m_none['impact_score']:.2f} points.")

    return df


if __name__ == "__main__":
    run_canonical_validation(verbose=True)
