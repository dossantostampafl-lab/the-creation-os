use creation_security_gateway::sandbox::{self, SandboxBackend};

#[test]
fn unavailable_fails_closed() {
    assert_eq!(
        sandbox::probe::select("auto", false, false).unwrap(),
        SandboxBackend::Unavailable
    );
}

#[test]
fn selects_only_supported_backend() {
    assert_eq!(
        sandbox::probe::select("auto", true, false).unwrap(),
        SandboxBackend::Kata
    );
    assert_eq!(
        sandbox::probe::select("auto", false, true).unwrap(),
        SandboxBackend::Firecracker
    );
    assert!(sandbox::probe::select("firecracker", true, false).is_err());
}
