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
# Small model that supports a runtime grammar: used only to spot the "Deus" wake word.
VOSK_WAKE_URL = 'https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip'


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


def vosk_model_installed(directory: Path) -> bool:
    if not directory.is_dir() or not any(directory.rglob('final.mdl')):
        return False
    try:
        from vosk import Model, SetLogLevel
    except ImportError:
        return True
    # Loading is the only reliable completeness check: Vosk needs several files besides final.mdl.
    SetLogLevel(-1)
    try:
        Model(str(directory))
    except Exception:
        return False
    return True


def install_vosk(root: Path, url: str, packaged_name: str, name: str) -> None:
    target = root / name
    if vosk_model_installed(target):
        return
    if target.exists():
        shutil.rmtree(target)
    archive = root / f'{name}.zip'
    download(url, archive)
    with tempfile.TemporaryDirectory(dir=root) as temp:
        directory = Path(temp)
        with zipfile.ZipFile(archive) as package:
            for entry in package.infolist():
                target = (directory / entry.filename).resolve()
                if not target.is_relative_to(directory.resolve()):
                    raise RuntimeError('Unsafe model archive path')
            package.extractall(directory)
        (directory / packaged_name).rename(root / name)
    archive.unlink()


def main() -> None:
    root = Path(settings.deus_local_voice_models_dir)
    root.mkdir(parents=True, exist_ok=True)
    download(KOKORO_BASE + 'kokoro-v1.0.onnx', root / 'kokoro-v1.0.onnx')
    download(KOKORO_BASE + 'voices-v1.0.bin', root / 'voices-v1.0.bin')
    install_vosk(root, VOSK_URL, 'vosk-model-pt-fb-v0.1.1-20220516_2113', 'vosk-pt')
    install_vosk(root, VOSK_WAKE_URL, 'vosk-model-small-pt-0.3', 'vosk-wake-pt')
    print('Local speech models prepared (Kokoro pm_santa / Vosk Portuguese).', flush=True)


if __name__ == '__main__':
    main()
