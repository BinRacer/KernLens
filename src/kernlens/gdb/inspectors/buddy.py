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

Every count that the kernel derives on its own is read from the kernel,
not assumed:

* the migratetype *count* comes from ``enum migratetype`` /
  ``migratetype_names`` (``CONFIG_CMA`` and ``CONFIG_MEMORY_ISOLATION``
  each add one);
* the number of ``free_area`` entries comes from the array's own size
  (``MAX_ORDER``, movable by ``CONFIG_ARCH_FORCE_MAX_ORDER``);
* the zone count comes from how many ``node_zones[]`` entries actually
  carry a name.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.addr import KAddr
from ._base import MASK64, InspectorBase

#: ``enum migratetype`` names, in ``enum`` order, before the two entries
#: that a ``CONFIG_*`` knob can add.  Used only when the kernel's own
#: names cannot be read.
MIGRATE_TYPES = ("Unmovable", "Movable", "Reclaimable", "HighAtomic")

#: Names of the optional trailing entries of ``enum migratetype``.
CMA_MIGRATETYPE = "CMA"
ISOLATE_MIGRATETYPE = "Isolate"

#: Zone names the kernel uses, in ascending order.
ZONE_NAMES = ("DMA", "DMA32", "Normal", "HighMem", "Movable", "Device")

#: ``MAX_ORDER`` fallback, taken from x86_64's usual ``11``.
BUDDY_MAX_ORDER = 11

#: Upper bound on ``NR_PAGE_ORDERS`` a walk will accept, so a corrupt
#: array size cannot drive an unbounded loop.
BUDDY_MAX_ORDER_LIMIT = 64

#: Default ``MIGRATE_TYPES`` when the enum cannot be read.
BUDDY_MIN_MIGRATETYPES = 4

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
        norders = self._norders()
        # ``migratetype_names`` is ``const char * const[N]``, so the
        # entries are pointers, not C strings.
        free_area_size = nmtypes * 0x10 + 8
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
                for zone_order in range(norders):
                    if order is not None and order != zone_order:
                        continue
                    area = (
                        zone_addr + free_area_off + zone_order * free_area_size
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

    def _norders(self) -> int:
        """Return ``NR_PAGE_ORDERS``, the number of ``free_area`` entries.

        Taken from the array's own size, because ``CONFIG_ARCH_FORCE_MAX_ORDER``
        can move ``MAX_ORDER`` away from the usual 11 and the count is not
        a symbol or an enumerator.  Falls back to :data:`BUDDY_MAX_ORDER`
        when the ``struct zone`` layout is unavailable, and refuses an
        implausible size so a bad read cannot drive an unbounded loop.
        """
        length = self._array_length("struct zone", "free_area")
        if length is not None and 1 <= length <= BUDDY_MAX_ORDER_LIMIT:
            return length
        return BUDDY_MAX_ORDER

    def _nmtypes(self) -> int:
        """Return ``MIGRATE_TYPES``, the number of free-area lists."""
        return len(self._migratetype_names())

    def _migratetype_names(self) -> tuple[str, ...]:
        """Return the ``enum migratetype`` names for this kernel.

        Read from ``migratetype_names``, the very array
        ``show_migration_types()`` prints, because it is both exact and
        the *order* is load-bearing: the count is the stride of
        ``free_area``, so an entry guessed wrong misplaces every list
        after it.  The ``CONFIG_*`` knobs are only the last resort, for
        an image whose symbols are stripped.
        """
        names = self._migratetype_table()
        if names:
            return names
        fallback = list(MIGRATE_TYPES)
        if self.config_contains("CMA"):
            fallback.append(CMA_MIGRATETYPE)
        if self.config_contains("MEMORY_ISOLATION"):
            fallback.append(ISOLATE_MIGRATETYPE)
        return tuple(fallback)

    def _migratetype_table(self) -> tuple[str, ...]:
        """Read ``migratetype_names`` from the image, or ``()``.

        The array is ``const char * const[MIGRATE_TYPES]``, so each entry
        is a pointer to a literal; they are read in order until one stops
        resolving to a string.  This is the authoritative source because
        it is the very table ``show_migration_types()`` uses.
        """
        address = self._reader.kvar_addr("migratetype_names")
        if not address:
            return ()
        names: list[str] = []
        for index in range(len(ZONE_NAMES) + BUDDY_MAX_ORDER_LIMIT):
            pointer = self._read_u64(address + index * 8)
            if not pointer:
                break
            text = self._cstring(pointer)
            if not text:
                break
            names.append(text)
        return tuple(names)

    def _migratetype_from_enum(self) -> tuple[str, ...]:
        """Build a name list from ``enum migratetype``'s members, or ``()``.

        Not on the main path: the members are ``MIGRATE_*`` identifiers,
        not the display names, and two of them (``MIGRATE_HIGHATOMIC``
        and ``MIGRATE_PCPTYPES``) share a value, so deriving the labels
        means guessing which alias names the list.  It is offered only as
        a diagnostic for a kernel whose ``migratetype_names`` is missing.
        """
        members = self.enum_members("migratetype")
        if not members:
            return ()
        names: list[str] = []
        seen: set[int] = set()
        for member, value in sorted(members.items(), key=lambda item: item[1]):
            if not member.startswith("MIGRATE_") or member == "MIGRATE_TYPES":
                continue
            if value in seen:
                continue
            seen.add(value)
            label = member.removeprefix("MIGRATE_").capitalize()
            if label == "Pcptypes":
                # The alias that shares ``MIGRATE_HIGHATOMIC``'s value;
                # the other spelling is the one the allocator prints.
                continue
            names.append(label)
        return tuple(names) if names else ()

    def _nzones(self) -> int:
        """Return how many ``node_zones[]`` entries a pgdat has.

        Counted by reading each entry's ``name`` pointer: the array is
        ``MAX_NR_ZONES`` long (6 on x86_64) but only the leading entries
        are populated, and the names are *not* a dense prefix of any
        fixed list -- a 6.1 boot has ``DMA``, ``DMA32``, ``Normal`` and
        ``Movable``, skipping ``HighMem`` -- so the count is taken from
        the kernel rather than from a name table.
        """
        node_data = self._reader.kvar_addr("node_data")
        if not node_data:
            return BUDDY_MIN_MIGRATETYPES
        numa = self.config_contains("NUMA")
        pgdat = self._read_u64(node_data) if numa else node_data
        if not pgdat:
            return BUDDY_MIN_MIGRATETYPES
        zone_size = self._layout_sizeof("struct zone")
        name_off = self._layout_offset("struct zone", "name")
        if not zone_size or name_off is None:
            return BUDDY_MIN_MIGRATETYPES
        count = 0
        for index in range(len(ZONE_NAMES)):
            pointer = self._read_u64(pgdat + index * zone_size + name_off)
            if not pointer or not self._cstring(pointer):
                break
            count += 1
        return count or BUDDY_MIN_MIGRATETYPES

    def _zone_names(self) -> tuple[str, ...]:
        """Return the zone names in ``node_zones[]`` order.

        ``zone_names`` is the array the kernel indexes by ``zone_type``
        and prints in ``/proc/zoneinfo``, so it is preferred: it gives
        the display spelling (``Normal``, not the ``ZONE_NORMAL``
        identifier) and, like ``enum zone_type``, is ``CONFIG_*``-
        conditioned in the same order.  The enum names are the fallback
        for an image whose symbols are stripped.
        """
        names = self._zone_names_from_table()
        if names:
            return names
        names = self._zone_names_from_enum()
        return names or ZONE_NAMES

    def _zone_names_from_table(self) -> tuple[str, ...]:
        """Read ``zone_names`` from the image, or ``()``.

        Each entry is a pointer to a string literal; they are read until
        one stops resolving, which is where the populated prefix of the
        array ends.
        """
        address = self._reader.kvar_addr("zone_names")
        if not address:
            return ()
        names: list[str] = []
        for index in range(len(ZONE_NAMES)):
            pointer = self._read_u64(address + index * 8)
            if not pointer:
                break
            text = self._cstring(pointer)
            if not text:
                break
            names.append(text)
        return tuple(names)

    def _zone_names_from_enum(self) -> tuple[str, ...]:
        """Return zone names from ``enum zone_type``, or ``()``.

        Sorted by enum *value*, which is the index into ``node_zones[]``.
        The enum itself is ``CONFIG_*``-conditioned (``ZONE_DMA32``,
        ``ZONE_HIGHMEM`` and ``ZONE_DEVICE`` each appear only with their
        option), so ordering by the kernel's own values is what keeps
        the labels attached to the right zone.
        """
        members = self.enum_members("zone_type")
        if not members:
            return ()
        ordered = sorted(
            (value, name)
            for name, value in members.items()
            if name.startswith("ZONE_")
        )
        names: list[str] = []
        seen: set[int] = set()
        for value, member in ordered:
            if value in seen:
                continue
            seen.add(value)
            names.append(member.removeprefix("ZONE_"))
        return tuple(names)

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
    "BUDDY_MAX_ORDER_LIMIT",
    "BUDDY_MIN_MIGRATETYPES",
    "BUDDY_PAGES_LIMIT",
    "CMA_MIGRATETYPE",
    "ISOLATE_MIGRATETYPE",
    "MIGRATE_TYPES",
    "ZONE_NAMES",
    "BuddyInspector",
    "BuddyPage",
]