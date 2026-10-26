#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""The SLUB allocator: the global ``slab_caches`` list and object lookup.

Caches are walked through ``slab_caches``; each ``struct kmem_cache`` is
decoded with x86_64 field offsets.  :meth:`slab_object` maps an object
address back to its cache via the ``struct slab``/``struct page`` head.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.addr import KAddr
from ._base import InspectorBase

#: ``open(O_CREAT) | O_EXCL`` flag used for recoverability probing.
OO_SHIFT = 16
OO_MASK = (1 << OO_SHIFT) - 1

#: ``kmem_cache->flags`` bits worth naming.
SLAB_FLAGS: tuple[tuple[str, int], ...] = (
    ("SLAB_DEBUG_FREE", 0x00000100),
    ("SLAB_RED_ZONE", 0x00000400),
    ("SLAB_POISON", 0x00000800),
    ("SLAB_HWCACHE_ALIGN", 0x00002000),
    ("SLAB_CACHE_DMA", 0x00004000),
    ("SLAB_STORE_USER", 0x00010000),
    ("SLAB_RECLAIM_ACCOUNT", 0x00020000),
    ("SLAB_PANIC", 0x00040000),
    ("SLAB_DESTROY_BY_RCU", 0x00080000),
    ("SLAB_MEM_SPREAD", 0x00100000),
    ("SLAB_TRACE", 0x00200000),
    ("SLAB_DEBUG_OBJECTS", 0x00400000),
    ("SLAB_NOLEAKTRACE", 0x00800000),
    ("SLAB_NOTRACK", 0x01000000),
    ("SLAB_FAILSLAB", 0x02000000),
)

#: Bounds on the kmem_cache list walk.
SLAB_CACHE_LIMIT = 1 << 14

#: Fields decoded from ``struct kmem_cache``; resolved from DWARF, then
#: from :mod:`kernlens.gdb.layouts` when the build has no debug info.
_KMEM_CACHE_FIELDS: tuple[str, ...] = (
    "name", "size", "object_size", "offset", "oo", "align", "flags",
    "list",
)


@dataclass(frozen=True, slots=True)
class SlabCache:
    """One ``struct kmem_cache``."""

    address: int
    name: str
    size: int
    object_size: int
    offset: int
    oo_order: int
    oo_objects: int
    align: int
    flags: tuple[str, ...]


class SlabCacheInspector(InspectorBase):
    """Enumerate SLUB caches and resolve objects to their cache."""

    __slots__: tuple[str, ...] = ()

    def slab_caches(self) -> tuple[SlabCache, ...]:
        """Return every ``struct kmem_cache`` from the global list."""
        head = self._reader.kvar_addr("slab_caches")
        if not head:
            return ()
        list_off = self._slab_list_offset()
        if list_off is None:
            return ()
        result: list[SlabCache] = []
        for obj in self._walk_list(head, list_off, SLAB_CACHE_LIMIT):
            cache = self._read_slab_cache(obj)
            if cache is not None:
                result.append(cache)
        return tuple(result)

    def slab_cache(self, name: str) -> SlabCache | None:
        """Return the cache whose ``name`` matches exactly, or ``None``."""
        for cache in self.slab_caches():
            if cache.name == name:
                return cache
        return None

    def slab_cache_summary(
        self, name_filter: str | None = None,
    ) -> tuple[SlabCache, ...]:
        """Return the caches, optionally filtered by a name substring."""
        caches = self.slab_caches()
        if name_filter is None:
            return caches
        return tuple(c for c in caches if name_filter in c.name)

    def slab_object(
        self, addr: int, page_size: int = 64,
    ) -> tuple[int, SlabCache] | None:
        """Return ``(object_addr, cache)`` for a SLUB object address.

        Translates *addr* through the direct map to its ``struct page``,
        follows the compound head, and reads ``slab_cache`` from the
        resulting ``struct slab``.  ``object_addr`` is the start of the
        containing object (``addr`` rounded down to ``cache->size``).
        """
        if not addr:
            return None
        try:
            page_offset = self._page_offset_base()
            vmemmap = self._vmemmap_base()
            phys = KAddr.virt_to_phys(addr, page_offset)
            page = KAddr.phys_to_page(phys, vmemmap, page_size)
        except ValueError:
            return None
        head = page
        compound = self._reader.u64(
            f"((struct page *){page})->compound_head"
        )
        if compound and (compound & 1):
            head = compound & ~1
        cache_ptr = self._reader.u64(
            f"((struct slab *){head})->slab_cache"
        )
        if not cache_ptr:
            return None
        cache = next(
            (c for c in self.slab_caches() if c.address == cache_ptr), None,
        )
        if cache is None:
            cache = self._read_slab_cache(cache_ptr)
        if cache is None:
            return None
        base = KAddr.page_to_virt(head, page_offset, vmemmap, page_size)
        if cache.size > 0 and addr >= base:
            obj = base + ((addr - base) // cache.size) * cache.size
        else:
            obj = addr
        return obj, cache

    def _slab_list_offset(self) -> int | None:
        """Return ``offsetof(struct kmem_cache, list)``."""
        return self._layout_offset("struct kmem_cache", "list")

    def _read_slab_cache(self, obj: int) -> SlabCache | None:
        """Decode one ``struct kmem_cache``.

        Field offsets come from the loaded ``vmlinux`` DWARF, with a
        verified fallback for the no-debug-info case; the layout varies
        with ``CONFIG_*`` (the debug options add members), so they must
        not be assumed.
        """
        if not self._is_kernel(obj):
            return None
        offsets = {
            key: self._layout_offset("struct kmem_cache", key)
            for key in _KMEM_CACHE_FIELDS
        }
        if offsets["name"] is None or offsets["size"] is None:
            return None
        name_ptr = self._read_u64(obj + offsets["name"])
        name = self._cstring(name_ptr) if name_ptr else None
        size = self._read_u32(obj + offsets["size"], signed=False)
        object_size = (
            self._read_u32(obj + offsets["object_size"], signed=False)
            if offsets["object_size"] is not None else None
        )
        offset = (
            self._read_u32(obj + offsets["offset"], signed=False)
            if offsets["offset"] is not None else None
        )
        oo_x = (
            self._read_u32(obj + offsets["oo"], signed=False)
            if offsets["oo"] is not None else None
        )
        align = (
            self._read_u32(obj + offsets["align"], signed=False)
            if offsets["align"] is not None else None
        )
        flags = (
            self._read_u64(obj + offsets["flags"])
            if offsets["flags"] is not None else 0
        ) or 0
        if name is None or size is None:
            return None
        return SlabCache(
            address=obj,
            name=name,
            size=size,
            object_size=object_size or 0,
            offset=offset or 0,
            oo_order=(oo_x or 0) >> OO_SHIFT,
            oo_objects=(oo_x or 0) & OO_MASK,
            align=align or 0,
            flags=tuple(flag for flag, mask in SLAB_FLAGS if flags & mask),
        )


__all__ = [
    "OO_MASK",
    "OO_SHIFT",
    "SLAB_CACHE_LIMIT",
    "SLAB_FLAGS",
    "SlabCache",
    "SlabCacheInspector",
]