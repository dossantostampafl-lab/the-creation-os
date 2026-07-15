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

export type Agent = {
  id: string;
  name: string;
  universe?: string;
  universe_name?: string;
  status?: string;
  active?: boolean;
  enabled?: boolean;
};

export type ChatItem = {
  id: string;
  role: "creator" | "god" | "trinity";
  text: string;
  meta?: string;
};
