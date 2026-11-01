import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  streamChatMessage,
  fetchConversations,
  fetchMessages,
  type Conversation,
  type StreamMeta,
} from './services/api';
import { JarvisCore, type JarvisCoreRef } from './components/JarvisCore';
import type { CoreState } from './core/jarvisCore';
import { LocalSpeechRecognition } from './services/stt';
import './App.css';

interface DisplayMessage {
  id: string;
  sender: 'user' | 'jarvis';
  text: string;
  pending?: boolean;
}

declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
  }
}

/* ------------------------------------------------------------------ helpers */

const SPEECH_RATE = 0.96;

/** Strip anything that reads badly out loud. */
function cleanForSpeech(raw: string): string {
  return raw
    .replace(/```[\s\S]*?```/g, ' Code block omitted. ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/https?:\/\/\S+/g, '')
    .replace(/[*#_~>|]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/* ── voice selection ─────────────────────────────────────────────── */

// To lock one exact voice, put part of its name here, e.g. 'Microsoft David' or 'Microsoft George'
const VOICE_HINT: string = '';

const MALE = /daniel|arthur|oliver|george|ryan|guy|thomas|james|david|mark|male/i;
const FEMALE = /female|zira|samantha|karen|moira|tessa|serena|fiona|susan|hazel|libby|sonia/i;

function pickVoice(isOnline: boolean = true): SpeechSynthesisVoice | undefined {
  const voices = window.speechSynthesis?.getVoices?.() ?? [];
  if (!voices.length) return undefined;

  // Cloud voices check: Google voices, Edge Online/Natural voices require internet!
  const isCloudVoice = (v: SpeechSynthesisVoice) => {
    return /google|online|natural|cloud|server/i.test(v.name);
  };

  // If offline, strictly filter OUT any cloud voice
  const candidateVoices = isOnline
    ? voices
    : voices.filter((v) => !isCloudVoice(v));

  // If offline and no local voices matched, return undefined so browser uses default OS voice
  if (!isOnline && candidateVoices.length === 0) {
    return undefined;
  }

  if (VOICE_HINT) {
    const hint = VOICE_HINT.toLowerCase();
    const exact = candidateVoices.find((v) => v.name.toLowerCase().includes(hint));
    if (exact) return exact;
  }

  const score = (v: SpeechSynthesisVoice) => {
    let s = 0;
    // Prefer English
    if (/^en-GB/i.test(v.lang)) s += 40;        // JARVIS is British RP
    else if (/^en-IN/i.test(v.lang)) s += 25;
    else if (/^en-US/i.test(v.lang)) s += 20;
    else if (/^en/i.test(v.lang)) s += 10;
    else return -1;

    // In online mode, Google UK English Male is great
    if (isOnline && /google uk english male/i.test(v.name)) s += 30;
    if (isOnline && /natural|neural/i.test(v.name)) s += 15;

    // Local Windows voices (always works offline)
    if (/george/i.test(v.name)) s += 35;
    if (/david/i.test(v.name)) s += 25;
    if (/mark/i.test(v.name)) s += 20;
    if (MALE.test(v.name)) s += 10;
    if (FEMALE.test(v.name)) s -= 20;
    return s;
  };

  const sorted = [...candidateVoices]
    .filter((v) => score(v) >= 0)
    .sort((a, b) => score(b) - score(a));

  return sorted[0] || (isOnline ? candidateVoices[0] : undefined);
}


/* ------------------------------------------------------------------- icons */

const Chevron = ({ dir }: { dir: 'left' | 'right' }) => (
  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.6">
    {dir === 'left' ? <path d="M15 5l-7 7 7 7" /> : <path d="M9 5l7 7-7 7" />}
  </svg>
);

const MicIcon = () => (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.6">
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0014 0M12 18v3" />
  </svg>
);

const SendIcon = () => (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M4 12h15M13 6l6 6-6 6" />
  </svg>
);

/* --------------------------------------------------------------------- app */

export const App: React.FC = () => {
  /* conversation */
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isConversationsLoading, setIsConversationsLoading] = useState(true);
  const [conversationsError, setConversationsError] = useState<string | null>(null);
  const [latestLatency, setLatestLatency] = useState<number | null>(null);

  /* layout */
  const [historyOpen, setHistoryOpen] = useState(true);
  const [chatOpen, setChatOpen] = useState(true);

  /* network & speech engine mode */
  const [isOnline, setIsOnline] = useState<boolean>(
    typeof navigator !== 'undefined' ? navigator.onLine : true,
  );
  const [speechMode, setSpeechMode] = useState<'auto' | 'cloud' | 'local'>('auto');

  useEffect(() => {
    const onOnline = () => {
      setIsOnline(true);
      setSpeechMode('auto');
    };
    const onOffline = () => {
      setIsOnline(false);
      setSpeechMode('local');
    };
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  const effectiveEngine: 'cloud' | 'local' = useMemo(() => {
    if (speechMode === 'cloud') return 'cloud';
    if (speechMode === 'local') return 'local';
    return isOnline ? 'cloud' : 'local';
  }, [speechMode, isOnline]);

  /* voice */
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [liveTranscript, setLiveTranscript] = useState('');

  /* subtitles */
  const [subtitleText, setSubtitleText] = useState('');
  const [revealCount, setRevealCount] = useState(0);
  const [subtitleOn, setSubtitleOn] = useState(false);

  const coreRef = useRef<JarvisCoreRef>(null);
  const idRef = useRef(0);
  const loadingRef = useRef(false);
  const localSttRef = useRef<LocalSpeechRecognition | null>(null);
  const cloudRecognitionRef = useRef<any>(null);
  const transcriptRef = useRef('');
  const sentRef = useRef(false);
  const hideTimerRef = useRef<number | null>(null);
  const msPerWordRef = useRef(90);
  const bottomRef = useRef<HTMLDivElement>(null);
  const subtitleRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  const nextId = () => `m${++idRef.current}`;
  const coreState: CoreState = isSpeaking
    ? 'speaking'
    : isListening
      ? 'listening'
      : isLoading
        ? 'thinking'
        : 'idle';

  /* ------------------------------------------------------------ scrolling */

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, isLoading]);

  useEffect(() => {
    const el = subtitleRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [revealCount]);

  useEffect(() => {
    const el = composerRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`;
  }, [input]);

  /* -------------------------------------------------------------- history */

  const loadConversationsList = useCallback(async () => {
    setIsConversationsLoading(true);
    setConversationsError(null);
    try {
      const data = await fetchConversations();
      setConversations(data);
    } catch (error: unknown) {
      setConversationsError(
        error instanceof Error ? error.message : 'Failed to load conversations.',
      );
    } finally {
      setIsConversationsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConversationsList();
  }, [loadConversationsList]);

  /* ---------------------------------------------------------------- speech */

  const clearHideTimer = () => {
    if (hideTimerRef.current) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  };

  const stopSpeaking = useCallback(() => {
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    clearHideTimer();
    setIsSpeaking(false);
    setSubtitleOn(false);
    setSubtitleText('');
    setRevealCount(0);
  }, []);

  const LOCAL_TTS = import.meta.env.VITE_TTS_URL || '';
  const LOCAL_VOICE = import.meta.env.VITE_TTS_VOICE || 'bm_george';

  const speakResponse = useCallback(
    async (raw: string) => {
      if (!voiceEnabled) return;
      const clean = cleanForSpeech(raw);
      if (!clean) return;

      const words = clean.split(/\s+/);
      msPerWordRef.current = Math.max(45, 1000 / (2.85 * SPEECH_RATE));
      setSubtitleText(clean);
      setRevealCount(0);
      setSubtitleOn(true);

      const finish = () => {
        setIsSpeaking(false);
        setRevealCount(words.length);
        hideTimerRef.current = window.setTimeout(() => {
          setSubtitleOn(false);
          setSubtitleText('');
          setRevealCount(0);
        }, 520);
      };

      // 1. local neural voice, if configured and endpoint is up
      if (LOCAL_TTS) {
        try {
          const res = await fetch(LOCAL_TTS, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: clean, voice: LOCAL_VOICE }),
          });
          if (res.ok) {
            const url = URL.createObjectURL(new Blob([await res.arrayBuffer()], { type: 'audio/wav' }));
            const audio = new Audio(url);
            audio.onplay = () => setIsSpeaking(true);
            audio.onended = () => {
              URL.revokeObjectURL(url);
              finish();
            };
            audio.onerror = () => {
              URL.revokeObjectURL(url);
              finish();
            };
            await audio.play();
            return;
          }
        } catch {
          /* fall through to browser voice */
        }
      }

      // 2. fall back to Web Speech
      if (!('speechSynthesis' in window)) return;
      window.speechSynthesis.cancel();

      const isCloud = effectiveEngine === 'cloud' && isOnline;
      const voice = pickVoice(isCloud);

      const utterance = new SpeechSynthesisUtterance(clean);
      if (voice) {
        utterance.voice = voice;
        utterance.lang = voice.lang;
      }
      utterance.rate = SPEECH_RATE;
      // Standard pitch 1.0 for clean local Windows SAPI playback
      utterance.pitch = isCloud ? 0.92 : 1.0;
      utterance.volume = 1;
      utterance.onstart = () => setIsSpeaking(true);
      utterance.onboundary = (e: SpeechSynthesisEvent) => {
        if (typeof e.charIndex === 'number') {
          const upto = clean.slice(0, e.charIndex).trim();
          if (upto) setRevealCount(Math.min(words.length, upto.split(/\s+/).length));
        }
      };
      utterance.onend = finish;
      utterance.onerror = (e) => {
        console.warn('[TTS] Synthesis error:', e);
        setIsSpeaking(false);
        setSubtitleOn(false);
      };

      // Workaround for Chrome bug where calling speak immediately after cancel drops audio
      window.setTimeout(() => {
        try {
          if (window.speechSynthesis.paused) {
            window.speechSynthesis.resume();
          }
          window.speechSynthesis.speak(utterance);
        } catch (err) {
          console.warn('[TTS] Speak failed:', err);
          finish();
        }
      }, 30);
    },
    [voiceEnabled, effectiveEngine, isOnline],
  );

  // progressive subtitle reveal (also drives the core's speech pulses)
  useEffect(() => {
    if (!subtitleOn || !subtitleText) return;
    const total = subtitleText.split(/\s+/).length;
    if (revealCount >= total) return;
    const timer = window.setTimeout(() => {
      setRevealCount((c) => Math.min(total, c + 1));
      if (revealCount % 2 === 0) coreRef.current?.pulse(0.28);
    }, msPerWordRef.current);
    return () => window.clearTimeout(timer);
  }, [subtitleOn, subtitleText, revealCount]);

  const revealedText = useMemo(() => {
    if (!subtitleText) return '';
    return subtitleText.split(/\s+/).slice(0, Math.max(1, revealCount)).join(' ');
  }, [subtitleText, revealCount]);

  // some browsers populate voices asynchronously
  useEffect(() => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.getVoices();
      const onVoices = () => window.speechSynthesis.getVoices();
      window.speechSynthesis.addEventListener?.('voiceschanged', onVoices);
      return () => window.speechSynthesis.removeEventListener?.('voiceschanged', onVoices);
    }
  }, []);

  /* ---------------------------------------------------------- recognition */

  const startLocalListening = useCallback(() => {
    if (!localSttRef.current) {
      localSttRef.current = new LocalSpeechRecognition({
        onStateChange: (listening) => {
          setIsListening(listening);
          if (!listening) {
            setLiveTranscript('');
          }
        },
        onTranscript: (text, isFinal) => {
          const trimmed = text.trim();
          transcriptRef.current = trimmed;
          setLiveTranscript(trimmed);
          if (isFinal && trimmed && !sentRef.current) {
            sentRef.current = true;
            executeMessage(trimmed);
          }
        },
        onError: (err) => {
          setVoiceError(err);
          setIsListening(false);
        },
      });
    }

    localSttRef.current.start().catch((err) => {
      setIsListening(false);
      setVoiceError(err?.message || 'Could not start offline microphone.');
    });
  }, []);

  const startCloudListening = useCallback(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      startLocalListening();
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-IN';

    recognition.onstart = () => {
      setIsListening(true);
      setLiveTranscript('');
    };

    recognition.onresult = (event: any) => {
      let text = '';
      for (let i = 0; i < event.results.length; i++) text += event.results[i][0].transcript;
      transcriptRef.current = text.trim();
      setLiveTranscript(transcriptRef.current);
    };

    recognition.onerror = (event: any) => {
      setIsListening(false);
      if (event?.error === 'network') {
        console.warn('[STT] Network error detected. Automatically switching to offline STT.');
        setIsOnline(false);
        setSpeechMode('local');
        setVoiceError('No internet connection. Switched to offline STT.');
        startLocalListening();
      } else if (event?.error === 'not-allowed') {
        setVoiceError('Microphone permission denied.');
      } else if (event?.error && event.error !== 'no-speech') {
        setVoiceError('Voice input error: ' + event.error);
      }
    };

    recognition.onend = () => {
      setIsListening(false);
      const said = transcriptRef.current.trim();
      setLiveTranscript('');
      transcriptRef.current = '';
      if (said && !sentRef.current) {
        sentRef.current = true;
        executeMessage(said);
      }
    };

    cloudRecognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      startLocalListening();
    }
  }, [startLocalListening]);

  const stopListening = useCallback(() => {
    try {
      cloudRecognitionRef.current?.stop();
    } catch {}
    try {
      localSttRef.current?.stop();
    } catch {}
    setIsListening(false);
  }, []);

  const toggleListening = useCallback(() => {
    if (isLoading || loadingRef.current) return;
    if (isListening) {
      stopListening();
      return;
    }

    setVoiceError(null);
    stopSpeaking();
    transcriptRef.current = '';
    sentRef.current = false;

    if (effectiveEngine === 'cloud' && navigator.onLine) {
      startCloudListening();
    } else {
      startLocalListening();
    }
  }, [isLoading, isListening, stopListening, stopSpeaking, effectiveEngine, startCloudListening, startLocalListening]);

  useEffect(() => {
    return () => {
      localSttRef.current?.stop();
      cloudRecognitionRef.current?.stop();
    };
  }, []);

  /* ------------------------------------------------------------ messaging */

  const handleSelectConversation = async (selectedId: string) => {
    if (selectedId === conversationId || isLoadingMessages || isLoading) return;
    stopSpeaking();
    setIsLoadingMessages(true);
    try {
      const fetched = await fetchMessages(selectedId);
      setMessages(
        fetched.map((msg) => ({
          id: nextId(),
          sender: msg.role === 'user' ? 'user' : 'jarvis',
          text: msg.content,
        })),
      );
      setConversationId(selectedId);
      setLatestLatency(null);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      setConversationsError(`Could not load conversation: ${message}`);
    } finally {
      setIsLoadingMessages(false);
    }
  };

  const handleNewChat = () => {
    // mark the pending utterance as handled so recognition.onend can't send it
    sentRef.current = true;
    transcriptRef.current = '';
    stopSpeaking();
    stopListening();
    setConversationId(undefined);
    setMessages([]);
    setLatestLatency(null);
    setInput('');
  };

  const executeMessage = async (raw: string) => {
    const text = raw.trim();
    if (!text || loadingRef.current) return;

    // mark the pending utterance as handled so recognition.onend can't send it
    sentRef.current = true;
    transcriptRef.current = '';
    stopSpeaking();
    stopListening();
    setInput('');

    const botId = nextId();
    setMessages((prev) => [
      ...prev,
      { id: nextId(), sender: 'user', text },
      { id: botId, sender: 'jarvis', text: '', pending: true },
    ]);
    setIsLoading(true);
    loadingRef.current = true;

    const started = performance.now();
    let acc = '';
    let failed = false;

    try {
      await streamChatMessage(
        text,
        conversationId ?? null,
        (chunk) => {
          acc += chunk;
          setMessages((prev) =>
            prev.map((m) => (m.id === botId ? { ...m, text: acc, pending: true } : m)),
          );
        },
        (meta: StreamMeta) => {
          setConversationId(meta.conversation_id);
          const total = meta.metrics?.total_backend_ms ?? performance.now() - started;
          setLatestLatency(Math.round(total));
        },
        (error) => {
          failed = true;
          setMessages((prev) =>
            prev.map((m) => (m.id === botId ? { ...m, text: `Error: ${error}`, pending: false } : m)),
          );
        },
      );
    } catch (error: unknown) {
      failed = true;
      const message = error instanceof Error ? error.message : 'Something went wrong.';
      setMessages((prev) =>
        prev.map((m) => (m.id === botId ? { ...m, text: `Error: ${message}`, pending: false } : m)),
      );
    } finally {
      setIsLoading(false);
      loadingRef.current = false;
      setMessages((prev) => prev.map((m) => (m.id === botId ? { ...m, pending: false } : m)));
    }

    if (!failed && acc) {
      speakResponse(acc);
      loadConversationsList();
    }
  };

  const handleSend = (event: React.FormEvent) => {
    event.preventDefault();
    executeMessage(input);
  };

  const handleComposerKey = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      if (isLoading || loadingRef.current) return;
      executeMessage(input);
    }
  };

  /* keyboard shortcuts */
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const mod = event.metaKey || event.ctrlKey;
      if (mod && event.key.toLowerCase() === 'b') {
        event.preventDefault();
        setHistoryOpen((v) => !v);
      }
      if (mod && event.key.toLowerCase() === 'j') {
        event.preventDefault();
        setChatOpen((v) => !v);
      }
      if (event.key === 'Escape') {
        stopSpeaking();
        stopListening();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [stopSpeaking, stopListening]);

  /* ---------------------------------------------------------------- render */

  const stateLabel =
    coreState === 'listening'
      ? 'LISTENING'
      : coreState === 'speaking'
        ? 'SPEAKING'
        : coreState === 'thinking'
          ? 'THINKING'
          : 'IDLE';
  const stateHint =
    coreState === 'listening'
      ? 'Listening — speak, then pause'
      : coreState === 'speaking'
        ? ''
        : coreState === 'thinking'
          ? 'Jarvis is processing…'
          : 'Click the core to speak';

  const suggestions = [
    'What time is it?',
    'List files in my Documents folder',
    'Open notepad',
    'Search the web for today’s AI news',
  ];

  const renderBody = (text: string) => {
    const parts = text.split(/(```[\s\S]*?```)/g);
    return parts.map((part, index) => {
      if (part.startsWith('```') && part.endsWith('```')) {
        const code = part.slice(3, -3).replace(/^\n/, '');
        return (
          <pre key={index}>
            <code>{code}</code>
          </pre>
        );
      }
      if (!part) return null;
      return (
        <p key={index} className="msg-text">
          {part}
        </p>
      );
    });
  };

  return (
    <div className="app">
      <div className="grain" aria-hidden="true" />

      <header className="nav">
        <span className="nav-brand">JARVIS</span>
        <button
          type="button"
          className="engine-badge"
          onClick={() => {
            const next = effectiveEngine === 'cloud' ? 'local' : 'cloud';
            setSpeechMode(next);
          }}
          title="Click to toggle speech engine: Cloud (Online) / Sherpa (Offline)"
        >
          <span className={`engine-dot ${effectiveEngine === 'cloud' ? 'is-cloud' : 'is-local'}`} />
          <span className="engine-text">
            {effectiveEngine === 'cloud' ? 'Cloud STT (Online)' : 'Sherpa STT (Offline)'}
          </span>
        </button>
      </header>

      <div className="workspace">
        {/* ------------------------------------------------ left: history */}
        <aside className={`panel panel-history${historyOpen ? ' is-open' : ''}`}>
          <div className="panel-inner">
            <div className="panel-head">
              <span className="eyebrow">History</span>
              <button type="button" className="ghost-btn" onClick={handleNewChat} disabled={isLoading}>
                New chat
              </button>
            </div>

            <div className="history-list">
              {isConversationsLoading ? (
                <p className="panel-note">Loading…</p>
              ) : conversationsError ? (
                <p className="panel-note is-error">{conversationsError}</p>
              ) : conversations.length === 0 ? (
                <p className="panel-note">No conversations yet</p>
              ) : (
                conversations.map((conv) => (
                  <button
                    key={conv.id}
                    type="button"
                    className={`history-item${conv.id === conversationId ? ' is-active' : ''}`}
                    onClick={() => handleSelectConversation(conv.id)}
                    disabled={isLoadingMessages || isLoading}
                    title={conv.title || 'Untitled chat'}
                  >
                    <span className="history-title">{conv.title || 'Untitled chat'}</span>
                  </button>
                ))
              )}
            </div>

            <div className="panel-foot">
              <button
                type="button"
                className={`voice-btn${voiceEnabled ? ' is-on' : ''}`}
                onClick={() => {
                  if (voiceEnabled) stopSpeaking();
                  setVoiceEnabled((v) => !v);
                }}
              >
                <span className="voice-led" />
                <span>Voice replies {voiceEnabled ? 'on' : 'off'}</span>
              </button>
            </div>
          </div>
        </aside>

        {/* ------------------------------------------------- center: stage */}
        <main className={`stage${subtitleOn ? ' has-subtitles' : ''}`}>
          <button
            type="button"
            className={`edge-toggle edge-left${historyOpen ? '' : ' is-closed'}`}
            onClick={() => setHistoryOpen((v) => !v)}
            aria-label={historyOpen ? 'Hide history' : 'Show history'}
            title={historyOpen ? 'Hide history' : 'Show history'}
          >
            <Chevron dir={historyOpen ? 'left' : 'right'} />
          </button>

          <button
            type="button"
            className={`edge-toggle edge-right${chatOpen ? '' : ' is-closed'}`}
            onClick={() => setChatOpen((v) => !v)}
            aria-label={chatOpen ? 'Hide conversation' : 'Show conversation'}
            title={chatOpen ? 'Hide conversation' : 'Show conversation'}
          >
            <Chevron dir={chatOpen ? 'right' : 'left'} />
          </button>

          <div className="stage-center">
            <div className="core-frame">
              <span className="corner tl" />
              <span className="corner tr" />
              <span className="corner bl" />
              <span className="corner br" />
              <JarvisCore
                ref={coreRef}
                state={coreState}
                onActivate={toggleListening}
                disabled={isLoading || coreState === 'thinking'}
                label={stateLabel}
                hint={stateHint}
                showCaption={!subtitleOn}
              />
            </div>
          </div>

          <div className={`live-transcript${liveTranscript ? ' is-on' : ''}`}>
            <span className="live-dot" />
            {liveTranscript || '…'}
          </div>

          {voiceError ? (
            <p className="stage-error" onClick={() => setVoiceError(null)}>
              {voiceError}
            </p>
          ) : null}

          <div className={`subtitles${subtitleOn ? ' is-on' : ''}`} aria-live="polite">
            <div className="subtitles-card">
              <div className="subtitles-header">
                <span className="subtitles-dot" />
                <span className="subtitles-label">SPEAKING</span>
              </div>
              <div className="subtitles-body" ref={subtitleRef}>
                {revealedText}
              </div>
            </div>
          </div>
        </main>

        {/* -------------------------------------------- right: conversation */}
        <aside className={`panel panel-chat${chatOpen ? ' is-open' : ''}`}>
          <div className="panel-inner">
            <div className="panel-head">
              <span className="eyebrow">Conversation</span>
              {latestLatency !== null ? (
                <span className="latency">
                  {latestLatency < 1000 ? `${latestLatency} ms` : `${(latestLatency / 1000).toFixed(1)} s`}
                </span>
              ) : null}
            </div>

            <div className="chat-scroll">
              {isLoadingMessages ? (
                <p className="panel-note">Loading messages…</p>
              ) : messages.length === 0 ? (
                <div className="chat-empty">
                  <p className="chat-empty-title">Nothing here yet.</p>
                  <p className="chat-empty-sub">
                    Speak to the core, or type below. Everything you say is kept in this thread.
                  </p>
                  <div className="suggestions">
                    {suggestions.map((s) => (
                      <button
                        key={s}
                        type="button"
                        className="suggestion"
                        onClick={() => executeMessage(s)}
                        disabled={isLoading}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((msg) => (
                  <article key={msg.id} className={`msg ${msg.sender}`}>
                    <div className="msg-meta">{msg.sender === 'user' ? 'You' : 'Jarvis'}</div>
                    {msg.pending && !msg.text ? (
                      <div className="msg-thinking">
                        <i />
                        <i />
                        <i />
                      </div>
                    ) : (
                      <div className="msg-body">{renderBody(msg.text)}</div>
                    )}
                    {msg.sender === 'jarvis' && msg.text && !msg.pending ? (
                      <button
                        type="button"
                        className="msg-replay"
                        onClick={() => speakResponse(msg.text)}
                        title="Speak again"
                      >
                        Replay
                      </button>
                    ) : null}
                  </article>
                ))
              )}
              <div ref={bottomRef} />
            </div>

            <form className="composer" onSubmit={handleSend}>
              <button
                type="button"
                className={`composer-mic${isListening ? ' is-on' : ''}`}
                onClick={toggleListening}
                disabled={isLoading || isLoadingMessages}
                aria-label="Voice input"
                title={isLoading ? 'Jarvis is processing…' : 'Voice input'}
              >
                <MicIcon />
              </button>
              <textarea
                ref={composerRef}
                className="composer-input"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleComposerKey}
                placeholder={
                  isListening
                    ? 'Listening…'
                    : isLoading
                      ? 'Jarvis is processing…'
                      : 'Message Jarvis'
                }
                rows={1}
                disabled={isLoading || isLoadingMessages}
              />
              <button
                type="submit"
                className="composer-send"
                disabled={isLoading || !input.trim()}
                aria-label="Send"
                title={isLoading ? 'Jarvis is processing…' : 'Send'}
              >
                <SendIcon />
              </button>
            </form>
          </div>
        </aside>
      </div>
    </div>
  );
};

export default App;
