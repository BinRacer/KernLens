#!/usr/bin/env python3
#
# ruff: noqa: EXE001
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""GDB-side companions for :mod:`kernlens`.

Importing this package is safe outside GDB: the public names are resolved
lazily, and only the components that read debuggee memory require the
``gdb`` module.  Inside a GDB Python session either import the package::

    import sys
    sys.path.insert(0, "/path/to/repo/src")
    from kernlens.gdb import kdbg

The facade is also available directly as
:mod:`kernlens.gdb.facade`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "BpfMap",
    "BpfProg",
    "BuddyPage",
    "CpuInfo",
    "DebugConfig",
    "DmabufEntry",
    "DmesgRecord",
    "IdtEntry",
    "IdtInfo",
    "Kallsym",
    "Kaslr",
    "Kbase",
    "KbaseResult",
    "KernelDebugger",
    "KernelInspector",
    "KernelStyler",
    "MemoryReader",
    "PageTableWalker",
    "PageWalk",
    "SgEntry",
    "SlabCache",
    "SlubInspector",
    "SymbolResolver",
    "WalkLevel",
    "kdbg",
]

if TYPE_CHECKING:
    from .config import DebugConfig as DebugConfig
    from .cpu import CpuInfo as CpuInfo
    from .facade import KernelDebugger as KernelDebugger
    from .facade import kdbg as kdbg
    from .kaslr import Kaslr as Kaslr
    from .kbase import IdtEntry as IdtEntry
    from .kbase import IdtInfo as IdtInfo
    from .kbase import Kbase as Kbase
    from .kbase import KbaseResult as KbaseResult
    from .kernel import BpfMap as BpfMap
    from .kernel import BpfProg as BpfProg
    from .kernel import BuddyPage as BuddyPage
    from .kernel import DmabufEntry as DmabufEntry
    from .kernel import DmesgRecord as DmesgRecord
    from .kernel import Kallsym as Kallsym
    from .kernel import KernelInspector as KernelInspector
    from .kernel import SgEntry as SgEntry
    from .kernel import SlabCache as SlabCache
    from .reader import MemoryReader as MemoryReader
    from .slub import SlubInspector as SlubInspector
    from .styler import KernelStyler as KernelStyler
    from .symbols import SymbolResolver as SymbolResolver
    from .walker import PageTableWalker as PageTableWalker
    from .walker import PageWalk as PageWalk
    from .walker import WalkLevel as WalkLevel


_EXPORTS = {
    "BpfMap": ".kernel",
    "BpfProg": ".kernel",
    "BuddyPage": ".kernel",
    "CpuInfo": ".cpu",
    "DebugConfig": ".config",
    "DmabufEntry": ".kernel",
    "DmesgRecord": ".kernel",
    "IdtEntry": ".kbase",
    "IdtInfo": ".kbase",
    "Kaslr": ".kaslr",
    "Kbase": ".kbase",
    "KbaseResult": ".kbase",
    "Kallsym": ".kernel",
    "KernelDebugger": ".facade",
    "KernelInspector": ".kernel",
    "KernelStyler": ".styler",
    "MemoryReader": ".reader",
    "PageTableWalker": ".walker",
    "PageWalk": ".walker",
    "SgEntry": ".kernel",
    "SlabCache": ".kernel",
    "SlubInspector": ".slub",
    "SymbolResolver": ".symbols",
    "WalkLevel": ".walker",
    "kdbg": ".facade",
}


def __getattr__(name: str) -> Any:
    """Resolve a component lazily from its own module."""
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    module = import_module(module_name, __name__)
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted([*globals(), *__all__])