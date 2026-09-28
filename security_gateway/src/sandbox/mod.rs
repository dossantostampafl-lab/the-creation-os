pub mod firecracker;
pub mod kata;
pub mod probe;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SandboxBackend {
    Kata,
    Firecracker,
    Unavailable,
}

/// Why an isolated backend did not run the work. `Ok` from a backend carries the execution id and is the
/// only thing that may ever be reported as executed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SandboxError {
    /// The backend was selected but is not available right now.
    Unavailable,
    /// The tool is not on the allowlist.
    NotAllowlisted,
    /// Authorization passed, but no real integration with the isolation runtime exists yet.
    NotImplemented,
}

pub trait Sandbox {
    fn backend(&self) -> SandboxBackend;
    /// Returns the execution id of work that actually ran.
    fn execute_allowlisted(&self, tool_id: &str, args_json: &str) -> Result<String, SandboxError>;
}
