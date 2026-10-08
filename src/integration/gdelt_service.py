import asyncio
import uuid
from typing import List, Dict, Any, Optional

from src.ingestion.gdelt_client import GDELTClient
from src.integration.observation_adapter import adapt_gdelt_to_run_request
from src.integration.runtime import RuntimeOrchestrator
from src.integration.runtime_models import PipelineRun, RunStatus
from src.integration.runtime_store import RuntimeStore

class GDELTIntegrationService:
    def __init__(self, orchestrator: RuntimeOrchestrator, store: RuntimeStore, gdelt_client: Optional[GDELTClient] = None):
        self.orchestrator = orchestrator
        self.store = store
        self.gdelt_client = gdelt_client or GDELTClient()

    def submit_search(self, query: str, max_records: int = 50) -> Dict[str, Any]:
        """
        Executes a GDELT live search, normalizes the results,
        adapts them to runtime observation inputs, and submits
        a PipelineRun to the orchestrator.
        """
        try:
            # 1. Fetch from GDELT
            raw_articles = self.gdelt_client.fetch_live(query=query, max_records=max_records)
            
            if not raw_articles:
                return {"error": "Empty result set from GDELT."}
                
            # 2. Normalize to GDELT NewsDocuments
            docs = self.gdelt_client.normalize(raw_articles)
            
            if not docs:
                return {"error": "No valid articles after normalization."}
                
            # 3. Adapt to PipelineRunRequest
            req = adapt_gdelt_to_run_request(docs)
            
            # 4. Create and store run
            run_id = uuid.uuid4().hex
            run = PipelineRun(
                run_id=run_id,
                request=req,
            )
            self.store.add_run(run)
            
            # 5. Submit to orchestrator as a background task
            asyncio.create_task(self.orchestrator.process_run(run))
            
            return {"run_id": run_id, "status": run.status.value, "count": len(req.observations)}
            
        except Exception as e:
            return {"error": f"GDELT integration failure: {str(e)}"}
