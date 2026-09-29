use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use creation_security_gateway::journal::FileExecutionJournal;
use creation_security_gateway::replay::FileReplayStore;
use creation_security_gateway::sandbox::{probe, SandboxBackend};
use creation_security_gateway::server::Gateway;
use creation_security_gateway::validation::GatewayState;

fn required_secret(name: &str) -> Vec<u8> {
    match std::env::var(name) {
        Ok(value) if value.len() >= 32 => value.into_bytes(),
        _ => {
            eprintln!("{name} (32+ characters) is required; refusing to serve");
            std::process::exit(2);
        }
    }
}

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
    let key = required_secret("STF_GATEWAY_SIGNING_KEY");
    let control_token = required_secret("STF_GATEWAY_CONTROL_TOKEN");
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
    let execution_journal =
        match FileExecutionJournal::open(Path::new(&state_dir).join("executions.jsonl")) {
            Ok(journal) => journal,
            Err(error) => {
                eprintln!("execution journal unavailable: {error}");
                std::process::exit(2);
            }
        };
    let prefixes = std::env::var("STF_ALLOWED_ENVIRONMENTS")
        .unwrap_or_else(|_| "cyber_range:".into())
        .split(',')
        .map(|item| item.trim().to_owned())
        .filter(|item| !item.is_empty())
        .collect();
    let mut gateway = Gateway {
        state: GatewayState::new(Box::new(replay), prefixes)
            .with_control_token(control_token)
            .with_execution_journal(Box::new(execution_journal)),
        backend,
        key,
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
