"""
Output Validation Utilities
==============================
Stage-output validators that confirm each stage produced correct, complete,
in-bounds results before marking a chunk COMPLETE.

Rules
-----
* Invalid rows are COUNTED and REPORTED — never silently repaired.
* Validators return a ValidationResult; callers decide whether to fail.
* All checks are run against the actual output file, not in-memory state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Validation result container
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    valid: bool
    input_rows: int
    output_rows: int
    missing_row_ids: List = field(default_factory=list)
    duplicate_row_ids: List = field(default_factory=list)
    extra_row_ids: List = field(default_factory=list)
    invalid_rows: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def report(self) -> str:
        lines = [
            f"  valid={self.valid}",
            f"  input_rows={self.input_rows}  output_rows={self.output_rows}",
            f"  missing_row_ids={len(self.missing_row_ids)}",
            f"  duplicate_row_ids={len(self.duplicate_row_ids)}",
            f"  extra_row_ids={len(self.extra_row_ids)}",
            f"  invalid_rows={self.invalid_rows}",
        ]
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        for w in self.warnings:
            lines.append(f"  WARN: {w}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Leakage-protected column list
# ---------------------------------------------------------------------------

LEAKAGE_COLUMNS = frozenset([
    "1_DAY_RETURN",
    "2_DAY_RETURN",
    "3_DAY_RETURN",
    "7_DAY_RETURN",
    "LSTM_POLARITY",
    "TEXTBLOB_POLARITY",
])


def check_leakage_columns(df: pd.DataFrame, context: str = "") -> List[str]:
    """
    Return a list of error strings for any leakage column present in df.

    Raises nothing — callers decide how to handle violations.
    """
    violations = []
    for col in LEAKAGE_COLUMNS:
        if col in df.columns:
            violations.append(
                f"[LEAKAGE] Column '{col}' present in {context or 'DataFrame'}. "
                f"This column MUST NOT enter any model inference path."
            )
    return violations


def assert_no_leakage(df: pd.DataFrame, context: str = "") -> None:
    """
    Raise ValueError if any leakage column is found in df.

    Use this as a hard guard at model input boundaries.
    """
    violations = check_leakage_columns(df, context)
    if violations:
        raise ValueError(
            "LEAKAGE GUARD TRIGGERED:\n" + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# Row identity validators
# ---------------------------------------------------------------------------


def validate_row_identity(
    expected_row_ids: List,
    actual_row_ids: List,
    allow_duplicates: bool = False,
) -> ValidationResult:
    """
    Verify that output row IDs exactly match expected input row IDs.

    Parameters
    ----------
    expected_row_ids : list
        Row IDs from the input slice (e.g. [0, 1, 2, ..., N-1]).
    actual_row_ids : list
        Row IDs found in the output file.
    allow_duplicates : bool
        If False, duplicate output IDs are flagged as errors.
    """
    expected_set: Set = set(expected_row_ids)
    actual_list = list(actual_row_ids)

    # Duplicate detection
    seen: Set = set()
    duplicates = []
    for rid in actual_list:
        if rid in seen:
            duplicates.append(rid)
        seen.add(rid)

    actual_set: Set = seen

    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)

    errors = []
    if missing:
        errors.append(f"{len(missing)} missing row IDs (first 10: {missing[:10]})")
    if extra:
        errors.append(f"{len(extra)} unexpected extra row IDs (first 10: {extra[:10]})")
    if duplicates and not allow_duplicates:
        errors.append(f"{len(duplicates)} duplicate row IDs (first 10: {duplicates[:10]})")

    valid = len(errors) == 0

    return ValidationResult(
        valid=valid,
        input_rows=len(expected_row_ids),
        output_rows=len(actual_row_ids),
        missing_row_ids=missing,
        duplicate_row_ids=duplicates,
        extra_row_ids=extra,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# FinBERT output validator
# ---------------------------------------------------------------------------


def validate_finbert_output(df: pd.DataFrame) -> ValidationResult:
    """
    Validate FinBERT prediction output columns.

    Checks
    ------
    * FINBERT_POSITIVE, FINBERT_NEGATIVE, FINBERT_NEUTRAL each in [0, 1]
    * Probabilities sum approximately to 1.0 (within 0.01 tolerance)
    * FINBERT_SCORE in [-1, 1]
    * No NaN values
    """
    required = [
        "FINBERT_POSITIVE", "FINBERT_NEGATIVE",
        "FINBERT_NEUTRAL", "FINBERT_SCORE",
    ]
    result = ValidationResult(valid=True, input_rows=len(df), output_rows=len(df))

    for col in required:
        if col not in df.columns:
            result.errors.append(f"Missing required column: {col}")
            result.valid = False

    if not result.valid:
        return result

    invalid_count = 0

    for col in ["FINBERT_POSITIVE", "FINBERT_NEGATIVE", "FINBERT_NEUTRAL"]:
        bad = df[col].isna() | (df[col] < 0) | (df[col] > 1)
        n_bad = bad.sum()
        if n_bad > 0:
            result.errors.append(
                f"{n_bad} rows have {col} outside [0,1]"
            )
            invalid_count += n_bad
            result.valid = False

    # Probability sum check
    prob_sum = df["FINBERT_POSITIVE"] + df["FINBERT_NEGATIVE"] + df["FINBERT_NEUTRAL"]
    bad_sum = (prob_sum - 1.0).abs() > 0.01
    n_bad_sum = bad_sum.sum()
    if n_bad_sum > 0:
        result.errors.append(
            f"{n_bad_sum} rows have probability sum outside [0.99, 1.01]"
        )
        invalid_count += n_bad_sum
        result.valid = False

    # Score bounds
    score_col = df["FINBERT_SCORE"]
    bad_score = score_col.isna() | (score_col < -1) | (score_col > 1)
    n_bad_score = bad_score.sum()
    if n_bad_score > 0:
        result.errors.append(
            f"{n_bad_score} rows have FINBERT_SCORE outside [-1, 1]"
        )
        invalid_count += n_bad_score
        result.valid = False

    result.invalid_rows = int(invalid_count)
    return result


# ---------------------------------------------------------------------------
# Event output validator
# ---------------------------------------------------------------------------

VALID_EVENT_TYPES = frozenset([
    "Credit Event",
    "Geopolitical",
    "Macroeconomic",
    "Merger & Acquisition",
    "Regulatory / Legal",
    "Corporate / Earnings",
    "Product / Technology",
    "Commodity / Supply Chain",
    "Market / Liquidity",
    "Other / Unclear",
    "NO_EVENT",
])


def validate_event_output(df: pd.DataFrame) -> ValidationResult:
    """
    Validate event classifier output columns.

    Checks
    ------
    * EVENT_TYPE is a member of the established taxonomy
    * EVENT_CONFIDENCE in [0, 1]
    * No NaN
    """
    result = ValidationResult(valid=True, input_rows=len(df), output_rows=len(df))
    invalid_count = 0

    if "EVENT_TYPE" in df.columns:
        bad_type = ~df["EVENT_TYPE"].isin(VALID_EVENT_TYPES)
        n_bad = bad_type.sum()
        if n_bad > 0:
            bad_vals = df.loc[bad_type, "EVENT_TYPE"].unique()[:5].tolist()
            result.errors.append(
                f"{n_bad} rows have EVENT_TYPE outside taxonomy (examples: {bad_vals})"
            )
            invalid_count += n_bad
            result.valid = False
    else:
        result.errors.append("Missing required column: EVENT_TYPE")
        result.valid = False

    if "EVENT_CONFIDENCE" in df.columns:
        bad_conf = df["EVENT_CONFIDENCE"].isna() | (
            df["EVENT_CONFIDENCE"] < 0
        ) | (df["EVENT_CONFIDENCE"] > 1)
        n_bad = bad_conf.sum()
        if n_bad > 0:
            result.errors.append(
                f"{n_bad} rows have EVENT_CONFIDENCE outside [0, 1]"
            )
            invalid_count += n_bad
            result.valid = False
    else:
        result.errors.append("Missing required column: EVENT_CONFIDENCE")
        result.valid = False

    result.invalid_rows = int(invalid_count)
    return result


# ---------------------------------------------------------------------------
# Impact score output validator
# ---------------------------------------------------------------------------


def validate_impact_output(df: pd.DataFrame) -> ValidationResult:
    """
    Validate impact scoring output columns.

    Checks
    ------
    * IMPACT_SCORE in [1, 10]
    * No NaN
    * No infinite values
    """
    result = ValidationResult(valid=True, input_rows=len(df), output_rows=len(df))
    invalid_count = 0

    col = "IMPACT_SCORE"
    if col not in df.columns:
        result.errors.append(f"Missing required column: {col}")
        result.valid = False
        return result

    scores = df[col]

    nan_mask = scores.isna()
    inf_mask = scores.apply(lambda x: math.isinf(float(x)) if pd.notna(x) else False)
    range_mask = (scores < 1.0) | (scores > 10.0)

    n_nan = int(nan_mask.sum())
    n_inf = int(inf_mask.sum())
    n_range = int(range_mask.sum())

    if n_nan > 0:
        result.errors.append(f"{n_nan} rows have NaN IMPACT_SCORE")
        invalid_count += n_nan
        result.valid = False

    if n_inf > 0:
        result.errors.append(f"{n_inf} rows have infinite IMPACT_SCORE")
        invalid_count += n_inf
        result.valid = False

    if n_range > 0:
        result.errors.append(f"{n_range} rows have IMPACT_SCORE outside [1, 10]")
        invalid_count += n_range
        result.valid = False

    result.invalid_rows = int(invalid_count)
    return result


# ---------------------------------------------------------------------------
# CSV output accounting validator
# ---------------------------------------------------------------------------


def validate_output_csv(
    output_path: Path,
    expected_row_ids: Optional[List] = None,
    row_id_col: str = "row_id",
) -> ValidationResult:
    """
    Load an output CSV and perform row-identity and completeness checks.

    Parameters
    ----------
    output_path : Path
        Path to the stage output CSV.
    expected_row_ids : list, optional
        Expected row IDs. If None, only basic file checks are done.
    row_id_col : str
        Column name for the stable row identifier.
    """
    if not output_path.exists():
        return ValidationResult(
            valid=False,
            input_rows=len(expected_row_ids) if expected_row_ids else 0,
            output_rows=0,
            errors=[f"Output file not found: {output_path}"],
        )

    try:
        df = pd.read_csv(output_path, low_memory=False)
    except Exception as exc:
        return ValidationResult(
            valid=False,
            input_rows=len(expected_row_ids) if expected_row_ids else 0,
            output_rows=0,
            errors=[f"Failed to read output CSV: {exc}"],
        )

    if expected_row_ids is None:
        return ValidationResult(
            valid=True,
            input_rows=len(df),
            output_rows=len(df),
        )

    if row_id_col not in df.columns:
        return ValidationResult(
            valid=False,
            input_rows=len(expected_row_ids),
            output_rows=len(df),
            errors=[f"Row-identity column '{row_id_col}' not found in output"],
        )

    return validate_row_identity(expected_row_ids, df[row_id_col].tolist())
