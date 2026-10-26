#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""The buddy allocator: zone free lists and node/zone metadata.

Traverses ``node_data[].node_zones[].free_area[].free_list[]``.  Page
0's ``lru`` links are used to recover ``offsetof(page, lru)`` from the
``node_data[].node_zones[].node_pages`` back-pointer, so nothing is
hard-coded beyond the x86_64 ``struct zone`` size.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.addr import KAddr
from ._base import MASK64, InspectorBase

#: ``enum migratetype`` names, extended by CONFIG_CMA / CONFIG_MEMORY_ISOLATION.
MIGRATE_TYPES = ("Unmovable", "Movable", "Reclaimable", "HighAtomic")

#: Zone names the kernel uses, in ascending order.
ZONE_NAMES = ("DMA", "DMA32", "Normal", "HighMem", "Movable", "Device")

#: Default ``MAX_ORDER`` (``free_area`` entries) on x86_64.
BUDDY_MAX_ORDER = 11

#: Bounds on a buddy freelist walk.
BUDDY_PAGES_LIMIT = 0x1000


@dataclass(frozen=True, slots=True)
class BuddyPage:
    """One ``struct page`` on a buddy/PCP free list."""

    index: int
    page: int
    phys: int
    virt: int


class BuddyInspector(InspectorBase):
    """Walk the buddy free lists and decode zone/node metadata."""

    __slots__: tuple[str, ...] = ()

    def buddy_zones(
        self,
        *,
        zone: str | None = None,
        order: int | None = None,
        mtype: str | None = None,
        page_size: int = 64,
        node: int | None = None,
    ) -> tuple[BuddyPage, ...]:
        """Return pages on the buddy free lists that match the filters.

        Traverses ``node_data[].node_zones[].free_area[].free_list[]``.
        Page 0's ``lru`` links are used to recover ``offsetof(page, lru)``
        from the ``node_data[].node_zones[].node_pages`` back-pointer.
        """
        node_data = self._reader.kvar_addr("node_data")
        if not node_data:
            return ()
        numa = self.config_contains("NUMA")
        # ``node_data`` is an array of pgdat pointers (NUMA) or a single
        # inline pgdat; index the array directly, never dereference the
        # already-resolved first pgdat again.
        first_pgdat = self._read_u64(node_data) if numa else node_data
        if not first_pgdat:
            return ()
        # ``offsetof(struct page, lru)`` is layout-dependent; prefer the
        # DWARF value and fall back to the page-0 back-pointer trick.
        lru_offset = self._layout_offset("struct page", "lru")
        if lru_offset is None:
            zero_page = self._read_u64(first_pgdat)
            if not zero_page:
                return ()
            lru_offset = self._find_lru_offset(zero_page, page_size)
        if lru_offset is None:
            return ()

        nmtypes = self._nmtypes()
        nzones = self._nzones()
        names = self._zone_names()
        mtypes = self._migratetype_names()
        zone_size = self._layout_sizeof("struct zone")
        free_area_off = self._layout_offset("struct zone", "free_area")
        if free_area_off is None or not zone_size:
            return ()
        found: list[BuddyPage] = []
        for node_index in range(self.nr_nodes()):
            if node is not None and node_index != node:
                continue
            pgdat = (
                self._read_u64(node_data + node_index * 8)
                if numa else node_data
            )
            if not pgdat:
                continue
            for zone_index in range(nzones):
                name = (
                    names[zone_index]
                    if zone_index < len(names)
                    else f"zone{zone_index}"
                )
                if zone is not None and zone != name:
                    continue
                zone_addr = pgdat + zone_index * zone_size
                for zone_order in range(BUDDY_MAX_ORDER):
                    if order is not None and order != zone_order:
                        continue
                    area = (
                        zone_addr + free_area_off
                        + zone_order * (nmtypes * 0x10 + 8)
                    )
                    for mtype_index in range(nmtypes):
                        if (
                            mtype is not None
                            and mtype.lower() != mtypes[mtype_index].lower()
                        ):
                            continue
                        list_head = area + mtype_index * 0x10
                        self._walk_buddy_pages(
                            list_head, lru_offset, page_size, found,
                        )
        return tuple(found)

    def _walk_buddy_pages(
        self,
        list_head: int,
        lru_offset: int,
        page_size: int,
        out: list[BuddyPage],
    ) -> None:
        """Follow a doubly linked ``struct page.lru`` free list."""
        first = self._read_u64(list_head)
        if not first or first == list_head:
            return
        seen: set[int] = set()
        current = first
        while current and current != list_head and len(out) < BUDDY_PAGES_LIMIT:
            page = (current - lru_offset) & MASK64
            if page in seen:
                break
            seen.add(page)
            try:
                phys = KAddr.page_to_phys(page, self._vmemmap_base(), page_size)
                virt = KAddr.page_to_virt(
                    page, self._page_offset_base(), self._vmemmap_base(),
                    page_size,
                )
            except ValueError:
                break
            out.append(
                BuddyPage(index=len(out), page=page, phys=phys, virt=virt)
            )
            next_link = self._read_u64(current)
            if not next_link:
                break
            current = next_link

    def _find_lru_offset(self, zero_page: int, page_size: int) -> int | None:
        """Return ``offsetof(struct page, lru)`` from page 0's links."""
        vmemmap = self._vmemmap_base()
        for index in range(64):
            value = self._read_u64(zero_page + index * 8)
            if not value:
                continue
            page = (value - index * 8) & MASK64
            try:
                phys = KAddr.page_to_phys(page, vmemmap, page_size)
            except ValueError:
                continue
            if phys == 0:
                return index * 8
        return None

    # --- zone / node metadata -------------------------------------------

    def _nmtypes(self) -> int:
        """Return the ``MIGRATE_TYPES`` count."""
        return len(self._migratetype_names())

    def _migratetype_names(self) -> tuple[str, ...]:
        """Return the ``enum migratetype`` names for the current config."""
        names = list(MIGRATE_TYPES)
        if self.config_contains("CMA"):
            names.append("CMA")
        if self.config_contains("MEMORY_ISOLATION"):
            names.append("Isolate")
        return tuple(names)

    def _nzones(self) -> int:
        """Return the number of zones from ``zone_names``, or a fallback."""
        zone_names = self._reader.kvar_addr("zone_names")
        if not zone_names:
            return 4
        for index in range(len(ZONE_NAMES) + 1):
            ptr = self._read_u64(zone_names + index * 8)
            text = self._cstring(ptr) if ptr else None
            if text is None or text not in ZONE_NAMES:
                return index or 4
        return len(ZONE_NAMES)

    def _zone_names(self) -> tuple[str, ...]:
        """Return the zone names in order."""
        return ZONE_NAMES[: self._nzones()]

    def nr_nodes(self) -> int:
        """Return the number of NUMA nodes (1 when CONFIG_NUMA is off)."""
        if not self.config_contains("NUMA"):
            return 1
        value = self._reader.read_kvar("nr_online_nodes", "int")
        if value and 0 < value <= 64:
            return value
        return 1


__all__ = [
    "BUDDY_MAX_ORDER",
    "BUDDY_PAGES_LIMIT",
    "MIGRATE_TYPES",
    "ZONE_NAMES",
    "BuddyInspector",
    "BuddyPage",
]