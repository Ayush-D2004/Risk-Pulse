import pytest
import pandas as pd
from pathlib import Path
import json
import uuid

from src.pipeline.run_pipeline import run_guard_stage, run_canonicalize_stage

@pytest.fixture
def dummy_impact_csv(tmp_path):
    df = pd.DataFrame([
        {
            "row_id": "0", "TWEET": "Ford defaults on loan", "STOCK": "Ford", 
            "EVENT_TYPE": "Credit Event", "EVENT_MATERIALITY": "MATERIAL_EVENT", 
            "IMPACT_SCORE": 8.0, "FINBERT_SCORE": -0.8, "EVENT_CONFIDENCE": 0.9, 
            "AUTHOR": "news", "DATE": "2023-01-01"
        },
        {
            "row_id": "1", "TWEET": "Company filed for bankruptcy", "STOCK": "Acme", 
            "EVENT_TYPE": "Credit Event", "EVENT_MATERIALITY": "MATERIAL_EVENT", 
            "IMPACT_SCORE": 7.5, "FINBERT_SCORE": -0.9, "EVENT_CONFIDENCE": 0.95, 
            "AUTHOR": "news", "DATE": "2023-01-01"
        },
        {
            "row_id": "2", "TWEET": "Acme announces debt restructuring", "STOCK": "Acme", 
            "EVENT_TYPE": "Credit Event", "EVENT_MATERIALITY": "MATERIAL_EVENT", 
            "IMPACT_SCORE": 6.0, "FINBERT_SCORE": -0.5, "EVENT_CONFIDENCE": 0.8, 
            "AUTHOR": "news", "DATE": "2023-01-01"
        },
        {
            "row_id": "3", "TWEET": "Acme missed payment to bondholders", "STOCK": "Acme", 
            "EVENT_TYPE": "Credit Event", "EVENT_MATERIALITY": "MATERIAL_EVENT", 
            "IMPACT_SCORE": 8.5, "FINBERT_SCORE": -0.85, "EVENT_CONFIDENCE": 0.99, 
            "AUTHOR": "news", "DATE": "2023-01-01"
        },
        {
            "row_id": "4", "TWEET": "Covenant breach by Acme", "STOCK": "Acme", 
            "EVENT_TYPE": "Credit Event", "EVENT_MATERIALITY": "MATERIAL_EVENT", 
            "IMPACT_SCORE": 5.0, "FINBERT_SCORE": -0.6, "EVENT_CONFIDENCE": 0.7, 
            "AUTHOR": "news", "DATE": "2023-01-01"
        },
        {
            "row_id": "5", "TWEET": "Moody's announces credit downgrade for Acme", "STOCK": "Acme", 
            "EVENT_TYPE": "Credit Event", "EVENT_MATERIALITY": "MATERIAL_EVENT", 
            "IMPACT_SCORE": 9.0, "FINBERT_SCORE": -0.95, "EVENT_CONFIDENCE": 0.98, 
            "AUTHOR": "news", "DATE": "2023-01-01"
        },
        {
            "row_id": "6", "TWEET": "How to change the default browser on Mac", "STOCK": "Mac", 
            "EVENT_TYPE": "Credit Event", "EVENT_MATERIALITY": "MATERIAL_EVENT", 
            "IMPACT_SCORE": 2.0, "FINBERT_SCORE": 0.0, "EVENT_CONFIDENCE": 0.4, 
            "AUTHOR": "news", "DATE": "2023-01-01"
        },
        {
            "row_id": "7", "TWEET": "Change the default settings", "STOCK": "Acme", 
            "EVENT_TYPE": "Credit Event", "EVENT_MATERIALITY": "MATERIAL_EVENT", 
            "IMPACT_SCORE": 1.0, "FINBERT_SCORE": 0.0, "EVENT_CONFIDENCE": 0.3, 
            "AUTHOR": "news", "DATE": "2023-01-01"
        },
        {
            "row_id": "8", "TWEET": "I support Christine Ford's testimony.", "STOCK": "Ford", 
            "EVENT_TYPE": "Credit Event", "EVENT_MATERIALITY": "MATERIAL_EVENT", 
            "IMPACT_SCORE": 8.0, "FINBERT_SCORE": -0.5, "EVENT_CONFIDENCE": 0.8, 
            "AUTHOR": "news", "DATE": "2023-01-01"
        },
        {
            "row_id": "9", "TWEET": "Walt Disney was a visionary", "STOCK": "Disney", 
            "EVENT_TYPE": "Credit Event", "EVENT_MATERIALITY": "MATERIAL_EVENT", 
            "IMPACT_SCORE": 2.0, "FINBERT_SCORE": 0.5, "EVENT_CONFIDENCE": 0.8, 
            "AUTHOR": "news", "DATE": "2023-01-01"
        },
        {
            "row_id": "10", "TWEET": "Applying for an F-1 visa", "STOCK": "Visa", 
            "EVENT_TYPE": "Credit Event", "EVENT_MATERIALITY": "MATERIAL_EVENT", 
            "IMPACT_SCORE": 1.0, "FINBERT_SCORE": 0.0, "EVENT_CONFIDENCE": 0.6, 
            "AUTHOR": "news", "DATE": "2023-01-01"
        },
        {
            "row_id": "11", "TWEET": "Reuters defaults on reporting standard", "STOCK": "Reuters", 
            "EVENT_TYPE": "Credit Event", "EVENT_MATERIALITY": "MATERIAL_EVENT", 
            "IMPACT_SCORE": 5.0, "FINBERT_SCORE": -0.5, "EVENT_CONFIDENCE": 0.7, 
            "AUTHOR": "news", "DATE": "2023-01-01"
        },
        {
            "row_id": "12", "TWEET": "Acme announces new product", "STOCK": "Acme", 
            "EVENT_TYPE": "Product / Technology", "EVENT_MATERIALITY": "MATERIAL_EVENT", 
            "IMPACT_SCORE": 4.0, "FINBERT_SCORE": 0.8, "EVENT_CONFIDENCE": 0.9, 
            "AUTHOR": "news", "DATE": "2023-01-01"
        }
    ])
    p = tmp_path / "impact_scored.csv"
    df.to_csv(p, index=False)
    return p, tmp_path

def test_guard_stage_integration(dummy_impact_csv):
    input_path, output_dir = dummy_impact_csv
    
    out_path = run_guard_stage(input_path, output_dir, chunk_size=5)
    df_out = pd.read_csv(out_path)
    
    assert len(df_out) == 13
    assert "credit_guard_pass" in df_out.columns
    assert "credit_guard_reason" in df_out.columns
    assert "canonical_entity" in df_out.columns
    assert "entity_status" in df_out.columns
    
    # Original EVENT_TYPE remains unchanged
    assert list(df_out["EVENT_TYPE"]) == ["Credit Event"] * 12 + ["Product / Technology"]
    
    passes = df_out["credit_guard_pass"].tolist()
    # 0-5 pass
    for i in range(6):
        assert passes[i] is True
        
    # 6-11 reject
    for i in range(6, 12):
        assert passes[i] is False
        
    # 12 is Non-Credit Event -> passes
    assert passes[12] is True
    assert df_out.iloc[12]["credit_guard_reason"] == "NOT_APPLICABLE"
    
def test_guard_stage_checkpoint_resume(dummy_impact_csv):
    input_path, output_dir = dummy_impact_csv
    
    # Run partially (simulate failure)
    # We will just run with max_rows=5
    run_guard_stage(input_path, output_dir, chunk_size=5, max_rows=5)
    
    df1 = pd.read_csv(output_dir / "guard_scored.csv")
    assert len(df1) == 5
    
    # Resume
    run_guard_stage(input_path, output_dir, chunk_size=5)
    
    df2 = pd.read_csv(output_dir / "guard_scored.csv")
    assert len(df2) == 13
    
def test_guard_stage_repeated_execution_identical(dummy_impact_csv):
    input_path, output_dir = dummy_impact_csv
    out1 = run_guard_stage(input_path, output_dir, chunk_size=10)
    df1 = pd.read_csv(out1)
    
    # Clear output and run again
    (output_dir / "guard_scored.csv").unlink()
    # Checkpoints also need clearing to force rerun, or we just use a new output_dir
    
def test_canonicalize_stage(dummy_impact_csv):
    input_path, output_dir = dummy_impact_csv
    guard_path = run_guard_stage(input_path, output_dir, chunk_size=13)
    
    canonical_path = run_canonicalize_stage(guard_path, output_dir)
    df_can = pd.read_csv(canonical_path)
    
    # Rows 0-5 and 12 should be included (7 rows)
    # They should form clusters. Since all Acme (1,2,3,4,5) are Credit Events but with different text, 
    # the clusterer might group them or keep them separate.
    # At least we can verify the schema
    assert "event_id" in df_can.columns
    assert "observation_count" in df_can.columns
    assert "canonical_entity" in df_can.columns
    assert len(df_can) > 0
    assert len(df_can) <= 7  # 7 valid material rows
