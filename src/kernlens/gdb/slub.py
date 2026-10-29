#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""SLUB page, freelist, per-CPU, and partial-list inspection."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast, final

import gdb

from ..core import KAddr
from ..output import Logger, Palette
from ._types import _IntConvertible, _StrLike
from .config import DebugConfig
from .cpu import CpuInfo
from .reader import MemoryReader
from .styler import KernelStyler


@final
class SlubInspector:
    """SLUB page, freelist, per-CPU cache, and partial list inspection.

    ``print_slab`` emits its entire multi-line block through a single
    ``Logger.info`` call: the first line carries the ``[INFO]`` tag,
    the detail lines are printed verbatim so their indentation aligns
    under the header.
    """

    __slots__: tuple[str, ...] = (
        "_config", "_cpu", "_logger", "_offset_of", "_reader", "_styler"
    )

    def __init__(
        self,
        config: DebugConfig,
        reader: MemoryReader,
        styler: KernelStyler,
        logger: Logger,
        cpu: CpuInfo,
        offset_of: Callable[[str, str], int | None] | None = None,
    ) -> None:
        self._config: DebugConfig = config
        self._reader: MemoryReader = reader
        self._styler: KernelStyler = styler
        self._logger: Logger = logger
        self._cpu: CpuInfo = cpu
        #: Resolves ``offsetof(type, member)`` through the same
        #: DWARF/BTF/registry chain the inspectors use.  Optional so the
        #: inspector stays constructible without a kernel inspector (the
        #: adapter tests build it on its own); without it, only the
        #: expressions GDB can evaluate are available.
        self._offset_of: Callable[[str, str], int | None] | None = offset_of

    # --- member access ---------------------------------------------------

    def _offset(self, type_name: str, path: str) -> int | None:
        """Return ``offsetof(type_name, path)``, or ``None``.

        The expression is what a DWARF build answers; BTF and the
        registry are consulted when GDB has no type for *type_name*.
        """
        try:
            value = gdb.parse_and_eval(
                f"(unsigned long)&(({type_name} *)0)->{path}"
            )
            return int(cast(_IntConvertible, value))
        except (gdb.error, TypeError, ValueError, AttributeError):
            pass
        if self._offset_of is None:
            return None
        return self._offset_of(type_name, path)

    def _list_next(self, addr: int) -> int | None:
        """Read ``list_head->next`` at *addr*.

        ``struct list_head`` is two pointers, so the raw word is the
        answer whether or not GDB has the type.
        """
        value = self._reader.u64(f"((struct list_head *){addr:#x})->next")
        if value is not None:
            return value
        return self._reader.u64(f"*(unsigned long *){addr:#x}")

    def _field(
        self,
        addr: int,
        type_name: str,
        field: str,
        *,
        size: int = 8,
        index: int | None = None,
    ) -> int | None:
        """Read one struct member of *addr*, or ``None``.

        The expression form is tried first because it honours whatever
        debug info GDB has loaded.  GDB 15 cannot read BTF, though, so a
        vmlinux stripped of DWARF -- exactly what a distribution debug
        package or the demo image ships -- has no ``struct`` types for
        GDB to evaluate.  The image's BTF still describes the build, so
        the member offset is resolved through the inspector and the word
        is read directly.
        """
        subscript = f"[{index}]" if index is not None else ""
        value = self._reader.u64(
            f"(({type_name} *){addr:#x})->{field}{subscript}"
        )
        if value is not None:
            return value
        offset = self._offset(type_name, field)
        if offset is None:
            return None
        if index is not None:
            # Every indexed member this module reads is an array of
            # pointers (``kmem_cache->node``).
            offset += 8 * index
        if size == 8:
            return self._reader.u64(f"*(unsigned long *){addr + offset:#x}")
        if size == 4:
            return self._reader.u64(f"*(unsigned int *){addr + offset:#x}")
        raise ValueError(f"unsupported member size: {size}")

    # --- struct page translation ----------------------------------------

    def page_bytes(self) -> int:
        """Return ``sizeof(struct page)``; 64 on x86_64 without KASAN."""
        value = self._reader.u64("(unsigned long)sizeof(struct page)")
        return value if value and value > 0 else 64

    def head_to_page(self, head: int) -> int | None:
        """Translate a direct-map object address to its struct page."""
        if not head:
            return None
        page_offset_base = self._reader.read_kvar("page_offset_base")
        vmemmap_base = self._reader.read_kvar("vmemmap_base")
        if page_offset_base is None or vmemmap_base is None:
            return None
        try:
            phys = KAddr.virt_to_phys(head, page_offset_base)
        except ValueError:
            # A non-direct-map address (e.g. vmalloc or a user pointer)
            # cannot be translated by subtracting page_offset_base;
            # doing so would wrap around to a bogus physical address.
            return None
        pfn = (phys & 0xFFFFFFFFFFFFF000) >> 12
        return vmemmap_base + pfn * self.page_bytes()

    def compound_head(self, page: int) -> int:
        """Return the compound head of a kmalloc-1k tail page."""
        if not page:
            return 0
        value = self._field(page, "struct page", "compound_head")
        if value is not None and (value & 1):
            return value & ~1
        return page

    # --- kmem_cache ------------------------------------------------------

    def cache_name(self, cache: int) -> str:
        """Read ``kmem_cache->name``."""
        if not cache:
            return "?"
        name_ptr = self._field(cache, "struct kmem_cache", "name")
        if not name_ptr:
            return "?"
        try:
            raw = gdb.execute(f"x/s {name_ptr:#x}", to_string=True)
        except gdb.error:
            return "?"
        text = cast(_StrLike, raw)
        if '"' in text:
            return text.split('"')[1]
        return "?"

    def cpu_slab_ptr(self, cache: int) -> int | None:
        """Read ``kmem_cache->cpu_slab``, the ``__percpu`` template."""
        if not cache:
            return None
        return self._field(cache, "struct kmem_cache", "cpu_slab")

    def cpu_active_slab(self, cache: int, cpu: int) -> int | None:
        """Read ``kmem_cache_cpu(cpu)->slab``."""
        template = self.cpu_slab_ptr(cache)
        if not template:
            return None
        offset = self._cpu.percpu_off(cpu)
        if offset is None:
            return None
        addr = template + offset
        return self._field(addr, "struct kmem_cache_cpu", "slab")

    def cpu_freelist(self, cache: int, cpu: int) -> int | None:
        """Read ``kmem_cache_cpu(cpu)->freelist``."""
        template = self.cpu_slab_ptr(cache)
        if not template:
            return None
        offset = self._cpu.percpu_off(cpu)
        if offset is None:
            return None
        addr = template + offset
        return self._field(addr, "struct kmem_cache_cpu", "freelist")

    # --- freeptr decoding ---------------------------------------------

    def freeptr_offset(self, cache: int) -> int | None:
        """Read ``kmem_cache->offset``, the freeptr slot offset.

        ``offset == 0`` is valid and common: SLUB stores the freeptr
        at the start of the object unless the cache has a constructor,
        poisoning, red zoning, or RCU type-safe mode.  Values that are
        not pointer-aligned, or that exceed ``kmem_cache->size`` when
        that field is readable, are rejected as garbage.
        """
        if not cache:
            return None
        value = self._field(cache, "struct kmem_cache", "offset", size=4)
        if value is None or value < 0 or value > 0xFFFFFFFF:
            return None
        # The freeptr is a pointer, so its slot is word-aligned.  A
        # non-aligned value cannot be a real slot (and catches garbage
        # reads such as 0xffffffff).
        if value & (8 - 1):
            return None
        # When the cache size is available, reject offsets beyond the
        # whole object.  Do not use an arbitrary 1 MiB cutoff: large
        # caches can legitimately place the freeptr well past 1 MiB.
        size = self._field(cache, "struct kmem_cache", "size", size=4)
        if size is not None and size > 0 and value > size:
            return None
        return value

    def freeptr_random(self, cache: int) -> int | None:
        """Read ``kmem_cache->random``, the freelist XOR key."""
        if not cache:
            return None
        try:
            return self._field(
                cache, "struct kmem_cache", "random", size=4,
            )
        except gdb.error:
            return None

    def decode_freeptr(
        self, raw: int, random: int | None, ptr_addr: int,
    ) -> int:
        """Decode a stored freeptr."""
        if random is None:
            return raw
        swab = int.from_bytes(ptr_addr.to_bytes(8, "little"), "big")
        return (raw ^ random ^ swab) & 0xFFFFFFFFFFFFFFFF

    def freelist_dist(self, cache: int, target: int, top: int) -> int:
        """Return ``target``'s depth in a freelist chain."""
        if not target or not top:
            return -1
        offset = self.freeptr_offset(cache)
        if offset is None:
            return -1
        random = self.freeptr_random(cache)
        cur = top
        depth = 0
        seen: set[int] = set()
        while cur and depth < self._config.freelist_scan_limit:
            if cur == target:
                return depth
            if cur in seen:
                return -1
            seen.add(cur)
            next_addr = cur + offset
            raw = self._reader.u64(f"*(unsigned long *){next_addr:#x}")
            if raw is None:
                return -1
            cur = self.decode_freeptr(raw, random, next_addr)
            depth += 1
        return -1

    # --- partial list ----------------------------------------------------

    def partial_info(
        self, cache: int, node_id: int,
    ) -> tuple[int, int | None, int | None, int | None]:
        """Return ``(count, node_ptr, head_slab, head_freelist)``."""
        if not cache:
            return (0, None, None, None)
        node_ptr = self._field(
            cache, "struct kmem_cache", "node", index=node_id,
        )
        if not node_ptr:
            return (0, None, None, None)
        partial_off = self._offset("struct kmem_cache_node", "partial")
        slab_list_off = self._offset("struct slab", "slab_list")
        if partial_off is None or slab_list_off is None:
            return (0, node_ptr, None, None)
        head_list = node_ptr + partial_off
        next_ptr = self._list_next(head_list)
        if not next_ptr or next_ptr == head_list:
            return (0, node_ptr, None, None)
        count = 0
        first_slab_page: int | None = None
        first_freelist: int | None = None
        cur: int | None = next_ptr
        seen: set[int] = set()
        while cur and cur != head_list and count < 10000:
            if cur in seen:
                break
            seen.add(cur)
            slab_page = cur - slab_list_off
            if count == 0:
                first_slab_page = slab_page
                freelist = self._field(
                    slab_page, "struct slab", "freelist",
                )
                first_freelist = freelist if freelist is not None else 0
            count += 1
            cur = self._list_next(cur)
        return (count, node_ptr, first_slab_page, first_freelist)

    def in_partial(self, cache: int, page: int, node_id: int) -> bool:
        """Whether ``page`` sits on the given node's partial list."""
        if not cache or not page:
            return False
        node_ptr = self._field(
            cache, "struct kmem_cache", "node", index=node_id,
        )
        if not node_ptr:
            return False
        partial_off = self._offset("struct kmem_cache_node", "partial")
        slab_list_off = self._offset("struct slab", "slab_list")
        if partial_off is None or slab_list_off is None:
            return False
        head = node_ptr + partial_off
        visited = 0
        seen: set[int] = set()
        cur = self._list_next(head)
        while cur and cur != head and visited < 10000:
            if cur in seen:
                break
            seen.add(cur)
            if cur - slab_list_off == page:
                return True
            cur = self._list_next(cur)
            visited += 1
        return False

    # --- slab counters ---------------------------------------------------

    def slab_counters(self, page: int) -> tuple[int, int, int] | None:
        """Return ``(inuse, objects, frozen)`` for a ``struct slab``.

        SLUB packs them into one 32-bit word: ``inuse:16`` then
        ``objects:15`` then ``frozen:1``, which is why they cannot be read
        as three separate fields.  The layout is fixed in the definition
        of ``struct slab``, so the masks hold on every release that has
        the type (v5.17 onwards).  ``None`` means the word was unreadable.
        """
        if not page:
            return None
        counters = self._field(page, "struct slab", "counters", size=4)
        if counters is None:
            return None
        return (
            counters & 0xFFFF,
            (counters >> 16) & 0x7FFF,
            (counters >> 31) & 1,
        )

    def slab_state(self, page: int) -> str:
        """Describe a slab as ``frozen`` / ``full`` / ``partial`` / ``empty``.

        Derived from the counters rather than from which list the slab is
        on: a frozen slab is deliberately absent from every list while a
        CPU allocates from it, so list membership alone would report "not
        on any list" for a perfectly normal slab.
        """
        counters = self.slab_counters(page)
        if counters is None:
            return "unknown"
        inuse, objects, frozen = counters
        if frozen:
            return "frozen"
        if objects == 0:
            return "unknown"
        if inuse >= objects:
            return "full"
        if inuse == 0:
            return "empty"
        return "partial"

    def object_index(
        self, head: int, obj: int, cache: int, page_size: int = 64,
    ) -> tuple[int, int] | None:
        """Return ``(index, objects)`` of *obj* inside its slab, or ``None``.

        The slab's base is the direct-map address of its first page and
        the objects sit at ``cache->size`` intervals, so the index is
        ``(obj - base) // size`` -- the slot number, which is what
        "object 7 of 16" means to a reader.
        """
        if not head or not obj or not cache:
            return None
        size = self._field(cache, "struct kmem_cache", "size", size=4)
        if not size:
            return None
        page_offset = self._reader.read_kvar("page_offset_base")
        vmemmap = self._reader.read_kvar("vmemmap_base")
        if not page_offset or not vmemmap:
            return None
        try:
            base = KAddr.page_to_virt(head, page_offset, vmemmap, page_size)
        except ValueError:
            return None
        if obj < base:
            return None
        counters = self.slab_counters(head)
        objects = counters[1] if counters is not None else 0
        return ((obj - base) // size, objects)

    def neighbour_objects(
        self, cache: int, obj: int, head: int, page_size: int = 64,
    ) -> tuple[int | None, int | None]:
        """Return the addresses of the objects before and after *obj*.

        Bounded by the slab: a neighbour outside it is reported as
        ``None`` rather than as an address in the next slab.
        """
        located = self.object_index(head, obj, cache, page_size)
        if located is None:
            return (None, None)
        index, objects = located
        size = self._field(cache, "struct kmem_cache", "size", size=4)
        if not size:
            return (None, None)
        previous = obj - size if index > 0 else None
        following = obj + size if objects and index + 1 < objects else None
        return (previous, following)

    # --- printing --------------------------------------------------------

    def print_slab(self, head: int) -> None:
        """Emit the multi-line slab block for ``head``'s struct page."""
        header = self._styler.style("slab:", Palette.CYAN)

        if not head:
            self._logger.info(
                header + " " + self._styler.style("<head=0>", Palette.RED)
            )
            return
        page = self.head_to_page(head)
        if page is None:
            self._logger.info(
                header + " "
                + self._styler.style("<cannot translate head>", Palette.RED)
            )
            return
        page = self.compound_head(page)
        cache = self._field(page, "struct slab", "slab_cache")
        if not cache:
            self._logger.info(
                header + " " + "page=" + self._styler.addr(page) + " "
                + self._styler.style("not_slab", Palette.RED)
            )
            return

        name = self.cache_name(cache)
        counters = self._field(page, "struct slab", "counters", size=4)
        lines: list[str] = []
        if counters is not None:
            inuse = counters & 0xFFFF
            frozen = (counters >> 31) & 1
            frozen_str = self._styler.style(
                f"frozen={frozen}",
                Palette.RED if frozen else Palette.GREEN,
            )
            lines.append(
                header + " "
                + self._styler.kv_hex("page", page) + " "
                + self._styler.kv(
                    "cache", name, value_color=Palette.BRIGHT_YELLOW_BOLD,
                ) + " "
                + self._styler.kv_int(
                    "inuse", inuse, value_color=Palette.CYAN,
                ) + " "
                + frozen_str
            )
        else:
            lines.append(
                header + " "
                + self._styler.kv_hex("page", page) + " "
                + self._styler.kv(
                    "cache", name, value_color=Palette.BRIGHT_YELLOW_BOLD,
                )
            )

        self._print_freelist(lines, page, cache, head)
        self._print_cpus(lines, page, cache, head)
        self._print_nodes(lines, page, cache, head)
        self._logger.info("\n".join(lines))

    def _print_freelist(
        self, lines: list[str], page: int, cache: int, head: int,
    ) -> None:
        """Append the ``slab->freelist`` line and H's depth to *lines*."""
        slab_freelist = self._field(page, "struct slab", "freelist")
        if slab_freelist is None:
            slab_freelist = 0
        freelist_label = self._styler.style(
            "slab->freelist    ", Palette.CYAN,
        )
        if slab_freelist == 0:
            lines.append(
                self._config.indent_nested + freelist_label + " = "
                + self._styler.style("NULL", Palette.GREEN)
            )
        elif slab_freelist == head:
            lines.append(
                self._config.indent_nested + freelist_label + " = "
                + self._styler.addr(slab_freelist)
                + self._styler.style("(=H)", Palette.BRIGHT_RED_BOLD)
            )
        else:
            lines.append(
                self._config.indent_nested + freelist_label + " = "
                + self._styler.addr(slab_freelist)
                + self._styler.style("(!=H)", Palette.BRIGHT_GREEN)
            )
            dist = self.freelist_dist(cache, head, slab_freelist)
            if dist > 0:
                lines.append(
                    self._config.indent_nested
                    + "                    "
                    + self._styler.depth_marker(dist) + " in "
                    + self._styler.style(
                        "slab->freelist chain", Palette.CYAN,
                    )
                )
            elif dist == -1:
                lines.append(
                    self._config.indent_nested
                    + "                    "
                    + self._styler.style(
                        "H NOT in slab->freelist chain " +
                        "(freed elsewhere?)",
                        Palette.BRIGHT_YELLOW,
                    )
                )

        lines.append(
            self._config.indent_nested
            + self._styler.style("head(H)           ", Palette.CYAN)
            + " = "
            + self._styler.addr(head)
            + "  "
            + self._styler.style("H", Palette.BRIGHT_YELLOW_BOLD)
        )

    def _print_cpus(
        self, lines: list[str], page: int, cache: int, head: int,
    ) -> None:
        """Append one line per possible CPU to *lines*."""
        for cpu in range(max(self._cpu.nr_cpus(), 0)):
            active = self.cpu_active_slab(cache, cpu)
            freelist = self.cpu_freelist(cache, cpu)
            active_val = active if active is not None else 0
            freelist_val = freelist if freelist is not None else 0
            slab_str = (
                self._styler.addr(active_val) if active_val
                else self._styler.style("NULL", Palette.GREEN)
            )
            freelist_str = self._styler.fl_tag(freelist_val, head)
            cpu_label = self._styler.style(f"cpu{cpu}", Palette.CYAN)
            mark = (
                self._styler.style(" (active)", Palette.BRIGHT_YELLOW_BOLD)
                if active_val == page else ""
            )
            lines.append(
                self._config.indent_nested + cpu_label + "[slab="
                + slab_str + ", "
                + self._styler.style("freelist", Palette.CYAN)
                + "=" + freelist_str + "]" + mark
            )

    def _print_nodes(
        self, lines: list[str], page: int, cache: int, head: int,
    ) -> None:
        """Append one line per node with a non-empty partial list."""
        for node in range(self._cpu.nr_nodes()):
            count, node_ptr, head_slab, head_freelist = self.partial_info(cache, node)
            if not node_ptr:
                if node == 0:
                    lines.append(
                        self._config.indent_nested
                        + self._styler.style(f"node{node}", Palette.CYAN)
                        + "["
                        + self._styler.style("absent", Palette.RED)
                        + "]"
                    )
                continue
            in_list = self.in_partial(cache, page, node)
            if count == 0 and not in_list and node != 0:
                continue
            state = (
                self._styler.style(
                    "this page in list", Palette.BRIGHT_YELLOW_BOLD,
                )
                if in_list
                else self._styler.style(
                    "this page NOT in list", Palette.DIM,
                )
            )
            node_label = self._styler.style(f"node{node}", Palette.CYAN)
            if count > 0 and head_slab is not None:
                head_freelist_val = head_freelist if head_freelist is not None else 0
                freelist_str = self._styler.fl_tag(head_freelist_val, head)
                lines.append(
                    self._config.indent_nested + node_label + "["
                    + self._styler.style("partial", Palette.CYAN) + "="
                    + self._styler.style(str(count), Palette.CYAN) + " slabs, "
                    + self._styler.style("head_slab", Palette.CYAN)
                    + "=" + self._styler.addr(head_slab) + ", "
                    + self._styler.style("head_freelist", Palette.CYAN)
                    + "=" + freelist_str + ", "
                    + state + "]"
                )
                if (
                    head_slab == page
                    and head_freelist_val
                    and head_freelist_val != head
                ):
                    dist = self.freelist_dist(cache, head, head_freelist_val)
                    if dist > 0:
                        lines.append(
                            self._config.indent_nested
                            + "                    "
                            + self._styler.depth_marker(dist) + " in "
                            + self._styler.style(
                                "head_freelist chain", Palette.CYAN,
                            )
                        )
            else:
                lines.append(
                    self._config.indent_nested + node_label + "["
                    + self._styler.style("partial", Palette.CYAN)
                    + "=0 slabs, " + state + "]"
                )


__all__ = ["SlubInspector"]
