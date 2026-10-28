# J.A.R.V.I.S. - Local Voice AI Assistant ⚡

A high-performance, privacy-first local AI assistant powered by **Ollama**, **FastAPI**, and **React (Vite)** with voice interaction, local file management, Windows application control, and real-time internet search.

---

## 🚀 Key Features & Optimizations

1. **🎙️ Voice Interaction (Speech-to-Text & Text-to-Speech)**
   - **Voice Input**: Integrated browser speech recognition with animated pulsing microphone.
   - **Jarvis Voice Output**: Natural spoken replies using SpeechSynthesis with mute/unmute and stop controls.
   - **Visual Audio Waves**: Real-time waveform visualizer while Jarvis is speaking.

2. **⚡ Blazing Fast Response Times (<0.1s - 3s)**
   - **Deterministic Fast-Path Engine**: Instant (<10ms) responses for common actions (apps, folder listing, file searching, file reading, file writing, time, calculations).
   - **Smart Single-Pass Streaming**: Bypasses slow multi-round tool calling by pre-fetching referenced files in 10ms and streaming directly to the client.

3. **📁 Local Files & Folder System**
   - **Excluded Heavy Dirs**: Automatically prunes `node_modules`, `.venv`, `.git`, `dist`, `build`, and `AppData` so file searches complete in **<0.2s** instead of hanging for 30+ seconds.
   - **Smart Resolver**: Deep search finds nested project folders like `jarvis` and relative files like `main.py` instantly.
   - **File Reading & Writing**: Reads `.py`, `.txt`, `.md`, `.json`, `.pdf`, `.docx` and writes notes/code.
   - **Explorer Integration**: Opens files and folders natively in Windows File Explorer.

4. **💻 Windows Application Control**
   - **Launch Apps**: `"open notepad"`, `"launch calculator"`, `"open chrome"`, `"open vscode"`, `"open spotify"`, `"open explorer"`, etc.
   - **Close Apps**: `"close notepad"`, `"kill calculator"`, `"exit chrome"`.

5. **🌐 Live Internet & Web Search**
   - Live web search powered by DuckDuckGo Lite & Wikipedia Summary API for up-to-date news, current events, and facts without requiring paid API keys.

---

## 🛠️ How to Run

### 1. Start Backend (FastAPI + Ollama)
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload --port 8000
```

### 2. Start Frontend (React + Vite)
```powershell
cd frontend
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in Chrome or Edge.

---

## 🗣️ Example Voice & Text Commands

| Action | Example Command |
|---|---|
| **Folder Contents** | *"List files in jarvis"*, *"Show files in Documents"* |
| **File Search** | *"Search for main.py"*, *"Find python files in my workspace"* |
| **Read File** | *"Read main.py"*, *"Show content of notes.txt"* |
| **Write File** | *"Write hello world to notes.txt"* |
| **Launch App** | *"Open notepad"*, *"Launch calculator"*, *"Open chrome"*, *"Open vscode"* |
| **Close App** | *"Close notepad"*, *"Kill calculator"* |
| **Web Search** | *"Search web for latest SpaceX launch"*, *"Google quantum computing"* |
| **Quick Tools** | *"What time is it?"*, *"What is today's date?"*, *"Calculate 45 * 12"* |
| **General Q&A** | *"Explain how neural networks work"*, *"Write a python function for quicksort"* |
