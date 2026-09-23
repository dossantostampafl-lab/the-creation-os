import { describe, expect, it } from "vitest";
import { isFarewell, splitWakePhrase } from "./voice";

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
