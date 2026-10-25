#!/usr/bin/env python3
#
# ruff: noqa: EXE001
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""x86_64 page-table helpers (4-level and 5-level paging).

Public surface
--------------

:class:`KPageTable`
    Stateless namespace, all-static.  Covers index extraction (PGD /
    P4D / PUD / PMD / PTE / offset), address canonicalization,
    page-table entry address computation, PTE decoding (present / pfn
    / huge / flags), huge-page splitting (2 MiB, 1 GiB), and
    physical-address construction from a walked PTE.

    These functions only compute addresses and decode entries; they
    never read memory.  Walking a live page table in gdb combines them
    with the toolkit's ``MemoryReader``.

Quick start
-----------

::

    from kernlens.core.paging import KPageTable

    KPageTable.split(0xffff888000001234)
    # (0x111, 0x000, 0x000, 0x001, 0x234)

    KPageTable.split_5(0xffff800000001234)
    # (0x1ff, 0x100, 0x000, 0x000, 0x001, 0x234)

    KPageTable.pte_present(0x8000000000123067)   # True
    KPageTable.pte_pfn(0x8000000000123067)       # 0x123
    KPageTable.pte_is_huge(0x80000000001230e7)   # True (PS=1)
    KPageTable.pte_flags(0x8000000000123067)
    # ['P', 'RW', 'US', 'A', 'D', 'NX']
"""

from __future__ import annotations

from typing import Final, final

from .constants import PAGE_MASK, PAGE_SHIFT, PTR_MASK

__all__ = [
    "KPageTable",
]


# ---------------------------------------------------------------------
# Page-table helpers
# ---------------------------------------------------------------------


@final
class KPageTable:
    """x86_64 page-table helpers, all-static.

    Covers both 4-level paging (48-bit VA) and 5-level paging (57-bit
    VA, LA57).  Every 5-level-only method takes ``five_level=True``;
    every other method accepts the same keyword with default ``False``.
    """

    __slots__: tuple[str, ...] = ()

    # --- page-table geometry --------------------------------------------

    BITS_PER_LEVEL: Final[int] = 9
    ENTRIES_PER_LEVEL: Final[int] = 1 << BITS_PER_LEVEL
    ENTRY_SIZE: Final[int] = 8
    PTE_SHIFT: Final[int] = 12
    HUGE_2M_SHIFT: Final[int] = 21
    HUGE_1G_SHIFT: Final[int] = 30
    PGD_SHIFT_4: Final[int] = 39
    PGD_SHIFT_5: Final[int] = 48
    PHYS_BITS: Final[int] = 52

    # --- PTE flag bits --------------------------------------------------

    PTE_PRESENT: Final[int] = 1 << 0
    PTE_RW: Final[int] = 1 << 1
    PTE_USER: Final[int] = 1 << 2
    PTE_PWT: Final[int] = 1 << 3
    PTE_PCD: Final[int] = 1 << 4
    PTE_ACCESSED: Final[int] = 1 << 5
    PTE_DIRTY: Final[int] = 1 << 6
    PTE_PAT: Final[int] = 1 << 7
    PTE_GLOBAL: Final[int] = 1 << 8
    PTE_PS: Final[int] = 1 << 7
    PTE_NX: Final[int] = 1 << 63

    PTE_ADDR_MASK: Final[int] = 0x000FFFFFFFFFF000

    # --- index extraction -----------------------------------------------

    @staticmethod
    def pgd_index(va: int, five_level: bool = False) -> int:
        """Return the PGD (PML4/PML5) index for *va*."""
        shift = KPageTable.PGD_SHIFT_5 if five_level \
            else KPageTable.PGD_SHIFT_4
        return (va >> shift) & 0x1FF

    @staticmethod
    def p4d_index(va: int) -> int:
        """Return the P4D index for *va* (5-level paging only)."""
        return (va >> 39) & 0x1FF

    @staticmethod
    def pud_index(va: int) -> int:
        """Return the PUD index for *va*."""
        return (va >> 30) & 0x1FF

    @staticmethod
    def pmd_index(va: int) -> int:
        """Return the PMD index for *va*."""
        return (va >> 21) & 0x1FF

    @staticmethod
    def pte_index(va: int) -> int:
        """Return the PTE index for *va*."""
        return (va >> 12) & 0x1FF

    @staticmethod
    def page_offset(va: int) -> int:
        """Return the 12-bit page offset of *va*."""
        return va & 0xFFF

    # --- split helpers --------------------------------------------------

    @staticmethod
    def split_4(va: int) -> tuple[int, int, int, int, int]:
        """Split *va* for 4-level paging -> ``(pgd, pud, pmd, pte, off)``."""
        return (
            KPageTable.pgd_index(va, False),
            KPageTable.pud_index(va),
            KPageTable.pmd_index(va),
            KPageTable.pte_index(va),
            KPageTable.page_offset(va),
        )

    @staticmethod
    def split_5(va: int) -> tuple[int, int, int, int, int, int]:
        """Split *va* for 5-level paging -> ``(pgd, p4d, pud, pmd, pte, off)``."""
        return (
            KPageTable.pgd_index(va, True),
            KPageTable.p4d_index(va),
            KPageTable.pud_index(va),
            KPageTable.pmd_index(va),
            KPageTable.pte_index(va),
            KPageTable.page_offset(va),
        )

    @staticmethod
    def split(
        va: int, five_level: bool = False,
    ) -> tuple[int, ...]:
        """Split *va* into indices; length 5 (4-level) or 6 (5-level)."""
        if five_level:
            return KPageTable.split_5(va)
        return KPageTable.split_4(va)

    @staticmethod
    def split_2m(va: int) -> tuple[int, int]:
        """Split *va* into ``(pmd_index, 2 MiB offset)``."""
        return ((va >> 21) & 0x1FF, va & 0x1FFFFF)

    @staticmethod
    def split_1g(va: int) -> tuple[int, int]:
        """Split *va* into ``(pud_index, 1 GiB offset)``."""
        return ((va >> 30) & 0x1FF, va & 0x3FFFFFFF)

    @staticmethod
    def huge_2m_base(va: int) -> int:
        """Return the base address of the 2 MiB huge page covering *va*."""
        return va & PTR_MASK & ~0x1FFFFF

    @staticmethod
    def huge_1g_base(va: int) -> int:
        """Return the base address of the 1 GiB huge page covering *va*."""
        return va & PTR_MASK & ~0x3FFFFFFF

    @staticmethod
    def is_2m_aligned(va: int) -> bool:
        """Return ``True`` when *va* is 2 MiB-aligned."""
        return (va & 0x1FFFFF) == 0

    @staticmethod
    def is_1g_aligned(va: int) -> bool:
        """Return ``True`` when *va* is 1 GiB-aligned."""
        return (va & 0x3FFFFFFF) == 0

    # --- canonicalization -----------------------------------------------

    @staticmethod
    def canonicalize(va: int, five_level: bool = False) -> int:
        """Force *va* into canonical form for the selected paging mode."""
        bits = 57 if five_level else 48
        mask = (1 << bits) - 1
        body = va & mask
        if body & (1 << (bits - 1)):
            return body | (PTR_MASK & ~mask)
        return body

    # --- entry addresses ------------------------------------------------

    @staticmethod
    def entry_addr(table_base: int, index: int) -> int:
        """Return the address of entry *index* inside a page-table page."""
        if not 0 <= index < KPageTable.ENTRIES_PER_LEVEL:
            raise ValueError(
                f"index must be in [0, {KPageTable.ENTRIES_PER_LEVEL}), " +
                f"got {index}"
            )
        return (table_base & PTR_MASK & ~PAGE_MASK) + (
            index * KPageTable.ENTRY_SIZE
        )

    @staticmethod
    def pgd_entry_addr(
        pgd_base: int, va: int, five_level: bool = False,
    ) -> int:
        """Return the PGD (PML4/PML5) entry address for *va*."""
        return KPageTable.entry_addr(
            pgd_base, KPageTable.pgd_index(va, five_level)
        )

    @staticmethod
    def p4d_entry_addr(p4d_base: int, va: int) -> int:
        """Return the P4D entry address for *va*."""
        return KPageTable.entry_addr(
            p4d_base, KPageTable.p4d_index(va)
        )

    @staticmethod
    def pud_entry_addr(pud_base: int, va: int) -> int:
        """Return the PUD entry address for *va*."""
        return KPageTable.entry_addr(
            pud_base, KPageTable.pud_index(va)
        )

    @staticmethod
    def pmd_entry_addr(pmd_base: int, va: int) -> int:
        """Return the PMD entry address for *va*."""
        return KPageTable.entry_addr(
            pmd_base, KPageTable.pmd_index(va)
        )

    @staticmethod
    def pte_entry_addr(pte_base: int, va: int) -> int:
        """Return the PTE entry address for *va*."""
        return KPageTable.entry_addr(
            pte_base, KPageTable.pte_index(va)
        )

    @staticmethod
    def next_table(entry: int) -> int:
        """Return the next-level table base address from *entry*."""
        return entry & KPageTable.PTE_ADDR_MASK

    # --- PTE decoding ---------------------------------------------------

    @staticmethod
    def pte_present(pte: int) -> bool:
        """Return ``True`` when the PTE's present bit is set."""
        return bool(pte & KPageTable.PTE_PRESENT)

    @staticmethod
    def pte_writable(pte: int) -> bool:
        """Return ``True`` when the PTE's RW bit is set."""
        return bool(pte & KPageTable.PTE_RW)

    @staticmethod
    def pte_user(pte: int) -> bool:
        """Return ``True`` when the PTE's US bit is set."""
        return bool(pte & KPageTable.PTE_USER)

    @staticmethod
    def pte_accessed(pte: int) -> bool:
        """Return ``True`` when the PTE's A bit is set."""
        return bool(pte & KPageTable.PTE_ACCESSED)

    @staticmethod
    def pte_dirty(pte: int) -> bool:
        """Return ``True`` when the PTE's D bit is set."""
        return bool(pte & KPageTable.PTE_DIRTY)

    @staticmethod
    def pte_global(pte: int) -> bool:
        """Return ``True`` when the PTE's G bit is set."""
        return bool(pte & KPageTable.PTE_GLOBAL)

    @staticmethod
    def pte_nx(pte: int) -> bool:
        """Return ``True`` when the PTE's NX (bit 63) is set."""
        return bool(pte & KPageTable.PTE_NX)

    @staticmethod
    def pte_is_huge(entry: int) -> bool:
        """Return ``True`` when a PMD/PUD entry is a huge-page leaf."""
        return bool(entry & KPageTable.PTE_PS)

    @staticmethod
    def pte_phys(pte: int) -> int:
        """Return the physical base address stored in a 4 KiB PTE."""
        return pte & KPageTable.PTE_ADDR_MASK

    @staticmethod
    def pte_pfn(pte: int) -> int:
        """Return the page frame number stored in a 4 KiB PTE."""
        return KPageTable.pte_phys(pte) >> PAGE_SHIFT

    @staticmethod
    def pte_flags(pte: int) -> list[str]:
        """Return the list of set flag names for *pte*."""
        names = [
            ("P", KPageTable.PTE_PRESENT),
            ("RW", KPageTable.PTE_RW),
            ("US", KPageTable.PTE_USER),
            ("PWT", KPageTable.PTE_PWT),
            ("PCD", KPageTable.PTE_PCD),
            ("A", KPageTable.PTE_ACCESSED),
            ("D", KPageTable.PTE_DIRTY),
            ("PAT", KPageTable.PTE_PAT),
            ("G", KPageTable.PTE_GLOBAL),
            ("PS", KPageTable.PTE_PS),
            ("NX", KPageTable.PTE_NX),
        ]
        return [name for name, bit in names if pte & bit]

    @staticmethod
    def make_pte(phys: int, flags: int = 0) -> int:
        """Build a PTE from a physical base address and flag bits."""
        if phys < 0:
            raise ValueError(f"phys must be >= 0, got {phys}")
        return (phys & KPageTable.PTE_ADDR_MASK) | (flags & 0xFFF) | (
            flags & KPageTable.PTE_NX
        )

    # --- leaf-to-physical construction ---------------------------------

    @staticmethod
    def pte_to_phys(entry: int, va: int) -> int:
        """Reconstruct the physical address of a 4 KiB leaf for *va*."""
        return KPageTable.pte_phys(entry) | (va & 0xFFF)

    @staticmethod
    def pmd_to_phys(entry: int, va: int) -> int:
        """Reconstruct the physical address of a 2 MiB leaf for *va*."""
        base = entry & 0x000FFFFFFFE00000
        return base | (va & 0x1FFFFF)

    @staticmethod
    def pud_to_phys(entry: int, va: int) -> int:
        """Reconstruct the physical address of a 1 GiB leaf for *va*."""
        base = entry & 0x000FFFFFC0000000
        return base | (va & 0x3FFFFFFF)
