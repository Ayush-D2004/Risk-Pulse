import pytest
import asyncio
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from src.dashboard.api import app, gdelt_service, runtime_store
from src.integration.runtime_models import RunStatus, RunMode, ObservationSource
from src.integration.observation_adapter import adapt_gdelt_to_run_request
from src.ingestion.models import NewsDocument

# Mock data
MOCK_RAW_ARTICLES = [
    {
        "url": "http://example.com/apple-news",
        "title": "Apple announces new iPhone",
        "domain": "example.com",
        "seendate": "20231015093000Z",
        "language": "English",
        "sourcecountry": "US"
    },
    {
        "url": "http://example.com/tesla-news",
        "title": "Tesla stocks rise",
        "domain": "example.com",
        "seendate": "20231015103000Z",
        "language": "English",
        "sourcecountry": "US"
    }
]

@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client

def test_gdelt_news_document_to_observation_input():
    # 1. GDELT NewsDocument -> ObservationInput
    # 2. Provenance is LIVE_GDELT + GDELT
    
    doc = NewsDocument(
        document_id="doc1",
        source="GDELT",
        publisher="example.com",
        title="Breaking News",
        body="Some body text",
        url="http://example.com/1",
        published_at="2024-03-15T10:00:00Z",
        language="english",
    )
    
    req = adapt_gdelt_to_run_request([doc])
    
    assert req.mode == RunMode.LIVE_GDELT
    assert len(req.observations) == 1
    obs = req.observations[0]
    
    assert obs.source == ObservationSource.GDELT
    assert obs.text == "Some body text"
    assert obs.headline == "Breaking News"
    assert obs.url == "http://example.com/1"
    assert obs.author == "example.com"
    assert obs.entity is None

def test_gdelt_news_document_to_observation_input_fallback_body():
    # If body is None, text should be title
    doc = NewsDocument(
        document_id="doc2",
        source="GDELT",
        title="Only Title Available",
        url="http://example.com/2",
        published_at="2024-03-15T10:00:00Z",
        language="english",
    )
    
    req = adapt_gdelt_to_run_request([doc])
    obs = req.observations[0]
    assert obs.text == "Only Title Available"

@pytest.mark.asyncio
@patch("src.integration.gdelt_service.GDELTClient")
async def test_gdelt_integration_service_success(MockClient):
    # 3. Mocked GDELT client returns observations
    # 4. Observations reach RuntimeOrchestrator
    
    mock_client_instance = MockClient.return_value
    mock_client_instance.fetch_live.return_value = MOCK_RAW_ARTICLES
    
    # Need to manually construct normalize output since we mock it or we can just let a real client normalize it
    # We will use the real normalizer logic
    from src.ingestion.gdelt_client import GDELTClient
    real_client = GDELTClient(raw_dir="tests/tmp", processed_dir="tests/tmp")
    normalized_docs = real_client.normalize(MOCK_RAW_ARTICLES)
    mock_client_instance.normalize.return_value = normalized_docs

    from src.integration.gdelt_service import GDELTIntegrationService
    from src.integration.runtime import RuntimeOrchestrator
    
    mock_orchestrator = MagicMock(spec=RuntimeOrchestrator)
    # create_task needs an awaitable
    async def mock_process(run):
        run.status = RunStatus.COMPLETED
    mock_orchestrator.process_run.side_effect = mock_process
    
    from src.integration.runtime_store import RuntimeStore
    store = RuntimeStore()
    
    service = GDELTIntegrationService(orchestrator=mock_orchestrator, store=store, gdelt_client=mock_client_instance)
    
    result = service.submit_search("Apple")
    
    assert "run_id" in result
    assert result["count"] == 2
    
    run = store.get_run(result["run_id"])
    assert run is not None
    assert run.request.mode == RunMode.LIVE_GDELT
    assert len(run.request.observations) == 2
    
    mock_orchestrator.process_run.assert_called_once_with(run)

@patch("src.integration.gdelt_service.GDELTClient")
def test_gdelt_integration_service_empty(MockClient):
    # 6. Empty GDELT result handled correctly
    mock_client_instance = MockClient.return_value
    mock_client_instance.fetch_live.return_value = []
    
    from src.integration.gdelt_service import GDELTIntegrationService
    from src.integration.runtime_store import RuntimeStore
    store = RuntimeStore()
    
    service = GDELTIntegrationService(orchestrator=MagicMock(), store=store, gdelt_client=mock_client_instance)
    
    result = service.submit_search("EmptyQuery")
    assert "error" in result
    assert result["error"] == "Empty result set from GDELT."

@patch("src.integration.gdelt_service.GDELTClient")
def test_gdelt_integration_service_malformed_handled(MockClient):
    # 7. Malformed document handled correctly
    # If GDELT API returns garbage that normalize drops, making the list empty
    
    mock_client_instance = MockClient.return_value
    mock_client_instance.fetch_live.return_value = [{"url": "http://missing-date.com"}] # Missing date, will be dropped
    
    from src.ingestion.gdelt_client import GDELTClient
    real_client = GDELTClient(raw_dir="tests/tmp", processed_dir="tests/tmp")
    mock_client_instance.normalize.side_effect = real_client.normalize
    
    from src.integration.gdelt_service import GDELTIntegrationService
    from src.integration.runtime_store import RuntimeStore
    store = RuntimeStore()
    
    service = GDELTIntegrationService(orchestrator=MagicMock(), store=store, gdelt_client=mock_client_instance)
    
    result = service.submit_search("Malformed")
    assert "error" in result
    assert result["error"] == "No valid articles after normalization."

@patch("src.integration.gdelt_service.GDELTClient")
def test_gdelt_integration_service_api_failure(MockClient):
    # 5. Runtime failure propagates correctly (e.g. timeout)
    mock_client_instance = MockClient.return_value
    mock_client_instance.fetch_live.side_effect = Exception("HTTP 504 Timeout")
    
    from src.integration.gdelt_service import GDELTIntegrationService
    from src.integration.runtime_store import RuntimeStore
    store = RuntimeStore()
    
    service = GDELTIntegrationService(orchestrator=MagicMock(), store=store, gdelt_client=mock_client_instance)
    
    result = service.submit_search("TimeoutQuery")
    assert "error" in result
    assert "GDELT integration failure" in result["error"]
    assert "Timeout" in result["error"]

def test_api_endpoint_contract(client, monkeypatch):
    # 8. API endpoint contract
    # We will mock the gdelt_service in the API module
    
    class MockService:
        def submit_search(self, query, max_records):
            if query == "Bad":
                return {"error": "Mocked Error"}
            return {"run_id": "mock_run_id", "status": "RUNNING", "count": 5}
            
    import src.dashboard.api as api
    monkeypatch.setattr(api, "gdelt_service", MockService())
    
    # Success case
    resp = client.post("/api/intelligence/gdelt/search", json={"query": "Apple", "max_records": 10})
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "mock_run_id"
    assert data["count"] == 5
    
    # Error case
    resp_err = client.post("/api/intelligence/gdelt/search", json={"query": "Bad"})
    assert resp_err.status_code == 400
    assert resp_err.json()["detail"] == "Mocked Error"
