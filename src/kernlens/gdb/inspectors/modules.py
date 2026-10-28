#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""The ``struct module`` linked list and the ``sys_call_table``.

Both tables are located by symbol; the ``struct module`` layout is
recovered by scanning for the ``name`` string field and the 6.4+
``MOD_MEM_*`` descriptor array, avoiding a dependency on the exact
field offsets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

import gdb

from .._types import _IntConvertible, _StrLike
from ._base import LIST_LIMIT, MASK64, PTRSIZE, InspectorBase

#: ``enum mod_mem_type`` entries that make up a module's runtime
#: footprint (MOD_TEXT, MOD_DATA, MOD_RODATA, MOD_RO_AFTER_INIT).
MOD_MEM_TYPES = 4


@dataclass(frozen=True, slots=True)
class Module:
    """One entry from the ``modules`` list."""

    address: int
    name: str
    size: int
    used_by: int | None


@dataclass(frozen=True, slots=True)
class Syscall:
    """One entry from ``sys_call_table``."""

    index: int
    address: int
    symbol: str | None


class ModulesInspector(InspectorBase):
    """The loaded-module list and the syscall dispatch table."""

    __slots__: tuple[str, ...] = ()

    #: Cached ``offsetof(struct module, name)``; ``False`` means not probed.
    _module_name: "int | None | Literal[False]"
    #: Cached ``(mem_off, mem_size, size_off)``; ``False`` means not probed.
    _mem_layout: "tuple[int, int, int] | None | Literal[False]"
    #: Cached ``sys_call_table`` length; ``False`` means not probed.
    _syscall_count: "int | None | Literal[False]"

    # --- modules --------------------------------------------------------

    def modules(self) -> tuple[Module, ...]:
        """Return the ``modules`` list, or ``()`` when unavailable.

        Layout is recovered by scanning ``struct module`` for a string
        field (the name) and for the 6.4+ memory-descriptor array, which
        avoids depending on the exact field offset.
        """
        head = self._reader.kvar_addr("modules")
        if not head:
            return ()
        name_offset = self._module_name_offset()
        if name_offset is None:
            return ()

        result: list[Module] = []
        head_next = self._reader.u64(f"*(unsigned long *){head:#x}")
        if not head_next:
            return ()
        node = head_next
        seen: set[int] = set()
        while node and node != head and len(result) < LIST_LIMIT:
            if node in seen:
                break
            seen.add(node)
            obj = (node - self._offsetof_list()) & MASK64
            name = self._cstring(obj + name_offset) or "?"
            address, size = self._module_mem(obj)
            used_by = self._module_refcnt(obj)
            result.append(
                Module(
                    address=address or obj,
                    name=name,
                    size=size,
                    used_by=used_by,
                )
            )
            nxt = self._reader.u64(f"*(unsigned long *){node:#x}")
            if not nxt:
                break
            node = nxt
        return tuple(result)

    def _offsetof_list(self) -> int:
        """Return ``offsetof(struct module, list)`` (0 when unknown)."""
        offset = self._reader.u64(
            "(unsigned long)&((struct module *)0)->list"
        )
        return offset or 0

    def _module_name_offset(self) -> int | None:
        """Locate ``struct module``'s ``name`` string field.

        The DWARF offset is exact, so it is preferred; the scan is kept
        as a fallback for a build without debug info.
        """
        if self._module_name is not False:
            return self._module_name
        dwarf = self._layout_offset("struct module", "name")
        if dwarf is not None:
            self._module_name = dwarf
            return dwarf
        self._module_name = None
        head = self._reader.kvar_addr("modules")
        if not head:
            return None
        node = self._reader.u64(f"*(unsigned long *){head:#x}")
        if not node:
            return None
        obj = (node - self._offsetof_list()) & MASK64
        for index in range(0x100):
            offset = index * PTRSIZE
            text = self._cstring(obj + offset)
            if text and text.isprintable() and 2 <= len(text) < 64:
                self._module_name = offset
                return offset
        return None

    def _module_mem(self, obj: int) -> tuple[int | None, int]:
        """Return ``(text_base, size)`` for a module (0 when unknown)."""
        cached = self._mem_layout
        if cached is False:
            cached = self._find_module_mem()
            self._mem_layout = cached
        if not cached:
            return None, 0
        offset, mem_size, size_offset = cached
        total = 0
        base: int | None = None
        for mem_type in range(MOD_MEM_TYPES):
            ptr = obj + offset + mem_type * mem_size
            entry_base = self._reader.u64(f"*(unsigned long *){ptr:#x}")
            if mem_type == 0:
                base = entry_base
            size = self._reader.u64(
                f"*(unsigned int *)({ptr + size_offset:#x})"
            )
            if size:
                total += size
        return base, total

    def _find_module_mem(self) -> tuple[int, int, int] | None:
        """Scan ``struct module`` for the ``MOD_MEM_*`` descriptor array."""
        head = self._reader.kvar_addr("modules")
        if not head:
            return None
        node = self._reader.u64(f"*(unsigned long *){head:#x}")
        if not node:
            return None
        obj = (node - self._offsetof_list()) & MASK64
        for index in range(0x100):
            offset = index * PTRSIZE
            for mem_size in (0x10, 0x48):
                if self._module_mem_valid(obj, offset, mem_size):
                    return offset, mem_size, PTRSIZE
        return None

    def _module_mem_valid(self, obj: int, offset: int, mem_size: int) -> bool:
        """Whether an ``offset``/``mem_size`` pair looks like ``MOD_MEM_*``."""
        for mem_type in range(MOD_MEM_TYPES):
            ptr = obj + offset + mem_type * mem_size
            base = self._reader.u64(f"*(unsigned long *){ptr:#x}")
            if base is None or base == 0 or (base & 0xFFF) != 0:
                return False
            size = self._reader.u64(
                f"*(unsigned int *)({ptr + PTRSIZE:#x})"
            )
            if size is None or not 0 < size < 0x100000:
                return False
        return True

    def _module_refcnt(self, obj: int) -> int | None:
        """Return ``module->refcnt`` minus the list's own reference."""
        value = self._reader.u64(
            f"((struct module *){obj:#x})->refcnt.counter"
        )
        if value is None:
            return None
        return max(0, value - 1)

    # --- syscalls -------------------------------------------------------

    def syscall_count(self) -> int | None:
        """Return the ``sys_call_table`` entry count, or ``None``."""
        if self._syscall_count is not False:
            return self._syscall_count
        self._syscall_count = None
        try:
            value = gdb.parse_and_eval(
                "sizeof(sys_call_table) / sizeof(void *)"
            )
            self._syscall_count = int(cast("_IntConvertible", value))
        except (gdb.error, TypeError, ValueError):
            self._syscall_count = None
        return self._syscall_count

    def syscalls(self, name_filter: str | None = None) -> tuple[Syscall, ...]:
        """Return the ``sys_call_table`` entries, optionally filtered."""
        table = self._reader.kvar_addr("sys_call_table")
        if not table:
            return ()
        count = self.syscall_count()
        if count is None or count <= 0:
            return ()
        result: list[Syscall] = []
        for index in range(count):
            addr = self._reader.u64(
                f"*(unsigned long *){table + index * PTRSIZE:#x}"
            )
            if addr is None:
                continue
            symbol = self._symbol_at(addr)
            if name_filter is not None:
                if symbol is None or name_filter not in symbol:
                    continue
            result.append(Syscall(index=index, address=addr, symbol=symbol))
        return tuple(result)

    def _symbol_at(self, addr: int) -> str | None:
        """Resolve a runtime *addr* to a symbol name, or ``None``.

        GDB's symbol table is indexed by link-time addresses, so the
        KASLR slide is removed before the lookup; otherwise every
        relabelled function misses and ``sys_call_table`` decodes to a
        table of unnamed pointers.
        """
        try:
            raw = gdb.execute(f"info symbol {addr:#x}", to_string=True)
        except (gdb.error, TypeError, ValueError):
            return None
        text = cast(_StrLike, raw)
        if "No symbol" in text:
            offset = self._reader.kaslr_offset
            if offset:
                link = (addr - offset) & MASK64
                try:
                    raw = gdb.execute(
                        f"info symbol {link:#x}", to_string=True
                    )
                except (gdb.error, TypeError, ValueError):
                    return None
                text = cast(_StrLike, raw)
                if "No symbol" in text:
                    return None
            else:
                return None
        name = text.split(" in section")[0].strip()
        # GDB appends " + <offset>" for an interior address; drop it so
        # the result matches a bare symbol name.
        name = name.split(" + ")[0].strip()
        return name or None


__all__ = ["MOD_MEM_TYPES", "Module", "ModulesInspector", "Syscall"]