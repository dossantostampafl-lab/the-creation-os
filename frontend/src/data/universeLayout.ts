import type { Agent, ChronicleEntry, Inception, Mission, Universe } from "../types";

export type UniverseVisual = {
  id: string;
  code: string;
  title: string;
  agents: number;
  description: string;
  left: number;
  top: number;
  color: string;
  colorSoft: string;
  icon: string;
};

export const DEMO_VISUAL_DATA = "DEMO_VISUAL_DATA";

export const universeLayout: UniverseVisual[] = [
  {
    id: "knowledge",
    code: "conhecimento",
    title: "CONHECIMENTO",
    agents: 2,
    description: "Consolida aprendizado\ne memória consciente.",
    left: 13,
    top: 38,
    color: "#3b82f6",
    colorSoft: "#71b7ff",
    icon: "book",
  },
  {
    id: "evolution",
    code: "evolucao",
    title: "EVOLUÇÃO",
    agents: 2,
    description: "Pesquisa, melhora\ne expande capacidades.",
    left: 18,
    top: 61,
    color: "#48d99b",
    colorSoft: "#86f4c4",
    icon: "leaf",
  },
  {
    id: "engineering",
    code: "engenharia",
    title: "ENGENHARIA",
    agents: 3,
    description: "Executa missões técnicas\ne constrói soluções.",
    left: 73,
    top: 19,
    color: "#3a8dff",
    colorSoft: "#7abfff",
    icon: "code",
  },
  {
    id: "security",
    code: "seguranca",
    title: "SEGURANÇA",
    agents: 1,
    description: "Protege, audita\ne mitiga riscos.",
    left: 78,
    top: 40,
    color: "#ff8a24",
    colorSoft: "#ffbd66",
    icon: "shield",
  },
  {
    id: "community",
    code: "comunidade",
    title: "COMUNIDADE",
    agents: 2,
    description: "Conecta, observa\ne aprende com o todo.",
    left: 68,
    top: 61,
    color: "#b65cff",
    colorSoft: "#e192ff",
    icon: "users",
  },
  {
    id: "infrastructure",
    code: "infraestrutura",
    title: "INFRAESTRUTURA",
    agents: 2,
    description: "Sustenta, escala\ne mantém o sistema.",
    left: 77,
    top: 77,
    color: "#f0a435",
    colorSoft: "#ffd071",
    icon: "box",
  },
];

export const operationalSteps = [
  ["CENTRAL CORE", "Planeja e valida"],
  ["TREE CORE", "Distribui e consolida"],
  ["MISSION PLANNER", "Define estratégia"],
  ["TASK GRAPH", "Orquestra tarefas"],
  ["CAPABILITY ENGINE", "Habilita e executa"],
];

export const flowAgents = [
  ["AGENTE 01", "Análise"],
  ["AGENTE 02", "Desenvolvimento"],
  ["AGENTE 03", "Testes"],
  ["AGENTE N", "Execução"],
];

export const demoInceptions: Inception[] = [
  {
    id: "INC-2047",
    conversation_id: DEMO_VISUAL_DATA,
    title: "Refatorar módulo de commission ledger",
    description: "Engenharia",
    status: "Engenharia",
  },
  {
    id: "INC-2048",
    conversation_id: DEMO_VISUAL_DATA,
    title: "Investigar exposição de header RBAC",
    description: "Segurança",
    status: "Segurança",
  },
];

export const demoMissions: Mission[] = [
  { id: "mission-demo", title: "Missão #204", objective: DEMO_VISUAL_DATA, status: "MANIFESTED" },
];

export const demoChronicles: ChronicleEntry[] = [
  {
    id: "demo-1",
    event_id: DEMO_VISUAL_DATA,
    position: 1,
    actor_role: "GOD",
    event_type: "registrou nova conversa com o Criador",
    aggregate_type: "09:41:21",
    aggregate_id: null,
    created_at: "2026-07-13T09:41:21",
  },
  {
    id: "demo-2",
    event_id: DEMO_VISUAL_DATA,
    position: 2,
    actor_role: "Tree Core",
    event_type: "distribuiu 3 tarefas ao universo Engenharia",
    aggregate_type: "09:40:58",
    aggregate_id: null,
    created_at: "2026-07-13T09:40:58",
  },
  {
    id: "demo-3",
    event_id: DEMO_VISUAL_DATA,
    position: 3,
    actor_role: "Pulse",
    event_type: "6/6 serviços saudáveis",
    aggregate_type: "09:40:33",
    aggregate_id: null,
    created_at: "2026-07-13T09:40:33",
  },
  {
    id: "demo-4",
    event_id: DEMO_VISUAL_DATA,
    position: 4,
    actor_role: "Malkuth",
    event_type: "manifestou resultado da missão #204",
    aggregate_type: "09:40:12",
    aggregate_id: null,
    created_at: "2026-07-13T09:40:12",
  },
  {
    id: "demo-5",
    event_id: DEMO_VISUAL_DATA,
    position: 5,
    actor_role: "Chronicles",
    event_type: "ciclo de auditoria concluído sem falhas",
    aggregate_type: "09:39:48",
    aggregate_id: null,
    created_at: "2026-07-13T09:39:48",
  },
];

export function agentsForUniverse(universe: UniverseVisual, agents: Agent[]) {
  const normalizedCode = universe.code.toLowerCase();
  return agents.filter((agent) => agent.universe.toLowerCase() === normalizedCode || agent.universe.toLowerCase() === universe.title.toLowerCase());
}

export function mergeUniverseData(realUniverses: Universe[]) {
  return universeLayout.map((visual) => {
    const real = realUniverses.find(
      (item) => item.code.toLowerCase() === visual.code || item.name.toLowerCase() === visual.title.toLowerCase(),
    );
    return real ? { ...visual, id: real.id, title: real.name.toUpperCase() } : visual;
  });
}
