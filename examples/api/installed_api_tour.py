#!/usr/bin/env python3
#
# ruff: noqa: F821
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Example GDB trace script loaded after KernLens.

``gdbinit.py`` installs the public KernLens names into GDB's
``__main__`` namespace.  A script sourced afterwards can therefore use
``KAddr``, ``KPageTable``, ``kdbg``, ``read_kvar``, ``walk``, ... without
an explicit ``from kernlens import ...``::

    (gdb) source /path/to/KernLens/gdbinit.py
    (gdb) source /path/to/KernLens/examples/api/installed_api_tour.py

The fallback below only exists so this file remains inspectable from a
normal Python process; in GDB the names are already present.
"""

from __future__ import annotations

try:
    import gdb
except ImportError as exc:  # pragma: no cover - GDB only
    raise SystemExit("installed_api_tour.py must be sourced by GDB") from exc


def _bootstrap_if_needed() -> None:
    """Load the public API if this file was not sourced after gdbinit."""
    try:
        KAddr  # type: ignore[used-before-def]  # noqa: B018
    except NameError:
        import sys
        from pathlib import Path

        src = Path(__file__).resolve().parents[1] / "src"
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from kernlens.gdb.api import install_public_api

        install_public_api(globals())


_bootstrap_if_needed()


def kernlens_trace_report(address: int) -> None:
    """Print a small report using the public KernLens API."""
    print(f"KernLens API : {len(KERNLENS_API)} names, kdbg={type(kdbg).__name__}")
    print(f"address      : {address:#018x}")
    print(f"byte_swap64  : {BitOps.byte_swap64(address):#018x}")
    print(f"popcount     : {BitOps.popcount(address)}")
    print(f"logger       : {type(logger).__name__}")
    print(f"styler       : {type(styler).__name__}")
    print(f"canonical 48 : {KAddr.is_canonical(address, 48)}")
    print(f"direct map   : {KAddr.is_direct_map(address)}")
    print(f"split 4-level: {KPageTable.split_4(address)}")
    print(f"symbol       : {kdbg.sym(address)}")
    page_walk = walk(address)
    print(f"page walk    : {page_walk.note or page_walk.phys}")


class SlabTraceBreakpoint(gdb.Breakpoint):
    """Example breakpoint trace using only the installed KernLens API.

    Install it after loading a matching ``vmlinux``::

        (gdb) python install_slab_trace()

    The handler reads the first x86-64 argument with ``kdbg.u64``,
    prints the owning slab with ``kdbg.print_slab``, and continues.
    Replace the symbol/register pair with your own trace point.
    """

    def __init__(self, symbol: str = "kfree", arg_expr: str = "$rdi") -> None:
        super().__init__(bp_spec(symbol), internal=False)
        self.silent = True
        self._arg_expr = arg_expr

    def stop(self) -> bool:
        head = kdbg.u64(self._arg_expr)
        if head:
            kdbg.print_slab(head)
        return False


def install_slab_trace(
    symbol: str = "kfree", arg_expr: str = "$rdi",
) -> SlabTraceBreakpoint:
    """Create and enable the example slab-free breakpoint."""
    return SlabTraceBreakpoint(symbol, arg_expr)


# A sourced file may call the API immediately.  The address is a real
# direct-map page of the test kernel (Linux 6.1.134, pwn4kernel VM):
# ``page_offset_base + 0x120000``, which its live page tables map with a
# present 4 KiB PTE.  Any mapped kernel address works just as well.
kernlens_trace_report(0xFFFF9DBDC0120000)