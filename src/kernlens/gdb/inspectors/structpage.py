#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""x86_64 ``struct page`` helpers: ``page_type`` and ``_refcount``.

The kernel packs the type into the high byte of the word at
``page + 0x30`` (the 32-bit ``mapcount`` plus the 24-bit type), and the
refcount lives at ``page + 0x34``.
"""

from __future__ import annotations

from ._base import InspectorBase

#: ``enum page_type`` names, in the order the kernel packs them.
PAGE_TYPES: tuple[str, ...] = (
    "buddy", "offline", "table", "guard",
    "hugetlb", "slab", "zsmalloc", "unaccepted",
)

#: ``CONFIG_PAGE_TYPE`` layout of the ``struct page`` type word, read from
#: a Linux 6.1.134 (x86_64) vmlinux.  The type is packed into the high
#: byte of the word at ``_mapcount``, and ``_refcount`` follows it.
PAGE_TYPE_FALLBACK = 0x30
PAGE_REFCOUNT_FALLBACK = 0x34


class StructPageInspector(InspectorBase):
    """Decode the packed ``struct page`` type/refcount fields."""

    __slots__: tuple[str, ...] = ()

    def page_type(self, page: int) -> str:
        """Return the ``enum page_type`` name for a ``struct page``.

        The kernel packs the type into the high byte of the word at
        ``_mapcount`` (the 32-bit mapcount plus the 24-bit type).
        A value of ``-1`` means "initialized, not typed"; a non-negative
        value is a live mapcount.
        """
        offset = (
            self._layout_offset("struct page", "_mapcount")
            or PAGE_TYPE_FALLBACK
        )
        signed = self._read_u32(page + offset, signed=True)
        if signed is None:
            return "?"
        if signed == -1:
            return "initialized"
        if signed >= 0:
            return f"mapcount: {signed}"
        raw = signed & 0xFFFFFFFF
        idx = (raw >> 24) - 0xF0
        if 0 <= idx < len(PAGE_TYPES):
            return PAGE_TYPES[idx]
        return "unknown"

    def page_refcount(self, page: int) -> int | None:
        """Return ``page->_refcount`` as a signed 32-bit value."""
        offset = (
            self._layout_offset("struct page", "_refcount")
            or PAGE_REFCOUNT_FALLBACK
        )
        return self._read_u32(page + offset, signed=True)


__all__ = [
    "PAGE_REFCOUNT_FALLBACK",
    "PAGE_TYPE_FALLBACK",
    "PAGE_TYPES",
    "StructPageInspector",
]