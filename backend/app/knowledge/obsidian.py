from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.knowledge.contracts import Scope
from app.knowledge.service import KnowledgeService
from app.models.knowledge import KnowledgeItem, KnowledgeRelation, KnowledgeRevision


def file_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

def atomic_write(path: Path, content: str) -> None:
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.pending', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

class ObsidianExporter:
    def __init__(self, factory: async_sessionmaker[AsyncSession], root: Path):
        self.factory = factory
        self.root = root

    async def export(self, scope: Scope) -> dict[str, int]:
        notes: dict[str, tuple[str, str]] = {}
        async with self.factory() as session:
            rows = list(await session.scalars(select(KnowledgeRevision).join(KnowledgeItem, KnowledgeItem.current_revision_id == KnowledgeRevision.id).where(KnowledgeItem.creator_id == scope.creator_id)))
            for row in rows:
                if await KnowledgeService(session).eligible(scope, row):
                    relations = list(await session.scalars(select(KnowledgeRelation.to_id).where(KnowledgeRelation.from_id == row.item_id, KnowledgeRelation.creator_id == scope.creator_id)))
                    front = {'schema_version': 1, 'id': row.item_id, 'revision_id': row.id, 'title': row.title, 'kind': row.kind, 'epistemic_state': row.epistemic_state, 'source_type': row.source_type, 'source_id': row.source_id}
                    # JSON flow syntax is valid YAML and safely quotes untrusted titles.
                    content = '---\n' + json.dumps(front, ensure_ascii=False) + '\n---\n\n' + row.content + '\n\n' + '\n'.join('[[' + item_id + ']]' for item_id in relations) + '\n'
                    notes[row.item_id] = (row.kind, content)
        return await asyncio.to_thread(self._export, scope, notes)

    def _export(self, scope: Scope, notes: dict[str, tuple[str, str]]) -> dict[str, int]:
        import uuid
        uuid.UUID(scope.creator_id)
        if self.root.is_symlink() or any(parent.is_symlink() for parent in self.root.parents):
            raise ValueError('export root cannot be a symlink')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        base = self.root / scope.creator_id
        if base.is_symlink():
            raise ValueError('export scope cannot be a symlink')
        base.mkdir(mode=0o700, exist_ok=True)
        journal_path = base / '.manifest.sqlite'
        lock_path = base / '.export.lock'
        if journal_path.is_symlink() or lock_path.is_symlink():
            raise ValueError('unsafe export metadata')
        report = {'written': 0, 'removed': 0, 'conflicts': 0}
        with lock_path.open('a') as lock, sqlite3.connect(journal_path) as journal:
            fcntl.flock(lock, fcntl.LOCK_EX)
            journal.execute('PRAGMA synchronous=FULL')
            journal.execute('CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY, path TEXT, old_hash TEXT, new_hash TEXT, state TEXT)')
            existing = {row[0]: row[1:] for row in journal.execute('SELECT id,path,old_hash,new_hash,state FROM files')}
            for item_id in sorted(set(existing) | set(notes)):
                previous = existing.get(item_id)
                if previous:
                    relative = Path(previous[0])
                    if relative.is_absolute() or len(relative.parts) != 2 or relative.parts[0] not in {'document','decision','preference','result','diagnostic','derived_note'} or relative.name != item_id + '.md':
                        raise ValueError('unsafe export manifest path')
                    path = base / relative
                else:
                    path = base / notes[item_id][0] / (item_id + '.md')
                if path.is_symlink() or path.parent.is_symlink():
                    raise ValueError('export path cannot be a symlink')
                path.parent.mkdir(mode=0o700, exist_ok=True)
                current = file_hash(path)
                managed = current is None or (previous is not None and current in (previous[1], previous[2]))
                if item_id not in notes:
                    if not managed and path.exists():
                        quarantine = base / '.quarantine'
                        if quarantine.is_symlink():
                            raise ValueError('unsafe quarantine')
                        quarantine.mkdir(mode=0o700, exist_ok=True)
                        target = quarantine / path.name
                        if target.exists():
                            target = quarantine / (item_id + '-' + uuid.uuid4().hex + '.md')
                        os.replace(path, target)
                        report['conflicts'] += 1
                    elif path.exists():
                        path.unlink()
                        report['removed'] += 1
                    journal.execute('DELETE FROM files WHERE id=?', (item_id,))
                    journal.commit()
                    continue
                kind, content = notes[item_id]
                new_hash = hashlib.sha256(content.encode()).hexdigest()
                if not managed:
                    # Leave human changes intact. The pending DB revision remains eligible for future export.
                    report['conflicts'] += 1
                    continue
                if current == new_hash:
                    journal.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?)', (item_id, str(path.relative_to(base)), current, new_hash, 'confirmed'))
                    journal.commit()
                    continue
                journal.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?)', (item_id, str(path.relative_to(base)), current, new_hash, 'prepared'))
                journal.commit()
                atomic_write(path, content)
                journal.execute('UPDATE files SET state=? WHERE id=?', ('confirmed', item_id))
                journal.commit()
                report['written'] += 1
        return report
