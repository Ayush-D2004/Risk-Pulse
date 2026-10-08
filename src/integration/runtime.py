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
        
        try:
            await asyncio.to_thread(self._execute_pipeline, run)
            run.status = RunStatus.COMPLETED
        except Exception as e:
            run.status = RunStatus.FAILED
            run.error = str(e)
            
        run.completed_at = datetime.now(timezone.utc)

    def _execute_pipeline(self, run: PipelineRun):
        req = run.request
        observations = req.observations
        mode = req.mode
        
        # ingestion
        stage_ingest = PipelineStage(name="ingestion", status=StageStatus.RUNNING, started_at=datetime.now(timezone.utc))
        run.stages.append(stage_ingest)
        stage_ingest.output = {"count": len(observations), "mode": mode.value}
        stage_ingest.status = StageStatus.COMPLETED
        stage_ingest.completed_at = datetime.now(timezone.utc)
        
        # preprocessing
        stage_pre = PipelineStage(name="preprocessing", status=StageStatus.RUNNING, started_at=datetime.now(timezone.utc))
        run.stages.append(stage_pre)
        valid_obs = []
        for obs in observations:
            if obs.text.strip():
                valid_obs.append(obs)
        stage_pre.output = {"valid_count": len(valid_obs)}
        stage_pre.status = StageStatus.COMPLETED
        stage_pre.completed_at = datetime.now(timezone.utc)
        
        signals = []
        for obs in valid_obs:
            text = obs.text
            raw_entity = obs.entity or "UNKNOWN"
            
            with self.inference_lock:
                # entity_resolution
                norm_res = self.entity_normalizer.normalize(raw_entity)
                canonical_entity = norm_res["canonical_entity"]
                if not canonical_entity:
                    canonical_entity = f"UNRESOLVED_{norm_res['candidate_entity']}" if norm_res["candidate_entity"] else "UNRESOLVED_UNKNOWN"
                
                # sentiment
                fb_df = self.finbert.predict([text], batch_size=1)
                fb_res = fb_df.iloc[0]
                sentiment_score = float(fb_res["FINBERT_SCORE"])
                
                # event_classification
                rel_results = classify_batch(self.event_classifier, [text], RELEVANCE_DESCRIPTIONS, "This text is about {}.", batch_size=1)
                top_rel_label = rel_results[0]["labels"][0]
                rel_score = float(rel_results[0]["scores"][0])
                
                relevance = "FINANCIAL_EVENT" if top_rel_label == RELEVANCE_DESCRIPTIONS[0] else "NO_MATERIAL_EVENT"
                
                event_type = "NO_EVENT"
                event_conf = 0.0
                
                if relevance == "FINANCIAL_EVENT":
                    ev_results = classify_batch(self.event_classifier, [text], EVENT_DESCRIPTIONS, "This text describes {}.", batch_size=1)
                    top_ev_desc = ev_results[0]["labels"][0]
                    event_conf = float(ev_results[0]["scores"][0])
                    label_index = EVENT_DESCRIPTIONS.index(top_ev_desc)
                    event_type = EVENT_LABELS[label_index]
                    
                # materiality
                mat_label, final_event_type, mat_reason = classify_materiality(
                    text=text,
                    original_type=event_type,
                    relevance=relevance,
                    confidence=event_conf
                )
            
            sig = RiskSignal(
                event_id=run.run_id,
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
            
        stage_ent = PipelineStage(name="entity_resolution", status=StageStatus.COMPLETED, started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), output={"processed": len(signals)})
        run.stages.append(stage_ent)
        stage_sent = PipelineStage(name="sentiment", status=StageStatus.COMPLETED, started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), output={"processed": len(signals)})
        run.stages.append(stage_sent)
        stage_ev = PipelineStage(name="event_classification", status=StageStatus.COMPLETED, started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), output={"processed": len(signals)})
        run.stages.append(stage_ev)
        stage_mat = PipelineStage(name="materiality", status=StageStatus.COMPLETED, started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), output={"processed": len(signals)})
        run.stages.append(stage_mat)
        
        # impact
        stage_impact = PipelineStage(name="impact", status=StageStatus.RUNNING, started_at=datetime.now(timezone.utc))
        run.stages.append(stage_impact)
        for sig in signals:
            self.impact_scorer.score(sig, in_place=True)
        stage_impact.output = {"processed": len(signals)}
        stage_impact.status = StageStatus.COMPLETED
        stage_impact.completed_at = datetime.now(timezone.utc)
        
        # clustering
        stage_cluster = PipelineStage(name="clustering", status=StageStatus.RUNNING, started_at=datetime.now(timezone.utc))
        run.stages.append(stage_cluster)
        canonical_signals = []
        with self.inference_lock:
            for sig in signals:
                clustered_sig = self.clusterer.process_signal(sig)
                if clustered_sig not in canonical_signals:
                    canonical_signals.append(clustered_sig)
        stage_cluster.output = {"clusters_formed": len(canonical_signals)}
        stage_cluster.status = StageStatus.COMPLETED
        stage_cluster.completed_at = datetime.now(timezone.utc)
        
        # market_context
        stage_market = PipelineStage(name="market_context", status=StageStatus.RUNNING, started_at=datetime.now(timezone.utc))
        run.stages.append(stage_market)
        
        for sig in canonical_signals:
            if mode in (RunMode.LIVE_GDELT, RunMode.ANALYST_SIMULATION):
                sig.market_context = None
                stage_market.status = StageStatus.SKIPPED
                stage_market.output = {"reason": "live/simulated observations lack resolvable market context"}
            else:
                try:
                    res = self.market_fetcher.fetch(sig.entity, sig.timestamp)
                    sig.market_context = res.market_context
                    stage_market.status = StageStatus.COMPLETED
                except Exception as e:
                    sig.market_context = None
                    stage_market.status = StageStatus.SKIPPED
                    stage_market.output = {"reason": str(e)}
            
            # Rescore impact with market context
            self.impact_scorer.score(sig, in_place=True)
            
        if stage_market.status == StageStatus.RUNNING:
            stage_market.status = StageStatus.COMPLETED
        stage_market.completed_at = datetime.now(timezone.utc)
        
        # portfolio_stress
        stage_stress = PipelineStage(name="portfolio_stress", status=StageStatus.RUNNING, started_at=datetime.now(timezone.utc))
        run.stages.append(stage_stress)
        
        stress_results = []
        for sig in canonical_signals:
            res = self.stress_engine.run_signal(sig)
            stress_results.append(res)
            
        stage_stress.output = {
            "processed": len(stress_results)
        }
        stage_stress.status = StageStatus.COMPLETED
        stage_stress.completed_at = datetime.now(timezone.utc)
        
        # Final Run Output
        run.final_result = {
            "signals": [s.to_dict() for s in canonical_signals],
            "stress_results": [r.model_dump(mode="json") for r in stress_results]
        }
