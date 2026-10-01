"""
Financial sentiment inference using ProsusAI/FinBERT.

The model is downloaded by Hugging Face Transformers on first use.
For reproducible deployments, pin/cache the model in the final release.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification


MODEL_NAME = "ProsusAI/finbert"


@dataclass
class SentimentResult:
    positive: float
    negative: float
    neutral: float
    score: float
    label: str


class FinBERTSentiment:
    def __init__(self, model_name: str = MODEL_NAME, device: str | None = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.to(self.device)
        self.model.eval()

        self.id2label = {
            int(k): str(v).lower()
            for k, v in self.model.config.id2label.items()
        }

    @torch.inference_mode()
    def predict(self, texts: Iterable[str], batch_size: int = 16) -> List[SentimentResult]:
        texts = [str(x) if x is not None else "" for x in texts]
        output = []

        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            inputs = self.tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            logits = self.model(**inputs).logits
            probs = torch.softmax(logits, dim=-1).cpu().numpy()

            for p in probs:
                values = {}
                for idx, prob in enumerate(p):
                    label = self.id2label.get(idx, str(idx))
                    values[label] = float(prob)

                positive = values.get("positive", 0.0)
                negative = values.get("negative", 0.0)
                neutral = values.get("neutral", 0.0)
                score = positive - negative

                label = max(
                    {"positive": positive, "negative": negative, "neutral": neutral},
                    key=lambda x: {"positive": positive, "negative": negative, "neutral": neutral}[x]
                )
                output.append(SentimentResult(
                    positive=positive,
                    negative=negative,
                    neutral=neutral,
                    score=score,
                    label=label,
                ))

        return output
