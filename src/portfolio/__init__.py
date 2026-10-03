# -*- coding: utf-8 -*-
"""
Module B — Portfolio Stress Testing
====================================
Synthetic wholesale banking portfolio and exposure model.

This module provides:
- Canonical data models for credit exposures and portfolio holdings
- Deterministic synthetic portfolio generation
- Entity → exposure matching for RiskSignal integration
- Aggregation utilities (sector, geography, asset type)

Design:
    Does NOT modify any frozen Risk Engine code.
    Stress formulas are NOT implemented here — only the exposure structure.
"""

from src.portfolio.models import (
    AssetType,
    CreditRating,
    Exposure,
    ExposureMatch,
    Portfolio,
    PortfolioSummary,
)
from src.portfolio.synthetic_portfolio import generate_synthetic_portfolio
from src.portfolio.exposure_model import ExposureModel
from src.portfolio.shock_models import (
    ApplicableAsset,
    ShockScenario,
    ShockScope,
)
from src.portfolio.shock_mapper import ShockMapper
from src.portfolio.stress_models import StressedExposure, StressedPortfolio
from src.portfolio.stress_engine import StressEngine
from src.portfolio.orchestration_models import AggregationMetrics, StressScenarioResult
from src.portfolio.orchestration import StressScenarioEngine
from src.portfolio.comparison_models import AttributionMetrics, RiskAttribution, ScenarioComparisonDelta, ScenarioComparisonPair, BatchComparisonMatrix
from src.portfolio.scenario_comparison import ScenarioComparisonEngine

__all__ = [
    "AssetType",
    "CreditRating",
    "Exposure",
    "ExposureMatch",
    "Portfolio",
    "PortfolioSummary",
    "generate_synthetic_portfolio",
    "ExposureModel",
    "ApplicableAsset",
    "ShockScenario",
    "ShockScope",
    "ShockMapper",
    "StressedExposure",
    "StressedPortfolio",
    "StressEngine",
    "AggregationMetrics",
    "StressScenarioResult",
    "StressScenarioEngine",
    "AttributionMetrics",
    "RiskAttribution",
    "ScenarioComparisonDelta",
    "ScenarioComparisonPair",
    "BatchComparisonMatrix",
    "ScenarioComparisonEngine",
]
