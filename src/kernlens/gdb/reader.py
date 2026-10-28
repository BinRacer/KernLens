#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Safe, KASLR-aware GDB memory reads."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast, final

import gdb

from ._types import _IntConvertible
from .config import DebugConfig

#: Mask for a 64-bit value.
_MASK64 = 0xFFFFFFFFFFFFFFFF


@final
class MemoryReader:
    """Safe GDB memory reads.

    Every read tolerates unreadable addresses and returns ``None``
    instead of raising.  Breakpoint callbacks cannot tolerate
    exceptions, so ``None`` is the universal failure signal.

    KASLR-aware reads (``read_kvar`` / ``kvar_addr``) add
    ``config.kaslr_offset`` to the link-time symbol address before
    dereferencing; a bare ``gdb.parse_and_eval("*(&sym)")`` on a KASLR
    kernel hits the unmapped link-time address.

    The slide is *self-healing*: when it is unset the reader asks its
    recovery hook (the facade's IDT-based detector) for it, and when a
    read at the current slide fails it re-detects and retries.  A
    link-time read is tried last, because GDB may already carry the
    relocation (``add-symbol-file vmlinux <runtime>``).  Whenever the
    slide changes, the ``on_change`` hook fires so derived caches can be
    dropped; this is what makes the ported commands follow a KASLR
    change instead of requiring a manual ``kl-base``.
    """

    __slots__: tuple[str, ...] = (
        "_config", "_detect_failed", "_on_change", "_recover",
        "_recovering",
    )

    def __init__(self, config: DebugConfig) -> None:
        self._config: DebugConfig = config
        self._recover: Callable[[], int | None] | None = None
        self._on_change: Callable[[], None] | None = None
        self._recovering: bool = False
        self._detect_failed: bool = False

    # --- KASLR self-healing ---------------------------------------------

    def set_kaslr_hooks(
        self,
        recover: Callable[[], int | None] | None,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        """Install the KASLR auto-detection callbacks.

        *recover* returns the runtime slide (or ``None``); *on_change*
        runs whenever the slide changes so derived caches can be reset.
        """
        self._recover = recover
        self._on_change = on_change

    @property
    def kaslr_offset(self) -> int:
        """The KASLR slide currently applied to KASLR-aware reads."""
        return self._config.kaslr_offset

    def ensure_kaslr(self) -> int:
        """Return the slide, auto-detecting it once when unset."""
        if self._config.kaslr_offset:
            return self._config.kaslr_offset
        if self._detect_failed:
            return 0
        return self.redetect_kaslr()

    def redetect_kaslr(self, *, force: bool = False) -> int:
        """(Re)derive the slide from the live kernel.

        Returns the slide in effect afterwards: the freshly detected one,
        or the previous one when detection is unavailable/failed.  A
        failed detection is remembered so it is not retried on every
        read, unless *force* is set (the read-failure path).
        """
        if self._recovering or self._recover is None:
            return self._config.kaslr_offset
        if self._detect_failed and not force:
            return self._config.kaslr_offset
        self._recovering = True
        try:
            offset = self._recover()
        except Exception:  # noqa: BLE001 - a read must never raise
            offset = None
        finally:
            self._recovering = False
        if offset is None:
            self._detect_failed = True
            return self._config.kaslr_offset
        self._detect_failed = False
        offset &= _MASK64
        if offset != self._config.kaslr_offset:
            self._config.kaslr_offset = offset
            if self._on_change is not None:
                self._on_change()
        return offset

    def _readable(self, addr: int) -> bool:
        """Whether a pointer-sized word can be read at *addr*."""
        return self.u64(f"*(unsigned long *){addr:#x}") is not None

    # --- primitive reads ------------------------------------------------

    def u64(self, expr: str) -> int | None:
        """Evaluate a GDB expression as an int; ``None`` on failure."""
        try:
            value = gdb.parse_and_eval(expr)
            return int(cast(_IntConvertible, value))
        except (gdb.error, TypeError, ValueError):
            # GDB can represent an expression as a non-scalar Value
            # (for example with no inferior loaded); int() then raises
            # gdb.error instead of parse_and_eval() doing so.
            return None

    def read_kvar(
        self, name: str, type_name: str = "unsigned long",
    ) -> int | None:
        """Read a global variable at its KASLR-adjusted runtime address."""
        link = self.u64(f"(unsigned long)&{name}")
        if not link:
            return None
        offset = self.ensure_kaslr()
        value = self.u64(
            f"*({type_name} *){((link + offset) & _MASK64):#x}"
        )
        if value is not None:
            return value
        detected = self.redetect_kaslr(force=True)
        if detected != offset:
            value = self.u64(
                f"*({type_name} *){((link + detected) & _MASK64):#x}"
            )
            if value is not None:
                return value
        if offset:
            # GDB may already carry the relocation.
            return self.u64(f"*({type_name} *){link:#x}")
        return None

    def kvar_addr(self, name: str) -> int | None:
        """Return a global's runtime address, self-healing the slide."""
        link = self.u64(f"(unsigned long)&{name}")
        if not link:
            return None
        offset = self.ensure_kaslr()
        addr = (link + offset) & _MASK64
        if self._readable(addr):
            return addr
        detected = self.redetect_kaslr(force=True)
        if detected != offset:
            addr = (link + detected) & _MASK64
            if self._readable(addr):
                return addr
        if offset and self._readable(link):
            return link
        return addr

    def arg(self, name: str, reg: str) -> int | None:
        """Read a function argument by name or by SysV register."""
        for expr in (f"(unsigned long){name}", f"(unsigned long)${reg}"):
            value = self.u64(expr)
            if value is not None:
                return value
        return None

    def read_field(
        self, obj: int, type_name: str, path: str,
    ) -> int | None:
        """Read ``((type *)obj)->path`` as an int."""
        if not obj:
            return None
        return self.u64(f"(({type_name} *){obj})->{path}")

    def read_bytes(self, addr: int, size: int) -> bytes | None:
        """Read *size* raw bytes at *addr*; ``None`` on any failure.

        GDB's ``read_memory`` raises when any byte in the range is
        unmapped, so callers that walk a buffer must tolerate ``None``.
        """
        if size <= 0:
            return b""
        try:
            inferior = gdb.selected_inferior()
            return bytes(inferior.read_memory(addr, size))
        except (gdb.error, AttributeError, MemoryError, TypeError, ValueError):
            return None


__all__ = ["MemoryReader"]
