#!/usr/bin/env python3
#
# ruff: noqa: F821
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Resolve a symbol, then read it, then decode it.

The six commands here form a chain where each one depends on the answer
to the previous, and the chain is the point:

1. `kl-klookup <name>` -- a *substring* search over kallsyms.  Note it
   returns several hits for `init_task`: `ftrace_graph_init_task`,
   `__start_init_task`, and the variable you probably wanted.  Picking
   the wrong one is the most common way a symbol-based tracer starts
   from the wrong address, so this example prints the whole list and
   then selects by exact name.
2. `kl-sym <address>` -- the inverse: address to symbol plus source
   location.  Deterministic, because it is an exact match.
3. `kl-read <address> <count>` -- raw 64-bit words, each annotated with
   the symbol it falls in.  This is what to use when the field you want
   has no DWARF (asm labels, per-CPU offsets, a struct from a module).
4. `kl-kvar <symbol>` -- a KASLR-aware global *value*.  It resolves the
   symbol and dereferences it, so `jiffies` here is the tick count, not
   the address of the variable.  The distinction matters: `&jiffies`
   through GDB would give a link-time address.
5. `kl-read-field <address> <type> <path>` -- the typed read, including
   nested paths.  This needs DWARF, which is why step 3 exists as a
   fallback.
6. `kl-bt` / `kl-chain` -- the current stack, in two formats: `kl-bt`
   is for reading, `kl-chain` is for pasting into a report.

Source it after `gdbinit.py` and run `ytour`::

    (gdb) source /path/to/KernLens/gdbinit.py
    (gdb) source /path/to/KernLens/examples/api/symbols_tour.py
    (gdb) ytour                 # resolves init_task
    (gdb) ytour kmalloc_caches
"""

from __future__ import annotations

import argparse
import shlex

try:
    import gdb
except ImportError as exc:  # pragma: no cover - GDB only
    raise SystemExit("symbols_tour.py must be sourced by GDB") from exc


def _bootstrap_if_needed() -> None:
    """Load the public API if this file was not sourced after gdbinit."""
    try:
        kdbg  # type: ignore[used-before-def]  # noqa: B018
    except NameError:
        import sys
        from pathlib import Path

        src = Path(__file__).resolve().parents[2] / "src"
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from kernlens.gdb.api import install_public_api

        install_public_api(globals())


_bootstrap_if_needed()


def _section(title: str) -> None:
    gdb.write(f"\n=== {title} " + "=" * max(0, 58 - len(title)) + "\n")


def _run(command: str) -> None:
    gdb.write(f"-- {command}\n")
    gdb.execute(command)


def _exact(name: str) -> int | None:
    """The address of the symbol called exactly ``name``, or None.

    `kdbg.lookup()` is a substring search -- `init_task` matches eight
    symbols -- so the caller has to select on the exact name.  Doing that
    here, once, is what keeps the rest of the example honest: every later
    step reads a real variable rather than a `__start_` marker.
    """
    for symbol in kdbg.lookup(name):  # noqa: F821
        if symbol.name == name:
            return int(symbol.address)
    return None


def tour(name: str, depth: int) -> None:
    """Chain the six commands so each one's output feeds the next."""
    _run("kl-base")

    _section(f"1. substring search (kl-klookup {name})")
    _run(f"kl-klookup {name}")

    address = _exact(name)
    if address is None:
        _section("2. no exact match")
        gdb.write(
            f"-- `{name}` appears in no symbol exactly.  The list above is\n"
            "   what the substring search found; pass one of those names.\n"
        )
        return

    _section(f"2. exact resolution (kl-sym {address:#x})")
    _run(f"kl-sym {address:#x}")

    _section("3. raw words (kl-read)")
    # Eight words is one cache line, which is enough to see alignment and
    # the first field without burying the reader in output.
    _run(f"kl-read {address:#x} 8")

    _section("4. as a global value (kl-kvar)")
    _run(f"kl-kvar {name}")

    _section("5. a typed field (kl-read-field)")
    # `init_task` is a `task_struct`; anything else may not be, so this
    # step is allowed to fail loudly rather than silently printing zeros.
    _run(f"kl-read-field {address:#x} 'struct task_struct' pid")

    _section("6. the current stack (kl-bt, kl-chain)")
    _run(f"kl-bt {depth}")
    _run(f"kl-chain {depth}")

    _section("reading the result")
    gdb.write(
        "Step 1 returning several symbols is not a defect -- kallsyms\n"
        "stores substring matches, and the `__start_`/`__end_` markers are\n"
        "real symbols that bracket a section.  Selecting by exact name is\n"
        "the caller's job, and step 2 is how to confirm it happened: if\n"
        "`kl-sym` names a different symbol than you asked for, the address\n"
        "is wrong, and steps 3-5 will read the wrong memory with complete\n"
        "confidence.\n"
    )


class SymbolsTourCommand(gdb.Command):
    """ytour [symbol] [--depth N] -- resolve, read, then decode."""

    def __init__(self) -> None:
        super().__init__("ytour", gdb.COMMAND_USER)

    def invoke(self, arg: str, from_tty: bool) -> None:
        parser = argparse.ArgumentParser(prog="ytour", add_help=False)
        parser.add_argument("symbol", nargs="?", default="init_task")
        parser.add_argument("--depth", type=int, default=4)
        try:
            args = parser.parse_args(shlex.split(arg))
        except SystemExit:
            gdb.write("usage: ytour [symbol] [--depth N]\n")
            return
        tour(args.symbol, args.depth)


_YTOUR = SymbolsTourCommand()

gdb.write(
    "symbols_tour: run 'ytour' to resolve init_task, "
    "'ytour <symbol>' for another\n"
)