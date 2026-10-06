#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic Canonical Event Selector
======================================
Selects a deterministic real event from the pipeline output that matches the portfolio.
"""

import pandas as pd
from typing import Dict, Any

def select_real_event(csv_path: str) -> Dict[str, Any]:
    """
    Selects a deterministic real canonical event from the pipeline output
    that matches a known portfolio entity and naturally maps to an ENTITY scope.
    """
    df = pd.read_csv(csv_path)
    
    # Portfolio exposure universe entities
    portfolio_entities = [
        "Apple", "Microsoft", "Tesla", "Samsung", "PetroGlobal", 
        "Rosneft", "SaudiChem", "ShellEnergy", "GlobalBank", 
        "AsiaCredit", "Boeing", "Amazon", "RetailCo", "MedDevice", "CountryX"
    ]
    
    # Event types that map to ENTITY scope in ShockMapper
    entity_scoped_events = [
        "Credit Event",
        "Merger & Acquisition",
        "Regulatory / Legal",
        "Corporate / Earnings",
        "Product / Technology",
        "Other / Unclear"
    ]
    
    # Filter valid and material
    candidates = df[
        (df["entity_status"] == "valid") & 
        (df["materiality"] == "MATERIAL_EVENT") & 
        (df["impact_score"] >= 1.0) &
        (df["event_type"].isin(entity_scoped_events))
    ]
    
    # Match entity aliases
    matched = candidates[candidates["canonical_entity"].isin(portfolio_entities)]
    
    if matched.empty:
        raise ValueError("No real canonical event overlaps with the portfolio exposure universe.")
        
    # Sort deterministically
    top_matches = matched.sort_values(
        ["impact_score", "timestamp", "event_id"], 
        ascending=[False, True, True]
    )
    
    return top_matches.iloc[0].to_dict()
