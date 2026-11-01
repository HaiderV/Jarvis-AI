import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from main import app
from app.stt.service import get_stt_service

@pytest.fixture
def client():
    return TestClient(app)

def test_stt_service_ready():
    service = get_stt_service()
    assert service.is_ready is True
    assert service.recognizer is not None

def test_health_endpoint_offline_ready(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["stt"] == "ready"

def test_stt_transcribe_wav(client):
    wav_path = Path("data/models/sherpa-onnx-streaming-zipformer-en-2023-06-26/test_wavs/0.wav")
    if not wav_path.exists():
        pytest.skip("Test wav not present")
    
    with open(wav_path, "rb") as f:
        audio_bytes = f.read()

    response = client.post("/api/stt/transcribe", content=audio_bytes)
    assert response.status_code == 200
    data = response.json()
    assert "text" in data
    assert len(data["text"]) > 0
    assert "NIGHTFALL" in data["text"].upper()
