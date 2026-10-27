#!/usr/bin/env python3
#
# ruff: noqa: EXE001
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""KernLens - Linux kernel introspection for GDB.

Public surface
--------------

The package root re-exports the public core and output names so
``from kernlens import X`` works for the host-side API.  The GDB adapter
is imported explicitly from :mod:`kernlens.gdb`.  The full API lives in:

* :mod:`kernlens.core.bitops` — :class:`BitOps`, :data:`BITS`
* :mod:`kernlens.core.codec` — :class:`IntCodec` / :class:`ByteOrderCodec`
  / :class:`ByteOrder` / :class:`IntType` / :data:`LE` / :data:`BE`
* :mod:`kernlens.core.fmt` — :class:`IntFmt`
* :mod:`kernlens.core.addr` — :class:`KAddr`
* :mod:`kernlens.core.paging` — :class:`KPageTable`
* :mod:`kernlens.output` — :class:`Logger` / :class:`Palette` /
  :class:`LogLevel` / :class:`Styler`

The public kernel layout constants live in
:mod:`kernlens.core.constants`.
"""

from .core.addr import KAddr
from .core.bitops import BITS, BitOps
from .core.codec import (
    BE,
    ByteOrder,
    ByteOrderCodec,
    IntCodec,
    IntType,
    LE,
)
from .core.constants import (
    KERNEL_BASE,
    KERNEL_BOTTOM,
    KERNEL_OFFSET,
    MAX_ERRNO,
    MODULE_END,
    MODULE_START,
    PAGE_MASK,
    PAGE_OFFSET_BASE,
    PAGE_SHIFT,
    PAGE_SIZE,
    PTR_BITS,
    PTR_HEX_DIGITS,
    USER_TOP,
    VMALLOC_END,
    VMALLOC_START,
    VMEMAP_BASE,
)
from .core.fmt import IntFmt
from .core.paging import KPageTable
from .output import LogLevel, Logger, Palette, Styler

__version__ = "0.3.0"

#: Natural-order sorted; see the docstring above for the grouping each
#: name belongs to.
__all__ = [
    "BE",
    "BITS",
    "BitOps",
    "ByteOrder",
    "ByteOrderCodec",
    "IntCodec",
    "IntFmt",
    "IntType",
    "KAddr",
    "KERNEL_BASE",
    "KERNEL_BOTTOM",
    "KERNEL_OFFSET",
    "KPageTable",
    "LE",
    "LogLevel",
    "Logger",
    "MAX_ERRNO",
    "MODULE_END",
    "MODULE_START",
    "PAGE_MASK",
    "PAGE_OFFSET_BASE",
    "PAGE_SHIFT",
    "PAGE_SIZE",
    "PTR_BITS",
    "PTR_HEX_DIGITS",
    "Palette",
    "Styler",
    "USER_TOP",
    "VMALLOC_END",
    "VMALLOC_START",
    "VMEMAP_BASE",
    "__version__",
]
