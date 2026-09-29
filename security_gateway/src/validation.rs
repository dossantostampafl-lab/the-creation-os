use std::collections::{HashMap, HashSet};

use subtle::ConstantTimeEq;

use crate::contracts::{ExecutionEnvelope, RequestedAction};
use crate::replay::ReplayStore;
use crate::signature;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DenyReason {
    ProtocolVersion,
    RuntimeBindingMissing,
    BadSignature,
    KillSwitch,
    Expired,
    Revoked,
    StaleMission,
    TargetMismatch,
    EnvironmentMismatch,
    EnvironmentNotAllowed,
    ActionClassMismatch,
    CapabilityMismatch,
    ParametersTampered,
    ToolMismatch,
    Replay,
    PolicyNotPermit,
    MissingGrant,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GatewayDecision {
    Permit,
    Deny(DenyReason),
}

pub struct GatewayState {
    pub revoked_grants: HashSet<String>,
    pub min_mission_version: HashMap<String, u64>,
    pub killed_missions: HashSet<String>,
    pub global_kill: bool,
    pub allowed_environment_prefixes: Vec<String>,
    pub replay: Box<dyn ReplayStore>,
    control_token: Option<Vec<u8>>,
}

impl GatewayState {
    pub fn new(replay: Box<dyn ReplayStore>, allowed_environment_prefixes: Vec<String>) -> Self {
        Self {
            revoked_grants: HashSet::new(),
            min_mission_version: HashMap::new(),
            killed_missions: HashSet::new(),
            global_kill: false,
            allowed_environment_prefixes,
            replay,
            control_token: None,
        }
    }

    pub fn with_control_token(mut self, token: impl Into<Vec<u8>>) -> Self {
        self.control_token = Some(token.into());
        self
    }

    pub fn control_allowed(&self, supplied: Option<&str>) -> bool {
        let Some(expected) = self.control_token.as_deref() else {
            return false;
        };
        let Some(supplied) = supplied else {
            return false;
        };
        expected.len() == supplied.len() && bool::from(expected.ct_eq(supplied.as_bytes()))
    }
}

fn deny(reason: DenyReason) -> GatewayDecision {
    GatewayDecision::Deny(reason)
}

pub fn evaluate(
    state: &mut GatewayState,
    envelope: &ExecutionEnvelope,
    requested: &RequestedAction,
    key: &[u8],
    now_unix: i64,
) -> GatewayDecision {
    if envelope.protocol_version != 2 {
        return deny(DenyReason::ProtocolVersion);
    }
    if envelope.run_id.is_empty()
        || envelope.execution_id.is_empty()
        || envelope.contract_hash.is_empty()
        || envelope.plan_hash.is_empty()
        || envelope.tool_id.is_empty()
    {
        return deny(DenyReason::RuntimeBindingMissing);
    }
    if !signature::verify_signature(envelope, key) {
        return deny(DenyReason::BadSignature);
    }
    if state.global_kill || state.killed_missions.contains(&envelope.mission_id) {
        return deny(DenyReason::KillSwitch);
    }
    if envelope.grant_id.is_empty() {
        return deny(DenyReason::MissingGrant);
    }
    if envelope.expires_unix <= now_unix {
        return deny(DenyReason::Expired);
    }
    if state.revoked_grants.contains(&envelope.grant_id) {
        return deny(DenyReason::Revoked);
    }
    let floor = state
        .min_mission_version
        .get(&envelope.mission_id)
        .copied()
        .unwrap_or(0);
    if envelope.mission_version != requested.mission_version || envelope.mission_version < floor {
        return deny(DenyReason::StaleMission);
    }
    if envelope.target != requested.target {
        return deny(DenyReason::TargetMismatch);
    }
    if envelope.environment != requested.environment {
        return deny(DenyReason::EnvironmentMismatch);
    }
    if !state
        .allowed_environment_prefixes
        .iter()
        .any(|prefix| envelope.environment.starts_with(prefix.as_str()))
    {
        return deny(DenyReason::EnvironmentNotAllowed);
    }
    if envelope.action_class != requested.action_class {
        return deny(DenyReason::ActionClassMismatch);
    }
    if envelope.capability != requested.capability {
        return deny(DenyReason::CapabilityMismatch);
    }
    if envelope.parameters_hash != requested.parameters_hash {
        return deny(DenyReason::ParametersTampered);
    }
    if envelope.tool_id != requested.tool_id || envelope.tool_id != envelope.capability {
        return deny(DenyReason::ToolMismatch);
    }
    if envelope.decision != "permit" || envelope.decision_id.is_empty() {
        return deny(DenyReason::PolicyNotPermit);
    }
    if !state.replay.reserve(&envelope.nonce) {
        return deny(DenyReason::Replay);
    }
    GatewayDecision::Permit
}
