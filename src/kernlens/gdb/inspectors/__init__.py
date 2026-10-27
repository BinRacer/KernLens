#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""Kernel subsystem inspectors, one file per closed domain.

Every inspector is a small mixin that reads one kernel subsystem through
the KASLR-aware :class:`~kernlens.gdb.reader.MemoryReader`:

* :mod:`~kernlens.gdb.inspectors.metadata` — version / cmdline / config
* :mod:`~kernlens.gdb.inspectors.modules` — the ``modules`` list and
  ``sys_call_table``
* :mod:`~kernlens.gdb.inspectors.structpage` — x86_64 ``struct page``
* :mod:`~kernlens.gdb.inspectors.kallsyms` — the embedded symbol table
* :mod:`~kernlens.gdb.inspectors.dmesg` — the ``printk_ringbuffer``
* :mod:`~kernlens.gdb.inspectors.bpf` — BPF progs/maps
* :mod:`~kernlens.gdb.inspectors.buddy` — the buddy allocator
* :mod:`~kernlens.gdb.inspectors.slabcache` — SLUB caches
* :mod:`~kernlens.gdb.inspectors.dmabuf` — dma-buf and scatterlists

``KernelInspector`` (in :mod:`kernlens.gdb.kernel`) composes them all
behind one object so the facade can keep binding the classic method
names.  Splitting the old 1.6k-line class this way gives each domain its
own constants, dataclasses, and tests.
"""

from __future__ import annotations

from ._base import InspectorBase
from .bpf import (
    BpfInspector,
    BpfMap,
    BpfProg,
    bpf_attach_type_name,
    bpf_map_type_name,
    bpf_prog_type_name,
)
from .buddy import BuddyInspector, BuddyPage, BlockLocation, ZoneSpan
from .dmabuf import DmabufEntry, DmabufInspector, SgEntry
from .dmesg import DmesgInspector, DmesgRecord
from .kallsyms import Kallsym, KallsymsInspector
from .metadata import MetadataInspector
from .modules import Module, ModulesInspector, Syscall
from .slabcache import SlabCache, SlabCacheInspector
from .structpage import StructPageInspector

__all__ = [
    "BpfInspector",
    "BpfMap",
    "BpfProg",
    "BuddyInspector",
    "BuddyPage",
    "BlockLocation",
    "ZoneSpan",
    "DmabufEntry",
    "DmabufInspector",
    "DmesgInspector",
    "DmesgRecord",
    "InspectorBase",
    "Kallsym",
    "KallsymsInspector",
    "MetadataInspector",
    "Module",
    "ModulesInspector",
    "SgEntry",
    "SlabCache",
    "SlabCacheInspector",
    "StructPageInspector",
    "Syscall",
    "bpf_attach_type_name",
    "bpf_map_type_name",
    "bpf_prog_type_name",
]