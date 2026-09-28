use std::collections::HashSet;
use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::Path;

/// Atomic reservation of a nonce. A nonce can be reserved once, ever.
pub trait ReplayStore: Send {
    fn reserve(&mut self, nonce: &str) -> bool;
}

#[derive(Default)]
pub struct ReplayGuard {
    seen: HashSet<String>,
}

impl ReplayGuard {
    pub fn consume(&mut self, nonce: &str) -> bool {
        self.seen.insert(nonce.to_owned())
    }
}

impl ReplayStore for ReplayGuard {
    fn reserve(&mut self, nonce: &str) -> bool {
        self.consume(nonce)
    }
}

/// Append-only nonce log: a restart does not forget what was already spent.
pub struct FileReplayStore {
    seen: HashSet<String>,
    file: File,
}

impl FileReplayStore {
    pub fn open(path: &Path) -> std::io::Result<Self> {
        let mut seen = HashSet::new();
        if path.exists() {
            for line in BufReader::new(File::open(path)?).lines() {
                seen.insert(line?);
            }
        }
        let file = OpenOptions::new().create(true).append(true).open(path)?;
        Ok(Self { seen, file })
    }
}

impl ReplayStore for FileReplayStore {
    fn reserve(&mut self, nonce: &str) -> bool {
        if nonce.is_empty() || nonce.contains('\n') || self.seen.contains(nonce) {
            return false;
        }
        // Persist before granting: if the write fails, the nonce is refused (fail closed).
        if writeln!(self.file, "{nonce}")
            .and_then(|_| self.file.sync_all())
            .is_err()
        {
            return false;
        }
        self.seen.insert(nonce.to_owned());
        true
    }
}
