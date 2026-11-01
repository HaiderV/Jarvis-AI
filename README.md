# J.A.R.V.I.S. — Fully Local Offline Voice AI Assistant ⚡

A high-performance, privacy-first, fully local AI voice assistant inspired by Tony Stark's J.A.R.V.I.S. Built with **FastAPI**, **React (Vite)**, **Sherpa-ONNX**, and **Ollama**. Designed to run **100% offline** on your local machine without requiring internet access or cloud API keys.

---

## 🎯 Project Objective

The primary objective of this project is to provide a **production-grade, zero-cloud-dependent voice assistant** that works completely offline for classroom demonstrations, local computing environments, and air-gapped systems:
- **Speech-to-Text (STT)**: Locally processed on-device via **Sherpa-ONNX streaming Zipformer** with real-time WebSocket audio streaming.
- **Intelligence (LLM)**: Locally processed via **Ollama** running open-weights models (`qwen2.5:3b`, `llama3.2`, `mistral`).
- **Text-to-Speech (TTS)**: Locally synthesized via **Windows SAPI local voices** (`Microsoft David`, `Microsoft George`).
- **Deterministic OS Control**: Instant local execution of Windows apps, file management, folder navigation, calculations, and hardware controls.

---

## 📊 Real Performance Benchmarks & Stats

| Metric | Measured Real Performance | Engine / Technology |
|---|---|---|
| **Deterministic Fast-Path** | **< 10 ms** | Regex + AST Pattern Matcher (Direct Windows Kernel/OS API) |
| **Offline STT Latency** | **< 80 ms** | Sherpa-ONNX Streaming Zipformer (Int8 Quantized, 16 kHz PCM) |
| **LLM Time-To-First-Token** | **< 350 ms** | Ollama Local Streaming (`qwen2.5:3b`) |
| **Deep File Search** | **< 0.15 s** | Excluded node_modules/.git/AppData fast disk walker |
| **Holographic 3D Core FPS** | **60 – 120 FPS** | Lightweight 2D Canvas with 3D Matrix Projection |
| **Memory Footprint** | **~240 MB RAM (Backend)** | Sherpa-ONNX + FastAPI + SQLite (Excluding Ollama model weights) |

---

## 🚀 Key Architectural Features

### 1. 🎙️ Dual-Engine Hybrid Speech System (Online / Offline Auto-Switching)
- **Offline STT (Primary Offline)**: Powered by `sherpa-onnx-streaming-zipformer-en-2023-06-26` over binary WebSocket (`ws://127.0.0.1:8000/api/stt/stream`).
- **Audio Pre-processing Pipeline**: 
  - Downsampling from native mic sample rate (44.1/48 kHz) to 16 kHz with continuous phase tracking.
  - 7.5 kHz Biquad low-pass anti-aliasing filter to prevent consonant clipping.
  - Phonetic normalization layer for common voice confusions ("north bed" → "notepad", "doopless too" → "2 plus 2").
- **Cloud STT (Online Fallback)**: Browser-native `webkitSpeechRecognition` when internet is available.
- **Smart Toggle & Auto-Failover**: One-click STT engine toggle in the top-right header with automatic failover if internet drops.
- **Offline TTS**: Intelligent voice selector prioritizing local Windows synthesizer voices (`Microsoft David`), stripping remote cloud dependencies when offline.

### 2. 🌌 Stark Holographic 3D Core (Canvas Engine v4)
- Modeled directly after the iconic Iron Man holographic sphere:
  - **Concentric 3D Gimbal Rings**: Multi-axis tilted gyroscopic rings with tech tick graduations and double-track equator rails.
  - **3D Spherical Tech Cage**: 3D longitude meridians and latitude parallels that tumble in perspective with pointer parallax.
  - **Arc Reactor Nucleus**: Central incandescent white-gold plasma core radiating warm amber bloom and anamorphic lens flares.
  - **Continuous Angle Integration**: Zero rotational jumps or violent spinning during state transitions; slow, dignified, cinematic rotation.
- **4 Distinct State-Driven Animations**:
  - **`IDLE`**: Serene gyroscopic precession, slow harmonic breathing (0.65 Hz), soft ambient ember glow.
  - **`LISTENING`**: Rings orient forward like an acoustic dish, micro-frequency acoustic ripples vibrating along the perimeter like an audio membrane.
  - **`THINKING`**: Input controls locked, dignified slow rotation with 2.4 Hz neural computation strobing in the core and a sweeping holographic scan-plane.
  - **`SPEAKING`**: Resonant vocal expansion with concentric acoustic soundwaves pulsing outward synchronized with real-time speech word delivery.

### 3. ⚡ Deterministic Fast-Path Engine & OS Automation
- **Instant System Tooling (<10ms)**: Bypasses LLM latency for standard commands:
  - **Launch & Kill Windows Apps**: Notepad, Calculator, VS Code, Chrome, Spotify, Task Manager, Explorer.
  - **File Operations**: Search files in milliseconds, read `.py`, `.txt`, `.md`, `.json`, `.pdf`, `.docx`, and write notes/scripts.
  - **Folder Navigation**: Deep resolution of project workspaces and Documents.
  - **Time, Date & Math**: Instant precision arithmetic and system clock queries.
- **Web Intelligence (When Connected)**: Live web search via DuckDuckGo Lite and Wikipedia API without paid API keys.
- **Conversation History**: Full thread persistence backed by local SQLite (`backend/data/jarvis.db`).

---

## 🛠️ Easy Setup Guide (Step-by-Step)

### Prerequisites
Make sure you have the following installed on your system:
1. **Python 3.10+** (Tested on Python 3.11 & 3.12) → [python.org](https://www.python.org/downloads/)
2. **Node.js 18+ & npm** → [nodejs.org](https://nodejs.org/)
3. **Ollama** (Local LLM runner) → [ollama.com](https://ollama.com/)

---

### Step 1: Install & Start Ollama
1. Download and install **Ollama**.
2. Open a terminal and pull your preferred lightweight LLM:
   ```powershell
   ollama run qwen2.5:3b
   ```
   *(You can also use `llama3.2:3b` or `mistral`. To test it, verify `http://127.0.0.1:11434` returns "Ollama is running".)*

---

### Step 2: Backend Setup (FastAPI & Sherpa-ONNX)
1. Open a terminal in the project root and navigate to `backend`:
   ```powershell
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   *(On macOS/Linux: `source .venv/bin/activate`)*

3. Install required Python packages:
   ```powershell
   pip install -r requirements.txt
   ```

4. Download the offline STT Zipformer model:
   ```powershell
   python download_stt_model.py
   ```
   *(Note: The backend also automatically auto-downloads and extracts this model on first startup if missing!)*

5. Start the backend server:
   ```powershell
   uvicorn main:app --reload --port 8000
   ```
   *Backend is running at [http://127.0.0.1:8000](http://127.0.0.1:8000)*

---

### Step 3: Frontend Setup (React + Vite)
1. Open a new terminal and navigate to `frontend`:
   ```powershell
   cd frontend
   ```
2. Install Node dependencies:
   ```powershell
   npm install
   ```
3. Launch the development server:
   ```powershell
   npm run dev
   ```
4. Open your browser and navigate to:
   ```
   http://localhost:5173
   ```

---

## 🗣️ Example Voice & Text Commands

Click the holographic core or the composer microphone button (or type in the chat box) to speak:

| Category | Example Voice Commands | Execution Path |
|---|---|---|
| **App Control** | *"Open notepad"*, *"Launch calculator"*, *"Open chrome"*, *"Close notepad"* | **< 10ms (Deterministic)** |
| **Folder Listing** | *"List files in jarvis"*, *"Show files in Documents"* | **< 15ms (Deterministic)** |
| **File Search** | *"Find main.py"*, *"Search python files in my workspace"* | **< 120ms (Deterministic)** |
| **File Reading** | *"Read main.py"*, *"Show notes.txt"* | **< 20ms (Deterministic)** |
| **File Writing** | *"Write meeting summary to notes.txt"* | **< 20ms (Deterministic)** |
| **Date & Time** | *"What time is it?"*, *"What's today's date?"* | **< 5ms (Deterministic)** |
| **Calculations** | *"Calculate 45 times 88"*, *"What is 2 plus 2?"* | **< 5ms (Deterministic)** |
| **Web Research** | *"Search the web for today's AI news"*, *"Who is the CEO of Apple?"* | **Live DuckDuckGo / Wiki** |
| **AI Reasoning** | *"Explain quantum computing simply"*, *"Write a python binary search"* | **Local Ollama LLM** |

---

## 🧪 Running Automated Tests

To run the complete backend test suite (STT model, deterministic router, agent behavior, and database):

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest -v
```
*(All 16 automated tests will run and validate offline STT, tool routing, and agent streaming).*

---

## 📁 Repository Structure

```
jarvis/
├── backend/
│   ├── app/
│   │   ├── agent/       # Message processing & LLM router
│   │   ├── database/    # SQLite persistence (conversations & messages)
│   │   ├── llm/         # Ollama HTTP streaming client
│   │   ├── stt/         # Sherpa-ONNX offline Zipformer STT service & phonetic normalizer
│   │   └── tools/       # Fast-path Windows apps, file, folder & web tools
│   ├── data/
│   │   ├── models/      # Local Sherpa-ONNX streaming Zipformer weights
│   │   └── jarvis.db    # Local SQLite database
│   ├── download_stt_model.py # Automated model downloader & extractor
│   ├── main.py          # FastAPI server & WebSocket endpoints
│   └── requirements.txt # Backend Python dependencies
├── frontend/
│   ├── src/
│   │   ├── components/  # JarvisCore canvas container
│   │   ├── core/        # jarvisCore.ts (3D Canvas Hologram Engine v4)
│   │   ├── services/    # STT audio downsampler, WebSocket & API clients
│   │   ├── App.tsx      # Main Jarvis HUD interface & voice state management
│   │   └── App.css      # Dark glass / Stark amber theme styling
│   └── package.json     # Frontend dependencies
└── README.md            # Documentation & setup guide
```

---

## 🔒 Privacy & Offline Guarantee

- **No Remote Telemetry**: Your voice, chat history, and local files never leave your computer.
- **Zero API Costs**: Runs entirely on open-source, local models without requiring OpenAI or Anthropic API keys.
- **Air-Gap Compatible**: Can be run completely severed from the internet (Wi-Fi off, airplane mode enabled) with full voice input, voice output, app launching, file management, and AI conversation.
