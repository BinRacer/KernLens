#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""Kernel introspection facade: one object, one method per subsystem.

``KernelInspector`` composes the per-domain mixins in
:mod:`kernlens.gdb.inspectors` behind a single object, so the debugger
facade keeps binding the classic method names while the implementation
is split across focused modules.  The only state this class owns is the
per-subsystem cache slots and :meth:`reset`.

See :mod:`kernlens.gdb.inspectors` for the per-domain readers.
"""

from __future__ import annotations

from typing import Literal

from .inspectors import (
    BpfInspector,
    BpfMap,
    BpfProg,
    BuddyInspector,
    BuddyPage,
    DmabufEntry,
    DmabufInspector,
    DmesgInspector,
    DmesgRecord,
    Kallsym,
    KallsymsInspector,
    MetadataInspector,
    Module,
    ModulesInspector,
    SgEntry,
    SlabCache,
    SlabCacheInspector,
    StructPageInspector,
    Syscall,
    bpf_attach_type_name,
    bpf_map_type_name,
    bpf_prog_type_name,
)
from .reader import MemoryReader


class KernelInspector(
    MetadataInspector,
    ModulesInspector,
    KallsymsInspector,
    DmesgInspector,
    BpfInspector,
    BuddyInspector,
    StructPageInspector,
    SlabCacheInspector,
    DmabufInspector,
):
    """Kernel version, config, modules, memory, BPF, and SLUB in one API.

    Derived state (the config image, the module struct offsets, the
    syscall count, the decoded kallsyms table, the BPF array offset) is
    computed once and cached; call :meth:`reset` after a ``file`` reload
    or a different kernel is loaded.
    """

    #: All cache slots live on :class:`InspectorBase` -- see the comment
    #: there for why a mixin cannot own its own ``__slots__``.
    __slots__: tuple[str, ...] = ()

    #: Cached parsed ``CONFIG_*`` image (``None`` until first read).
    _config: "dict[str, str] | None"
    #: Cached ``offsetof(struct module, name)``; ``False`` means not probed.
    _module_name: "int | None | Literal[False]"
    #: Cached ``(mem_off, mem_size, size_off)``; ``False`` means not probed.
    _mem_layout: "tuple[int, int, int] | None | Literal[False]"
    #: Cached ``sys_call_table`` length; ``False`` means not probed.
    _syscall_count: "int | None | Literal[False]"
    #: Cached decoded kallsyms table (``None`` until first read).
    _kallsyms: "tuple[Kallsym, ...] | None"
    #: Cached BPF array-data offset; ``False`` means not probed.
    _bpf_array_off: "int | None | Literal[False]"

    def __init__(self, reader: MemoryReader) -> None:
        self._reader: MemoryReader = reader
        self._offsets = {}
        self._fallbacks = set()
        self._btf = False
        self._config = None
        self._module_name = False
        self._mem_layout = False
        self._syscall_count = False
        self._kallsyms = None
        self._bpf_array_off = False
        self._page_is_enum = False

    def reset(self) -> None:
        """Drop cached derived state (call after an objfile reload)."""
        self._offsets = {}
        self.clear_layout_fallbacks()
        self._config = None
        self._module_name = False
        self._mem_layout = False
        self._syscall_count = False
        self._kallsyms = None
        self._bpf_array_off = False
        self._page_is_enum = False


__all__ = [
    "BpfMap",
    "BpfProg",
    "BuddyPage",
    "DmabufEntry",
    "DmesgRecord",
    "Kallsym",
    "KernelInspector",
    "Module",
    "SgEntry",
    "SlabCache",
    "Syscall",
    "bpf_attach_type_name",
    "bpf_map_type_name",
    "bpf_prog_type_name",
]