import os

from fastapi.testclient import TestClient


def _set_test_env() -> None:
    os.environ.setdefault("OPENAI_API_KEY", "test-openai")
    os.environ.setdefault("VAPI_API_KEY", "test-vapi")
    os.environ.setdefault("VAPI_PHONE_NUMBER_ID", "phone-id")
    os.environ.setdefault("ELEVENLABS_VOICE_ID", "voice-id")


_set_test_env()

def _build_client() -> TestClient:
    from app.main import app

    return TestClient(app)


client = _build_client()


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "env" in payload


def test_docs_route_enabled_in_development() -> None:
    response = client.get("/docs")
    assert response.status_code == 200
