"""Creator-only downloads of verified artifacts published locally by the host operator."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.dependencies import actor
from app.config import settings
from app.core.domain import Actor

router = APIRouter(prefix='/builds', tags=['builds'])
ARTIFACTS = {
    'android-debug': ('creation-debug.apk', 'apk', 'debug'),
    'android-release': ('creation-release-unsigned.apk', 'apk', 'release_unsigned'),
    'android-bundle': ('creation-release.aab', 'aab', 'release_unsigned'),
}
VERSION_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}')


def _checked_path(root: Path, *parts: str) -> Path:
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Symlink is not an artifact')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Artifact escapes release root')
    return path


def _manifest() -> tuple[dict | None, Path]:
    root = Path(settings.release_artifacts_dir)
    try:
        path = _checked_path(root, 'manifest.json')
        if not path.exists():
            return None, root
        if path.stat().st_size > 65536:
            raise ValueError('Manifest too large')
        manifest = json.loads(path.read_text(encoding='utf-8'))
        if manifest.get('schema_version') != 1 or not isinstance(manifest.get('version'), str):
            raise ValueError('Invalid manifest version')
        if not VERSION_PATTERN.fullmatch(manifest['version']):
            raise ValueError('Invalid release directory')
        files = manifest.get('files')
        if not isinstance(files, list) or not 1 <= len(files) <= len(ARTIFACTS):
            raise ValueError('Invalid files')
        seen = set()
        for entry in files:
            artifact_id = entry['id']
            if artifact_id not in ARTIFACTS or artifact_id in seen:
                raise ValueError('Invalid artifact id')
            seen.add(artifact_id)
            if (entry['filename'], entry['type'], entry['variant']) != ARTIFACTS[artifact_id]:
                raise ValueError('Invalid artifact metadata')
            if not isinstance(entry['title'], str) or not 1 <= len(entry['title']) <= 120:
                raise ValueError('Invalid title')
            if type(entry['size_bytes']) is not int or entry['size_bytes'] <= 0:
                raise ValueError('Invalid file size')
            if not isinstance(entry['sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', entry['sha256']):
                raise ValueError('Invalid digest')
            artifact = _checked_path(root, manifest['version'], entry['filename'])
            if not artifact.is_file() or artifact.stat().st_size != entry['size_bytes']:
                raise ValueError('Missing or truncated artifact')
            digest = hashlib.sha256()
            with artifact.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            if digest.hexdigest() != entry['sha256']:
                raise ValueError('Artifact integrity failure')
        return manifest, root
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise HTTPException(503, 'Arquivos de instalação indisponíveis ou com integridade inválida. Verifique a publicação no host.') from exc


@router.get('')
def list_builds(a: Actor = Depends(actor)):
    manifest, _ = _manifest()
    if manifest is None:
        return {'status': 'not_configured', 'version': None, 'files': []}
    # Only the declared metadata is returned, never operator-provided paths or extra fields.
    fields = ('id', 'title', 'filename', 'type', 'variant', 'size_bytes', 'sha256')
    return {'status': 'available', 'version': manifest['version'],
            'files': [{field: entry[field] for field in fields} for entry in manifest['files']]}


@router.get('/{artifact_id}/download')
def download_build(artifact_id: str, a: Actor = Depends(actor)):
    if artifact_id not in ARTIFACTS:
        raise HTTPException(404, 'Arquivo não publicado.')
    manifest, root = _manifest()
    if manifest is not None:
        for entry in manifest['files']:
            if entry['id'] == artifact_id:
                path = _checked_path(root, manifest['version'], entry['filename'])
                return FileResponse(path, filename=entry['filename'], media_type='application/octet-stream',
                                    headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
    raise HTTPException(404, 'Arquivo não publicado.')
