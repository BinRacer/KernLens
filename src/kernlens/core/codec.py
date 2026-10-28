#!/usr/bin/env python3
#
# ruff: noqa: EXE001 RUF022
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Byte-order-aware integer <-> bytes codec.

Public surface
--------------

:class:`IntCodec`
    Byte-order-aware integer <-> bytes codec, all-static.  Every
    method takes ``byteorder`` as a trailing keyword with default
    ``ByteOrder.LE``.

:class:`ByteOrderCodec`
    View that binds one :class:`ByteOrder` to :class:`IntCodec`'s
    statics, giving the short ``LE.pack_u16(...)`` shorthand.

:data:`LE`, :data:`BE`
    Pre-built :class:`ByteOrderCodec` views.

:class:`ByteOrder`
    Enum of the two byte orders.

:class:`IntType`
    Enum of the eight integer types (4 widths x 2 signednesses).

Quick start
-----------

::

    from kernlens.core.codec import BE, ByteOrder, IntCodec, IntType, LE

    LE.pack_u16(0x1234)                        # b'\\x34\\x12'
    BE.pack_u16(0x1234)                        # b'\\x12\\x34'
    IntCodec.pack_u16(0x1234, ByteOrder.BE)    # same, explicit
    IntCodec.pack_array([1, 2], IntType.U32)
    # b'\\x01\\x00\\x00\\x00\\x02\\x00\\x00\\x00'
"""

from __future__ import annotations

import struct
from enum import Enum
from typing import Final, cast, final

__all__ = [
    "BE",
    "ByteOrder",
    "ByteOrderCodec",
    "IntCodec",
    "IntType",
    "LE",
]


# ---------------------------------------------------------------------
# Byte-order descriptor
# ---------------------------------------------------------------------


@final
class ByteOrder(Enum):
    """Struct format prefix for a given byte order.

    * :attr:`LE` -> ``"<"`` (little-endian)
    * :attr:`BE` -> ``">"`` (big-endian)
    """

    LE = "<"
    BE = ">"

    @property
    def prefix(self) -> str:
        """Return the struct format prefix character."""
        return self.value


# ---------------------------------------------------------------------
# Integer type descriptor
# ---------------------------------------------------------------------


@final
class IntType(Enum):
    """Integer type: a struct code paired with its byte width.

    Members are grouped by signedness and width::

        U8  U16  U32  U64      # unsigned, 1/2/4/8 bytes
        I8  I16  I32  I64      # signed,   1/2/4/8 bytes
    """

    U8 = ("B", 1)
    U16 = ("H", 2)
    U32 = ("I", 4)
    U64 = ("Q", 8)

    I8 = ("b", 1)
    I16 = ("h", 2)
    I32 = ("i", 4)
    I64 = ("q", 8)

    @property
    def code(self) -> str:
        """Return the struct format character (e.g. ``"H"``)."""
        return self.value[0]

    @property
    def width(self) -> int:
        """Return the encoded width in bytes (1, 2, 4 or 8)."""
        return self.value[1]

    @property
    def bits(self) -> int:
        """Return the encoded width in bits (8, 16, 32 or 64)."""
        return self.width * 8

    @property
    def signed(self) -> bool:
        """Return ``True`` for signed types, ``False`` for unsigned."""
        return self.code.islower()

    @property
    def mask(self) -> int:
        """Return the mask covering the type's value bits."""
        return (1 << self.bits) - 1

    @property
    def min_value(self) -> int:
        """Return the smallest value representable by this type."""
        if self.signed:
            return -(1 << (self.bits - 1))
        return 0

    @property
    def max_value(self) -> int:
        """Return the largest value representable by this type."""
        if self.signed:
            return (1 << (self.bits - 1)) - 1
        return self.mask


def _resolve_byteorder(
    byteorder: ByteOrder | ByteOrderCodec,
) -> ByteOrder:
    """Accept either a :class:`ByteOrder` or a bound codec view."""
    if isinstance(byteorder, ByteOrderCodec):
        return byteorder.byteorder
    return byteorder


def _fmt(
    int_type: IntType, byteorder: ByteOrder | ByteOrderCodec,
) -> str:
    """Return the struct format string for *int_type* in *byteorder*."""
    if int_type.width == 1:
        return int_type.code
    return _resolve_byteorder(byteorder).prefix + int_type.code


# ---------------------------------------------------------------------
# Integer codec (stateless namespace; byte order is a parameter)
# ---------------------------------------------------------------------


@final
class IntCodec:
    """Byte-order-aware integer <-> bytes codec, all-static."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def pack(
        value: int,
        int_type: IntType,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> bytes:
        """Pack *value* as *int_type* using *byteorder*."""
        return struct.pack(_fmt(int_type, byteorder), value)

    @staticmethod
    def unpack(
        data: bytes,
        int_type: IntType,
        offset: int = 0,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> int:
        """Unpack *int_type* from *data* at *offset* using *byteorder*."""
        return cast(
            int,
            struct.unpack_from(_fmt(int_type, byteorder), data, offset)[0],
        )

    @staticmethod
    def pack_u8(
        value: int,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> bytes:
        """Pack an unsigned 8-bit integer (byte order ignored)."""
        return IntCodec.pack(value, IntType.U8, byteorder)

    @staticmethod
    def pack_u16(
        value: int,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> bytes:
        """Pack an unsigned 16-bit integer."""
        return IntCodec.pack(value, IntType.U16, byteorder)

    @staticmethod
    def pack_u32(
        value: int,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> bytes:
        """Pack an unsigned 32-bit integer."""
        return IntCodec.pack(value, IntType.U32, byteorder)

    @staticmethod
    def pack_u64(
        value: int,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> bytes:
        """Pack an unsigned 64-bit integer."""
        return IntCodec.pack(value, IntType.U64, byteorder)

    @staticmethod
    def unpack_u8(
        data: bytes,
        offset: int = 0,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> int:
        """Unpack an unsigned 8-bit integer (byte order ignored)."""
        return IntCodec.unpack(data, IntType.U8, offset, byteorder)

    @staticmethod
    def unpack_u16(
        data: bytes,
        offset: int = 0,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> int:
        """Unpack an unsigned 16-bit integer."""
        return IntCodec.unpack(data, IntType.U16, offset, byteorder)

    @staticmethod
    def unpack_u32(
        data: bytes,
        offset: int = 0,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> int:
        """Unpack an unsigned 32-bit integer."""
        return IntCodec.unpack(data, IntType.U32, offset, byteorder)

    @staticmethod
    def unpack_u64(
        data: bytes,
        offset: int = 0,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> int:
        """Unpack an unsigned 64-bit integer."""
        return IntCodec.unpack(data, IntType.U64, offset, byteorder)

    @staticmethod
    def pack_i8(
        value: int,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> bytes:
        """Pack a signed 8-bit integer (byte order ignored)."""
        return IntCodec.pack(value, IntType.I8, byteorder)

    @staticmethod
    def pack_i16(
        value: int,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> bytes:
        """Pack a signed 16-bit integer."""
        return IntCodec.pack(value, IntType.I16, byteorder)

    @staticmethod
    def pack_i32(
        value: int,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> bytes:
        """Pack a signed 32-bit integer."""
        return IntCodec.pack(value, IntType.I32, byteorder)

    @staticmethod
    def pack_i64(
        value: int,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> bytes:
        """Pack a signed 64-bit integer."""
        return IntCodec.pack(value, IntType.I64, byteorder)

    @staticmethod
    def unpack_i8(
        data: bytes,
        offset: int = 0,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> int:
        """Unpack a signed 8-bit integer (byte order ignored)."""
        return IntCodec.unpack(data, IntType.I8, offset, byteorder)

    @staticmethod
    def unpack_i16(
        data: bytes,
        offset: int = 0,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> int:
        """Unpack a signed 16-bit integer."""
        return IntCodec.unpack(data, IntType.I16, offset, byteorder)

    @staticmethod
    def unpack_i32(
        data: bytes,
        offset: int = 0,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> int:
        """Unpack a signed 32-bit integer."""
        return IntCodec.unpack(data, IntType.I32, offset, byteorder)

    @staticmethod
    def unpack_i64(
        data: bytes,
        offset: int = 0,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> int:
        """Unpack a signed 64-bit integer."""
        return IntCodec.unpack(data, IntType.I64, offset, byteorder)

    @staticmethod
    def pack_array(
        values: list[int] | tuple[int, ...],
        int_type: IntType,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> bytes:
        """Pack a homogeneous sequence of integers as ``int_type``."""
        if int_type.width == 1:
            fmt = f"{len(values)}{int_type.code}"
        else:
            fmt = (
                f"{_resolve_byteorder(byteorder).prefix}"
                f"{len(values)}{int_type.code}"
            )
        return struct.pack(fmt, *values)

    @staticmethod
    def unpack_array(
        data: bytes,
        int_type: IntType,
        count: int,
        offset: int = 0,
        byteorder: ByteOrder | ByteOrderCodec = ByteOrder.LE,
    ) -> list[int]:
        """Unpack *count* consecutive values of *int_type* from *data*."""
        if count < 0:
            raise ValueError(f"count must be >= 0, got {count}")
        if int_type.width == 1:
            fmt = f"{count}{int_type.code}"
        else:
            fmt = (
                f"{_resolve_byteorder(byteorder).prefix}"
                f"{count}{int_type.code}"
            )
        return list(struct.unpack_from(fmt, data, offset))

    @staticmethod
    def is_in_range(value: int, int_type: IntType) -> bool:
        """Return ``True`` if *value* fits *int_type*'s value range."""
        return int_type.min_value <= value <= int_type.max_value


# ---------------------------------------------------------------------
# Byte-order view (shorthand for IntCodec statics)
# ---------------------------------------------------------------------


@final
class ByteOrderCodec:
    """Bind one :class:`ByteOrder` to :class:`IntCodec`'s statics."""

    __slots__: tuple[str, ...] = ("_byteorder",)

    def __init__(self, byteorder: ByteOrder) -> None:
        self._byteorder = byteorder

    @property
    def byteorder(self) -> ByteOrder:
        """Return the bound byte order."""
        return self._byteorder

    def pack(self, value: int, int_type: IntType) -> bytes:
        """Pack *value* as *int_type* using the bound byte order."""
        return IntCodec.pack(value, int_type, self._byteorder)

    def unpack(self, data: bytes, int_type: IntType, offset: int = 0) -> int:
        """Unpack *int_type* from *data* at *offset* using the bound byte order."""
        return IntCodec.unpack(data, int_type, offset, self._byteorder)

    def pack_u8(self, value: int) -> bytes:
        """Pack an unsigned 8-bit integer."""
        return IntCodec.pack_u8(value, self._byteorder)

    def pack_u16(self, value: int) -> bytes:
        """Pack an unsigned 16-bit integer."""
        return IntCodec.pack_u16(value, self._byteorder)

    def pack_u32(self, value: int) -> bytes:
        """Pack an unsigned 32-bit integer."""
        return IntCodec.pack_u32(value, self._byteorder)

    def pack_u64(self, value: int) -> bytes:
        """Pack an unsigned 64-bit integer."""
        return IntCodec.pack_u64(value, self._byteorder)

    def unpack_u8(self, data: bytes, offset: int = 0) -> int:
        """Unpack an unsigned 8-bit integer."""
        return IntCodec.unpack_u8(data, offset, self._byteorder)

    def unpack_u16(self, data: bytes, offset: int = 0) -> int:
        """Unpack an unsigned 16-bit integer."""
        return IntCodec.unpack_u16(data, offset, self._byteorder)

    def unpack_u32(self, data: bytes, offset: int = 0) -> int:
        """Unpack an unsigned 32-bit integer."""
        return IntCodec.unpack_u32(data, offset, self._byteorder)

    def unpack_u64(self, data: bytes, offset: int = 0) -> int:
        """Unpack an unsigned 64-bit integer."""
        return IntCodec.unpack_u64(data, offset, self._byteorder)

    def pack_i8(self, value: int) -> bytes:
        """Pack a signed 8-bit integer."""
        return IntCodec.pack_i8(value, self._byteorder)

    def pack_i16(self, value: int) -> bytes:
        """Pack a signed 16-bit integer."""
        return IntCodec.pack_i16(value, self._byteorder)

    def pack_i32(self, value: int) -> bytes:
        """Pack a signed 32-bit integer."""
        return IntCodec.pack_i32(value, self._byteorder)

    def pack_i64(self, value: int) -> bytes:
        """Pack a signed 64-bit integer."""
        return IntCodec.pack_i64(value, self._byteorder)

    def unpack_i8(self, data: bytes, offset: int = 0) -> int:
        """Unpack a signed 8-bit integer."""
        return IntCodec.unpack_i8(data, offset, self._byteorder)

    def unpack_i16(self, data: bytes, offset: int = 0) -> int:
        """Unpack a signed 16-bit integer."""
        return IntCodec.unpack_i16(data, offset, self._byteorder)

    def unpack_i32(self, data: bytes, offset: int = 0) -> int:
        """Unpack a signed 32-bit integer."""
        return IntCodec.unpack_i32(data, offset, self._byteorder)

    def unpack_i64(self, data: bytes, offset: int = 0) -> int:
        """Unpack a signed 64-bit integer."""
        return IntCodec.unpack_i64(data, offset, self._byteorder)

    def pack_array(
        self, values: list[int] | tuple[int, ...], int_type: IntType,
    ) -> bytes:
        """Pack a homogeneous sequence of integers as ``int_type``."""
        return IntCodec.pack_array(values, int_type, self._byteorder)

    def unpack_array(
        self, data: bytes, int_type: IntType, count: int, offset: int = 0,
    ) -> list[int]:
        """Unpack *count* consecutive values of *int_type* from *data*."""
        return IntCodec.unpack_array(data, int_type, count, offset, self._byteorder)

    def is_in_range(self, value: int, int_type: IntType) -> bool:
        """Return ``True`` if *value* fits *int_type*'s value range."""
        return IntCodec.is_in_range(value, int_type)


# ---------------------------------------------------------------------
# Pre-built views
# ---------------------------------------------------------------------

LE: Final[ByteOrderCodec] = ByteOrderCodec(ByteOrder.LE)
BE: Final[ByteOrderCodec] = ByteOrderCodec(ByteOrder.BE)
