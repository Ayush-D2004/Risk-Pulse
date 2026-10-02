#!/usr/bin/env python3
"""
Audit zero-shot event-classification predictions.

Expected inputs:
  1) Original tweet dataset CSV
  2) Event-classifier output CSV

The script joins predictions to the original rows using row_id when available,
then prints:
  - event distribution
  - confidence statistics by event type
  - low-confidence counts
  - representative examples per event type
  - focused Credit Event examples

It is intended for model validation, not model training.
"""

import argparse
from pathlib import Path
import sys
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def read_csv(path, usecols=None):
    return pd.read_csv(
        path,
        usecols=usecols,
        low_memory=False,
        on_bad_lines="skip",
    )


def resolve_text_column(df):
    for col in ["TWEET", "text", "TEXT", "tweet"]:
        if col in df.columns:
            return col
    raise ValueError("Could not find tweet text column in original dataset.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--original", required=True,
                        help="Original dataset CSV containing tweet text.")
    parser.add_argument("--predictions", required=True,
                        help="Event classifier output CSV.")
    parser.add_argument("--examples-per-class", type=int, default=10)
    parser.add_argument("--credit-examples", type=int, default=40)
    parser.add_argument("--low-confidence", type=float, default=0.60)
    args = parser.parse_args()

    pred = read_csv(args.predictions)

    if "row_id" not in pred.columns:
        if "Unnamed: 0" in pred.columns:
            pred = pred.rename(columns={"Unnamed: 0": "row_id"})
        else:
            pred.insert(0, "row_id", range(len(pred)))

    required_pred = {"row_id", "EVENT_TYPE", "EVENT_CONFIDENCE"}
    missing = required_pred - set(pred.columns)
    if missing:
        raise ValueError(f"Prediction file missing columns: {sorted(missing)}")

    pred["row_id"] = pd.to_numeric(pred["row_id"], errors="coerce")
    pred = pred.dropna(subset=["row_id"]).copy()
    pred["row_id"] = pred["row_id"].astype(int)
    pred["EVENT_CONFIDENCE"] = pd.to_numeric(
        pred["EVENT_CONFIDENCE"], errors="coerce"
    )

    # Read only columns needed for audit from the original dataset.
    header = pd.read_csv(args.original, nrows=0)
    text_col = resolve_text_column(header)

    wanted = [text_col]
    if "row_id" in header.columns:
        wanted.append("row_id")
    elif "Unnamed: 0" in header.columns:
        wanted.append("Unnamed: 0")

    for col in ["STOCK", "MENTION", "DATE", "FINBERT_SCORE"]:
        if col in header.columns and col not in wanted:
            wanted.append(col)

    original = read_csv(args.original, usecols=wanted)

    # If the original file does not explicitly contain row_id, check Unnamed: 0
    # or create the zero-based row index used by the inference pipeline.
    if "row_id" not in original.columns:
        if "Unnamed: 0" in original.columns:
            original = original.rename(columns={"Unnamed: 0": "row_id"})
        else:
            original.insert(0, "row_id", range(len(original)))

    original["row_id"] = pd.to_numeric(original["row_id"], errors="coerce")
    original = original.dropna(subset=["row_id"]).copy()
    original["row_id"] = original["row_id"].astype(int)

    df = pred.merge(original, on="row_id", how="left", suffixes=("", "_original"))

    print("\n" + "=" * 80)
    print("EVENT CLASSIFIER AUDIT")
    print("=" * 80)

    print(f"\nPrediction rows: {len(pred):,}")
    print(f"Rows successfully joined to original data: "
          f"{df[text_col].notna().sum():,}")

    print("\n--- Event distribution ---")
    counts = df["EVENT_TYPE"].value_counts(dropna=False)
    for event, count in counts.items():
        pct = count / len(df) * 100
        print(f"{str(event):30s} {count:7,d}  ({pct:5.1f}%)")

    print("\n--- Confidence statistics by event ---")
    stats = (
        df.groupby("EVENT_TYPE")["EVENT_CONFIDENCE"]
        .agg(["count", "mean", "median", "min", "max"])
        .sort_values("count", ascending=False)
    )
    print(stats.to_string(float_format=lambda x: f"{x:.3f}"))

    print(f"\n--- Low-confidence predictions (< {args.low_confidence:.2f}) ---")
    low = df[df["EVENT_CONFIDENCE"] < args.low_confidence]
    print(f"Count: {len(low):,} ({len(low) / len(df) * 100:.1f}%)")

    if len(low):
        print(
            low[["EVENT_TYPE", "EVENT_CONFIDENCE", text_col]]
            .sort_values("EVENT_CONFIDENCE")
            .head(25)
            .to_string(index=False)
        )

    print("\n--- Representative examples by event type ---")
    # Deterministic sampling makes audits reproducible.
    for event in counts.index:
        subset = df[df["EVENT_TYPE"] == event].copy()
        subset = subset.sort_values(
            ["EVENT_CONFIDENCE", "row_id"],
            ascending=[False, True],
        ).head(args.examples_per_class)

        print("\n" + "-" * 80)
        print(f"{event} | n={len(df[df['EVENT_TYPE'] == event]):,}")

        for _, row in subset.iterrows():
            stock = row.get("STOCK", "")
            date = row.get("DATE", "")
            conf = row.get("EVENT_CONFIDENCE", "")
            score = row.get("FINBERT_SCORE", "")

            print(
                f"\nrow_id={int(row['row_id']) if pd.notna(row['row_id']) else row['row_id']} "
                f"| confidence={conf:.3f} "
                f"| FinBERT={score if pd.notna(score) else 'N/A'} "
                f"| stock={stock if pd.notna(stock) else 'N/A'} "
                f"| date={date if pd.notna(date) else 'N/A'}"
            )
            print(str(row[text_col]).replace("\n", " ")[:700])

    print("\n" + "=" * 80)
    print("CREDIT EVENT FOCUSED AUDIT")
    print("=" * 80)

    credit = df[df["EVENT_TYPE"] == "Credit Event"].copy()

    if credit.empty:
        print("No Credit Event predictions found.")
    else:
        # Show a mixture of highest-confidence and lower-confidence cases.
        n = min(args.credit_examples, len(credit))
        high_n = max(1, n // 2)
        low_n = n - high_n

        high = credit.sort_values(
            ["EVENT_CONFIDENCE", "row_id"], ascending=[False, True]
        ).head(high_n)

        low = credit.sort_values(
            ["EVENT_CONFIDENCE", "row_id"], ascending=[True, True]
        ).head(low_n)

        selected = pd.concat([high, low]).drop_duplicates("row_id")

        for _, row in selected.iterrows():
            print(
                f"\nrow_id={int(row['row_id']) if pd.notna(row['row_id']) else row['row_id']} "
                f"| confidence={row['EVENT_CONFIDENCE']:.3f}"
            )
            print(str(row[text_col]).replace("\n", " ")[:900])

    print("\nAudit complete.")


if __name__ == "__main__":
    main()
