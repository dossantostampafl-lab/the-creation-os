use std::io::{Read, Write};
use std::net::TcpListener;
use std::thread;

use creation_security_gateway::range_control::{RangeControlClient, RangeControlError};

fn one_response(response: &'static str) -> (String, thread::JoinHandle<String>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = listener.local_addr().unwrap().to_string();
    let handle = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let mut request = [0_u8; 4096];
        let n = stream.read(&mut request).unwrap();
        stream.write_all(response.as_bytes()).unwrap();
        String::from_utf8_lossy(&request[..n]).to_string()
    });
    (addr, handle)
}

#[test]
fn health_uses_only_fixed_authenticated_route_and_accepts_cyber_range_identity() {
    let body = r#"{"status":"ok","environment":"CYBER_RANGE"}"#;
    let response = Box::leak(format!(
        "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        body.len(), body
    ).into_boxed_str());
    let (addr, request) = one_response(response);
    let token = "r".repeat(40);
    let client = RangeControlClient::new(addr, token.clone()).unwrap();

    client.verify_health().unwrap();

    let request = request.join().unwrap();
    assert!(request.starts_with("GET /health HTTP/1.1\r\n"));
    assert!(request.contains(&format!("Authorization: Bearer {token}\r\n")));
    assert!(!request.contains("http://"));
    assert!(!request.contains("/scenarios/"));
}

#[test]
fn health_rejects_wrong_environment_even_on_http_200() {
    let body = r#"{"status":"ok","environment":"PRODUCTION"}"#;
    let response = Box::leak(format!(
        "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        body.len(), body
    ).into_boxed_str());
    let (addr, request) = one_response(response);
    let client = RangeControlClient::new(addr, "r".repeat(40)).unwrap();

    assert_eq!(client.verify_health(), Err(RangeControlError::InvalidResponse));
    request.join().unwrap();
}

#[test]
fn range_control_requires_a_real_control_token() {
    assert_eq!(
        RangeControlClient::new("127.0.0.1:7071".into(), "short".into()).unwrap_err(),
        RangeControlError::InvalidConfiguration
    );
}
