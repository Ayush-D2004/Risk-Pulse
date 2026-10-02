#!/usr/bin/env python3
import os
import sys
import json
import time
import numpy as np
from pathlib import Path
from collections import Counter, defaultdict
from sklearn.model_selection import GroupShuffleSplit

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.models import NewsDocument
from src.ingestion.processor import IngestionProcessor
from src.ingestion.semantic_classifier import SemanticCandidateClassifier
from src.ingestion.benchmark_candidate_filter import (
    try_fetch_gdelt_data, 
    classify_financial_relevance_batch,
    create_benchmark_registry
)
from src.ingestion.gdelt_client import GDELTClient

DATA_CACHE_FILE = Path("data/processed/gdelt_candidate_labels.json")

def load_or_fetch_dataset(target_count=5000):
    """Fetch GDELT documents, label them with the authoritative classifier, and cache them."""
    if DATA_CACHE_FILE.exists():
        print(f"Loading cached dataset from {DATA_CACHE_FILE}...")
        with open(DATA_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            docs = [NewsDocument(**d["document"]) for d in data]
            labels = {d["document"]["document_id"]: d["label"] for d in data}
            return docs, labels

    print(f"No cached data found. Fetching up to {target_count} GDELT documents...")
    gdelt_articles = try_fetch_gdelt_data(target_count=target_count)
    
    if gdelt_articles and len(gdelt_articles) >= 50:
        client = GDELTClient()
        docs = client.normalize(gdelt_articles)
    else:
        print("GDELT fetch failed due to API limits and no local cache exists.")
        return None, None

    print(f"Running authoritative classifier on {len(docs)} documents to generate labels...")
    # This acts as our ground truth
    labels = classify_financial_relevance_batch(docs, batch_size=32)
    
    # Save cache
    DATA_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    cache_data = []
    for doc in docs:
        did = doc.document_id
        if did in labels:
            cache_data.append({
                "document": doc.__dict__,
                "label": labels[did]
            })
            
    with open(DATA_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2, default=str)
        
    print(f"Cached {len(cache_data)} labeled documents to {DATA_CACHE_FILE}")
    return docs, labels

def evaluate_thresholds(classifier, val_docs, val_labels, deterministic_kept_ids):
    """Evaluate thresholds explicitly for the semantic fallback."""
    print("\n" + "=" * 72)
    print("THRESHOLD TRADEOFF ANALYSIS (Validation Set)")
    print("=" * 72)
    
    # We only care about documents DROPPED by the deterministic gate
    val_dropped_docs = [d for d in val_docs if d.document_id not in deterministic_kept_ids]
    val_dropped_labels = {d.document_id: val_labels[d.document_id] for d in val_dropped_docs}
    
    if not val_dropped_docs:
        print("No validation documents dropped by deterministic gate!")
        return 0.5
        
    texts = [f"{d.title} {d.body or ''}".strip() for d in val_dropped_docs]
    probas = classifier.predict_proba(texts)
    
    total_val_docs = len(val_docs)
    val_fin_docs = sum(val_labels.values())
    
    print(f"{'Threshold':<10} | {'Recall':<10} | {'Precision':<10} | {'Candidate Rate':<15}")
    print("-" * 55)
    
    thresholds = [x/100.0 for x in range(10, 95, 5)] # 0.10 to 0.90
    
    best_t = 0.5
    for t in thresholds:
        semantic_kept_ids = {d.document_id for i, d in enumerate(val_dropped_docs) if probas[i] >= t}
        
        total_kept_ids = deterministic_kept_ids.union(semantic_kept_ids)
        total_kept_count = len(total_kept_ids)
        
        tp = sum(1 for d in val_docs if val_labels[d.document_id] and d.document_id in total_kept_ids)
        
        recall = tp / val_fin_docs if val_fin_docs > 0 else 0
        precision = tp / total_kept_count if total_kept_count > 0 else 0
        candidate_rate = total_kept_count / total_val_docs if total_val_docs > 0 else 0
        
        print(f"{t:<10.2f} | {recall:<10.4f} | {precision:<10.4f} | {candidate_rate:<15.4f}")
        
    return best_t

def main():
    print("Loading data...")
    # Target 5000 docs for the large eval. 
    docs, labels = load_or_fetch_dataset(target_count=5000)
    
    if docs is None:
        print("\n[STOP] Cannot proceed. GDELT API is rate-limited and no cached data of sufficient size is available.")
        print("The production benchmark cannot yet be completed. Please wait for GDELT API limits to reset and run this script again.")
        return
        
    # Align lists
    valid_docs = [d for d in docs if d.document_id in labels]
    
    print(f"Dataset Size: {len(valid_docs)}")
    y = [1 if labels[d.document_id] else 0 for d in valid_docs]
    print(f"Positive ratio: {sum(y)/len(y):.2%}")
    
    # 3. Prevent train/test leakage by grouping duplicate/similar headlines
    # Create group IDs based on normalized headline
    groups = []
    import re
    for d in valid_docs:
        norm_title = re.sub(r'[^a-z0-9]', '', d.title.lower())
        groups.append(norm_title)
        
    # GroupShuffleSplit ensures same group doesn't span train/val/test
    gss1 = GroupShuffleSplit(n_splits=1, test_size=0.30, random_state=42)
    train_idx, temp_idx = next(gss1.split(valid_docs, y, groups))
    
    docs_train = [valid_docs[i] for i in train_idx]
    y_train = [y[i] for i in train_idx]
    
    docs_temp = [valid_docs[i] for i in temp_idx]
    y_temp = [y[i] for i in temp_idx]
    groups_temp = [groups[i] for i in temp_idx]
    
    gss2 = GroupShuffleSplit(n_splits=1, test_size=0.50, random_state=42)
    val_idx, test_idx = next(gss2.split(docs_temp, y_temp, groups_temp))
    
    docs_val = [docs_temp[i] for i in val_idx]
    y_val = [y_temp[i] for i in val_idx]
    
    docs_test = [docs_temp[i] for i in test_idx]
    y_test = [y_temp[i] for i in test_idx]
    
    print(f"Split sizes (Groups separated): Train {len(docs_train)}, Val {len(docs_val)}, Test {len(docs_test)}")
    
    # Train the semantic classifier
    print("\n--- Training Semantic Fallback Classifier ---")
    semantic_clf = SemanticCandidateClassifier(threshold=0.5)
    train_texts = [f"{d.title} {d.body or ''}".strip() for d in docs_train]
    semantic_clf.train(train_texts, y_train)
    
    # Initialize processor
    registry = create_benchmark_registry()
    processor = IngestionProcessor(registry=registry)
    # Ensure disabled initially
    processor.semantic_classifier.classifier = None 
    
    print("\n--- Evaluating Deterministic Gate on Validation Set ---")
    val_candidate_results = processor.candidate_filter(docs_val)
    val_det_kept_ids = {cr.document.document_id for cr in val_candidate_results if cr.kept}
    
    # Evaluate thresholds
    evaluate_thresholds(semantic_clf, docs_val, {d.document_id: l for d, l in zip(docs_val, y_val)}, val_det_kept_ids)
    
    # Request user to select threshold (or hardcode for now based on typical tradeoffs)
    optimal_t = 0.50 # We will just use a moderate default if user isn't prompted
    print(f"\nSelecting threshold = {optimal_t} for final evaluation.")
    semantic_clf.threshold = optimal_t
    semantic_clf.save_classifier()
    
    # Final Evaluation on TEST set
    print("\n" + "=" * 72)
    print("FINAL EVALUATION ON TEST SET")
    print("=" * 72)
    
    test_labels = {d.document_id: l for d, l in zip(docs_test, y_test)}
    n_test_fin = sum(y_test)
    
    # A = Keyword only
    kw_kept = processor.financial_relevance_filter(docs_test)
    kw_kept_ids = {d.document_id for d in kw_kept}
    
    # B & C = Deterministic + Semantic 
    b_candidate_results = []
    
    temp_clf = processor.semantic_classifier.classifier
    processor.semantic_classifier.classifier = None # disable C
    b_results = processor.candidate_filter(docs_test)
    b_kept_ids = {cr.document.document_id for cr in b_results if cr.kept}
    
    processor.semantic_classifier = semantic_clf # enable C
    c_results = processor.candidate_filter(docs_test)
    c_kept_ids = {cr.document.document_id for cr in c_results if cr.kept}
    
    # Metrics
    def calc_metrics(kept_ids):
        tp = sum(1 for d in docs_test if test_labels[d.document_id] and d.document_id in kept_ids)
        fp = sum(1 for d in docs_test if not test_labels[d.document_id] and d.document_id in kept_ids)
        fn = sum(1 for d in docs_test if test_labels[d.document_id] and d.document_id not in kept_ids)
        recall = tp / n_test_fin if n_test_fin > 0 else 0
        precision = tp / len(kept_ids) if len(kept_ids) > 0 else 0
        cand_rate = len(kept_ids) / len(docs_test) if len(docs_test) > 0 else 0
        return recall, precision, cand_rate, fn, fp
        
    a_rec, a_prec, a_cr, a_fn, a_fp = calc_metrics(kw_kept_ids)
    b_rec, b_prec, b_cr, b_fn, b_fp = calc_metrics(b_kept_ids)
    c_rec, c_prec, c_cr, c_fn, c_fp = calc_metrics(c_kept_ids)
    
    print(f"{'Stage':<20} | {'Recall':<10} | {'Precision':<10} | {'Candidate Rate':<15}")
    print("-" * 65)
    print(f"{'A (Keyword)':<20} | {a_rec:<10.4f} | {a_prec:<10.4f} | {a_cr:<15.4f}")
    print(f"{'B (Deterministic)':<20} | {b_rec:<10.4f} | {b_prec:<10.4f} | {b_cr:<15.4f}")
    print(f"{'C (Det + Semantic)':<20} | {c_rec:<10.4f} | {c_prec:<10.4f} | {c_cr:<15.4f}")
    
    print("\nDetailed breakdown for C (Det + Semantic Fallback):")
    print(f"  False Negatives: {c_fn}")
    print(f"  False Positives: {c_fp}")
    
    # Compute metrics
    c_semantic_sent = len(docs_test) - len(b_kept_ids)
    c_auth_sent = len(c_kept_ids)
    
    print("\nCOMPUTE BENCHMARK:")
    print(f"  Semantic invocation rate: {c_semantic_sent/len(docs_test):.2%} ({c_semantic_sent} / {len(docs_test)})")
    print(f"  Final NLP invocation rate: {c_auth_sent/len(docs_test):.2%} ({c_auth_sent} / {len(docs_test)})")
    
    baseline_auth_sent = len(docs_test) # If we sent everything without filtering
    reduction_rate = 1.0 - (c_auth_sent / baseline_auth_sent)
    print(f"  Compute reduction vs Baseline (sending all): {reduction_rate:.2%}")
    
    # ---------------------------------------------------------
    # ERROR ANALYSIS
    # ---------------------------------------------------------
    print("\n" + "=" * 72)
    print("FALSE POSITIVE ANALYSIS (Semantic Stage)")
    print("=" * 72)
    
    fps = [cr for cr in c_results if cr.kept and not test_labels[cr.document.document_id] and "SEMANTIC" in cr.reasons]
    print(f"Total semantic false positives: {len(fps)}\n")
    for cr in fps[:30]:
        print(f"[FP] Prob={cr.semantic_probability:.3f} | {cr.document.title}")
        
    print("\n" + "=" * 72)
    print("FALSE NEGATIVE ANALYSIS (Semantic Stage)")
    print("=" * 72)
    
    fns = [cr for cr in c_results if not cr.kept and test_labels[cr.document.document_id]]
    print(f"Total false negatives remaining: {len(fns)}\n")
    for cr in fns:
        print(f"[FN] Prob={cr.semantic_probability:.3f} | {cr.document.title}")

if __name__ == "__main__":
    main()
