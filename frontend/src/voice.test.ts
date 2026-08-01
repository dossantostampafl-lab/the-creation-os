import { describe, expect, it, vi } from "vitest";
import { buildContextualVoiceMessage, stopAudioPlayback } from "./voice";

const baseContext = {
  currentSubject: "assunto",
  missionTitle: "Missao X",
  opportunityTitle: "Oportunidade Y",
  pendingDecision: "inception_review",
  lastGodReply: "resposta anterior",
};

describe("buildContextualVoiceMessage", () => {
  it("returns the trimmed input untouched when it does not reference prior context", () => {
    expect(buildContextualVoiceMessage("  ola deus  ", baseContext)).toBe("ola deus");
  });

  it("wraps the input with conversation context when it references it", () => {
    const result = buildContextualVoiceMessage("continue", baseContext);
    expect(result).toContain("Contexto da conversa de voz com DEUS:");
    expect(result).toContain("assunto atual: assunto");
    expect(result).toContain("missao em analise: Missao X");
    expect(result).toContain("fala atual do Criador: continue");
  });

  it("fills in defaults for missing context fields", () => {
    const result = buildContextualVoiceMessage("resuma", {
      currentSubject: null,
      missionTitle: null,
      opportunityTitle: null,
      pendingDecision: null,
      lastGodReply: null,
    });
    expect(result).toContain("assunto atual: nao definido");
    expect(result).toContain("missao em analise: nenhuma");
    expect(result).toContain("decisao pendente: nenhuma");
  });
});

describe("stopAudioPlayback", () => {
  it("pauses and resets the player, then revokes the object URL", () => {
    const player = { pause: vi.fn(), currentTime: 5, src: "blob:x" };
    const revoke = vi.fn();
    stopAudioPlayback(player, "blob:x", revoke);
    expect(player.pause).toHaveBeenCalledOnce();
    expect(player.currentTime).toBe(0);
    expect(player.src).toBe("");
    expect(revoke).toHaveBeenCalledWith("blob:x");
  });

  it("does nothing when there is no player or object URL", () => {
    const revoke = vi.fn();
    expect(() => stopAudioPlayback(null, null, revoke)).not.toThrow();
    expect(revoke).not.toHaveBeenCalled();
  });
});
