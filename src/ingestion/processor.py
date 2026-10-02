import hashlib
import json
from pathlib import Path
from typing import List, Set, Optional, FrozenSet
from dataclasses import dataclass, field
from src.ingestion.models import NewsDocument
from src.ingestion.entity_registry import EntityRegistry
from src.ingestion.semantic_classifier import SemanticCandidateClassifier
import spacy


@dataclass
class CandidateResult:
    """
    Lightweight audit structure for the candidate filter decision.

    This does NOT modify NewsDocument. The downstream NLP pipeline continues
    to receive unmodified NewsDocument objects. This structure exists solely
    for observability: why was each document kept or dropped by the cheap
    pre-NLP candidate funnel?
    """
    document: NewsDocument
    kept: bool
    reasons: FrozenSet[str] = field(default_factory=frozenset)
    # Individual signal values for attribution analysis
    entity_signal: bool = False
    domain_signal: bool = False
    gdelt_theme_signal: bool = False
    keyword_signal: bool = False
    resolved_entity_ids: List[str] = field(default_factory=list)
    semantic_signal: bool = False
    semantic_probability: float = 0.0


class IngestionProcessor:
    """
    Handles inexpensive filtering, deduplication, and initial entity extraction
    for the ingestion pipeline prior to expensive downstream NLP inference.
    """
    def __init__(self, config_path: str = "config/ingestion_config.json", registry: Optional[EntityRegistry] = None):
        self.config_path = Path(config_path)
        self.financial_keywords: Set[str] = set()
        self.trusted_financial_domains: Set[str] = set()
        self.gdelt_financial_theme_prefixes: List[str] = []

        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                self.financial_keywords = set(config.get("financial_keywords", []))
                self.trusted_financial_domains = set(
                    d.lower() for d in config.get("trusted_financial_domains", [])
                )
                self.gdelt_financial_theme_prefixes = config.get(
                    "gdelt_financial_theme_prefixes", []
                )
        else:
            self.financial_keywords = {"merger", "acquisition", "stake"}

        self.nlp = spacy.load("en_core_web_sm")
        self.registry = registry or EntityRegistry()
        
        # Load lightweight semantic fallback classifier (if trained/available)
        self.semantic_classifier = SemanticCandidateClassifier(threshold=0.3) # Default threshold, tunable

    def filter_language(self, docs: List[NewsDocument], target_lang: str = "english") -> List[NewsDocument]:
        """Keep only documents matching the target language."""
        return [d for d in docs if d.language.lower() == target_lang.lower()]

    def deduplicate(self, docs: List[NewsDocument]) -> List[NewsDocument]:
        """
        Deduplicate using URL, Headline normalization, Content Hash, and Publisher+Timestamp.
        """
        seen_urls: Set[str] = set()
        seen_hashes: Set[str] = set()
        seen_pub_time: Set[str] = set()

        deduped = []
        for doc in docs:
            # 1. URL check
            url_norm = doc.url.strip().lower()
            if url_norm in seen_urls:
                continue

            # 2. Headline norm hash
            title_norm = "".join(c.lower() for c in doc.title if c.isalnum())

            # 3. Content hash
            content_str = title_norm + (doc.body or "")
            content_hash = hashlib.sha256(content_str.encode("utf-8")).hexdigest()
            if content_hash in seen_hashes:
                continue

            # 4. Publisher + Timestamp check
            pub_time_key = f"{doc.publisher}_{doc.published_at.isoformat()}"
            if pub_time_key in seen_pub_time:
                continue

            seen_urls.add(url_norm)
            seen_hashes.add(content_hash)
            seen_pub_time.add(pub_time_key)
            deduped.append(doc)

        return deduped

    def financial_relevance_filter(self, docs: List[NewsDocument]) -> List[NewsDocument]:
        """
        LEGACY keyword-only filter. Retained for backward compatibility and
        benchmark baseline comparison.

        WARNING: This is the single-point vocabulary failure that the
        candidate_filter() method replaces. A financially material article
        will be dropped if none of the configured keywords appear in the text.
        """
        filtered = []
        for doc in docs:
            text = f"{doc.title} {doc.body or ''}".lower()
            if any(kw in text for kw in self.financial_keywords):
                filtered.append(doc)
        return filtered

    # ------------------------------------------------------------------
    # SIGNAL A: Entity signal
    # ------------------------------------------------------------------
    def _check_entity_signal(self, doc: NewsDocument) -> tuple:
        """
        Determine whether at least one entity in the document resolves to
        a tracked entity in the EntityRegistry.

        IMPORTANT DISTINCTION:
            resolved entity → candidate_for_downstream_NLP = True
            This does NOT mean financial_relevance = True.

        An article mentioning "Apple" may be irrelevant to financial risk,
        but we would rather allow it through the expensive relevance
        classifier than accidentally discard a genuine Apple event.

        Returns:
            (signal_fired: bool, resolved_entity_ids: list[str])
        """
        resolved_ids = self.extract_entities(doc)
        return (len(resolved_ids) > 0, resolved_ids)

    # ------------------------------------------------------------------
    # SIGNAL B: Publisher/domain signal
    # ------------------------------------------------------------------
    def _check_domain_signal(self, doc: NewsDocument) -> bool:
        """
        Check whether the document originates from a trusted financial/
        business news domain configured in ingestion_config.json.

        This is a candidate bypass, NOT a statement that every article from
        these domains is financially material. Documents from trusted domains
        are forwarded to the authoritative downstream relevance classifier.
        """
        domain = (doc.domain or "").strip().lower()
        if not domain:
            # Fallback: try to extract domain from publisher field
            domain = (doc.publisher or "").strip().lower()
        if not domain:
            return False

        # Check exact match and subdomain match (e.g. "uk.reuters.com" matches "reuters.com")
        for trusted in self.trusted_financial_domains:
            if domain == trusted or domain.endswith("." + trusted):
                return True
        return False

    # ------------------------------------------------------------------
    # SIGNAL C: GDELT theme signal
    # ------------------------------------------------------------------
    def _check_gdelt_theme_signal(self, doc: NewsDocument) -> bool:
        """
        Check whether the document's raw GDELT metadata contains themes
        matching configured financial/economic theme prefixes.

        CURRENT STATUS (GDELT DOC API, artlist mode):
            The DOC API artlist response does NOT include GKG theme
            annotations. The raw_metadata for DOC API articles contains
            only: url, title, seendate, domain, language, sourcecountry,
            socialimage, and similar surface-level fields.

            Therefore this signal is currently ALWAYS FALSE for documents
            ingested via the DOC API feed.

        If the ingestion source is later expanded to include GKG-enriched
        records (e.g., from the GKG files or a joined pipeline), this
        signal will automatically activate using the configured prefixes.
        """
        raw = doc.raw_metadata
        if not raw:
            return False

        # Look for any field that could contain theme data.
        # Known GDELT GKG fields: "themes", "V2Themes", "THEMES"
        themes_raw = None
        for key in ("themes", "V2Themes", "THEMES", "Themes"):
            if key in raw:
                themes_raw = raw[key]
                break

        if themes_raw is None:
            return False

        # Themes may be a semicolon-delimited string or a list
        if isinstance(themes_raw, str):
            themes_list = [t.strip() for t in themes_raw.split(";") if t.strip()]
        elif isinstance(themes_raw, list):
            themes_list = [str(t).strip() for t in themes_raw if t]
        else:
            return False

        for theme in themes_list:
            theme_upper = theme.upper()
            for prefix in self.gdelt_financial_theme_prefixes:
                if theme_upper.startswith(prefix.upper()):
                    return True
        return False

    # ------------------------------------------------------------------
    # SIGNAL D: Keyword signal
    # ------------------------------------------------------------------
    def _check_keyword_signal(self, doc: NewsDocument) -> bool:
        """
        The existing financial keyword mechanism. Checks whether any
        configured keyword appears in the document title + body.

        keyword match → signal = True
        No keyword match → signal = False

        But: keyword signal = False must no longer mean DROP.
        This is now one of four signals in the OR gate.
        """
        text = f"{doc.title} {doc.body or ''}".lower()
        return any(kw in text for kw in self.financial_keywords)

    # ------------------------------------------------------------------
    # HIGH-RECALL CANDIDATE FUNNEL
    # ------------------------------------------------------------------
    def candidate_filter(self, docs: List[NewsDocument]) -> List[CandidateResult]:
        """
        High-recall candidate funnel that replaces the keyword-only gate.

        A document is KEPT if ANY of the following signals is True:
            SIGNAL A: resolved_entity       (EntityRegistry match)
            SIGNAL B: trusted_financial_domain
            SIGNAL C: validated_gdelt_financial_theme
            SIGNAL D: financial_keyword_match

        This is deliberately an OR gate. No weighted scores, no thresholds,
        no learned model. The purpose is to remove the single-point
        vocabulary failure while keeping the filter extremely cheap and
        explainable.

        Returns:
            List[CandidateResult] for ALL input documents (kept and dropped),
            enabling full benchmark and audit analysis.
        """
        results = []
        dropped_docs = []
        dropped_indices = []

        for i, doc in enumerate(docs):
            reasons = set()

            # Signal A: Entity
            entity_signal, resolved_ids = self._check_entity_signal(doc)
            if entity_signal:
                reasons.add("ENTITY")

            # Signal B: Domain
            domain_signal = self._check_domain_signal(doc)
            if domain_signal:
                reasons.add("DOMAIN")

            # Signal C: GDELT Theme
            gdelt_theme_signal = self._check_gdelt_theme_signal(doc)
            if gdelt_theme_signal:
                reasons.add("GDELT_THEME")

            # Signal D: Keyword
            keyword_signal = self._check_keyword_signal(doc)
            if keyword_signal:
                reasons.add("KEYWORD")

            kept = len(reasons) > 0

            cr = CandidateResult(
                document=doc,
                kept=kept,
                reasons=set(reasons),
                entity_signal=entity_signal,
                domain_signal=domain_signal,
                gdelt_theme_signal=gdelt_theme_signal,
                keyword_signal=keyword_signal,
                resolved_entity_ids=resolved_ids,
            )
            results.append(cr)
            
            if not kept:
                dropped_docs.append(doc)
                dropped_indices.append(i)

        # STAGE 2: Lightweight Semantic Fallback ONLY for dropped documents
        if dropped_docs and self.semantic_classifier.classifier is not None:
            texts_to_score = [f"{d.title} {d.body or ''}".strip() for d in dropped_docs]
            probas = self.semantic_classifier.predict_proba(texts_to_score)
            
            for doc_idx, proba in zip(dropped_indices, probas):
                results[doc_idx].semantic_probability = proba
                if proba >= self.semantic_classifier.threshold:
                    results[doc_idx].semantic_signal = True
                    results[doc_idx].kept = True
                    results[doc_idx].reasons.add("SEMANTIC")

        # Freeze the reasons sets to match the FrozenSet typing
        for cr in results:
            cr.reasons = frozenset(cr.reasons)

        return results

    def extract_entities(self, doc: NewsDocument) -> List[str]:
        """
        Extract entities using spaCy, then resolve using EntityRegistry.
        Returns a list of resolved canonical entity IDs.
        """
        spacy_doc = self.nlp(doc.title)
        resolved_ids = set()

        # 1. Use NER candidates
        for ent in spacy_doc.ents:
            if ent.label_ in ["ORG", "PERSON"]:
                resolved = self.registry.resolve(ent.text, context=doc.title)
                if resolved and resolved.confidence >= 0.5:
                    resolved_ids.add(resolved.ticker or resolved.entity_id)

        # 2. Heuristic fallback (fast scan over title for known aliases to improve recall)
        text_lower = f" {doc.title.lower()} "
        for alias in self.registry.alias_index.keys():
            # boundary check to avoid substring false positives e.g. "apple" in "pineapple"
            if f" {alias} " in text_lower:
                resolved = self.registry.resolve(alias, context=doc.title)
                if resolved and resolved.confidence >= 0.5:
                    resolved_ids.add(resolved.ticker or resolved.entity_id)

        return list(resolved_ids)
