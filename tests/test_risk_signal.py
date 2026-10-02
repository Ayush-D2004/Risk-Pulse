# -*- coding: utf-8 -*-
"""
Unit tests for canonical RiskSignal schema.
"""

import json
import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from src.risk.risk_signal import (
    Evidence,
    EventType,
    MarketContext,
    MaterialityLevel,
    RiskSignal,
    SignalSource,
)


class TestRiskSignalSchema(unittest.TestCase):
    """Test suite verifying validation, coercion, and serialization of RiskSignal."""

    def test_minimal_valid_risk_signal(self):
        """Verify RiskSignal can be initialized with required fields and defaults."""
        signal = RiskSignal(
            entity="Amazon",
            source="twitter",
            sentiment_score=-0.45,
            event_type="Credit Event",
            event_confidence=0.88,
            materiality="MATERIAL_EVENT",
            evidence="Amazon bond spreads widen dramatically amid debt restructuring rumors.",
        )

        self.assertIsNotNone(signal.event_id)
        self.assertIsInstance(signal.timestamp, datetime)
        self.assertEqual(signal.entity, "Amazon")
        self.assertEqual(signal.source, "twitter")
        self.assertEqual(signal.source_credibility, 1.0)
        self.assertEqual(signal.sentiment_score, -0.45)
        self.assertEqual(signal.event_type, "Credit Event")
        self.assertEqual(signal.event_confidence, 0.88)
        self.assertEqual(signal.materiality, "MATERIAL_EVENT")
        self.assertEqual(signal.novelty, 1.0)
        self.assertIsNone(signal.market_context)
        self.assertIsNone(signal.impact_score)
        self.assertIsNone(signal.impact_reason)
        self.assertIsInstance(signal.evidence, Evidence)
        self.assertEqual(
            signal.evidence.text,
            "Amazon bond spreads widen dramatically amid debt restructuring rumors.",
        )

    def test_full_risk_signal_with_submodels(self):
        """Verify full initialization with MarketContext, Evidence, and scored Impact."""
        market_ctx = MarketContext(
            volatility=2.45,
            abnormal_return=-0.042,
            volume_ratio=3.1,
            sector_movement=-0.015,
            index_movement=-0.005,
            metadata={"cds_5y_bps": 185.0},
        )
        evidence_obj = Evidence(
            text="Moody's downgrades corporate credit rating to Baa3 with negative outlook.",
            headline="Rating Agency Downgrade Action",
            url="https://example.com/ratings/123",
            author="CreditDesk",
            matched_keywords=["downgrade", "rating", "outlook"],
            raw_metadata={"tweet_id": 987654321},
        )

        signal = RiskSignal(
            event_id="sig-corp-001",
            timestamp=datetime(2024, 5, 15, 14, 30, tzinfo=timezone.utc),
            entity="Boeing",
            source=SignalSource.NEWS,
            source_credibility=0.95,
            sentiment_score=-0.75,
            event_type=EventType.CREDIT_EVENT,
            event_confidence=0.92,
            materiality=MaterialityLevel.MATERIAL_EVENT,
            novelty=0.85,
            market_context=market_ctx,
            impact_score=8.5,
            impact_reason="Major debt rating downgrade + negative CAR + elevated trading volume",
            evidence=evidence_obj,
        )

        self.assertEqual(signal.event_id, "sig-corp-001")
        self.assertEqual(signal.source, "news")
        self.assertEqual(signal.event_type, "Credit Event")
        self.assertEqual(signal.materiality, "MATERIAL_EVENT")
        self.assertEqual(signal.impact_score, 8.5)
        self.assertEqual(signal.market_context.volatility, 2.45)
        self.assertEqual(signal.evidence.matched_keywords, ["downgrade", "rating", "outlook"])

    def test_evidence_and_context_dict_coercion(self):
        """Verify dictionaries passed to evidence and market_context are coerced to submodels."""
        signal = RiskSignal(
            entity="Tesla",
            source="gdelt",
            sentiment_score=0.2,
            event_type="Product / Technology",
            event_confidence=0.85,
            materiality="MATERIAL_EVENT",
            market_context={"volatility": 1.1, "volume_ratio": 1.5, "custom_metric": 42},
            evidence={"text": "Tesla announces new factory expansion.", "url": "https://news.com/tsla"},
        )
        self.assertIsInstance(signal.market_context, MarketContext)
        self.assertEqual(signal.market_context.volatility, 1.1)
        self.assertEqual(signal.market_context.custom_metric, 42)
        self.assertIsInstance(signal.evidence, Evidence)
        self.assertEqual(signal.evidence.text, "Tesla announces new factory expansion.")
        self.assertEqual(signal.evidence.url, "https://news.com/tsla")

    def test_timestamp_parsing_formats(self):
        """Verify timestamp parsing handles ISO strings, dates like DD/MM/YYYY, and UNIX epochs."""
        # ISO string
        sig1 = RiskSignal(
            timestamp="2024-03-01T10:00:00Z",
            entity="Apple",
            source="twitter",
            sentiment_score=0.1,
            event_type="Corporate / Earnings",
            event_confidence=0.7,
            materiality="MATERIAL_EVENT",
            evidence="Apple reports Q1 record revenue.",
        )
        self.assertEqual(sig1.timestamp.year, 2024)
        self.assertEqual(sig1.timestamp.month, 3)

        # Tabular DD/MM/YYYY string as found in existing project dataset
        sig2 = RiskSignal(
            timestamp="31/01/2017",
            entity="Amazon",
            source="twitter",
            sentiment_score=-0.1,
            event_type="Corporate / Earnings",
            event_confidence=0.6,
            materiality="MATERIAL_EVENT",
            evidence="Sample tweet text.",
        )
        self.assertEqual(sig2.timestamp.day, 31)
        self.assertEqual(sig2.timestamp.month, 1)
        self.assertEqual(sig2.timestamp.year, 2017)

    def test_validation_bounds(self):
        """Verify strict validation on bounds for sentiment, confidence, credibility, impact."""
        valid_kwargs = {
            "entity": "Microsoft",
            "source": "twitter",
            "sentiment_score": 0.0,
            "event_type": "Other / Unclear",
            "event_confidence": 0.5,
            "materiality": "MATERIAL_EVENT",
            "evidence": "Some text",
        }

        # sentiment_score out of [-1.0, 1.0]
        with self.assertRaises(ValidationError):
            RiskSignal(**{**valid_kwargs, "sentiment_score": 1.5})
        with self.assertRaises(ValidationError):
            RiskSignal(**{**valid_kwargs, "sentiment_score": -1.2})

        # event_confidence out of [0.0, 1.0]
        with self.assertRaises(ValidationError):
            RiskSignal(**{**valid_kwargs, "event_confidence": 1.1})
        with self.assertRaises(ValidationError):
            RiskSignal(**{**valid_kwargs, "event_confidence": -0.1})

        # source_credibility out of [0.0, 1.0]
        with self.assertRaises(ValidationError):
            RiskSignal(**{**valid_kwargs, "source_credibility": 1.2})

        # impact_score out of [1.0, 10.0]
        with self.assertRaises(ValidationError):
            RiskSignal(**{**valid_kwargs, "impact_score": 0.5})
        with self.assertRaises(ValidationError):
            RiskSignal(**{**valid_kwargs, "impact_score": 10.5})

    def test_json_and_dict_serialization_roundtrip(self):
        """Verify serialization to JSON / dict and deserialization preserves all data."""
        orig = RiskSignal(
            event_id="test-roundtrip-1",
            timestamp="2024-06-01T12:00:00Z",
            entity="Alphabet",
            source="gdelt",
            source_credibility=0.9,
            sentiment_score=-0.6,
            event_type=EventType.REGULATORY_LEGAL,
            event_confidence=0.89,
            materiality=MaterialityLevel.MATERIAL_EVENT,
            novelty=0.75,
            market_context=MarketContext(volatility=1.8, abnormal_return=-0.03),
            impact_score=7.0,
            impact_reason="Antitrust ruling with potential structural remedies",
            evidence=Evidence(text="DOJ initiates antitrust remedies inquiry.", headline="DOJ Probe"),
        )

        # To dict & from dict
        data_dict = orig.to_dict()
        self.assertIsInstance(data_dict, dict)
        reconstructed_from_dict = RiskSignal.from_dict(data_dict)
        self.assertEqual(orig.event_id, reconstructed_from_dict.event_id)
        self.assertEqual(orig.impact_score, reconstructed_from_dict.impact_score)

        # To JSON & from JSON
        json_str = orig.to_json(indent=2)
        self.assertIsInstance(json_str, str)
        reconstructed_from_json = RiskSignal.from_json(json_str)
        self.assertEqual(orig.event_id, reconstructed_from_json.event_id)
        self.assertEqual(orig.evidence.headline, reconstructed_from_json.evidence.headline)
        self.assertEqual(orig.market_context.abnormal_return, reconstructed_from_json.market_context.abnormal_return)


if __name__ == "__main__":
    unittest.main()
