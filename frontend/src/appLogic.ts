import type { ChatItem, ConversationMessage, Inception } from "./types";

export type RequestedPanel =
  | "inceptions"
  | "missions"
  | "opportunities"
  | "perception"
  | "chronicle"
  | "capabilities"
  | "universes"
  | "notifications"
  | "search"
  | null;

export function normalizeStatus(value: string) {
  return value.toLowerCase();
}

export function pendingInception(item: Inception) {
  return !["approved", "rejected", "cancelled"].includes(normalizeStatus(item.status));
}

export function normalizeEntityKey(value: string) {
  const normalized = value
    .normalize("NFKD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
  if (/engenharia|engineering|engineer|eng/.test(normalized)) return "eng";
  if (/juridico|legal|jur/.test(normalized)) return "jur";
  if (/finance|financial|financas|fin/.test(normalized)) return "fin";
  if (/seguranca|security|seg/.test(normalized)) return "seg";
  if (/negocios|business|neg/.test(normalized)) return "neg";
  if (/ciencia|science|cie/.test(normalized)) return "cie";
  if (/conhecimento|knowledge|con/.test(normalized)) return "con";
  if (/criacao|creation|cri/.test(normalized)) return "cri";
  return normalized;
}

export function inferRequestedPanel(message: string): RequestedPanel {
  const normalized = message
    .normalize("NFKD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
  if (
    !/(?:^|\b)(mostrar|mostre|abrir|abra|exibir|exiba|visualizar|ver|buscar|pesquisar|procurar)(?:\b|$)/.test(normalized)
  ) {
    return null;
  }
  if (/(buscar|pesquisar|procurar|busca|pesquisa)/.test(normalized)) return "search";
  if (/(notificacao|notificacoes|alerta|alertas)/.test(normalized)) return "notifications";
  if (/(inception|inceptions|ideia|aprovacao)/.test(normalized)) return "inceptions";
  if (/(missao|missoes|mission|projeto)/.test(normalized)) return "missions";
  if (/(universo|universos|agente|agentes|engenharia|seguranca|infraestrutura|conhecimento|comunidade|evolucao)/.test(normalized)) {
    return "universes";
  }
  if (/(oportunidade|oportunidades|analise|ranking)/.test(normalized)) return "opportunities";
  if (/(percepcao|fonte|coleta|source|perception)/.test(normalized)) return "perception";
  if (/(auditoria|chronicle|cronica|historico|log)/.test(normalized)) return "chronicle";
  if (/(capability|capabilities|connector|automation|automacao)/.test(normalized)) return "capabilities";
  return null;
}

export function shouldClosePanel(message: string) {
  const normalized = message
    .normalize("NFKD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
  return /(feche|fechar|volte para a conversa|voltar para a conversa|feche o painel|close)/.test(normalized);
}

export function panelTitle(panel: Exclude<RequestedPanel, null>) {
  return {
    inceptions: "Inceptions",
    missions: "Missao ativa",
    opportunities: "Oportunidades",
    perception: "Percepcao",
    chronicle: "Chronicle",
    capabilities: "Capabilities",
    universes: "Universos e agentes",
    notifications: "Notificacoes",
    search: "Busca",
  }[panel];
}

// Lote: DEUS inicia conversa automaticamente após login. Converts a
// persisted Message row (fetched from GET /conversations/{id}/messages)
// into the same ChatItem shape the live sendToGod() flow already appends —
// "trinity" is a frontend-only synthetic role never persisted as a Message,
// so any role besides "creator" is treated as "god".
export function conversationMessageToChatItem(item: ConversationMessage): ChatItem {
  const role: ChatItem["role"] = item.role === "creator" ? "creator" : "god";
  if (role === "creator") return { id: item.id, role, text: item.content, meta: "Creator" };
  const isGreeting = item.metadata_json?.greeting === true;
  const nextAction = item.metadata_json?.next_action;
  const meta = isGreeting ? "greeting" : typeof nextAction === "string" ? nextAction : "history";
  return { id: item.id, role, text: item.content, meta };
}

export function missionProgressFraction(status: string): number {
  const stages = ["drafted", "planned", "validated", "authorized", "distributed", "executing", "manifested"];
  const index = stages.indexOf(normalizeStatus(status));
  if (index < 0) return 0;
  return (index + 1) / stages.length;
}
