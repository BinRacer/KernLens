#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Safe, KASLR-aware GDB memory reads."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class FieldValue:
    """One struct field, rendered without assuming it is an integer.

    ``read_field`` returns ``int | None``, which conflates "this field is
    not a scalar" with "this address is unreadable".  A live 6.1.134
    kernel showed the cost: ``task_struct::comm`` -- a ``char[16]``, and
    the field a reader most often wants -- came back as ``<unreadable>``
    while GDB printed ``"swapper/0"`` from the same address.

    Exactly one of :attr:`integer`, :attr:`string` and :attr:`text`
    carries the value; ``text`` is always the display form.
    """

    #: The display form.  ``None`` when the value could not be read.
    text: str | None
    #: The C type GDB reported, for context such as ``char [16]``.
    type_name: str
    #: The value when the field is a scalar or an address.
    integer: int | None = None
    #: The decoded text when the field is a NUL-terminated ``char[]``.
    string: str | None = None
    #: Pointer fields keep their numeric form rather than dereferencing.
    is_pointer: bool = False
    #: Element count for an array, ``None`` for anything else.
    length: int | None = None


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
        """Read ``((type *)obj)->path`` as an int.

        Only meaningful for a field whose value *is* an integer.  A
        ``char[]``, a struct and a float all fail here and come back as
        ``None``, which is indistinguishable from an unreadable address;
        :meth:`field_value` is the general form and is what the command
        uses.
        """
        if not obj:
            return None
        return self.u64(f"(({type_name} *){obj})->{path}")

    def field_value(
        self, obj: int, type_name: str, path: str,
    ) -> "FieldValue | None":
        """Read ``((type *)obj)->path`` whatever its type is.

        The integer form above silently returned ``None`` for anything
        that is not a scalar, so the most useful field in the kernel --
        ``task_struct::comm``, a ``char[16]`` -- was reported as
        ``<unreadable>`` on a live 6.1.134 kernel while GDB itself read
        ``"swapper/0"`` from the same address.  The caller had no way to
        tell "no such field" from "wrong kind of value".

        Returns ``None`` only when the expression cannot be evaluated at
        all.  Arrays are rendered as text (a ``char[]`` that is NUL
        terminated) or as a byte count, and pointers, structs and floats
        keep their rendered form, so a caller can always show something
        truthful.
        """
        if not obj:
            return None
        try:
            value = gdb.parse_and_eval(f"(({type_name} *){obj})->{path}")
        except (gdb.error, TypeError, ValueError):
            return None
        return self._describe(value)

    def _describe(self, value: "gdb.Value") -> "FieldValue":
        """Render one GDB value without ever raising."""
        type_name = str(value.type)
        code = getattr(value.type, "code", None)
        # A pointer is an address, not the thing it points at: keeping it
        # numeric is what makes `->mm` readable as 0x0 instead of a
        # struct dump of whatever happens to live at address zero.
        if code == gdb.TYPE_CODE_PTR:
            address = self._as_int(value)
            return FieldValue(
                text=None if address is None else f"{address:#x}",
                integer=address,
                type_name=type_name,
                is_pointer=True,
            )
        if code in (gdb.TYPE_CODE_INT, gdb.TYPE_CODE_ENUM, gdb.TYPE_CODE_BOOL):
            integer = self._as_int(value)
            return FieldValue(
                text=None if integer is None else f"{integer:#x}",
                integer=integer,
                type_name=type_name,
            )
        if code == gdb.TYPE_CODE_ARRAY:
            return self._describe_array(value, type_name)
        # Structs, unions, floats, functions: keep GDB's own rendering.
        try:
            text = str(value)
        except (gdb.error, ValueError):
            text = "<unreadable>"
        return FieldValue(text=text, type_name=type_name)

    @staticmethod
    def _as_int(value: "gdb.Value") -> int | None:
        try:
            return int(cast(_IntConvertible, value)) & _MASK64
        except (gdb.error, TypeError, ValueError):
            return None

    def _describe_array(self, value: "gdb.Value", type_name: str) -> "FieldValue":
        """A ``char[]`` becomes its string; any other array, its length.

        Only a one-byte element type can be a string, and only when the
        element is an integer -- a ``struct list_head[4]`` is not text.
        """
        try:
            length = int(value.type.sizeof) // max(
                int(value.type.target().sizeof), 1,
            )
        except (gdb.error, TypeError, ValueError, AttributeError):
            length = 0
        element = value.type.target()
        address = value.address
        if (
            getattr(element, "code", None) == gdb.TYPE_CODE_INT
            and int(element.sizeof) == 1
            and address is not None
        ):
            try:
                raw = bytes(gdb.selected_inferior().read_memory(
                    int(address), int(value.type.sizeof),
                ))
            except (gdb.error, AttributeError, MemoryError, TypeError, ValueError):
                raw = None
            if raw is not None:
                # Drop the padding after the terminator: a `char[16]`
                # holding "swapper/0" is 16 bytes of mostly NULs.
                text = raw.split(b"\x00", 1)[0].decode("utf-8", "replace")
                return FieldValue(
                    text=text,
                    type_name=type_name,
                    string=text,
                    length=length,
                )
        return FieldValue(
            text=f"{type_name} ({length} element(s))",
            type_name=type_name,
            length=length,
        )

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


__all__ = ["FieldValue", "MemoryReader"]
