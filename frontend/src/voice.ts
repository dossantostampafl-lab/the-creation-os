import { useCallback, useEffect, useRef, useState } from "react";
import { synthesizeVoice, transcribeVoice } from "./api";

/**
 * DEUS's voice and ears.
 * Voice: ElevenLabs through the backend when configured, otherwise the browser's speech synthesis.
 * Ears: the browser's speech recognition, with an optional "Deus" wake word (like a smart speaker).
 */

const VOICE_KEY = "creation_voice_enabled";
const WAKE_KEY = "creation_wake_word";
const QUALITY_HINTS = ["natural", "neural", "online", "google", "premium", "enhanced"];
const MAX_SPOKEN_CHARS = 1200;
const ATTENTION_MS = 12000;
/** Silence after the last final segment that means the Creator has finished speaking.
  * Browsers finalise a result at every pause -- often after a single word -- so acting on
  * the first one sends a fragment and stops listening mid-sentence. */
const SETTLE_MS = 700;
const WAKE_WORD = /(^|[^\p{L}])(deus|zeus|d[eê]\s+us)(?![\p{L}])/iu;

function voiceLanguage(): string {
  const browser = navigator.language || "pt-BR";
  // The Creator speaks Brazilian Portuguese. Normalize any Portuguese browser locale so the
  // recognizer does not silently fall back to a different Portuguese acoustic model.
  return browser.toLowerCase().startsWith("pt") ? "pt-BR" : browser;
}

const portuguese = () => voiceLanguage().toLowerCase().startsWith("pt");

export const voiceText = {
  greeting: () => (portuguese() ? "Estou aqui." : "I'm here."),
  wakeHint: () => (portuguese() ? "Diga “Deus” para chamar" : "Say “Deus” to call"),
  listening: () => (portuguese() ? "Ouvindo…" : "Listening…"),
  farewell: () => (portuguese() ? "Até logo." : "Goodbye."),
  conversationHint: () => (portuguese() ? "Em conversa — diga “tchau” para encerrar" : "In conversation — say “bye” to end"),
  dismissed: () => (portuguese() ? "Proposta descartada." : "Proposal dismissed."),
  started: () => (portuguese() ? "Missão autorizada. Iniciando." : "Mission authorized. Starting."),
  cancelled: () => (portuguese() ? "Missão cancelada." : "Mission cancelled."),
};

// Short phrases that close a voice conversation ("tchau", "obrigado", "pode parar", "bye"...).
const FAREWELL = /^(tchau|até logo|até mais|até amanhã|obrigad[oa]|valeu|pode parar|para de ouvir|chega|encerrar|encerra|é só isso|só isso|bye|goodbye|thanks|thank you|stop listening|that's all)\b/iu;

/** True when a short utterance only says goodbye, so a longer "obrigado, e a missão?" still counts as a request. */
export function isFarewell(transcript: string): boolean {
  const text = transcript.trim().replace(/[.!?]+$/u, "");
  return text.split(/\s+/).filter(Boolean).length <= 4 && FAREWELL.test(text);
}

// Bare answers to the Trinity ("autoriza", "pode iniciar", "cancela a missão", "sim, aprova"...).
// The whole utterance must be the command, so "inicia uma nova missão" still reaches DEUS.
const YES = String.raw`(?:(?:sim|pode|ok|yes)[,]?\s+)?`;
const NO = String.raw`(?:(?:não|nao|no)[,]?\s+)?`;
const OBJECT = String.raw`(?:\s+(?:a\s+miss[aã]o|ela|isso|agora|j[aá]|the\s+mission|it|now))?`;
const command = (prefix: string, verbs: string) => new RegExp(`^${prefix}(?:${verbs})${OBJECT}$`, "iu");
const AUTHORIZE = command(YES, "autoriz[ae]r?|autorizad[oa]|inici[ae]r?|come[cç][ae]r?|authori[sz]e|start|launch|go(?:\\s+ahead)?");
const CANCEL = command(NO, "cancel[ae]r?|cancelad[oa]|abort[ae]r?|cancel|abort");
const APPROVE = command(YES, "aprov[ae]r?|aprovad[oa]|approve|approved");
const REJECT = command(NO, "rejeit[ae]r?|rejeitad[oa]|recus[ae]r?|reject|rejected|decline");

export type SpokenDecision = "authorize" | "cancel" | "approve" | "reject";

/** The Creator's spoken decision on the Trinity's latest proposal, or null when the utterance is anything else. */
export function spokenDecision(transcript: string): SpokenDecision | null {
  const text = transcript.trim().replace(/[.!?]+$/u, "").replace(/\s+/gu, " ");
  if (AUTHORIZE.test(text)) return "authorize";
  if (CANCEL.test(text)) return "cancel";
  if (APPROVE.test(text)) return "approve";
  if (REJECT.test(text)) return "reject";
  return null;
}

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

// ElevenLabs is tried first. When it is not configured (HTTP 501) the session keeps the browser voice;
// after a temporary failure (rate limit, outage, network) it is retried after a short cooldown.
const PREMIUM_RETRY_MS = 60_000;
let premiumRetryAt = 0;
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
  // Each speak() is a new turn; callbacks from an interrupted turn must not touch the current one.
  const turn = useRef(0);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  useEffect(() => {
    if (!browserVoice) return;
    const load = () => { voices.current = window.speechSynthesis.getVoices(); };
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", load);
  }, [browserVoice]);

  useEffect(() => () => {
    current.current?.stop();
    current.current = null;
    if (browserVoice) window.speechSynthesis.cancel();
    voiceActivity.level = 0;
  }, [browserVoice]);

  const stop = useCallback(() => {
    turn.current += 1;
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
    const myTurn = turn.current;
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
      if (turn.current !== myTurn) return;
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
      if (turn.current !== myTurn) return;
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
    // Read the live preference: a reply that arrives after the Creator muted DEUS must stay silent.
    if (!enabledRef.current || !content) {
      handlers.onEnd?.();
      return;
    }
    if (Date.now() < premiumRetryAt) {
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
    const myTurn = turn.current;
    const finish = () => {
      if (finished) return;
      finished = true;
      cleanup();
      if (turn.current !== myTurn) return;
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
        const notConfigured = failure instanceof Error && failure.message === "HTTP_501";
        const autoplayBlocked = failure instanceof DOMException && failure.name === "NotAllowedError";
        if (notConfigured) premiumRetryAt = Number.POSITIVE_INFINITY;
        else if (!autoplayBlocked) premiumRetryAt = Date.now() + PREMIUM_RETRY_MS;
        speakWithBrowser(content, { onEnd: finish });
      });
  }, [speakWithBrowser, stop]);

  const acknowledge = useCallback((text: string, handlers: SpeakHandlers = {}) => {
    const content = speakable(text);
    stop();
    if (!enabledRef.current || !content) {
      handlers.onEnd?.();
      return;
    }
    // Wake acknowledgements must be immediate: never wait on a network TTS round trip.
    speakWithBrowser(content, handlers);
  }, [speakWithBrowser, stop]);

  return { supported, enabled, speaking, toggle, speak, acknowledge, stop };
}

type RecognitionAlternative = { transcript: string; confidence?: number };
type RecognitionResult = ArrayLike<RecognitionAlternative> & { isFinal: boolean };
type RecognitionResultEvent = Event & { resultIndex: number; results: ArrayLike<RecognitionResult> };
type Recognition = EventTarget & {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives?: number;
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

type EarsState = "off" | "sleeping" | "attentive";

type EarsOptions = {
  /** DEUS is thinking or speaking: stop listening so it does not hear itself. */
  paused: boolean;
  /** The Creator said only the wake word. */
  onWake: () => void;
  /** A request addressed to DEUS. */
  onCommand: (text: string) => void;
  /** Live transcript while DEUS is attentive. */
  onInterim: (text: string) => void;
  /** Attention lapsed because nobody spoke. */
  onLapse?: () => void;
  /** The Creator said goodbye while DEUS was attentive. */
  onFarewell?: () => void;
};

/** The wake word ("Deus") followed by a pause makes DEUS attentive; "Deus, <request>" sends the request at once. */
export function splitWakePhrase(transcript: string): { woke: boolean; request: string } {
  const match = WAKE_WORD.exec(transcript);
  if (!match) return { woke: false, request: "" };
  const request = transcript.slice(match.index + match[0].length).replace(/^[\s,.!?;:—-]+/, "").trim();
  return { woke: true, request };
}


export function bestRecognitionAlternative(
  result: RecognitionResult,
  attentive: boolean,
): RecognitionAlternative {
  const alternatives = Array.from({ length: result.length }, (_, index) => result[index]).filter(Boolean);
  if (!alternatives.length) return { transcript: "", confidence: 0 };
  if (!attentive) {
    const wakeMatches = alternatives.filter((item) => splitWakePhrase(item.transcript).woke);
    if (wakeMatches.length) {
      return wakeMatches.reduce((best, item) => (item.confidence ?? 0) > (best.confidence ?? 0) ? item : best);
    }
  }
  return alternatives.reduce((best, item) => (item.confidence ?? 0) > (best.confidence ?? 0) ? item : best);
}

/** What an utterance means, once the Creator has finished saying it. */
export type Utterance =
  | { kind: "farewell" }
  | { kind: "command"; text: string }
  | { kind: "wake" }
  | { kind: "ignore" };

/** Decides without touching state, so the rule can be read and tested on its own. */
export function interpretUtterance(transcript: string, attentive: boolean): Utterance {
  const text = transcript.trim();
  if (!text) return { kind: "ignore" };
  if (attentive) {
    if (isFarewell(text)) return { kind: "farewell" };
    // Already listening, so a leading "Deus, ..." is just a form of address.
    const { woke, request } = splitWakePhrase(text);
    return { kind: "command", text: woke && request ? request : text };
  }
  const { woke, request } = splitWakePhrase(text);
  if (!woke) return { kind: "ignore" };
  return request ? { kind: "command", text: request } : { kind: "wake" };
}

export function useDeusEars({ paused, onWake, onCommand, onInterim, onLapse, onFarewell }: EarsOptions) {
  const supported = typeof window !== "undefined" && recognitionConstructor() !== null;
  const [wakeEnabled, setWakeEnabled] = useState(() => supported && readPreference(WAKE_KEY, true));
  const [state, setState] = useState<EarsState>("off");
  const [error, setError] = useState<string | null>(null);
  const recognition = useRef<Recognition | null>(null);
  const mounted = useRef(false);
  const failures = useRef(0);
  const attentive = useRef(false);
  /** Final segments of the sentence in progress, and the timer that ends it. */
  const spoken = useRef<string[]>([]);
  const confidences = useRef<number[]>([]);
  const settleTimer = useRef<number | undefined>(undefined);
  const mediaStream = useRef<MediaStream | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const transcriptionRetryAt = useRef(0);
  const attentionTimer = useRef(0);
  const desired = useRef({ wakeEnabled, paused });
  const handlers = useRef({ onWake, onCommand, onInterim, onLapse, onFarewell });
  handlers.current = { onWake, onCommand, onInterim, onLapse, onFarewell };
  desired.current = { wakeEnabled, paused };

  const publish = useCallback(() => {
    const running = recognition.current !== null;
    setState(attentive.current ? "attentive" : running && desired.current.wakeEnabled ? "sleeping" : "off");
  }, []);

  const setAttentive = useCallback((value: boolean) => {
    attentive.current = value;
    window.clearTimeout(attentionTimer.current);
    // Attention always lapses: an unanswered "Deus" or mic press must not capture later speech.
    if (value) armAttention();
    publish();
    // armAttention only touches refs, so the first render's copy stays correct.
  }, [publish]);

  function armAttention() {
    window.clearTimeout(attentionTimer.current);
    attentionTimer.current = window.setTimeout(() => {
      attentive.current = false;
      void finishCapture();
      handlers.current.onInterim("");
      handlers.current.onLapse?.();
      sync();
    }, ATTENTION_MS);
  }

  /** A final segment is one pause, not one sentence. Collect them and decide once the Creator
    * stops: acting on the first sends a fragment ("Deus, crie" from "Deus, crie um universo")
    * and ends the turn while they are still talking. */
  function handleFinal(transcript: string, confidence?: number) {
    const text = transcript.trim();
    if (!text) return;
    spoken.current.push(text);
    if (typeof confidence === "number" && confidence > 0) confidences.current.push(confidence);
    waitForTheEnd();
  }

  function waitForTheEnd() {
    window.clearTimeout(settleTimer.current);
    settleTimer.current = window.setTimeout(flush, SETTLE_MS);
  }

  async function finishCapture(): Promise<Blob | null> {
    const active = recorder.current;
    if (!active || active.state === "inactive") return null;
    recorder.current = null;
    return new Promise((resolve) => {
      active.onstop = () => {
        const chunks = audioChunks.current;
        audioChunks.current = [];
        resolve(chunks.length ? new Blob(chunks, { type: active.mimeType || "audio/webm" }) : null);
      };
      try {
        active.stop();
      } catch {
        audioChunks.current = [];
        resolve(null);
      }
    });
  }

  async function maybeImproveTranscript(browserText: string, averageConfidence: number | null): Promise<string> {
    // Confidence 0/undefined is common on Chromium and does not mean "bad". Only pay the
    // network/STT latency when the recognizer explicitly reports low confidence.
    if (averageConfidence === null || averageConfidence >= 0.72 || Date.now() < transcriptionRetryAt.current) {
      void finishCapture();
      return browserText;
    }
    const audio = await finishCapture();
    if (!audio || audio.size < 400) return browserText;
    try {
      const improved = await transcribeVoice(audio);
      return improved.text.trim() || browserText;
    } catch (failure) {
      const disabled = failure instanceof Error && failure.message === "HTTP_501";
      transcriptionRetryAt.current = disabled ? Number.POSITIVE_INFINITY : Date.now() + 60_000;
      return browserText;
    }
  }

  function flush() {
    window.clearTimeout(settleTimer.current);
    const said = spoken.current.join(" ").replace(/\s+/g, " ").trim();
    const heardConfidence = confidences.current.length
      ? confidences.current.reduce((sum, value) => sum + value, 0) / confidences.current.length
      : null;
    spoken.current = [];
    confidences.current = [];
    if (!said) return;

    const utterance = interpretUtterance(said, attentive.current);
    switch (utterance.kind) {
      case "ignore":
        void finishCapture();
        return;
      case "farewell":
        void finishCapture();
        setAttentive(false);
        handlers.current.onInterim("");
        handlers.current.onFarewell?.();
        return;
      case "wake":
        setAttentive(true);
        handlers.current.onWake();
        return;
      case "command": {
        setAttentive(false);
        handlers.current.onInterim("");
        const browserText = utterance.text;
        void maybeImproveTranscript(browserText, heardConfidence)
          .then((text) => handlers.current.onCommand(text));
        return;
      }
    }
  }

  function start() {
    const Ctor = recognitionConstructor();
    if (!Ctor || recognition.current) return;
    const instance = new Ctor();
    instance.lang = "pt-BR";
    instance.interimResults = true;
    instance.continuous = true;
    instance.maxAlternatives = 4;
    instance.onresult = (event) => {
      failures.current = 0;
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const best = bestRecognitionAlternative(result, attentive.current);
        if (result.isFinal) handleFinal(best.transcript, best.confidence);
        else interim += best.transcript;
      }
      if (interim) {
        // Still speaking: hold both the attention window and the end-of-sentence timer open.
        if (spoken.current.length) waitForTheEnd();
        if (attentive.current) {
          armAttention();
          handlers.current.onInterim(interim.trim());
        }
      }
    };
    instance.onerror = (event) => {
      const blocked = event.error === "not-allowed" || event.error === "service-not-allowed";
      if (blocked || event.error === "audio-capture") {
        setError(blocked
          ? (portuguese() ? "O navegador bloqueou o microfone." : "The browser blocked the microphone.")
          : (portuguese() ? "Nenhum microfone encontrado." : "No microphone was found."));
        setWakeEnabled(false);
        writePreference(WAKE_KEY, false);
        attentive.current = false;
      } else if (event.error !== "no-speech" && event.error !== "aborted") {
        failures.current += 1;
      }
    };
    instance.onend = () => {
      if (recognition.current === instance) recognition.current = null;
      // Browsers end recognition after silence; keep listening while DEUS is meant to,
      // backing off when the recognition service keeps failing (offline, for example).
      window.setTimeout(sync, failures.current ? 250 * 2 ** Math.min(failures.current, 6) : 100);
    };
    recognition.current = instance;
    try {
      instance.start();
      if (attentive.current) armAttention();
    } catch {
      recognition.current = null;
    }
  }

  async function ensureCapture() {
    if (!attentive.current || desired.current.paused || recorder.current || typeof MediaRecorder === "undefined") return;
    if (!navigator.mediaDevices?.getUserMedia || Date.now() < transcriptionRetryAt.current) return;
    try {
      mediaStream.current ??= await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
      if (!attentive.current || desired.current.paused) return;
      const next = new MediaRecorder(mediaStream.current);
      audioChunks.current = [];
      next.ondataavailable = (event) => { if (event.data.size) audioChunks.current.push(event.data); };
      recorder.current = next;
      next.start(200);
    } catch {
      // Web Speech remains fully functional when MediaRecorder/getUserMedia is unavailable.
    }
  }

  function sync() {
    if (!mounted.current) return;
    const { wakeEnabled: wake, paused: hold } = desired.current;
    const shouldListen = !hold && (wake || attentive.current);
    if (shouldListen && !recognition.current) start();
    if (shouldListen && attentive.current) void ensureCapture();
    if (!shouldListen && recognition.current) {
      const instance = recognition.current;
      recognition.current = null;
      instance.abort();
    }
    if (!shouldListen && recorder.current) void finishCapture();
    publish();
  }

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      window.clearTimeout(attentionTimer.current);
      const instance = recognition.current;
      recognition.current = null;
      instance?.abort();
      const activeRecorder = recorder.current;
      recorder.current = null;
      if (activeRecorder && activeRecorder.state !== "inactive") activeRecorder.stop();
      mediaStream.current?.getTracks().forEach((track) => track.stop());
      mediaStream.current = null;
    };
  }, []);

  useEffect(() => {
    sync();
  });

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
    void finishCapture();
    handlers.current.onInterim("");
  }, [setAttentive]);

  return { supported, wakeEnabled, state, error, toggleWake, summon, dismiss };
}
