import type { Inception } from "./types";

export type RequestedPanel =
  | "inceptions"
  | "missions"
  | "opportunities"
  | "perception"
  | "chronicle"
  | "capabilities"
  | "universes"
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
  if (!/(?:^|\b)(mostrar|mostre|abrir|abra|exibir|exiba|visualizar|ver)(?:\b|$)/.test(normalized)) return null;
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
  }[panel];
}
