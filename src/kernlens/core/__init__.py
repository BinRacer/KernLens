#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Pure-Python core: bit math, codecs, formatting, addresses, and paging.

Nothing in this package imports ``gdb``; it is safe to use in unit
tests, scripts, and host-side tooling.
"""

from .addr import KAddr
from .bitops import BITS, BitOps
from .codec import BE, LE, ByteOrder, ByteOrderCodec, IntCodec, IntType
from .constants import (
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
from .fmt import IntFmt
from .paging import KPageTable

__all__ = [
    "BE", "BITS", "BitOps", "ByteOrder", "ByteOrderCodec", "IntCodec",
    "IntFmt", "IntType", "KAddr", "KERNEL_BASE", "KERNEL_BOTTOM",
    "KERNEL_OFFSET", "KPageTable", "LE", "MAX_ERRNO", "MODULE_END",
    "MODULE_START", "PAGE_MASK", "PAGE_OFFSET_BASE", "PAGE_SHIFT",
    "PAGE_SIZE", "PTR_BITS", "PTR_HEX_DIGITS", "USER_TOP", "VMALLOC_END",
    "VMALLOC_START", "VMEMAP_BASE",
]
