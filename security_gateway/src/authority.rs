use crate::contracts::ExecutionEnvelope;

/// Revalidates durable backend authority immediately before any sandbox effect.
///
/// Implementations must fail closed. A successful cryptographic envelope is necessary but not sufficient:
/// cancellation, revocation, expiry and persisted runtime bindings are authoritative at claim time.
pub trait AuthorityCheck: Send {
    fn claim(&self, envelope: &ExecutionEnvelope) -> Result<(), String>;
}

/// Default for an unconfigured gateway. Production never gains execution authority merely by starting.
pub struct DenyAuthority;

impl AuthorityCheck for DenyAuthority {
    fn claim(&self, _envelope: &ExecutionEnvelope) -> Result<(), String> {
        Err("runtime_authority_unavailable".into())
    }
}
