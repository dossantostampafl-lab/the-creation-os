use super::{Sandbox, SandboxBackend, SandboxError};

pub struct FirecrackerSandbox {
    pub available: bool,
}

impl Sandbox for FirecrackerSandbox {
    fn backend(&self) -> SandboxBackend {
        SandboxBackend::Firecracker
    }

    fn execute_allowlisted(&self, tool_id: &str, _args_json: &str) -> Result<String, SandboxError> {
        if !self.available {
            return Err(SandboxError::Unavailable);
        }
        if tool_id != "range.health.verify" {
            return Err(SandboxError::NotAllowlisted);
        }
        // Running work inside Firecracker is an operator-supplied integration that has not been connected or
        // exercised on a real host. Until it is, this adapter never reports work as executed.
        Err(SandboxError::NotImplemented)
    }
}
