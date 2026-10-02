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

import io
import sys
from typing import Any, Dict, List

import pandas as pd

from src.risk.impact_scorer import ImpactScoreResult, ImpactScorer
from src.risk.risk_signal import MarketContext, RiskSignal

# Ensure UTF-8 output on Windows consoles that default to cp1252
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


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
    # -----------------------------------------------------------------------
    # New market-context integration cases (Step 2)
    # Event | NLP signal | Market context | Expected behaviour
    # -----------------------------------------------------------------------
    {
        "case_id": "11a_earnings_miss_mkt_decline",
        "category": "Market Context Integration",
        "description": "Earnings miss: Negative NLP + strong abnormal decline + high volume -> score INCREASES",
        "entity": "RetailBank",
        "source": "official",
        "source_credibility": 1.00,
        "sentiment_score": -0.75,
        "event_type": "Corporate / Earnings",
        "event_confidence": 0.91,
        "materiality": "MATERIAL_EVENT",
        "novelty": 1.0,
        "market_context": {
            "abnormal_return": -0.085,   # -8.5% CAR — significant price dislocation
            "volume_ratio": 4.2,          # 4.2× baseline volume
            "volatility": 3.1,            # elevated vol z-score
        },
        "text": "RetailBank Q3 earnings miss EPS by 52%; NIM compression worsens; guidance slashed.",
    },
    {
        "case_id": "11b_earnings_miss_no_move",
        "category": "Market Context Integration",
        "description": "Earnings miss: Negative NLP + NO abnormal movement -> smaller score increase vs 11a",
        "entity": "RetailBank",
        "source": "official",
        "source_credibility": 1.00,
        "sentiment_score": -0.75,
        "event_type": "Corporate / Earnings",
        "event_confidence": 0.91,
        "materiality": "MATERIAL_EVENT",
        "novelty": 1.0,
        "market_context": {
            "abnormal_return": 0.002,    # flat — market priced it in
            "volume_ratio": 1.1,          # barely above baseline
            "volatility": 0.9,            # low vol
        },
        "text": "RetailBank Q3 earnings miss EPS by 52%; NIM compression worsens; guidance slashed.",
    },
    {
        "case_id": "12_ma_large_abnormal",
        "category": "Market Context Integration",
        "description": "M&A: Positive NLP + large abnormal move -> context modifies score upward",
        "entity": "PharmaCo",
        "source": "news",
        "source_credibility": 0.95,
        "sentiment_score": 0.55,
        "event_type": "Merger & Acquisition",
        "event_confidence": 0.89,
        "materiality": "MATERIAL_EVENT",
        "novelty": 1.0,
        "market_context": {
            "abnormal_return": 0.18,     # +18% takeover premium jump
            "volume_ratio": 6.5,          # surge in volume
            "volatility": 2.5,
        },
        "text": "PharmaCo to be acquired by GlobalPharma in $22B all-cash deal at 38% premium.",
    },
    {
        "case_id": "13a_geopolitical_mkt_confirms",
        "category": "Market Context Integration",
        "description": "Geopolitical: Negative NLP + market confirms reaction -> higher impact",
        "entity": "EnergyMajor",
        "source": "news",
        "source_credibility": 0.90,
        "sentiment_score": -0.72,
        "event_type": "Geopolitical",
        "event_confidence": 0.87,
        "materiality": "MATERIAL_EVENT",
        "novelty": 1.0,
        "market_context": {
            "abnormal_return": -0.065,   # -6.5% on sanctions news
            "volume_ratio": 3.8,
            "volatility": 2.7,
        },
        "text": "New US sanctions target EnergyMajor oil exports; analysts warn of supply disruption.",
    },
    {
        "case_id": "13b_geopolitical_mkt_unchanged",
        "category": "Market Context Integration",
        "description": "Geopolitical: Negative NLP + market unchanged -> do NOT automatically score as catastrophic",
        "entity": "EnergyMajor",
        "source": "news",
        "source_credibility": 0.90,
        "sentiment_score": -0.72,
        "event_type": "Geopolitical",
        "event_confidence": 0.87,
        "materiality": "MATERIAL_EVENT",
        "novelty": 1.0,
        "market_context": {
            "abnormal_return": 0.003,    # essentially flat — market not reacting
            "volume_ratio": 1.05,
            "volatility": 0.8,
        },
        "text": "New US sanctions target EnergyMajor oil exports; analysts warn of supply disruption.",
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
            "mkt_mod": res.market_modifier,
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
        print("CANONICAL IMPACT SCORER VALIDATION RESULTS (with Market Context Integration)")
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
            "mkt_mod",
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
            print(f"  -> Score: {r['impact_score']} ({r['tier']}) | Raw: {r['raw_composite']} | Gated: {r['is_gated']} | MktMod: {r['mkt_mod']}")
            print(f"  -> Reason: {r['reason']}")

        print("\n" + "=" * 125)
        print("SPECIFIC DIAGNOSTIC FINDINGS (Bounded Modifiers Validation):")
        print("=" * 125)

        # Diagnostic 1: Confidence Sensitivity
        c_high = df[df["case_id"] == "08a_credit_high_conf"].iloc[0]
        c_low = df[df["case_id"] == "08b_credit_low_conf"].iloc[0]
        conf_drop = c_high["impact_score"] - c_low["impact_score"]
        print(f"\n[Diagnostic 1 - Confidence Modifier (0.70 + 0.30 * conf)]:")
        print(f"  Credit event at 0.95 confidence: {c_high['impact_score']} ({c_high['tier']}) [conf_mod: {c_high['conf_mod']}]")
        print(f"  Credit event at 0.65 confidence: {c_low['impact_score']} ({c_low['tier']}) [conf_mod: {c_low['conf_mod']}]")
        print(f"  Delta: -{conf_drop:.2f} points drop.")

        # Diagnostic 2: Novelty Sensitivity
        acq_1 = df[df["case_id"] == "09a_acq_novelty_1_0"].iloc[0]
        acq_02 = df[df["case_id"] == "09b_acq_novelty_0_2"].iloc[0]
        acq_0 = df[df["case_id"] == "09c_acq_novelty_0_0"].iloc[0]
        print(f"\n[Diagnostic 2 - Novelty Modifier (0.75 + 0.25 * nov)]:")
        print(f"  Major $15B Acquisition (novelty = 1.0): {acq_1['impact_score']} ({acq_1['tier']}) [nov_mod: {acq_1['nov_mod']}]")
        print(f"  Major $15B Acquisition (novelty = 0.2): {acq_02['impact_score']} ({acq_02['tier']}) [nov_mod: {acq_02['nov_mod']}]")
        print(f"  Major $15B Acquisition (novelty = 0.0): {acq_0['impact_score']} ({acq_0['tier']}) [nov_mod: {acq_0['nov_mod']}]")
        print(f"  Retained severity: Even at novelty = 0.0, the acquisition still scores {acq_0['impact_score']} ({acq_0['tier']}).")

        # Diagnostic 3: Original market confirmation effect (cases 10a/10b)
        m_none = df[df["case_id"] == "10a_mkt_unconfirmed"].iloc[0]
        m_heavy = df[df["case_id"] == "10b_mkt_confirmed"].iloc[0]
        print(f"\n[Diagnostic 3 - Market Context Confirmation Effect (original cases 10a/10b)]:")
        print(f"  Earnings miss without market data: {m_none['impact_score']} ({m_none['tier']}) [mkt_mod: {m_none['mkt_mod']}]")
        print(f"  Earnings miss with CAR -7.2% / Vol 3.4x: {m_heavy['impact_score']} ({m_heavy['tier']}) [mkt_mod: {m_heavy['mkt_mod']}]")
        print(f"  Uplift from market reaction: +{m_heavy['impact_score'] - m_none['impact_score']:.2f} points.")

        # Diagnostic 4: Earnings miss — market confirms vs does not
        e_confirm = df[df["case_id"] == "11a_earnings_miss_mkt_decline"].iloc[0]
        e_flat = df[df["case_id"] == "11b_earnings_miss_no_move"].iloc[0]
        print(f"\n[Diagnostic 4 - Earnings Miss: Market confirmation vs muted reaction]:")
        print(f"  Negative NLP + strong decline (CAR -8.5%, Vol 4.2x): {e_confirm['impact_score']} ({e_confirm['tier']}) [mkt_mod: {e_confirm['mkt_mod']}]")
        print(f"  Negative NLP + flat market  (CAR +0.2%, Vol 1.1x): {e_flat['impact_score']} ({e_flat['tier']}) [mkt_mod: {e_flat['mkt_mod']}]")
        print(f"  Score difference (market-confirmed vs not): +{e_confirm['impact_score'] - e_flat['impact_score']:.2f} points.")
        assert e_confirm["impact_score"] > e_flat["impact_score"], "FAIL: market-confirmed earnings miss must score higher"
        print(f"  PASS: market-confirmed > market-flat ✓")

        # Diagnostic 5: M&A — large abnormal move modifies score upward
        ma_large = df[df["case_id"] == "12_ma_large_abnormal"].iloc[0]
        ma_base = df[df["case_id"] == "05_major_acquisition"].iloc[0]  # same event type, no mkt ctx
        print(f"\n[Diagnostic 5 - M&A: Large abnormal move vs no market context]:")
        print(f"  M&A no market context: {ma_base['impact_score']} ({ma_base['tier']}) [mkt_mod: {ma_base['mkt_mod']}]")
        print(f"  M&A +18% CAR / Vol 6.5x: {ma_large['impact_score']} ({ma_large['tier']}) [mkt_mod: {ma_large['mkt_mod']}]")
        assert ma_large["mkt_mod"] > ma_base["mkt_mod"], "FAIL: large abnormal move must increase market modifier"
        print(f"  PASS: market modifier elevated for large abnormal move ✓")

        # Diagnostic 6: Geopolitical — market confirms vs market unchanged
        geo_confirm = df[df["case_id"] == "13a_geopolitical_mkt_confirms"].iloc[0]
        geo_flat = df[df["case_id"] == "13b_geopolitical_mkt_unchanged"].iloc[0]
        print(f"\n[Diagnostic 6 - Geopolitical: Market confirms vs market unchanged]:")
        print(f"  Geopolitical + market reaction (CAR -6.5%, Vol 3.8x): {geo_confirm['impact_score']} ({geo_confirm['tier']}) [mkt_mod: {geo_confirm['mkt_mod']}]")
        print(f"  Geopolitical + market unchanged (CAR +0.3%, Vol 1.05x): {geo_flat['impact_score']} ({geo_flat['tier']}) [mkt_mod: {geo_flat['mkt_mod']}]")
        print(f"  Score difference: +{geo_confirm['impact_score'] - geo_flat['impact_score']:.2f} points.")
        assert geo_confirm["impact_score"] > geo_flat["impact_score"], "FAIL: market-confirmed geopolitical must score higher"
        assert geo_flat["impact_score"] < 9.0, "FAIL: muted-market geopolitical must NOT be automatically catastrophic"
        print(f"  PASS: market-confirmed > market-unchanged, and muted-market < 9.0 ✓")

    return df


if __name__ == "__main__":
    run_canonical_validation(verbose=True)
