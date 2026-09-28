use serde_json::{json, Value};

use crate::contracts::{ExecutionEnvelope, RequestedAction};
use crate::sandbox::firecracker::FirecrackerSandbox;
use crate::sandbox::kata::KataSandbox;
use crate::sandbox::{Sandbox, SandboxBackend};
use crate::validation::{evaluate, GatewayDecision, GatewayState};

pub struct Gateway {
    pub state: GatewayState,
    pub backend: SandboxBackend,
    pub key: Vec<u8>,
}

fn reply(decision: &str, reasons: Vec<String>) -> String {
    json!({ "decision": decision, "reasons": reasons }).to_string()
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
            return reply("deny", vec!["malformed".into()]);
        };
        if let GatewayDecision::Deny(reason) =
            evaluate(&mut self.state, &envelope, &requested, &self.key, now_unix)
        {
            return reply("deny", vec![format!("{reason:?}")]);
        }
        let outcome = match self.backend {
            SandboxBackend::Kata => KataSandbox { available: true }
                .execute_allowlisted(&requested.tool_id, &requested.args_json),
            SandboxBackend::Firecracker => FirecrackerSandbox { available: true }
                .execute_allowlisted(&requested.tool_id, &requested.args_json),
            // No isolated backend: a permitted request still never runs anywhere.
            SandboxBackend::Unavailable => return reply("deny", vec!["SandboxUnavailable".into()]),
        };
        match outcome {
            Ok(_) => reply("permit", vec![]),
            Err(reason) => reply("deny", vec![reason]),
        }
    }
}
