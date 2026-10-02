import sys
from pathlib import Path
import json
import time

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.gdelt_client import GDELTClient
from src.ingestion.processor import IngestionProcessor
from src.ingestion.entity_registry import EntityRegistry
from src.risk.risk_signal import RiskSignal, Evidence
from src.risk.event_clusterer import EventClusterer

def create_mock_registry() -> EntityRegistry:
    registry = EntityRegistry()
    entities = [
        {
            "entity_id": "ent_001",
            "canonical_name": "Apple Inc.",
            "ticker": "AAPL",
            "aliases": ["Apple", "the iPhone maker"]
        },
        {
            "entity_id": "ent_002",
            "canonical_name": "Microsoft Corporation",
            "ticker": "MSFT",
            "aliases": ["Microsoft", "the software giant"]
        },
        {
            "entity_id": "ent_003",
            "canonical_name": "Rosneft Oil Company",
            "ticker": "ROSN.ME",
            "aliases": ["Rosneft", "Russian oil giant"]
        },
        {
            "entity_id": "ent_004",
            "canonical_name": "CITGO Petroleum Corporation",
            "ticker": "CITGO",
            "aliases": ["Citgo"]
        },
        {
            "entity_id": "ent_005",
            "canonical_name": "Activision Blizzard",
            "ticker": "ATVI",
            "aliases": ["Activision"]
        }
    ]
    for ent in entities:
        registry.add_entity(ent)
    return registry

def main():
    print("Initializing components...")
    
    registry = create_mock_registry()
    client = GDELTClient()
    processor = IngestionProcessor(registry=registry)
    clusterer = EventClusterer()

    # 1. Expand the test fixture with registry tests
    test_articles = [
        # Base tests
        {
            "url": "https://reuters.com/article/1",
            "title": "Rosneft acquires 19.5% Citgo stake",
            "domain": "reuters.com",
            "seendate": "20231015093000Z",
            "language": "English"
        },
        {
            "url": "https://wsj.com/article/5",
            "title": "Russian oil giant takes minority interest in Citgo",
            "domain": "wsj.com",
            "seendate": "20231015103000Z",
            "language": "English"
        },
        # Entity Resolution tests
        {
            "url": "https://news.com/aapl1",
            "title": "Apple announces new product",
            "domain": "news.com",
            "seendate": "20231015100000Z",
            "language": "English"
        },
        {
            "url": "https://news.com/aapl2",
            "title": "Apple Inc. reports record earnings",
            "domain": "news.com",
            "seendate": "20231015100100Z",
            "language": "English"
        },
        {
            "url": "https://news.com/msft1",
            "title": "Microsoft Corp acquires Activision",
            "domain": "news.com",
            "seendate": "20231015100200Z",
            "language": "English"
        },
        {
            "url": "https://news.com/msft2",
            "title": "The software giant sues competitor",
            "domain": "news.com",
            "seendate": "20231015100300Z",
            "language": "English"
        },
        {
            "url": "https://news.com/unknown1",
            "title": "UnknownCompany Ltd. goes bankrupt",
            "domain": "news.com",
            "seendate": "20231015100400Z",
            "language": "English"
        }
    ]

    print(f"\n--- 1. Normalization ---")
    docs = client.normalize(test_articles)
    
    print(f"\n--- 2. Financial Relevance Filtering ---")
    financial_docs = processor.financial_relevance_filter(docs)
    print(f"Kept {len(financial_docs)} documents.")

    print(f"\n--- 3. Entity Resolution Tests ---")
    for doc in financial_docs:
        resolved_entities = processor.extract_entities(doc)
        print(f"'{doc.title}' -> Resolved Entities: {resolved_entities}")

    print(f"\n--- 4. Cross-Source Integration ---")
    twitter_signal = RiskSignal(
        entity="ROSN.ME",
        source="twitter",
        sentiment_score=0.2,
        event_type="Merger & Acquisition",
        event_confidence=0.85,
        materiality="MATERIAL_EVENT",
        timestamp="2023-10-15T09:00:00Z",
        evidence=Evidence(text="Rosneft takes stake in Citgo")
    )
    clusterer.process_signal(twitter_signal)

    for doc in financial_docs:
        entities = processor.extract_entities(doc)
        for ent in entities:
            # Mock NLP classification
            signal = RiskSignal(
                entity=ent,
                source="gdelt",
                source_credibility=0.8,
                sentiment_score=0.1,
                event_type="Merger & Acquisition",
                event_confidence=0.9,
                materiality="MATERIAL_EVENT",
                timestamp=doc.published_at,
                evidence=Evidence(headline=doc.title, text=doc.title)
            )
            clusterer.process_signal(signal)

    for i, cluster in enumerate(clusterer.clusters, 1):
        if "ROSN" in cluster.entity or "CITG" in cluster.entity:
            print(f"Cluster {i} | Entity: {cluster.entity} | Size: {cluster.size}")
            for cand in cluster.candidates:
                print(f"  - [{cand.signal.source}] Novelty: {cand.signal.novelty:.2f} | {cand.text_for_embedding[:60]}...")

    print(f"\n--- 5. Benchmark ---")
    print("Running resolution benchmark on 7,000 synthetic records...")
    import copy
    large_docs = []
    for i in range(1000):
        for doc in docs:  # All docs, to test filtering
            large_docs.append(copy.deepcopy(doc))
            
    t0 = time.time()
    # Candidate filtering
    filtered_large = processor.financial_relevance_filter(large_docs)
    
    t1 = time.time()
    # Extraction
    for d in filtered_large:
        _ = processor.extract_entities(d)
    t2 = time.time()
    
    print(f"Filtering {len(large_docs)} docs -> {len(filtered_large)} docs took {t1-t0:.4f} seconds.")
    print(f"Entity Resolution on {len(filtered_large)} docs took {t2-t1:.4f} seconds.")
    print(f"Overall Throughput: {len(large_docs)/(t2-t0):.2f} docs/sec.")

if __name__ == "__main__":
    main()
