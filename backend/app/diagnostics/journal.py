from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class JournalFull(RuntimeError):
    pass

class DiagnosticJournal:
    def __init__(self, root: Path, max_bytes: int = 100*1024*1024):
        if root.is_symlink():
            raise ValueError('journal root is not allowed to be a symlink')
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root, self.max_bytes = root, max_bytes
        self.path = root/'journal.sqlite'
        if self.path.is_symlink():
            raise ValueError('unsafe journal path')
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY, data TEXT, bytes INTEGER, acknowledged INTEGER DEFAULT 0, created_at REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT)')
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=2)
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA max_page_count='+str(max(16, self.max_bytes//4096)))
        try:
            with db:
                yield db
        finally:
            db.close()

    def append(self, observation: dict) -> None:
        serialized = json.dumps(observation, sort_keys=True)
        with self.connect() as db:
            if db.execute('SELECT 1 FROM observations WHERE id=?', (observation['id'],)).fetchone():
                return
            db.execute('DELETE FROM observations WHERE acknowledged=1 AND created_at<?', (time.time()-7*86400,))
            used = db.execute('SELECT COALESCE(SUM(bytes),0) FROM observations').fetchone()[0]
            if used + len(serialized.encode()) > self.max_bytes:
                self._full()
                raise JournalFull('diagnostic journal capacity reached')
            try:
                db.execute('INSERT INTO observations(id,data,bytes,created_at) VALUES(?,?,?,?)', (observation['id'],serialized,len(serialized.encode()),time.time()))
                marker = self.root/'spool-full.json'
                if marker.exists() and not marker.is_symlink():
                    marker.unlink()
            except sqlite3.OperationalError as exc:
                if 'full' in str(exc).lower():
                    self._full()
                    raise JournalFull('diagnostic journal capacity reached') from exc
                raise

    def _full(self):
        path = self.root/'spool-full.json'
        if path.is_symlink():
            raise ValueError('unsafe journal marker')
        with path.open('w') as handle:
            json.dump({'status':'spool_full','observed_at':time.time(),'new_observations_admitted':False},handle)
            handle.flush()
            os.fsync(handle.fileno())

    def pending(self, limit: int = 100) -> list[dict]:
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT data FROM observations WHERE acknowledged=0 ORDER BY created_at,id LIMIT ?', (limit,))]

    def ack(self, observation_id: str) -> None:
        with self.connect() as db:
            db.execute('UPDATE observations SET acknowledged=1 WHERE id=?', (observation_id,))

    def bind_creator(self, creator_id: str) -> None:
        with self.connect() as db:
            found = db.execute("SELECT value FROM metadata WHERE key='creator'").fetchone()
            if found and found[0] != creator_id:
                raise ValueError('diagnostic journal belongs to another Creator')
            db.execute("INSERT OR IGNORE INTO metadata VALUES('creator',?)",(creator_id,))

    def get_rules(self) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT value FROM metadata WHERE key='rules'").fetchone()
            return json.loads(row[0]) if row else {}

    def set_rules(self, data: dict) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO metadata VALUES('rules',?)", (json.dumps(data),))
