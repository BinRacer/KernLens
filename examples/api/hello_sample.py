#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# ruff: noqa: F821
"""The smallest useful KernLens script: one address, three answers.

This is the file to copy when starting a new script.  It shows the two
things that are easy to get wrong in a GDB Python script -- where the
names come from, and how to survive being sourced outside GDB -- and
then calls four parts of the API that need no setup at all.

Load it after ``gdbinit.py``, like any other example::

    (gdb) source /path/to/KernLens/gdbinit.py
    (gdb) source /path/to/KernLens/examples/api/hello_sample.py
    (gdb) hello 0xffffffff81000000

Run it outside GDB and it prints the same lines from the pure-Python
half, because :class:`~kernlens.core.addr.KAddr` and
:class:`~kernlens.core.bitops.BitOps` never touch the debugger.  That is
the property worth copying: the arithmetic you write can be unit-tested
on the host, and only the parts that read memory need a target.
"""

from __future__ import annotations

import sys

# ``gdbinit.py`` installs the public names into ``__main__``, which is the
# namespace a sourced file runs in -- so a script normally just uses them.
# This block is only for the other case: running the file from a plain
# Python interpreter (or from a test), where there is no GDB to install
# anything and the package may not be on the path.
try:
    KAddr  # noqa: B018 - probe, not a bare expression statement
except NameError:  # pragma: no cover - GDB path never runs this
    sys.path.insert(
        0, str(__import__("pathlib").Path(__file__).parents[2] / "src"),
    )
    from kernlens import KAddr, KPageTable
    from kernlens.core.bitops import BitOps

#: A link-time ``_text`` address: always mapped on a kernel with a
#: matching ``vmlinux``, and readable without any slide arithmetic.
SAMPLE = 0xFFFFffff81000000


def hello(address: int = SAMPLE) -> None:
    """Print a few facts that need no debugger state."""
    print(f"address      : {address:#018x}")
    print(f"byte_swap64  : {BitOps.byte_swap64(address):#018x}")
    print(f"popcount     : {BitOps.popcount(address)}")
    print(f"canonical 48 : {KAddr.is_canonical(address, 48)}")
    print(f"canonical 57 : {KAddr.is_canonical(address, 57)}")
    print(f"kernel       : {KAddr.is_kernel(address)}")
    print(f"page offset  : {KPageTable.page_offset(address):#x}")
    print(f"4-level      : {KPageTable.split_4(address)}")


if __name__ == "__main__":
    hello(int(sys.argv[1], 0) if len(sys.argv) > 1 else SAMPLE)