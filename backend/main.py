import io
import json
import wave
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, status, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import numpy as np

from app.agent.service import process_message, process_message_stream
from app.database import repository
from fastapi.responses import StreamingResponse
from app.stt.service import get_stt_service

logger = logging.getLogger("jarvis.api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-ensure offline STT model is downloaded and extracted on first run
    try:
        from download_stt_model import ensure_model
        ensure_model()
    except Exception as e:
        logger.warning(f"Could not auto-ensure STT model: {e}")

    # Initialize offline STT model once on startup
    stt = get_stt_service()
    if stt.is_ready:
        print("[Jarvis] Offline Sherpa-ONNX Zipformer STT engine loaded and ready.")
    else:
        print("[Jarvis] WARNING: Offline STT model not loaded. Check data/models path.")
    yield

app = FastAPI(title="Jarvis API", version="1.0.0", lifespan=lifespan)

# CORS configuration for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str = Field(..., description="User message to send to Jarvis")
    conversation_id: Optional[str] = Field(None, description="Optional conversation ID")

class ChatResponse(BaseModel):
    reply: str
    conversation_id: str

@app.get("/")
async def root():
    return {"message": "Jarvis API is running"}

@app.get("/api/health")
async def health_check():
    from app.llm.ollama_client import get_ollama_http_client, OLLAMA_BASE_URL
    ollama_status = "disconnected"
    try:
        client = get_ollama_http_client()
        res = await client.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2.0)
        if res.status_code == 200:
            ollama_status = "connected"
    except Exception:
        pass

    stt = get_stt_service()
    stt_status = "ready" if stt.is_ready else "not_configured"

    return {
        "status": "ok",
        "ollama": ollama_status,
        "stt": stt_status,
        "offline_ready": (ollama_status == "connected" and stt_status == "ready")
    }

@app.websocket("/api/stt/stream")
async def websocket_stt_stream(websocket: WebSocket):
    await websocket.accept()
    stt_service = get_stt_service()
    if not stt_service.is_ready:
        await websocket.send_json({"error": "STT model not loaded on server."})
        await websocket.close()
        return

    stream = stt_service.create_stream()
    last_sent_text = ""

    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message and message["bytes"]:
                pcm_data = message["bytes"]
                text, is_endpoint = stt_service.accept_pcm16_chunk(stream, pcm_data)
                
                # Emit update whenever new text is transcribed or endpoint triggered
                if text != last_sent_text or is_endpoint:
                    last_sent_text = text
                    await websocket.send_json({
                        "text": text,
                        "is_final": is_endpoint,
                        "endpoint": is_endpoint
                    })
                    if is_endpoint:
                        stt_service.reset_stream(stream)
                        last_sent_text = ""
            elif "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                    action = payload.get("action")
                    if action == "finish":
                        final_text = stt_service.get_final_result(stream)
                        await websocket.send_json({
                            "text": final_text,
                            "is_final": True,
                            "endpoint": False
                        })
                        stt_service.reset_stream(stream)
                        last_sent_text = ""
                    elif action == "reset":
                        stt_service.reset_stream(stream)
                        last_sent_text = ""
                except Exception:
                    pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WebSocket STT error: {e}")

@app.post("/api/stt/transcribe")
async def transcribe_audio_endpoint(request: Request):
    """Fallback / Testing HTTP endpoint to transcribe raw PCM or WAV audio bytes."""
    stt_service = get_stt_service()
    if not stt_service.is_ready:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="STT model not loaded")

    audio_bytes = await request.body()
    if not audio_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty audio payload")

    # If WAV file, extract raw PCM
    sample_rate = 16000
    if audio_bytes.startswith(b"RIFF"):
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                sample_rate = wf.getframerate()
                pcm_data = wf.readframes(wf.getnframes())
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid WAV data: {e}")
    else:
        pcm_data = audio_bytes

    stream = stt_service.create_stream()
    samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
    stream.accept_waveform(sample_rate, samples)
    while stt_service.recognizer.is_ready(stream):
        stt_service.recognizer.decode_stream(stream)

    text = stt_service.get_final_result(stream)
    return {"text": text}

@app.post("/tts")
async def tts_endpoint():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Backend neural TTS is not configured. Jarvis frontend uses the browser Web Speech API."
    )

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        result = await process_message(
            user_message=request.message, 
            conversation_id=request.conversation_id
        )
        return ChatResponse(
            reply=result["reply"], 
            conversation_id=result["conversation_id"]
        )
    except ValueError as e:
        err_msg = str(e)
        if "does not exist" in err_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal server error occurred.")

@app.get("/api/conversations")
async def get_conversations():
    try:
        return repository.list_conversations()
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve conversations.")

@app.get("/api/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str):
    try:
        return repository.get_messages(conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve messages.")

@app.post("/api/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    return StreamingResponse(
        process_message_stream(request.message, request.conversation_id),
        media_type="text/event-stream"
    )