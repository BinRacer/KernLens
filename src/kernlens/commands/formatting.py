#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# See the LICENSE file in the top-level directory for details.
"""Output formatting and argument-parsing helpers for the commands.

Everything here used to live at the top of ``gdbinit.py``.  The helpers
are stateless and read the ``kdbg`` facade directly, so both the command
functions and the help renderer share one implementation.

The helpers fall into three groups:

* writers, painters and small renderers (:func:`writeln`,
  :func:`style`, :func:`fmt_onoff`, :func:`fmt_cpu_ranges`);
* argument parsers used as ``argparse`` ``type=`` callables
  (:func:`parse_int`, :func:`parse_depth`);
* kernel facts derived from the facade with a built-in fallback
  (:func:`kernel_running`, :func:`default_base`,
  :func:`page_offset_base`, :func:`vmemmap_base`).
"""

from __future__ import annotations

import gdb

from .. import KERNEL_BASE, PAGE_OFFSET_BASE, VMEMAP_BASE
from ..gdb.facade import kdbg
from ..output import message

#: Mask for a 64-bit value.
MASK64 = 0xFFFFFFFFFFFFFFFF

#: GDB's memory-error class (falls back to ``gdb.error``).
GDB_MEMORY_ERROR = getattr(gdb, "MemoryError", gdb.error)


def writeln(message: str) -> None:
    """Write one line to GDB's stdout."""
    gdb.write(message + "\n")


def style(text: str, color: str) -> str:
    """Style *text* through the shared KernLens styler."""
    return kdbg.style(text, color)


def parse_int(text: str, what: str = "value") -> int:
    """Parse a Python/GDB-style integer, accepting bare hex too."""
    try:
        return int(text, 0)
    except ValueError:
        try:
            return int(text, 16)
        except ValueError as exc:
            raise gdb.GdbError(
                f"{what} must be an integer, got {text!r}"
            ) from exc


def parse_depth(argument: str, default: int = 8) -> int:
    """Parse a bounded backtrace depth."""
    text = argument.strip()
    if not text:
        return default
    depth = parse_int(text, "depth")
    if not 1 <= depth <= 128:
        raise gdb.GdbError("depth must be between 1 and 128")
    return depth


def fmt_cpu_ranges(cpus: list[int]) -> str:
    """Format CPU ids as compact ranges, e.g. ``0-3,6,8-9``."""
    if not cpus:
        return "-"
    ranges: list[str] = []
    start = previous = cpus[0]
    for cpu in cpus[1:]:
        if cpu == previous + 1:
            previous = cpu
            continue
        ranges.append(
            f"{start}" if start == previous else f"{start}-{previous}"
        )
        start = previous = cpu
    ranges.append(f"{start}" if start == previous else f"{start}-{previous}")
    return ",".join(ranges)


def fmt_onoff(value: bool) -> str:
    """Paint a boolean as an on/off status."""
    return message.on("True") if value else message.off("False")


def kernel_running() -> bool:
    """Return ``True`` when GDB has a live inferior with a PID."""
    try:
        inferior = gdb.selected_inferior()
    except (AttributeError, gdb.error):
        return False
    try:
        return int(getattr(inferior, "pid", 0)) > 0
    except (TypeError, ValueError, gdb.error):
        return False


def default_base() -> int:
    """Return the link-time/default kernel text base."""
    link = kdbg.link_text()
    return link if link is not None else KERNEL_BASE


def page_offset_base() -> int:
    """Return runtime ``page_offset_base`` or the built-in fallback."""
    value = kdbg.read_kvar("page_offset_base")
    return value if value is not None else PAGE_OFFSET_BASE


def vmemmap_base() -> int:
    """Return runtime ``vmemmap_base`` or the built-in fallback."""
    value = kdbg.read_kvar("vmemmap_base")
    return value if value is not None else VMEMAP_BASE


__all__ = [
    "GDB_MEMORY_ERROR",
    "MASK64",
    "default_base",
    "fmt_cpu_ranges",
    "fmt_onoff",
    "kernel_running",
    "page_offset_base",
    "parse_depth",
    "parse_int",
    "style",
    "vmemmap_base",
    "writeln",
]