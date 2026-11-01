"""
download_stt_model.py
---------------------
Downloads and extracts the lightweight Sherpa-ONNX streaming Zipformer English model
for fully local offline speech recognition.
"""

import sys
import tarfile
import urllib.request
from pathlib import Path

MODEL_NAME = "sherpa-onnx-streaming-zipformer-en-2023-06-26"
BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "data" / "models"
TARGET_DIR = MODELS_DIR / MODEL_NAME
URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{MODEL_NAME}.tar.bz2"

def ensure_model():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    tokens_file = TARGET_DIR / "tokens.txt"
    encoder_file = TARGET_DIR / "encoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx"

    if TARGET_DIR.exists() and tokens_file.exists() and encoder_file.exists():
        print(f"[OK] Model already installed at: {TARGET_DIR}")
        return

    tar_path = MODELS_DIR / f"{MODEL_NAME}.tar.bz2"
    print(f"[1/2] Downloading {MODEL_NAME} from GitHub releases...")
    urllib.request.urlretrieve(URL, tar_path)

    print(f"[2/2] Extracting archive to {MODELS_DIR}...")
    with tarfile.open(tar_path, "r:bz2") as tar:
        tar.extractall(MODELS_DIR)

    if tar_path.exists():
        tar_path.unlink()

    print("[SUCCESS] Sherpa-ONNX offline Zipformer model installed successfully!")

if __name__ == "__main__":
    ensure_model()
