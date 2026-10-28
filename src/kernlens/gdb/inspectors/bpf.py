#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""Enumerate BPF programs and maps through the idr/xarray tables.

``prog_idr`` / ``map_idr`` are ``struct idr`` wrapping an XArray, so the
walk descends ``xa_node`` trees collecting the leaf slots (each a
``struct bpf_prog`` / ``struct bpf_map`` pointer) and decodes them with
x86_64 field offsets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ._base import PTRSIZE, InspectorBase

#: ``struct xa_node``: only ``slots`` is 64 entries wide on every build.
XA_NODE_SLOTS = 64

#: ``struct bpf_map`` / ``struct bpf_array`` array-data layout, x86_64.
#: ``bpf_array`` follows ``bpf_map`` with ``u32 elem_size; u32 index_mask``
#: and an 8-byte-aligned flexible array.
BPF_ARRAY_TYPES = ("BPF_MAP_TYPE_ARRAY", "BPF_MAP_TYPE_PROG_ARRAY")
BPF_MAX_VALUE = 0x20
BPF_SCAN_LIMIT = 200


@dataclass(frozen=True, slots=True)
class BpfProg:
    """One entry from the BPF ``prog_idr``."""

    index: int
    address: int
    type: str
    attach_type: str
    func: int
    aux: int
    jited_len: int
    insn_count: int
    insns: bytes | None


@dataclass(frozen=True, slots=True)
class BpfMap:
    """One entry from the BPF ``map_idr``."""

    index: int
    address: int
    type: str
    key_size: int
    value_size: int
    max_entries: int
    array_addr: int | None


def bpf_prog_type_name(value: int) -> str:
    """Map an ``enum bpf_prog_type`` value to its name."""
    names = (
        "BPF_PROG_TYPE_UNSPEC", "BPF_PROG_TYPE_SOCKET_FILTER",
        "BPF_PROG_TYPE_KPROBE", "BPF_PROG_TYPE_SCHED_CLS",
        "BPF_PROG_TYPE_SCHED_ACT", "BPF_PROG_TYPE_TRACEPOINT",
        "BPF_PROG_TYPE_XDP", "BPF_PROG_TYPE_PERF_EVENT",
        "BPF_PROG_TYPE_CGROUP_SKB", "BPF_PROG_TYPE_CGROUP_SOCK",
        "BPF_PROG_TYPE_LWT_IN", "BPF_PROG_TYPE_LWT_OUT",
        "BPF_PROG_TYPE_LWT_XMIT", "BPF_PROG_TYPE_SOCK_OPS",
        "BPF_PROG_TYPE_SK_SKB", "BPF_PROG_TYPE_CGROUP_DEVICE",
        "BPF_PROG_TYPE_SK_MSG", "BPF_PROG_TYPE_RAW_TRACEPOINT",
        "BPF_PROG_TYPE_CGROUP_SOCK_ADDR", "BPF_PROG_TYPE_LWT_SEG6LOCAL",
        "BPF_PROG_TYPE_LIRC_MODE2", "BPF_PROG_TYPE_SK_REUSEPORT",
        "BPF_PROG_TYPE_FLOW_DISSECTOR", "BPF_PROG_TYPE_CGROUP_SYSCTL",
        "BPF_PROG_TYPE_RAW_TRACEPOINT_WRITABLE",
        "BPF_PROG_TYPE_CGROUP_SOCKOPT", "BPF_PROG_TYPE_TRACING",
        "BPF_PROG_TYPE_STRUCT_OPS", "BPF_PROG_TYPE_EXT",
        "BPF_PROG_TYPE_LSM", "BPF_PROG_TYPE_SK_LOOKUP",
        "BPF_PROG_TYPE_SYSCALL", "BPF_PROG_TYPE_NETFILTER",
    )
    if 0 <= value < len(names):
        return names[value]
    return f"BPF_PROG_TYPE_{value}"


def bpf_attach_type_name(value: int) -> str:
    """Map an ``enum bpf_attach_type`` value to its name."""
    names = (
        "BPF_CGROUP_INET_INGRESS", "BPF_CGROUP_INET_EGRESS",
        "BPF_CGROUP_INET_SOCK_CREATE", "BPF_CGROUP_SOCK_OPS",
        "BPF_SK_SKB_STREAM_PARSER", "BPF_SK_SKB_STREAM_VERDICT",
        "BPF_CGROUP_DEVICE", "BPF_SK_MSG_VERDICT",
        "BPF_CGROUP_INET4_BIND", "BPF_CGROUP_INET6_BIND",
        "BPF_CGROUP_INET4_CONNECT", "BPF_CGROUP_INET6_CONNECT",
        "BPF_CGROUP_INET4_POST_BIND", "BPF_CGROUP_INET6_POST_BIND",
        "BPF_CGROUP_UDP4_SENDMSG", "BPF_CGROUP_UDP6_SENDMSG",
        "BPF_LIRC_MODE2", "BPF_FLOW_DISSECTOR", "BPF_CGROUP_SYSCTL",
        "BPF_CGROUP_UDP4_RECVMSG", "BPF_CGROUP_UDP6_RECVMSG",
        "BPF_CGROUP_GETSOCKOPT", "BPF_CGROUP_SETSOCKOPT",
        "BPF_TRACE_RAW_TP", "BPF_TRACE_FENTRY", "BPF_TRACE_FEXIT",
        "BPF_MODIFY_RETURN", "BPF_LSM_MAC", "BPF_TRACE_ITER",
        "BPF_CGROUP_INET4_GETPEERNAME", "BPF_CGROUP_INET6_GETPEERNAME",
        "BPF_CGROUP_INET4_GETSOCKNAME", "BPF_CGROUP_INET6_GETSOCKNAME",
        "BPF_XDP_DEVMAP", "BPF_CGROUP_INET_SOCK_RELEASE",
        "BPF_XDP_CPUMAP", "BPF_SK_LOOKUP", "BPF_XDP",
        "BPF_SK_SKB_VERDICT", "BPF_SK_REUSEPORT_SELECT",
        "BPF_SK_REUSEPORT_SELECT_OR_MIGRATE", "BPF_PERF_EVENT",
        "BPF_TRACE_KPROBE_MULTI", "BPF_LSM_CGROUP", "BPF_STRUCT_OPS",
        "BPF_NETFILTER", "BPF_TCX_INGRESS", "BPF_TCX_EGRESS",
        "BPF_TRACE_UPROBE_MULTI",
    )
    if 0 <= value < len(names):
        return names[value]
    return f"BPF_ATTACH_TYPE_{value}"


def bpf_map_type_name(value: int) -> str:
    """Map an ``enum bpf_map_type`` value to its name."""
    names = (
        "BPF_MAP_TYPE_UNSPEC", "BPF_MAP_TYPE_HASH", "BPF_MAP_TYPE_ARRAY",
        "BPF_MAP_TYPE_PROG_ARRAY", "BPF_MAP_TYPE_PERF_EVENT_ARRAY",
        "BPF_MAP_TYPE_PERCPU_HASH", "BPF_MAP_TYPE_PERCPU_ARRAY",
        "BPF_MAP_TYPE_STACK_TRACE", "BPF_MAP_TYPE_CGROUP_ARRAY",
        "BPF_MAP_TYPE_LRU_HASH", "BPF_MAP_TYPE_LRU_PERCPU_HASH",
        "BPF_MAP_TYPE_LPM_TRIE", "BPF_MAP_TYPE_ARRAY_OF_MAPS",
        "BPF_MAP_TYPE_HASH_OF_MAPS", "BPF_MAP_TYPE_DEVMAP",
        "BPF_MAP_TYPE_SOCKMAP", "BPF_MAP_TYPE_CPUMAP",
        "BPF_MAP_TYPE_XSKMAP", "BPF_MAP_TYPE_SOCKHASH",
        "BPF_MAP_TYPE_CGROUP_STORAGE", "BPF_MAP_TYPE_REUSEPORT_SOCKARRAY",
        "BPF_MAP_TYPE_PERCPU_CGROUP_STORAGE", "BPF_MAP_TYPE_QUEUE",
        "BPF_MAP_TYPE_STACK", "BPF_MAP_TYPE_SK_STORAGE",
        "BPF_MAP_TYPE_DEVMAP_HASH", "BPF_MAP_TYPE_STRUCT_OPS",
        "BPF_MAP_TYPE_RINGBUF", "BPF_MAP_TYPE_INODE_STORAGE",
        "BPF_MAP_TYPE_TASK_STORAGE", "BPF_MAP_TYPE_BLOOM_FILTER",
        "BPF_MAP_TYPE_USER_RINGBUF", "BPF_MAP_TYPE_CGRP_STORAGE",
        "BPF_MAP_TYPE_ARENA",
    )
    if 0 <= value < len(names):
        return names[value]
    return f"BPF_MAP_TYPE_{value}"


class BpfInspector(InspectorBase):
    """Enumerate BPF programs/maps and decode their x86_64 fields."""

    __slots__: tuple[str, ...] = ()

    #: Cached array-data offset; ``False`` means not yet probed.
    _bpf_array_off: "int | None | bool"

    def bpf_progs(self) -> tuple[BpfProg, ...]:
        """Return the BPF programs registered in ``prog_idr``."""
        head = self._bpf_idr_head("prog_idr")
        if head is None:
            return ()
        result: list[BpfProg] = []
        for index, slot in enumerate(self._xarray_slots(head)):
            prog = self._read_bpf_prog(index, slot)
            if prog is not None:
                result.append(prog)
        return tuple(result)

    def bpf_maps(self) -> tuple[BpfMap, ...]:
        """Return the BPF maps registered in ``map_idr``."""
        head = self._bpf_idr_head("map_idr")
        if head is None:
            return ()
        result: list[BpfMap] = []
        for index, slot in enumerate(self._xarray_slots(head)):
            bpf_map = self._read_bpf_map(index, slot)
            if bpf_map is not None:
                result.append(bpf_map)
        return tuple(result)

    def bpf_map_value(self, addr: int, value_size: int) -> bytes | None:
        """Read an element from an array/prog-array map (capped)."""
        size = min(value_size, BPF_MAX_VALUE)
        if size <= 0:
            return None
        return self._read_bytes(addr, size)

    def _bpf_idr_head(self, symbol: str) -> int | None:
        """Return the ``xa_head`` pointer of a struct idr, or ``None``."""
        idr = self._reader.kvar_addr(symbol)
        if not idr:
            return None
        offset = self._bpf_head_offset(idr)
        if offset is None:
            return None
        return self._read_u64(idr + offset)

    def _bpf_head_offset(self, idr: int) -> int | None:
        """Locate ``struct xarray.xa_head`` inside a ``struct idr``.

        For an empty idr the head slot is zero, so this scans the first
        pointer-width words for one that holds a kernel ``xa_node``.
        """
        for index in range(8):
            value = self._read_u64(idr + index * PTRSIZE)
            if value and self._is_kernel(value & ~3):
                return index * PTRSIZE
        return None

    def _xarray_slots(self, head: int) -> list[int]:
        """Collect every value slot reachable from an XArray head."""
        node = head & ~3
        if not self._is_kernel(node):
            return [head] if head else []
        return self._xa_walk(node)

    def _xa_walk(self, node: int) -> list[int]:
        """Recurse through an ``xa_node`` collecting leaf slot values."""
        result: list[int] = []
        shift_off = self._layout_offset("struct xa_node", "shift")
        count_off = self._layout_offset("struct xa_node", "count")
        slots_off = self._layout_offset("struct xa_node", "slots")
        if shift_off is None or count_off is None or slots_off is None:
            return result
        shift = self._read_u8(node + shift_off)
        count_raw = self._read_u8(node + count_off)
        if shift is None or count_raw is None:
            return result
        count = count_raw
        for index in range(XA_NODE_SLOTS):
            slot = self._read_u64(node + slots_off + index * 8)
            if not slot:
                continue
            if shift:
                result.extend(self._xa_walk(slot & ~3))
            else:
                result.append(slot)
            count -= 1
            if count == 0:
                break
        return result

    def _read_bpf_prog(self, index: int, addr: int) -> BpfProg | None:
        """Decode one ``struct bpf_prog`` (DWARF/registry field offsets)."""
        if not self._is_kernel(addr):
            return None
        type_off = self._layout_offset("struct bpf_prog", "type")
        attach_off = self._layout_offset(
            "struct bpf_prog", "expected_attach_type"
        )
        len_off = self._layout_offset("struct bpf_prog", "len")
        jited_off = self._layout_offset("struct bpf_prog", "jited_len")
        func_off = self._layout_offset("struct bpf_prog", "bpf_func")
        aux_off = self._layout_offset("struct bpf_prog", "aux")
        insns_off = self._layout_offset("struct bpf_prog", "insns")
        if (
            type_off is None
            or len_off is None
            or jited_off is None
            or insns_off is None
        ):
            return None
        prog_type = self._read_u32(addr + type_off, signed=False)
        attach = (
            self._read_u32(addr + attach_off, signed=False)
            if attach_off is not None else None
        )
        insn_count = self._read_u32(addr + len_off, signed=False) or 0
        jited_len = self._read_u32(addr + jited_off, signed=False) or 0
        func = self._read_u64(addr + func_off) if func_off is not None else 0
        aux = self._read_u64(addr + aux_off) if aux_off is not None else 0
        insns = None
        if 0 < insn_count <= 0x1000:
            insns = self._read_bytes(addr + insns_off, insn_count * 8)
        return BpfProg(
            index=index,
            address=addr,
            type=bpf_prog_type_name(prog_type or 0),
            attach_type=bpf_attach_type_name(attach or 0),
            func=func or 0,
            aux=aux or 0,
            jited_len=jited_len,
            insn_count=insn_count,
            insns=insns,
        )

    def _read_bpf_map(self, index: int, addr: int) -> BpfMap | None:
        """Decode one ``struct bpf_array``/``struct bpf_map``.

        The ``map_type``/``key_size``/``value_size``/``max_entries``
        offsets shift with ``CONFIG_SECURITY`` (an LSM ``security``
        pointer is inserted), so they are resolved from the debug info
        or the layouts registry rather than assumed to be ``0x10``.
        """
        if not self._is_kernel(addr):
            return None
        type_off = self._layout_offset("struct bpf_map", "map_type")
        key_off = self._layout_offset("struct bpf_map", "key_size")
        val_off = self._layout_offset("struct bpf_map", "value_size")
        max_off = self._layout_offset("struct bpf_map", "max_entries")
        if (
            type_off is None
            or key_off is None
            or val_off is None
            or max_off is None
        ):
            return None
        map_type = self._read_u32(addr + type_off, signed=False)
        key_size = self._read_u32(addr + key_off, signed=False) or 0
        value_size = self._read_u32(addr + val_off, signed=False) or 0
        max_entries = self._read_u32(addr + max_off, signed=False) or 0
        name = bpf_map_type_name(map_type or 0)
        offset = self._bpf_map_array_offset(addr, name, max_entries, value_size)
        array_addr = addr + offset if offset is not None else None
        return BpfMap(
            index=index,
            address=addr,
            type=name,
            key_size=key_size,
            value_size=value_size,
            max_entries=max_entries,
            array_addr=array_addr,
        )

    def _bpf_map_array_offset(
        self, addr: int, map_type: str, max_entries: int, value_size: int,
    ) -> int | None:
        """Find the array-data offset inside a ``struct bpf_array``.

        Scans the raw u32 words for the ``{elem_size, index_mask}`` pair
        the kernel writes for array/prog-array maps, which pins the
        flexible-array offset without depending on field offsets.
        """
        if self._bpf_array_off is not False and self._bpf_array_off is not None:
            return self._bpf_array_off
        if map_type not in BPF_ARRAY_TYPES or max_entries <= 0:
            return None
        expected_elem = math.ceil(value_size / 8) * 8
        expected_mask = (1 << math.ceil(math.log2(max_entries))) - 1
        for index in range(BPF_SCAN_LIMIT):
            elem_size = self._read_u32(addr + 4 * index, signed=False)
            index_mask = self._read_u32(addr + 4 * (index + 1), signed=False)
            if elem_size == expected_elem and index_mask == expected_mask:
                offset = (index + 2) * 4 + PTRSIZE
                self._bpf_array_off = offset
                return offset
        return None


__all__ = [
    "BPF_ARRAY_TYPES",
    "BPF_MAX_VALUE",
    "BPF_SCAN_LIMIT",
    "XA_NODE_SLOTS",
    "BpfInspector",
    "BpfMap",
    "BpfProg",
    "bpf_attach_type_name",
    "bpf_map_type_name",
    "bpf_prog_type_name",
]