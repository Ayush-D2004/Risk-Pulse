"""
Leakage-safe evaluation helpers for historical tweet sentiment.

Important:
LSTM_POLARITY and TEXTBLOB_POLARITY are treated as benchmark/reference
signals, NOT as ground-truth labels for training FinBERT.
Future-return columns are evaluation-only targets.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def add_finbert_score(df: pd.DataFrame, predictor, text_col: str = "TWEET",
                      batch_size: int = 16) -> pd.DataFrame:
    results = predictor.predict(df[text_col].fillna("").tolist(), batch_size=batch_size)
    out = df.copy()
    out["FINBERT_POSITIVE"] = [r.positive for r in results]
    out["FINBERT_NEGATIVE"] = [r.negative for r in results]
    out["FINBERT_NEUTRAL"] = [r.neutral for r in results]
    out["FINBERT_SCORE"] = [r.score for r in results]
    out["FINBERT_LABEL"] = [r.label for r in results]
    return out


def correlation_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Descriptive correlations only. This does not establish causality.
    """
    cols = [
        "FINBERT_SCORE", "LSTM_POLARITY", "TEXTBLOB_POLARITY",
        "1_DAY_RETURN", "2_DAY_RETURN", "3_DAY_RETURN", "7_DAY_RETURN",
        "VOLATILITY_10D", "VOLATILITY_30D",
    ]
    cols = [c for c in cols if c in df.columns]
    return df[cols].corr(numeric_only=True)


def bucketed_return_summary(
    df: pd.DataFrame,
    score_col: str = "FINBERT_SCORE",
    return_col: str = "1_DAY_RETURN",
    bins: int = 5,
) -> pd.DataFrame:
    work = df[[score_col, return_col]].dropna().copy()
    work["sentiment_bucket"] = pd.qcut(
        work[score_col], q=bins, duplicates="drop"
    )
    return (
        work.groupby("sentiment_bucket", observed=True)[return_col]
        .agg(["count", "mean", "median", "std"])
        .reset_index()
    )
