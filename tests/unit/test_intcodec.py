"""Unit tests for :mod:`kernlens.core.codec`."""

from __future__ import annotations

import struct
import unittest

from kernlens import (
    BE,
    LE,
    ByteOrder,
    ByteOrderCodec,
    IntCodec,
    IntType,
)


class ByteOrderTests(unittest.TestCase):
    def test_prefix(self) -> None:
        self.assertEqual(ByteOrder.LE.prefix, "<")
        self.assertEqual(ByteOrder.BE.prefix, ">")

    def test_byte_order_codec_property(self) -> None:
        self.assertIs(LE.byteorder, ByteOrder.LE)
        self.assertIs(BE.byteorder, ByteOrder.BE)
        self.assertIsInstance(ByteOrderCodec(ByteOrder.BE), ByteOrderCodec)


class IntTypeTests(unittest.TestCase):
    def test_properties(self) -> None:
        expected = {
            IntType.U8: ("B", 1, 8, False),
            IntType.U16: ("H", 2, 16, False),
            IntType.U32: ("I", 4, 32, False),
            IntType.U64: ("Q", 8, 64, False),
            IntType.I8: ("b", 1, 8, True),
            IntType.I16: ("h", 2, 16, True),
            IntType.I32: ("i", 4, 32, True),
            IntType.I64: ("q", 8, 64, True),
        }
        for int_type, (code, width, bits, signed) in expected.items():
            with self.subTest(int_type=int_type):
                self.assertEqual(int_type.code, code)
                self.assertEqual(int_type.width, width)
                self.assertEqual(int_type.bits, bits)
                self.assertEqual(int_type.signed, signed)
                self.assertEqual(int_type.mask, (1 << bits) - 1)

    def test_value_bounds(self) -> None:
        self.assertEqual(IntType.U8.min_value, 0)
        self.assertEqual(IntType.U8.max_value, 255)
        self.assertEqual(IntType.I8.min_value, -128)
        self.assertEqual(IntType.I8.max_value, 127)
        self.assertEqual(IntType.U64.max_value, 0xFFFFFFFFFFFFFFFF)
        self.assertEqual(IntType.I64.min_value, -0x8000000000000000)
        self.assertEqual(IntType.I64.max_value, 0x7FFFFFFFFFFFFFFF)


class ScalarPackTests(unittest.TestCase):
    def test_pack_unsigned_little_endian(self) -> None:
        self.assertEqual(IntCodec.pack_u8(0xAB), b"\xab")
        self.assertEqual(IntCodec.pack_u16(0x1234), b"\x34\x12")
        self.assertEqual(
            IntCodec.pack_u32(0xDEADBEEF), b"\xef\xbe\xad\xde",
        )
        self.assertEqual(
            IntCodec.pack_u64(0x0123456789ABCDEF),
            b"\xef\xcd\xab\x89\x67\x45\x23\x01",
        )

    def test_pack_signed(self) -> None:
        self.assertEqual(IntCodec.pack_i8(-1), b"\xff")
        self.assertEqual(IntCodec.pack_i16(-2), b"\xfe\xff")
        self.assertEqual(IntCodec.pack_i32(-1), b"\xff\xff\xff\xff")
        self.assertEqual(
            IntCodec.pack_i64(-1), b"\xff" * 8,
        )

    def test_pack_big_endian(self) -> None:
        self.assertEqual(
            IntCodec.pack_u16(0x1234, ByteOrder.BE), b"\x12\x34",
        )
        self.assertEqual(
            IntCodec.pack_u32(0xDEADBEEF, ByteOrder.BE),
            b"\xde\xad\xbe\xef",
        )

    def test_pack_accepts_bound_codec(self) -> None:
        # ``LE`` / ``BE`` are ByteOrderCodec views, not ByteOrder members.
        self.assertEqual(IntCodec.pack_u16(0x1234, LE), b"\x34\x12")
        self.assertEqual(IntCodec.pack_u16(0x1234, BE), b"\x12\x34")
        self.assertEqual(IntCodec.pack_i32(-1, LE), b"\xff" * 4)
        self.assertEqual(IntCodec.unpack_u16(b"\x12\x34", 0, BE), 0x1234)
        self.assertEqual(IntCodec.unpack_i32(b"\xff" * 4, 0, BE), -1)

    def test_unpack_offsets(self) -> None:
        data = b"\x00\x01\x00\x02\x00\x03"
        self.assertEqual(IntCodec.unpack_u8(data), 0)
        self.assertEqual(IntCodec.unpack_u8(data, 1), 1)
        self.assertEqual(IntCodec.unpack_u16(data, 1), 0x0001)
        self.assertEqual(IntCodec.unpack_u16(data, 3), 0x0002)
        self.assertEqual(
            IntCodec.unpack_u16(data, 1, ByteOrder.BE), 0x0100,
        )
        self.assertEqual(IntCodec.unpack_u16(b"\x12\x34", 0, ByteOrder.BE),
                         0x1234)

    def test_unpack_signed(self) -> None:
        self.assertEqual(IntCodec.unpack_i8(b"\xff"), -1)
        self.assertEqual(IntCodec.unpack_i16(b"\xfe\xff"), -2)
        self.assertEqual(IntCodec.unpack_i32(b"\xff\xff\xff\xff"), -1)
        self.assertEqual(IntCodec.unpack_i64(b"\xff" * 8), -1)

    def test_pack_out_of_range(self) -> None:
        with self.assertRaises(struct.error):
            IntCodec.pack_u8(256)
        with self.assertRaises(struct.error):
            IntCodec.pack_i8(128)
        with self.assertRaises(struct.error):
            IntCodec.pack_u16(-1)

    def test_unpack_short_buffer(self) -> None:
        with self.assertRaises(struct.error):
            IntCodec.unpack_u32(b"\x00")


class ArrayTests(unittest.TestCase):
    def test_pack_array(self) -> None:
        self.assertEqual(
            IntCodec.pack_array([1, 2, 3], IntType.U32),
            b"\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00",
        )
        self.assertEqual(
            IntCodec.pack_array((1, 2), IntType.U16),
            b"\x01\x00\x02\x00",
        )
        self.assertEqual(
            IntCodec.pack_array([0xAB, 0xCD], IntType.U8),
            b"\xab\xcd",
        )
        self.assertEqual(IntCodec.pack_array([], IntType.U8), b"")

    def test_unpack_array(self) -> None:
        self.assertEqual(
            IntCodec.unpack_array(b"\x01\x00\x02\x00", IntType.U16, 2),
            [1, 2],
        )
        self.assertEqual(
            IntCodec.unpack_array(
                b"\x00\x01\x00\x02\x00\x03", IntType.U16, 2, 2,
            ),
            [0x0200, 0x0300],
        )
        self.assertEqual(
            IntCodec.unpack_array(b"\xab\xcd", IntType.U8, 2),
            [0xAB, 0xCD],
        )
        self.assertEqual(
            IntCodec.unpack_array(b"", IntType.U32, 0), [],
        )

    def test_unpack_array_rejects_negative_count(self) -> None:
        with self.assertRaises(ValueError):
            IntCodec.unpack_array(b"", IntType.U8, -1)

    def test_array_roundtrip(self) -> None:
        values = [0, 1, 0x7FFFFFFF, 0xFFFFFFFF]
        data = IntCodec.pack_array(values, IntType.U32)
        self.assertEqual(
            IntCodec.unpack_array(data, IntType.U32, len(values)),
            values,
        )


class RangeTests(unittest.TestCase):
    def test_is_in_range(self) -> None:
        self.assertTrue(IntCodec.is_in_range(0, IntType.U8))
        self.assertTrue(IntCodec.is_in_range(255, IntType.U8))
        self.assertFalse(IntCodec.is_in_range(256, IntType.U8))
        self.assertFalse(IntCodec.is_in_range(-1, IntType.U8))
        self.assertTrue(IntCodec.is_in_range(-1, IntType.I16))
        self.assertFalse(IntCodec.is_in_range(-32769, IntType.I16))
        self.assertFalse(IntCodec.is_in_range(32768, IntType.I16))


class ByteOrderCodecTests(unittest.TestCase):
    def test_scalars(self) -> None:
        self.assertEqual(LE.pack_u16(0x1234), b"\x34\x12")
        self.assertEqual(BE.pack_u16(0x1234), b"\x12\x34")
        self.assertEqual(BE.unpack_u16(b"\x12\x34"), 0x1234)
        self.assertEqual(LE.unpack_u32(b"\xef\xbe\xad\xde"), 0xDEADBEEF)

        self.assertEqual(LE.pack_u8(0xAB), b"\xab")
        self.assertEqual(LE.unpack_u8(b"\xab"), 0xAB)
        self.assertEqual(LE.pack_i16(-2), b"\xfe\xff")
        self.assertEqual(LE.unpack_i16(b"\xfe\xff"), -2)
        self.assertEqual(LE.pack_i64(-1), b"\xff" * 8)
        self.assertEqual(LE.unpack_i64(b"\xff" * 8), -1)
        self.assertEqual(BE.pack_i32(-1), b"\xff" * 4)
        self.assertEqual(BE.unpack_i32(b"\xff" * 4), -1)

    def test_arrays(self) -> None:
        self.assertEqual(
            LE.pack_array([1, 2], IntType.U32),
            b"\x01\x00\x00\x00\x02\x00\x00\x00",
        )
        self.assertEqual(
            BE.unpack_array(b"\x00\x00\x00\x01", IntType.U32, 1),
            [1],
        )
        self.assertEqual(
            LE.unpack_array(b"\x01\x00\x02\x00", IntType.U16, 2),
            [1, 2],
        )
        self.assertTrue(LE.is_in_range(255, IntType.U8))
        self.assertFalse(LE.is_in_range(256, IntType.U8))

    def test_generic_pack_unpack(self) -> None:
        self.assertEqual(LE.pack(-1, IntType.I16), b"\xff\xff")
        self.assertEqual(LE.unpack(b"\xff\xff", IntType.I16), -1)
        self.assertEqual(BE.pack(0x1234, IntType.U16), b"\x12\x34")
        self.assertEqual(BE.unpack(b"\x12\x34", IntType.U16), 0x1234)


if __name__ == "__main__":
    unittest.main()