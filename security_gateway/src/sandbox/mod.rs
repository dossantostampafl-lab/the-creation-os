pub mod probe;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SandboxBackend { Kata, Firecracker, Unavailable }

pub trait Sandbox {
    fn backend(&self) -> SandboxBackend;
    fn execute_allowlisted(&self, tool_id: &str, args_json: &str) -> Result<String, String>;
}
