#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Kernel layout constants and pointer-width facts.

The values describe a generic x86_64 kernel with KASLR disabled; live
tools override the layout through :class:`kernlens.gdb.DebugConfig`.
"""

from typing import Final

# ---------------------------------------------------------------------
# Page arithmetic / pointer width
# ---------------------------------------------------------------------

PAGE_SHIFT: Final[int] = 12
PAGE_SIZE: Final[int] = 1 << PAGE_SHIFT
PAGE_MASK: Final[int] = PAGE_SIZE - 1
PTR_BITS: Final[int] = 64
PTR_HEX_DIGITS: Final[int] = PTR_BITS // 4

PTR_MASK: Final[int] = (1 << PTR_BITS) - 1

# ---------------------------------------------------------------------
# Kernel layout (x86_64, KASLR off)
# ---------------------------------------------------------------------

KERNEL_BASE: Final[int] = 0xFFFFFFFF81000000
KERNEL_OFFSET: Final[int] = 0
PAGE_OFFSET_BASE: Final[int] = 0xFFFF888000000000
VMEMAP_BASE: Final[int] = 0xFFFFEA0000000000

# ---------------------------------------------------------------------
# Address-space boundaries (x86_64)
# ---------------------------------------------------------------------

USER_TOP: Final[int] = 0x00007FFFFFFFFFFF
KERNEL_BOTTOM: Final[int] = 0xFFFF800000000000
VMALLOC_START: Final[int] = 0xFFFFC90000000000
VMALLOC_END: Final[int] = 0xFFFFE8FFFFFFFFFF
MODULE_START: Final[int] = 0xFFFFFFFFC0000000
MODULE_END: Final[int] = 0xFFFFFFFFFEFFFFFF
MAX_ERRNO: Final[int] = 4095

__all__ = [
    "PAGE_SHIFT",
    "PAGE_SIZE",
    "PAGE_MASK",
    "PTR_BITS",
    "PTR_HEX_DIGITS",
    "PTR_MASK",
    "KERNEL_BASE",
    "KERNEL_OFFSET",
    "PAGE_OFFSET_BASE",
    "VMEMAP_BASE",
    "USER_TOP",
    "KERNEL_BOTTOM",
    "VMALLOC_START",
    "VMALLOC_END",
    "MODULE_START",
    "MODULE_END",
    "MAX_ERRNO",
]
