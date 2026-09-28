use std::collections::{HashMap, HashSet};

use crate::contracts::{ExecutionEnvelope, RequestedAction};
use crate::replay::ReplayStore;
use crate::signature;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DenyReason {
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
    Replay,
    PolicyNotPermit,
    MissingGrant,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GatewayDecision {
    Permit,
    Deny(DenyReason),
}

/// Everything the gateway remembers. Nothing here is ever loosened by a message from outside:
/// revocations, kills and mission versions only move toward "less allowed".
pub struct GatewayState {
    pub revoked_grants: HashSet<String>,
    pub min_mission_version: HashMap<String, u64>,
    pub killed_missions: HashSet<String>,
    pub global_kill: bool,
    pub allowed_environment_prefixes: Vec<String>,
    pub replay: Box<dyn ReplayStore>,
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
        }
    }
}

fn deny(reason: DenyReason) -> GatewayDecision {
    GatewayDecision::Deny(reason)
}

/// Parse -> integrity -> expiry/revocation -> mission/version -> target -> environment ->
/// action class -> invocation/replay -> policy decision. The first failure denies; nothing dispatches.
pub fn evaluate(
    state: &mut GatewayState,
    envelope: &ExecutionEnvelope,
    requested: &RequestedAction,
    key: &[u8],
    now_unix: i64,
) -> GatewayDecision {
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
    if envelope.decision != "permit" || envelope.decision_id.is_empty() {
        return deny(DenyReason::PolicyNotPermit);
    }
    // Last, because it spends the nonce: a request refused above must not burn it.
    if !state.replay.reserve(&envelope.nonce) {
        return deny(DenyReason::Replay);
    }
    GatewayDecision::Permit
}
