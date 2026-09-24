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
        Ok("dispatch accepted by Firecracker adapter".into())
    }
}
