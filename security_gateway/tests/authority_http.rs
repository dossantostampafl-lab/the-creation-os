use std::io::{Read, Write};
use std::net::TcpListener;
use std::thread;

use creation_security_gateway::authority::{AuthorityCheck, HttpAuthority};
use creation_security_gateway::contracts::ExecutionEnvelope;

fn envelope() -> ExecutionEnvelope {
    ExecutionEnvelope {
        protocol_version: 2,
        run_id: "run-1".into(),
        execution_id: "exec-1".into(),
        contract_hash: "contract-1".into(),
        plan_hash: "plan-1".into(),
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
        parameters_hash: "params-1".into(),
        tool_id: "range.health.verify".into(),
        signature: "sig".into(),
    }
}

fn serve_once(status: &str) -> (String, thread::JoinHandle<String>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let status = status.to_owned();
    let handle = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let mut request = Vec::new();
        let mut buffer = [0_u8; 4096];
        loop {
            let count = stream.read(&mut buffer).unwrap();
            if count == 0 {
                break;
            }
            request.extend_from_slice(&buffer[..count]);
            let text = String::from_utf8_lossy(&request);
            let Some(header_end) = text.find("\r\n\r\n") else {
                continue;
            };
            let content_length = text[..header_end]
                .lines()
                .find_map(|line| {
                    let (name, value) = line.split_once(':')?;
                    name.eq_ignore_ascii_case("content-length")
                        .then(|| value.trim().parse::<usize>().unwrap())
                })
                .unwrap_or(0);
            if request.len() >= header_end + 4 + content_length {
                break;
            }
        }
        let response = format!(
            "HTTP/1.1 {status}\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{{}}"
        );
        stream.write_all(response.as_bytes()).unwrap();
        String::from_utf8(request).unwrap()
    });
    (format!("http://{address}/api/v1/deus/security-missions/internal/execution-claims"), handle)
}

#[test]
fn remote_authority_posts_only_runtime_bindings_with_service_identity() {
    let (url, server) = serve_once("200 OK");
    let authority = HttpAuthority::new(url, "service-token-that-is-at-least-32-bytes".into()).unwrap();
    authority.claim(&envelope()).unwrap();
    let request = server.join().unwrap();

    assert!(request.starts_with("POST /api/v1/deus/security-missions/internal/execution-claims HTTP/1.1"));
    assert!(request.contains("X-STF-Service-Token: service-token-that-is-at-least-32-bytes"));
    assert!(request.contains("\"execution_id\":\"exec-1\""));
    assert!(request.contains("\"run_id\":\"run-1\""));
    assert!(request.contains("\"contract_hash\":\"contract-1\""));
    assert!(request.contains("\"plan_hash\":\"plan-1\""));
    assert!(request.contains("\"tool_id\":\"range.health.verify\""));
    assert!(request.contains("\"parameters_hash\":\"params-1\""));
    assert!(!request.contains("juice-shop"));
    assert!(!request.contains("args_json"));
}

#[test]
fn remote_authority_fails_closed_on_non_200_response() {
    let (url, server) = serve_once("409 Conflict");
    let authority = HttpAuthority::new(url, "service-token-that-is-at-least-32-bytes".into()).unwrap();
    assert!(authority.claim(&envelope()).is_err());
    server.join().unwrap();
}
