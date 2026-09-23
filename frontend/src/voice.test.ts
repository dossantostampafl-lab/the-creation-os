import { describe, expect, it } from "vitest";
import { isFarewell, splitWakePhrase, spokenDecision } from "./voice";

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
