"""Shared pytest configuration for the kernlens test suites.

The package lives under ``src/``; ``pyproject.toml`` adds it to
``pythonpath`` for pytest, so the suites also run from a bare checkout.
The integration tests install a fake ``gdb`` module themselves, so no
debugger or kernel is required.

``tests/`` is added to ``sys.path`` so the frozen contract constants in
``tests/contract_spec.py`` are importable from both the unit and the
integration suites.  ``tools/`` and ``hooks/`` are added for the same
reason: the site generators and the mkdocs hook are plain modules, not
installed packages, and a test that imports one by name is checking the
thing that actually runs rather than a copy of it.
"""

from __future__ import annotations

import pathlib
import sys

_TESTS = pathlib.Path(__file__).resolve().parent
_ROOT = _TESTS.parent
for _extra in (_TESTS, _ROOT / "tools", _ROOT / "hooks"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))