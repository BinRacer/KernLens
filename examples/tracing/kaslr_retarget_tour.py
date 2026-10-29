#!/usr/bin/env python3
#
# ruff: noqa: F821
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Make a tracer work when the KASLR slide is not the one you assumed.

Every address in a vmlinux is a link-time address.  On a KASLR kernel
nothing lives there, and the failure is quiet: a breakpoint set on
`0xffffffff81234567` reports success, never fires, and looks like the
code path was not taken.  This example is the four ways out, in the order
that gets you unstuck fastest.

1. `kl-status` -- the cheapest check.  It prints the slide KernLens
   currently believes, and the runtime `_text`, so a disagreement with
   `nm vmlinux | grep ' _text'` is visible immediately.
2. `kl-base` -- find the slide from the target rather than being told.
   It uses three independent methods (`--verbose` names which one won);
   `symbol` reads an IDT handler through the target's own table, so it
   works with no symbols and no debug info.
3. `kl-base` -- and this is the step people skip.  Finding the slide is
   not the same as *applying* it -- `kl-base` reports and applies.
   installs it, which is what makes every later `kl-*` command resolve
   runtime addresses.
4. `kl-base text` / `kl-base offset` -- the manual overrides, for when
   discovery fails: give a runtime `_text` or the slide itself.

There is a fifth command, `kl-color`, and it is last for a reason: it
belongs to the same "fix the environment before you debug" family, and
`of`-mode output is what makes the difference between the two `_text`
values readable in a terminal.

Source it after `gdbinit.py` and run `retarget`::

    (gdb) source /path/to/KernLens/gdbinit.py
    (gdb) source /path/to/KernLens/examples/tracing/kaslr_retarget_tour.py
    (gdb) retarget              # discover, verify, then apply
    (gdb) retarget --dry-run    # show what it would do
    (gdb) retarget --offset 0x19600000

The example deliberately does the discovery twice -- once without
applying, once with -- so the reader can see that the addresses really do
change, rather than taking it on faith.
"""

from __future__ import annotations

import argparse
import shlex

try:
    import gdb
except ImportError as exc:  # pragma: no cover - GDB only
    raise SystemExit("kaslr_retarget_tour.py must be sourced by GDB") from exc


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


def _run(command: str) -> str:
    """Execute a command, echo it, print its output, and return it.

    `to_string=True` is used rather than letting GDB print directly so
    the output can be captured for the comparison in :func:`apply` -- but
    that also means it has to be written back out here, which is the one
    thing easy to forget when switching a call to capture mode.
    """
    gdb.write(f"-- {command}\n")
    output = gdb.execute(command, to_string=True)
    if output:
        gdb.write(output if output.endswith("\n") else output + "\n")
    return output


def _link_text() -> int:
    """The link-time `_text`, which is what a tracer's tables contain.

    This is the address that does *not* move.  Comparing it against the
    runtime value is the whole content of "is the slide applied".
    """
    return int(kdbg.link_text())  # noqa: F821


def _runtime_text() -> int | None:
    """The runtime `_text`, or None when it cannot be resolved yet.

    `KAddr.kaslr_runtime` is pure arithmetic -- link address plus slide --
    so the interesting question is only what the slide currently is.
    """
    try:
        return int(kdbg.kaslr_slide()) + _link_text()  # noqa: F821
    except (AttributeError, TypeError):
        return None


def survey() -> None:
    """Steps 1-2: what KernLens believes, and what the target says."""
    _section("1. current state (kl-status)")
    _run("kl-status")

    _section("2. discover the slide from the target (kl-base --verbose)")
    _run("kl-base --verbose")

    _section("3. is it applied?")
    link = _link_text()
    slide = kdbg.kaslr_slide()  # noqa: F821
    _run(f"kl-sym {link:#x}")
    gdb.write(
        f"   link _text  : {link:#x}\n"
        f"   slide       : {slide:+#x}\n"
        f"   runtime _text: {link + slide:#x}\n"
    )


def apply(dry_run: bool) -> None:
    """Step 3: install the slide, then prove the addresses moved."""
    if dry_run:
        _section("4. would apply (dry run)")
        gdb.write(f"-- kl-base would install a slide of {kdbg.kaslr_slide():+#x}\n")
        return

    _section("4. apply it (kl-base)")
    _run("kl-base")

    _section("5. verify: the same symbol, after")
    # Resolving the link-time address is the check that matters: before
    # step 4 it names nothing, after it names `_text`.
    _run(f"kl-sym {_link_text():#x}")
    _run("kl-kvar jiffies")

    _section("6. the environment fix (kl-color)")
    _run("kl-color off")
    _run("kl-status")


def manual(value: str) -> None:
    """Step 4: the manual override, when discovery fails."""
    _section("4. manual override")
    # Both commands are shown because they answer different questions: a
    # crash log gives you a runtime `_text`, a diff gives you the slide.
    if value.lower().startswith("0x") and int(value, 0) < 0x1000_0000:
        _run(f"kl-base offset {value}")
    else:
        _run(f"kl-base text {value}")
    _run("kl-status")


def help_view() -> None:
    """The last resort, which is also the first thing to try."""
    _section("7. when a command's output is not what you expected")
    _run("kl-help kl-walk")


class RetargetCommand(gdb.Command):
    """retarget [--dry-run] [--offset VALUE] -- fix the KASLR slide."""

    def __init__(self) -> None:
        super().__init__("retarget", gdb.COMMAND_USER)

    def invoke(self, arg: str, from_tty: bool) -> None:
        parser = argparse.ArgumentParser(prog="retarget", add_help=False)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--offset", default=None)
        try:
            args = parser.parse_args(shlex.split(arg))
        except SystemExit:
            gdb.write("usage: retarget [--dry-run] [--offset VALUE]\n")
            return

        gdb.write("--- retarget: make runtime addresses resolvable ---\n")
        if args.offset is not None:
            manual(args.offset)
        else:
            survey()
            apply(args.dry_run)
        help_view()


_RETARGET = RetargetCommand()

gdb.write(
    "kaslr_retarget: run 'retarget' to discover and apply the slide, "
    "'retarget --offset 0x...' to set it manually\n"
)