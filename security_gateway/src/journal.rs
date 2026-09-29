use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{self, BufRead, BufReader, Write};
use std::path::Path;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct JournalOutcome {
    pub decision: String,
    pub status: String,
    pub reasons: Vec<String>,
    pub execution_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BeginExecution {
    Fresh,
    Unknown,
    Finished(JournalOutcome),
}

pub trait ExecutionJournal: Send {
    fn begin(&mut self, execution_id: &str) -> io::Result<BeginExecution>;
    fn finish(&mut self, execution_id: &str, outcome: JournalOutcome) -> io::Result<()>;
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "state", rename_all = "snake_case")]
enum Record {
    Begun {
        execution_id: String,
    },
    Finished {
        execution_id: String,
        outcome: JournalOutcome,
    },
}

#[derive(Debug, Clone)]
enum State {
    Begun,
    Finished(JournalOutcome),
}

pub struct FileExecutionJournal {
    file: File,
    states: HashMap<String, State>,
}

impl FileExecutionJournal {
    pub fn open(path: impl AsRef<Path>) -> io::Result<Self> {
        let path = path.as_ref();
        let reader = OpenOptions::new()
            .create(true)
            .read(true)
            .append(true)
            .open(path)?;
        let mut states = HashMap::new();
        for line in BufReader::new(reader.try_clone()?).lines() {
            let line = line?;
            if line.trim().is_empty() {
                continue;
            }
            let record: Record = serde_json::from_str(&line)
                .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
            match record {
                Record::Begun { execution_id } => {
                    states.insert(execution_id, State::Begun);
                }
                Record::Finished {
                    execution_id,
                    outcome,
                } => {
                    states.insert(execution_id, State::Finished(outcome));
                }
            }
        }
        let file = OpenOptions::new().create(true).append(true).open(path)?;
        Ok(Self { file, states })
    }

    fn append(&mut self, record: &Record) -> io::Result<()> {
        serde_json::to_writer(&mut self.file, record).map_err(io::Error::other)?;
        self.file.write_all(b"\n")?;
        self.file.flush()?;
        self.file.sync_data()?;
        Ok(())
    }
}

impl ExecutionJournal for FileExecutionJournal {
    fn begin(&mut self, execution_id: &str) -> io::Result<BeginExecution> {
        match self.states.get(execution_id) {
            Some(State::Begun) => Ok(BeginExecution::Unknown),
            Some(State::Finished(outcome)) => Ok(BeginExecution::Finished(outcome.clone())),
            None => {
                let record = Record::Begun {
                    execution_id: execution_id.to_owned(),
                };
                self.append(&record)?;
                self.states.insert(execution_id.to_owned(), State::Begun);
                Ok(BeginExecution::Fresh)
            }
        }
    }

    fn finish(&mut self, execution_id: &str, outcome: JournalOutcome) -> io::Result<()> {
        let record = Record::Finished {
            execution_id: execution_id.to_owned(),
            outcome: outcome.clone(),
        };
        self.append(&record)?;
        self.states
            .insert(execution_id.to_owned(), State::Finished(outcome));
        Ok(())
    }
}

#[derive(Default)]
pub struct MemoryExecutionJournal {
    states: HashMap<String, State>,
}

impl ExecutionJournal for MemoryExecutionJournal {
    fn begin(&mut self, execution_id: &str) -> io::Result<BeginExecution> {
        match self.states.get(execution_id) {
            Some(State::Begun) => Ok(BeginExecution::Unknown),
            Some(State::Finished(outcome)) => Ok(BeginExecution::Finished(outcome.clone())),
            None => {
                self.states.insert(execution_id.to_owned(), State::Begun);
                Ok(BeginExecution::Fresh)
            }
        }
    }

    fn finish(&mut self, execution_id: &str, outcome: JournalOutcome) -> io::Result<()> {
        self.states
            .insert(execution_id.to_owned(), State::Finished(outcome));
        Ok(())
    }
}
