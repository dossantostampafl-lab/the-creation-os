use std::fmt;
use std::io::{Read, Write};
use std::net::{Ipv4Addr, TcpStream};
use std::time::Duration;

use serde_json::Value;

const MAX_RESPONSE_BYTES: u64 = 64 * 1024;
const IO_TIMEOUT: Duration = Duration::from_secs(3);

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RangeControlError {
    InvalidConfiguration,
    Unavailable,
    InvalidResponse,
}

#[derive(Clone)]
pub struct RangeControlClient {
    addr: String,
    host: String,
    token: String,
}

impl fmt::Debug for RangeControlClient {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("RangeControlClient")
            .field("addr", &self.addr)
            .field("host", &self.host)
            .field("token", &"<redacted>")
            .finish()
    }
}

fn valid_scenario_id(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.is_empty() || bytes.len() > 64 || value.contains("..") {
        return false;
    }
    bytes[0].is_ascii_alphanumeric()
        && bytes
            .iter()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(*byte, b'.' | b'_' | b'-'))
}

impl RangeControlClient {
    pub fn new(addr: String, token: String) -> Result<Self, RangeControlError> {
        if token.len() < 32
            || addr.len() > 255
            || addr.contains('/')
            || addr.contains('@')
            || addr.chars().any(char::is_whitespace)
        {
            return Err(RangeControlError::InvalidConfiguration);
        }
        let Some((host, port)) = addr.rsplit_once(':') else {
            return Err(RangeControlError::InvalidConfiguration);
        };
        let port_ok = port
            .parse::<u16>()
            .ok()
            .filter(|value| *value > 0)
            .is_some();
        let host_ok = host == "host.docker.internal"
            || host
                .parse::<Ipv4Addr>()
                .ok()
                .is_some_and(|ip| ip.is_private() || ip.is_loopback());
        if !host_ok || !port_ok {
            return Err(RangeControlError::InvalidConfiguration);
        }
        let host = host.to_owned();
        Ok(Self { addr, host, token })
    }

    fn request(&self, method: &str, path: &str) -> Result<Value, RangeControlError> {
        let mut stream =
            TcpStream::connect(&self.addr).map_err(|_| RangeControlError::Unavailable)?;
        stream
            .set_read_timeout(Some(IO_TIMEOUT))
            .map_err(|_| RangeControlError::Unavailable)?;
        stream
            .set_write_timeout(Some(IO_TIMEOUT))
            .map_err(|_| RangeControlError::Unavailable)?;

        let content_length = if method == "POST" {
            "Content-Length: 0\r\n"
        } else {
            ""
        };
        let request = format!(
            "{method} {path} HTTP/1.1\r\nHost: {}\r\nAuthorization: Bearer {}\r\n{content_length}Connection: close\r\n\r\n",
            self.host, self.token
        );
        stream
            .write_all(request.as_bytes())
            .map_err(|_| RangeControlError::Unavailable)?;

        let mut response = Vec::new();
        stream
            .take(MAX_RESPONSE_BYTES + 1)
            .read_to_end(&mut response)
            .map_err(|_| RangeControlError::Unavailable)?;
        if response.len() as u64 > MAX_RESPONSE_BYTES {
            return Err(RangeControlError::InvalidResponse);
        }
        let text =
            std::str::from_utf8(&response).map_err(|_| RangeControlError::InvalidResponse)?;
        let Some((head, body)) = text.split_once("\r\n\r\n") else {
            return Err(RangeControlError::InvalidResponse);
        };
        let status = head.lines().next().unwrap_or_default();
        if !(status.starts_with("HTTP/1.1 200 ") || status.starts_with("HTTP/1.0 200 ")) {
            return Err(RangeControlError::InvalidResponse);
        }
        serde_json::from_str(body).map_err(|_| RangeControlError::InvalidResponse)
    }

    pub fn verify_health(&self) -> Result<(), RangeControlError> {
        let payload = self.request("GET", "/health")?;
        if payload.get("status").and_then(Value::as_str) != Some("ok")
            || payload.get("environment").and_then(Value::as_str) != Some("CYBER_RANGE")
        {
            return Err(RangeControlError::InvalidResponse);
        }
        Ok(())
    }

    pub fn start_scenario(&self, scenario_id: &str) -> Result<(), RangeControlError> {
        if !valid_scenario_id(scenario_id) {
            return Err(RangeControlError::InvalidConfiguration);
        }
        let payload = self.request("POST", &format!("/scenarios/{scenario_id}/start"))?;
        if payload.get("scenario_id").and_then(Value::as_str) != Some(scenario_id)
            || payload.get("status").and_then(Value::as_str) != Some("active")
        {
            return Err(RangeControlError::InvalidResponse);
        }
        Ok(())
    }

    pub fn verify_scenario(&self, scenario_id: &str) -> Result<bool, RangeControlError> {
        if !valid_scenario_id(scenario_id) {
            return Err(RangeControlError::InvalidConfiguration);
        }
        let payload = self.request("GET", "/state")?;
        if payload.get("environment").and_then(Value::as_str) != Some("CYBER_RANGE") {
            return Err(RangeControlError::InvalidResponse);
        }
        let Some(scenarios) = payload.get("scenarios").and_then(Value::as_array) else {
            return Err(RangeControlError::InvalidResponse);
        };
        Ok(scenarios.iter().any(|scenario| {
            scenario.get("scenario_id").and_then(Value::as_str) == Some(scenario_id)
                && scenario.get("status").and_then(Value::as_str) == Some("active")
        }))
    }

    pub fn start_campaign(&self, campaign_id: &str) -> Result<(), RangeControlError> {
        if !valid_scenario_id(campaign_id) {
            return Err(RangeControlError::InvalidConfiguration);
        }
        let payload = self.request("POST", &format!("/campaigns/{campaign_id}/start"))?;
        if payload.get("campaign_id").and_then(Value::as_str) != Some(campaign_id)
            || payload.get("status").and_then(Value::as_str) != Some("active")
        {
            return Err(RangeControlError::InvalidResponse);
        }
        Ok(())
    }

    pub fn advance_campaign(&self, campaign_id: &str) -> Result<(), RangeControlError> {
        if !valid_scenario_id(campaign_id) {
            return Err(RangeControlError::InvalidConfiguration);
        }
        let payload = self.request("POST", &format!("/campaigns/{campaign_id}/advance"))?;
        let status = payload.get("status").and_then(Value::as_str);
        if payload.get("campaign_id").and_then(Value::as_str) != Some(campaign_id)
            || !matches!(status, Some("active") | Some("completed"))
        {
            return Err(RangeControlError::InvalidResponse);
        }
        Ok(())
    }

    pub fn campaign_completed(&self, campaign_id: &str) -> Result<bool, RangeControlError> {
        if !valid_scenario_id(campaign_id) {
            return Err(RangeControlError::InvalidConfiguration);
        }
        let payload = self.request("GET", &format!("/campaigns/{campaign_id}/state"))?;
        if payload.get("campaign_id").and_then(Value::as_str) != Some(campaign_id) {
            return Err(RangeControlError::InvalidResponse);
        }
        match payload.get("status").and_then(Value::as_str) {
            Some("completed") => Ok(true),
            Some("active") => Ok(false),
            _ => Err(RangeControlError::InvalidResponse),
        }
    }

    pub fn reset(&self) -> Result<(), RangeControlError> {
        let payload = self.request("POST", "/reset")?;
        if payload.get("status").and_then(Value::as_str) != Some("reset") {
            return Err(RangeControlError::InvalidResponse);
        }
        Ok(())
    }
}
