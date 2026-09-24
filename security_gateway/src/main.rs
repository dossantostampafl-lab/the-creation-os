use creation_security_gateway::sandbox::probe;

fn main() {
    let configured = std::env::var("STF_SANDBOX_BACKEND").unwrap_or_else(|_| "auto".into());
    let kata = std::env::var("STF_KATA_AVAILABLE").as_deref() == Ok("1");
    let firecracker = std::env::var("STF_FIRECRACKER_AVAILABLE").as_deref() == Ok("1");
    match probe::select(&configured, kata, firecracker) {
        Ok(creation_security_gateway::sandbox::SandboxBackend::Unavailable) => {
            eprintln!("no isolated sandbox backend available; privileged execution disabled");
        }
        Ok(backend) => println!("isolated sandbox selected: {backend:?}"),
        Err(error) => {
            eprintln!("sandbox configuration rejected: {error}");
            std::process::exit(2);
        }
    }
}
