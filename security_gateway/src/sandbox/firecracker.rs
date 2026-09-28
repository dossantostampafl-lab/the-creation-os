use super::{Sandbox, SandboxBackend};

pub struct FirecrackerSandbox {
    pub available: bool,
}

impl Sandbox for FirecrackerSandbox {
    fn backend(&self) -> SandboxBackend {
        SandboxBackend::Firecracker
    }

    fn execute_allowlisted(&self, tool_id: &str, _args_json: &str) -> Result<String, String> {
        if !self.available {
            return Err("Firecracker unavailable".into());
        }
        if tool_id != "range.health.verify" {
            return Err("tool is not allowlisted".into());
        }
        // Authorization is enforced by the gateway; running work inside Firecracker is an operator-supplied
        // integration that has not been exercised on a real host, so no work is executed here.
        Ok("authorized for the Firecracker boundary; no work executed by this adapter".into())
    }
}
