#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Portfolio Stress Engine
=======================
Deterministic stress calculator for the wholesale banking portfolio.

Consumes:
- Portfolio (and ExposureModel)
- ShockScenario (from ShockMapper)

Produces:
- StressedPortfolio (containing StressedExposures)

Responsibilities:
- Matches exposures by scope (ENTITY, SECTOR, GEOGRAPHY, BROAD_MARKET, SYSTEMIC)
- Applies asset-specific shocks (PD, LGD, Bond/Equity price)
- Computes base and stressed Expected Loss (EL)
- Computes base and stressed Market Value (MTM)
- Performs portfolio-level aggregation

All calculations are deterministic and the engine is strictly read-only on inputs.
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Set

from src.portfolio.models import Exposure, Portfolio
from src.portfolio.exposure_model import ExposureModel
from src.portfolio.shock_models import ShockScenario, ShockScope
from src.portfolio.stress_models import StressedExposure, StressedPortfolio


class StressEngine:
    """
    Deterministic Portfolio Stress Engine.
    """

    def __init__(self, portfolio: Portfolio) -> None:
        """
        Initialize with a frozen Portfolio.
        Uses ExposureModel for deterministic entity matching.
        """
        self._portfolio = portfolio
        self._exposure_model = ExposureModel(portfolio)

    def _get_affected_exposure_ids(self, scenario: ShockScenario) -> Set[str]:
        """
        Determine which exposure IDs are in-scope for the given scenario.
        """
        scope = ShockScope(scenario.shock_scope)
        affected_ids = set()

        if scope == ShockScope.NONE:
            return affected_ids

        if scope == ShockScope.ENTITY:
            # Use deterministic entity matching
            match_result = self._exposure_model.match_entity(scenario.affected_entity)
            if match_result.matched:
                for exp in match_result.exposures:
                    affected_ids.add(exp.exposure_id)

        elif scope == ShockScope.SECTOR:
            # We need affected_sector from the scenario. If missing, assume no match.
            if scenario.affected_sector:
                for exp in self._exposure_model.by_sector(scenario.affected_sector):
                    affected_ids.add(exp.exposure_id)

        elif scope == ShockScope.GEOGRAPHY:
            if scenario.affected_geography:
                for exp in self._exposure_model.by_geography(scenario.affected_geography):
                    affected_ids.add(exp.exposure_id)

        elif scope in (ShockScope.BROAD_MARKET, ShockScope.SYSTEMIC):
            # Affects all exposures that match the scenario's applicable asset classes
            for exp in self._portfolio.exposures:
                if exp.asset_type in scenario.applicable_assets:
                    affected_ids.add(exp.exposure_id)

        return affected_ids

    def _process_exposure(
        self,
        exp: Exposure,
        scenario: ShockScenario,
        is_affected: bool,
    ) -> StressedExposure:
        """
        Apply deterministic stress math to a single exposure.
        """
        # --- Base Metrics ---
        base_pd = exp.probability_of_default
        base_lgd = exp.loss_given_default
        ead = exp.ead
        base_el = ead * base_pd * base_lgd

        # We treat EAD as the base market value for MTM shocks
        base_mv = ead

        # Initialize stressed metrics to base (unaffected state)
        stressed_pd = base_pd
        stressed_lgd = base_lgd
        stressed_mv = base_mv

        # --- Apply Shocks (if affected and applicable) ---
        if is_affected and exp.asset_type in scenario.applicable_assets:
            # PD and LGD bounds at 1.0 (100%)
            if "pd_delta" in self._get_asset_capabilities(exp.asset_type):
                stressed_pd = min(Decimal("1.0"), base_pd + Decimal(str(scenario.pd_delta)))
            
            if "lgd_delta" in self._get_asset_capabilities(exp.asset_type):
                stressed_lgd = min(Decimal("1.0"), base_lgd + Decimal(str(scenario.lgd_delta)))

            if "bond_price_shock" in self._get_asset_capabilities(exp.asset_type):
                stressed_mv = base_mv * (Decimal("1.0") + Decimal(str(scenario.bond_price_shock)))

            if "equity_price_shock" in self._get_asset_capabilities(exp.asset_type):
                stressed_mv = base_mv * (Decimal("1.0") + Decimal(str(scenario.equity_price_shock)))

        # --- Compute Final Metrics ---
        stressed_el = ead * stressed_pd * stressed_lgd
        incremental_el = stressed_el - base_el
        mtm_impact = stressed_mv - base_mv

        return StressedExposure(
            exposure_id=exp.exposure_id,
            obligor=exp.obligor,
            asset_type=exp.asset_type,
            sector=exp.sector,
            geography=exp.geography,
            ead=ead,
            is_affected=is_affected,
            base_pd=base_pd,
            stressed_pd=stressed_pd,
            base_lgd=base_lgd,
            stressed_lgd=stressed_lgd,
            base_expected_loss=base_el,
            stressed_expected_loss=stressed_el,
            incremental_expected_loss=incremental_el,
            base_market_value=base_mv,
            stressed_market_value=stressed_mv,
            mtm_impact=mtm_impact,
            event_id=scenario.event_id,
            scenario_id=scenario.rule_id,
        )

    def _get_asset_capabilities(self, asset_type: str) -> Set[str]:
        """Return which shock fields apply to which asset classes."""
        # Using the logic from ASSET_SHOCK_APPLICABILITY in shock_models
        # Hardcoding the map here ensures engine knows *how* to apply it.
        mapping = {
            "Corporate Loan":              {"pd_delta", "lgd_delta"},
            "Revolving Credit Facility":   {"pd_delta", "lgd_delta"},
            "Corporate Bond":              {"pd_delta", "lgd_delta", "bond_price_shock"},
            "Equity":                      {"equity_price_shock"},
        }
        return mapping.get(asset_type, set())

    def run_stress(self, scenario: ShockScenario) -> StressedPortfolio:
        """
        Execute the deterministic stress scenario across the portfolio.
        
        Args:
            scenario: The input ShockScenario.
            
        Returns:
            StressedPortfolio with full aggregate and exposure-level details.
        """
        affected_ids = self._get_affected_exposure_ids(scenario)

        stressed_exposures: List[StressedExposure] = []
        
        # Totals accumulators
        affected_count = 0
        affected_ead = Decimal("0")
        
        sum_base_el = Decimal("0")
        sum_stressed_el = Decimal("0")
        sum_incremental_el = Decimal("0")
        
        sum_base_mv = Decimal("0")
        sum_stressed_mv = Decimal("0")
        sum_mtm_impact = Decimal("0")

        for exp in self._portfolio.exposures:
            is_affected = exp.exposure_id in affected_ids
            
            # Compute exposure-level stress
            res = self._process_exposure(exp, scenario, is_affected)
            stressed_exposures.append(res)
            
            # Aggregate metrics
            if is_affected:
                affected_count += 1
                affected_ead += exp.ead
                
            sum_base_el += res.base_expected_loss
            sum_stressed_el += res.stressed_expected_loss
            sum_incremental_el += res.incremental_expected_loss
            
            sum_base_mv += res.base_market_value
            sum_stressed_mv += res.stressed_market_value
            sum_mtm_impact += res.mtm_impact

        # Calculate percentages safely
        total_ead = self._portfolio.total_ead
        affected_pct = float(affected_ead / total_ead) if total_ead > Decimal("0") else 0.0

        return StressedPortfolio(
            portfolio_id=self._portfolio.portfolio_id,
            total_exposures=self._portfolio.exposure_count,
            affected_exposure_count=affected_count,
            total_ead=total_ead,
            affected_ead=affected_ead,
            affected_ead_pct=affected_pct,
            base_expected_loss=sum_base_el,
            stressed_expected_loss=sum_stressed_el,
            incremental_expected_loss=sum_incremental_el,
            total_base_market_value=sum_base_mv,
            total_stressed_market_value=sum_stressed_mv,
            total_mtm_impact=sum_mtm_impact,
            stressed_exposures=stressed_exposures,
            event_id=scenario.event_id,
            scenario_id=scenario.rule_id,
        )
