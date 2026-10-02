import os
import pickle
from typing import List, Optional, Tuple, Dict
from pathlib import Path
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.linear_model import LogisticRegression
except ImportError:
    SentenceTransformer = None
    LogisticRegression = None


class SemanticCandidateClassifier:
    """
    Lightweight fallback semantic classifier.
    Uses sentence-transformers (all-MiniLM-L6-v2) to encode text and a 
    Logistic Regression model to predict P(FINANCIAL_EVENT).
    """
    def __init__(self, model_dir: str = "models/semantic_candidate", threshold: float = 0.5):
        self.model_dir = Path(model_dir)
        self.model_path = self.model_dir / "logistic_regression.pkl"
        self.threshold = threshold
        self.encoder = None
        self.classifier = None
        self._initialize_encoder()
        self._load_classifier()

    def _initialize_encoder(self):
        if SentenceTransformer is None:
            print("WARNING: sentence-transformers not installed. Semantic classifier disabled.")
            return
        # Use CPU explicitly as requested
        self.encoder = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

    def _load_classifier(self):
        if self.model_path.exists():
            with open(self.model_path, "rb") as f:
                self.classifier = pickle.load(f)

    def save_classifier(self):
        self.model_dir.mkdir(parents=True, exist_ok=True)
        with open(self.model_path, "wb") as f:
            pickle.dump(self.classifier, f)

    def encode_texts(self, texts: List[str], show_progress_bar: bool = False) -> np.ndarray:
        if self.encoder is None:
             raise RuntimeError("Encoder not initialized.")
        clean_texts = [t if t else "" for t in texts]
        return self.encoder.encode(clean_texts, show_progress_bar=show_progress_bar, convert_to_numpy=True)

    def train(self, texts: List[str], labels: List[int], C: float = 1.0, class_weight: str = 'balanced'):
        """Train the logistic regression model on the given texts and boolean/int labels."""
        if self.encoder is None or LogisticRegression is None:
            raise RuntimeError("Missing dependencies for SemanticCandidateClassifier")
        
        print(f"Encoding {len(texts)} training texts...")
        embeddings = self.encode_texts(texts, show_progress_bar=True)
        print("Training Logistic Regression model...")
        self.classifier = LogisticRegression(C=C, class_weight=class_weight, random_state=42, max_iter=1000)
        self.classifier.fit(embeddings, labels)
        self.save_classifier()
        print(f"Model saved to {self.model_path}")

    def predict_proba(self, texts: List[str]) -> List[float]:
        if self.encoder is None or self.classifier is None:
            # If not trained or dependencies missing, fallback to returning 0 probability
            return [0.0] * len(texts)
        
        embeddings = self.encode_texts(texts)
        
        # Predict probability for class 1 (FINANCIAL_EVENT)
        probas = self.classifier.predict_proba(embeddings)[:, 1]
        return probas.tolist()

    def predict(self, texts: List[str]) -> List[bool]:
        """Predict whether texts pass the candidate gate based on the threshold."""
        probas = self.predict_proba(texts)
        return [p >= self.threshold for p in probas]
