"""Publication retries must recover interrupted manifests without changing immutable files."""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

PUBLISHER = Path(__file__).resolve().parents[2] / 'deploy/oracle/publish-builds.sh'


def staging(directory: Path, version: str, content: bytes = b'verified android bytes') -> dict:
    directory.mkdir()
    (directory / 'creation-debug.apk').write_bytes(content)
    manifest = {'schema_version': 1, 'version': version, 'files': [{
        'id': 'android-debug', 'title': 'Android Debug', 'filename': 'creation-debug.apk',
        'type': 'apk', 'variant': 'debug', 'size_bytes': len(content),
        'sha256': hashlib.sha256(content).hexdigest(),
    }]}
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    return manifest


def publish(source: Path, root: Path, env: dict | None = None):
    return subprocess.run(['bash', str(PUBLISHER), str(source), str(root)], capture_output=True, text=True, env=env)


def test_retry_recovers_manifest_replace_failure_without_overwriting_version(tmp_path):
    root = tmp_path / 'releases'
    old = tmp_path / 'old'
    staging(old, 'old_version')
    assert publish(old, root).returncode == 0
    previous_manifest = (root / 'manifest.json').read_bytes()
    source = tmp_path / 'new'
    expected = staging(source, 'new_version')
    shim = tmp_path / 'interruption'
    shim.mkdir()
    (shim / 'sitecustomize.py').write_text(
        'import os\n'
        'original = os.replace\n'
        'def interrupted(source, destination, *args, **kwargs):\n'
        '    if os.path.basename(destination) == "manifest.json":\n'
        '        raise OSError("simulated manifest publication interruption")\n'
        '    return original(source, destination, *args, **kwargs)\n'
        'os.replace = interrupted\n'
    )
    failed = publish(source, root, {**os.environ, 'PYTHONPATH': str(shim)})
    assert failed.returncode != 0
    assert 'simulated manifest publication interruption' in failed.stderr
    assert (root / 'manifest.json').read_bytes() == previous_manifest
    artifact = root / 'new_version' / 'creation-debug.apk'
    before = artifact.stat()
    recovered = publish(source, root)
    assert recovered.returncode == 0, recovered.stderr
    assert json.loads((root / 'manifest.json').read_text()) == expected
    assert artifact.stat().st_ino == before.st_ino
    assert artifact.stat().st_mtime_ns == before.st_mtime_ns
    assert publish(source, root).returncode == 0  # Also safe after a completed publication.


@pytest.mark.parametrize('damage', ['different_bytes', 'missing', 'extra_file', 'artifact_symlink', 'version_symlink', 'artifact_directory'])
def test_conflicting_existing_version_rejects_retry_and_preserves_current_manifest(tmp_path, damage):
    root = tmp_path / 'releases'
    old = tmp_path / 'old'
    staging(old, 'old_version')
    assert publish(old, root).returncode == 0
    previous_manifest = (root / 'manifest.json').read_bytes()
    source = tmp_path / 'new'
    staging(source, 'new_version')
    destination = root / 'new_version'
    destination.mkdir()
    artifact = destination / 'creation-debug.apk'
    shutil.copyfile(source / artifact.name, artifact)
    if damage == 'different_bytes':
        # Same size, different hash: size-only checks must not authorize reuse.
        artifact.write_bytes(b'x' * artifact.stat().st_size)
    elif damage == 'missing':
        artifact.unlink()
    elif damage == 'extra_file':
        (destination / 'unexpected.apk').write_bytes(b'extra')
    elif damage == 'artifact_symlink':
        artifact.unlink()
        artifact.symlink_to(source / artifact.name)
    elif damage == 'version_symlink':
        shutil.rmtree(destination)
        destination.symlink_to(source, target_is_directory=True)
    else:
        artifact.unlink()
        artifact.mkdir()
    original_content = artifact.read_bytes() if artifact.is_file() else None
    failed = publish(source, root)
    assert failed.returncode != 0
    assert (root / 'manifest.json').read_bytes() == previous_manifest
    if original_content is not None:
        assert artifact.read_bytes() == original_content
