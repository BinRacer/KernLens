#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""CPU topology, online masks, and per-CPU base lookups."""

from __future__ import annotations

from typing import cast, final

import gdb  # type: ignore[import-not-found]

from ._types import _IntConvertible
from .reader import MemoryReader

_MASK64: int = 0xFFFFFFFFFFFFFFFF


@final
class CpuInfo:
    """CPU topology and per-CPU base reads."""

    __slots__: tuple[str, ...] = ("_reader",)

    def __init__(self, reader: MemoryReader) -> None:
        self._reader: MemoryReader = reader

    def nr_cpus(self) -> int:
        """Return ``nr_cpu_ids``, or -1 if unreadable."""
        value = self._reader.read_kvar("nr_cpu_ids", "int")
        return value if value is not None else -1

    def nr_nodes(self) -> int:
        """Return ``nr_node_ids``, defaulting to 1 on UMA or failure."""
        value = self._reader.read_kvar("nr_node_ids", "int")
        if value is None or value <= 0:
            return 1
        return value

    def cpu_online(self, cpu: int | None) -> bool | None:
        """Test a CPU's online bit; ``None`` if the mask is unreadable."""
        if cpu is None or cpu < 0:
            return None
        mask = self._reader.kvar_addr("__cpu_online_mask")
        if not mask:
            return None
        word = self._reader.u64(
            f"((struct cpumask *){mask:#x})->bits[{cpu // 64}]"
        )
        if word is None:
            return None
        return bool((word >> (cpu % 64)) & 1)

    def percpu_start(self) -> int | None:
        """Return the start of the per-CPU section, or ``None``.

        ``__per_cpu_start`` is **zero-based** on x86_64 -- it is the first
        thing in the per-CPU section, so GDB reports its address as ``0``.
        That is a genuine value, not "symbol not found", so it must be
        returned as ``0`` rather than treated as a failure (a missing
        symbol makes the raw ``parse_and_eval`` raise instead).
        """
        try:
            value = gdb.parse_and_eval("(unsigned long)&__per_cpu_start")
            return int(cast(_IntConvertible, value))
        except (gdb.error, TypeError, ValueError):
            return None

    def cur_cpu(self) -> int | None:
        """Best-effort ``raw_smp_processor_id()`` via ``cpu_number``.

        The number lives at ``$gs_base + offset`` where *offset* is the
        symbol's offset inside the per-CPU section, so the section's base
        (``__per_cpu_start``) has to be subtracted -- and it is zero on
        x86_64, which must not be read as a failure.  ``$gs_base`` may be
        reported as a negative Python int, so it is masked to 64 bits
        before it is turned back into an address.
        """
        try:
            gs_value = gdb.parse_and_eval("$gs_base")
            gs_base = int(cast(_IntConvertible, gs_value)) & _MASK64
        except (gdb.error, TypeError, ValueError):
            return None
        if gs_base == 0:
            return None
        percpu_start = self.percpu_start()
        if percpu_start is None:
            return None
        for sym_expr in (
            "(unsigned long)&pcpu_hot.cpu_number",
            "(unsigned long)&cpu_number",
        ):
            try:
                sym_value = gdb.parse_and_eval(sym_expr)
                sym = int(cast(_IntConvertible, sym_value))
            except (gdb.error, TypeError, ValueError):
                continue
            if not sym or sym < percpu_start:
                continue
            offset = sym - percpu_start
            address = (gs_base + offset) & _MASK64
            value = self._reader.u64(f"*(int *)({address:#x})")
            if value is not None:
                return value
        return None

    def percpu_off(self, cpu: int) -> int | None:
        """Read ``__per_cpu_offset[cpu]`` at its runtime address."""
        if cpu < 0:
            return None
        addr = self._reader.kvar_addr(f"__per_cpu_offset[{cpu}]")
        if not addr:
            return None
        return self._reader.u64(f"*(unsigned long *){addr:#x}")


__all__ = ["CpuInfo"]
