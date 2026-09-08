export type Mission = {
  id: string;
  title: string;
  objective: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
};

export type Task = {
  id: string;
  mission_id: string;
  step_id: string;
  universe_id: string | null;
  agent_id: string | null;
  status: string;
  attempt_count: number;
  max_attempts: number;
};

export type Universe = {
  id: string;
  code: string;
  name: string;
  active: boolean;
};

export type Agent = {
  id: string;
  code: string;
  name: string;
  universe_id: string;
  active: boolean;
};

export type MemorySummary = {
  conversation: number;
  mission: number;
  universe: number;
  conscious: number;
  total: number;
};

export type SystemState = {
  projection: string;
  position: number;
  generated_at: string;
  missions: Mission[];
  tasks: Task[];
  universes: Universe[];
  agents: Agent[];
  memory: MemorySummary;
  pulse: Record<string, { value: unknown; observed_at: string }>;
  counts: {
    missions: number;
    running_missions: number;
    tasks: number;
    ready_tasks: number;
    running_tasks: number;
    failed_tasks: number;
    active_universes: number;
    active_agents: number;
  };
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

export type ChronicleEvent = {
  event_id: string;
  position: number;
  correlation_id: string;
  causation_id: string | null;
  actor_role: string;
  event_type: string;
  aggregate_type: string;
  aggregate_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type Session = {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
};
