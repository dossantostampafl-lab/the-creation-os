import { describe, expect, it } from "vitest";
import { bestRecognitionAlternative, interpretUtterance, isFarewell, preferServerTranscript, splitSentences, splitWakePhrase, spokenDecision } from "./voice";

describe("splitWakePhrase", () => {
  it("wakes on the bare wake word", () => {
    expect(splitWakePhrase("Deus")).toEqual({ woke: true, request: "" });
    expect(splitWakePhrase("ei, deus!")).toEqual({ woke: true, request: "" });
  });

  it("extracts the request spoken in the same breath", () => {
    expect(splitWakePhrase("Deus, como estão os universos?")).toEqual({ woke: true, request: "como estão os universos?" });
    expect(splitWakePhrase("ok Zeus qual é a missão atual")).toEqual({ woke: true, request: "qual é a missão atual" });
    expect(splitWakePhrase("Deus, status")).toEqual({ woke: true, request: "status" });
  });

  it("ignores words that merely contain the wake word", () => {
    expect(splitWakePhrase("adeus, até amanhã")).toEqual({ woke: false, request: "" });
    expect(splitWakePhrase("deusa da criação")).toEqual({ woke: false, request: "" });
  });

  it("wakes on common transcriptions of “Deus”", () => {
    expect(splitWakePhrase("Zeus")).toEqual({ woke: true, request: "" });
    expect(splitWakePhrase("dê us, status")).toEqual({ woke: true, request: "status" });
  });

  it("does not wake on words that merely resemble “Deus”", () => {
    expect(splitWakePhrase("Teus")).toEqual({ woke: false, request: "" });
    expect(splitWakePhrase("teus planos estão prontos")).toEqual({ woke: false, request: "" });
    expect(splitWakePhrase("Deu!")).toEqual({ woke: false, request: "" });
    expect(splitWakePhrase("deu certo")).toEqual({ woke: false, request: "" });
    expect(splitWakePhrase("os teus planos estão prontos")).toEqual({ woke: false, request: "" });
    expect(splitWakePhrase("isso deu certo")).toEqual({ woke: false, request: "" });
    expect(splitWakePhrase("deusa da criação")).toEqual({ woke: false, request: "" });
    expect(splitWakePhrase("adeus")).toEqual({ woke: false, request: "" });
    expect(splitWakePhrase("deixa")).toEqual({ woke: false, request: "" });
    expect(splitWakePhrase("teuso")).toEqual({ woke: false, request: "" });
  });
});

describe("isFarewell", () => {
  it("recognises short goodbyes in Portuguese and English", () => {
    for (const phrase of ["tchau", "Tchau!", "até logo", "obrigado", "pode parar", "é só isso", "bye", "thanks"]) {
      expect(isFarewell(phrase)).toBe(true);
    }
  });

  it("keeps requests that merely start politely", () => {
    expect(isFarewell("obrigado, e como está a missão de engenharia agora?")).toBe(false);
    expect(isFarewell("qual é o status dos universos")).toBe(false);
  });
});

describe("spokenDecision", () => {
  it("hears short approvals and rejections", () => {
    for (const phrase of ["aprova", "Sim, aprova!", "pode aprovar", "aprovado", "approve", "yes approve it"]) {
      expect(spokenDecision(phrase)).toBe("approve");
    }
    for (const phrase of ["rejeita", "não, rejeita", "recusa", "reject", "rejeitado."]) {
      expect(spokenDecision(phrase)).toBe("reject");
    }
  });

  it("hears the go and the stop for a prepared Mission", () => {
    for (const phrase of ["autoriza", "Pode iniciar!", "inicia a missão", "sim, autoriza", "começa", "pode começar", "start", "authorize"]) {
      expect(spokenDecision(phrase)).toBe("authorize");
    }
    for (const phrase of ["cancela", "não, cancela", "cancelar a missão", "abort", "cancel"]) {
      expect(spokenDecision(phrase)).toBe("cancel");
    }
  });

  it("leaves other requests alone", () => {
    expect(spokenDecision("sim")).toBeNull();
    expect(spokenDecision("aprova e depois me conta como vai ficar a missão inteira")).toBeNull();
    expect(spokenDecision("qual é o plano")).toBeNull();
    expect(spokenDecision("inicia uma missão para criar o site e depois publica")).toBeNull();
    expect(spokenDecision("inicia uma nova missão")).toBeNull();
    expect(spokenDecision("start a landing page")).toBeNull();
    expect(spokenDecision("cancela o lembrete")).toBeNull();
    expect(spokenDecision("aprova e depois me conta")).toBeNull();
  });
});

describe("interpretUtterance", () => {
  it("sends the whole sentence, not the first pause", () => {
    // The browser finalises at every pause, so this arrives as several segments joined by the
    // caller. Acting on "Deus, crie" alone is what made the microphone seem to hear one word.
    expect(interpretUtterance("Deus, crie um universo de finanças", false))
      .toEqual({ kind: "command", text: "crie um universo de finanças" });
    expect(interpretUtterance("crie um universo de finanças", true))
      .toEqual({ kind: "command", text: "crie um universo de finanças" });
  });

  it("wakes on the bare wake word and waits for the request", () => {
    expect(interpretUtterance("Deus", false)).toEqual({ kind: "wake" });
    expect(interpretUtterance("ei, deus!", false)).toEqual({ kind: "wake" });
  });

  it("ignores speech that was not addressed to DEUS", () => {
    expect(interpretUtterance("adeus, até amanhã", false)).toEqual({ kind: "ignore" });
    expect(interpretUtterance("qualquer conversa na sala", false)).toEqual({ kind: "ignore" });
    expect(interpretUtterance("   ", true)).toEqual({ kind: "ignore" });
  });

  it("hears a goodbye only while attentive", () => {
    expect(interpretUtterance("tchau", true)).toEqual({ kind: "farewell" });
    // Asleep, a goodbye is just talk in the room.
    expect(interpretUtterance("tchau", false)).toEqual({ kind: "ignore" });
  });

  it("treats a leading name as address once already listening", () => {
    expect(interpretUtterance("Deus, status", true)).toEqual({ kind: "command", text: "status" });
  });
});


describe("bestRecognitionAlternative", () => {
  it("prefers a wake-word alternative while sleeping even when it is not the first hypothesis", () => {
    const result = Object.assign([
      { transcript: "adeus", confidence: 0.91 },
      { transcript: "Deus", confidence: 0.76 },
      { transcript: "dê us", confidence: 0.68 },
    ], { isFinal: true });
    expect(bestRecognitionAlternative(result, false).transcript).toBe("Deus");
  });

  it("prefers the highest-confidence dictation while already attentive", () => {
    const result = Object.assign([
      { transcript: "status dos universo", confidence: 0.51 },
      { transcript: "status dos universos", confidence: 0.89 },
    ], { isFinal: true });
    expect(bestRecognitionAlternative(result, true).transcript).toBe("status dos universos");
  });
});

describe("preferServerTranscript", () => {
  it("keeps the browser sentence when server audio started too late and is clearly clipped", () => {
    expect(preferServerTranscript(
      "continue a análise do projeto inteiro",
      "projeto",
    )).toBe("continue a análise do projeto inteiro");
  });

  it("uses server STT when it contains a complete correction", () => {
    expect(preferServerTranscript(
      "texto errado do navegador",
      "continue o projeto",
    )).toBe("continue o projeto");
  });

  it("removes a repeated wake word from the authoritative server transcript", () => {
    expect(preferServerTranscript(
      "verifique o projeto",
      "Deus, verifique o projeto",
    )).toBe("verifique o projeto");
  });
});

describe("splitSentences", () => {
  it("splits a reply into sentences for incremental speech", () => {
    expect(splitSentences("Os universos respiram. A missão segue em execução! Algo mais?"))
      .toEqual(["Os universos respiram.", "A missão segue em execução!", "Algo mais?"]);
  });

  it("keeps a single sentence and decimal numbers whole", () => {
    expect(splitSentences("Tudo em ordem")).toEqual(["Tudo em ordem"]);
    expect(splitSentences("A versão 2.5 está pronta.")).toEqual(["A versão 2.5 está pronta."]);
    expect(splitSentences("  ")).toEqual([]);
  });
});
