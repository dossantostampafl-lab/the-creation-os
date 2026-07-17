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

export type MissionManifestation = {
  id: string;
  mission_id: string;
  decision_id: string;
  manifestation_state: "PENDING" | "MANIFESTED" | "FAILED";
  manifestation_payload: Record<string, unknown>;
  manifestation_fingerprint: string;
  audit_metadata: Record<string, unknown>;
  created_at: string;
  manifested_at: string | null;
};

export type CapabilityFramework = {
  id: string | null;
  capability_id: string;
  name: string;
  description: string;
  version: string;
  connector_id: string;
  connector_capability: string;
  enabled: boolean;
  permissions: string[];
  dependencies: string[];
  metadata: Record<string, string>;
  mandatory: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type AutomationExecution = {
  id: string;
  creator_id: string;
  connector_id: string;
  capability: string;
  idempotency_key: string;
  request_fingerprint: string;
  status: string;
  result_payload: Record<string, unknown>;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string;
};

export type Opportunity = {
  id: string;
  title: string;
  universe: string;
  category: string;
  status: string;
  summary: string;
  explanation: string;
  confidence: number;
  impact: number;
  urgency: number;
  risk: number;
  priority_score: number;
  recommended_action: string;
  evidence: { observations?: Array<Record<string, unknown>> };
  risks: Record<string, unknown>;
  scoring: Record<string, unknown>;
  detected_at: string;
  expires_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  rejection_reason: string | null;
  inception_id: string | null;
  created_at: string;
  updated_at: string;
};

export type PerceptionSource = {
  id: string;
  name: string;
  universe: string;
  provider: string;
  capability_name: string;
  connector_name: string;
  enabled: boolean;
  state: string;
  schedule_interval_seconds: number;
  minimum_interval_seconds: number;
  last_started_at: string | null;
  last_succeeded_at: string | null;
  last_failed_at: string | null;
  failure_count: number;
  max_consecutive_failures: number;
  next_run_at: string | null;
  last_cursor: string | null;
  created_at: string;
  updated_at: string;
};

export type PerceptionRun = {
  id: string;
  source_id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  observations_count: number;
  opportunities_count: number;
  attempts_count: number;
  error_code: string | null;
  error_message: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type PerceptionRunResult = {
  source: PerceptionSource;
  run: PerceptionRun;
  observations_count: number;
  opportunities_count: number;
  notifications_count: number;
};

export type CreatorNotification = {
  id: string;
  recipient_actor_id: string;
  type: string;
  title: string;
  message: string;
  opportunity_id: string | null;
  priority_score: number | null;
  status: string;
  created_at: string;
  read_at: string | null;
  acknowledged_at: string | null;
};

export type ChatItem = {
  id: string;
  role: "creator" | "god" | "trinity";
  text: string;
  meta?: string;
};
