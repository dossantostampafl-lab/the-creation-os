import { useCallback, useEffect, useRef, useState } from "react";
import { synthesizeVoice } from "./api";

/**
 * DEUS's voice and ears.
 * Voice: ElevenLabs through the backend when configured, otherwise the browser's speech synthesis.
 * Ears: the browser's speech recognition, with an optional "Deus" wake word (like a smart speaker).
 */

const VOICE_KEY = "creation_voice_enabled";
const WAKE_KEY = "creation_wake_word";
const QUALITY_HINTS = ["natural", "neural", "online", "google", "premium", "enhanced"];
const MAX_SPOKEN_CHARS = 1200;
const ATTENTION_MS = 8000;
const WAKE_WORD = /(^|[^\p{L}])(deus|zeus)(?![\p{L}])/iu;

export function voiceLanguage(): string {
  return navigator.language || "en-US";
}

const portuguese = () => voiceLanguage().toLowerCase().startsWith("pt");

export const voiceText = {
  greeting: () => (portuguese() ? "Estou aqui." : "I'm here."),
  wakeHint: () => (portuguese() ? "Diga “Deus” para chamar" : "Say “Deus” to call"),
  listening: () => (portuguese() ? "Ouvindo…" : "Listening…"),
};

/** Live loudness of DEUS's voice (0–1), read by the cosmic brain every frame. */
export const voiceActivity = { level: 0 };

function readPreference(key: string, fallback: boolean): boolean {
  try {
    const value = window.localStorage.getItem(key);
    return value === null ? fallback : value === "on";
  } catch {
    return fallback;
  }
}

function writePreference(key: string, value: boolean) {
  try {
    window.localStorage.setItem(key, value ? "on" : "off");
  } catch {
    // Preferences are a convenience only.
  }
}

function pickVoice(voices: SpeechSynthesisVoice[], lang: string): SpeechSynthesisVoice | null {
  const base = lang.toLowerCase().split("-")[0];
  const exact = voices.filter((voice) => voice.lang.toLowerCase() === lang.toLowerCase());
  const family = voices.filter((voice) => voice.lang.toLowerCase().startsWith(base));
  const pool = exact.length ? exact : family;
  if (!pool.length) return null;
  return pool.find((voice) => QUALITY_HINTS.some((hint) => voice.name.toLowerCase().includes(hint))) ?? pool[0];
}

/** Strips Markdown so it is not read aloud symbol by symbol, and keeps within the synthesis limit. */
function speakable(text: string): string {
  const plain = text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/[*_#>`~|]/g, "")
    .replace(/\[(.*?)\]\(.*?\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
  if (plain.length <= MAX_SPOKEN_CHARS) return plain;
  const cut = plain.slice(0, MAX_SPOKEN_CHARS);
  const sentenceEnd = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("! "), cut.lastIndexOf("? "));
  return sentenceEnd > MAX_SPOKEN_CHARS / 2 ? cut.slice(0, sentenceEnd + 1) : cut;
}

type SpeakHandlers = { onStart?: () => void; onEnd?: () => void };

// ElevenLabs is tried first; after a failure (not configured, offline) the session uses the browser voice.
let premiumVoiceAvailable = true;
const phraseCache = new Map<string, Blob>();
let audioContext: AudioContext | null = null;

/** Browsers only start audio contexts after a user gesture; unlock on the first click or key press. */
function unlockAudio() {
  try {
    audioContext ??= new AudioContext();
    if (audioContext.state !== "running") void audioContext.resume();
  } catch {
    audioContext = null;
  }
}

if (typeof window !== "undefined") {
  window.addEventListener("pointerdown", unlockAudio, { once: true, capture: true });
  window.addEventListener("keydown", unlockAudio, { once: true, capture: true });
}

/** Approximates loudness while audio plays when the analyser is unavailable. */
function simulatedMeter(audio: HTMLAudioElement): () => void {
  const timer = window.setInterval(() => {
    voiceActivity.level = audio.paused ? 0 : 0.3 + Math.random() * 0.5;
  }, 110);
  return () => {
    window.clearInterval(timer);
    voiceActivity.level = 0;
  };
}

function meter(audio: HTMLAudioElement): () => void {
  // A suspended context would swallow the audio, so only route through it when it is running.
  if (!audioContext || audioContext.state !== "running") return simulatedMeter(audio);
  try {
    const source = audioContext.createMediaElementSource(audio);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    analyser.connect(audioContext.destination);
    const samples = new Uint8Array(analyser.fftSize);
    let frame = 0;
    const tick = () => {
      analyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (const sample of samples) sum += ((sample - 128) / 128) ** 2;
      voiceActivity.level = Math.min(1, Math.sqrt(sum / samples.length) * 4);
      frame = requestAnimationFrame(tick);
    };
    tick();
    return () => {
      cancelAnimationFrame(frame);
      source.disconnect();
      analyser.disconnect();
      voiceActivity.level = 0;
    };
  } catch {
    return simulatedMeter(audio);
  }
}

export function useDeusVoice() {
  const browserVoice = typeof window !== "undefined" && "speechSynthesis" in window;
  const supported = browserVoice || typeof Audio !== "undefined";
  const [enabled, setEnabled] = useState(() => readPreference(VOICE_KEY, true));
  const [speaking, setSpeaking] = useState(false);
  const voices = useRef<SpeechSynthesisVoice[]>([]);
  const current = useRef<{ stop: () => void } | null>(null);

  useEffect(() => {
    if (!browserVoice) return;
    const load = () => { voices.current = window.speechSynthesis.getVoices(); };
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", load);
      current.current?.stop();
    };
  }, [browserVoice]);

  const stop = useCallback(() => {
    current.current?.stop();
    current.current = null;
    if (browserVoice) window.speechSynthesis.cancel();
    voiceActivity.level = 0;
    setSpeaking(false);
  }, [browserVoice]);

  const toggle = useCallback(() => {
    setEnabled((was) => {
      writePreference(VOICE_KEY, !was);
      if (was) stop();
      return !was;
    });
  }, [stop]);

  const speakWithBrowser = useCallback((content: string, handlers: SpeakHandlers) => {
    if (!browserVoice) {
      handlers.onEnd?.();
      return;
    }
    window.speechSynthesis.cancel();
    const lang = voiceLanguage();
    const utterance = new SpeechSynthesisUtterance(content);
    utterance.lang = lang;
    const voice = pickVoice(voices.current, lang);
    if (voice) utterance.voice = voice;
    utterance.pitch = 0.82;
    utterance.rate = 0.97;
    let settle = 0;
    let finished = false;
    // Some browsers never fire "end" for long utterances; never leave DEUS stuck speaking.
    const watchdog = window.setTimeout(() => finish(), 4000 + content.length * 90);
    utterance.onstart = () => {
      setSpeaking(true);
      handlers.onStart?.();
    };
    utterance.onboundary = (event) => {
      if (event.name !== "word") return;
      voiceActivity.level = 1;
      window.clearTimeout(settle);
      settle = window.setTimeout(() => { voiceActivity.level = 0.15; }, 140);
    };
    function finish() {
      if (finished) return;
      finished = true;
      window.clearTimeout(settle);
      window.clearTimeout(watchdog);
      voiceActivity.level = 0;
      setSpeaking(false);
      handlers.onEnd?.();
    }
    utterance.onend = finish;
    utterance.onerror = finish;
    current.current = { stop: () => window.speechSynthesis.cancel() };
    window.speechSynthesis.speak(utterance);
  }, [browserVoice]);

  const speak = useCallback((text: string, handlers: SpeakHandlers = {}) => {
    const content = speakable(text);
    stop();
    if (!enabled || !content) {
      handlers.onEnd?.();
      return;
    }
    if (!premiumVoiceAvailable) {
      speakWithBrowser(content, handlers);
      return;
    }

    const controller = new AbortController();
    let audio: HTMLAudioElement | null = null;
    let release = () => {};
    let url = "";
    let finished = false;
    const cleanup = () => {
      release();
      if (url) URL.revokeObjectURL(url);
    };
    const finish = () => {
      if (finished) return;
      finished = true;
      cleanup();
      setSpeaking(false);
      handlers.onEnd?.();
    };
    current.current = {
      stop: () => {
        finished = true;
        controller.abort();
        audio?.pause();
        cleanup();
      },
    };
    setSpeaking(true);
    handlers.onStart?.();

    const cached = phraseCache.get(content);
    (cached ? Promise.resolve(cached) : synthesizeVoice(content, controller.signal))
      .then(async (blob) => {
        if (finished) return;
        if (content.length < 80) phraseCache.set(content, blob);
        url = URL.createObjectURL(blob);
        audio = new Audio(url);
        audio.onended = finish;
        audio.onerror = finish;
        release = meter(audio);
        await audio.play();
      })
      .catch((failure: unknown) => {
        if (finished || (failure instanceof DOMException && failure.name === "AbortError")) return;
        cleanup();
        // Autoplay refusals are momentary; anything else means ElevenLabs is not usable this session.
        if (!(failure instanceof DOMException && failure.name === "NotAllowedError")) premiumVoiceAvailable = false;
        speakWithBrowser(content, { onEnd: finish });
      });
  }, [enabled, speakWithBrowser, stop]);

  return { supported, enabled, speaking, toggle, speak, stop };
}

type RecognitionResultEvent = Event & { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> };
type Recognition = EventTarget & {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: RecognitionResultEvent) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: Event & { error?: string }) => void) | null;
};
type RecognitionConstructor = new () => Recognition;

function recognitionConstructor(): RecognitionConstructor | null {
  const scope = window as unknown as { SpeechRecognition?: RecognitionConstructor; webkitSpeechRecognition?: RecognitionConstructor };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

export type EarsState = "off" | "sleeping" | "attentive";

type EarsOptions = {
  /** DEUS is thinking or speaking: stop listening so it does not hear itself. */
  paused: boolean;
  /** The Creator said only the wake word. */
  onWake: () => void;
  /** A request addressed to DEUS. */
  onCommand: (text: string) => void;
  /** Live transcript while DEUS is attentive. */
  onInterim: (text: string) => void;
};

/** The wake word ("Deus") followed by a pause makes DEUS attentive; "Deus, <request>" sends the request at once. */
export function splitWakePhrase(transcript: string): { woke: boolean; request: string } {
  const match = WAKE_WORD.exec(transcript);
  if (!match) return { woke: false, request: "" };
  const request = transcript.slice(match.index + match[0].length).replace(/^[\s,.!?;:—-]+/, "").trim();
  return { woke: true, request };
}

export function useDeusEars({ paused, onWake, onCommand, onInterim }: EarsOptions) {
  const supported = typeof window !== "undefined" && recognitionConstructor() !== null;
  const [wakeEnabled, setWakeEnabled] = useState(() => supported && readPreference(WAKE_KEY, false));
  const [state, setState] = useState<EarsState>("off");
  const [error, setError] = useState<string | null>(null);
  const recognition = useRef<Recognition | null>(null);
  const attentive = useRef(false);
  const attentionTimer = useRef(0);
  const desired = useRef({ wakeEnabled, paused });
  const handlers = useRef({ onWake, onCommand, onInterim });
  handlers.current = { onWake, onCommand, onInterim };
  desired.current = { wakeEnabled, paused };

  const publish = useCallback(() => {
    const running = recognition.current !== null;
    setState(attentive.current ? "attentive" : running && desired.current.wakeEnabled ? "sleeping" : "off");
  }, []);

  const setAttentive = useCallback((value: boolean) => {
    attentive.current = value;
    window.clearTimeout(attentionTimer.current);
    publish();
  }, [publish]);

  function armAttention() {
    window.clearTimeout(attentionTimer.current);
    attentionTimer.current = window.setTimeout(() => {
      attentive.current = false;
      handlers.current.onInterim("");
      sync();
    }, ATTENTION_MS);
  }

  function handleFinal(transcript: string) {
    const text = transcript.trim();
    if (!text) return;
    if (attentive.current) {
      setAttentive(false);
      handlers.current.onCommand(text);
      return;
    }
    const { woke, request } = splitWakePhrase(text);
    if (!woke) return;
    if (request.split(/\s+/).filter(Boolean).length >= 2) {
      handlers.current.onCommand(request);
    } else {
      setAttentive(true);
      handlers.current.onWake();
    }
  }

  function start() {
    const Ctor = recognitionConstructor();
    if (!Ctor || recognition.current) return;
    const instance = new Ctor();
    instance.lang = voiceLanguage();
    instance.interimResults = true;
    instance.continuous = true;
    instance.onresult = (event) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) handleFinal(result[0].transcript);
        else interim += result[0].transcript;
      }
      if (attentive.current && interim) {
        armAttention();
        handlers.current.onInterim(interim.trim());
      }
    };
    instance.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        setError(portuguese() ? "O navegador bloqueou o microfone." : "The browser blocked the microphone.");
        setWakeEnabled(false);
        writePreference(WAKE_KEY, false);
        attentive.current = false;
      }
    };
    instance.onend = () => {
      if (recognition.current === instance) recognition.current = null;
      // Browsers end recognition after silence; keep listening while DEUS is meant to.
      window.setTimeout(sync, 250);
    };
    recognition.current = instance;
    try {
      instance.start();
      if (attentive.current) armAttention();
    } catch {
      recognition.current = null;
    }
  }

  function sync() {
    const { wakeEnabled: wake, paused: hold } = desired.current;
    const shouldListen = !hold && (wake || attentive.current);
    if (shouldListen && !recognition.current) start();
    if (!shouldListen && recognition.current) {
      const instance = recognition.current;
      recognition.current = null;
      instance.abort();
    }
    publish();
  }

  useEffect(() => {
    sync();
  });

  useEffect(() => () => {
    window.clearTimeout(attentionTimer.current);
    recognition.current?.abort();
    recognition.current = null;
  }, []);

  const toggleWake = useCallback(() => {
    setError(null);
    setWakeEnabled((was) => {
      writePreference(WAKE_KEY, !was);
      return !was;
    });
  }, []);

  /** Push-to-talk: DEUS listens for one request right away. */
  const summon = useCallback(() => {
    setError(null);
    setAttentive(true);
  }, [setAttentive]);

  const dismiss = useCallback(() => {
    setAttentive(false);
    handlers.current.onInterim("");
  }, [setAttentive]);

  return { supported, wakeEnabled, state, error, toggleWake, summon, dismiss };
}
