from typing import Dict, List, Optional
from .runtime_models import PipelineRun, RunStatus

class RuntimeStore:
    def __init__(self):
        self._runs: Dict[str, PipelineRun] = {}

    def add_run(self, run: PipelineRun):
        self._runs[run.run_id] = run
        
    def get_run(self, run_id: str) -> Optional[PipelineRun]:
        return self._runs.get(run_id)
        
    def get_all_runs(self) -> List[PipelineRun]:
        return list(self._runs.values())
        
    def get_active_runs(self) -> List[PipelineRun]:
        return [r for r in self._runs.values() if r.status in (RunStatus.PENDING, RunStatus.RUNNING)]
