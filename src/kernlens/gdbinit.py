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

    source /path/to/kernlens/gdbinit.py

``kernlens path`` prints the absolute path of the copy that belongs to
the installed package, and ``kernlens install`` writes the marked block
into ``~/.gdbinit`` for you.  The checkout's ``src/`` directory (or the
wheel's ``site-packages``) is added to ``sys.path`` automatically, so the
file works even when GDB's embedded Python does not see the interpreter
that installed the package.

No breakpoint is installed at load time; commands are lazy and only
touch kernel memory when invoked.

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

    source /path/to/kernlens/gdbinit.py
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
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

# ``gdb`` is already imported by the interpreter that sources this file;
# bail out with a readable message when run under a plain Python.
if "gdb" not in sys.modules:  # pragma: no cover - only runs inside GDB
    raise SystemExit(
        "gdbinit.py must be sourced by GDB's Python interpreter "
        "(use `kernlens path` to find it)"
    )

# GDB's Python usually has neither the checkout's ``src/`` nor the host
# interpreter's ``site-packages`` on ``sys.path``.  This file is sourced
# by absolute path, so its own location is enough: the parent of the
# ``kernlens/`` directory is ``src/`` in a checkout and ``site-packages``
# in a wheel.  Adding it lets ``import kernlens`` and its dependencies
# (``typing_extensions`` below Python 3.12) resolve in the interpreter
# that is actually running the debugger.
_PACKAGE_PARENT = Path(__file__).resolve().parent.parent
if (
    (_PACKAGE_PARENT / "kernlens" / "__init__.py").is_file()
    and str(_PACKAGE_PARENT) not in sys.path
):
    sys.path.insert(0, str(_PACKAGE_PARENT))

from kernlens import (  # noqa: E402, F401
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
from kernlens.commands import (  # noqa: E402, F401
    aliases,
    register_all,
    registry,
)
from kernlens.commands.formatting import (  # noqa: E402, F401
    fmt_cpu_ranges as _fmt_cpu_ranges,
    parse_depth as _parse_depth,
    parse_int as _parse_int,
    style as _style,
    writeln as _write,
)
from kernlens.gdb.api import install_public_api  # noqa: E402
from kernlens.gdb.facade import kdbg  # noqa: E402

#: Names copied into the target namespace.  ``__all__`` is derived from
#: this list so the two cannot disagree about what a sourced script sees.
#: ``KERNLENS_API`` is installed separately: it is the mapping that
#: ``install_public_api`` returns, not a name in this module.
_EXPORTS: tuple[str, ...] = (
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
)


def _register_all() -> None:
    """Register commands and their ``kl-`` aliases, then print a banner."""
    # Slab/backtrace output is already framed by the commands; keep the
    # generic Logger [INFO] tag out of the way.
    kdbg.logger.set_show_tag(False)
    register_all()


def bootstrap(namespace: MutableMapping[str, Any]) -> None:
    """Install the public API and register the commands in *namespace*.

    ``source`` runs a Python file in GDB's ``__main__`` namespace, so the
    names a later ``source trace.py`` expects have to land there.  The
    checkout shim calls this with its own ``globals()`` for the same
    reason; an ordinary ``import`` of this module has no side effects and
    lets the shim choose the namespace.
    """
    for name in _EXPORTS:
        namespace[name] = globals()[name]
    namespace["KERNLENS_API"] = install_public_api(namespace)
    namespace["_ALL_COMMANDS"] = registry()
    namespace["_ALIASES"] = aliases()
    namespace["_register_all"] = _register_all
    namespace["__all__"] = [
        "KERNLENS_API", *_EXPORTS, "_ALL_COMMANDS", "_ALIASES",
    ]

    _register_all()
    _write(
        _style("KernLens", Palette.BOLD)
        + f" {__version__} loaded  "
        + _style("kl-help", Palette.CYAN)
        + " for a command list"
    )


if __name__ == "__main__":
    bootstrap(globals())
