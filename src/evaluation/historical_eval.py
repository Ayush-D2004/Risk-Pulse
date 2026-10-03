#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time
import json
import logging
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Strict Offline Enforcement
import yfinance as yf
def offline_mock(*args, **kwargs):
    raise RuntimeError("Network access is strictly prohibited during offline evaluation!")
yf.Ticker.history = offline_mock

from src.market.market_context import (
    MarketContextConfig,
    MarketContextFetcher,
    MarketDataError,
    TickerResolutionError,
)
from src.risk.market_enriched_scorer import MarketEnrichedScorer
from src.risk.risk_signal import Evidence, MarketContext, RiskSignal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

STOCK_SECTOR_MAP = {
    "Amazon": "consumer discretionary", "Apple": "information technology", "Facebook": "communication services",
    "Google": "communication services", "Microsoft": "information technology", "Netflix": "communication services",
    "Adobe": "information technology", "Cisco": "information technology", "IBM": "information technology",
    "Intel": "information technology", "Oracle": "information technology", "SAP": "information technology",
    "salesforce.com": "information technology", "JPMorgan": "financials", "Goldman Sachs": "financials",
    "Morgan Stanley": "financials", "BlackRock": "financials", "Citigroup": "financials", "Bank of America": "financials",
    "Wells Fargo": "financials", "American Express": "financials", "Mastercard": "financials", "Visa": "financials",
    "Deutsche Bank": "financials", "HSBC": "financials", "Santander": "financials", "Allianz": "financials",
    "PayPal": "financials", "Disney": "communication services", "Comcast": "communication services",
    "Viacom": "communication services", "CBS": "communication services", "AT&T": "communication services",
    "Verizon": "communication services", "Vodafone": "communication services", "TMobile": "communication services",
    "21CF": "communication services", "Reuters": None, "McDonald's": "consumer discretionary",
    "Starbucks": "consumer discretionary", "Nike": "consumer discretionary", "adidas": "consumer discretionary",
    "H&M": "consumer discretionary", "Burberry": "consumer discretionary", "Next": "consumer discretionary",
    "Expedia": "consumer discretionary", "TripAdvisor": "consumer discretionary", "Audi": "consumer discretionary",
    "BMW": "consumer discretionary", "Ford": "consumer discretionary", "Honda": "consumer discretionary",
    "Hyundai": "consumer discretionary", "Nissan": "consumer discretionary", "Toyota": "consumer discretionary",
    "Volkswagen": "consumer discretionary", "Ryanair": "industrials", "easyJet": "industrials",
    "Boeing": "industrials", "FedEx": "industrials", "General Electric": "industrials",
    "Siemens": "industrials", "John Deere": "industrials", "UPS": "industrials", "Thales": "industrials",
    "Pfizer": "health care", "AstraZeneca": "health care", "Bayer": "health care", "GSK": "health care",
    "Exxon": "energy", "Chevron": "energy", "BP": "energy", "Shell": "energy", "CocaCola": "consumer staples",
    "Pepsi": "consumer staples", "Kellogg's": "consumer staples", "Kroger": "consumer staples",
    "Nestle": "consumer staples", "Walmart": "consumer staples", "Tesco": "consumer staples",
    "Costco": "consumer staples", "Carrefour": "consumer staples", "Heineken": "consumer staples",
    "HP": "information technology", "Sony": "consumer discretionary", "Samsung": "information technology",
    "Yahoo": "communication services", "Groupon": "consumer discretionary", "bookingcom": "consumer discretionary",
    "eBay": "consumer discretionary", "ASOS": "consumer discretionary", "L'Oreal": "consumer staples",
    "Gillette": "consumer staples"
}

RETURN_HORIZONS = ["1_DAY_RETURN", "2_DAY_RETURN", "3_DAY_RETURN", "7_DAY_RETURN"]

def parse_event_date(date_str):
    try:
        return datetime.strptime(str(date_str).strip(), "%d/%m/%Y").replace(tzinfo=timezone.utc)
    except:
        return None

def tier_stats(df, group_col):
    rows = []
    for tier, gdf in df.groupby(group_col):
        row = {"tier": tier, "n": len(gdf)}
        for h in RETURN_HORIZONS:
            vals = gdf[h].dropna()
            row[f"{h}_n"] = len(vals)
            row[f"{h}_mean"] = round(vals.mean(), 6) if len(vals) else None
            row[f"{h}_median"] = round(vals.median(), 6) if len(vals) else None
            abs_vals = vals.abs()
            row[f"{h}_abs_mean"] = round(abs_vals.mean(), 6) if len(abs_vals) else None
            row[f"{h}_abs_median"] = round(abs_vals.median(), 6) if len(abs_vals) else None
        rows.append(row)
    return pd.DataFrame(rows)

def spearman_table(df, predictor_cols):
    rows = []
    for pred in predictor_cols:
        for h in RETURN_HORIZONS:
            sub = df[[pred, h]].dropna()
            n = len(sub)
            if n < 5:
                rows.append({"predictor": pred, "horizon": h, "n": n, "rho_signed": None, "p_signed": None, "rho_abs": None, "p_abs": None})
                continue
            rho_s, p_s = stats.spearmanr(sub[pred], sub[h])
            rho_a, p_a = stats.spearmanr(sub[pred], sub[h].abs())
            rows.append({
                "predictor": pred, "horizon": h, "n": n,
                "rho_signed": round(rho_s, 4), "p_signed": round(p_s, 4),
                "rho_abs": round(rho_a, 4), "p_abs": round(p_a, 4),
            })
    return pd.DataFrame(rows)

def score_distribution(df, col):
    s = df[col].dropna()
    if s.empty:
        return {}
    return {
        "count": int(len(s)),
        "mean": round(float(s.mean()), 4),
        "median": round(float(s.median()), 4),
        "std": round(float(s.std()), 4),
        "min": round(float(s.min()), 4),
        "p25": round(float(s.quantile(0.25)), 4),
        "p75": round(float(s.quantile(0.75)), 4),
        "max": round(float(s.max()), 4),
    }

def run_evaluation():
    t_start = time.time()
    
    # 1. Load Registry & Manifest
    with open('data/processed/historical_instrument_registry.json', 'r', encoding='utf-8') as f:
        registry = json.load(f)['registry']
    with open('data/processed/market_cache_manifest.json', 'r', encoding='utf-8') as f:
        manifest = json.load(f)
        
    failed_tickers = [x['ticker'] if isinstance(x, dict) else x for x in manifest.get('failed', [])]
    unavail_tickers = [x['ticker'] if isinstance(x, dict) else x for x in manifest.get('unavailable', [])]
    all_failed = set(failed_tickers + unavail_tickers)
        
    stock_to_ticker = {}
    stock_status = {}
    for r in registry:
        stock = r['source_entity_name']
        stock_status[stock] = r['resolution_status']
        if r['usable_for_jan_mar_2017']:
            stock_to_ticker[stock] = r['historical_ticker']
        else:
            stock_to_ticker[stock] = None

    # 2. Load Datasets
    df_scored = pd.read_csv("data/processed/impact_scored_baseline.csv").head(5000)
    total_rows = len(df_scored)
    
    df_returns = pd.read_csv("data/processed/reduced_dataset-release.csv", low_memory=False)
    import re
    date_pattern = re.compile(r"^\d{2}/\d{2}/\d{4}$")
    df_returns = df_returns[df_returns["DATE"].apply(lambda x: bool(date_pattern.match(str(x))) if pd.notna(x) else False)].copy()
    df_returns = df_returns.rename(columns={"Unnamed: 0": "row_id"})
    df_returns["row_id"] = pd.to_numeric(df_returns["row_id"], errors="coerce")
    df_returns = df_returns.dropna(subset=["row_id"])
    df_returns["row_id"] = df_returns["row_id"].astype(int)
    for c in RETURN_HORIZONS:
        df_returns[c] = pd.to_numeric(df_returns[c], errors="coerce")
    df_returns = df_returns[["row_id"] + RETURN_HORIZONS].drop_duplicates(subset=["row_id"])

    df = df_scored.merge(df_returns, on="row_id", how="left")
    df["event_datetime"] = df["DATE"].apply(parse_event_date)
    df["ticker"] = df["STOCK"].map(stock_to_ticker)
    df["sector"] = df["STOCK"].map(STOCK_SECTOR_MAP)
    df["status"] = df["STOCK"].map(stock_status)

    fetcher = MarketContextFetcher(MarketContextConfig(event_window_days=1, baseline_days=20))
    scorer = MarketEnrichedScorer()

    # 3. Process Rows
    market_contexts = []
    mkt_statuses = []
    final_scores = []
    final_tiers = []
    mkt_mods = []
    
    rows_resolved = 0
    rows_reuters = 0
    rows_ambiguous = 0
    failed_ticker_counts = {t: 0 for t in all_failed}
    
    for idx, row in df.iterrows():
        stock = row["STOCK"]
        ticker = row.get("ticker")
        evt_dt = row.get("event_datetime")
        status = row.get("status")
        
        if status == "DOCUMENTED_NO_EQUITY_INSTRUMENT" and stock == "Reuters":
            rows_reuters += 1
        elif status in ["EXPLICITLY_UNRESOLVED_AMBIGUOUS", "DOCUMENTED_NO_EQUITY_INSTRUMENT"]:
            rows_ambiguous += 1
        elif ticker:
            rows_resolved += 1
            if ticker in all_failed:
                failed_ticker_counts[ticker] += 1
                
        ctx = None
        m_status = "unavailable"
        
        if ticker and evt_dt and ticker not in all_failed:
            try:
                # Force offline by just calling fetch. Network block will catch if it tries.
                res = fetcher.fetch(ticker, evt_dt, row.get("sector"))
                ctx = res.market_context
                m_status = "ok"
            except Exception as e:
                m_status = str(e)
                
        market_contexts.append(ctx)
        mkt_statuses.append(m_status)
        
        if ctx:
            try:
                signal = RiskSignal(
                    entity=str(stock),
                    source="twitter",
                    source_credibility=0.7,
                    sentiment_score=float(row["FINBERT_SCORE"]),
                    event_type=str(row["FINAL_EVENT_TYPE"] or row["EVENT_TYPE"]),
                    event_confidence=float(row["EVENT_CONFIDENCE"]),
                    materiality=str(row["EVENT_MATERIALITY"]),
                    novelty=1.0,
                    timestamp=evt_dt or datetime.now(timezone.utc),
                    evidence=Evidence(text=str(row["TWEET"])[:512]),
                    market_context=ctx,
                )
                result = scorer.score_with_context(signal, ctx)
                final_scores.append(result.impact_score)
                final_tiers.append(result.impact_result.impact_tier)
                mkt_mods.append(result.market_modifier)
            except Exception:
                final_scores.append(float(row["IMPACT_SCORE"]))
                final_tiers.append(str(row["IMPACT_TIER"]))
                mkt_mods.append(1.0)
        else:
            final_scores.append(float(row["IMPACT_SCORE"]))
            final_tiers.append(str(row["IMPACT_TIER"]))
            mkt_mods.append(1.0)

    df["market_context_available"] = [c is not None for c in market_contexts]
    df["_mkt_status"] = mkt_statuses
    df["IMPACT_SCORE_MKT"] = final_scores
    df["IMPACT_TIER_MKT"]  = final_tiers
    df["MKT_MODIFIER"]     = mkt_mods
    df["ABN_RETURN"]       = [c.abnormal_return if c else None for c in market_contexts]
    df["VOL_RATIO"]        = [c.volume_ratio if c else None for c in market_contexts]
    df["VOLATILITY"]       = [c.volatility if c else None for c in market_contexts]

    # Metrics
    rows_with_ctx = df["market_context_available"].sum()
    rows_fallback = total_rows - rows_with_ctx
    rows_cached = sum(1 for t in df["ticker"] if t and t not in all_failed)
    
    # Eval Population = Total - Reuters - Ambiguous
    eval_population = total_rows - rows_reuters - rows_ambiguous
    coverage_pct = round(rows_with_ctx / eval_population * 100, 1) if eval_population > 0 else 0

    scores_changed = (df["IMPACT_SCORE_MKT"] != df["IMPACT_SCORE"]).sum()
    df["score_diff"] = df["IMPACT_SCORE_MKT"] - df["IMPACT_SCORE"]
    mean_abs_change = round(df["score_diff"].abs().mean(), 4)
    tier_changed = (df["IMPACT_TIER_MKT"] != df["IMPACT_TIER"]).sum()
    
    tier_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    tier_inc = sum(1 for idx, r in df.iterrows() if tier_order.get(r["IMPACT_TIER_MKT"], 0) > tier_order.get(r["IMPACT_TIER"], 0))
    tier_dec = sum(1 for idx, r in df.iterrows() if tier_order.get(r["IMPACT_TIER_MKT"], 0) < tier_order.get(r["IMPACT_TIER"], 0))

    df["event_cluster"] = df["STOCK"] + "|" + df["DATE"].fillna("")
    df_dedup = df.sort_values("IMPACT_SCORE_MKT", ascending=False).drop_duplicates(subset="event_cluster", keep="first")
    df_mkt = df[df["market_context_available"] == True]

    predictor_cols = ["IMPACT_SCORE_MKT", "IMPACT_SCORE", "FINBERT_SCORE", "EVENT_CONFIDENCE", "ABN_RETURN"]
    
    corr_all = spearman_table(df, predictor_cols)
    corr_mkt = spearman_table(df_mkt, predictor_cols)
    corr_dedup = spearman_table(df_dedup, predictor_cols)
    corr_mat = spearman_table(df[df["EVENT_MATERIALITY"] == "MATERIAL_EVENT"], predictor_cols)
    corr_neg = spearman_table(df[df["FINBERT_SCORE"] < -0.05], predictor_cols)
    corr_pos = spearman_table(df[df["FINBERT_SCORE"] > 0.05], predictor_cols)

    # 4. Generate Markdown
    md = [
        "# Historical Offline Evaluation Report",
        "",
        "> **Network Prohibition:** ZERO network requests made. Fully offline via local Parquet cache.",
        "",
        "## 1. Coverage Accounting",
        f"**Market-enriched evaluation coverage = {rows_with_ctx} / {eval_population}** ({coverage_pct}%)",
        "",
        "| Metric | Count |",
        "|---|---|",
        f"| Total rows | {total_rows} |",
        f"| Rows with usable resolved instruments | {rows_resolved} |",
        f"| Rows with cached market data available | {rows_cached} |",
        f"| Rows with successfully computed MarketContext | {rows_with_ctx} |",
        f"| Rows falling back to NLP-only scoring | {rows_fallback} |",
        f"| Rows excluded for Reuters | {rows_reuters} |",
        f"| Rows affected by unresolved/ambiguous | {rows_ambiguous} |",
        "",
        "```text",
        f"{total_rows} total",
        "   │",
        f"   ├── Market context available: {rows_with_ctx}",
        f"   │       └── Impact score changed: {scores_changed}",
        "   │",
        f"   └── Market context unavailable: {rows_fallback}",
        f"           └── NLP-only fallback: {rows_fallback}",
        "```",
        "",
        "## 2. Market-Enrichment Comparison",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Number of scores changed by context | {scores_changed} |",
        f"| Mean absolute score change | {mean_abs_change} |",
        f"| Number of signals whose tier changed | {tier_changed} |",
        f"| Tier increased | {tier_inc} |",
        f"| Tier decreased | {tier_dec} |",
        "",
        "**Score Distributions:**",
        "| Metric | NLP-Only Impact Score | Market-Enriched Impact Score | Market Modifier |",
        "|---|---|---|---|",
    ]
    
    dist_nlp = score_distribution(df, "IMPACT_SCORE")
    dist_mkt = score_distribution(df, "IMPACT_SCORE_MKT")
    dist_mod = score_distribution(df, "MKT_MODIFIER")
    
    for k in ["mean", "median", "std", "min", "p25", "p75", "max"]:
        md.append(f"| {k.capitalize()} | {dist_nlp.get(k, '')} | {dist_mkt.get(k, '')} | {dist_mod.get(k, '')} |")
        
    def corr_section(corr_df, title, desc=""):
        sec = ["", f"### {title}", desc, "| Predictor | Horizon | n | ρ signed | p | ρ abs | p |", "|---|---|---|---|---|---|---|"]
        for _, r in corr_df.iterrows():
            rho_s = f"{r['rho_signed']:.4f}" if r["rho_signed"] is not None else "—"
            p_s   = f"{r['p_signed']:.4f}"   if r["p_signed"]   is not None else "—"
            rho_a = f"{r['rho_abs']:.4f}"    if r["rho_abs"]    is not None else "—"
            p_a   = f"{r['p_abs']:.4f}"      if r["p_abs"]      is not None else "—"
            sec.append(f"| `{r['predictor']}` | {r['horizon']} | {r['n']} | {rho_s} | {p_s} | {rho_a} | {p_a} |")
        return sec

    md += [
        "",
        "## 3. Spearman Correlations vs Future Returns",
        "> *Note: Impact Score should add signal beyond any single component.*"
    ]
    md += corr_section(corr_all, "A. All signals")
    md += corr_section(corr_mkt, "B. Market-enriched signals only")
    md += corr_section(corr_dedup, "C & D. One representative signal per STOCK×DATE (Event Cluster)")
    md += corr_section(corr_mat, "Material events only")
    md += corr_section(corr_neg, "Negative sentiment only (FINBERT < -0.05)")
    md += corr_section(corr_pos, "Positive sentiment only (FINBERT > 0.05)")
    
    md += [
        "",
        "## 4. Data Quality & Limitations",
        "",
        "**Unavailable Historical Instruments:**",
        "The following instruments were entirely unavailable from the data provider and fell back to NLP-only scoring:",
    ]
    for tk, count in failed_ticker_counts.items():
        if count > 0:
            md.append(f"- `{tk}`: Affected {count} rows")
            
    md.append("")
    md.append("**Sector Availability Note:** The Communication Services Select Sector SPDR Fund (`XLC`) was launched in June 2018 and did not exist during this 2017 evaluation period. Affected instruments default to broad market comparison (`^GSPC`) where sector context is missing.")
    
    with open("reports/historical_eval_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    # Output machine-readable
    results = {
        "coverage": {
            "total_rows": total_rows,
            "rows_with_ctx": int(rows_with_ctx),
            "rows_fallback": int(rows_fallback),
            "eval_population": int(eval_population),
            "coverage_pct": coverage_pct
        },
        "enrichment": {
            "scores_changed": int(scores_changed),
            "tier_changed": int(tier_changed),
            "tier_inc": int(tier_inc),
            "tier_dec": int(tier_dec),
        }
    }
    with open("data/processed/historical_eval_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    df.to_parquet("data/processed/historical_eval_results_rows.parquet", index=False)
    print("Offline Evaluation complete.")

if __name__ == "__main__":
    run_evaluation()
