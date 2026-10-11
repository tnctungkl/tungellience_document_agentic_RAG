from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.validation.schemas import AgentResponse, Citation


class FakeAgent:
    def run(self, query: str) -> AgentResponse:
        return AgentResponse(
            answer="Test answer.",
            action="retrieve",
            query=query,
            confidence=0.91,
            citations=[Citation(source="test.md", chunk_id=str(uuid4()), score=0.91)],
        )


def test_root_serves_web_ui() -> None:
    client = TestClient(create_app(FakeAgent()))
    response = client.get("/")

    assert response.status_code == 200
    assert "Tungelligence" in response.text


def test_health_endpoint() -> None:
    client = TestClient(create_app(FakeAgent()))
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_query_endpoint_returns_agent_response() -> None:
    client = TestClient(create_app(FakeAgent()))
    response = client.post("/v1/query", json={"query": "What is the policy?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "Test answer."


def test_report_endpoint_returns_pdf() -> None:
    client = TestClient(create_app(FakeAgent()))
    payload = FakeAgent().run("What is the policy?").model_dump(mode="json")
    response = client.post("/v1/report", json={"response": payload})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_report_endpoint_rejects_empty_answer() -> None:
    client = TestClient(create_app(FakeAgent()))
    payload = FakeAgent().run("What is the policy?").model_dump(mode="json")
    payload["answer"] = ""
    response = client.post("/v1/report", json={"response": payload})

    assert response.status_code == 400
