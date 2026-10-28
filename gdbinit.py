#!/usr/bin/env python3
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# ruff: noqa: EXE001
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
# See the LICENSE file in the top-level directory for details.
"""Checkout shim for the KernLens GDB startup file.

The real bootstrap now lives in ``src/kernlens/gdbinit.py`` so that it can
ship inside the wheel.  This file stays because ``~/.gdbinit`` lines and
documentation written against a checkout point at it; it adds ``src/`` to
``sys.path`` and hands the real bootstrap this file's ``__main__``
namespace, which is the namespace ``source`` executes in.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from kernlens.gdbinit import bootstrap  # noqa: E402

bootstrap(globals())
