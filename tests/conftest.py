"""Shared pytest configuration for the kernlens test suites.

The package lives under ``src/``; ``pyproject.toml`` adds it to
``pythonpath`` for pytest, so the suites also run from a bare checkout.
The integration tests install a fake ``gdb`` module themselves, so no
debugger or kernel is required.

``tests/`` is added to ``sys.path`` so the frozen contract constants in
``tests/contract_spec.py`` are importable from both the unit and the
integration suites.
"""

from __future__ import annotations

import pathlib
import sys

_TESTS = pathlib.Path(__file__).resolve().parent
_ROOT = _TESTS.parent
for _extra in (_TESTS, _ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))