export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
};

export type Conversation = {
  id: string;
  creator_id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type GodResponse = {
  id: string;
  conversation_id: string;
  message_id: string;
  god_message_id: string;
  interaction_type: "DIRECT_RESPONSE" | "INFORMATIONAL" | "POTENTIAL" | "UNSUPPORTED";
  reply: { message: string; policy_version: string };
  potential_detected: boolean;
  next_action: string;
  fingerprint: string;
  created_at: string;
  completed_at: string;
};

export type TrinityResponse = {
  god_interaction_id: string;
  conversation_id: string;
  interaction_type: string;
  sophia_understanding_id: string;
  rockmam_assessment_id: string;
  assessment_result: "VIABLE" | "NOT_VIABLE" | "REQUIRES_CREATOR";
  understanding_created: boolean;
  assessment_created: boolean;
  god_consolidated_result: {
    creator_approval_required: boolean;
    creates_inception: boolean;
    creates_mission: boolean;
    assessment_result: string;
    assessment_fingerprint: string;
  };
};

export type Inception = {
  id: string;
  conversation_id: string;
  title: string;
  description: string;
  status: string;
};

export type Mission = {
  id: string;
  title: string;
  objective: string;
  status: string;
};

export type Capability = {
  id: string;
  name: string;
  description: string;
};

export type Agent = {
  id: string;
  name: string;
  description: string;
  universe: string;
  capabilities: Capability[];
  priority: number;
  status: string;
  version: number;
  heartbeat_at: string | null;
  created_at: string;
  updated_at: string;
  enabled: boolean;
};

export type Universe = {
  id: string;
  code: string;
  name: string;
  active: boolean;
  created_at: string;
};

export type ChronicleEntry = {
  id: string;
  event_id: string;
  position: number;
  actor_role: string;
  event_type: string;
  aggregate_type: string;
  aggregate_id: string | null;
  created_at: string;
};

export type Pulse = {
  status: string;
  database: { status?: string; detail?: string };
  redis: { status?: string; detail?: string };
  redis_streams: { status?: string; detail?: string };
  chronicles_chain: {
    valid: boolean;
    reason: string | null;
    first_invalid_event_id: string | null;
  };
  active_universes: number;
  active_agents: number;
  running_missions: number;
  pending_inceptions: number;
  pending_tasks: number;
  failed_tasks: number;
  error_count: number;
  timestamp: string;
};

export type ChatItem = {
  id: string;
  role: "creator" | "god" | "trinity";
  text: string;
  meta?: string;
};
