#[path = "../src/auth.rs"]
mod auth;
#[path = "../src/contracts.rs"]
mod contracts;
#[path = "../src/replay.rs"]
mod replay;

use contracts::ExecutionEnvelope;

fn envelope() -> ExecutionEnvelope {
    ExecutionEnvelope {
        mission_id: "m1".into(),
        mission_version: 1,
        action_id: "a1".into(),
        actor: "agent".into(),
        target: "juice-shop".into(),
        environment: "CYBER_RANGE".into(),
        capability: "range.validate".into(),
        action_class: "validate".into(),
        risk_class: "R2".into(),
        decision_id: "d1".into(),
        grant_id: "g1".into(),
        expires_unix: 200,
        nonce: "n1".into(),
        parameters_hash: "abc".into(),
        signature: "sig".into(),
    }
}

#[test]
fn rejects_cross_environment_and_expiry() {
    assert!(auth::validate(&envelope(), "REAL_AUTHORIZED", 100, "abc").is_err());
    assert!(auth::validate(&envelope(), "CYBER_RANGE", 201, "abc").is_err());
}

#[test]
fn rejects_parameter_tamper() {
    assert!(auth::validate(&envelope(), "CYBER_RANGE", 100, "bad").is_err());
}

#[test]
fn rejects_nonce_replay() {
    let mut guard = replay::ReplayGuard::default();
    assert!(guard.consume("n1"));
    assert!(!guard.consume("n1"));
}
