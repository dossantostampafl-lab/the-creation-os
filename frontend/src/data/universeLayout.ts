import type { Agent, Universe } from "../types";

export type UniverseVisual = {
  id: string;
  code: string;
  title: string;
  description: string;
  left: number;
  top: number;
  color: string;
  colorSoft: string;
  icon: string;
};

export const universeLayout: UniverseVisual[] = [
  {
    id: "knowledge",
    code: "conhecimento",
    title: "CONHECIMENTO",
    description: "Consolida aprendizado\ne memória consciente.",
    left: 19,
    top: 52,
    color: "#3b82f6",
    colorSoft: "#71b7ff",
    icon: "book",
  },
  {
    id: "evolution",
    code: "evolucao",
    title: "EVOLUÇÃO",
    description: "Pesquisa, melhora\ne expande capacidades.",
    left: 18,
    top: 71,
    color: "#48d99b",
    colorSoft: "#86f4c4",
    icon: "leaf",
  },
  {
    id: "engineering",
    code: "engenharia",
    title: "ENGENHARIA",
    description: "Executa missões técnicas\ne constrói soluções.",
    left: 74,
    top: 22,
    color: "#3a8dff",
    colorSoft: "#7abfff",
    icon: "code",
  },
  {
    id: "security",
    code: "seguranca",
    title: "SEGURANÇA",
    description: "Protege, audita\ne mitiga riscos.",
    left: 79,
    top: 43,
    color: "#ff8a24",
    colorSoft: "#ffbd66",
    icon: "shield",
  },
  {
    id: "community",
    code: "comunidade",
    title: "COMUNIDADE",
    description: "Conecta, observa\ne aprende com o todo.",
    left: 69,
    top: 61,
    color: "#b65cff",
    colorSoft: "#e192ff",
    icon: "users",
  },
  {
    id: "infrastructure",
    code: "infraestrutura",
    title: "INFRAESTRUTURA",
    description: "Sustenta, escala\ne mantém o sistema.",
    left: 78,
    top: 70,
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

export function agentsForUniverse(universe: UniverseVisual, agents: Agent[]) {
  const normalizedCode = universe.code.toLowerCase();
  const normalizedTitle = universe.title.toLowerCase();
  return agents.filter((agent) => {
    const normalizedUniverse = agent.universe.toLowerCase();
    return normalizedUniverse === normalizedCode || normalizedUniverse === normalizedTitle;
  });
}

export function mergeUniverseData(realUniverses: Universe[]) {
  return realUniverses.map((real, index) => {
    const visual =
      universeLayout.find((item) => real.code.toLowerCase() === item.code || real.name.toLowerCase() === item.title.toLowerCase()) ??
      universeLayout[index % universeLayout.length];
    return { ...visual, id: real.id, code: real.code, title: real.name.toUpperCase() };
  });
}
