use creation_security_gateway::authority::AuthorityCheck;
use creation_security_gateway::contracts::{ExecutionEnvelope, RequestedAction};
use creation_security_gateway::journal::{ExecutionJournal, FileExecutionJournal, JournalOutcome};
use creation_security_gateway::replay::ReplayGuard;
use creation_security_gateway::sandbox::SandboxBackend;
use creation_security_gateway::server::Gateway;
use creation_security_gateway::signature::expected_signature;
use creation_security_gateway::validation::GatewayState;

const KEY: &[u8] = b"test-key";

struct PermitAuthority;
impl AuthorityCheck for PermitAuthority {
    fn claim(&self, _envelope: &ExecutionEnvelope) -> Result<(), String> {
        Ok(())
    }
}

fn path(label: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!("stf-gateway-journal-{label}-{}.jsonl", std::process::id()))
}

fn envelope(execution_id: &str, nonce: &str) -> ExecutionEnvelope {
    let mut value = ExecutionEnvelope {
        protocol_version: 2,
        run_id: "run-1".into(),
        execution_id: execution_id.into(),
        contract_hash: "c".repeat(64),
        plan_hash: "p".repeat(64),
        mission_id: "m1".into(),
        mission_version: 1,
        action_id: "a1".into(),
        actor: "agent:red".into(),
        target: "juice-shop".into(),
        environment: "cyber_range:lab-a".into(),
        capability: "range.health.verify".into(),
        action_class: "validate".into(),
        risk_class: "R1".into(),
        decision: "permit".into(),
        decision_id: "d1".into(),
        grant_id: "g1".into(),
        expires_unix: 200,
        nonce: nonce.into(),
        parameters_hash: "abc".into(),
        tool_id: "range.health.verify".into(),
        signature: String::new(),
    };
    value.signature = expected_signature(&value, KEY);
    value
}

fn requested() -> RequestedAction {
    RequestedAction {
        mission_version: 1,
        target: "juice-shop".into(),
        environment: "cyber_range:lab-a".into(),
        capability: "range.health.verify".into(),
        action_class: "validate".into(),
        parameters_hash: "abc".into(),
        tool_id: "range.health.verify".into(),
        args_json: "{}".into(),
    }
}

fn line(execution_id: &str, nonce: &str) -> String {
    serde_json::json!({
        "op": "execute",
        "envelope": envelope(execution_id, nonce),
        "requested": requested()
    })
    .to_string()
}

fn gateway(journal: FileExecutionJournal) -> Gateway {
    Gateway {
        state: GatewayState::new(Box::new(ReplayGuard::default()), vec!["cyber_range:".into()])
            .with_authority(Box::new(PermitAuthority))
            .with_execution_journal(Box::new(journal)),
        backend: SandboxBackend::Kata,
        key: KEY.to_vec(),
    }
}

#[test]
fn interrupted_execution_is_unknown_after_restart_before_any_adapter_call() {
    let path = path("unknown");
    let _ = std::fs::remove_file(&path);
    let mut journal = FileExecutionJournal::open(&path).unwrap();
    journal.begin("exec-unknown").unwrap();
    drop(journal);

    let mut value = gateway(FileExecutionJournal::open(&path).unwrap());
    let reply: serde_json::Value =
        serde_json::from_str(&value.handle_line(&line("exec-unknown", "nonce-u"), 100)).unwrap();
    assert_eq!(reply["decision"], "deny");
    assert_eq!(reply["status"], "unknown");
    assert_eq!(reply["reasons"][0], "ExecutionOutcomeUnknown");
    let _ = std::fs::remove_file(&path);
}

#[test]
fn finished_execution_is_replayed_verbatim_after_restart() {
    let path = path("finished");
    let _ = std::fs::remove_file(&path);
    let outcome = JournalOutcome {
        decision: "permit".into(),
        status: "authorized".into(),
        reasons: vec!["ExecutionNotImplemented".into()],
        execution_id: None,
    };
    let mut journal = FileExecutionJournal::open(&path).unwrap();
    journal.begin("exec-finished").unwrap();
    journal.finish("exec-finished", outcome).unwrap();
    drop(journal);

    let mut value = gateway(FileExecutionJournal::open(&path).unwrap());
    let reply: serde_json::Value =
        serde_json::from_str(&value.handle_line(&line("exec-finished", "nonce-f"), 100)).unwrap();
    assert_eq!(reply["decision"], "permit");
    assert_eq!(reply["status"], "authorized");
    assert_eq!(reply["reasons"][0], "ExecutionNotImplemented");
    let _ = std::fs::remove_file(&path);
}
