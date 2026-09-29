use serde_json::{json, Value};

use crate::contracts::{ExecutionEnvelope, RequestedAction};
use crate::sandbox::firecracker::FirecrackerSandbox;
use crate::sandbox::kata::KataSandbox;
use crate::sandbox::{Sandbox, SandboxBackend, SandboxError};
use crate::validation::{evaluate_preclaim, reserve_nonce, GatewayDecision, GatewayState};

pub struct Gateway {
    pub state: GatewayState,
    pub backend: SandboxBackend,
    pub key: Vec<u8>,
}

fn reply(decision: &str, reasons: Vec<String>) -> String {
    json!({ "decision": decision, "reasons": reasons }).to_string()
}

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
    pub fn handle_line(&mut self, line: &str, now_unix: i64) -> String {
        if line.len() > 64 * 1024 {
            return reply("deny", vec!["message_too_large".into()]);
        }
        let message: Value = match serde_json::from_str(line) {
            Ok(value) => value,
            Err(_) => return reply("deny", vec!["malformed".into()]),
        };
        match message.get("op").and_then(Value::as_str) {
            Some("execute") => self.execute(&message, now_unix),
            Some("revoke_grant") | Some("set_mission_version") | Some("kill") => {
                self.control(&message)
            }
            _ => reply("deny", vec!["unknown_op".into()]),
        }
    }

    fn control(&mut self, message: &Value) -> String {
        let token = message.get("service_token").and_then(Value::as_str);
        if !self.state.control_allowed(token) {
            return reply("deny", vec!["control_auth_required".into()]);
        }
        match message.get("op").and_then(Value::as_str) {
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

        // Cryptographic and structural checks happen before the authority service sees the claim.
        if let GatewayDecision::Deny(reason) =
            evaluate_preclaim(&self.state, &envelope, &requested, &self.key, now_unix)
        {
            return reply_execute("deny", "denied", vec![format!("{reason:?}")], None);
        }

        // A signed permit is never sufficient: cancellation/revocation are re-read from durable state here.
        if self.state.claim_authority(&envelope).is_err() {
            return reply_execute(
                "deny",
                "denied",
                vec!["RuntimeAuthorityDenied".into()],
                None,
            );
        }

        // Spend replay protection only after a successful, idempotent pre-effect claim.
        if let GatewayDecision::Deny(reason) = reserve_nonce(&mut self.state, &envelope.nonce) {
            return reply_execute("deny", "denied", vec![format!("{reason:?}")], None);
        }

        let outcome = match self.backend {
            SandboxBackend::Kata => KataSandbox { available: true }
                .execute_allowlisted(&requested.tool_id, &requested.args_json),
            SandboxBackend::Firecracker => FirecrackerSandbox { available: true }
                .execute_allowlisted(&requested.tool_id, &requested.args_json),
            SandboxBackend::Unavailable => Err(SandboxError::Unavailable),
        };
        match outcome {
            Ok(execution_id) => reply_execute("permit", "executed", vec![], Some(execution_id)),
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
