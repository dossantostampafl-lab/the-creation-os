use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use creation_security_gateway::range_control::RangeControlClient;
use creation_security_gateway::replay::FileReplayStore;
use creation_security_gateway::sandbox::{probe, SandboxBackend};
use creation_security_gateway::server::Gateway;
use creation_security_gateway::validation::GatewayState;

fn main() {
    let configured = std::env::var("STF_SANDBOX_BACKEND").unwrap_or_else(|_| "auto".into());
    let kata = std::env::var("STF_KATA_AVAILABLE").as_deref() == Ok("1");
    let firecracker = std::env::var("STF_FIRECRACKER_AVAILABLE").as_deref() == Ok("1");
    let backend = match probe::select(&configured, kata, firecracker) {
        Ok(SandboxBackend::Unavailable) => {
            eprintln!("no isolated sandbox backend available; privileged execution disabled");
            SandboxBackend::Unavailable
        }
        Ok(backend) => {
            println!("isolated sandbox selected: {backend:?}");
            backend
        }
        Err(error) => {
            eprintln!("sandbox configuration rejected: {error}");
            std::process::exit(2);
        }
    };
    // Without a signing key nothing can be verified, so there is nothing to serve.
    let key = match std::env::var("STF_GATEWAY_SIGNING_KEY") {
        Ok(value) if value.len() >= 32 => value.into_bytes(),
        _ => {
            eprintln!("STF_GATEWAY_SIGNING_KEY (32+ characters) is required; refusing to serve");
            std::process::exit(2);
        }
    };
    let state_dir =
        std::env::var("STF_GATEWAY_STATE_DIR").unwrap_or_else(|_| "/var/lib/stf-gateway".into());
    if let Err(error) = std::fs::create_dir_all(&state_dir) {
        eprintln!("state directory unavailable: {error}");
        std::process::exit(2);
    }
    let replay = match FileReplayStore::open(&Path::new(&state_dir).join("nonces.log")) {
        Ok(store) => store,
        Err(error) => {
            eprintln!("replay store unavailable: {error}");
            std::process::exit(2);
        }
    };
    let prefixes = std::env::var("STF_ALLOWED_ENVIRONMENTS")
        .unwrap_or_else(|_| "cyber_range:".into())
        .split(',')
        .map(|item| item.trim().to_owned())
        .filter(|item| !item.is_empty())
        .collect();
    let range_control = match (
        std::env::var("CYBER_RANGE_CONTROL_ADDR")
            .ok()
            .filter(|value| !value.trim().is_empty()),
        std::env::var("CYBER_RANGE_CONTROL_TOKEN")
            .ok()
            .filter(|value| !value.trim().is_empty()),
    ) {
        (None, None) => None,
        (Some(addr), Some(token)) => match RangeControlClient::new(addr, token) {
            Ok(client) => Some(client),
            Err(_) => {
                eprintln!("Cyber Range control relay configuration rejected");
                std::process::exit(2);
            }
        },
        _ => {
            eprintln!("CYBER_RANGE_CONTROL_ADDR and CYBER_RANGE_CONTROL_TOKEN must be configured together");
            std::process::exit(2);
        }
    };
    let mut gateway = Gateway {
        state: GatewayState::new(Box::new(replay), prefixes),
        backend,
        key,
        range_control,
    };

    let address = std::env::var("STF_GATEWAY_ADDR").unwrap_or_else(|_| "0.0.0.0:7443".into());
    let listener = TcpListener::bind(&address).unwrap_or_else(|error| {
        eprintln!("cannot listen on {address}: {error}");
        std::process::exit(2);
    });
    for stream in listener.incoming().flatten() {
        let mut writer = match stream.try_clone() {
            Ok(writer) => writer,
            Err(_) => continue,
        };
        let mut line = String::new();
        if BufReader::new(stream).read_line(&mut line).is_ok() {
            let now = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map(|d| d.as_secs() as i64)
                .unwrap_or(0);
            let _ = writeln!(writer, "{}", gateway.handle_line(line.trim(), now));
        }
    }
}
