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


@dataclass(frozen=True, slots=True)
class ZoneSpan:
    """One ``struct zone``, reduced to what an address lookup needs."""

    name: str
    node: int
    #: Kernel-virtual address of the ``struct zone``.
    address: int
    start_pfn: int
    spanned_pages: int
    present_pages: int

    @property
    def end_pfn(self) -> int:
        """One past the last pfn this zone spans."""
        return self.start_pfn + self.spanned_pages


@dataclass(frozen=True, slots=True)
class BlockLocation:
    """Where an address sits inside the buddy allocator's blocks.

    ``order`` is ``None`` when the page is not on a free list, in which
    case the block size is unknown and every derived field is ``None``
    rather than a guess -- the kernel only records the order while a
    block is free (``set_buddy_order`` in ``__free_one_page``).
    """

    phys: int
    pfn: int
    page: int
    zone: ZoneSpan | None
    #: ``True`` when the pfn is inside ``spanned_pages`` but outside
    #: ``present_pages`` -- an unpopulated hole in the zone.
    hole: bool
    order: int | None
    #: ``1 << order``, the block's length in pages.
    size_pages: int | None
    #: pfn of the block's first page.
    base_pfn: int | None
    #: ``pfn - base_pfn``: which page of the block this is.
    position: int | None
    #: The block head's ``struct page`` address.
    block_page: int | None
    #: The block head's physical address.
    block_phys: int | None
    #: The block head's direct-map address.
    block_virt: int | None
    #: Whether *this* pfn is itself the head of a block of ``order``.
    is_block_head: bool

    @property
    def managed(self) -> bool:
        """Whether any zone claims this pfn."""
        return self.zone is not None

    @property
    def free(self) -> bool:
        """Whether the page is on a buddy free list."""
        return self.order is not None


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

    # --- address -> zone / block ----------------------------------------

    def zone_spans(self) -> tuple[ZoneSpan, ...]:
        """Return every populated ``struct zone``, in node/zone order.

        Read from ``node_data[].node_zones[]``: the same traversal
        :meth:`buddy_zones` uses, so a zone an address can belong to is
        exactly a zone whose free lists that method walks.
        """
        node_data = self._reader.kvar_addr("node_data")
        if not node_data:
            return ()
        numa = self.config_contains("NUMA")
        zone_size = self._layout_sizeof("struct zone")
        if not zone_size:
            return ()
        offsets = {
            name: self._layout_offset("struct zone", name)
            for name in ("name", "zone_start_pfn", "spanned_pages",
                         "present_pages")
        }
        if offsets["zone_start_pfn"] is None or offsets["spanned_pages"] is None:
            return ()
        nzones = self._nzones()
        names = self._zone_names()
        spans: list[ZoneSpan] = []
        for node_index in range(self.nr_nodes()):
            pgdat = (
                self._read_u64(node_data + node_index * 8)
                if numa else node_data
            )
            if not pgdat:
                continue
            for zone_index in range(nzones):
                address = pgdat + zone_index * zone_size
                label = self._zone_label(address, offsets["name"], names,
                                         zone_index)
                if label is None:
                    continue
                start = self._read_u64(
                    address + offsets["zone_start_pfn"]
                )
                spanned = self._read_u64(
                    address + offsets["spanned_pages"]
                )
                present = (
                    self._read_u64(address + offsets["present_pages"])
                    if offsets["present_pages"] is not None else None
                )
                if start is None or spanned is None or not spanned:
                    continue
                spans.append(
                    ZoneSpan(
                        name=label,
                        node=node_index,
                        address=address,
                        start_pfn=start,
                        spanned_pages=spanned,
                        present_pages=(
                            present if present is not None else spanned
                        ),
                    )
                )
        return tuple(spans)

    def _zone_label(
        self, address: int, name_off: int | None,
        names: tuple[str, ...], index: int,
    ) -> str | None:
        """Return a zone's name, or ``None`` when the slot is empty.

        The name pointer is authoritative (an unpopulated
        ``node_zones[]`` slot has none); the ``zone_names`` table is only
        used when the field itself is unavailable.
        """
        if name_off is not None:
            pointer = self._read_u64(address + name_off)
            if not pointer:
                return None
            text = self._cstring(pointer)
            if text:
                return text
            return None
        return names[index] if index < len(names) else None

    def zone_of_pfn(
        self, pfn: int, spans: tuple[ZoneSpan, ...] | None = None,
    ) -> tuple[ZoneSpan | None, bool]:
        """Return ``(zone, is_hole)`` for *pfn*.

        ``(None, False)`` means no zone spans the pfn -- memory the
        allocator does not manage at all.  ``(zone, True)`` means the
        pfn is inside the zone's ``spanned_pages`` but outside its
        ``present_pages``, i.e. a hole in the physical map.
        """
        for span in spans if spans is not None else self.zone_spans():
            if span.start_pfn <= pfn < span.end_pfn:
                hole = not (
                    span.start_pfn <= pfn
                    < span.start_pfn + span.present_pages
                )
                return span, hole
        return None, False

    def block_of_pfn(
        self,
        pfn: int,
        phys: int,
        *,
        spans: tuple[ZoneSpan, ...] | None = None,
        page_size: int = 64,
    ) -> BlockLocation:
        """Locate *pfn* in the buddy allocator's block structure.

        The search runs from the largest order down, because only one
        order can have both an aligned base and a head whose ``private``
        equals that order: a smaller block can never sit at the head of
        a larger one.  Trying the largest first therefore cannot report
        a sub-block of a real free block as the answer.

        A pfn that is not free still gets its zone and page, but no
        order/position -- see :class:`BlockLocation`.
        """
        vmemmap = self._vmemmap_base()
        page_offset = self._page_offset_base()
        page = (vmemmap + (pfn * page_size)) & MASK64
        span, hole = self.zone_of_pfn(pfn, spans)
        base_fields = {
            "phys": phys, "pfn": pfn, "page": page, "zone": span,
            "hole": hole,
        }
        for order in range(self._norders() - 1, -1, -1):
            size_pages = 1 << order
            if pfn & (size_pages - 1):
                continue
            head = (vmemmap + ((pfn) * page_size)) & MASK64
            if self.buddy_order(head) != order:
                continue
            head_phys = pfn << 12
            try:
                head_virt = KAddr.page_to_virt(
                    head, page_offset, vmemmap, page_size,
                )
            except ValueError:
                head_virt = None
            return BlockLocation(
                **base_fields,
                order=order,
                size_pages=size_pages,
                base_pfn=pfn,
                position=0,
                block_page=head,
                block_phys=head_phys,
                block_virt=head_virt,
                is_block_head=True,
            )
        # Not a head: look for a larger free block that contains it.
        for order in range(self._norders() - 1, 0, -1):
            size_pages = 1 << order
            base = pfn & ~(size_pages - 1)
            head = (vmemmap + (base * page_size)) & MASK64
            if self.buddy_order(head) != order:
                continue
            head_phys = base << 12
            try:
                head_virt = KAddr.page_to_virt(
                    head, page_offset, vmemmap, page_size,
                )
            except ValueError:
                head_virt = None
            return BlockLocation(
                **base_fields,
                order=order,
                size_pages=size_pages,
                base_pfn=base,
                position=pfn - base,
                block_page=head,
                block_phys=head_phys,
                block_virt=head_virt,
                is_block_head=False,
            )
        return BlockLocation(
            **base_fields,
            order=None, size_pages=None, base_pfn=None, position=None,
            block_page=None, block_phys=None, block_virt=None,
            is_block_head=False,
        )

    def block_range(
        self, location: BlockLocation, page_size: int = 64,
    ) -> tuple[int, int, int, int] | None:
        """Return ``(first_pfn, last_pfn, first_phys, last_phys)``.

        Inclusive on both ends, so it can be printed as a range.  ``None``
        when the page is not inside a known free block.
        """
        del page_size
        if location.base_pfn is None or location.size_pages is None:
            return None
        first = location.base_pfn
        last = first + location.size_pages - 1
        return first, last, first << 12, (last << 12) | 0xFFF

    def buddy_pfn(self, location: BlockLocation) -> tuple[int, int] | None:
        """Return the ``(pfn, phys)`` of the block's buddy, or ``None``.

        ``buddy = base ^ size`` is exact while the block is the only unit
        at its order, which is the case for anything still on a free
        list.  The caller must still check the buddy's own state.
        """
        if location.base_pfn is None or location.size_pages is None:
            return None
        pfn = location.base_pfn ^ location.size_pages
        return pfn, pfn << 12

    # --- free_area counters and one list's contents ----------------------

    def free_area_counts(
        self,
        *,
        zone: str | None = None,
        order: int | None = None,
        mtype: str | None = None,
        node: int | None = None,
        spans: tuple[ZoneSpan, ...] | None = None,
    ) -> tuple[tuple[str, int, int, int], ...]:
        """Return ``(zone, node, order, nr_free)`` for each non-empty order.

        ``nr_free`` is **one counter per order**, covering every
        migratetype in that ``free_area`` -- not one per migratetype.
        The kernel keeps it that way (``area->nr_free++`` in
        ``__free_one_page``, printed per order by ``/proc/buddyinfo``),
        and the per-type breakdown only exists as "is this list empty?",
        which costs a walk.  Reading a per-type counter therefore cannot
        work: the bytes past the counter are the next ``free_area``'s
        ``free_list[]`` pointers.
        """
        node_data = self._reader.kvar_addr("node_data")
        if not node_data:
            return ()
        numa = self.config_contains("NUMA")
        zone_size = self._layout_sizeof("struct zone")
        free_area_off = self._layout_offset("struct zone", "free_area")
        nr_free_off = self._layout_offset("struct free_area", "nr_free")
        area_size = self._layout_sizeof("struct free_area")
        if (
            not zone_size or free_area_off is None
            or nr_free_off is None or not area_size
        ):
            return ()
        norders = self._norders()
        resolved = spans if spans is not None else self.zone_spans()
        by_address = {span.address: span for span in resolved}
        wanted = mtype.lower() if mtype is not None else None
        rows: list[tuple[str, int, int, int]] = []
        for node_index in range(self.nr_nodes()):
            if node is not None and node_index != node:
                continue
            pgdat = (
                self._read_u64(node_data + node_index * 8)
                if numa else node_data
            )
            if not pgdat:
                continue
            for zone_index in range(self._nzones()):
                address = pgdat + zone_index * zone_size
                span = by_address.get(address)
                label = span.name if span is not None else None
                if label is None:
                    continue
                if zone is not None and zone.lower() != label.lower():
                    continue
                for zone_order in range(norders):
                    if order is not None and order != zone_order:
                        continue
                    area = (
                        address + free_area_off + zone_order * area_size
                    )
                    if wanted is not None and not self._mtype_nonempty(
                        area, wanted,
                    ):
                        continue
                    count = self._read_u64(area + nr_free_off)
                    if count:
                        rows.append(
                            (label, node_index, zone_order, count)
                        )
        return tuple(rows)

    def _mtype_nonempty(self, area: int, mtype: str) -> bool:
        """Whether ``free_area[*].free_list[mtype]`` holds any block."""
        index = next(
            (
                i for i, name in enumerate(self._migratetype_names())
                if name.lower() == mtype
            ),
            None,
        )
        if index is None:
            return False
        head = area + index * 0x10
        first = self._read_u64(head)
        return bool(first) and first != head

    def freelist_blocks(
        self,
        zone_name: str,
        order: int,
        mtype: str,
        *,
        node: int = 0,
        limit: int = 64,
        page_size: int = 64,
    ) -> tuple[BuddyPage, ...]:
        """Return the blocks on one ``free_area[order][mtype]`` list.

        Yields them in list order, which is the order the allocator would
        hand them out, so ``index`` doubles as the list position.
        """
        node_data = self._reader.kvar_addr("node_data")
        if not node_data:
            return ()
        numa = self.config_contains("NUMA")
        pgdat = (
            self._read_u64(node_data + node * 8) if numa else node_data
        )
        if not pgdat:
            return ()
        zone_size = self._layout_sizeof("struct zone")
        free_area_off = self._layout_offset("struct zone", "free_area")
        area_size = self._layout_sizeof("struct free_area")
        lru_offset = self._layout_offset("struct page", "lru") or 0x8
        mtypes = self._migratetype_names()
        if not zone_size or free_area_off is None or not area_size:
            return ()
        names = self._zone_names()
        zone_index = next(
            (
                index for index, name in enumerate(names)
                if name.lower() == zone_name.lower()
            ),
            None,
        )
        if zone_index is None:
            return ()
        mtype_index = next(
            (
                index for index, name in enumerate(mtypes)
                if name.lower() == mtype.lower()
            ),
            None,
        )
        if mtype_index is None:
            return ()
        list_head = (
            pgdat + zone_index * zone_size + free_area_off
            + order * area_size + mtype_index * 0x10
        )
        vmemmap = self._vmemmap_base()
        page_offset = self._page_offset_base()
        found: list[BuddyPage] = []
        seen: set[int] = set()
        current = self._read_u64(list_head)
        while (
            current and current != list_head and len(found) < limit
        ):
            page = (current - lru_offset) & MASK64
            if page in seen:
                break
            seen.add(page)
            try:
                phys = KAddr.page_to_phys(page, vmemmap, page_size)
                virt = KAddr.page_to_virt(
                    page, page_offset, vmemmap, page_size,
                )
            except ValueError:
                break
            found.append(
                BuddyPage(index=len(found), page=page, phys=phys, virt=virt)
            )
            current = self._read_u64(current)
        return tuple(found)

    def freelist_count(
        self,
        zone_name: str,
        order: int,
        mtype: str,
        *,
        node: int = 0,
        limit: int = 4096,
        page_size: int = 64,
    ) -> int:
        """How many blocks one ``free_area[order][mtype]`` list holds.

        A walk, because the kernel keeps only the per-order total.  The
        result is used to decide whether a list is worth expanding, so it
        is capped by *limit* to keep a corrupt list from running away.
        """
        return len(
            self.freelist_blocks(
                zone_name, order, mtype, node=node, limit=limit,
                page_size=page_size,
            )
        )


__all__ = [
    "BUDDY_MAX_ORDER",
    "BUDDY_MAX_ORDER_LIMIT",
    "BUDDY_MIN_MIGRATETYPES",
    "BUDDY_PAGES_LIMIT",
    "CMA_MIGRATETYPE",
    "ISOLATE_MIGRATETYPE",
    "MIGRATE_TYPES",
    "ZONE_NAMES",
    "BlockLocation",
    "BuddyInspector",
    "BuddyPage",
    "ZoneSpan",
]