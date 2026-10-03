use std::io::{Read, Write};
use std::net::TcpStream;
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

#[derive(Debug, Clone)]
pub struct RangeControlClient {
    addr: String,
    host: String,
    token: String,
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
        if host.is_empty() || port.parse::<u16>().ok().filter(|value| *value > 0).is_none() {
            return Err(RangeControlError::InvalidConfiguration);
        }
        Ok(Self {
            addr,
            host: host.to_owned(),
            token,
        })
    }

    pub fn verify_health(&self) -> Result<(), RangeControlError> {
        let mut stream = TcpStream::connect(&self.addr).map_err(|_| RangeControlError::Unavailable)?;
        stream
            .set_read_timeout(Some(IO_TIMEOUT))
            .map_err(|_| RangeControlError::Unavailable)?;
        stream
            .set_write_timeout(Some(IO_TIMEOUT))
            .map_err(|_| RangeControlError::Unavailable)?;
        let request = format!(
            "GET /health HTTP/1.1\r\nHost: {}\r\nAuthorization: Bearer {}\r\nConnection: close\r\n\r\n",
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
        let text = std::str::from_utf8(&response).map_err(|_| RangeControlError::InvalidResponse)?;
        let Some((head, body)) = text.split_once("\r\n\r\n") else {
            return Err(RangeControlError::InvalidResponse);
        };
        let status = head.lines().next().unwrap_or_default();
        if !(status.starts_with("HTTP/1.1 200 ") || status.starts_with("HTTP/1.0 200 ")) {
            return Err(RangeControlError::InvalidResponse);
        }
        let payload: Value =
            serde_json::from_str(body).map_err(|_| RangeControlError::InvalidResponse)?;
        if payload.get("status").and_then(Value::as_str) != Some("ok")
            || payload.get("environment").and_then(Value::as_str) != Some("CYBER_RANGE")
        {
            return Err(RangeControlError::InvalidResponse);
        }
        Ok(())
    }
}
