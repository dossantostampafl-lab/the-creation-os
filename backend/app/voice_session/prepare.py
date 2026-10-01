"""Install public local speech models into a persistent directory before activation."""
from __future__ import annotations

import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from app.config import settings

KOKORO_BASE = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/'
VOSK_URL = 'https://alphacephei.com/vosk/models/vosk-model-pt-fb-v0.1.1-20220516_2113.zip'


def download(url: str, path: Path) -> None:
    if path.exists():
        return
    staging = path.with_suffix(path.suffix + '.download')
    try:
        with urllib.request.urlopen(url, timeout=60) as response, staging.open('wb') as output:
            shutil.copyfileobj(response, output)
        staging.replace(path)
    finally:
        staging.unlink(missing_ok=True)


def main() -> None:
    root = Path(settings.deus_local_voice_models_dir)
    root.mkdir(parents=True, exist_ok=True)
    download(KOKORO_BASE + 'kokoro-v1.0.onnx', root / 'kokoro-v1.0.onnx')
    download(KOKORO_BASE + 'voices-v1.0.bin', root / 'voices-v1.0.bin')
    if not (root / 'vosk-pt').exists():
        archive = root / 'vosk-pt.zip'
        download(VOSK_URL, archive)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            directory = Path(temp)
            with zipfile.ZipFile(archive) as package:
                for entry in package.infolist():
                    target = (directory / entry.filename).resolve()
                    if not target.is_relative_to(directory.resolve()):
                        raise RuntimeError('Unsafe model archive path')
                package.extractall(directory)
            source = directory / 'vosk-model-pt-fb-v0.1.1-20220516_2113'
            source.rename(root / 'vosk-pt')
        archive.unlink()
    print('Local speech models prepared (Kokoro pm_santa / Vosk Portuguese).', flush=True)


if __name__ == '__main__':
    main()
