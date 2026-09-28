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
        // Authorization is enforced by the gateway; running work inside Kata is an operator-supplied
        // integration that has not been exercised on a real host, so no work is executed here.
        Ok("authorized for the Kata boundary; no work executed by this adapter".into())
    }
}
