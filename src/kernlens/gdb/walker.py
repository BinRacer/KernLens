#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Live x86_64 page-table walking and its result types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast, final

import gdb

from ..core.paging import KPageTable
from ._types import _IntConvertible
from .reader import MemoryReader

#: Mask for a 64-bit value.
_MASK64 = 0xFFFFFFFFFFFFFFFF


@final
@dataclass(frozen=True, slots=True)
class WalkLevel:
    """One decoded level of an x86_64 page-table walk."""

    #: Level name: ``pgd`` / ``p4d`` / ``pud`` / ``pmd`` / ``pte``.
    name: str
    #: 9-bit index of the entry inside the table.
    index: int
    #: Address of the 8-byte entry in memory.
    entry_addr: int
    #: Raw entry value.
    value: int
    #: Next-level table base, or ``None`` for a leaf / absent entry.
    next_table: int | None = None
    #: Whether this entry is a huge-page leaf (``PS`` bit set).
    huge: bool = False


@final
@dataclass(frozen=True, slots=True)
class PageWalk:
    """Result of walking the page tables for one virtual address.

    ``phys`` is ``None`` unless the walk reached a present leaf; in that
    case ``page_size`` is 4096, 2 MiB, or 1 GiB.  ``note`` explains why a
    walk stopped early and is ``None`` for a complete walk.
    """

    va: int
    root: int | None
    five_level: bool
    levels: tuple[WalkLevel, ...] = ()
    phys: int | None = None
    page_size: int | None = None
    note: str | None = None

    @property
    def ok(self) -> bool:
        """Whether the walk reached a present leaf entry."""
        return self.phys is not None


@final
class PageTableWalker:
    """Walk x86_64 page tables through a :class:`MemoryReader`.

    ``walk`` can take an explicit ``root`` (a ``CR3`` value or a
    page-table base) and an explicit ``five_level`` flag, which makes a
    captured table dump reproducible.  With neither supplied it reads
    ``$cr3`` / ``$cr4`` from the live debuggee, falling back to the
    ``init_top_pgt`` / ``swapper_pg_dir`` symbols when ``$cr3`` is not
    available.

    Unreadable entries, missing next-level tables, and non-present
    entries end the walk with a ``note``; the method never raises for
    them, because it is meant to run from breakpoint callbacks.
    """

    __slots__: tuple[str, ...] = ("_reader",)

    #: Level shifts, outermost first.
    _SHIFTS_4: tuple[int, ...] = (39, 30, 21, 12)
    _SHIFTS_5: tuple[int, ...] = (48, 39, 30, 21, 12)
    _NAMES_4: tuple[str, ...] = ("pgd", "pud", "pmd", "pte")
    _NAMES_5: tuple[str, ...] = ("pgd", "p4d", "pud", "pmd", "pte")

    def __init__(self, reader: MemoryReader) -> None:
        self._reader: MemoryReader = reader

    # --- paging roots ---------------------------------------------------

    def _mapped_root(self, cr3: int) -> int:
        """Map a physical ``CR3`` to a virtual address we can read.

        ``$cr3`` holds a physical address, but the page tables live in
        the direct map, so their entries are only readable at
        ``page_offset_base + phys``.  Walking a physical address would
        fail with "unreadable pgd entry".
        """
        if cr3 >= 0xFFFF800000000000:
            return cr3
        return self._mapped(cr3)

    def _mapped(self, addr: int) -> int:
        """Direct-map *addr* when it is a physical address."""
        if addr >= 0xFFFF800000000000:
            return addr
        page_offset = self._reader.read_kvar("page_offset_base")
        return (page_offset + addr) & _MASK64 if page_offset else addr

    def _phys(self, addr: int) -> int:
        """Normalise a virtual or physical table base to a physical base.

        ``$cr3`` and the entries it points to are physical; the
        ``init_top_pgt`` fallback is already kernel-virtual.  Unmasking
        the virtual case (rather than masking the whole value) keeps the
        low physical bits that :meth:`KPageTable.entry_addr` needs.
        """
        if addr < 0xFFFF800000000000:
            return addr
        page_offset = self._reader.read_kvar("page_offset_base")
        return (addr - page_offset) & _MASK64 if page_offset else addr

    def read_cr3(self) -> int | None:
        """Return the live ``CR3`` page-table base (physical), or ``None``."""
        try:
            value = gdb.parse_and_eval("$cr3")
            return (
                int(cast(_IntConvertible, value))
                & KPageTable.PTE_ADDR_MASK
            )
        except (gdb.error, TypeError, ValueError):
            return None

    def la57(self) -> bool | None:
        """Return ``True`` when ``CR4.LA57`` is set; ``None`` if unknown."""
        try:
            value = gdb.parse_and_eval("$cr4")
            return bool(int(cast(_IntConvertible, value)) & (1 << 12))
        except (gdb.error, TypeError, ValueError):
            return None

    def root(self) -> int | None:
        """Best-effort page-table base: ``CR3``, else the kernel top table."""
        cr3 = self.read_cr3()
        if cr3:
            return cr3
        for symbol in ("init_top_pgt", "swapper_pg_dir"):
            table = self._reader.kvar_addr(symbol)
            if table:
                return table
        return None

    # --- walk -----------------------------------------------------------

    def walk(
        self,
        va: int,
        *,
        five_level: bool | None = None,
        root: int | None = None,
    ) -> PageWalk:
        """Walk the tables for *va* and return every decoded level."""
        va &= 0xFFFFFFFFFFFFFFFF
        if five_level is None:
            five_level = self.la57() is True
        if root is None:
            root = self.root()
        if not root:
            return PageWalk(
                va=va, root=None, five_level=five_level,
                note="cannot determine the page-table root "
                "(CR3/init_top_pgt unreadable)",
            )

        table = self._phys(root) & KPageTable.PTE_ADDR_MASK
        # ``entry_addr`` wants a physical table base; each entry is
        # direct-mapped for the read because the tables themselves are
        # only mapped there.
        names = self._NAMES_5 if five_level else self._NAMES_4
        shifts = self._SHIFTS_5 if five_level else self._SHIFTS_4
        levels: list[WalkLevel] = []

        for name, shift in zip(names, shifts):
            index = (va >> shift) & 0x1FF
            entry_addr = KPageTable.entry_addr(table, index)
            value = self._reader.u64(
                f"*(unsigned long *){self._mapped(entry_addr):#x}"
            )
            if value is None:
                return PageWalk(
                    va=va, root=root, five_level=five_level,
                    levels=tuple(levels),
                    note=f"unreadable {name} entry at {entry_addr:#x}",
                )
            if not KPageTable.pte_present(value):
                levels.append(
                    WalkLevel(name, index, entry_addr, value)
                )
                return PageWalk(
                    va=va, root=root, five_level=five_level,
                    levels=tuple(levels),
                    note=f"{name} entry is not present",
                )

            # PS is meaningful in a PUD/PMD entry; bit 7 is PAT in a PTE.
            if name in ("pud", "pmd") and KPageTable.pte_is_huge(value):
                page_size = 1 << (30 if name == "pud" else 21)
                if name == "pud":
                    phys = KPageTable.pud_to_phys(value, va)
                else:
                    phys = KPageTable.pmd_to_phys(value, va)
                levels.append(
                    WalkLevel(name, index, entry_addr, value, huge=True)
                )
                return PageWalk(
                    va=va, root=root, five_level=five_level,
                    levels=tuple(levels), phys=phys,
                    page_size=page_size,
                )

            if name == "pte":
                levels.append(
                    WalkLevel(name, index, entry_addr, value)
                )
                return PageWalk(
                    va=va, root=root, five_level=five_level,
                    levels=tuple(levels),
                    phys=KPageTable.pte_to_phys(value, va),
                    page_size=1 << 12,
                )

            next_table = KPageTable.next_table(value)
            levels.append(
                WalkLevel(name, index, entry_addr, value, next_table)
            )
            if not next_table:
                return PageWalk(
                    va=va, root=root, five_level=five_level,
                    levels=tuple(levels),
                    note=f"{name} entry has no next-level table",
                )
            table = next_table

        return PageWalk(
            va=va, root=root, five_level=five_level,
            levels=tuple(levels), note="paging levels are not configured",
        )


__all__ = ["PageTableWalker", "PageWalk", "WalkLevel"]
