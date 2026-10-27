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

from .. import __version__
from ..gdb.facade import kdbg
from ..output import message
from ..output.tree import IndentContextManager
from .framework import Command, CommandCategory

_status_parser = argparse.ArgumentParser(
    description="Shows the KernLens version, color mode, KASLR slide, and layout."
)


@Command(
    _status_parser,
    category=CommandCategory.OVERVIEW,
    aliases=["kl-status"],
    examples="kl-status",
)
def kernlens_status() -> None:
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
    print()
    print(
        message.hint("kl-help")
        + " lists every command, "
        + message.hint("kl-help kl-<command>")
        + " explains one"
    )


__all__ = ["kernlens_status"]