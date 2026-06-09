"""Guard the lazy-startup invariant: importing the CLI must not load query.

The query package roughly 2.4x's CLI startup, which taxes every invocation
including --help. This regression already shipped once (an eager top-level
import added during a refactor and reverted two commits later), so the
invariant gets a real test. It must run in a subprocess: the pytest process
itself imports query modules all over the suite.
"""

from __future__ import annotations

import subprocess
import sys

_PROBE = """
import sys
import edgarpack.cli
loaded = sorted(m for m in sys.modules if m.startswith("edgarpack"))
heavy = [m for m in loaded if m.startswith(("edgarpack.query", "edgarpack.distill"))]
print(",".join(heavy) if heavy else "OK")
"""


def test_cli_import_does_not_load_query_package():
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "OK", (
        f"importing edgarpack.cli eagerly loaded: {result.stdout.strip()}"
    )


def test_lazy_render_reexport_resolves_and_rejects_unknown():
    import edgarpack.cli as cli

    assert callable(cli._render_query_table)
    try:
        cli._does_not_exist
    except AttributeError:
        pass
    else:
        raise AssertionError("unknown attribute did not raise AttributeError")
