/**
 * stt.ts — Fully Local Offline Speech-to-Text Client
 * Streams 16kHz PCM audio from microphone to FastAPI Sherpa-ONNX WebSocket.
 */

const WS_BASE_URL = import.meta.env.VITE_STT_WS_URL || 'ws://127.0.0.1:8000/api/stt/stream';

export interface LocalSTTCallbacks {
  onTranscript: (text: string, isFinal: boolean) => void;
  onStateChange: (isListening: boolean) => void;
  onError: (error: string) => void;
}

export class LocalSpeechRecognition {
  private ws: WebSocket | null = null;
  private audioContext: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private processor: ScriptProcessorNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private isListening = false;
  private callbacks: LocalSTTCallbacks;
  private pendingFinal = false;

  constructor(callbacks: LocalSTTCallbacks) {
    this.callbacks = callbacks;
  }

  public get active(): boolean {
    return this.isListening;
  }

  public async start(): Promise<void> {
    if (this.isListening) return;

    try {
      // 1. Request microphone permission
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: false, // Prevents aggressive clipping of word-initial consonants ("T", "N", "H")
          autoGainControl: true,
        },
      });

      // 2. Open WebSocket connection to local Sherpa-ONNX STT backend
      const wsUrl = WS_BASE_URL.startsWith('ws')
        ? WS_BASE_URL
        : `ws://${window.location.hostname}:8000/api/stt/stream`;

      this.ws = new WebSocket(wsUrl);
      this.ws.binaryType = 'arraybuffer';

      this.ws.onopen = () => {
        this.isListening = true;
        this.pendingFinal = false;
        this.callbacks.onStateChange(true);
        this.setupAudioPipeline();
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.error) {
            this.callbacks.onError(data.error);
            this.stop();
            return;
          }
          if (data.text !== undefined) {
            const isFinal = Boolean(data.is_final);
            this.callbacks.onTranscript(data.text, isFinal);
            if (isFinal) {
              this.pendingFinal = true;
              this.stop();
            }
          }
        } catch {
          // ignore non-json messages
        }
      };

      this.ws.onerror = () => {
        this.callbacks.onError('Local STT server connection failed. Ensure backend is running.');
        this.stop();
      };

      this.ws.onclose = () => {
        if (this.isListening) {
          this.stop();
        }
      };
    } catch (err: unknown) {
      this.stop();
      if (err instanceof DOMException && err.name === 'NotAllowedError') {
        this.callbacks.onError('Microphone permission denied.');
      } else {
        const msg = err instanceof Error ? err.message : 'Failed to access microphone.';
        this.callbacks.onError(msg);
      }
    }
  }

  private filterNode: BiquadFilterNode | null = null;
  private resampleOffset = 0;

  private setupAudioPipeline(): void {
    if (!this.mediaStream) return;

    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    // Pass sampleRate 16000 to trigger browser-native C++ polyphase sinc downsampling
    try {
      this.audioContext = new AudioCtx({ sampleRate: 16000 });
    } catch {
      this.audioContext = new AudioCtx();
    }
    const sampleRate = this.audioContext.sampleRate;
    this.resampleOffset = 0;

    this.source = this.audioContext.createMediaStreamSource(this.mediaStream);

    // Anti-aliasing low-pass filter: removes frequencies above Nyquist (8000 Hz) before downsampling
    this.filterNode = this.audioContext.createBiquadFilter();
    this.filterNode.type = 'lowpass';
    this.filterNode.frequency.value = 7500;
    this.filterNode.Q.value = 0.707; // Butterworth characteristic

    // Buffer size 4096 offers ~85ms buffer at 48kHz, optimal for streaming
    this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);

    this.processor.onaudioprocess = (e) => {
      if (!this.isListening || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;

      const inputFloats = e.inputBuffer.getChannelData(0);
      const pcm16 = this.downsampleTo16k(inputFloats, sampleRate);
      if (pcm16.length > 0) {
        this.ws.send(pcm16.buffer as ArrayBuffer);
      }
    };

    this.source.connect(this.filterNode);
    this.filterNode.connect(this.processor);
    this.processor.connect(this.audioContext.destination);
  }

  private downsampleTo16k(input: Float32Array, inputRate: number): Int16Array {
    if (Math.abs(inputRate - 16000) < 10) {
      const output = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        output[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      return output;
    }

    const ratio = inputRate / 16000;
    const outputSamples: number[] = [];
    let idx = this.resampleOffset;

    while (idx < input.length - 1) {
      const i0 = Math.floor(idx);
      const i1 = i0 + 1;
      const frac = idx - i0;
      // High-quality linear interpolation between samples
      const sample = (1 - frac) * input[i0] + frac * input[i1];
      const s = Math.max(-1, Math.min(1, sample));
      outputSamples.push(s < 0 ? s * 0x8000 : s * 0x7fff);
      idx += ratio;
    }

    // Preserve phase offset into next chunk to eliminate buffer boundary pops/clicks
    this.resampleOffset = idx - (input.length - 1);
    return new Int16Array(outputSamples);
  }

  public stop(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN && !this.pendingFinal) {
      try {
        this.ws.send(JSON.stringify({ action: 'finish' }));
      } catch {
        // ws might already be closing
      }
    }

    if (this.processor) {
      try {
        this.processor.disconnect();
      } catch {}
      this.processor = null;
    }

    if (this.source) {
      try {
        this.source.disconnect();
      } catch {}
      this.source = null;
    }

    if (this.filterNode) {
      try {
        this.filterNode.disconnect();
      } catch {}
      this.filterNode = null;
    }

    if (this.audioContext && this.audioContext.state !== 'closed') {
      try {
        this.audioContext.close();
      } catch {}
      this.audioContext = null;
    }

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
      this.mediaStream = null;
    }

    if (this.ws) {
      try {
        this.ws.close();
      } catch {}
      this.ws = null;
    }

    if (this.isListening) {
      this.isListening = false;
      this.callbacks.onStateChange(false);
    }
  }
}
