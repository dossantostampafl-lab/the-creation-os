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
    def __init__(self, root: Path, max_bytes: int = 100 * 1024 * 1024):
        if root.is_symlink():
            raise ValueError("journal root is not allowed to be a symlink")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = root
        self.max_bytes = max_bytes
        self.path = root / "journal.sqlite"
        if self.path.is_symlink():
            raise ValueError("unsafe journal path")

        with self.connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS observations(
                    id TEXT PRIMARY KEY,
                    data TEXT,
                    bytes INTEGER,
                    acknowledged INTEGER DEFAULT 0,
                    created_at REAL,
                    sequence INTEGER
                )
                """
            )
            columns = {
                row[1] for row in db.execute("PRAGMA table_info(observations)").fetchall()
            }
            if "sequence" not in columns:
                db.execute("ALTER TABLE observations ADD COLUMN sequence INTEGER")
            db.execute(
                """
                UPDATE observations
                SET sequence = rowid
                WHERE sequence IS NULL
                """
            )
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_diagnostic_observations_sequence "
                "ON observations(sequence)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT)"
            )
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=2)
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA max_page_count=" + str(max(16, self.max_bytes // 4096)))
        try:
            with db:
                yield db
        finally:
            db.close()

    def append(self, observation: dict) -> None:
        serialized = json.dumps(observation, sort_keys=True)
        encoded_bytes = len(serialized.encode())
        with self.connect() as db:
            if db.execute(
                "SELECT 1 FROM observations WHERE id=?",
                (observation["id"],),
            ).fetchone():
                return
            db.execute(
                "DELETE FROM observations WHERE acknowledged=1 AND created_at<?",
                (time.time() - 7 * 86400,),
            )
            used = int(
                db.execute(
                    "SELECT COALESCE(SUM(bytes),0) FROM observations"
                ).fetchone()[0]
            )
            if used + encoded_bytes > self.max_bytes:
                self._full(db)
                raise JournalFull("diagnostic journal capacity reached")
            sequence = int(
                db.execute(
                    "SELECT COALESCE(MAX(sequence),0)+1 FROM observations"
                ).fetchone()[0]
            )
            try:
                db.execute(
                    """
                    INSERT INTO observations(id,data,bytes,created_at,sequence)
                    VALUES(?,?,?,?,?)
                    """,
                    (
                        observation["id"],
                        serialized,
                        encoded_bytes,
                        time.time(),
                        sequence,
                    ),
                )
                marker = self.root / "spool-full.json"
                if marker.exists() and not marker.is_symlink():
                    marker.unlink()
            except sqlite3.OperationalError as exc:
                if "full" in str(exc).lower():
                    self._full(db)
                    raise JournalFull("diagnostic journal capacity reached") from exc
                raise

    def _full(self, db: sqlite3.Connection) -> None:
        row = db.execute(
            "SELECT value FROM metadata WHERE key='dropped_observations'"
        ).fetchone()
        dropped = int(row[0]) if row else 0
        path = self.root / "spool-full.json"
        if path.is_symlink():
            raise ValueError("unsafe journal marker")
        if path.exists():
            try:
                previous = json.loads(path.read_text())
                dropped = max(dropped, int(previous.get("dropped_observations", 0)))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        dropped += 1
        with path.open("w") as handle:
            json.dump(
                {
                    "status": "spool_full",
                    "observed_at": time.time(),
                    "new_observations_admitted": False,
                    "dropped_observations": dropped,
                },
                handle,
            )
            handle.flush()
            os.fsync(handle.fileno())
        try:
            db.execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES('dropped_observations',?)",
                (str(dropped),),
            )
            # JournalFull deliberately escapes the surrounding transaction. Persist the
            # drop counter before raising so the exception cannot roll this evidence back.
            db.commit()
        except sqlite3.Error:
            # A physically full SQLite file may reject metadata writes. The reserved
            # filesystem marker above remains the durable local health signal.
            pass

    def pending(self, limit: int = 100) -> list[dict]:
        with self.connect() as db:
            return [
                json.loads(row[0])
                for row in db.execute(
                    """
                    SELECT data
                    FROM observations
                    WHERE acknowledged=0
                    ORDER BY sequence,created_at,id
                    LIMIT ?
                    """,
                    (limit,),
                )
            ]

    def ack(self, observation_id: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE observations SET acknowledged=1 WHERE id=?",
                (observation_id,),
            )

    def health(self) -> dict[str, object]:
        with self.connect() as db:
            pending, used = db.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN acknowledged=0 THEN 1 ELSE 0 END),0),
                    COALESCE(SUM(bytes),0)
                FROM observations
                """
            ).fetchone()
            row = db.execute(
                "SELECT value FROM metadata WHERE key='dropped_observations'"
            ).fetchone()
        marker = self.root / "spool-full.json"
        dropped = int(row[0]) if row else 0
        if marker.exists() and not marker.is_symlink():
            try:
                marker_data = json.loads(marker.read_text())
                dropped = max(
                    dropped,
                    int(marker_data.get("dropped_observations", 0)),
                )
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        return {
            "spool_full": marker.exists(),
            "dropped_observations": dropped,
            "pending_observations": int(pending),
            "used_bytes": int(used),
            "max_bytes": int(self.max_bytes),
        }

    def bind_creator(self, creator_id: str) -> None:
        with self.connect() as db:
            found = db.execute(
                "SELECT value FROM metadata WHERE key='creator'"
            ).fetchone()
            if found and found[0] != creator_id:
                raise ValueError("diagnostic journal belongs to another Creator")
            db.execute(
                "INSERT OR IGNORE INTO metadata VALUES('creator',?)",
                (creator_id,),
            )

    def get_rules(self) -> dict:
        with self.connect() as db:
            row = db.execute(
                "SELECT value FROM metadata WHERE key='rules'"
            ).fetchone()
            return json.loads(row[0]) if row else {}

    def set_rules(self, data: dict) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO metadata VALUES('rules',?)",
                (json.dumps(data),),
            )
