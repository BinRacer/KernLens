#!/usr/bin/env python3
"""Example GDB tracer built on ``kernlens.gdb.facade``.

Usage (inside GDB, with ``vmlinux`` and the target loaded)::

    source /path/to/repo/examples/gdb_tracer.py

Environment variables read at install time:

``KERNLENS_SYMBOL``
    Function to break on.  Defaults to ``kfree``.
``KERNLENS_ARG``
    GDB expression for the object/page argument.  Defaults to ``$rdi``
    (the first argument on x86-64 System V).  For example, if you hook
    ``__slab_free`` instead, the object head is the third argument,
    ``$rdx``.

The defaults are the real hook point this project validates against:
``kfree``'s first argument on Linux 6.1.134 (the pwn4kernel VM test
kernel) is the object head in ``$rdi``.  Override the environment
variables to trace your own symbol.

No KASLR slide has to be supplied: the breakpoint goes through
``kdbg.bp_spec()``, which asks the reader for the slide it is actually
using (derived from the live IDT) and falls back to the bare symbol when
there is no slide to apply.

After loading, these commands are available::

    kernlens-tracer-slab <address>          # print one slab
    kernlens-tracer-color [on|off]          # toggle logger + styler color

The tracer prefixes its own commands with ``kernlens-tracer-`` because
KernLens already ships ``kernlens-slab`` and ``kernlens-color``; without
the prefix GDB would raise "command already exists" and the tracer's
versions would never be reachable.

The breakpoint prints the slab and continues (it never stops the
target), which makes it suitable for tracing allocation/free paths
while a workload runs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import gdb
except ImportError as exc:  # pragma: no cover - only runs inside GDB
    raise SystemExit(
        "gdb_tracer.py must be sourced by GDB's Python interpreter"
    ) from exc

# Make the checkout importable when the file is sourced directly.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from kernlens.gdb.facade import kdbg  # noqa: E402

DEFAULT_SYMBOL = "kfree"
DEFAULT_ARG = "$rdi"
_INSTALLED = False


class SlabFreeBreakpoint(gdb.Breakpoint):
    """Print the slab that owns ``arg_expr`` and continue."""

    def __init__(self, spec: str, arg_expr: str) -> None:
        super().__init__(spec, internal=False)
        self.silent = True
        self._arg_expr = arg_expr

    def stop(self) -> bool:
        try:
            head = int(gdb.parse_and_eval(self._arg_expr))
        except (gdb.error, TypeError, ValueError) as exc:
            kdbg.warn(f"cannot read {self._arg_expr}: {exc}")
            return False
        kdbg.print_slab(head)
        return False


class SlabCommand(gdb.Command):
    """``kernlens-tracer-slab <address>``."""

    def __init__(self) -> None:
        super().__init__("kernlens-tracer-slab", gdb.COMMAND_USER)

    def invoke(self, argument: str, from_tty: bool) -> None:
        del from_tty
        expression = argument.strip()
        if not expression:
            raise gdb.GdbError("usage: kernlens-tracer-slab <address>")
        try:
            head = int(gdb.parse_and_eval(expression))
        except (gdb.error, TypeError, ValueError) as exc:
            raise gdb.GdbError(f"cannot evaluate {expression!r}: {exc}") from exc
        kdbg.print_slab(head)


class ColorCommand(gdb.Command):
    """``kernlens-tracer-color [on|off]``."""

    def __init__(self) -> None:
        super().__init__("kernlens-tracer-color", gdb.COMMAND_USER)

    def invoke(self, argument: str, from_tty: bool) -> None:
        del from_tty
        choice = argument.strip().lower()
        if choice in ("on", "1", "yes", "true"):
            kdbg.enable_color()
        elif choice in ("off", "0", "no", "false"):
            kdbg.disable_color()
        elif choice:
            raise gdb.GdbError("usage: kernlens-tracer-color [on|off]")
        gdb.write(f"kernlens color: {'on' if kdbg.color_enabled else 'off'}\n")


def _register_command(command_type: type[gdb.Command]) -> None:
    """Register a command once, tolerating a prior ``gdbinit.py`` load."""
    try:
        command_type()
    except gdb.error as exc:
        if "already exists" not in str(exc).lower():
            raise


def install(
    symbol: str = DEFAULT_SYMBOL,
    arg_expr: str = DEFAULT_ARG,
) -> None:
    """Install the breakpoint and commands.  Safe to call once."""
    global _INSTALLED
    if _INSTALLED:
        kdbg.info("kernlens-tracer: already installed")
        return
    # ``bp_spec()`` returns a bare symbol name when no slide has been set,
    # which would plant the breakpoint at its link-time (nokaslr) address.
    # Adopt the slide the reader derives from the live IDT so a KASLR
    # kernel is hooked at the right place; on a nokaslr kernel the derived
    # slide is zero and ``bp_spec`` falls back to the bare symbol.
    slide = kdbg.kaslr_slide()
    if slide:
        kdbg.kaslr_offset = slide
    kdbg.info(
        f"kernlens-tracer: symbol={symbol} arg={arg_expr} "
        f"kaslr=+{slide:#x}"
    )

    text = kdbg.link_text()
    if text is not None:
        kdbg.info(f"kernlens-tracer: link _text={kdbg.addr(text)}")

    SlabFreeBreakpoint(kdbg.bp_spec(symbol), arg_expr)
    _register_command(SlabCommand)
    _register_command(ColorCommand)
    _INSTALLED = True
    kdbg.info(
        "kernlens-tracer: ready; use 'kernlens-tracer-slab <address>' "
        "or 'kernlens-tracer-color off'"
    )


# ``source`` executes this file in __main__, so install immediately.  Any
# failure is a real configuration error inside GDB and should surface.
install(
    symbol=os.environ.get("KERNLENS_SYMBOL", DEFAULT_SYMBOL),
    arg_expr=os.environ.get("KERNLENS_ARG", DEFAULT_ARG),
)