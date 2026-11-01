import os
import re
import sys
import logging
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import sherpa_onnx

logger = logging.getLogger("jarvis.stt")

# Default model directory relative to backend root
DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "models" / "sherpa-onnx-streaming-zipformer-en-2023-06-26"

def normalize_voice_command(text: str) -> str:
    """
    Normalizes common phonetic confusions and joins/splits for voice assistant commands.
    """
    if not text:
        return ""
    t = " " + text.strip() + " "
    
    # 1. Jarvis wake words / greetings
    t = re.sub(r"(?i)\bhello\s*(?:javish|jarves|jarvus|javis|charvis)\b", "hello jarvis", t)
    t = re.sub(r"(?i)\bhello(?:javish|jarves|jarvus|javis|charvis)\b", "hello jarvis", t)
    t = re.sub(r"(?i)\b(?:javish|jarves|jarvus|javis|charvis)\b", "jarvis", t)
    
    # 2. Notepad launcher
    t = re.sub(r"(?i)\b(?:north\s*bed|note\s*bed|not\s*bad|node\s*pad)\b", "notepad", t)
    
    # 3. 2 plus 2 / math confusions
    t = re.sub(r"(?i)\b(?:doopless|do\s*plus|to\s*plus|too\s*plus)\s*(?:too|to|two)\b", "2 plus 2", t)
    t = re.sub(r"(?i)\btwo\s*plus\s*two\b", "2 plus 2", t)
    t = re.sub(r"(?i)\bdoopless\b", "2 plus", t)
    
    # 4. Calculator
    t = re.sub(r"(?i)\b(?:calculater|calculatur)\b", "calculator", t)
    
    t = re.sub(r"\s+", " ", t)
    return t.strip()

class SherpaSTTService:
    _instance: Optional["SherpaSTTService"] = None

    def __init__(self, model_dir: Optional[Path] = None):
        self.model_dir = model_dir or DEFAULT_MODEL_DIR
        self.recognizer: Optional[sherpa_onnx.OnlineRecognizer] = None
        self.is_ready = False
        self._init_recognizer()

    def _init_recognizer(self):
        tokens = self.model_dir / "tokens.txt"
        encoder_int8 = self.model_dir / "encoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx"
        encoder = encoder_int8 if encoder_int8.exists() else self.model_dir / "encoder-epoch-99-avg-1-chunk-16-left-128.onnx"
        
        decoder_int8 = self.model_dir / "decoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx"
        decoder = decoder_int8 if decoder_int8.exists() else self.model_dir / "decoder-epoch-99-avg-1-chunk-16-left-128.onnx"
        
        joiner_int8 = self.model_dir / "joiner-epoch-99-avg-1-chunk-16-left-128.int8.onnx"
        joiner = joiner_int8 if joiner_int8.exists() else self.model_dir / "joiner-epoch-99-avg-1-chunk-16-left-128.onnx"

        if not (tokens.exists() and encoder.exists() and decoder.exists() and joiner.exists()):
            logger.warning(f"Sherpa-ONNX model files not found in {self.model_dir}. Offline STT will be unavailable until downloaded.")
            self.is_ready = False
            return

        logger.info(f"Loading Sherpa-ONNX Streaming Zipformer from {self.model_dir}...")
        self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(tokens),
            encoder=str(encoder),
            decoder=str(decoder),
            joiner=str(joiner),
            num_threads=min(4, max(1, (os.cpu_count() or 4) // 2)),
            sample_rate=16000,
            feature_dim=80,
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=1.8, # Silence after speech segment
            rule2_min_trailing_silence=1.0, # Silence after long speech segment
            rule3_min_utterance_length=20.0,
            decoding_method="modified_beam_search",
            max_active_paths=4,
            provider="cpu"
        )
        self.is_ready = True
        logger.info("Sherpa-ONNX Streaming Zipformer initialized successfully and ready for offline recognition.")

    def create_stream(self) -> sherpa_onnx.OnlineStream:
        if not self.is_ready or not self.recognizer:
            raise RuntimeError("Sherpa-ONNX STT recognizer is not initialized.")
        return self.recognizer.create_stream()

    def accept_pcm16_chunk(
        self,
        stream: sherpa_onnx.OnlineStream,
        pcm_bytes: bytes,
        sample_rate: int = 16000
    ) -> Tuple[str, bool]:
        """
        Accepts raw PCM 16-bit mono audio chunk.
        Returns (current_text, is_endpoint).
        """
        if not self.is_ready or not self.recognizer:
            return "", False

        if not pcm_bytes:
            raw_text = self.recognizer.get_result(stream).strip()
            return normalize_voice_command(raw_text), False

        # Convert int16 PCM buffer to float32 normalized samples [-1.0, 1.0]
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        stream.accept_waveform(sample_rate, samples)

        while self.recognizer.is_ready(stream):
            self.recognizer.decode_stream(stream)

        is_endpoint = self.recognizer.is_endpoint(stream)
        raw_text = self.recognizer.get_result(stream).strip()
        text = normalize_voice_command(raw_text)

        return text, is_endpoint

    def get_final_result(self, stream: sherpa_onnx.OnlineStream) -> str:
        """
        Retrieves final recognized text from the stream.
        """
        if not self.is_ready or not self.recognizer:
            return ""
        raw_text = self.recognizer.get_result(stream).strip()
        return normalize_voice_command(raw_text)

    def reset_stream(self, stream: sherpa_onnx.OnlineStream):
        if self.recognizer and stream:
            self.recognizer.reset(stream)

def get_stt_service() -> SherpaSTTService:
    if SherpaSTTService._instance is None:
        SherpaSTTService._instance = SherpaSTTService()
    return SherpaSTTService._instance
