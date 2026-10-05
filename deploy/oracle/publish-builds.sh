#!/usr/bin/env bash
# Validate immutable files before atomically replacing the current manifest.
set -euo pipefail
if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo 'Usage: publish-builds.sh <staging-directory> [release-root]' >&2
  exit 2
fi
python3 - "$1" "${2:-/var/lib/creation/releases}" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
source, root = map(Path, sys.argv[1:])
if source.is_symlink() or root.is_symlink():
    raise SystemExit('Staging and release root must not be symlinks')
source = source.resolve(strict=True)
root.mkdir(parents=True, exist_ok=True)
root = root.resolve(strict=True)
path = source / 'manifest.json'
if path.is_symlink() or path.stat().st_size > 65536:
    raise SystemExit('Invalid manifest')
manifest = json.loads(path.read_text())
version = manifest.get('version', '')
if manifest.get('schema_version') != 1 or not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', version):
    raise SystemExit('Invalid release version')
allowed = {
    'android-debug': ('creation-debug.apk', 'apk', 'debug'),
    'android-release': ('creation-release-unsigned.apk', 'apk', 'release_unsigned'),
    'android-bundle': ('creation-release.aab', 'aab', 'release_unsigned'),
}
files = manifest.get('files')
if not isinstance(files, list) or not 1 <= len(files) <= 3:
    raise SystemExit('Invalid file count')
def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
seen = set()
for entry in files:
    key = entry.get('id')
    if key not in allowed or key in seen or (entry.get('filename'), entry.get('type'), entry.get('variant')) != allowed[key]:
        raise SystemExit('Invalid artifact declaration')
    seen.add(key)
    if not isinstance(entry.get('title'), str) or not 1 <= len(entry['title']) <= 120:
        raise SystemExit('Invalid artifact title')
    if type(entry.get('size_bytes')) is not int or entry['size_bytes'] <= 0 or not isinstance(entry.get('sha256'), str) or not re.fullmatch(r'[a-f0-9]{64}', entry['sha256']):
        raise SystemExit('Invalid artifact integrity metadata')
    path = source / entry['filename']
    if path.is_symlink() or not path.is_file() or path.stat().st_size != entry['size_bytes'] or digest(path) != entry['sha256']:
        raise SystemExit('Missing, unsafe or corrupt artifact')
def verify_version(directory):
    # A retry may reuse exactly these immutable bytes, never an incomplete or different release.
    if directory.is_symlink() or not directory.is_dir():
        raise SystemExit('Existing version must be a regular directory without symlinks')
    expected = {entry['filename'] for entry in files}
    if {path.name for path in directory.iterdir()} != expected:
        raise SystemExit('Existing version artifact inventory differs from the manifest')
    for entry in files:
        artifact = directory / entry['filename']
        if artifact.is_symlink() or not artifact.is_file():
            raise SystemExit('Existing version contains an unsafe artifact')
        if artifact.stat().st_size != entry['size_bytes'] or digest(artifact) != entry['sha256']:
            raise SystemExit('Existing version artifact integrity differs from the manifest')


destination = root / version
if destination.exists() or destination.is_symlink():
    # A previous run may have installed this directory before its manifest replace failed.
    # Verify the whole inventory and leave every existing file untouched before resuming.
    verify_version(destination)
else:
    temporary = Path(tempfile.mkdtemp(prefix='.publish-', dir=root))
    try:
        for entry in files:
            output = temporary / entry['filename']
            shutil.copyfile(source / entry['filename'], output)
            if output.stat().st_size != entry['size_bytes'] or digest(output) != entry['sha256']:
                raise SystemExit('Artifact changed during publication')
            output.chmod(0o644)
        temporary.chmod(0o755)
        os.rename(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
fd, current = tempfile.mkstemp(prefix='.manifest-', dir=root)
try:
    with os.fdopen(fd, 'w') as stream:
        json.dump(manifest, stream)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(current, 0o644)
    os.replace(current, root / 'manifest.json')
finally:
    if os.path.exists(current):
        os.unlink(current)
print(f'Published {version}: {len(files)} verified local artifacts')
PY
