import asyncio
import uuid
import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import torch

from src.integration.runtime_models import PipelineRun, PipelineRunRequest, RunStatus, PipelineStage, StageStatus, RunMode, ObservationSource, ObservationInput
from src.integration.runtime_store import RuntimeStore

from src.nlp.finbert_inference import FinBERT
from src.nlp.event_classifier_v2 import build_classifier, classify_batch, RELEVANCE_DESCRIPTIONS, EVENT_DESCRIPTIONS, EVENT_LABELS
from src.nlp.event_materiality_v4 import classify_text as classify_materiality
from src.nlp.entity_normalizer import EntityNormalizer
from src.risk.impact_scorer import ImpactScorer
from src.risk.risk_signal import RiskSignal, Evidence, MarketContext
from src.risk.event_clusterer import EventClusterer
from src.portfolio.orchestration import StressScenarioEngine
from src.portfolio.models import Portfolio
from src.market.market_context import MarketContextFetcher, MarketContextConfig

class RuntimeOrchestrator:
    def __init__(self, store: RuntimeStore, portfolio: Portfolio, device: str = "cpu"):
        self.store = store
        self.portfolio = portfolio
        self.device = device
        
        if self.device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError(f"Requested device={self.device} but CUDA is not available.")
            
        self.finbert = FinBERT(device=self.device)
        self.event_classifier = build_classifier("MoritzLaurer/deberta-v3-base-zeroshot-v2.0", device=self.device)
        self.entity_normalizer = EntityNormalizer()
        self.impact_scorer = ImpactScorer()
        self.stress_engine = StressScenarioEngine(portfolio=self.portfolio)
        self.clusterer = EventClusterer()
        self.market_fetcher = MarketContextFetcher(MarketContextConfig())
        
        self.inference_lock = threading.Lock()
        
    async def process_run(self, run: PipelineRun):
        run.status = RunStatus.RUNNING
        self.store.update_run(run)
        
        try:
            await asyncio.to_thread(self._execute_pipeline, run)
            run.status = RunStatus.COMPLETED
        except Exception as e:
            run.status = RunStatus.FAILED
            run.error = str(e)
            
        run.completed_at = datetime.now(timezone.utc)
        self.store.update_run(run)

    def _get_or_create_stage(self, run: PipelineRun, name: str) -> PipelineStage:
        for s in run.stages:
            if s.name == name:
                return s
        new_stage = PipelineStage(name=name, status=StageStatus.PENDING)
        run.stages.append(new_stage)
        return new_stage

    def _set_stage_running(self, run: PipelineRun, name: str) -> PipelineStage:
        stage = self._get_or_create_stage(run, name)
        stage.status = StageStatus.RUNNING
        stage.started_at = datetime.now(timezone.utc)
        self.store.update_run(run)
        time.sleep(0.12)  # Brief pause to broadcast active stage state over SSE
        return stage

    def _set_stage_completed(
        self,
        run: PipelineRun,
        name: str,
        output: Optional[Dict[str, Any]] = None,
        status: StageStatus = StageStatus.COMPLETED
    ) -> PipelineStage:
        stage = self._get_or_create_stage(run, name)
        stage.status = status
        stage.completed_at = datetime.now(timezone.utc)
        if output:
            stage.output = output
        self.store.update_run(run)
        time.sleep(0.08)  # Brief pause for visible progression to next stage
        return stage

    def _execute_pipeline(self, run: PipelineRun):
        req = run.request
        observations = req.observations
        mode = req.mode

        # 1. Ingestion Stage
        self._set_stage_running(run, "ingestion")
        self._set_stage_completed(
            run, 
            "ingestion", 
            output={"count": len(observations), "mode": mode.value}
        )

        # 2. Preprocessing Stage
        self._set_stage_running(run, "preprocessing")
        valid_obs = [obs for obs in observations if obs.text.strip()]
        self._set_stage_completed(
            run, 
            "preprocessing", 
            output={"valid_count": len(valid_obs)}
        )

        # 3. Entity Resolution Stage
        self._set_stage_running(run, "entity_resolution")
        resolved_entities = []
        with self.inference_lock:
            for obs in valid_obs:
                raw_entity = obs.entity or "UNKNOWN"
                norm_res = self.entity_normalizer.normalize(raw_entity)
                canonical_entity = norm_res["canonical_entity"]
                if not canonical_entity:
                    canonical_entity = f"UNRESOLVED_{norm_res['candidate_entity']}" if norm_res["candidate_entity"] else "UNRESOLVED_UNKNOWN"
                resolved_entities.append(canonical_entity)
        self._set_stage_completed(
            run, 
            "entity_resolution", 
            output={"resolved": len(resolved_entities)}
        )

        # 4. Sentiment Analysis Stage (FinBERT)
        self._set_stage_running(run, "sentiment")
        sentiment_scores = []
        with self.inference_lock:
            texts = [obs.text for obs in valid_obs]
            if texts:
                fb_df = self.finbert.predict(texts, batch_size=max(1, len(texts)))
                sentiment_scores = [float(row["FINBERT_SCORE"]) for _, row in fb_df.iterrows()]
        self._set_stage_completed(
            run, 
            "sentiment", 
            output={"scored": len(sentiment_scores)}
        )

        # 5. Zero-Shot Event Classification Stage (DeBERTa-v3)
        self._set_stage_running(run, "event_classification")
        classified_events = []
        with self.inference_lock:
            for obs in valid_obs:
                text = obs.text
                rel_results = classify_batch(self.event_classifier, [text], RELEVANCE_DESCRIPTIONS, "This text is about {}.", batch_size=1)
                top_rel_label = rel_results[0]["labels"][0]
                relevance = "FINANCIAL_EVENT" if top_rel_label == RELEVANCE_DESCRIPTIONS[0] else "NO_MATERIAL_EVENT"

                event_type = "NO_EVENT"
                event_conf = 0.0
                if relevance == "FINANCIAL_EVENT":
                    ev_results = classify_batch(self.event_classifier, [text], EVENT_DESCRIPTIONS, "This text describes {}.", batch_size=1)
                    top_ev_desc = ev_results[0]["labels"][0]
                    event_conf = float(ev_results[0]["scores"][0])
                    label_index = EVENT_DESCRIPTIONS.index(top_ev_desc)
                    event_type = EVENT_LABELS[label_index]
                classified_events.append((relevance, event_type, event_conf))
        self._set_stage_completed(
            run, 
            "event_classification", 
            output={"classified": len(classified_events)}
        )

        # 6. Materiality Triage Stage
        self._set_stage_running(run, "materiality")
        signals = []
        with self.inference_lock:
            for i, obs in enumerate(valid_obs):
                text = obs.text
                canonical_entity = resolved_entities[i]
                sentiment_score = sentiment_scores[i]
                relevance, event_type, event_conf = classified_events[i]

                mat_label, final_event_type, mat_reason = classify_materiality(
                    text=text,
                    original_type=event_type,
                    relevance=relevance,
                    confidence=event_conf
                )

                event_id = f"{run.run_id}_{i+1}" if len(valid_obs) > 1 else run.run_id
                sig = RiskSignal(
                    event_id=event_id,
                    entity=canonical_entity,
                    source=obs.source.value,
                    sentiment_score=sentiment_score,
                    event_type=final_event_type,
                    event_confidence=event_conf,
                    materiality=mat_label,
                    timestamp=obs.timestamp or datetime.now(timezone.utc),
                    evidence=Evidence(
                        text=text,
                        headline=obs.headline,
                        url=obs.url,
                        author=obs.author
                    )
                )
                signals.append(sig)
        self._set_stage_completed(
            run, 
            "materiality", 
            output={"material_signals": len(signals)}
        )

        # 7. Impact Scoring Stage
        self._set_stage_running(run, "impact")
        for sig in signals:
            self.impact_scorer.score(sig, in_place=True)
        self._set_stage_completed(
            run, 
            "impact", 
            output={"scored_signals": len(signals)}
        )

        # 8. Semantic Clustering Stage (FAISS)
        self._set_stage_running(run, "clustering")
        canonical_signals = []
        with self.inference_lock:
            for sig in signals:
                clustered_sig = self.clusterer.process_signal(sig)
                if clustered_sig not in canonical_signals:
                    canonical_signals.append(clustered_sig)
        self._set_stage_completed(
            run, 
            "clustering", 
            output={"clusters_formed": len(canonical_signals)}
        )

        # 9. Market Context Stage (Yahoo Finance)
        self._set_stage_running(run, "market_context")
        market_status = StageStatus.COMPLETED
        market_output = {}
        for sig in canonical_signals:
            if mode in (RunMode.LIVE_GDELT, RunMode.ANALYST_SIMULATION):
                sig.market_context = None
                market_status = StageStatus.SKIPPED
                market_output = {"reason": "live/simulated observations lack resolvable market context"}
            else:
                try:
                    res = self.market_fetcher.fetch(sig.entity, sig.timestamp)
                    sig.market_context = res.market_context
                    market_status = StageStatus.COMPLETED
                except Exception as e:
                    sig.market_context = None
                    market_status = StageStatus.SKIPPED
                    market_output = {"reason": str(e)}

            # Rescore impact with market context
            self.impact_scorer.score(sig, in_place=True)
        self._set_stage_completed(
            run, 
            "market_context", 
            output=market_output, 
            status=market_status
        )

        # 10. Portfolio Stress Engine Stage
        self._set_stage_running(run, "portfolio_stress")
        stress_results = []
        for sig in canonical_signals:
            res = self.stress_engine.run_signal(sig)
            stress_results.append(res)
        self._set_stage_completed(
            run, 
            "portfolio_stress", 
            output={"stress_scenarios": len(stress_results)}
        )

        # Final Run Output
        run.final_result = {
            "signals": [s.to_dict() for s in canonical_signals],
            "stress_results": [r.model_dump(mode="json") for r in stress_results]
        }
