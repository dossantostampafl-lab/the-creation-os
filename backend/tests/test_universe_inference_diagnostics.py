import os
import runpy
import subprocess
from pathlib import Path

import pytest

from app.admin.seed import CANONICAL_UNIVERSES

ROOT = Path(__file__).resolve().parents[2]


def test_diagnostic_preserves_explicit_pinned_classification():
    namespace = runpy.run_path(str(ROOT / "deploy/oracle/check-universe-inference.py"), run_name="diagnostic-import")
    spec = CANONICAL_UNIVERSES[0]
    caps = {**spec.capabilities, "inference_provider": "anthropic", "inference_routing": "pinned"}
    assert namespace["canonical_profile_shape"](spec, caps) == "custom"
    assert namespace["canonical_profile_shape"](spec, {**caps, "inference_routing": "configured"}) == "generated-current"


@pytest.mark.parametrize("failed", ["api", "worker", "missing-api", "missing-worker", ""])
def test_shell_diagnostic_reports_each_container_failure(tmp_path, failed):
    # Run the actual diagnostic loop, replacing only the external Docker executable.
    capture = tmp_path / "calls"
    docker = tmp_path / "docker"
    docker.write_text("""#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
if args[0] == 'ps':
    service = next(a.split('=')[-1] for a in args if a.startswith('label=com.docker.compose.service='))
    if os.environ['FAILED'] != 'missing-' + service: print('container-' + service)
else:
    service = args[args.index('-e') + 1].split('=')[-1]
    with open(os.environ['CAPTURE'], 'a') as f: f.write(service + '\\n')
    sys.stdin.read()
    sys.exit(1 if service == os.environ['FAILED'] else 0)
""")
    docker.chmod(0o755)
    source = (ROOT / "deploy/oracle/check-inference.sh").read_text()
    block = source[source.index("# Compare synthetic generation"):]
    result = subprocess.run(["bash", "-uc", block], env={**os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"], "CAPTURE": str(capture),
        "FAILED": failed, "UNIVERSE_INFERENCE_DIAGNOSTIC": "true", "REPO_DIR": str(ROOT)},
        capture_output=True, text=True)
    assert capture.read_text().splitlines() == [s for s in ["api", "worker"] if failed != 'missing-' + s]
    assert result.returncode == (1 if failed else 0), result.stderr
