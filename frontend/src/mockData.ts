import type { Agent } from "./types";

export const mockChronicle = [
  { label: "GOD", text: "Canal direto aguardando a palavra do Criador", mock: true },
  { label: "SOPHIA", text: "Compreensao estrutural pronta para POTENTIAL", mock: true },
  { label: "ROCKMAM", text: "Avaliacao deterministica sem execucao", mock: true },
];

export const mockPulse = {
  status: "mock telemetry",
  heartbeat: "steady",
  load: "low",
};

export const mockUniverses = [
  { id: "living", name: "Living Core", x: 21, y: 29 },
  { id: "tree", name: "Tree Core", x: 58, y: 23 },
  { id: "central", name: "Central Core", x: 74, y: 55 },
  { id: "malkuth", name: "Malkuth", x: 37, y: 68 },
];

export const fallbackAgents: Agent[] = [
  { id: "oracle", name: "Oracle", universe: "Living Core", status: "mock", active: true },
  { id: "cartographer", name: "Cartographer", universe: "Tree Core", status: "mock", active: true },
  { id: "executor", name: "Executor", universe: "Malkuth", status: "mock", active: false },
];
