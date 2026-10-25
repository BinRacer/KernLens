"""Unit tests for :mod:`kernlens.core.bitops`."""

from __future__ import annotations

import unittest

from kernlens import BITS, BitOps, IntType


class ByteSwapTests(unittest.TestCase):
    def test_byte_swap_fixed_widths(self) -> None:
        self.assertEqual(BitOps.byte_swap16(0x1234), 0x3412)
        self.assertEqual(BitOps.byte_swap32(0xDEADBEEF), 0xEFBEADDE)
        self.assertEqual(
            BitOps.byte_swap64(0x0123456789ABCDEF),
            0xEFCDAB8967452301,
        )

    def test_byte_swap_masks_input(self) -> None:
        self.assertEqual(BitOps.byte_swap32(0x1_DEADBEEF), 0xEFBEADDE)

    def test_byte_swap_rejects_bad_width(self) -> None:
        for bits in (0, -8, 7, 12):
            with self.subTest(bits=bits):
                with self.assertRaises(ValueError):
                    BitOps.byte_swap(1, bits)


class WidthReinterpretationTests(unittest.TestCase):
    def test_sign_extend(self) -> None:
        self.assertEqual(BitOps.sign_extend(0x7FFF, 16), 0x7FFF)
        self.assertEqual(BitOps.sign_extend(0x8000, 16), -0x8000)
        self.assertEqual(BitOps.sign_extend(0xFFFF, 16), -1)
        self.assertEqual(BitOps.sign_extend(0x1FF, 8), -1)
        self.assertEqual(BitOps.sign_extend(0x80, 8), -128)

    def test_truncate_and_to_unsigned(self) -> None:
        self.assertEqual(BitOps.truncate(0x1234, 8), 0x34)
        self.assertEqual(BitOps.to_u8(-1), 0xFF)
        self.assertEqual(BitOps.to_u16(-1), 0xFFFF)
        self.assertEqual(BitOps.to_u32(-1), 0xFFFFFFFF)
        self.assertEqual(BitOps.to_u64(-1), 0xFFFFFFFFFFFFFFFF)

    def test_to_signed(self) -> None:
        self.assertEqual(BitOps.to_i8(0xFF), -1)
        self.assertEqual(BitOps.to_i16(0x8000), -0x8000)
        self.assertEqual(BitOps.to_i32(0xFFFFFFFF), -1)
        self.assertEqual(BitOps.to_i64(0xFFFFFFFFFFFFFFFF), -1)

    def test_coerce_uses_int_type(self) -> None:
        self.assertEqual(BitOps.coerce(0x1FF, IntType.U8), 0xFF)
        self.assertEqual(BitOps.coerce(0x80, IntType.I8), -128)
        self.assertEqual(BitOps.coerce(-1, IntType.U16), 0xFFFF)
        self.assertEqual(BitOps.coerce(0xFFFFFFFF, IntType.I32), -1)

    def test_bad_bit_widths(self) -> None:
        for bits in (0, -1, 65):
            with self.subTest(bits=bits):
                with self.assertRaises(ValueError):
                    BitOps.sign_extend(0, bits)
                with self.assertRaises(ValueError):
                    BitOps.truncate(0, bits)


class WidthMetadataTests(unittest.TestCase):
    def test_mask_and_sign_bit(self) -> None:
        self.assertEqual(BitOps.mask(1), 1)
        self.assertEqual(BitOps.mask(8), 0xFF)
        self.assertEqual(BitOps.mask(64), 0xFFFFFFFFFFFFFFFF)
        self.assertEqual(BitOps.sign_bit(1), 1)
        self.assertEqual(BitOps.sign_bit(8), 0x80)
        self.assertEqual(BitOps.sign_bit(64), 0x8000000000000000)

    def test_ranges(self) -> None:
        self.assertEqual(BitOps.unsigned_range(8), (0, 255))
        self.assertEqual(BitOps.signed_range(8), (-128, 127))
        self.assertEqual(
            BitOps.unsigned_range(64),
            (0, 0xFFFFFFFFFFFFFFFF),
        )
        self.assertEqual(
            BitOps.signed_range(64),
            (-0x8000000000000000, 0x7FFFFFFFFFFFFFFF),
        )


class ScanTests(unittest.TestCase):
    def test_popcount(self) -> None:
        self.assertEqual(BitOps.popcount(0), 0)
        self.assertEqual(BitOps.popcount(0xFF), 8)
        self.assertEqual(BitOps.popcount(0x8000000000000001), 2)
        self.assertEqual(BitOps.popcount(-1), 64)

    def test_leading_zeros(self) -> None:
        self.assertEqual(BitOps.leading_zeros(0), 64)
        self.assertEqual(BitOps.leading_zeros(1), 63)
        self.assertEqual(BitOps.leading_zeros(0x8000000000000000), 0)
        self.assertEqual(BitOps.leading_zeros(1, 8), 7)
        self.assertEqual(BitOps.leading_zeros(0, 8), 8)

    def test_trailing_first_last(self) -> None:
        self.assertEqual(BitOps.trailing_zeros(0), -1)
        self.assertEqual(BitOps.trailing_zeros(1), 0)
        self.assertEqual(BitOps.trailing_zeros(0x100), 8)
        self.assertEqual(BitOps.trailing_zeros(-1), 0)

        self.assertEqual(BitOps.first_set(0), 0)
        self.assertEqual(BitOps.first_set(1), 1)
        self.assertEqual(BitOps.first_set(0x100), 9)
        self.assertEqual(BitOps.first_set(-1), 1)

        self.assertEqual(BitOps.last_set(0), 0)
        self.assertEqual(BitOps.last_set(1), 1)
        self.assertEqual(BitOps.last_set(0x100), 9)
        self.assertEqual(BitOps.last_set(-1), 64)


class PowerOfTwoTests(unittest.TestCase):
    def test_is_power_of_2(self) -> None:
        self.assertFalse(BitOps.is_power_of_2(0))
        self.assertTrue(BitOps.is_power_of_2(1))
        self.assertTrue(BitOps.is_power_of_2(2))
        self.assertTrue(BitOps.is_power_of_2(1 << 63))
        self.assertFalse(BitOps.is_power_of_2(3))
        self.assertFalse(BitOps.is_power_of_2(-2))

    def test_next_power_of_2(self) -> None:
        self.assertEqual(BitOps.next_power_of_2(0), 1)
        self.assertEqual(BitOps.next_power_of_2(1), 1)
        self.assertEqual(BitOps.next_power_of_2(3), 4)
        self.assertEqual(BitOps.next_power_of_2(1024), 1024)
        self.assertEqual(BitOps.next_power_of_2(1025), 2048)

    def test_log2(self) -> None:
        self.assertEqual(BitOps.log2_floor(1), 0)
        self.assertEqual(BitOps.log2_floor(2), 1)
        self.assertEqual(BitOps.log2_floor(3), 1)
        self.assertEqual(BitOps.log2_floor(1024), 10)
        self.assertEqual(BitOps.log2_ceil(1), 0)
        self.assertEqual(BitOps.log2_ceil(2), 1)
        self.assertEqual(BitOps.log2_ceil(3), 2)
        self.assertEqual(BitOps.log2_ceil(1024), 10)

    def test_log2_rejects_non_positive(self) -> None:
        for value in (0, -1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    BitOps.log2_floor(value)
                with self.assertRaises(ValueError):
                    BitOps.log2_ceil(value)


class RotationTests(unittest.TestCase):
    def test_rotate_32(self) -> None:
        self.assertEqual(BitOps.rotate_left(0x12345678, 8, 32), 0x34567812)
        self.assertEqual(BitOps.rotate_right(0x12345678, 8, 32), 0x78123456)

    def test_rotate_64_masks_and_wraps_shift(self) -> None:
        self.assertEqual(
            BitOps.rotate_left(0x8000000000000001, 1),
            0x0000000000000003,
        )
        self.assertEqual(
            BitOps.rotate_right(0x0000000000000003, 1),
            0x8000000000000001,
        )
        self.assertEqual(BitOps.rotate_left(0x1234, 0, 16), 0x1234)
        self.assertEqual(BitOps.rotate_left(0x1234, 16, 16), 0x1234)

    def test_rotate_rejects_bad_width(self) -> None:
        for bits in (0, -8, 7):
            with self.subTest(bits=bits):
                with self.assertRaises(ValueError):
                    BitOps.rotate_left(0, 1, bits)
                with self.assertRaises(ValueError):
                    BitOps.rotate_right(0, 1, bits)


class AlignmentTests(unittest.TestCase):
    def test_align(self) -> None:
        self.assertEqual(BitOps.align_up(0x1234, 0x1000), 0x2000)
        self.assertEqual(BitOps.align_up(0x1000, 0x1000), 0x1000)
        self.assertEqual(BitOps.align_down(0x1FFF, 0x1000), 0x1000)
        self.assertEqual(BitOps.align_up(0x1234, 1), 0x1234)
        self.assertEqual(BitOps.align_down(0x1234, 1), 0x1234)
        self.assertTrue(BitOps.is_aligned(0x2000, 0x1000))
        self.assertFalse(BitOps.is_aligned(0x2001, 0x1000))

    def test_align_rejects_non_power_of_two(self) -> None:
        for alignment in (0, -1, 3, 6):
            with self.subTest(alignment=alignment):
                with self.assertRaises(ValueError):
                    BitOps.align_up(0, alignment)
                with self.assertRaises(ValueError):
                    BitOps.align_down(0, alignment)
                with self.assertRaises(ValueError):
                    BitOps.is_aligned(0, alignment)


class SingleBitTests(unittest.TestCase):
    def test_bit_ops(self) -> None:
        self.assertTrue(BitOps.bit_test(0b1010, 1))
        self.assertFalse(BitOps.bit_test(0b1010, 0))
        self.assertEqual(BitOps.bit_set(0, 3), 8)
        self.assertEqual(BitOps.bit_clear(0xFF, 3), 0xF7)
        self.assertEqual(BitOps.bit_toggle(0, 3), 8)
        self.assertEqual(BitOps.bit_toggle(8, 3), 0)

    def test_negative_bit_rejected(self) -> None:
        for method in (
            BitOps.bit_test, BitOps.bit_set,
            BitOps.bit_clear, BitOps.bit_toggle,
        ):
            with self.subTest(method=method.__name__):
                with self.assertRaises(ValueError):
                    method(0, -1)


class BitFieldTests(unittest.TestCase):
    def test_extract_insert_clear(self) -> None:
        self.assertEqual(BitOps.extract_bits(0x12345678, 8, 8), 0x56)
        self.assertEqual(BitOps.extract_bits(0x12345678, 0, 4), 0x8)
        self.assertEqual(BitOps.insert_bits(0, 0xAB, 8, 8), 0xAB00)
        self.assertEqual(
            BitOps.insert_bits(0xFFFFFFFF, 0x0, 8, 8), 0xFFFF00FF,
        )
        self.assertEqual(BitOps.clear_bits(0xFFFF, 8, 8), 0x00FF)

    def test_bad_field_arguments(self) -> None:
        with self.assertRaises(ValueError):
            BitOps.extract_bits(0, -1, 8)
        with self.assertRaises(ValueError):
            BitOps.insert_bits(0, 0, -1, 8)
        with self.assertRaises(ValueError):
            BitOps.clear_bits(0, -1, 8)
        for width in (0, -1):
            with self.subTest(width=width):
                with self.assertRaises(ValueError):
                    BitOps.extract_bits(0, 0, width)
                with self.assertRaises(ValueError):
                    BitOps.insert_bits(0, 0, 0, width)
                with self.assertRaises(ValueError):
                    BitOps.clear_bits(0, 0, width)


class CpumaskTests(unittest.TestCase):
    def test_cpumask(self) -> None:
        self.assertTrue(BitOps.cpumask_test(0b1010, 1))
        self.assertFalse(BitOps.cpumask_test(0b1010, 0))
        self.assertEqual(BitOps.cpumask_count(0b1010), 2)
        self.assertEqual(BitOps.cpumask_first(0b1010), 1)
        self.assertEqual(BitOps.cpumask_first(0), -1)
        self.assertEqual(BitOps.cpumask_next(0b1010, -1), 1)
        self.assertEqual(BitOps.cpumask_next(0b1010, 1), 3)
        self.assertEqual(BitOps.cpumask_next(0b1010, 3), -1)
        self.assertEqual(BitOps.cpumask_next(0, 0), -1)
        with self.assertRaises(ValueError):
            BitOps.cpumask_test(0, -1)


class AliasTests(unittest.TestCase):
    def test_bits_alias(self) -> None:
        self.assertIsInstance(BITS, BitOps)
        self.assertEqual(BITS.byte_swap32(0xDEADBEEF), 0xEFBEADDE)


if __name__ == "__main__":
    unittest.main()