#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# See the LICENSE file in the top-level directory for details.
"""The overview command: ``kl-status``."""

from __future__ import annotations

import argparse
import sys

import gdb

from .. import __version__
from ..gdb.facade import kdbg
from ..output import message
from ..output.tree import IndentContextManager
from .framework import Command, CommandCategory

_status_parser = argparse.ArgumentParser(
    description="Shows the KernLens version, color mode, KASLR slide, and layout."
)
_status_parser.add_argument(
    "--doctor",
    action="store_true",
    help=(
        "also print what GDB loaded: the object file, DWARF/BTF "
        "availability, and whether a target is attached"
    ),
)


def _doctor_lines() -> list[tuple[str, str]]:
    """The load-path facts ``kl-status --doctor`` adds.

    Every probe is defensive: this is the command a user runs *because*
    something is wrong, so a missing ``gdb`` attribute must produce a
    line, not an exception.
    """
    lines: list[tuple[str, str]] = [
        ("gdb", str(getattr(gdb, "VERSION", "unknown"))),
        ("python", sys.version.split()[0]),
    ]
    try:
        progspace = gdb.current_progspace()
        filename = getattr(progspace, "filename", None)
    except (AttributeError, gdb.error):
        filename = None
    lines.append(("objfile", str(filename) if filename else "none"))

    lookup = getattr(gdb, "lookup_type", None)
    if callable(lookup):
        try:
            lookup("struct page")
        except gdb.error:
            lines.append((
                "dwarf",
                "struct page not found; load a vmlinux with debug info",
            ))
        else:
            lines.append(("dwarf", "struct page resolved"))
    else:
        lines.append(("dwarf", "not checked"))

    try:
        from ..gdb.btf import find_in_gdb

        btf = find_in_gdb()
    except (ImportError, AttributeError, TypeError, ValueError, gdb.error):
        btf = None
    lines.append((
        "btf",
        "loaded image has .BTF" if btf is not None else "no .BTF in the loaded image",
    ))

    try:
        pid = int(getattr(gdb.selected_inferior(), "pid", 0))
    except (AttributeError, TypeError, ValueError, gdb.error):
        pid = 0
    lines.append((
        "target",
        f"attached (pid {pid})" if pid else "no target; use target remote :1234",
    ))
    return lines


@Command(
    _status_parser,
    category=CommandCategory.OVERVIEW,
    aliases=["kl-status"],
    examples="kl-status\nkl-status --doctor",
)
def kernlens_status(doctor: bool = False) -> None:
    indent = IndentContextManager()
    color = kdbg.color_enabled
    indent.print(
        message.notice("KernLens")
        + f" {__version__} — "
        + message.notice("color:") + " "
        + (message.on("on") if color else message.off("off"))
    )
    link = kdbg.link_text()
    # ``reader`` derives the slide on demand for its own reads; ask it for
    # the value actually in effect instead of reporting a stale zero.
    slide = kdbg.kaslr_slide()
    runtime = (
        (link + slide) & 0xFFFFFFFFFFFFFFFF
        if link is not None
        else None
    )
    with indent:
        indent.print(
            indent.prefix("KASLR slide")
            + ": "
            + message.success(f"+{slide:#x}")
        )
        indent.print(
            indent.prefix("_text") + ": link="
            + (indent.addr_hex(link) if link is not None else message.warn("?"))
            + " runtime="
            + (
                indent.addr_hex(runtime)
                if runtime is not None
                else message.warn("?")
            )
        )
        page_offset = kdbg.read_kvar("page_offset_base")
        vmemmap = kdbg.read_kvar("vmemmap_base")
        indent.print(
            indent.prefix("page_offset")
            + ": "
            + (
                indent.addr_hex(page_offset)
                if page_offset is not None
                else message.warn("?")
            )
        )
        indent.print(
            indent.prefix("vmemmap")
            + ": "
            + (
                indent.addr_hex(vmemmap)
                if vmemmap is not None
                else message.warn("?")
            )
        )
        indent.print(
            indent.prefix("topology")
            + f": nr_cpus={kdbg.nr_cpus()} nr_nodes={kdbg.nr_nodes()}"
        )
        if doctor:
            for name, value in _doctor_lines():
                indent.print(indent.prefix(name) + ": " + value)
    print()
    print(
        message.hint("kl-help")
        + " lists every command, "
        + message.hint("kl-help kl-<command>")
        + " explains one"
    )


__all__ = ["kernlens_status"]