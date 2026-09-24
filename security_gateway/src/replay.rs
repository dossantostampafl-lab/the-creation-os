use std::collections::HashSet;

#[derive(Default)]
pub struct ReplayGuard { seen: HashSet<String> }

impl ReplayGuard {
    pub fn consume(&mut self, nonce: &str) -> bool {
        if self.seen.contains(nonce) { return false; }
        self.seen.insert(nonce.to_owned());
        true
    }
}
