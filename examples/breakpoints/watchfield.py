#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# ruff: noqa: F821
"""A field watchpoint that reports transitions instead of stopping.

Breaking on a function tells you it was called.  Watching a *field* tells
you it changed, which is usually the question: a refcount, a state enum,
a pointer that should be NULL while an object is on a list.

This example sets a hardware watchpoint on one struct field, then filters
in Python so only the transitions you care about stop the debuggee.  The
filter runs in :meth:`gdb.Breakpoint.stop`, so every write costs a trap
but only the interesting one is reported.

Load after ``gdbinit.py``::

    (gdb) source /path/to/KernLens/gdbinit.py
    (gdb) source /path/to/KernLens/examples/breakpoints/watchfield.py
    (gdb) kwatch-field 'struct page' _refcount.counter \\
             0xffffea0000004800 --expect 0

The ``--expect`` value is the interesting one: the watchpoint reports
every change but stops only when the field *becomes* that value, which is
how a use-after-free shows up as "refcount reached zero while still on a
list".
"""

from __future__ import annotations

import shlex

try:
    import gdb
except ImportError as exc:  # pragma: no cover - GDB only
    raise SystemExit(
        "watchfield.py must be sourced by GDB (it sets hardware watchpoints)"
    ) from exc


class TransitionWatchpoint(gdb.Breakpoint):
    """Stop only when a watched field reaches a chosen value.

    A hardware watchpoint reports the *address*, not the value, so the
    current value is read here with the same expression that built the
    watchpoint.  Reading it through the struct type rather than a raw
    ``*(unsigned long *)`` cast matters for a nested field like
    ``_refcount.counter``: the cast would read the whole containing
    struct and silently report the wrong number.
    """

    def __init__(
        self,
        expression: str,
        expect: int,
        *,
        label: str = "",
    ) -> None:
        super().__init__(expression, gdb.WP_WRITE, internal=False)
        self.silent = True
        self._expression = expression
        self._expect = expect
        self._label = label or expression
        self._previous: int | None = None
        self.changes = 0

    def _read(self) -> int | None:
        try:
            return int(gdb.parse_and_eval(self._expression))
        except (gdb.error, TypeError, ValueError):
            return None

    def stop(self) -> bool:
        value = self._read()
        if value is None:
            return False
        previous, self._previous = self._previous, value
        self.changes += 1
        if value != self._expect:
            return False
        was = "?" if previous is None else f"{previous:#x}"
        kdbg.warn(  # noqa: F821 - installed by gdbinit
            f"{self._label}: {was} -> {value:#x} "
            f"(change {self.changes}, pc={int(gdb.parse_and_eval('$pc')):#x})"
        )
        return True


class WatchFieldCommand(gdb.Command):
    """``kwatch-field <type> <field-path> <address> [--expect N]``."""

    def __init__(self) -> None:
        super().__init__("kwatch-field", gdb.COMMAND_BREAKPOINTS)

    def invoke(self, argument: str, from_tty: bool) -> None:
        del from_tty
        # ``split()`` is wrong here: GDB strips the shell-style quotes from
        # ``'struct page'``, so a whitespace split yields four tokens and
        # the type name is cut in half.  ``shlex`` is what KernLens' own
        # command layer uses, and it also survives the case where the
        # quotes do reach us (sourcing the file and typing the command by
        # hand behave differently here).
        try:
            words = shlex.split(argument)
        except ValueError:
            words = argument.split()
        expect = 0
        if "--expect" in words:
            index = words.index("--expect")
            try:
                expect = int(gdb.parse_and_eval(words[index + 1]))
            except (IndexError, gdb.error, TypeError, ValueError) as exc:
                raise gdb.GdbError(
                    "--expect needs a value GDB can evaluate"
                ) from exc
            words = words[:index] + words[index + 2:]
        if len(words) == 3:
            type_name, path, address = words
        elif len(words) == 4:
            # ``struct page _refcount.counter ADDR``: GDB dropped the
            # quotes, so the two-word type has to be rejoined.
            type_name = " ".join(words[:2])
            path, address = words[2], words[3]
        else:
            raise gdb.GdbError(
                "usage: kwatch-field <type> <field-path> <address> "
                "[--expect N]"
            )
        # The struct type is used in the expression, not a raw cast, so a
        # nested path keeps its real width.
        expression = f"(({type_name} *)({address}))->{path}"
        try:
            gdb.parse_and_eval(expression)
        except gdb.error as exc:
            raise gdb.GdbError(
                f"cannot evaluate {expression}: {exc}"
            ) from exc
        try:
            watchpoint = TransitionWatchpoint(
                expression, expect, label=f"{type_name}.{path}",
            )
        except gdb.error as exc:
            # A remote stub may have no hardware watchpoint support: QEMU's
            # gdbstub is one such target, and the raw error ("Do not
            # understand breakpoint type to set") does not say so.
            raise gdb.GdbError(
                f"cannot set a hardware watchpoint on {expression}: {exc}; "
                "this target may not support them -- use a software "
                "breakpoint on the writing function instead"
            ) from exc
        gdb.write(
            f"kwatch-field: watching {type_name}.{path} at {address}, "
            f"stopping when it becomes {expect:#x}\n"
        )
        if watchpoint is None:  # pragma: no cover - defensive
            raise gdb.GdbError("failed to create the watchpoint")


# ``gdb.Command`` registers itself in ``__init__``, so the instance has to
# be created; defining the class alone registers nothing.
_WATCH_COMMAND = WatchFieldCommand()

gdb.write(
    "watchfield.py: kwatch-field <type> <field-path> <address> "
    "[--expect N] is ready\n"
)