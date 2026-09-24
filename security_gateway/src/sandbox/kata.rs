use super::{Sandbox, SandboxBackend};

pub struct KataSandbox {
    pub available: bool,
}

impl Sandbox for KataSandbox {
    fn backend(&self) -> SandboxBackend {
        SandboxBackend::Kata
    }

    fn execute_allowlisted(&self, tool_id: &str, _args_json: &str) -> Result<String, String> {
        if !self.available {
            return Err("Kata unavailable".into());
        }
        if tool_id != "range.health.verify" {
            return Err("tool is not allowlisted".into());
        }
        Ok("dispatch accepted by Kata adapter".into())
    }
}
