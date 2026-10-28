#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""Kernel base and KASLR commands (pwndbg-style).

``kernlens-base`` / ``kbase`` / ``kaslr`` / ``kaslr-offset``.
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
    hide,
    parse_int_arg,
)

_MASK64 = 0xFFFFFFFFFFFFFFFF


# =========================================================================
# base
# =========================================================================

_base_parser = argparse.ArgumentParser(
    description="Selects the runtime kernel text base and KASLR slide."
)


@Command(
    _base_parser,
    category=CommandCategory.KERNEL_BASE,
    aliases=["kl-base"],
    examples="kl-base\n  auto-detect and apply the runtime text base",
)
def kernlens_base() -> None:
    result = kdbg.find_kbase()
    indent = IndentContextManager()
    if result is None:
        if kernel_running():
            print(
                message.error(
                    "kernel is running but the text base could not be "
                    "detected; load a matching vmlinux or use "
                    "kl-kaslr/kl-kaslr-offset manually"
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
    indent.print(indent.prefix("status") + ": " + message.success("kernel running"))


# =========================================================================
# kbase
# =========================================================================

_kbase_parser = argparse.ArgumentParser(
    description="Finds the kernel virtual base address."
)
_kbase_parser.add_argument(
    "-r", "--rebase", action="store_true",
    help="rebase loaded symbol file",
)
_kbase_parser.add_argument(
    "-v", "--verbose", action="store_true",
    help="also print the physical address of the text base",
)
# Legacy aliases (kept working, hidden from --help): earlier KernLens used
# ``-p/--phys`` where pwndbg uses ``-v/--verbose``, and ``-s/--set`` /
# ``-i/--idt`` which pwndbg's kbase does not have.
hide(_kbase_parser.add_argument(
    "-p", "--phys", action="store_true", dest="phys",
))
hide(_kbase_parser.add_argument(
    "-s", "--set", action="store_true", dest="set_offset",
))
hide(_kbase_parser.add_argument(
    "-i", "--idt", nargs="?", type=int, const=16, default=None,
    metavar="COUNT", dest="idt",
))
# KernLens-only: fold kl-kaslr / kl-kaslr-offset into kbase so the slide
# can be corrected where it is *reported* (kbase already prints
# ``kaslr=+0x...``).  Hidden like the other extras, so the pwndbg help
# surface is unchanged.
_kbase_apply = _kbase_parser.add_mutually_exclusive_group()
hide(_kbase_apply.add_argument(
    "--text", type=parse_int_arg, default=None, metavar="ADDR",
    help="set the KASLR slide from a runtime _text address",
))
hide(_kbase_apply.add_argument(
    "--offset", type=parse_int_arg, default=None, metavar="SLIDE",
    help="set the KASLR slide directly (e.g. 0x18e00000)",
))


@Command(
    _kbase_parser,
    category=CommandCategory.KERNEL_BASE,
    aliases=["kl-kbase"],
    examples=(
        "kl-kbase\n"
        "kl-kbase --verbose\n"
        "kl-kbase --rebase"
    ),
    notes=(
        "KernLens extras (hidden from --help): ``-s/--set`` applies the\n"
        "derived KASLR slide to the session, ``-i/--idt [count]`` dumps\n"
        "the interrupt descriptor table, and ``--text <addr>`` /\n"
        "``--offset <slide>`` set the slide here (the equivalents of\n"
        "``kl-kaslr`` and ``kl-kaslr-offset``), which is convenient\n"
        "because the report above already prints ``kaslr=+0x...``."
    ),
)
def kernlens_kbase(
    rebase: bool = False,
    verbose: bool = False,
    phys: bool = False,
    set_offset: bool = False,
    idt: int | None = None,
    text: int | None = None,
    offset: int | None = None,
) -> None:
    if idt is not None:
        _dump_idt(idt)
        return
    if text is not None:
        kernlens_kaslr(text)
        return
    if offset is not None:
        kernlens_kaslr_offset(offset)
        return
    result = kdbg.find_kbase()
    if result is None:
        print(
            message.error(
                "cannot locate the kernel text base; load a matching "
                "vmlinux or run under QEMU"
            )
        )
        return
    indent = IndentContextManager()
    indent.print(indent.prefix("text base") + ": " + indent.addr_hex(result.base))
    method = (
        message.notice(result.method)
        + (f"  handler={result.handler:#x}" if result.handler is not None else "")
    )
    indent.print(indent.prefix("method") + ": " + method)
    if result.handler_symbol:
        indent.print(
            indent.prefix("symbol") + ": " + message.notice(result.handler_symbol)
        )
    if result.idt is not None:
        indent.print(
            indent.prefix("idt") + ": base=" + indent.addr_hex(result.idt.base)
            + " limit=" + indent.aux_hex(result.idt.limit)
            + " source=" + message.notice(result.idt.source)
        )
    if result.link_text is not None:
        kaslr = (
            f"+{result.kaslr_offset:#x}"
            if result.kaslr_offset is not None
            else message.warn("?")
        )
        indent.print(
            indent.prefix("link _text") + ": "
            + indent.addr_hex(result.link_text) + f"  kaslr={kaslr}"
        )
    if phys or verbose:
        walk = kdbg.walk(result.base)
        indent.print(
            indent.prefix("Physical") + ": "
            + (
                indent.aux_hex(walk.phys)
                if walk.phys is not None
                else message.warn("?")
            )
        )
    if set_offset:
        if result.kaslr_offset is None:
            print(
                message.error("cannot derive the KASLR offset without &_text")
            )
            return
        kdbg.kaslr_offset = result.kaslr_offset
        indent.print(
            indent.prefix("KASLR offset set") + f": +{result.kaslr_offset:#x}"
        )
    elif result.kaslr_offset and result.link_text is not None:
        indent.print(
            indent.prefix("hint")
            + ": " + message.hint("kl-kbase --set applies this slide")
        )
    if rebase:
        _rebase(result.base)


def _rebase(base: int) -> None:
    """Reload the loaded symbol file at *base* (``--rebase``)."""
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
    """Dump up to *count* decoded IDT gate descriptors (``--idt``)."""
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
        + f" count={total} source={message.notice(str(getattr(info, 'source', '?')))}"
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


# =========================================================================
# kaslr / kaslr-offset
# =========================================================================

_kaslr_parser = argparse.ArgumentParser(
    description="Sets the KASLR slide from a runtime _text address."
)
_kaslr_parser.add_argument(
    "runtime_text", type=parse_int_arg,
    help="runtime address of the _text symbol",
)


@Command(
    _kaslr_parser,
    category=CommandCategory.KERNEL_BASE,
    aliases=["kl-kaslr"],
    examples="kl-kaslr 0xffffffff83000000",
)
def kernlens_kaslr(runtime_text: int) -> None:
    link = kdbg.link_text()
    if link is None:
        print(
            message.error(
                "cannot resolve &_text; load a matching vmlinux first"
            )
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


_kaslr_offset_parser = argparse.ArgumentParser(
    description="Sets the KASLR slide directly."
)
_kaslr_offset_parser.add_argument(
    "offset", type=parse_int_arg, help="KASLR slide (e.g. 0x18e00000)",
)


@Command(
    _kaslr_offset_parser,
    category=CommandCategory.KERNEL_BASE,
    aliases=["kl-kaslr-offset"],
    examples="kl-kaslr-offset 0x18e00000\nkl-kaslr-offset 0",
)
def kernlens_kaslr_offset(offset: int) -> None:
    offset &= _MASK64
    kdbg.kaslr_offset = offset
    print(message.notice("KASLR offset:") + f" +{offset:#x}")


__all__ = [
    "kernlens_base",
    "kernlens_kaslr",
    "kernlens_kaslr_offset",
    "kernlens_kbase",
]