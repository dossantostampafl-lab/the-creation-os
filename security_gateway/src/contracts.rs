use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionEnvelope {
    pub protocol_version: u8,
    pub run_id: String,
    pub execution_id: String,
    pub contract_hash: String,
    pub plan_hash: String,
    pub mission_id: String,
    pub mission_version: u64,
    pub action_id: String,
    pub actor: String,
    pub target: String,
    pub environment: String,
    pub capability: String,
    pub action_class: String,
    pub risk_class: String,
    pub decision: String,
    pub decision_id: String,
    pub grant_id: String,
    pub expires_unix: i64,
    pub nonce: String,
    pub parameters_hash: String,
    pub tool_id: String,
    pub signature: String,
}

/// What the caller now asks to run. It is compared with what the signed envelope authorized.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RequestedAction {
    pub mission_version: u64,
    pub target: String,
    pub environment: String,
    pub capability: String,
    pub action_class: String,
    pub parameters_hash: String,
    pub tool_id: String,
    pub args_json: String,
}
