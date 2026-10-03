use std::io::{Read, Write};
use std::net::TcpListener;
use std::thread;

use creation_security_gateway::contracts::{ExecutionEnvelope, RequestedAction};
use creation_security_gateway::range_control::RangeControlClient;
use creation_security_gateway::replay::ReplayGuard;
use creation_security_gateway::sandbox::SandboxBackend;
use creation_security_gateway::server::Gateway;
use creation_security_gateway::signature::expected_signature;
use creation_security_gateway::validation::GatewayState;

const KEY: &[u8] = b"test-key";

fn envelope(nonce: &str) -> ExecutionEnvelope {
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
        nonce: nonce.into(),
        parameters_hash: "abc".into(),
        signature: String::new(),
    };
    value.signature = expected_signature(&value, KEY);
    value
}

fn requested(tool_id: &str) -> RequestedAction {
    RequestedAction {
        mission_version: 1,
        target: "juice-shop".into(),
        environment: "cyber_range:lab-a".into(),
        capability: "range.health.verify".into(),
        action_class: "validate".into(),
        parameters_hash: "abc".into(),
        tool_id: tool_id.into(),
        args_json: "{}".into(),
    }
}

fn state() -> GatewayState {
    GatewayState::new(
        Box::new(ReplayGuard::default()),
        vec!["cyber_range:".into()],
    )
}

fn health_server() -> (String, thread::JoinHandle<String>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = listener.local_addr().unwrap().to_string();
    let handle = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let mut request = [0_u8; 4096];
        let n = stream.read(&mut request).unwrap();
        let body = r#"{"status":"ok","environment":"CYBER_RANGE"}"#;
        let response = format!(
            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
            body.len(), body
        );
        stream.write_all(response.as_bytes()).unwrap();
        String::from_utf8_lossy(&request[..n]).to_string()
    });
    (addr, handle)
}

#[test]
fn range_health_executes_only_through_authenticated_control_relay() {
    let (addr, seen) = health_server();
    let token = "r".repeat(40);
    let mut gateway = Gateway {
        state: state(),
        backend: SandboxBackend::Unavailable,
        key: KEY.to_vec(),
        range_control: Some(RangeControlClient::new(addr, token.clone()).unwrap()),
    };
    let line = serde_json::json!({
        "op": "execute",
        "envelope": envelope("range-health-1"),
        "requested": requested("range.health.verify")
    })
    .to_string();

    let reply: serde_json::Value = serde_json::from_str(&gateway.handle_line(&line, 100)).unwrap();

    assert_eq!(reply["decision"], "permit");
    assert_eq!(reply["status"], "executed");
    assert!(reply["execution_id"]
        .as_str()
        .unwrap()
        .starts_with("range-control:range.health.verify:"));
    let request = seen.join().unwrap();
    assert!(request.starts_with("GET /health HTTP/1.1\r\n"));
    assert!(request.contains(&format!("Authorization: Bearer {token}\r\n")));
}

#[test]
fn a_different_tool_never_uses_the_range_control_bypass() {
    let client = RangeControlClient::new("127.0.0.1:9".into(), "r".repeat(40)).unwrap();
    let mut gateway = Gateway {
        state: state(),
        backend: SandboxBackend::Unavailable,
        key: KEY.to_vec(),
        range_control: Some(client),
    };
    let line = serde_json::json!({
        "op": "execute",
        "envelope": envelope("range-health-2"),
        "requested": requested("sandbox.health.verify")
    })
    .to_string();

    let reply: serde_json::Value = serde_json::from_str(&gateway.handle_line(&line, 100)).unwrap();

    assert_eq!(reply["decision"], "deny");
    assert_eq!(reply["status"], "denied");
    assert_eq!(reply["reasons"][0], "ToolCapabilityMismatch");
}

#[test]
fn range_health_rejects_unbound_arguments_before_any_control_connection() {
    let client = RangeControlClient::new("127.0.0.1:9".into(), "r".repeat(40)).unwrap();
    let mut gateway = Gateway {
        state: state(),
        backend: SandboxBackend::Unavailable,
        key: KEY.to_vec(),
        range_control: Some(client),
    };
    let mut request = requested("range.health.verify");
    request.args_json = r#"{"target":"anything"}"#.into();
    let line = serde_json::json!({
        "op": "execute",
        "envelope": envelope("range-health-args"),
        "requested": request
    })
    .to_string();

    let reply: serde_json::Value = serde_json::from_str(&gateway.handle_line(&line, 100)).unwrap();

    assert_eq!(reply["decision"], "deny");
    assert_eq!(reply["status"], "denied");
    assert_eq!(reply["reasons"][0], "RangeControlRequestInvalid");
}

fn post_server(path: &'static str, body: &'static str) -> (String, thread::JoinHandle<String>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = listener.local_addr().unwrap().to_string();
    let handle = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let mut request = [0_u8; 4096];
        let n = stream.read(&mut request).unwrap();
        let response = format!(
            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
            body.len(), body
        );
        stream.write_all(response.as_bytes()).unwrap();
        let text = String::from_utf8_lossy(&request[..n]).to_string();
        assert!(text.starts_with(&format!("POST {path} HTTP/1.1\r\n")));
        text
    });
    (addr, handle)
}

#[test]
fn scenario_start_uses_only_the_declared_scenario_route() {
    let body = r#"{"scenario_id":"juice-shop-baseline","status":"active"}"#;
    let (addr, seen) = post_server("/scenarios/juice-shop-baseline/start", body);
    let mut gateway = Gateway {
        state: state(),
        backend: SandboxBackend::Unavailable,
        key: KEY.to_vec(),
        range_control: Some(RangeControlClient::new(addr, "r".repeat(40)).unwrap()),
    };
    let mut e = envelope("range-start-1");
    e.target = "juice-shop-baseline".into();
    e.capability = "range.scenario.start".into();
    e.signature = expected_signature(&e, KEY);
    let mut r = requested("range.scenario.start");
    r.target = "juice-shop-baseline".into();
    r.capability = "range.scenario.start".into();
    let line = serde_json::json!({"op":"execute","envelope":e,"requested":r}).to_string();

    let reply: serde_json::Value = serde_json::from_str(&gateway.handle_line(&line, 100)).unwrap();

    assert_eq!(reply["decision"], "permit");
    assert_eq!(reply["status"], "executed");
    seen.join().unwrap();
}

#[test]
fn range_reset_control_is_cleanup_only_and_uses_fixed_reset_route() {
    let body = r#"{"status":"reset","removed_state_files":1}"#;
    let (addr, seen) = post_server("/reset", body);
    let mut gateway = Gateway {
        state: state(),
        backend: SandboxBackend::Unavailable,
        key: KEY.to_vec(),
        range_control: Some(RangeControlClient::new(addr, "r".repeat(40)).unwrap()),
    };

    let before: serde_json::Value = serde_json::from_str(
        &gateway.handle_line(r#"{"op":"range_reset","mission_id":"m1"}"#, 100),
    )
    .unwrap();
    assert_eq!(before["decision"], "deny");
    gateway.handle_line(r#"{"op":"kill","mission_id":"m1"}"#, 100);

    let unbound: serde_json::Value =
        serde_json::from_str(&gateway.handle_line(r#"{"op":"range_reset"}"#, 100)).unwrap();
    assert_eq!(unbound["decision"], "deny");

    let wrong: serde_json::Value = serde_json::from_str(
        &gateway.handle_line(r#"{"op":"range_reset","mission_id":"m2"}"#, 100),
    )
    .unwrap();
    assert_eq!(wrong["decision"], "deny");

    let reply: serde_json::Value = serde_json::from_str(
        &gateway.handle_line(r#"{"op":"range_reset","mission_id":"m1"}"#, 100),
    )
    .unwrap();

    assert_eq!(reply["decision"], "ok");
    seen.join().unwrap();
}

#[test]
fn campaign_start_uses_only_the_declared_campaign_route() {
    let body = r#"{"campaign_id":"stf-foundation-v1","status":"active"}"#;
    let (addr, seen) = post_server("/campaigns/stf-foundation-v1/start", body);
    let mut gateway = Gateway {
        state: state(),
        backend: SandboxBackend::Unavailable,
        key: KEY.to_vec(),
        range_control: Some(RangeControlClient::new(addr, "r".repeat(40)).unwrap()),
    };
    let mut e = envelope("campaign-start-1");
    e.target = "stf-foundation-v1".into();
    e.capability = "range.campaign.start".into();
    e.signature = expected_signature(&e, KEY);
    let mut r = requested("range.campaign.start");
    r.target = "stf-foundation-v1".into();
    r.capability = "range.campaign.start".into();
    let line = serde_json::json!({"op":"execute","envelope":e,"requested":r}).to_string();

    let reply: serde_json::Value = serde_json::from_str(&gateway.handle_line(&line, 100)).unwrap();

    assert_eq!(reply["decision"], "permit");
    assert_eq!(reply["status"], "executed");
    seen.join().unwrap();
}
