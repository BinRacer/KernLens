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

#: How many times the first alignment may probe before giving up.
#:
#: Detection is a full IDT scan, and a session where it cannot work --
#: ``nokaslr``, an unreadable IDT, a target attached after the fact --
#: fails the same way every time.  Retrying it on every read turned one
#: command into two scans forever, which is what this bounds.  More than
#: one attempt is still worth it because the first commands of a session
#: can run while the inferior is still settling.
_ALIGN_ATTEMPTS = 3


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
        "_align_attempts", "_align_closed", "_config",
        "_on_change", "_recover", "_recovering",
    )

    def __init__(self, config: DebugConfig) -> None:
        self._config: DebugConfig = config
        self._recover: Callable[[], int | None] | None = None
        self._on_change: Callable[[], None] | None = None
        self._recovering: bool = False
        #: Probes spent on the first alignment of this session.
        self._align_attempts: int = 0
        #: The first alignment is over -- succeeded or gave up.  From then
        #: on a command reads the slide instead of probing for it.
        self._align_closed: bool = False

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
        """Align the slide once per session, then just read it.

        The first command that needs the slide probes for it, up to
        :data:`_ALIGN_ATTEMPTS` times, and every later command reads the
        answer.  When the probes are exhausted the alignment is *closed*
        with the slide at whatever it is, and no command probes again --
        ``kl-base`` is how a user re-opens it, because that is the command
        a user reaches for when they believe a base is now knowable.

        The distinction that matters: this is a session-level latch, not a
        per-read cache.  A per-read cache still paid one probe per command
        in a session where detection could not succeed, and the earlier
        ``force`` path reset the failure memory on every read, so the cost
        never went away.
        """
        if self._config.kaslr_offset:
            self._align_closed = True
            return self._config.kaslr_offset
        if self._align_closed:
            return self._config.kaslr_offset
        while self._align_attempts < _ALIGN_ATTEMPTS:
            self._align_attempts += 1
            offset = self._probe()
            if offset:
                return offset
        # Out of attempts: close the alignment so the rest of the session
        # is free.  The slide stays whatever the last probe left, which is
        # zero for a kernel that genuinely has none.
        self._align_closed = True
        return self._config.kaslr_offset

    def reopen_alignment(self) -> int:
        """Forget the latch and align again (``kl-base`` calls this).

        Resetting the attempt count is what makes this a *retry* rather
        than an override: a user who fixed the reason detection failed gets
        the same three probes as a fresh session, and a user who did not
        gets three more rather than an unbounded loop.
        """
        self._align_closed = False
        self._align_attempts = 0
        return self.ensure_kaslr()

    def _probe(self) -> int:
        """Run the recovery hook once and record the outcome.

        Returns the slide on success and ``0`` on failure, so the caller
        can treat truthiness as "the probe worked".  A ``0`` return is
        also a legitimate answer -- a nokaslr kernel really has no slide --
        which is why the caller bounds the attempts rather than testing
        the value.
        """
        if self._recovering or self._recover is None:
            return 0
        self._recovering = True
        try:
            offset = self._recover()
        except Exception:  # noqa: BLE001 - a read must never raise
            offset = None
        finally:
            self._recovering = False
        if offset is None:
            return 0
        offset &= _MASK64
        if offset != self._config.kaslr_offset:
            self._config.kaslr_offset = offset
            if self._on_change is not None:
                self._on_change()
        return self._config.kaslr_offset

    def redetect_kaslr(self) -> int:
        """Probe the kernel for the slide, bypassing the latch once.

        The read-failure path uses this: a read that succeeded before and
        fails now means the slide moved (``kl-base --rebase``, a resumed
        VM), so one more probe is warranted even when the alignment is
        closed.  A successful probe re-opens nothing -- the slide is simply
        correct again.
        """
        offset = self._probe()
        if offset:
            self._align_closed = True
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
        detected = self.redetect_kaslr()
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
        detected = self.redetect_kaslr()
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
