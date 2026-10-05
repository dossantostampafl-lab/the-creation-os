import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import builds
from app.api.dependencies import actor
from app.core.domain import Actor


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(builds, 'settings', SimpleNamespace(release_artifacts_dir=str(tmp_path)))
    app = FastAPI()
    app.include_router(builds.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        yield client, app, tmp_path


def publish(root):
    data = b'test-apk-bytes'
    directory = root / 'v1'
    directory.mkdir()
    (directory / 'creation-debug.apk').write_bytes(data)
    manifest = {'schema_version': 1, 'version': 'v1', 'files': [{
        'id': 'android-debug', 'title': 'Android teste', 'filename': 'creation-debug.apk',
        'type': 'apk', 'variant': 'debug', 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
    }]}
    (root / 'manifest.json').write_text(json.dumps(manifest))
    return manifest


def authorize(app):
    app.dependency_overrides[actor] = lambda: Actor(id='creator', role='creator')


async def test_list_and_download_require_creator(client):
    http, _, _ = client
    assert (await http.get('/builds')).status_code == 401
    assert (await http.get('/builds/android-debug/download')).status_code == 401


async def test_unconfigured_and_available_download(client):
    http, app, root = client
    authorize(app)
    assert (await http.get('/builds')).json()['status'] == 'not_configured'
    manifest = publish(root)
    response = await http.get('/builds')
    assert response.json() == {'status': 'available', 'version': 'v1', 'files': manifest['files']}
    download = await http.get('/builds/android-debug/download')
    assert download.content == b'test-apk-bytes'
    assert 'creation-debug.apk' in download.headers['content-disposition']
    assert download.headers['cache-control'] == 'private, no-store'
    assert (await http.get('/builds/unknown/download')).status_code == 404


@pytest.mark.parametrize('damage', ['hash', 'missing', 'symlink', 'traversal', 'duplicate', 'manifest_symlink'])
async def test_corrupted_or_escaping_artifacts_never_download(client, damage):
    http, app, root = client
    authorize(app)
    manifest = publish(root)
    artifact = root / 'v1' / 'creation-debug.apk'
    if damage == 'hash':
        artifact.write_bytes(b'wrong-apk-data')
    elif damage == 'missing':
        artifact.unlink()
    elif damage == 'symlink':
        outside = root.parent / 'outside.apk'
        outside.write_bytes(artifact.read_bytes())
        artifact.unlink()
        artifact.symlink_to(outside)
    elif damage == 'traversal':
        manifest['version'] = '../outside'
        (root / 'manifest.json').write_text(json.dumps(manifest))
    elif damage == 'duplicate':
        manifest['files'].append(manifest['files'][0])
        (root / 'manifest.json').write_text(json.dumps(manifest))
    else:
        outside = root.parent / 'outside.json'
        outside.write_text(json.dumps(manifest))
        (root / 'manifest.json').unlink()
        (root / 'manifest.json').symlink_to(outside)
    assert (await http.get('/builds')).status_code == 503
    assert (await http.get('/builds/android-debug/download')).status_code == 503
