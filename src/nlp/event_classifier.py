"""
RiskPulse event classification baseline.

This is a ZERO-SHOT BASELINE, not the final production classifier.

It maps financial text into the controlled event taxonomy required by the
hackathon. The design deliberately keeps the taxonomy and model interface
separate so we can later replace zero-shot inference with a supervised
financial event classifier without changing the Risk Engine API.

Recommended first model:
    MoritzLaurer/deberta-v3-base-zeroshot-v2.0

Why this model:
- strong general-purpose zero-shot classification;
- smaller/practical enough for Colab experimentation;
- Apache-2.0 licensed model on Hugging Face.

Important:
This classifier should NOT be run over 862k rows blindly yet. First benchmark
it on a few thousand examples, inspect errors, then decide whether:
1. zero-shot is good enough for the prototype, or
2. we train a smaller supervised classifier for high-throughput inference.

The final Risk Engine should eventually return:
    event_type
    event_confidence
    candidate_event_scores

This gives the downstream impact engine both a selected event and an
explanation of the alternatives.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


MODEL_NAME = "MoritzLaurer/deberta-v3-base-zeroshot-v2.0"

EVENT_TAXONOMY = {
    "Credit Event": (
        "A credit-related event such as default, missed payment, "
        "bankruptcy, insolvency, debt restructuring, credit downgrade, "
        "liquidity distress, or deterioration in credit quality."
    ),
    "Geopolitical": (
        "A geopolitical event such as war, military conflict, sanctions, "
        "trade restrictions, diplomatic conflict, political instability, "
        "terrorism, or international supply disruption."
    ),
    "Macroeconomic": (
        "A macroeconomic event involving interest rates, inflation, GDP, "
        "employment, central-bank policy, currencies, recession, monetary "
        "policy, fiscal policy, or broad economic conditions."
    ),
    "Merger & Acquisition": (
        "A merger, acquisition, takeover, buyout, divestiture, spin-off, "
        "strategic combination, or major corporate transaction."
    ),
    "Regulatory / Legal": (
        "A regulatory or legal event such as a government investigation, "
        "lawsuit, court decision, regulation, compliance action, fine, "
        "antitrust action, or change in legal requirements."
    ),
    "Corporate / Earnings": (
        "A company-specific corporate event such as earnings, revenue, "
        "profit, loss, guidance, management change, restructuring, layoffs, "
        "dividend, buyback, accounting issue, or operational result."
    ),
    "Product / Technology": (
        "A product or technology event such as a product launch, product "
        "failure, major technology release, patent, cybersecurity incident, "
        "research breakthrough, or technological disruption."
    ),
    "Commodity / Supply Chain": (
        "A commodity or supply-chain event involving oil, gas, metals, "
        "agriculture, raw materials, shortages, logistics, production "
        "disruptions, or major input-cost changes."
    ),
    "Market / Liquidity": (
        "A broad market or liquidity event such as a market crash, sharp "
        "selloff, unusual volatility, liquidity crisis, trading disruption, "
        "or major change in market conditions."
    ),
    "Other / Unclear": (
        "Financial or business-related information that does not clearly "
        "belong to any of the defined event categories."
    ),
}


@dataclass
class EventResult:
    event_type: str
    confidence: float
    candidate_scores: dict[str, float]


class ZeroShotEventClassifier:
    def __init__(
        self,
        model_name: str = MODEL_NAME,
        device: str | None = None,
        max_length: int = 256,
    ):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.max_length = max_length

        print(f"[EventClassifier] model={model_name}")
        print(f"[EventClassifier] device={self.device}")

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.to(self.device)
        self.model.eval()

        # DeBERTa-v3 zero-shot checkpoints normally use NLI labels. We locate
        # entailment dynamically rather than assuming a fixed class index.
        self.id2label = {
            int(k): str(v).lower()
            for k, v in self.model.config.id2label.items()
        }

        self.entailment_id = None
        for idx, label in self.id2label.items():
            if "entail" in label:
                self.entailment_id = idx
                break

        if self.entailment_id is None:
            raise RuntimeError(
                f"Could not identify an entailment class in {self.id2label}"
            )

        self.labels = list(EVENT_TAXONOMY.keys())
        self.descriptions = list(EVENT_TAXONOMY.values())

    @torch.inference_mode()
    def predict(
        self,
        texts: Iterable[str],
        batch_size: int = 8,
    ) -> list[EventResult]:
        """
        Score each text against every event description.

        We use:
            premise = event text
            hypothesis = "This text describes <event description>."

        Scores are normalized across event classes so the output can be
        interpreted as a candidate distribution.
        """
        texts = [
            "" if pd.isna(x) else str(x)
            for x in texts
        ]

        results: list[EventResult] = []

        for text in texts:
            if not text.strip():
                results.append(
                    EventResult(
                        event_type="Other / Unclear",
                        confidence=0.0,
                        candidate_scores={
                            label: 0.0 for label in self.labels
                        },
                    )
                )
                continue

            # Each text is paired with every candidate category. We process
            # the pairs in mini-batches to control GPU memory.
            pairs = [
                (
                    text,
                    f"This text describes {description}"
                )
                for description in self.descriptions
            ]

            entailment_scores = []

            for start in range(0, len(pairs), batch_size):
                batch = pairs[start:start + batch_size]

                encoded = self.tokenizer(
                    [x[0] for x in batch],
                    [x[1] for x in batch],
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                )
                encoded = {
                    key: value.to(self.device)
                    for key, value in encoded.items()
                }

                logits = self.model(**encoded).logits
                scores = logits[:, self.entailment_id]
                entailment_scores.extend(scores.detach().cpu().tolist())

            # Softmax converts arbitrary NLI entailment logits into a
            # normalized candidate distribution across our event taxonomy.
            probabilities = torch.softmax(
                torch.tensor(entailment_scores, dtype=torch.float32),
                dim=0,
            ).tolist()

            candidate_scores = {
                label: float(score)
                for label, score in zip(self.labels, probabilities)
            }

            event_type = max(
                candidate_scores,
                key=candidate_scores.get,
            )
            confidence = candidate_scores[event_type]

            results.append(
                EventResult(
                    event_type=event_type,
                    confidence=confidence,
                    candidate_scores=candidate_scores,
                )
            )

        return results


def classify_dataframe(
    df: pd.DataFrame,
    classifier: ZeroShotEventClassifier,
    text_col: str = "TWEET",
    batch_size: int = 8,
) -> pd.DataFrame:
    """Append event classification fields without modifying the source columns."""
    if text_col not in df.columns:
        raise ValueError(f"Missing required text column: {text_col}")

    results = classifier.predict(
        df[text_col].fillna("").tolist(),
        batch_size=batch_size,
    )

    out = df.copy()
    out["EVENT_TYPE"] = [r.event_type for r in results]
    out["EVENT_CONFIDENCE"] = [r.confidence for r in results]

    # Preserve all candidate probabilities. These become useful later for
    # uncertainty-aware impact scoring and explainability.
    for label in EVENT_TAXONOMY:
        safe_name = (
            label.upper()
            .replace(" & ", "_")
            .replace(" / ", "_")
            .replace(" ", "_")
        )
        out[f"EVENT_PROB_{safe_name}"] = [
            r.candidate_scores[label]
            for r in results
        ]

    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Zero-shot event classification for RiskPulse."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--text-column", default="TWEET")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    output = Path(args.output)
    if output.exists() and not args.overwrite:
        raise FileExistsError(
            f"{output} already exists. Use --overwrite to replace it."
        )

    # This CLI intentionally uses a single DataFrame for the first baseline.
    # Once the taxonomy is validated, we will add chunked inference analogous
    # to finbert_inference.py.
    df = pd.read_csv(args.input, nrows=args.max_rows)
    if "row_id" not in df.columns:
        if "Unnamed: 0" in df.columns:
            df = df.rename(columns={"Unnamed: 0": "row_id"})
        else:
            df.insert(0, "row_id", range(len(df)))

    classifier = ZeroShotEventClassifier(
        device=args.device,
        max_length=args.max_length,
    )

    result = classify_dataframe(
        df,
        classifier,
        text_col=args.text_column,
        batch_size=args.batch_size,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)

    print(f"[done] classified {len(result):,} rows")
    print(f"[done] output: {output}")
    print("\nEvent distribution:")
    print(result["EVENT_TYPE"].value_counts())


if __name__ == "__main__":
    main()
