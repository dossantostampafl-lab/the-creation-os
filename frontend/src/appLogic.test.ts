import { describe, expect, it } from "vitest";
import {
  inferRequestedPanel,
  normalizeEntityKey,
  normalizeStatus,
  pendingInception,
  shouldClosePanel,
} from "./appLogic";
import type { Inception } from "./types";

function inception(status: string): Inception {
  return { id: "i1", conversation_id: "c1", title: "t", description: "d", status };
}

describe("normalizeStatus", () => {
  it("lowercases the value", () => {
    expect(normalizeStatus("APPROVED")).toBe("approved");
  });
});

describe("pendingInception", () => {
  it("treats approved/rejected/cancelled as not pending", () => {
    expect(pendingInception(inception("approved"))).toBe(false);
    expect(pendingInception(inception("rejected"))).toBe(false);
    expect(pendingInception(inception("cancelled"))).toBe(false);
  });

  it("treats other statuses as pending, case-insensitively", () => {
    expect(pendingInception(inception("proposed"))).toBe(true);
    expect(pendingInception(inception("AWAITING_CREATOR_DECISION"))).toBe(true);
  });
});

describe("normalizeEntityKey", () => {
  it("maps accented and english variants to the same universe code", () => {
    expect(normalizeEntityKey("Engenharia")).toBe("eng");
    expect(normalizeEntityKey("Engineering")).toBe("eng");
    expect(normalizeEntityKey("Segurança")).toBe("seg");
    expect(normalizeEntityKey("Security")).toBe("seg");
  });

  it("falls back to the normalized value for unknown universes", () => {
    expect(normalizeEntityKey("Mystery")).toBe("mystery");
  });
});

describe("inferRequestedPanel", () => {
  it("returns null when the message has no display verb", () => {
    expect(inferRequestedPanel("aprove a inception")).toBeNull();
  });

  it("maps display verbs plus a topic keyword to the right panel", () => {
    expect(inferRequestedPanel("mostre as inceptions pendentes")).toBe("inceptions");
    expect(inferRequestedPanel("abra as missoes")).toBe("missions");
    expect(inferRequestedPanel("ver oportunidades")).toBe("opportunities");
    expect(inferRequestedPanel("exibir fontes de percepcao")).toBe("perception");
    expect(inferRequestedPanel("mostrar o chronicle")).toBe("chronicle");
    expect(inferRequestedPanel("abra as capabilities")).toBe("capabilities");
    expect(inferRequestedPanel("mostre os agentes de engenharia")).toBe("universes");
  });

  it("returns null when a verb has no recognized topic", () => {
    expect(inferRequestedPanel("mostre o tempo")).toBeNull();
  });
});

describe("shouldClosePanel", () => {
  it("recognizes phrases asking to close or return to the conversation", () => {
    expect(shouldClosePanel("feche o painel")).toBe(true);
    expect(shouldClosePanel("volte para a conversa")).toBe(true);
    expect(shouldClosePanel("close")).toBe(true);
  });

  it("ignores unrelated messages", () => {
    expect(shouldClosePanel("mostre as missoes")).toBe(false);
  });
});
