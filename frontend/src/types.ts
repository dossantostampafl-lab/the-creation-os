export type MissionView = {
  id: string;
  title: string;
  objective: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
};

export type TaskView = {
  id: string;
  mission_id: string;
  step_id: string;
  universe_id: string;
  agent_id: string;
  status: string;
  attempt_count: number;
  max_attempts: number;
};

export type UniverseView = {
  id: string;
  code: string;
  name: string;
  active: boolean;
};

export type AgentView = {
  id: string;
  code: string;
  name: string;
  universe_id: string;
  active: boolean;
};

export type MemoryView = {
  conversation: number;
  mission: number;
  universe: number;
  conscious: number;
  total: number;
};

export type SystemCounts = {
  missions: number;
  running_missions: number;
  tasks: number;
  ready_tasks: number;
  running_tasks: number;
  failed_tasks: number;
  active_universes: number;
  active_agents: number;
};

export type PulseValue = {
  value: unknown;
  observed_at: string;
};

export type SystemState = {
  projection: string;
  position: number;
  generated_at: string;
  missions: MissionView[];
  tasks: TaskView[];
  universes: UniverseView[];
  agents: AgentView[];
  memory: MemoryView;
  pulse: Record<string, PulseValue>;
  counts: SystemCounts;
};

export type ChronicleEvent = {
  event_id: string;
  position: number;
  correlation_id: string;
  causation_id: string | null;
  actor_role: string;
  event_type: string;
  aggregate_type: string;
  aggregate_id: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type ChronicleRecord = {
  id: string;
  event_id: string;
  correlation_id: string;
  causation_id: string | null;
  actor_type: string;
  actor_id: string | null;
  event_type: string;
  aggregate_type: string;
  aggregate_id: string | null;
  payload_json: Record<string, unknown>;
  payload_hash: string;
  previous_hash: string | null;
  created_at: string;
};

export type ProjectionStatus = {
  chronicle_head: number;
  projections: Array<{
    name: string;
    position: number | null;
    lag: number | null;
    status: "CURRENT" | "LAGGING" | "MISSING" | "INVALID";
    updated_at?: string;
  }>;
};
