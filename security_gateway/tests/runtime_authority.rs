use creation_security_gateway::contracts::{ExecutionEnvelope, RequestedAction};
use creation_security_gateway::replay::ReplayGuard;
use creation_security_gateway::sandbox::SandboxBackend;
use creation_security_gateway::server::Gateway;
use creation_security_gateway::signature::expected_signature;
use creation_security_gateway::validation::{evaluate, GatewayDecision, GatewayState};

const KEY: &[u8] = b"test-key";

fn envelope() -> ExecutionEnvelope {
    let mut value = ExecutionEnvelope {
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

fn state() -> GatewayState {
    GatewayState::new(
        Box::new(ReplayGuard::default()),
        vec!["cyber_range:".into()],
    )
}

#[test]
fn envelope_serializes_the_protocol_v2_runtime_binding() {
    let value = serde_json::to_value(envelope()).unwrap();
    assert_eq!(value["protocol_version"], 2);
    assert_eq!(value["run_id"], "run-1");
    assert_eq!(value["execution_id"], "exec-1");
    assert_eq!(
        value["contract_hash"],
        "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    );
    assert_eq!(
        value["plan_hash"],
        "pppppppppppppppppppppppppppppppppppppppppppppppppppppppppppppppp"
    );
    assert_eq!(value["tool_id"], "range.health.verify");
}

#[test]
fn changing_the_effective_tool_is_never_permitted() {
    let mut request = requested();
    request.tool_id = "range.health.verify.other".into();
    assert_ne!(
        evaluate(&mut state(), &envelope(), &request, KEY, 100),
        GatewayDecision::Permit
    );
}

#[test]
fn unauthenticated_control_messages_fail_closed() {
    let mut gateway = Gateway {
        state: state(),
        backend: SandboxBackend::Unavailable,
        key: KEY.to_vec(),
    };
    let reply = gateway.handle_line(r#"{"op":"kill","mission_id":"m1"}"#, 100);
    assert!(reply.contains("deny"));
    assert!(reply.contains("control_auth_required"));
}
