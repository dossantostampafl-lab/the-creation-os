use serde_json::{json, Value};

use crate::contracts::{ExecutionEnvelope, RequestedAction};
use crate::range_control::{RangeControlClient, RangeControlError};
use crate::sandbox::firecracker::FirecrackerSandbox;
use crate::sandbox::kata::KataSandbox;
use crate::sandbox::{Sandbox, SandboxBackend, SandboxError};
use crate::validation::{evaluate, GatewayDecision, GatewayState};

pub struct Gateway {
    pub state: GatewayState,
    pub backend: SandboxBackend,
    pub key: Vec<u8>,
    pub range_control: Option<RangeControlClient>,
}

fn reply(decision: &str, reasons: Vec<String>) -> String {
    json!({ "decision": decision, "reasons": reasons }).to_string()
}

/// The answer to an execute request: `decision` is the authorization outcome, `status` is what actually
/// happened (denied, authorized, executed), and `execution_id` exists only when work really ran.
fn reply_execute(
    decision: &str,
    status: &str,
    reasons: Vec<String>,
    execution_id: Option<String>,
) -> String {
    let mut value = json!({ "decision": decision, "status": status, "reasons": reasons });
    if let Some(id) = execution_id {
        value["execution_id"] = json!(id);
    }
    value.to_string()
}

impl Gateway {
    /// One JSON line in, one JSON line out. Control messages only ever tighten the state.
    pub fn handle_line(&mut self, line: &str, now_unix: i64) -> String {
        let message: Value = match serde_json::from_str(line) {
            Ok(value) => value,
            Err(_) => return reply("deny", vec!["malformed".into()]),
        };
        match message.get("op").and_then(Value::as_str) {
            Some("execute") => self.execute(&message, now_unix),
            Some("revoke_grant") => {
                if let Some(id) = message.get("grant_id").and_then(Value::as_str) {
                    self.state.revoked_grants.insert(id.to_owned());
                }
                reply("ok", vec![])
            }
            Some("set_mission_version") => {
                let mission = message.get("mission_id").and_then(Value::as_str);
                let version = message.get("version").and_then(Value::as_u64);
                if let (Some(mission), Some(version)) = (mission, version) {
                    let entry = self
                        .state
                        .min_mission_version
                        .entry(mission.to_owned())
                        .or_insert(0);
                    *entry = (*entry).max(version);
                }
                reply("ok", vec![])
            }
            Some("kill") => {
                match message.get("mission_id").and_then(Value::as_str) {
                    Some(mission) => {
                        self.state.killed_missions.insert(mission.to_owned());
                    }
                    None => self.state.global_kill = true,
                }
                reply("ok", vec![])
            }
            _ => reply("deny", vec!["unknown_op".into()]),
        }
    }

    fn execute(&mut self, message: &Value, now_unix: i64) -> String {
        let envelope: Result<ExecutionEnvelope, _> =
            serde_json::from_value(message["envelope"].clone());
        let requested: Result<RequestedAction, _> =
            serde_json::from_value(message["requested"].clone());
        let (Ok(envelope), Ok(requested)) = (envelope, requested) else {
            return reply_execute("deny", "denied", vec!["malformed".into()], None);
        };
        if let GatewayDecision::Deny(reason) =
            evaluate(&mut self.state, &envelope, &requested, &self.key, now_unix)
        {
            return reply_execute("deny", "denied", vec![format!("{reason:?}")], None);
        }
        if requested.tool_id == "range.health.verify" {
            if requested.capability != "range.health.verify"
                || !requested.environment.starts_with("cyber_range:")
                || requested.args_json.trim() != "{}"
            {
                return reply_execute(
                    "deny",
                    "denied",
                    vec!["RangeControlRequestInvalid".into()],
                    None,
                );
            }
            let Some(client) = self.range_control.as_ref() else {
                return reply_execute(
                    "deny",
                    "denied",
                    vec!["RangeControlUnavailable".into()],
                    None,
                );
            };
            return match client.verify_health() {
                Ok(()) => reply_execute(
                    "permit",
                    "executed",
                    vec![],
                    Some(format!("range-health:{}:{}", envelope.action_id, envelope.nonce)),
                ),
                Err(RangeControlError::Unavailable) => reply_execute(
                    "deny",
                    "denied",
                    vec!["RangeControlUnavailable".into()],
                    None,
                ),
                Err(RangeControlError::InvalidConfiguration | RangeControlError::InvalidResponse) => {
                    reply_execute(
                        "deny",
                        "denied",
                        vec!["RangeControlInvalidResponse".into()],
                        None,
                    )
                }
            };
        }
        let outcome = match self.backend {
            SandboxBackend::Kata => KataSandbox { available: true }
                .execute_allowlisted(&requested.tool_id, &requested.args_json),
            SandboxBackend::Firecracker => FirecrackerSandbox { available: true }
                .execute_allowlisted(&requested.tool_id, &requested.args_json),
            // No isolated backend: a permitted request still never runs anywhere.
            SandboxBackend::Unavailable => Err(SandboxError::Unavailable),
        };
        match outcome {
            Ok(execution_id) => reply_execute("permit", "executed", vec![], Some(execution_id)),
            // Authorized, but nothing ran: a permit is not an execution.
            Err(SandboxError::NotImplemented) => reply_execute(
                "permit",
                "authorized",
                vec!["ExecutionNotImplemented".into()],
                None,
            ),
            Err(SandboxError::NotAllowlisted) => {
                reply_execute("deny", "denied", vec!["ToolNotAllowlisted".into()], None)
            }
            Err(SandboxError::Unavailable) => {
                reply_execute("deny", "denied", vec!["SandboxUnavailable".into()], None)
            }
        }
    }
}
