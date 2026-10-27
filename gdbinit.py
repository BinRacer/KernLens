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
"""KernLens GDB startup file.

Source this file from ``~/.gdbinit`` to make the KernLens commands
available in every GDB session::

    source /path/to/KernLens/gdbinit.py

The checkout's ``src/`` directory is added to ``sys.path`` automatically,
so the file also works when KernLens is not installed into GDB's Python
environment.  No breakpoint is installed at load time; commands are
lazy and only touch kernel memory when invoked.

This file is only the bootstrap.  The commands live in
``kernlens.commands`` as plain functions decorated with
:class:`kernlens.commands.Command` (pwndbg-style ``argparse`` parsers plus
``OnlyWhen*`` guards); importing that package registers them.  Sourcing
this file imports the package and instantiates every command and its
``kl-`` alias.

The public Python API is installed into GDB's ``__main__`` namespace as
well.  A script sourced afterwards can use ``KAddr``, ``KPageTable``,
``IntFmt``, ``kdbg``, ``read_kvar``, ``walk``, and the other names from
``kernlens.gdb.api.FACADE_FUNCTIONS`` without imports.  Stateless core
helpers such as ``byte_swap64``, ``popcount``, ``pack_u16``,
``virt_to_phys``, and ``split_4`` are installed as free functions too.
Class-qualified forms such as ``BitOps.byte_swap64`` and
``BitOps_byte_swap64`` are available to avoid name collisions.
Stateful components such as ``logger``, ``styler``, ``reader``, and
``slub`` are installed as the default instances owned by ``kdbg``::

    source /path/to/KernLens/gdbinit.py
    source /path/to/KernLens/examples/api/installed_api_tour.py

``KERNLENS_API`` is the complete installed mapping; ``KERNLENS_QUALIFIED``
and ``KERNLENS_PREFIXED`` hold the class-qualified aliases.
``KERNLENS_INSTANCES`` and ``KERNLENS_CLASSES`` expose the stateful
defaults and their constructors.

Commands
--------
Run ``kl-help`` (or ``kl-help kl-<command>``) for a grouped list or
detailed help, and pass ``-h``/``--help`` to any command.  Every command
has a short ``kl-`` alias; the original ``kernlens-`` spelling remains
available.  The full set is described in ``README.md``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ``gdb`` is already imported by the interpreter that sources this file;
# bail out with a readable message when run under a plain Python.
if "gdb" not in sys.modules:  # pragma: no cover - only runs inside GDB
    raise SystemExit(
        "gdbinit.py must be sourced by GDB's Python interpreter"
    )

# When sourced from a checkout, make ``kernlens`` importable.
_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from kernlens import (  # noqa: E402
    BitOps,
    ByteOrder,
    IntCodec,
    IntFmt,
    IntType,
    KAddr,
    KERNEL_BASE,
    KPageTable,
    PAGE_OFFSET_BASE,
    Palette,
    VMEMAP_BASE,
    __version__,
)
from kernlens.commands import (  # noqa: E402
    aliases,
    register_all,
    registry,
)
from kernlens.commands.formatting import (  # noqa: E402
    fmt_cpu_ranges as _fmt_cpu_ranges,
    parse_depth as _parse_depth,
    parse_int as _parse_int,
    style as _style,
    writeln as _write,
)
from kernlens.gdb.api import install_public_api  # noqa: E402
from kernlens.gdb.facade import kdbg  # noqa: E402

# Installing the public API into ``__main__`` lets a later
# ``source trace.py`` use the names without imports.
KERNLENS_API = install_public_api(globals())

#: Canonical command definitions, in decoration order.
_ALL_COMMANDS = registry()

#: ``kl-`` alias name -> canonical command name.
_ALIASES = aliases()


def _register_all() -> None:
    """Register commands and their ``kl-`` aliases, then print a banner."""
    # Slab/backtrace output is already framed by the commands; keep the
    # generic Logger [INFO] tag out of the way.
    kdbg.logger.set_show_tag(False)
    register_all()


# Register the commands and aliases, then announce the load.
_register_all()
_write(
    _style("KernLens", Palette.BOLD)
    + f" {__version__} loaded  "
    + _style("kl-help", Palette.CYAN)
    + " for a command list"
)

__all__ = [
    "KERNLENS_API",
    "kdbg",
    "register_all",
    # Core classes and constants re-exported into GDB's namespace so a
    # later ``source trace.py`` needs no imports.
    "BitOps",
    "ByteOrder",
    "IntCodec",
    "IntFmt",
    "IntType",
    "KAddr",
    "KERNEL_BASE",
    "KPageTable",
    "PAGE_OFFSET_BASE",
    "Palette",
    "VMEMAP_BASE",
    # Formatting/parse helpers kept for interactive use and the helper
    # tests (``gdbinit._parse_int``, ``gdbinit._fmt_cpu_ranges``).
    "_fmt_cpu_ranges",
    "_parse_depth",
    "_parse_int",
]