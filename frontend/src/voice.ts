import { useCallback, useEffect, useRef, useState } from "react";

/** Voice for DEUS using the browser's Web Speech API (no extra service or key required). */

const VOICE_KEY = "creation_voice_enabled";
const QUALITY_HINTS = ["natural", "neural", "online", "google", "premium", "enhanced"];

export function voiceLanguage(): string {
  return navigator.language || "en-US";
}

function pickVoice(voices: SpeechSynthesisVoice[], lang: string): SpeechSynthesisVoice | null {
  const base = lang.toLowerCase().split("-")[0];
  const exact = voices.filter((voice) => voice.lang.toLowerCase() === lang.toLowerCase());
  const family = voices.filter((voice) => voice.lang.toLowerCase().startsWith(base));
  const pool = exact.length ? exact : family;
  if (!pool.length) return null;
  return pool.find((voice) => QUALITY_HINTS.some((hint) => voice.name.toLowerCase().includes(hint))) ?? pool[0];
}

/** Strips Markdown so it is not read aloud symbol by symbol. */
function speakable(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/[*_#>`~|]/g, "")
    .replace(/\[(.*?)\]\(.*?\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

type SpeakHandlers = { onStart?: () => void; onWord?: () => void; onEnd?: () => void };

export function useDeusVoice() {
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;
  const [enabled, setEnabled] = useState(() => {
    try {
      return window.localStorage.getItem(VOICE_KEY) !== "off";
    } catch {
      return true;
    }
  });
  const [speaking, setSpeaking] = useState(false);
  const voices = useRef<SpeechSynthesisVoice[]>([]);

  useEffect(() => {
    if (!supported) return;
    const load = () => { voices.current = window.speechSynthesis.getVoices(); };
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", load);
      window.speechSynthesis.cancel();
    };
  }, [supported]);

  const stop = useCallback(() => {
    if (supported) window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [supported]);

  const toggle = useCallback(() => {
    setEnabled((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(VOICE_KEY, next ? "on" : "off");
      } catch {
        // Preference is a convenience only.
      }
      if (!next && supported) window.speechSynthesis.cancel();
      return next;
    });
  }, [supported]);

  const speak = useCallback((text: string, handlers: SpeakHandlers = {}) => {
    const content = speakable(text);
    if (!supported || !enabled || !content) {
      handlers.onEnd?.();
      return;
    }
    window.speechSynthesis.cancel();
    const lang = voiceLanguage();
    const utterance = new SpeechSynthesisUtterance(content);
    utterance.lang = lang;
    const voice = pickVoice(voices.current, lang);
    if (voice) utterance.voice = voice;
    // A slightly lower, unhurried voice suits a cosmic intelligence.
    utterance.pitch = 0.82;
    utterance.rate = 0.97;
    utterance.onstart = () => {
      setSpeaking(true);
      handlers.onStart?.();
    };
    utterance.onboundary = (event) => {
      if (event.name === "word") handlers.onWord?.();
    };
    const finish = () => {
      setSpeaking(false);
      handlers.onEnd?.();
    };
    utterance.onend = finish;
    utterance.onerror = finish;
    window.speechSynthesis.speak(utterance);
  }, [enabled, supported]);

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

/** Lets the Creator speak to DEUS; resolves with the final transcript. */
export function useCreatorListening(onTranscript: (text: string, final: boolean) => void) {
  const supported = typeof window !== "undefined" && recognitionConstructor() !== null;
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognition = useRef<Recognition | null>(null);
  const callback = useRef(onTranscript);
  callback.current = onTranscript;

  useEffect(() => () => recognition.current?.abort(), []);

  const start = useCallback(() => {
    const Ctor = recognitionConstructor();
    if (!Ctor) return;
    recognition.current?.abort();
    const instance = new Ctor();
    instance.lang = voiceLanguage();
    instance.interimResults = true;
    instance.continuous = false;
    let transcript = "";
    instance.onresult = (event) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) transcript += result[0].transcript;
        else interim += result[0].transcript;
      }
      callback.current((transcript + interim).trim(), false);
    };
    instance.onerror = (event) => {
      setError(event.error === "not-allowed" ? "Microphone permission was denied." : "Could not hear you. Try again.");
    };
    instance.onend = () => {
      setListening(false);
      if (transcript.trim()) callback.current(transcript.trim(), true);
    };
    recognition.current = instance;
    setError(null);
    setListening(true);
    instance.start();
  }, []);

  const stop = useCallback(() => recognition.current?.stop(), []);

  return { supported, listening, error, start, stop };
}
