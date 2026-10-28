#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""The dma-buf registry and its scatterlists.

The list symbol is ``debugfs_list`` on >= 6.10 and ``db_list`` before it.
``struct dma_buf``'s field offsets are recovered from the first entry (as
pwndbg does), so nothing is hard-coded beyond x86_64 pointer width.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.addr import KAddr
from ._base import MASK64, PTRSIZE, InspectorBase

#: ``SCATTERLIST`` chain/end flag bits.
SG_CHAIN = 0x1
SG_END = 0x2

#: Bound on the scatterlist walk.
SG_LIMIT = 1 << 12

#: Bound on the dma-buf list walk.
DMABUF_LIMIT = 1 << 12


@dataclass(frozen=True, slots=True)
class SgEntry:
    """One entry of a ``struct scatterlist`` chain."""

    index: int
    page: int
    virt: int
    phys: int
    offset: int
    length: int


@dataclass(frozen=True, slots=True)
class DmabufEntry:
    """One ``struct dma_buf`` from the debugfs list."""

    index: int
    address: int
    size: int
    file: int
    exporter: str
    name: str | None
    priv: int
    sg_entries: tuple[SgEntry, ...]


@dataclass(frozen=True, slots=True)
class _DmabufLayout:
    """Resolved ``struct dma_buf`` field offsets plus the exporter scan."""

    list_node: int
    exp_name: int
    name: int
    priv: int
    size_off: int
    file_off: int
    sg_off: int


class DmabufInspector(InspectorBase):
    """Enumerate dma-buf objects and decode their scatterlists."""

    __slots__: tuple[str, ...] = ()

    def dmabufs(self, page_size: int = 64) -> tuple[DmabufEntry, ...]:
        """Return the ``struct dma_buf`` entries from the global list.

        The list symbol is ``debugfs_list`` on >= 6.10 and ``db_list``
        before it.  Field offsets come from the loaded DWARF (then the
        layouts registry); pwndbg's field scan is used only when the
        struct is unknown to both.
        """
        head = self._reader.kvar_addr("debugfs_list")
        if not head:
            head = self._reader.kvar_addr("db_list")
        if not head:
            return ()
        first = self._read_u64(head)
        if not first or first == head:
            return ()
        layout = self._dmabuf_layout(first)
        if layout is None:
            return ()
        result: list[DmabufEntry] = []
        for index, base in enumerate(
            self._walk_list(head, layout.list_node, DMABUF_LIMIT)
        ):
            entry = self._read_dmabuf(index, base, layout, page_size)
            if entry is not None:
                result.append(entry)
        return tuple(result)

    def _dmabuf_layout(self, first: int) -> _DmabufLayout | None:
        """Resolve ``struct dma_buf``'s offsets for this build."""
        list_node = self._layout_offset("struct dma_buf", "list_node")
        exp_name = self._layout_offset("struct dma_buf", "exp_name")
        priv = self._layout_offset("struct dma_buf", "priv")
        if list_node is None or exp_name is None or priv is None:
            return self._dmabuf_scan_layout(first)
        base = (first - list_node) & MASK64
        size_off = self._layout_offset("struct dma_buf", "size") or 0
        file_off = self._layout_offset("struct dma_buf", "file") or PTRSIZE
        name_off = self._layout_offset("struct dma_buf", "name") or (
            exp_name + PTRSIZE
        )
        size = self._read_u64(base + size_off) or 0
        priv_ptr = self._read_u64(base + priv) or 0
        return _DmabufLayout(
            list_node=list_node,
            exp_name=exp_name,
            name=name_off,
            priv=priv,
            size_off=size_off,
            file_off=file_off,
            sg_off=self._dmabuf_sg_offset(priv_ptr, size),
        )

    def _dmabuf_scan_layout(self, first: int) -> _DmabufLayout | None:
        """Recover the offsets by scanning, as pwndbg does.

        *first* is ``&first_entry->list_node``.  ``list_node`` follows
        ``size``/``file``/``attachments``/``ops``/``vmapping_counter``,
        whose integer/pointer mix pins the offset; the exporter name is
        the first nearby readable ``char *``.  Used only when neither the
        debug info nor the registry knows ``struct dma_buf``.
        """
        list_node = None
        for index in range(1, 0x30):
            size = self._read_u64(first - (index + 5) * PTRSIZE)
            file = self._read_u64(first - (index + 4) * PTRSIZE)
            att_prev = self._read_u64(first - (index + 3) * PTRSIZE)
            att_next = self._read_u64(first - (index + 2) * PTRSIZE)
            ops = self._read_u64(first - (index + 1) * PTRSIZE)
            vmap = self._read_u64(first - index * PTRSIZE)
            if (
                size is None
                or file is None
                or att_prev is None
                or att_next is None
                or ops is None
                or vmap is None
            ):
                continue
            if self._is_kernel(size) or self._is_kernel(vmap):
                continue
            if not all(
                self._is_kernel(ptr) for ptr in (file, att_prev, att_next, ops)
            ):
                continue
            list_node = (index + 5) * PTRSIZE
            break
        if list_node is None:
            return None
        base = (first - list_node) & MASK64

        exp_name = None
        for index in range(5, 0x30):
            ptr = self._read_u64(base + index * PTRSIZE)
            if ptr and self._cstring(ptr):
                exp_name = index * PTRSIZE
                break
        if exp_name is None:
            return None

        size = self._read_u64(base) or 0
        priv_off = 0x90
        for index in range(0x30):
            priv = self._read_u64(base + index * PTRSIZE)
            if (
                priv is not None
                and self._is_kernel(priv)
                and self._dmabuf_sg_offset(priv, size) != 0x10
            ):
                priv_off = index * PTRSIZE
                break
        return _DmabufLayout(
            list_node=list_node,
            exp_name=exp_name,
            name=exp_name + PTRSIZE,
            priv=priv_off,
            size_off=0,
            file_off=PTRSIZE,
            sg_off=self._dmabuf_sg_offset(
                self._read_u64(base + priv_off) or 0, size,
            ),
        )

    def _dmabuf_sg_offset(self, priv: int, size: int) -> int:
        """Return the ``sg_table`` offset inside the exporter's priv struct.

        The exporter's private object (e.g. ``system_heap_buffer``) is not
        part of the ``struct dma_buf`` debug info, so the ``sg_table``
        pointer is found by scanning for a word equal to the buffer size.
        """
        if self._is_kernel(priv):
            for index in range(0x30):
                if self._read_u64(priv + index * PTRSIZE) == size:
                    return (index + 1) * PTRSIZE
        return 0x10

    def _read_dmabuf(
        self,
        index: int,
        base: int,
        layout: _DmabufLayout,
        page_size: int,
    ) -> DmabufEntry | None:
        """Decode one ``struct dma_buf`` from the resolved layout."""
        if not self._is_kernel(base):
            return None
        file = self._read_u64(base + layout.file_off) or 0
        size = self._read_u64(base + layout.size_off) or 0
        priv = self._read_u64(base + layout.priv) or 0
        exp_ptr = self._read_u64(base + layout.exp_name)
        name_ptr = self._read_u64(base + layout.name)
        return DmabufEntry(
            index=index,
            address=base,
            size=size,
            file=file,
            exporter=(self._cstring(exp_ptr) or "") if exp_ptr else "",
            name=(self._cstring(name_ptr) if name_ptr else None),
            priv=priv,
            sg_entries=self._dmabuf_sg_table(priv, layout.sg_off, page_size),
        )

    def _dmabuf_sg_table(
        self, priv: int, sg_off: int, page_size: int,
    ) -> tuple[SgEntry, ...]:
        """Walk the scatterlist chain reachable from ``priv.sg_table``."""
        if not self._is_kernel(priv):
            return ()
        sg_table = priv + sg_off
        sgl = self._read_u64(sg_table)
        nents = self._read_u32(sg_table + PTRSIZE, signed=False) or 0
        if not sgl or not nents or not self._is_kernel(sgl):
            return ()
        result: list[SgEntry] = []
        current = sgl
        seen: set[int] = set()
        while current and len(result) < SG_LIMIT:
            if current in seen:
                break
            seen.add(current)
            page_link = self._read_u64(current) or 0
            offset = self._read_u32(current + PTRSIZE, signed=False) or 0
            length = self._read_u32(current + PTRSIZE + 4, signed=False) or 0
            page = page_link & ~(SG_CHAIN | SG_END)
            try:
                virt = KAddr.page_to_virt(
                    page, self._page_offset_base(), self._vmemmap_base(),
                    page_size,
                )
                phys = KAddr.page_to_phys(page, self._vmemmap_base(), page_size)
            except ValueError:
                virt = phys = 0
            result.append(
                SgEntry(
                    index=len(result), page=page, virt=virt, phys=phys,
                    offset=offset, length=length,
                )
            )
            if page_link & SG_END:
                break
            current = current + 0x18
        return tuple(result)


__all__ = [
    "DMABUF_LIMIT",
    "SG_CHAIN",
    "SG_END",
    "SG_LIMIT",
    "DmabufEntry",
    "DmabufInspector",
    "SgEntry",
]