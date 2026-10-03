from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('failure', ['up', 'backfill'])
def test_activation_restores_flags_and_stops_partial_workers(tmp_path, failure):
    source = Path(__file__).resolve().parents[2]/'deploy/oracle/enable-connected-deus.sh'
    script = tmp_path/'deploy/oracle/enable-connected-deus.sh'
    script.parent.mkdir(parents=True)
    script.write_bytes(source.read_bytes())
    original = 'DEUS_CONTEXT_RETRIEVAL_ENABLED=false\nCORS_ALLOW_ORIGINS=https://example.test\n'
    (tmp_path/'.env').write_text(original)
    binary = tmp_path/'bin'
    binary.mkdir()
    docker = binary/'docker'
    docker.write_text('''#!/bin/sh
case "$*" in
 *pg_dump*) echo backup; exit 0;;
 *--build*) [ "$ACTIVATION_FAILURE" = up ] && exit 1;;
 *backfill*) [ "$ACTIVATION_FAILURE" = backfill ] && exit 1;;
esac
case "$*" in
 *stop*) echo stopped >> "$ACTIVATION_LOG";;
 *--force-recreate*) echo recreated >> "$ACTIVATION_LOG";;
esac
exit 0
''')
    docker.chmod(0o755)
    log = tmp_path/'events'
    result = subprocess.run(['bash',str(script)],env={**os.environ,'PATH':str(binary)+':'+os.environ['PATH'],'ACTIVATION_FAILURE':failure,'ACTIVATION_LOG':str(log)},capture_output=True,text=True,timeout=10)
    assert result.returncode==1
    assert (tmp_path/'.env').read_text()==original
    assert log.read_text().splitlines()==['stopped','recreated']
    assert list((tmp_path/'.connected-backups').glob('database-*.sql.gz'))
