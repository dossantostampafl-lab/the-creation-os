use creation_security_gateway::journal::{
    BeginExecution, ExecutionJournal, FileExecutionJournal, JournalOutcome,
};

fn path(label: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!(
        "stf-execution-journal-{label}-{}-{}.jsonl",
        std::process::id(),
        std::thread::current().name().unwrap_or("test")
    ))
}

#[test]
fn interrupted_execution_survives_restart_as_unknown_and_is_never_fresh_again() {
    let path = path("unknown");
    let _ = std::fs::remove_file(&path);
    {
        let mut journal = FileExecutionJournal::open(&path).unwrap();
        assert_eq!(journal.begin("exec-1").unwrap(), BeginExecution::Fresh);
    }
    {
        let mut journal = FileExecutionJournal::open(&path).unwrap();
        assert_eq!(journal.begin("exec-1").unwrap(), BeginExecution::Unknown);
    }
    let _ = std::fs::remove_file(&path);
}

#[test]
fn finished_outcome_survives_restart_and_is_returned_verbatim() {
    let path = path("done");
    let _ = std::fs::remove_file(&path);
    let outcome = JournalOutcome {
        decision: "permit".into(),
        status: "executed".into(),
        reasons: vec![],
        execution_id: Some("exec-2".into()),
    };
    {
        let mut journal = FileExecutionJournal::open(&path).unwrap();
        assert_eq!(journal.begin("exec-2").unwrap(), BeginExecution::Fresh);
        journal.finish("exec-2", outcome.clone()).unwrap();
    }
    {
        let mut journal = FileExecutionJournal::open(&path).unwrap();
        assert_eq!(
            journal.begin("exec-2").unwrap(),
            BeginExecution::Finished(outcome)
        );
    }
    let _ = std::fs::remove_file(&path);
}
