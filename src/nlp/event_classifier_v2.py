#!/usr/bin/env python3
"""
Two-stage financial relevance + event classifier.

Stage 1:
  Zero-shot classify text as either:
    - Financially Relevant
    - No Material Financial Event

Stage 2:
  For financially relevant text only, classify into the event taxonomy.

This is a validation/baseline component. It does not claim calibrated
probabilities or replace a supervised event classifier.

Example:
python relevance_event_classifier_v2.py \
  --input data/processed/reduced_dataset-release.csv \
  --output data/processed/event_predictions_v2.csv \
  --max-rows 5000 \
  --batch-size 32
"""

import argparse
from pathlib import Path

import pandas as pd
import torch
from transformers import pipeline


EVENT_LABELS = [
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
]

EVENT_DESCRIPTIONS = [
    "A material credit event involving default, bankruptcy, insolvency, debt restructuring, credit downgrade, missed payment, or a debt covenant problem.",
    "A material geopolitical event involving international conflict, war, sanctions, diplomatic relations, political instability, or government actions affecting countries or regions.",
    "A material macroeconomic event involving inflation, interest rates, central banks, GDP, employment, currencies, fiscal policy, or broad economic conditions.",
    "A merger, acquisition, takeover, divestiture, or significant purchase or sale of a company or ownership stake.",
    "A material regulatory or legal event involving lawsuits, investigations, fines, enforcement, regulation, government approval, bans, or legal disputes affecting a company or market.",
    "A corporate or earnings event involving revenue, profit, earnings, quarterly results, financial guidance, margins, forecasts, or material company financial performance.",
    "A product or technology event involving a significant product launch, technology release, technological failure, cybersecurity incident, or major technology development.",
    "A commodity or supply-chain event involving oil, gas, metals, agricultural commodities, production disruptions, logistics, shortages, or material supply constraints.",
    "A market or liquidity event involving major market movements, volatility, trading liquidity, equity selloffs, rallies, or broad financial-market conditions.",
    "Other or unclear financially relevant event that does not fit the preceding categories.",
]

RELEVANCE_LABELS = [
    "Financially Relevant",
    "No Material Financial Event",
]

RELEVANCE_DESCRIPTIONS = [
    "The text contains a concrete, potentially material financial, economic, corporate, market, regulatory, geopolitical, commodity, credit, product, or technology event that could affect a company, asset, sector, market, or portfolio.",
    "The text is primarily casual conversation, personal opinion, entertainment, advertising, shopping, customer service, fandom, generic social media chatter, or other content without a concrete material financial or economic event.",
]


def get_text_column(columns):
    for col in ("TWEET", "text", "TEXT", "tweet"):
        if col in columns:
            return col
    raise ValueError("Could not find tweet text column.")


def load_input(path, max_rows=None):
    # The historical dataset has malformed/embedded CSV records in places.
    # Use the same permissive parsing strategy for this baseline and preserve
    # the actual dataframe row index as row_id.
    df = pd.read_csv(
        path,
        low_memory=False,
        nrows=max_rows,
        on_bad_lines="skip",
    )

    text_col = get_text_column(df.columns)
    df = df.reset_index(drop=True)
    if "row_id" not in df.columns:
        if "Unnamed: 0" in df.columns:
            df = df.rename(columns={"Unnamed: 0": "row_id"})
        else:
            df.insert(0, "row_id", range(len(df)))

    return df, text_col


def build_classifier(model_name, device, use_fp16=True):
    torch_dtype = (
        torch.float16
        if (torch.cuda.is_available() and device != -1 and use_fp16)
        else torch.float32
    )
    print(f"[pipeline] device={device}, torch_dtype={torch_dtype}")
    return pipeline(
        "zero-shot-classification",
        model=model_name,
        device=device,
        torch_dtype=torch_dtype,
    )


def classify_batch(
    classifier,
    texts,
    candidate_labels,
    hypothesis_template,
    batch_size=32,
):
    if not texts:
        return []
    return classifier(
        texts,
        candidate_labels=candidate_labels,
        hypothesis_template=hypothesis_template,
        multi_label=False,
        batch_size=batch_size,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--model",
        default="MoritzLaurer/deberta-v3-base-zeroshot-v2.0",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Inference batch size passed to the GPU pipeline.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Number of rows per processing chunk.",
    )
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument(
        "--device",
        type=int,
        default=0 if torch.cuda.is_available() else -1,
    )
    parser.add_argument(
        "--no-fp16",
        action="store_true",
        help="Disable float16 mixed precision on GPU.",
    )
    args = parser.parse_args()

    print(f"Loading input: {args.input}")
    df, text_col = load_input(args.input, args.max_rows)
    print(f"Rows loaded: {len(df):,}")
    print(f"Text column: {text_col}")

    classifier = build_classifier(
        args.model,
        args.device,
        use_fp16=not args.no_fp16,
    )

    texts = (
        df[text_col]
        .fillna("")
        .astype(str)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .tolist()
    )

    relevance_labels = []
    relevance_scores = []
    event_labels = []
    event_scores = []

    chunk_size = args.chunk_size

    for start in range(0, len(texts), chunk_size):
        chunk = texts[start:start + chunk_size]

        relevance_results = classify_batch(
            classifier,
            chunk,
            RELEVANCE_DESCRIPTIONS,
            "This text is about {}.",
            batch_size=args.batch_size,
        )

        batch_relevance = []
        batch_relevance_score = []
        relevant_indices = []

        for i, result in enumerate(relevance_results):
            top_label = result["labels"][0]
            score = float(result["scores"][0])

            batch_relevance.append(
                "FINANCIAL_EVENT"
                if top_label == RELEVANCE_DESCRIPTIONS[0]
                else "NO_MATERIAL_EVENT"
            )
            batch_relevance_score.append(score)

            if top_label == RELEVANCE_DESCRIPTIONS[0]:
                relevant_indices.append(i)

        batch_events = ["NO_EVENT"] * len(chunk)
        batch_event_scores = [0.0] * len(chunk)

        if relevant_indices:
            relevant_texts = [chunk[i] for i in relevant_indices]

            event_results = classify_batch(
                classifier,
                relevant_texts,
                EVENT_DESCRIPTIONS,
                "This text describes {}.",
                batch_size=args.batch_size,
            )

            for local_i, result in enumerate(event_results):
                original_i = relevant_indices[local_i]
                top_description = result["labels"][0]
                score = float(result["scores"][0])

                label_index = EVENT_DESCRIPTIONS.index(top_description)
                batch_events[original_i] = EVENT_LABELS[label_index]
                batch_event_scores[original_i] = score

        relevance_labels.extend(batch_relevance)
        relevance_scores.extend(batch_relevance_score)
        event_labels.extend(batch_events)
        event_scores.extend(batch_event_scores)

        print(
            f"Processed {min(start + chunk_size, len(texts)):,}/"
            f"{len(texts):,}"
        )

    out = df.copy()

    out["FINANCIAL_RELEVANCE"] = relevance_labels
    out["RELEVANCE_CONFIDENCE"] = relevance_scores
    out["EVENT_TYPE"] = event_labels
    out["EVENT_CONFIDENCE"] = event_scores

    # Keep the existing stock/date fields when present. The classifier itself
    # does not use future return columns or existing sentiment labels.
    output_columns = [
        "row_id",
        text_col,
    ]

    for col in ["STOCK", "MENTION", "DATE"]:
        if col in out.columns:
            output_columns.append(col)

    output_columns += [
        "FINANCIAL_RELEVANCE",
        "RELEVANCE_CONFIDENCE",
        "EVENT_TYPE",
        "EVENT_CONFIDENCE",
    ]

    output_columns += [
        col for col in out.columns
        if col.startswith("FINBERT_")
    ]

    output_columns = list(dict.fromkeys(
        col for col in output_columns if col in out.columns
    ))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    out[output_columns].to_csv(output_path, index=False)

    print("\n" + "=" * 70)
    print("RELEVANCE DISTRIBUTION")
    print("=" * 70)
    print(out["FINANCIAL_RELEVANCE"].value_counts().to_string())

    print("\n" + "=" * 70)
    print("EVENT DISTRIBUTION — FINANCIALLY RELEVANT ONLY")
    print("=" * 70)

    relevant = out[out["FINANCIAL_RELEVANCE"] == "FINANCIAL_EVENT"]
    if len(relevant):
        print(relevant["EVENT_TYPE"].value_counts().to_string())
    else:
        print("No financially relevant rows detected.")

    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
