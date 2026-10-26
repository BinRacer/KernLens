#!/usr/bin/env python3
#
# ruff: noqa: EXE001
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""x86_64 address-space classification and translation helpers.

Public surface
--------------

:class:`KAddr`
    Stateless namespace, all-static: ``is_kernel`` / ``is_user`` /
    ``is_direct_map`` / ``is_vmalloc`` / ``virt_to_phys`` /
    ``phys_to_page`` / ``kaslr_runtime`` / ``is_err`` / ``ptr_err`` /
    ``err_ptr`` and friends.

Quick start
-----------

::

    from kernlens.core.addr import KAddr

    KAddr.is_kernel(0xffff888000000000)     # True
    KAddr.is_user(0x00007fffffffffff)       # True
    KAddr.is_direct_map(0xffff888001234000) # True
    KAddr.virt_to_phys(0xffff888000001000)  # 0x1000
    KAddr.phys_to_page(0x1000)              # struct page address
    KAddr.kaslr_runtime(0xffffffff81000000, 0x1e000000)
    KAddr.is_err(0xfffffffffffffff2)        # True
    KAddr.ptr_err(0xfffffffffffffff2)       # 14
"""

from __future__ import annotations

from typing import final

from .constants import (
    KERNEL_BASE,
    KERNEL_BOTTOM,
    MAX_ERRNO,
    MODULE_END,
    MODULE_START,
    PAGE_MASK,
    PAGE_OFFSET_BASE,
    PAGE_SHIFT,
    PAGE_SIZE,
    PTR_BITS,
    PTR_MASK,
    USER_TOP,
    VMALLOC_END,
    VMALLOC_START,
    VMEMAP_BASE,
)
from .validation import check_nonneg

__all__ = [
    "KAddr",
]


# ---------------------------------------------------------------------
# Kernel address helpers
# ---------------------------------------------------------------------


@final
class KAddr:
    """x86_64 address-space classification and translation helpers.

    Every method masks its input to 64 bits first, so a negative Python
    int behaves like the corresponding unsigned kernel value.
    """

    __slots__: tuple[str, ...] = ()

    # --- classification -------------------------------------------------

    @staticmethod
    def is_user(addr: int) -> bool:
        """Return ``True`` when *addr* lies in the user half."""
        return (addr & PTR_MASK) <= USER_TOP

    @staticmethod
    def is_kernel(addr: int) -> bool:
        """Return ``True`` when *addr* lies in the kernel half."""
        return (addr & PTR_MASK) >= KERNEL_BOTTOM

    @staticmethod
    def is_canonical(addr: int, bits: int = 48) -> bool:
        """Return ``True`` when *addr* is a canonical x86-64 pointer.

        *bits* selects the sign-extension width: 48 for 4-level
        paging, 57 for 5-level paging (LA57).
        """
        if bits not in (48, 57):
            raise ValueError(f"bits must be 48 or 57, got {bits}")
        masked = addr & PTR_MASK
        sign = (masked >> (bits - 1)) & 1
        top = masked >> bits
        if sign:
            return top == (1 << (PTR_BITS - bits)) - 1
        return top == 0

    @staticmethod
    def is_direct_map(
        addr: int,
        base: int = PAGE_OFFSET_BASE,
        size: int = 1 << 46,
    ) -> bool:
        """Return ``True`` when *addr* lies in the direct map."""
        masked = addr & PTR_MASK
        return base <= masked < base + size

    @staticmethod
    def is_vmemmap(
        addr: int,
        base: int = VMEMAP_BASE,
        size: int = 1 << 40,
    ) -> bool:
        """Return ``True`` when *addr* lies in the vmemmap array."""
        masked = addr & PTR_MASK
        return base <= masked < base + size

    @staticmethod
    def is_vmalloc(addr: int) -> bool:
        """Return ``True`` when *addr* lies in the vmalloc region."""
        masked = addr & PTR_MASK
        return VMALLOC_START <= masked <= VMALLOC_END

    @staticmethod
    def is_module(addr: int) -> bool:
        """Return ``True`` when *addr* lies in the module region."""
        masked = addr & PTR_MASK
        return MODULE_START <= masked <= MODULE_END

    @staticmethod
    def is_text(addr: int, base: int = KERNEL_BASE) -> bool:
        """Return ``True`` when *addr* lies between ``_text`` and modules."""
        masked = addr & PTR_MASK
        return base <= masked < MODULE_START

    # --- translation ----------------------------------------------------

    @staticmethod
    def virt_to_phys(
        addr: int,
        base: int = PAGE_OFFSET_BASE,
        size: int = 1 << 46,
    ) -> int:
        """Translate a direct-map address to its physical address.

        Raises ``ValueError`` when *addr* is outside
        ``[base, base + size)``; translating a vmalloc or text address
        by subtraction would otherwise produce a bogus huge physical
        address.
        """
        masked = addr & PTR_MASK
        if size <= 0:
            raise ValueError(f"size must be > 0, got {size}")
        if not KAddr.is_direct_map(masked, base, size):
            raise ValueError(
                f"addr {masked:#x} is outside the direct map "
                f"[{base:#x}, {base + size:#x})"
            )
        return masked - base

    @staticmethod
    def phys_to_virt(phys: int, base: int = PAGE_OFFSET_BASE) -> int:
        """Translate a physical address to a direct-map address."""
        check_nonneg(phys, "phys")
        return (phys + base) & PTR_MASK

    @staticmethod
    def phys_to_pfn(phys: int) -> int:
        """Return the page frame number of a physical address."""
        check_nonneg(phys, "phys")
        return phys >> PAGE_SHIFT

    @staticmethod
    def pfn_to_phys(pfn: int) -> int:
        """Return the physical address of a page frame number."""
        check_nonneg(pfn, "pfn")
        return pfn << PAGE_SHIFT

    @staticmethod
    def phys_to_page(
        phys: int,
        vmemmap: int = VMEMAP_BASE,
        page_size: int = 64,
    ) -> int:
        """Return the address of the ``struct page`` for *phys*."""
        check_nonneg(phys, "phys")
        if page_size <= 0:
            raise ValueError(f"page_size must be > 0, got {page_size}")
        return (vmemmap + (phys >> PAGE_SHIFT) * page_size) & PTR_MASK

    @staticmethod
    def virt_to_page(
        addr: int,
        page_offset_base: int = PAGE_OFFSET_BASE,
        vmemmap_base: int = VMEMAP_BASE,
        page_size: int = 64,
        direct_map_size: int = 1 << 46,
    ) -> int:
        """Translate a direct-map address to its ``struct page``."""
        phys = KAddr.virt_to_phys(
            addr, page_offset_base, direct_map_size,
        )
        return KAddr.phys_to_page(phys, vmemmap_base, page_size)

    @staticmethod
    def page_to_phys(
        page: int,
        vmemmap: int = VMEMAP_BASE,
        page_size: int = 64,
    ) -> int:
        """Return the physical address a ``struct page`` maps.

        Inverse of :meth:`phys_to_page`.  The caller must only pass a
        *first* (head, order-0) page: a tail page of a compound page
        would decode to the wrong frame.
        """
        if page_size <= 0:
            raise ValueError(f"page_size must be > 0, got {page_size}")
        pfn = (page - vmemmap) // page_size
        if pfn < 0:
            raise ValueError(f"{page:#x} is below the vmemmap base {vmemmap:#x}")
        return pfn << PAGE_SHIFT

    @staticmethod
    def page_to_virt(
        page: int,
        page_offset_base: int = PAGE_OFFSET_BASE,
        vmemmap_base: int = VMEMAP_BASE,
        page_size: int = 64,
    ) -> int:
        """Translate a ``struct page`` to its direct-map address."""
        phys = KAddr.page_to_phys(page, vmemmap_base, page_size)
        return KAddr.phys_to_virt(phys, page_offset_base)

    @staticmethod
    def page_align(addr: int) -> int:
        """Mask *addr* to its page-aligned (down) base."""
        return addr & PTR_MASK & ~PAGE_MASK

    @staticmethod
    def page_align_up(addr: int) -> int:
        """Round *addr* up to the next page boundary (idempotent)."""
        return (addr + PAGE_SIZE - 1) & PTR_MASK & ~PAGE_MASK

    # --- KASLR ----------------------------------------------------------

    @staticmethod
    def kaslr_runtime(link_addr: int, offset: int) -> int:
        """Add the KASLR *offset* to a link-time address."""
        return (link_addr + offset) & PTR_MASK

    @staticmethod
    def kaslr_link(runtime_addr: int, offset: int) -> int:
        """Subtract the KASLR *offset* from a runtime address."""
        return (runtime_addr - offset) & PTR_MASK

    # --- ERR_PTR --------------------------------------------------------

    @staticmethod
    def is_err(ptr: int) -> bool:
        """Return ``True`` when *ptr* is an ``ERR_PTR`` value."""
        masked = ptr & PTR_MASK
        return masked >= PTR_MASK - MAX_ERRNO + 1

    @staticmethod
    def ptr_err(ptr: int) -> int:
        """Decode an ``ERR_PTR`` into the positive errno it carries."""
        if not KAddr.is_err(ptr):
            raise ValueError(f"not an ERR_PTR: {ptr:#x}")
        return (1 << PTR_BITS) - (ptr & PTR_MASK)

    @staticmethod
    def err_ptr(err: int) -> int:
        """Encode a negative *err* (``-1`` .. ``-MAX_ERRNO``) as an ``ERR_PTR``."""
        if not -MAX_ERRNO <= err <= -1:
            raise ValueError(
                f"err must be in [-{MAX_ERRNO}, -1], got {err}"
            )
        return ((1 << PTR_BITS) + err) & PTR_MASK

    # --- pointer tags ---------------------------------------------------

    @staticmethod
    def ptr_tag(addr: int, mask: int = PAGE_MASK) -> int:
        """Return the tag bits of *addr* covered by *mask*."""
        return addr & PTR_MASK & mask

    @staticmethod
    def strip_tag(addr: int, mask: int = PAGE_MASK) -> int:
        """Return *addr* with the tag bits covered by *mask* cleared."""
        return addr & PTR_MASK & ~mask
