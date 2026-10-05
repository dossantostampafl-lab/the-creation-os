"""Every Python embedded in a deploy script must at least compile.

A retired setup script shipped with stray backslashes inside an f-string. It reached the server, wrote
.env, recreated the containers, and only then died on a SyntaxError -- leaving the run red after
it had already changed things. Nothing caught it, because the test's docker stub intercepted the
very call that would have run the code.

Compiling the source is cheap and does not need a container, a stub, or a server.
"""

from __future__ import annotations

import ast
import py_compile
import re
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY = REPO_ROOT / "deploy" / "oracle"

# python -c '...' up to the closing quote, and python - <<'PY' ... PY heredocs. The embedded
# code uses double quotes throughout, so the first unescaped ' closes the -c argument.
INLINE = re.compile(r"python3? -c '([^']*)'", re.DOTALL)
HEREDOC = re.compile(r"python3? - <<'PY'\n(.*?)\nPY\n", re.DOTALL)


def _blocks() -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    for script in sorted(DEPLOY.glob("*.sh")):
        text = script.read_text(encoding="utf-8")
        for pattern in (INLINE, HEREDOC):
            for index, code in enumerate(pattern.findall(text), start=1):
                if code.strip():
                    found.append((script.name, index, code))
    return found


def test_there_is_python_to_check() -> None:
    """A regex that matches nothing would make every assertion below vacuous."""
    assert len(_blocks()) >= 4, [b[:2] for b in _blocks()]


def test_temporal_probe_runs_with_training_without_context_retrieval(monkeypatch) -> None:
    import os
    monkeypatch.setenv('DEUS_CONTEXT_RETRIEVAL_ENABLED', 'false')
    monkeypatch.setenv('STF_AUTO_TRAINING_ENABLED', 'true')
    source = (DEPLOY / 'smoke-test.sh').read_text().split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
    tree = ast.parse(source)
    gates = []

    def visit(node, ancestors):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == 'check_temporal':
            gates.extend(ancestors)
        for child in ast.iter_child_nodes(node):
            visit(child, ancestors + ([node.test] if isinstance(node, ast.If) else []))

    visit(tree, [])
    assert gates, 'Temporal probe must be guarded by runtime configuration'
    scope = {'os': os, 'training_enabled': True, 'diagnostics_enabled': False}
    assert all(eval(compile(ast.Expression(gate), '<gate>', 'eval'), scope) for gate in gates)


@pytest.mark.parametrize("name,index,code", _blocks(), ids=lambda v: v if isinstance(v, str) else None)
def test_embedded_python_compiles(name: str, index: int, code: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(code)
        path = handle.name
    try:
        py_compile.compile(path, doraise=True)
    except py_compile.PyCompileError as error:
        raise AssertionError(f"{name} block {index} does not compile:\n{error}") from error
