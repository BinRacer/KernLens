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

:data:`EXTRA_PATHS` is the single source of truth for that list.  It is
public because two other places have to spell the same directories and
neither can read this file: ``pyproject.toml``'s ``pythonpath`` only
covers pytest, so the stdlib runner needs them as ``PYTHONPATH``, which
means CI and both CONTRIBUTING files repeat them.  ``test_structure``
compares the two -- a test that ran the documented command would be
better, but the documented command *is* this run, and a guard is what
stops the copies from drifting apart again.
"""

from __future__ import annotations

import pathlib
import sys

_TESTS = pathlib.Path(__file__).resolve().parent
_ROOT = _TESTS.parent

#: Directories put on ``sys.path`` for the suites and the tools they test.
#: Order is preserved in the documented ``PYTHONPATH``, so keep it.
EXTRA_PATHS: tuple[pathlib.Path, ...] = (
    _TESTS,
    _ROOT / "tools",
    _ROOT / "hooks",
)

for _extra in EXTRA_PATHS:
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))