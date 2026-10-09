import uuid
from datetime import datetime, timezone
import numpy as np
from typing import List, Dict, Optional, Tuple, Any
from pydantic import BaseModel, Field, ConfigDict
try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False
try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

from .risk_signal import RiskSignal
from src.nlp.entity_normalizer import EntityNormalizer

COMPATIBLE_EVENT_TYPES = {
    "Credit Event": {"Credit Event", "Market / Liquidity", "Corporate / Earnings"},
    "Geopolitical": {"Geopolitical", "Macroeconomic", "Regulatory / Legal", "Commodity / Supply Chain"},
    "Macroeconomic": {"Macroeconomic", "Geopolitical", "Regulatory / Legal", "Corporate / Earnings", "Commodity / Supply Chain", "Market / Liquidity"},
    "Merger & Acquisition": {"Merger & Acquisition", "Corporate / Earnings"},
    "Regulatory / Legal": {"Regulatory / Legal", "Geopolitical", "Macroeconomic", "Corporate / Earnings"},
    "Corporate / Earnings": {"Corporate / Earnings", "Macroeconomic", "Merger & Acquisition", "Regulatory / Legal", "Product / Technology", "Credit Event"},
    "Product / Technology": {"Product / Technology", "Corporate / Earnings"},
    "Commodity / Supply Chain": {"Commodity / Supply Chain", "Macroeconomic", "Geopolitical"},
    "Market / Liquidity": {"Market / Liquidity", "Macroeconomic", "Credit Event"},
    "Other / Unclear": {"Other / Unclear"},
    "NO_EVENT": {"NO_EVENT"},
}

def is_event_type_compatible(t1: str, t2: str) -> bool:
    if t1 == t2:
        return True
    s1 = COMPATIBLE_EVENT_TYPES.get(t1, {t1})
    s2 = COMPATIBLE_EVENT_TYPES.get(t2, {t2})
    return (t2 in s1) or (t1 in s2)

class EventCandidate(BaseModel):
    """
    Wraps a RiskSignal with its semantic embedding for clustering.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    signal: RiskSignal
    text_for_embedding: str
    embedding: Optional[np.ndarray] = None

    @classmethod
    def from_signal(cls, signal: RiskSignal) -> "EventCandidate":
        text = signal.evidence.headline + " " + signal.evidence.text if signal.evidence.headline else signal.evidence.text
        return cls(signal=signal, text_for_embedding=text)

class EventCluster(BaseModel):
    """
    A canonical event formed by grouping multiple EventCandidates.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    cluster_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    entity: str
    event_type: str
    candidates: List[EventCandidate] = Field(default_factory=list)
    centroid: Optional[np.ndarray] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def add_candidate(self, candidate: EventCandidate):
        self.candidates.append(candidate)
        if len(self.candidates) == 1:
            self.created_at = candidate.signal.timestamp
            self.updated_at = candidate.signal.timestamp
        else:
            self.updated_at = max(self.updated_at, candidate.signal.timestamp)
        self._update_centroid()

    def _update_centroid(self):
        if not self.candidates:
            return
        embeddings = [c.embedding for c in self.candidates if c.embedding is not None]
        if not embeddings:
            return
        mean_emb = np.mean(embeddings, axis=0)
        # Normalize the centroid for cosine similarity
        norm = np.linalg.norm(mean_emb)
        if norm > 0:
            mean_emb = mean_emb / norm
        self.centroid = mean_emb

    def get_canonical_signal(self) -> RiskSignal:
        """
        Returns the earliest signal as the canonical representation,
        but could be enhanced to return a merged signal.
        For now, returns the first candidate's signal.
        """
        if not self.candidates:
            raise ValueError("Cluster has no candidates")
        
        # Sort candidates by timestamp ascending
        sorted_candidates = sorted(self.candidates, key=lambda c: c.signal.timestamp)
        canonical = sorted_candidates[0].signal
        return canonical

    @property
    def size(self) -> int:
        return len(self.candidates)

class EventClusterer:
    """
    Groups RiskSignals into EventClusters using semantic embeddings (BAAI/bge-small-en-v1.5)
    and FAISS similarity search.
    """
    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        similarity_threshold: float = 0.85,
        time_window_hours: float = 72.0,
        normalizer: Optional[EntityNormalizer] = None
    ):
        self.similarity_threshold = similarity_threshold
        self.time_window_hours = time_window_hours
        self.normalizer = normalizer or EntityNormalizer()
        
        # Load embedding model
        if HAS_SENTENCE_TRANSFORMERS:
            self.encoder = SentenceTransformer(model_name)
            self.embedding_dim = self.encoder.get_sentence_embedding_dimension()
        else:
            self.encoder = None
            self.embedding_dim = 384
        
        # In-memory cluster storage
        self.clusters: List[EventCluster] = []
        
        self.id_to_cluster_idx: Dict[int, int] = {}
        self._next_faiss_id = 0
        if HAS_FAISS:
            self.index = faiss.IndexIDMap(faiss.IndexFlatIP(self.embedding_dim))
        else:
            self.index = None

    def generate_embedding(self, candidate: EventCandidate) -> np.ndarray:
        """Generate normalized embedding for the candidate."""
        if not HAS_SENTENCE_TRANSFORMERS or self.encoder is None:
            np.random.seed(hash(candidate.signal.entity + candidate.signal.event_type) % (2**32))
            emb = np.random.randn(self.embedding_dim)
            return (emb / np.linalg.norm(emb)).astype(np.float32)
        emb = self.encoder.encode(candidate.text_for_embedding, normalize_embeddings=True)
        return emb

    def compute_novelty(self, cluster: EventCluster, candidate: EventCandidate) -> float:
        """
        Computes novelty based on cluster state/growth.
        1.0 = breaking/new (first in cluster)
        0.0 = completely stale duplicate
        """
        if cluster.size == 0:
            return 1.0
            
        # Example decay based on size:
        # size 1 -> novelty 0.5
        # size 5 -> novelty 0.1
        # size 10 -> novelty 0.0
        return max(0.0, 1.0 / (cluster.size + 1))

    def process_signal(self, signal: RiskSignal) -> RiskSignal:
        """
        Processes a new RiskSignal, assigns it to a cluster or creates a new one,
        and sets its novelty score.
        """
        # Normalize the entity
        norm_res = self.normalizer.normalize(signal.entity)
        new_entity = norm_res["canonical_entity"]
        
        if norm_res["entity_status"] == "unresolved_source":
            new_entity = f"SOURCE_{norm_res['candidate_entity']}"
        elif not new_entity:
            cand = norm_res["candidate_entity"]
            new_entity = f"UNRESOLVED_{cand}" if cand else "UNRESOLVED_UNKNOWN"
            
        signal.entity = new_entity

        candidate = EventCandidate.from_signal(signal)
        candidate.embedding = self.generate_embedding(candidate)
        
        # Stage 1: Candidate Retrieval
        best_cluster, match_score = self._retrieve_candidate_cluster(candidate)
        
        if best_cluster and match_score >= self.similarity_threshold:
            # Stage 4: Incremental Updates (add to existing cluster)
            novelty = self.compute_novelty(best_cluster, candidate)
            signal.novelty = novelty
            best_cluster.add_candidate(candidate)
            self._update_faiss_index(best_cluster)
        else:
            # Create new cluster
            new_cluster = EventCluster(
                entity=signal.entity,
                event_type=signal.event_type
            )
            signal.novelty = 1.0 # Breaking/new
            new_cluster.add_candidate(candidate)
            
            self.clusters.append(new_cluster)
            cluster_idx = len(self.clusters) - 1
            
            # Add centroid to FAISS index
            self._add_to_faiss(new_cluster.centroid, cluster_idx)
            
        return signal

    def _retrieve_candidate_cluster(self, candidate: EventCandidate) -> Tuple[Optional[EventCluster], float]:
        """
        Stage 1 & 2 & 3: Find the best matching cluster based on FAISS similarity,
        entity/type matching, and temporal window.
        """
        if HAS_FAISS:
            if self.index is None or self.index.ntotal == 0:
                return None, 0.0

            k = min(50, self.index.ntotal)
            emb_query = np.expand_dims(candidate.embedding, axis=0)
            
            distances, indices = self.index.search(emb_query, k)
            
            best_cluster = None
            best_score = -1.0
            
            for score, faiss_id in zip(distances[0], indices[0]):
                if faiss_id == -1:
                    continue
                    
                cluster_idx = self.id_to_cluster_idx[faiss_id]
                cluster = self.clusters[cluster_idx]
                
                # Stage 2: Filters (Entity, Type, Temporal)
                if cluster.entity != candidate.signal.entity:
                    continue
                if not is_event_type_compatible(cluster.event_type, candidate.signal.event_type):
                    continue
                    
                # Temporal check (e.g. within 72 hours of cluster's last update)
                time_diff = abs((candidate.signal.timestamp - cluster.updated_at).total_seconds())
                if time_diff > self.time_window_hours * 3600:
                    continue
                    
                # Stage 3: Composite Score
                composite_score = float(score)
                
                if composite_score > best_score:
                    best_score = composite_score
                    best_cluster = cluster
                    
            return best_cluster, best_score
        else:
            if not self.clusters:
                return None, 0.0
                
            best_cluster = None
            best_score = -1.0
            
            for cluster in self.clusters:
                if cluster.centroid is None:
                    continue
                    
                score = np.dot(cluster.centroid, candidate.embedding)
                
                if cluster.entity != candidate.signal.entity:
                    continue
                if not is_event_type_compatible(cluster.event_type, candidate.signal.event_type):
                    continue
                    
                time_diff = abs((candidate.signal.timestamp - cluster.updated_at).total_seconds())
                if time_diff > self.time_window_hours * 3600:
                    continue
                    
                composite_score = float(score)
                if composite_score > best_score:
                    best_score = composite_score
                    best_cluster = cluster
                    
            return best_cluster, best_score

    def _add_to_faiss(self, centroid: np.ndarray, cluster_idx: int):
        if not HAS_FAISS:
            return
        faiss_id = self._next_faiss_id
        self._next_faiss_id += 1
        
        self.id_to_cluster_idx[faiss_id] = cluster_idx
        if self.index is not None:
            self.index.add_with_ids(np.expand_dims(centroid, axis=0), np.array([faiss_id], dtype=np.int64))

    def _update_faiss_index(self, cluster: EventCluster):
        self._rebuild_faiss_index()
        
    def _rebuild_faiss_index(self):
        if not HAS_FAISS:
            return
        self.index = faiss.IndexIDMap(faiss.IndexFlatIP(self.embedding_dim))
        self.id_to_cluster_idx.clear()
        self._next_faiss_id = 0
        
        for idx, cluster in enumerate(self.clusters):
            if cluster.centroid is not None:
                self._add_to_faiss(cluster.centroid, idx)
