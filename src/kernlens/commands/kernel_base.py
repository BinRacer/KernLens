#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""Kernel base and KASLR command.

``kernlens-base`` reports where the kernel text is loaded and, when asked,
corrects the slide.  It replaces four commands -- ``base``, ``kbase``,
``kaslr`` and ``kaslr-offset`` -- that all ended in the same place:

* ``kbase`` printed a longer version of what ``base`` printed, and two of
  its options were already aliases for the other two commands;
* ``kaslr`` set the slide from a runtime ``_text`` address and
  ``kaslr-offset`` set it directly -- two spellings of one assignment.

There is one KASLR slide, so there is one command that reads and writes it.
The other entry points are subcommands, and every report states the slide
that is now in effect, which is what the four commands disagreed about.
"""

from __future__ import annotations

import argparse
from typing import cast

import gdb

from ..gdb.facade import kdbg
from ..gdb.kbase import IdtInfo
from ..output import message
from ..output.tree import IndentContextManager
from .formatting import default_base, kernel_running
from .framework import (
    Command,
    CommandCategory,
    parse_int_arg,
)

_MASK64 = 0xFFFFFFFFFFFFFFFF

#: Subcommands, in the order ``kl-help`` mentions them.
_BASE_SUBCOMMANDS = ("show", "text", "offset", "idt", "rebase")

_base_parser = argparse.ArgumentParser(
    description="Reports the runtime kernel text base and KASLR slide.",
)
# A single ``nargs="*"`` positional carries the subcommand and its
# argument.  Two optional positionals would make argparse guess which one a
# lone number belongs to, and ``kl-base 0xffffffff83000000`` is genuinely
# ambiguous between "a runtime _text" and "a slide".
_base_parser.add_argument(
    "args", nargs="*", metavar="command",
    help=(
        "show | text <runtime _text> | offset <slide> | "
        "idt [count] | rebase | <runtime _text>"
    ),
)
_base_parser.add_argument(
    "-v", "--verbose", action="store_true",
    help="also print the physical address of the text base (with show)",
)
_base_parser.add_argument(
    "-r", "--rebase", action="store_true",
    help="reload the symbol file at the detected base",
)


@Command(
    _base_parser,
    category=CommandCategory.KERNEL_BASE,
    aliases=["kl-base"],
    examples=(
        "kl-base\n"
        "  detect and apply the runtime text base\n"
        "kl-base --verbose\n"
        "  also show the physical address of the text\n"
        "kl-base text 0xffffffff83000000\n"
        "  set the slide from a runtime _text address\n"
        "kl-base offset 0x2cc00000\n"
        "  set the slide directly\n"
        "kl-base idt 8\n"
        "  dump the first eight interrupt gates\n"
        "kl-base rebase\n"
        "  reload the symbol file at the detected base"
    ),
    notes=(
        "A bare address is read as a runtime ``_text``, because that is the\n"
        "value a breakpoint or a symbol listing gives you; use ``offset``\n"
        "for a slide.\n"
        "\n"
        "``show`` is the default.  It prints the base, the slide in effect,\n"
        "the link-time ``_text``, and how the base was found -- the union of\n"
        "what ``kl-base`` and ``kl-kbase`` used to report separately."
    ),
)
def kernlens_base(
    args: list[str] | None = None,
    verbose: bool = False,
    rebase: bool = False,
) -> None:
    tokens = list(args or [])
    sub = tokens[0] if tokens and tokens[0] in _BASE_SUBCOMMANDS else "show"
    rest = tokens[1:] if tokens and tokens[0] in _BASE_SUBCOMMANDS else tokens

    if sub == "idt":
        _dump_idt(parse_int_arg(rest[0]) if rest else 16)
        return
    if sub == "text":
        if not rest:
            _base_parser.print_usage()
            return
        _set_from_text(parse_int_arg(rest[0]))
        return
    if sub == "offset":
        if not rest:
            _base_parser.print_usage()
            return
        _set_offset(parse_int_arg(rest[0]))
        return
    if sub == "rebase":
        _rebase_detected()
        return
    # A bare number is a runtime _text: that is the value a breakpoint or a
    # symbol listing gives, and the commoner of the two corrections.
    if rest:
        _set_from_text(parse_int_arg(rest[0]))
        return
    _show(verbose, rebase)


def _show(verbose: bool, rebase: bool) -> None:
    """Report the base and slide, applying what was detected.

    ``kl-base`` is the manual retry for the framework's once-per-session
    alignment: it drops the latch and spends a fresh set of probes.  The
    user runs it after fixing whatever stopped detection -- loading the
    matching vmlinux, attaching the target, resuming a VM -- and it has to
    be the command that re-opens the question, because it is the one a
    user reaches for when they believe the base is now knowable.
    """
    kdbg.reader.reopen_alignment()
    result = kdbg.find_kbase()
    indent = IndentContextManager()
    if result is None:
        if kernel_running():
            print(
                message.error(
                    "kernel is running but the text base could not be "
                    "detected; load a matching vmlinux or pass the slide "
                    "with 'kl-base offset <slide>'"
                )
            )
            return
        kdbg.kaslr_offset = 0
        indent.print(
            indent.prefix("kernel base") + ": "
            + indent.addr_hex(default_base()) + " " + message.warn("(default)")
        )
        indent.print(indent.prefix("KASLR offset") + ": +0x0")
        indent.print(indent.prefix("status") + ": kernel not running")
        return
    link = getattr(result, "link_text", None)
    if link is None:
        link = kdbg.link_text()
    offset = getattr(result, "kaslr_offset", None)
    if offset is None:
        reference = link if link is not None else default_base()
        offset = (result.base - reference) & _MASK64
    kdbg.kaslr_offset = offset
    indent.print(
        indent.prefix("kernel base") + ": "
        + indent.addr_hex(result.base) + " " + message.success("(runtime)")
    )
    indent.print(indent.prefix("KASLR offset") + f": +{offset:#x}")
    if link is not None:
        indent.print(indent.prefix("link _text") + ": " + indent.addr_hex(link))
    indent.print(
        indent.prefix("method") + ": "
        + message.notice(str(getattr(result, "method", "unknown")))
    )
    if verbose:
        walk = kdbg.walk(result.base)
        indent.print(
            indent.prefix("Physical") + ": "
            + (
                indent.aux_hex(walk.phys)
                if walk.phys is not None
                else message.warn("?")
            )
        )
    indent.print(
        indent.prefix("status") + ": " + message.success("kernel running")
    )
    if rebase:
        _rebase(result.base)


def _set_from_text(runtime_text: int) -> None:
    """Set the slide from a runtime ``_text`` address."""
    link = kdbg.link_text()
    if link is None:
        print(
            message.error("cannot resolve &_text; load a matching vmlinux first")
        )
        return
    offset = (runtime_text - link) & _MASK64
    kdbg.kaslr_offset = offset
    indent = IndentContextManager()
    indent.print(indent.prefix("KASLR offset") + f": +{offset:#x}")
    indent.print(
        indent.prefix("link _text") + ": " + indent.addr_hex(link)
        + " runtime _text: " + indent.addr_hex(runtime_text)
    )
    indent.print(indent.prefix("status") + ": " + message.success("applied"))


def _set_offset(offset: int) -> None:
    """Set the slide directly."""
    offset &= _MASK64
    kdbg.kaslr_offset = offset
    indent = IndentContextManager()
    indent.print(indent.prefix("KASLR offset") + f": +{offset:#x}")
    indent.print(indent.prefix("status") + ": " + message.success("applied"))


def _rebase_detected() -> None:
    """``kl-base rebase``: detect the base, then reload the symbols there."""
    result = kdbg.find_kbase()
    if result is None:
        print(
            message.error(
                "cannot locate the kernel text base; load a matching vmlinux"
            )
        )
        return
    _rebase(result.base)


def _rebase(base: int) -> None:
    """Reload the loaded symbol file at *base* (``rebase``)."""
    try:
        progspace = gdb.current_progspace()
        objfile = progspace.filename if progspace is not None else None
    except (gdb.error, AttributeError):
        objfile = None
    if not objfile:
        print(message.error("no symbol file is loaded; load a vmlinux first"))
        return
    try:
        gdb.execute(f"add-symbol-file {objfile} {base:#x}")
    except (gdb.error, gdb.MemoryError) as exc:
        print(message.error(f"cannot rebase {objfile!r} at {base:#x}: {exc}"))
        return
    print(message.success(f"rebased {objfile} @ {base:#x}"))


def _dump_idt(count: int) -> None:
    """Dump up to *count* decoded IDT gate descriptors (``idt``)."""
    idt = getattr(kdbg.kbase, "idt", None)
    info = cast("IdtInfo | None", idt() if callable(idt) else None)
    if info is None:
        print(
            message.error(
                "cannot locate the IDT; run under QEMU or load a vmlinux"
            )
        )
        return
    total = int(getattr(info, "count", 0))
    indent = IndentContextManager()
    indent.print(
        indent.prefix("idt") + ": base="
        + indent.addr_hex(int(getattr(info, "base", 0)))
        + " limit=" + indent.aux_hex(int(getattr(info, "limit", 0)))
        + f" count={total}"
        + " source=" + message.notice(str(getattr(info, "source", "?")))
    )
    limit = total if count <= 0 else min(count, total)
    for index in range(limit):
        entry = kdbg.kbase.entry(index, info)
        if entry is None:
            continue
        kernel_gate = getattr(entry, "is_kernel_gate", False)
        if callable(kernel_gate):
            kernel_gate = kernel_gate()
        marker = (
            message.on("kernel")
            if kernel_gate
            else message.off("absent")
            if not bool(getattr(entry, "present", False))
            else message.warn("present")
        )
        indent.print(
            indent.prefix(f"idt[{index}]")
            + ": offset=" + indent.addr_hex(int(getattr(entry, "offset", 0)))
            + " sel=" + indent.aux_hex(int(getattr(entry, "selector", 0)))
            + " type=" + indent.aux_hex(int(getattr(entry, "gate_type", 0)))
            + f" ist={int(getattr(entry, 'ist', 0))}"
            + f" dpl={int(getattr(entry, 'dpl', 0))}"
            + " " + marker
        )


__all__ = [
    "kernlens_base",
]