export type VoiceConversationState = "idle" | "listening" | "processing" | "speaking" | "error";

export type BrowserSpeechRecognizer = {
  start: () => void;
  stop: () => void;
  supported: boolean;
};

type SpeechRecognitionResultLike = {
  readonly isFinal: boolean;
  readonly 0: { transcript: string };
};

type SpeechRecognitionEventLike = Event & {
  readonly resultIndex: number;
  readonly results: {
    readonly length: number;
    readonly [index: number]: SpeechRecognitionResultLike;
  };
};

type SpeechRecognitionErrorEventLike = Event & {
  readonly error: string;
};

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

type SpeechWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
};

export function createBrowserSpeechRecognizer(options: {
  onStart: () => void;
  onStop: () => void;
  onTranscript: (text: string) => void;
  onError: (message: string) => void;
}): BrowserSpeechRecognizer {
  const speechWindow = window as SpeechWindow;
  const Recognition = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
  if (!Recognition) {
    return {
      supported: false,
      start: () => options.onError("Reconhecimento de voz indisponivel neste navegador."),
      stop: options.onStop,
    };
  }

  const recognition = new Recognition();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = navigator.language || "pt-BR";
  recognition.onstart = options.onStart;
  recognition.onend = options.onStop;
  recognition.onerror = (event) => options.onError(`Falha no reconhecimento de voz: ${event.error}`);
  recognition.onresult = (event) => {
    let finalText = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      if (result.isFinal) finalText += result[0].transcript;
    }
    const normalized = finalText.trim();
    if (normalized) options.onTranscript(normalized);
  };

  return {
    supported: true,
    start: () => recognition.start(),
    stop: () => recognition.stop(),
  };
}

export function buildContextualVoiceMessage(input: string, context: {
  currentSubject: string | null;
  missionTitle: string | null;
  opportunityTitle: string | null;
  pendingDecision: string | null;
  lastGodReply: string | null;
}) {
  const normalized = input.trim();
  const referencesContext = /^(continue|explique melhor|volte|mostre|autorize|negue|resuma)\b/i.test(normalized);
  if (!referencesContext) return normalized;
  return [
    "Contexto da conversa de voz com GOD:",
    `assunto atual: ${context.currentSubject ?? "nao definido"}`,
    `missao em analise: ${context.missionTitle ?? "nenhuma"}`,
    `oportunidade em analise: ${context.opportunityTitle ?? "nenhuma"}`,
    `decisao pendente: ${context.pendingDecision ?? "nenhuma"}`,
    `ultima resposta de GOD: ${context.lastGodReply ?? "nenhuma"}`,
    `fala atual do Criador: ${normalized}`,
  ].join("\n");
}
