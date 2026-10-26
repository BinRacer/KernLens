#!/usr/bin/env python3
#
# ruff: noqa: EXE001
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Pure integer- and byte-string formatting helpers.

Public surface
--------------

:class:`IntFmt`
    Stateless namespace, all-static.  Every method takes a plain
    ``int`` or ``bytes`` and returns a plain ``str``; nothing touches
    color, logging, or the address space.

Quick start
-----------

::

    from kernlens.core.fmt import IntFmt

    IntFmt.addr(0xffff888000000000)       # '0xffff888000000000'
    IntFmt.hex64(0xdeadbeef)              # '0x00000000deadbeef'
    IntFmt.size(1536)                     # '1.5K'
    IntFmt.flags(0x5, {0: "A", 2: "C"})   # '0x5(A|C)'
    IntFmt.bytes_hex(b"\\xde\\xad")       # 'de ad'
    IntFmt.bytes_dump(b"\\x00" * 8)       # hexdump block
"""

from __future__ import annotations

from typing import final

from .constants import PAGE_MASK, PAGE_SHIFT, PTR_HEX_DIGITS, PTR_MASK
from .validation import check_nonneg
from .codec import ByteOrder, ByteOrderCodec, IntCodec, IntType

__all__ = [
    "IntFmt",
]


# ---------------------------------------------------------------------
# Integer and byte-string formatting
# ---------------------------------------------------------------------


@final
class IntFmt:
    """Pure integer- and byte-string formatting helpers, all-static.

    Integer-to-string::

        addr / hex / hex8 / hex16 / hex32 / hex64
        size(nbytes)                 '1M', '1.5K', '100'
        pfn / page_off
        off(base, delta)             '0xBASE±0xDELTA'
        field_off(delta)             '+0xNN' / '-0xNN'
        mask(value)  bits(value, bits=8)
        flags(value, names)          '0xNN(A|B|...)'
        percent(num, den)  signed(value)  signed_hex(value)
        timestamp(seconds)  duration_ns(ns)

    Byte-string-to-string::

        bytes_hex(data, limit=64)        'de ad be ef'
        bytes_ascii(data, limit=64)      '....'
        bytes_cstring(data, limit=64)    ASCII up to the first NUL
        bytes_dump(data, limit=64, base=0)  hexdump block
        bytes_u16_array / bytes_u32_array / bytes_u64_array
    """

    __slots__: tuple[str, ...] = ()

    # --- integers -------------------------------------------------------

    @staticmethod
    def addr(value: int) -> str:
        """Format a 64-bit pointer as ``0x`` plus 16 hex digits."""
        return f"0x{value & PTR_MASK:0{PTR_HEX_DIGITS}x}"

    @staticmethod
    def hex(value: int) -> str:
        """Format a value as ``0x`` plus minimal hex digits."""
        return f"{value:#x}"

    @staticmethod
    def hex8(value: int) -> str:
        """Format the low 8 bits as ``0xNN``."""
        return f"{value & 0xFF:#04x}"

    @staticmethod
    def hex16(value: int) -> str:
        """Format the low 16 bits as ``0xNNNN``."""
        return f"{value & 0xFFFF:#06x}"

    @staticmethod
    def hex32(value: int) -> str:
        """Format the low 32 bits as ``0xNNNNNNNN``."""
        return f"{value & 0xFFFFFFFF:#010x}"

    @staticmethod
    def hex64(value: int) -> str:
        """Format the low 64 bits as ``0x`` plus 16 hex digits."""
        return f"{value & PTR_MASK:#018x}"

    @staticmethod
    def off(base: int, delta: int) -> str:
        """Format ``base`` plus or minus ``delta`` as ``0xBASE±0xDELTA``."""
        if delta >= 0:
            return f"{base:#x}+{delta:#x}"
        return f"{base:#x}-{-delta:#x}"

    @staticmethod
    def field_off(delta: int) -> str:
        """Format a struct field offset as ``+0xNN`` or ``-0xNN``."""
        if delta >= 0:
            return f"+{delta:#x}"
        return f"-{-delta:#x}"

    @staticmethod
    def size(nbytes: int) -> str:
        """Format a byte count with a K/M/G/T suffix."""
        for unit, shift in (("T", 40), ("G", 30), ("M", 20), ("K", 10)):
            if nbytes >= 1 << shift:
                whole = nbytes >> shift
                rem = nbytes & ((1 << shift) - 1)
                if rem == 0:
                    return f"{whole}{unit}"
                tenths = round(rem * 10 / (1 << shift))
                if tenths >= 10:
                    # Rounding must carry into the next unit instead of
                    # emitting e.g. "1024K" for (1 MiB - 1).
                    return IntFmt.size((whole + 1) << shift)
                if tenths == 0:
                    return f"{whole}{unit}"
                return f"{whole}.{tenths}{unit}"
        return str(nbytes)

    @staticmethod
    def pfn(addr: int) -> str:
        """Format the page frame number of a physical address."""
        return f"{addr >> PAGE_SHIFT:#x}"

    @staticmethod
    def page_off(addr: int) -> str:
        """Format the page-internal offset of a physical address."""
        return f"{addr & PAGE_MASK:#x}"

    @staticmethod
    def mask(value: int) -> str:
        """Format a mask as ``0b`` plus binary digits."""
        return f"{value:#b}"

    @staticmethod
    def bits(value: int, bits: int = 8) -> str:
        """Format the low *bits* bits of *value* as fixed-width binary."""
        if bits <= 0:
            return ""
        return f"{value & ((1 << bits) - 1):0{bits}b}"

    @staticmethod
    def flags(value: int, names: dict[int, str]) -> str:
        """Format a bitmask with named bits."""
        if not names:
            return f"{value:#x}"
        parts: list[str] = []
        remaining = value
        for bit, name in names.items():
            if value & (1 << bit):
                parts.append(name)
                remaining &= ~(1 << bit)
        if remaining:
            parts.append(f"{remaining:#x}")
        if not parts:
            return f"{value:#x}"
        return f"{value:#x}({'|'.join(parts)})"

    @staticmethod
    def percent(num: int, den: int) -> str:
        """Format ``num/den`` as a percentage with one decimal digit."""
        if den == 0:
            return "?"
        return f"{100.0 * num / den:.1f}%"

    @staticmethod
    def signed(value: int) -> str:
        """Format a signed value with an explicit leading ``+`` when >= 0."""
        return f"+{value}" if value >= 0 else str(value)

    @staticmethod
    def signed_hex(value: int) -> str:
        """Format a signed value as hex with an explicit sign."""
        if value >= 0:
            return f"+{value:#x}"
        return f"-{-value:#x}"

    @staticmethod
    def timestamp(seconds: float) -> str:
        """Format a monotonic timestamp like dmesg: ``'[  123.456789]'``."""
        return f"[{seconds:12.6f}]"

    @staticmethod
    def duration_ns(ns: int) -> str:
        """Format a nanosecond duration with a human-readable suffix."""
        if ns < 0:
            return f"-{IntFmt.duration_ns(-ns)}"
        if ns < 1_000:
            return f"{ns}ns"
        if ns < 1_000_000:
            return f"{ns / 1_000:.2f}us"
        if ns < 1_000_000_000:
            return f"{ns / 1_000_000:.2f}ms"
        return f"{ns / 1_000_000_000:.2f}s"

    # --- byte strings ---------------------------------------------------

    @staticmethod
    def bytes_hex(data: bytes, limit: int = 64) -> str:
        """Format a byte string as space-separated hex pairs."""
        check_nonneg(limit, "limit")
        length = min(len(data), limit)
        text = " ".join(f"{byte:02x}" for byte in data[:length])
        if len(data) > limit:
            text = f"{text} ..." if text else "..."
        return text

    @staticmethod
    def bytes_ascii(data: bytes, limit: int = 64) -> str:
        """Format a byte string as printable ASCII, ``'.'`` otherwise."""
        check_nonneg(limit, "limit")
        length = min(len(data), limit)
        text = "".join(
            chr(byte) if 32 <= byte < 127 else "." for byte in data[:length]
        )
        if len(data) > limit:
            text += "..."
        return text

    @staticmethod
    def bytes_cstring(data: bytes, limit: int = 64) -> str:
        """Format a byte string as a C string: stop at the first NUL."""
        check_nonneg(limit, "limit")
        length = min(len(data), limit)
        end = data.find(b"\x00", 0, length)
        if end < 0:
            end = length
        return IntFmt.bytes_ascii(data[:end], limit=end)

    @staticmethod
    def bytes_dump(data: bytes, limit: int = 64, base: int = 0) -> str:
        """Format a byte string as a hexdump block (16 bytes per line)."""
        check_nonneg(limit, "limit")
        length = min(len(data), limit)
        lines: list[str] = []
        for off in range(0, length, 16):
            chunk = data[off:min(off + 16, length)]
            lo = " ".join(f"{byte:02x}" for byte in chunk[:8])
            hi = " ".join(f"{byte:02x}" for byte in chunk[8:])
            hex_part = f"{lo:<23}  {hi:<23}"
            ascii_part = "".join(
                chr(byte) if 32 <= byte < 127 else "."
                for byte in chunk
            )
            lines.append(
                f"{base + off:08x}  {hex_part}  |{ascii_part}|"
            )
        if len(data) > limit:
            lines.append(f"... ({len(data) - limit} more bytes)")
        return "\n".join(lines)

    @staticmethod
    def bytes_u16_array(
        data: bytes,
        count: int | None = None,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> str:
        """Format *data* as space-separated unsigned 16-bit values."""
        value_count = len(data) // 2 if count is None else count
        vals = IntCodec.unpack_array(
            data, IntType.U16, value_count, 0, byteorder
        )
        return " ".join(f"{value:#06x}" for value in vals)

    @staticmethod
    def bytes_u32_array(
        data: bytes,
        count: int | None = None,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> str:
        """Format *data* as space-separated unsigned 32-bit values."""
        value_count = len(data) // 4 if count is None else count
        vals = IntCodec.unpack_array(
            data, IntType.U32, value_count, 0, byteorder
        )
        return " ".join(f"{value:#010x}" for value in vals)

    @staticmethod
    def bytes_u64_array(
        data: bytes,
        count: int | None = None,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> str:
        """Format *data* as space-separated unsigned 64-bit values."""
        value_count = len(data) // 8 if count is None else count
        vals = IntCodec.unpack_array(
            data, IntType.U64, value_count, 0, byteorder
        )
        return " ".join(f"{value:#018x}" for value in vals)
