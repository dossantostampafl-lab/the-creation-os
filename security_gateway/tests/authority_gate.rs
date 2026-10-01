use creation_security_gateway::authority::AuthorityCheck;
use creation_security_gateway::contracts::{ExecutionEnvelope, RequestedAction};
use creation_security_gateway::replay::ReplayGuard;
use creation_security_gateway::sandbox::SandboxBackend;
use creation_security_gateway::server::Gateway;
use creation_security_gateway::signature::expected_signature;
use creation_security_gateway::validation::GatewayState;

const KEY: &[u8] = b"test-key";

struct RefuseAuthority;
impl AuthorityCheck for RefuseAuthority {
    fn claim(&self, _envelope: &ExecutionEnvelope) -> Result<(), String> {
        Err("revoked".into())
    }
}

struct PermitAuthority;
impl AuthorityCheck for PermitAuthority {
    fn claim(&self, _envelope: &ExecutionEnvelope) -> Result<(), String> {
        Ok(())
    }
}

fn envelope() -> ExecutionEnvelope {
    let mut value = ExecutionEnvelope {
        protocol_version: 2,
        run_id: "run-1".into(),
        execution_id: "exec-1".into(),
        contract_hash: "c".repeat(64),
        plan_hash: "p".repeat(64),
        mission_id: "m1".into(),
        mission_version: 1,
        action_id: "a1".into(),
        actor: "agent:red".into(),
        target: "juice-shop".into(),
        environment: "cyber_range:lab-a".into(),
        capability: "range.health.verify".into(),
        action_class: "validate".into(),
        risk_class: "R1".into(),
        decision: "permit".into(),
        decision_id: "d1".into(),
        grant_id: "g1".into(),
        expires_unix: 200,
        nonce: "n1".into(),
        parameters_hash: "abc".into(),
        tool_id: "range.health.verify".into(),
        signature: String::new(),
    };
    value.signature = expected_signature(&value, KEY);
    value
}

fn requested() -> RequestedAction {
    RequestedAction {
        mission_version: 1,
        target: "juice-shop".into(),
        environment: "cyber_range:lab-a".into(),
        capability: "range.health.verify".into(),
        action_class: "validate".into(),
        parameters_hash: "abc".into(),
        tool_id: "range.health.verify".into(),
        args_json: "{}".into(),
    }
}

fn line() -> String {
    serde_json::json!({"op": "execute", "envelope": envelope(), "requested": requested()})
        .to_string()
}

fn gateway(authority: Box<dyn AuthorityCheck>) -> Gateway {
    Gateway {
        state: GatewayState::new(
            Box::new(ReplayGuard::default()),
            vec!["cyber_range:".into()],
        )
        .with_authority(authority),
        backend: SandboxBackend::Kata,
        key: KEY.to_vec(),
    }
}

#[test]
fn a_valid_signature_still_cannot_reach_the_sandbox_when_runtime_authority_refuses() {
    let mut value = gateway(Box::new(RefuseAuthority));
    let reply = value.handle_line(&line(), 100);
    assert!(reply.contains("\"decision\":\"deny\""));
    assert!(reply.contains("RuntimeAuthorityDenied"));
}

#[test]
fn runtime_authority_must_claim_before_an_adapter_can_even_be_authorized() {
    let mut value = gateway(Box::new(PermitAuthority));
    let reply = value.handle_line(&line(), 100);
    assert!(reply.contains("\"decision\":\"permit\""));
    assert!(reply.contains("\"status\":\"authorized\""));
}
