export type VoiceConversationState = "idle" | "listening" | "processing" | "responding" | "speaking" | "error";

export type BrowserSpeechRecognizer = {
  start: () => Promise<void>;
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
  maxAlternatives: number;
  onstart: (() => void) | null;
  onaudiostart: (() => void) | null;
  onspeechstart: (() => void) | null;
  onspeechend: (() => void) | null;
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
      start: async () => options.onError("Reconhecimento de voz indisponivel neste navegador."),
      stop: options.onStop,
    };
  }

  const recognition = new Recognition();
  let recognitionTimeout: number | null = null;
  let receivedTranscript = false;
  let recognitionFailed = false;
  function clearRecognitionTimeout() {
    if (recognitionTimeout === null) return;
    window.clearTimeout(recognitionTimeout);
    recognitionTimeout = null;
  }
  function releaseCapture() {
    clearRecognitionTimeout();
  }
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = "pt-BR";
  recognition.maxAlternatives = 1;
  recognition.onstart = options.onStart;
  recognition.onaudiostart = () => undefined;
  recognition.onspeechstart = () => undefined;
  recognition.onspeechend = () => undefined;
  recognition.onend = () => {
    releaseCapture();
    if (!receivedTranscript && !recognitionFailed) options.onError("Nenhuma fala foi detectada.");
    else options.onStop();
  };
  recognition.onerror = (event) => {
    recognitionFailed = true;
    releaseCapture();
    options.onError(event.error === "no-speech" ? "Nenhuma fala detectada. Tente novamente." : `Falha no reconhecimento de voz: ${event.error}`);
  };
  recognition.onresult = (event) => {
    let finalText = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      if (result.isFinal) finalText += result[0].transcript;
    }
    const normalized = finalText.trim();
    if (normalized) {
      receivedTranscript = true;
      clearRecognitionTimeout();
      options.onTranscript(normalized);
    }
  };

  return {
    supported: true,
    start: async () => {
      if (!navigator.mediaDevices?.enumerateDevices) {
        options.onError("Este navegador nao oferece dispositivos de entrada de audio.");
        return;
      }
      try {
        receivedTranscript = false;
        recognitionFailed = false;
        const devices = await navigator.mediaDevices.enumerateDevices();
        if (!devices.some((device) => device.kind === "audioinput")) {
          options.onError("Nenhum microfone foi encontrado.");
          return;
        }
        recognitionTimeout = window.setTimeout(() => {
          recognitionFailed = true;
          releaseCapture();
          recognition.stop();
          options.onError("Nenhuma fala detectada. Tente novamente.");
        }, 10000);
        recognition.start();
      } catch (error) {
        releaseCapture();
        options.onError(error instanceof DOMException && error.name === "NotAllowedError" ? "Permissao do microfone negada." : "Nao foi possivel iniciar o reconhecimento de voz.");
      }
    },
    stop: () => {
      recognition.stop();
    },
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
    "Contexto da conversa de voz com DEUS:",
    `assunto atual: ${context.currentSubject ?? "nao definido"}`,
    `missao em analise: ${context.missionTitle ?? "nenhuma"}`,
    `oportunidade em analise: ${context.opportunityTitle ?? "nenhuma"}`,
    `decisao pendente: ${context.pendingDecision ?? "nenhuma"}`,
    `ultima resposta de DEUS: ${context.lastGodReply ?? "nenhuma"}`,
    `fala atual do Criador: ${normalized}`,
  ].join("\n");
}

export function stopAudioPlayback(
  player: Pick<HTMLAudioElement, "pause" | "currentTime" | "src"> | null,
  objectUrl: string | null,
  revokeObjectUrl: (url: string) => void = URL.revokeObjectURL,
) {
  if (player) {
    player.pause();
    player.currentTime = 0;
    player.src = "";
  }
  if (objectUrl) {
    revokeObjectUrl(objectUrl);
  }
}
