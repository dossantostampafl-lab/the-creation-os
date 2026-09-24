mod auth;
mod contracts;
mod replay;
mod sandbox;

fn main() {
    // Gateway starts without an execution listener until live grant validation
    // and an isolated sandbox backend are healthy. Fail closed by design.
    println!("creation-security-gateway: execution disabled until validated runtime is configured");
}
