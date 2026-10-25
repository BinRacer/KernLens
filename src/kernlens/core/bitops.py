#!/usr/bin/env python3
#
# ruff: noqa: EXE001
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Byte-order-independent integer bit operations.

Public surface
--------------

:class:`BitOps`
    Stateless namespace of integer bit operations, all-static.  Method
    families cover byte swap, width reinterpretation, population and
    bit scanning, power-of-two, rotation, alignment, single-bit, bit
    field, and ``cpumask`` helpers.

:data:`BITS`
    Short alias for :class:`BitOps`.  Static methods work on both the
    class and any instance, so ``BITS.byte_swap32(...)`` and
    ``BitOps.byte_swap32(...)`` are equivalent.

Quick start
-----------

::

    from kernlens.core.bitops import BITS, BitOps

    BitOps.byte_swap32(0xdeadbeef)     # 0xefbeadde
    BitOps.popcount(0xff)              # 8
    BitOps.align_up(0x1234, 0x1000)    # 0x2000
    BitOps.extract_bits(0x12345678, 8, 8)  # 0x56
    BitOps.cpumask_test(0x5, 2)        # True

    BITS.to_i16(0x8000)                # -32768
"""

from __future__ import annotations

from typing import Final, final

from .codec import IntType
from .constants import PTR_BITS, PTR_MASK
from .validation import check_bits, check_nonneg, check_pow2

__all__ = [
    "BITS",
    "BitOps",
]


# ---------------------------------------------------------------------
# Bit operations
# ---------------------------------------------------------------------


@final
class BitOps:
    """Byte-order-independent integer bit operations, all-static.

    Every method is a :func:`staticmethod`; the class holds no state.
    Call through the class or through :data:`BITS`.

    Method families
    ---------------

    Byte swap::

        byte_swap(value, bits)  byte_swap16  byte_swap32  byte_swap64

    Width reinterpretation::

        sign_extend(value, bits)  truncate(value, bits)
        to_u8 / to_u16 / to_u32 / to_u64
        to_i8 / to_i16 / to_i32 / to_i64
        coerce(value, int_type)

    Width metadata::

        mask(bits)  sign_bit(bits)
        unsigned_range(bits)  signed_range(bits)

    Population / leading / trailing::

        popcount(value)  leading_zeros(value, bits=64)  trailing_zeros(value)
        first_set(value)  last_set(value)

    Power-of-two / logarithm::

        is_power_of_2(value)
        next_power_of_2(value)
        log2_floor(value)  log2_ceil(value)

    Rotation::

        rotate_left(value, shift, bits=64)  rotate_right(value, shift, bits=64)

    Alignment::

        align_up(value, alignment)  align_down(value, alignment)
        is_aligned(value, alignment)

    Single bit::

        bit_test / bit_set / bit_clear / bit_toggle

    Bit field::

        extract_bits / insert_bits / clear_bits

    ``cpumask``::

        cpumask_test  cpumask_count  cpumask_first  cpumask_next
    """

    __slots__: tuple[str, ...] = ()

    # --- byte swap ------------------------------------------------------

    @staticmethod
    def byte_swap(value: int, bits: int) -> int:
        """Swap the bytes of a ``bits``-wide integer.

        Raises
        ------
        ValueError
            If ``bits`` is not a positive multiple of 8.
        """
        if bits <= 0 or bits % 8 != 0:
            raise ValueError(
                f"bits must be a positive multiple of 8, got {bits}"
            )
        byte_len = bits // 8
        mask = (1 << bits) - 1
        value &= mask
        return int.from_bytes(value.to_bytes(byte_len, "little"), "big")

    @staticmethod
    def byte_swap16(value: int) -> int:
        """Swap the two bytes of a 16-bit value."""
        return BitOps.byte_swap(value, 16)

    @staticmethod
    def byte_swap32(value: int) -> int:
        """Swap the four bytes of a 32-bit value."""
        return BitOps.byte_swap(value, 32)

    @staticmethod
    def byte_swap64(value: int) -> int:
        """Swap the eight bytes of a 64-bit value."""
        return BitOps.byte_swap(value, 64)

    # --- width reinterpretation ----------------------------------------

    @staticmethod
    def sign_extend(value: int, bits: int) -> int:
        """Sign-extend the low ``bits`` bits of ``value``."""
        check_bits(bits)
        mask = (1 << bits) - 1
        value &= mask
        if value & (1 << (bits - 1)):
            return value - (1 << bits)
        return value

    @staticmethod
    def truncate(value: int, bits: int) -> int:
        """Keep the low ``bits`` bits of ``value``, discarding the rest."""
        check_bits(bits)
        return value & ((1 << bits) - 1)

    @staticmethod
    def to_u8(value: int) -> int:
        """Truncate ``value`` to an unsigned 8-bit integer."""
        return BitOps.truncate(value, 8)

    @staticmethod
    def to_u16(value: int) -> int:
        """Truncate ``value`` to an unsigned 16-bit integer."""
        return BitOps.truncate(value, 16)

    @staticmethod
    def to_u32(value: int) -> int:
        """Truncate ``value`` to an unsigned 32-bit integer."""
        return BitOps.truncate(value, 32)

    @staticmethod
    def to_u64(value: int) -> int:
        """Truncate ``value`` to an unsigned 64-bit integer."""
        return BitOps.truncate(value, 64)

    @staticmethod
    def to_i8(value: int) -> int:
        """Sign-extend ``value`` to a signed 8-bit integer."""
        return BitOps.sign_extend(value, 8)

    @staticmethod
    def to_i16(value: int) -> int:
        """Sign-extend ``value`` to a signed 16-bit integer."""
        return BitOps.sign_extend(value, 16)

    @staticmethod
    def to_i32(value: int) -> int:
        """Sign-extend ``value`` to a signed 32-bit integer."""
        return BitOps.sign_extend(value, 32)

    @staticmethod
    def to_i64(value: int) -> int:
        """Sign-extend ``value`` to a signed 64-bit integer."""
        return BitOps.sign_extend(value, 64)

    @staticmethod
    def coerce(value: int, int_type: IntType) -> int:
        """Coerce ``value`` to ``int_type``'s signedness and width."""
        if int_type.signed:
            return BitOps.sign_extend(value, int_type.bits)
        return BitOps.truncate(value, int_type.bits)

    # --- width metadata ------------------------------------------------

    @staticmethod
    def mask(bits: int) -> int:
        """Return the mask covering ``bits`` value bits."""
        check_bits(bits)
        return (1 << bits) - 1

    @staticmethod
    def sign_bit(bits: int) -> int:
        """Return the sign-bit mask for a ``bits``-wide signed value."""
        check_bits(bits)
        return 1 << (bits - 1)

    @staticmethod
    def unsigned_range(bits: int) -> tuple[int, int]:
        """Return the ``(min, max)`` range of an unsigned type."""
        check_bits(bits)
        return (0, (1 << bits) - 1)

    @staticmethod
    def signed_range(bits: int) -> tuple[int, int]:
        """Return the ``(min, max)`` range of a signed type."""
        check_bits(bits)
        return (-(1 << (bits - 1)), (1 << (bits - 1)) - 1)

    # --- population / leading / trailing --------------------------------

    @staticmethod
    def popcount(value: int) -> int:
        """Return the number of set bits in ``value``."""
        if value < 0:
            value &= PTR_MASK
        return bin(value).count("1")

    @staticmethod
    def leading_zeros(value: int, bits: int = PTR_BITS) -> int:
        """Return the number of leading zero bits in a ``bits``-wide value."""
        check_bits(bits)
        value &= (1 << bits) - 1
        if value == 0:
            return bits
        return bits - value.bit_length()

    @staticmethod
    def trailing_zeros(value: int) -> int:
        """Return the number of trailing zero bits; -1 if zero."""
        if value < 0:
            value &= PTR_MASK
        if value == 0:
            return -1
        return (value & -value).bit_length() - 1

    @staticmethod
    def first_set(value: int) -> int:
        """Return the 1-based index of the first set bit; 0 if none."""
        if value < 0:
            value &= PTR_MASK
        if value == 0:
            return 0
        return (value & -value).bit_length()

    @staticmethod
    def last_set(value: int) -> int:
        """Return the 1-based index of the last set bit; 0 if none."""
        if value < 0:
            value &= PTR_MASK
        return value.bit_length()

    # --- power-of-two / logarithm ---------------------------------------

    @staticmethod
    def is_power_of_2(value: int) -> bool:
        """Return ``True`` when ``value`` is a positive power of two."""
        return value > 0 and (value & (value - 1)) == 0

    @staticmethod
    def next_power_of_2(value: int) -> int:
        """Return the smallest power of two >= ``value``."""
        if value <= 0:
            return 1
        if value & (value - 1) == 0:
            return value
        return 1 << value.bit_length()

    @staticmethod
    def log2_floor(value: int) -> int:
        """Return ``floor(log2(value))``."""
        if value <= 0:
            raise ValueError(f"value must be positive, got {value}")
        return value.bit_length() - 1

    @staticmethod
    def log2_ceil(value: int) -> int:
        """Return ``ceil(log2(value))``."""
        if value <= 0:
            raise ValueError(f"value must be positive, got {value}")
        return (value - 1).bit_length()

    # --- rotation -------------------------------------------------------

    @staticmethod
    def rotate_left(value: int, shift: int, bits: int = PTR_BITS) -> int:
        """Rotate a ``bits``-wide value left by ``shift`` bits."""
        if bits <= 0 or bits % 8 != 0:
            raise ValueError(
                f"bits must be a positive multiple of 8, got {bits}"
            )
        mask = (1 << bits) - 1
        value &= mask
        shift %= bits
        if shift == 0:
            return value
        return ((value << shift) | (value >> (bits - shift))) & mask

    @staticmethod
    def rotate_right(value: int, shift: int, bits: int = PTR_BITS) -> int:
        """Rotate a ``bits``-wide value right by ``shift`` bits."""
        if bits <= 0 or bits % 8 != 0:
            raise ValueError(
                f"bits must be a positive multiple of 8, got {bits}"
            )
        mask = (1 << bits) - 1
        value &= mask
        shift %= bits
        if shift == 0:
            return value
        return ((value >> shift) | (value << (bits - shift))) & mask

    # --- alignment ------------------------------------------------------

    @staticmethod
    def align_up(value: int, alignment: int) -> int:
        """Round ``value`` up to the next multiple of ``alignment``."""
        check_pow2(alignment)
        masked = value & PTR_MASK
        if alignment == 1:
            return masked
        return (masked + alignment - 1) & ~(alignment - 1) & PTR_MASK

    @staticmethod
    def align_down(value: int, alignment: int) -> int:
        """Round ``value`` down to the previous multiple of ``alignment``."""
        check_pow2(alignment)
        masked = value & PTR_MASK
        if alignment == 1:
            return masked
        return masked & ~(alignment - 1)

    @staticmethod
    def is_aligned(value: int, alignment: int) -> bool:
        """Return ``True`` when ``value`` is a multiple of ``alignment``."""
        check_pow2(alignment)
        return (value & PTR_MASK & (alignment - 1)) == 0

    # --- single bit -----------------------------------------------------

    @staticmethod
    def bit_test(value: int, bit: int) -> bool:
        """Return ``True`` when bit ``bit`` is set in ``value``."""
        check_nonneg(bit, "bit")
        return bool((value >> bit) & 1)

    @staticmethod
    def bit_set(value: int, bit: int) -> int:
        """Return ``value`` with bit ``bit`` set."""
        check_nonneg(bit, "bit")
        return value | (1 << bit)

    @staticmethod
    def bit_clear(value: int, bit: int) -> int:
        """Return ``value`` with bit ``bit`` cleared."""
        check_nonneg(bit, "bit")
        return value & ~(1 << bit)

    @staticmethod
    def bit_toggle(value: int, bit: int) -> int:
        """Return ``value`` with bit ``bit`` toggled."""
        check_nonneg(bit, "bit")
        return value ^ (1 << bit)

    # --- bit field ------------------------------------------------------

    @staticmethod
    def extract_bits(value: int, shift: int, width: int) -> int:
        """Extract ``width`` bits from ``value`` starting at ``shift``."""
        check_nonneg(shift, "shift")
        if width <= 0:
            raise ValueError(f"width must be > 0, got {width}")
        return (value >> shift) & ((1 << width) - 1)

    @staticmethod
    def insert_bits(value: int, field: int, shift: int, width: int) -> int:
        """Insert the low ``width`` bits of ``field`` at ``shift``."""
        check_nonneg(shift, "shift")
        if width <= 0:
            raise ValueError(f"width must be > 0, got {width}")
        mask = ((1 << width) - 1) << shift
        return (value & ~mask) | ((field << shift) & mask)

    @staticmethod
    def clear_bits(value: int, shift: int, width: int) -> int:
        """Return ``value`` with ``width`` bits cleared starting at ``shift``."""
        check_nonneg(shift, "shift")
        if width <= 0:
            raise ValueError(f"width must be > 0, got {width}")
        mask = ((1 << width) - 1) << shift
        return value & ~mask

    # --- cpumask --------------------------------------------------------

    @staticmethod
    def cpumask_test(word: int, cpu: int) -> bool:
        """Return ``True`` when bit ``cpu`` is set in a 64-bit mask word."""
        check_nonneg(cpu, "cpu")
        return bool((word >> cpu) & 1)

    @staticmethod
    def cpumask_count(word: int) -> int:
        """Return the number of set CPUs in a 64-bit mask word."""
        return BitOps.popcount(word)

    @staticmethod
    def cpumask_first(word: int) -> int:
        """Return the first set CPU in a 64-bit mask word; -1 if empty."""
        return BitOps.trailing_zeros(word)

    @staticmethod
    def cpumask_next(word: int, prev_cpu: int) -> int:
        """Return the first set CPU strictly greater than ``prev_cpu``."""
        if prev_cpu < 0:
            mask = word & PTR_MASK
        else:
            mask = word & PTR_MASK & ~((1 << (prev_cpu + 1)) - 1)
        return BitOps.trailing_zeros(mask)


#: Short alias for :class:`BitOps`.
BITS: Final[BitOps] = BitOps()
