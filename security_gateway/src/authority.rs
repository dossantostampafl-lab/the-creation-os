use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::Duration;

use serde_json::json;

use crate::contracts::ExecutionEnvelope;

/// Revalidates durable backend authority immediately before any sandbox effect.
///
/// Implementations must fail closed. A successful cryptographic envelope is necessary but not sufficient:
/// cancellation, revocation, expiry and persisted runtime bindings are authoritative at claim time.
pub trait AuthorityCheck: Send {
    fn claim(&self, envelope: &ExecutionEnvelope) -> Result<(), String>;
}

/// Default for an unconfigured gateway. Production never gains execution authority merely by starting.
pub struct DenyAuthority;

impl AuthorityCheck for DenyAuthority {
    fn claim(&self, _envelope: &ExecutionEnvelope) -> Result<(), String> {
        Err("runtime_authority_unavailable".into())
    }
}

pub struct HttpAuthority {
    host: String,
    port: u16,
    path: String,
    token: String,
    timeout: Duration,
}

impl HttpAuthority {
    pub fn new(url: String, token: String) -> Result<Self, String> {
        if token.len() < 32 {
            return Err("runtime authority token must be at least 32 characters".into());
        }
        let rest = url.strip_prefix("http://").ok_or_else(|| {
            "runtime authority URL must use internal http:// transport".to_string()
        })?;
        let (authority, path) = rest
            .split_once('/')
            .ok_or_else(|| "runtime authority URL must include an absolute path".to_string())?;
        let (host, port) = match authority.rsplit_once(':') {
            Some((host, port)) => {
                let port = port
                    .parse::<u16>()
                    .map_err(|_| "runtime authority URL has an invalid port".to_string())?;
                (host.to_owned(), port)
            }
            None => (authority.to_owned(), 80),
        };
        if host.is_empty() || path.is_empty() {
            return Err("runtime authority URL is incomplete".into());
        }
        Ok(Self {
            host,
            port,
            path: format!("/{path}"),
            token,
            timeout: Duration::from_secs(3),
        })
    }

    fn post_claim(&self, envelope: &ExecutionEnvelope) -> Result<(), String> {
        let body = json!({
            "execution_id": envelope.execution_id,
            "run_id": envelope.run_id,
            "contract_hash": envelope.contract_hash,
            "plan_hash": envelope.plan_hash,
            "tool_id": envelope.tool_id,
            "parameters_hash": envelope.parameters_hash,
        })
        .to_string();
        let request = format!(
            "POST {} HTTP/1.1\r\nHost: {}:{}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nX-STF-Service-Token: {}\r\nConnection: close\r\n\r\n{}",
            self.path,
            self.host,
            self.port,
            body.len(),
            self.token,
            body
        );
        let mut stream = TcpStream::connect((self.host.as_str(), self.port))
            .map_err(|error| format!("runtime authority unavailable: {error}"))?;
        stream
            .set_read_timeout(Some(self.timeout))
            .map_err(|error| format!("runtime authority timeout configuration failed: {error}"))?;
        stream
            .set_write_timeout(Some(self.timeout))
            .map_err(|error| format!("runtime authority timeout configuration failed: {error}"))?;
        stream
            .write_all(request.as_bytes())
            .map_err(|error| format!("runtime authority request failed: {error}"))?;
        stream
            .flush()
            .map_err(|error| format!("runtime authority request failed: {error}"))?;

        let mut response = String::new();
        stream
            .read_to_string(&mut response)
            .map_err(|error| format!("runtime authority response failed: {error}"))?;
        let status = response
            .lines()
            .next()
            .ok_or_else(|| "runtime authority returned an empty response".to_string())?;
        if !status.starts_with("HTTP/1.1 200 ") && !status.starts_with("HTTP/1.0 200 ") {
            return Err(format!("runtime authority denied claim: {status}"));
        }
        Ok(())
    }
}

impl AuthorityCheck for HttpAuthority {
    fn claim(&self, envelope: &ExecutionEnvelope) -> Result<(), String> {
        self.post_claim(envelope)
    }
}
