import { describe, expect, it } from "vitest";
import {
  conversationMessageToChatItem,
  inferRequestedPanel,
  missionProgressFraction,
  normalizeEntityKey,
  normalizeStatus,
  pendingInception,
  shouldClosePanel,
} from "./appLogic";
import type { ConversationMessage, Inception } from "./types";

function inception(status: string): Inception {
  return { id: "i1", conversation_id: "c1", title: "t", description: "d", status };
}

function conversationMessage(overrides: Partial<ConversationMessage> = {}): ConversationMessage {
  return {
    id: "m1",
    conversation_id: "c1",
    actor_id: "god",
    role: "god",
    content: "text",
    route: "god",
    metadata_json: {},
    correlation_id: "corr-1",
    created_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
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

describe("conversationMessageToChatItem", () => {
  it("maps a creator message with Creator meta", () => {
    const item = conversationMessageToChatItem(conversationMessage({ role: "creator", content: "ola", actor_id: "creator-1" }));
    expect(item).toEqual({ id: "m1", role: "creator", text: "ola", meta: "Creator" });
  });

  it("marks a login-greeting GOD message distinctly from a regular one", () => {
    const greeting = conversationMessageToChatItem(
      conversationMessage({ content: "Bem-vindo", metadata_json: { greeting: true } }),
    );
    expect(greeting).toEqual({ id: "m1", role: "god", text: "Bem-vindo", meta: "greeting" });

    const regular = conversationMessageToChatItem(
      conversationMessage({ content: "resposta", metadata_json: { next_action: "continue_conversation" } }),
    );
    expect(regular).toEqual({ id: "m1", role: "god", text: "resposta", meta: "continue_conversation" });
  });

  it("falls back to 'history' for a GOD message with no recognizable metadata", () => {
    const item = conversationMessageToChatItem(conversationMessage({ content: "x", metadata_json: {} }));
    expect(item.meta).toBe("history");
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

  it("maps search verbs to the search panel", () => {
    expect(inferRequestedPanel("buscar missao de engenharia")).toBe("search");
    expect(inferRequestedPanel("pesquisar agentes")).toBe("search");
  });

  it("maps notification keywords to the notifications panel", () => {
    expect(inferRequestedPanel("mostre as notificacoes")).toBe("notifications");
  });
});

describe("missionProgressFraction", () => {
  it("maps known statuses to their stage fraction, case-insensitively", () => {
    expect(missionProgressFraction("drafted")).toBeCloseTo(1 / 7);
    expect(missionProgressFraction("AUTHORIZED")).toBeCloseTo(4 / 7);
    expect(missionProgressFraction("manifested")).toBe(1);
  });

  it("returns 0 for an unrecognized status", () => {
    expect(missionProgressFraction("unknown")).toBe(0);
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
