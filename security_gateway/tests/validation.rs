use creation_security_gateway::contracts::{ExecutionEnvelope, RequestedAction};
use creation_security_gateway::replay::ReplayGuard;
use creation_security_gateway::signature::expected_signature;
use creation_security_gateway::validation::{evaluate, DenyReason, GatewayDecision, GatewayState};

const KEY: &[u8] = b"test-key";

fn envelope() -> ExecutionEnvelope {
    let mut e = ExecutionEnvelope {
        mission_id: "m1".into(),
        mission_version: 1,
        action_id: "a1".into(),
        actor: "agent".into(),
        target: "juice-shop".into(),
        environment: "cyber_range:lab-a".into(),
        capability: "range.validate".into(),
        action_class: "validate".into(),
        risk_class: "R2".into(),
        decision: "permit".into(),
        decision_id: "d1".into(),
        grant_id: "g1".into(),
        expires_unix: 200,
        nonce: "n1".into(),
        parameters_hash: "abc".into(),
        signature: String::new(),
    };
    e.signature = expected_signature(&e, KEY);
    e
}

fn requested() -> RequestedAction {
    RequestedAction {
        mission_version: 1,
        target: "juice-shop".into(),
        environment: "cyber_range:lab-a".into(),
        capability: "range.validate".into(),
        action_class: "validate".into(),
        parameters_hash: "abc".into(),
        tool_id: "sandbox.health.verify".into(),
        args_json: "{}".into(),
    }
}

fn sandbox_bound() -> (ExecutionEnvelope, RequestedAction) {
    let mut e = envelope();
    e.capability = "sandbox.health.verify".into();
    e.signature = expected_signature(&e, KEY);
    let mut r = requested();
    r.capability = "sandbox.health.verify".into();
    r.tool_id = "sandbox.health.verify".into();
    (e, r)
}

fn state() -> GatewayState {
    GatewayState::new(
        Box::new(ReplayGuard::default()),
        vec!["cyber_range:".into()],
    )
}

fn deny(reason: DenyReason) -> GatewayDecision {
    GatewayDecision::Deny(reason)
}

#[test]
fn permits_a_bound_request_once() {
    let mut s = state();
    assert_eq!(
        evaluate(&mut s, &envelope(), &requested(), KEY, 100),
        GatewayDecision::Permit
    );
    assert_eq!(
        evaluate(&mut s, &envelope(), &requested(), KEY, 100),
        deny(DenyReason::Replay)
    );
}

#[test]
fn tampered_envelope_fails_integrity() {
    let mut e = envelope();
    e.target = "other".into();
    assert_eq!(
        evaluate(&mut state(), &e, &requested(), KEY, 100),
        deny(DenyReason::BadSignature)
    );
}

#[test]
fn expired_revoked_and_killed_grants_are_denied() {
    assert_eq!(
        evaluate(&mut state(), &envelope(), &requested(), KEY, 200),
        deny(DenyReason::Expired)
    );
    let mut s = state();
    s.revoked_grants.insert("g1".into());
    assert_eq!(
        evaluate(&mut s, &envelope(), &requested(), KEY, 100),
        deny(DenyReason::Revoked)
    );
    let mut s = state();
    s.killed_missions.insert("m1".into());
    assert_eq!(
        evaluate(&mut s, &envelope(), &requested(), KEY, 100),
        deny(DenyReason::KillSwitch)
    );
    let mut s = state();
    s.global_kill = true;
    assert_eq!(
        evaluate(&mut s, &envelope(), &requested(), KEY, 100),
        deny(DenyReason::KillSwitch)
    );
}

#[test]
fn stale_mission_version_is_denied() {
    let mut s = state();
    s.min_mission_version.insert("m1".into(), 2);
    assert_eq!(
        evaluate(&mut s, &envelope(), &requested(), KEY, 100),
        deny(DenyReason::StaleMission)
    );
    let mut r = requested();
    r.mission_version = 2;
    assert_eq!(
        evaluate(&mut state(), &envelope(), &r, KEY, 100),
        deny(DenyReason::StaleMission)
    );
}

#[test]
fn target_environment_action_and_parameters_must_match() {
    let mut r = requested();
    r.target = "other".into();
    assert_eq!(
        evaluate(&mut state(), &envelope(), &r, KEY, 100),
        deny(DenyReason::TargetMismatch)
    );
    let mut r = requested();
    r.environment = "real:prod-a".into();
    assert_eq!(
        evaluate(&mut state(), &envelope(), &r, KEY, 100),
        deny(DenyReason::EnvironmentMismatch)
    );
    let mut r = requested();
    r.action_class = "exploit".into();
    assert_eq!(
        evaluate(&mut state(), &envelope(), &r, KEY, 100),
        deny(DenyReason::ActionClassMismatch)
    );
    let mut r = requested();
    r.parameters_hash = "bad".into();
    assert_eq!(
        evaluate(&mut state(), &envelope(), &r, KEY, 100),
        deny(DenyReason::ParametersTampered)
    );
}

#[test]
fn real_environments_are_off_unless_configured() {
    let mut e = envelope();
    e.environment = "real:prod-a".into();
    e.signature = expected_signature(&e, KEY);
    let mut r = requested();
    r.environment = "real:prod-a".into();
    assert_eq!(
        evaluate(&mut state(), &e, &r, KEY, 100),
        deny(DenyReason::EnvironmentNotAllowed)
    );
}

#[test]
fn missing_policy_decision_is_denied_and_does_not_burn_the_nonce() {
    let mut e = envelope();
    e.decision = "escalate".into();
    e.signature = expected_signature(&e, KEY);
    let mut s = state();
    assert_eq!(
        evaluate(&mut s, &e, &requested(), KEY, 100),
        deny(DenyReason::PolicyNotPermit)
    );
    assert_eq!(
        evaluate(&mut s, &envelope(), &requested(), KEY, 100),
        GatewayDecision::Permit
    );
}

#[test]
fn signature_matches_the_python_authorization_plane() {
    // Produced by backend/app/security_task_force/envelope.py for this exact envelope.
    assert_eq!(
        envelope().signature,
        "90f082e4f960680427a8e8337a2625f188bcaece8e865ee74add71c6cf4cedce"
    );
}

#[test]
fn file_replay_store_survives_a_restart() {
    use creation_security_gateway::replay::{FileReplayStore, ReplayStore};
    let path = std::env::temp_dir().join(format!("stf-replay-{}.log", std::process::id()));
    let _ = std::fs::remove_file(&path);
    assert!(FileReplayStore::open(&path).unwrap().reserve("n1"));
    assert!(!FileReplayStore::open(&path).unwrap().reserve("n1"));
    let _ = std::fs::remove_file(&path);
}

#[test]
fn server_denies_when_no_sandbox_and_tightens_on_control_messages() {
    use creation_security_gateway::sandbox::SandboxBackend;
    use creation_security_gateway::server::Gateway;
    let mut gateway = Gateway {
        state: state(),
        backend: SandboxBackend::Unavailable,
        key: KEY.to_vec(),
        range_control: None,
    };
    let (sandbox_envelope, sandbox_requested) = sandbox_bound();
    let line = serde_json::json!({
        "op": "execute",
        "envelope": sandbox_envelope,
        "requested": sandbox_requested
    })
    .to_string();
    assert!(gateway
        .handle_line(&line, 100)
        .contains("SandboxUnavailable"));
    gateway.handle_line(r#"{"op":"kill","mission_id":"m1"}"#, 100);
    let (killed_envelope, killed_requested) = sandbox_bound();
    let again = serde_json::json!({
        "op": "execute",
        "envelope": killed_envelope,
        "requested": killed_requested
    })
    .to_string();
    assert!(gateway.handle_line(&again, 100).contains("KillSwitch"));
    assert!(gateway.handle_line("not json", 100).contains("malformed"));
}

#[test]
fn server_permits_through_an_isolated_backend() {
    use creation_security_gateway::sandbox::SandboxBackend;
    use creation_security_gateway::server::Gateway;
    let mut gateway = Gateway {
        state: state(),
        backend: SandboxBackend::Kata,
        key: KEY.to_vec(),
        range_control: None,
    };
    let (sandbox_envelope, sandbox_requested) = sandbox_bound();
    let line = serde_json::json!({
        "op": "execute",
        "envelope": sandbox_envelope,
        "requested": sandbox_requested
    })
    .to_string();
    assert!(gateway.handle_line(&line, 100).contains("\"permit\""));
}

#[test]
fn a_permit_is_authorization_not_execution() {
    use creation_security_gateway::sandbox::SandboxBackend;
    use creation_security_gateway::server::Gateway;
    let mut gateway = Gateway {
        state: state(),
        backend: SandboxBackend::Kata,
        key: KEY.to_vec(),
        range_control: None,
    };
    let (sandbox_envelope, sandbox_requested) = sandbox_bound();
    let line = serde_json::json!({
        "op": "execute",
        "envelope": sandbox_envelope,
        "requested": sandbox_requested
    })
    .to_string();
    let reply: serde_json::Value = serde_json::from_str(&gateway.handle_line(&line, 100)).unwrap();
    assert_eq!(reply["decision"], "permit");
    assert_eq!(reply["status"], "authorized");
    assert!(
        reply.get("execution_id").is_none(),
        "nothing ran, so there is no execution id"
    );
}

#[test]
fn every_reply_to_an_execute_carries_a_status() {
    use creation_security_gateway::sandbox::SandboxBackend;
    use creation_security_gateway::server::Gateway;
    let mut gateway = Gateway {
        state: state(),
        backend: SandboxBackend::Unavailable,
        key: KEY.to_vec(),
        range_control: None,
    };
    let line =
        serde_json::json!({"op": "execute", "envelope": envelope(), "requested": requested()})
            .to_string();
    let reply: serde_json::Value = serde_json::from_str(&gateway.handle_line(&line, 100)).unwrap();
    assert_eq!(reply["decision"], "deny");
    assert_eq!(reply["status"], "denied");
}
