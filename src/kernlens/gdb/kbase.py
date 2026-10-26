#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Locate the runtime kernel text base from the x86-64 IDT.

The kernel IDT is a convenient anchor for KASLR recovery: its gate
descriptors point at exception entry stubs in ``.text``.  Given one
handler address, the base can be recovered without relying on a
pre-configured slide:

* compare the handler with the link-time address of the corresponding
  IDT stub symbol (``asm_exc_divide_error`` for gate 0);
* otherwise find the containing mapping via QEMU's ``monitor info mem``;
* finally fall back to the kernel text alignment (2 MiB).

The first strategy is exact when a matching ``vmlinux`` is loaded.  The
second is exact when QEMU exposes the memory map.  The last is a
deliberate heuristic for symbol-less/QEMU-less sessions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, final

import gdb  # type: ignore[import-not-found]

from ..core.addr import KAddr
from .config import DebugConfig
from .reader import MemoryReader

#: One x86-64 IDT gate descriptor is 16 bytes.
IDT_GATE_SIZE: Final[int] = 16

#: The architectural IDT has 256 entries.
IDT_MAX_ENTRIES: Final[int] = 256

#: Linux gate types: interrupt gate (0xE) and trap gate (0xF).
_IDT_GATE_TYPES: Final[tuple[int, ...]] = (0xE, 0xF)

#: Link-time symbols for the exception gates most commonly used as an
#: anchor.  Gate 0 is enough on normal kernels; the rest are fallbacks.
_IDT_SYMBOLS: Final[dict[int, tuple[str, ...]]] = {
    0: ("asm_exc_divide_error", "divide_error"),
    1: ("asm_exc_debug", "debug"),
    2: ("asm_exc_nmi", "nmi"),
    3: ("asm_exc_int3", "int3"),
    4: ("asm_exc_overflow", "overflow"),
    5: ("asm_exc_bounds", "bounds"),
    6: ("asm_exc_invalid_op", "invalid_op"),
    7: ("asm_exc_device_not_available", "device_not_available"),
    8: ("asm_exc_double_fault", "double_fault"),
    10: ("asm_exc_invalid_tss", "invalid_TSS"),
    11: ("asm_exc_segment_not_present", "segment_not_present"),
    12: ("asm_exc_stack_segment", "stack_segment"),
    13: ("asm_exc_general_protection", "general_protection"),
    14: ("asm_exc_page_fault", "page_fault"),
    16: ("asm_exc_coprocessor_error", "coprocessor_error"),
    17: ("asm_exc_alignment_check", "alignment_check"),
    18: ("asm_exc_machine_check", "machine_check"),
    19: ("asm_exc_simd_coprocessor_error", "simd_coprocessor_error"),
}

_IDT_REGISTER_RE: Final[re.Pattern[str]] = re.compile(
    r"\bIDT\s*=\s*(?:0x)?([0-9a-fA-F]+)\s+(?:0x)?([0-9a-fA-F]+)",
    re.IGNORECASE,
)
_MEM_MAP_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:0x)?([0-9a-fA-F]+)-(?:0x)?([0-9a-fA-F]+)\s+"
)
_MASK64: Final[int] = 0xFFFFFFFFFFFFFFFF
_TEXT_ALIGN: Final[int] = 0x200000
_MAX_TEXT_SPAN: Final[int] = 0x20000000


@dataclass(frozen=True, slots=True)
class IdtInfo:
    """Where the live IDT was found."""

    base: int
    limit: int
    source: str

    @property
    def count(self) -> int:
        """Number of complete 16-byte gate descriptors in the table."""
        return max(0, min(IDT_MAX_ENTRIES, (self.limit + 1) // IDT_GATE_SIZE))


@dataclass(frozen=True, slots=True)
class IdtEntry:
    """One decoded x86-64 IDT gate descriptor."""

    index: int
    address: int
    offset: int
    selector: int
    gate_type: int
    ist: int
    dpl: int
    present: bool

    @property
    def is_kernel_gate(self) -> bool:
        """Whether this looks like a present kernel exception gate."""
        return (
            self.present
            and self.gate_type in _IDT_GATE_TYPES
            and self.offset != 0
            and KAddr.is_kernel(self.offset)
        )


@dataclass(frozen=True, slots=True)
class KbaseResult:
    """Result of kernel text-base recovery."""

    base: int
    handler: int | None = None
    handler_symbol: str | None = None
    idt: IdtInfo | None = None
    method: str = "unknown"
    link_text: int | None = None
    kaslr_offset: int | None = None


@final
class Kbase:
    """Recover the runtime kernel text base from the live IDT.

    A new object is intentionally cheap and stateless apart from the
    reader/config references, so tracer code can instantiate an
    independent finder without touching global state.
    """

    __slots__: tuple[str, ...] = ("_config", "_reader")

    def __init__(self, config: DebugConfig, reader: MemoryReader) -> None:
        self._config: DebugConfig = config
        self._reader: MemoryReader = reader

    # --- IDT discovery --------------------------------------------------

    def _monitor(self, command: str) -> str:
        """Run a monitor command, returning ``""`` when unavailable."""
        try:
            return gdb.execute(command, to_string=True) or ""
        except (gdb.error, TypeError, ValueError, AttributeError):
            return ""

    def idt(self) -> IdtInfo | None:
        """Return the live IDT base/limit, if discoverable.

        QEMU exposes ``IDT=`` in ``monitor info registers``.  Some GDB
        stubs also expose ``$idt`` / ``$idt_limit``.  ``idt_table`` is
        the last resort for sessions where the kernel symbols point at
        the runtime table.
        """
        output = self._monitor("monitor info registers")
        match = _IDT_REGISTER_RE.search(output)
        if match:
            base = int(match.group(1), 16)
            if base:
                return IdtInfo(
                    base=base,
                    limit=int(match.group(2), 16),
                    source="monitor",
                )

        base = self._reader.u64("$idt")
        limit = self._reader.u64("$idt_limit")
        if base:
            return IdtInfo(
                base=base & _MASK64,
                limit=(limit if limit is not None else 0xFFF) & 0xFFFF,
                source="register",
            )

        table = self._reader.kvar_addr("idt_table")
        if table:
            return IdtInfo(
                base=table,
                limit=0xFFF,
                source="idt_table",
            )
        return None

    def entry(self, index: int, info: IdtInfo | None = None) -> IdtEntry | None:
        """Read and decode gate *index* from the live IDT."""
        info = info or self.idt()
        if info is None or index < 0 or index >= info.count:
            return None
        address = (info.base + index * IDT_GATE_SIZE) & _MASK64
        low = self._reader.u64(f"*(unsigned long *){address:#x}")
        high = self._reader.u64(f"*(unsigned long *){address + 8:#x}")
        if low is None or high is None:
            return None
        return IdtEntry(
            index=index,
            address=address,
            offset=(
                (low & 0xFFFF)
                | (((low >> 48) & 0xFFFF) << 16)
                | ((high & 0xFFFFFFFF) << 32)
            ),
            selector=(low >> 16) & 0xFFFF,
            gate_type=(low >> 40) & 0x1F,
            ist=(low >> 32) & 0x7,
            dpl=(low >> 45) & 0x3,
            present=bool((low >> 47) & 1),
        )

    def entries(self, info: IdtInfo | None = None) -> tuple[IdtEntry, ...]:
        """Read every complete gate descriptor in the IDT."""
        info = info or self.idt()
        if info is None:
            return ()
        result: list[IdtEntry] = []
        for index in range(info.count):
            entry = self.entry(index, info)
            if entry is not None:
                result.append(entry)
        return tuple(result)

    # --- base recovery --------------------------------------------------

    def _base_from_symbol(
        self, entry: IdtEntry, link_text: int | None,
    ) -> tuple[int, str] | None:
        if link_text is None:
            return None
        for symbol in _IDT_SYMBOLS.get(entry.index, ()):
            link_handler = self._reader.u64(
                f"(unsigned long)&{symbol}"
            )
            if not link_handler:
                continue
            base = (link_text + entry.offset - link_handler) & _MASK64
            if self._plausible(base, entry.offset):
                return base, symbol
        return None

    def _base_from_mapping(self, handler: int) -> int | None:
        """Find the mapping containing *handler* via QEMU ``info mem``."""
        for command in ("monitor info mem", "info mem"):
            output = self._monitor(command)
            if not output:
                continue
            for line in output.splitlines():
                match = _MEM_MAP_RE.match(line)
                if match is None:
                    continue
                start = int(match.group(1), 16)
                end = int(match.group(2), 16)
                if start <= handler < end and self._plausible(
                    start, handler,
                ):
                    return start
        return None

    @staticmethod
    def _plausible(base: int, handler: int) -> bool:
        """Sanity-check a candidate text base."""
        if not KAddr.is_kernel(base):
            return False
        if base > handler:
            return False
        return handler - base <= _MAX_TEXT_SPAN

    def _result(
        self,
        base: int,
        entry: IdtEntry,
        info: IdtInfo,
        method: str,
        handler_symbol: str | None = None,
        link_text: int | None = None,
    ) -> KbaseResult:
        offset = (
            (base - link_text) & _MASK64
            if link_text is not None
            else None
        )
        return KbaseResult(
            base=base & _MASK64,
            handler=entry.offset,
            handler_symbol=handler_symbol,
            idt=info,
            method=method,
            link_text=link_text,
            kaslr_offset=offset,
        )

    def find(self) -> KbaseResult | None:
        """Recover the kernel text base, or ``None`` when unavailable."""
        info = self.idt()
        if info is None:
            return None
        link_text = self._reader.u64("(unsigned long)&_text")
        # Exception gates 0..31 are enough for KASLR recovery; avoid
        # reading all 256 entries (some kernels leave high gates sparse).
        for index in range(min(info.count, 32)):
            entry = self.entry(index, info)
            if entry is None or not entry.is_kernel_gate:
                continue
            from_symbol = self._base_from_symbol(entry, link_text)
            if from_symbol is not None:
                base, symbol = from_symbol
                return self._result(
                    base, entry, info, "symbol", symbol, link_text,
                )
            mapping = self._base_from_mapping(entry.offset)
            if mapping is not None:
                return self._result(
                    mapping, entry, info, "mapping", None, link_text,
                )
            aligned = entry.offset & ~(_TEXT_ALIGN - 1)
            if self._plausible(aligned, entry.offset):
                return self._result(
                    aligned, entry, info, "align", None, link_text,
                )
        return None

    def text_base(self) -> int | None:
        """Convenience wrapper returning only the base address."""
        result = self.find()
        return result.base if result is not None else None


__all__ = [
    "IdtEntry",
    "IdtInfo",
    "Kbase",
    "KbaseResult",
]