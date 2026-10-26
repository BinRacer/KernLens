"""Unit tests for :mod:`kernlens.core.fmt`."""

from __future__ import annotations

import unittest

from kernlens import BE, IntFmt


class IntegerFormatTests(unittest.TestCase):
    def test_addr(self) -> None:
        self.assertEqual(IntFmt.addr(0xFFFF888000000000),
                         "0xffff888000000000")
        self.assertEqual(IntFmt.addr(0x1234), "0x0000000000001234")
        self.assertEqual(IntFmt.addr(-1), "0xffffffffffffffff")

    def test_hex_variants(self) -> None:
        self.assertEqual(IntFmt.hex(0x1234), "0x1234")
        self.assertEqual(IntFmt.hex8(0x1234), "0x34")
        self.assertEqual(IntFmt.hex16(0x12345), "0x2345")
        self.assertEqual(IntFmt.hex32(0x1234), "0x00001234")
        self.assertEqual(IntFmt.hex64(0xDEADBEEF), "0x00000000deadbeef")

    def test_offset(self) -> None:
        self.assertEqual(
            IntFmt.off(0xFFFF888000001000, 0x40),
            "0xffff888000001000+0x40",
        )
        self.assertEqual(
            IntFmt.off(0xFFFF888000001000, -0x40),
            "0xffff888000001000-0x40",
        )
        self.assertEqual(IntFmt.field_off(0x10), "+0x10")
        self.assertEqual(IntFmt.field_off(-0x10), "-0x10")
        self.assertEqual(IntFmt.field_off(0), "+0x0")

    def test_size(self) -> None:
        self.assertEqual(IntFmt.size(0), "0")
        self.assertEqual(IntFmt.size(100), "100")
        self.assertEqual(IntFmt.size(1024), "1K")
        self.assertEqual(IntFmt.size(1536), "1.5K")
        self.assertEqual(IntFmt.size(10 * 1024), "10K")
        self.assertEqual(IntFmt.size(1024 * 1024), "1M")
        self.assertEqual(IntFmt.size(1024 * 1024 * 1024), "1G")
        self.assertEqual(IntFmt.size(1 << 40), "1T")
        self.assertEqual(IntFmt.size(1 << 20 | 1 << 19), "1.5M")
        # Rounding must carry into the next unit, not print 1024K/M/G.
        self.assertEqual(IntFmt.size((1 << 20) - 1), "1M")
        self.assertEqual(IntFmt.size((1 << 30) - 1), "1G")
        self.assertEqual(IntFmt.size((1 << 40) - 1), "1T")

    def test_pfn_and_page_offset(self) -> None:
        self.assertEqual(IntFmt.pfn(0x123456), "0x123")
        self.assertEqual(IntFmt.page_off(0x123456), "0x456")
        self.assertEqual(IntFmt.pfn(0x1000), "0x1")

    def test_mask_and_bits(self) -> None:
        self.assertEqual(IntFmt.mask(0b1010), "0b1010")
        self.assertEqual(IntFmt.bits(0b1010, 4), "1010")
        self.assertEqual(IntFmt.bits(0b1010, 8), "00001010")
        self.assertEqual(IntFmt.bits(0b1010, 0), "")

    def test_flags(self) -> None:
        self.assertEqual(
            IntFmt.flags(0x5, {0: "A", 2: "C"}), "0x5(A|C)",
        )
        self.assertEqual(IntFmt.flags(0x5, {}), "0x5")
        self.assertEqual(IntFmt.flags(0, {0: "A"}), "0x0")
        self.assertEqual(
            IntFmt.flags(0x7, {0: "A"}), "0x7(A|0x6)",
        )

    def test_percent(self) -> None:
        self.assertEqual(IntFmt.percent(1, 3), "33.3%")
        self.assertEqual(IntFmt.percent(1, 2), "50.0%")
        self.assertEqual(IntFmt.percent(0, 0), "?")

    def test_signed(self) -> None:
        self.assertEqual(IntFmt.signed(5), "+5")
        self.assertEqual(IntFmt.signed(-5), "-5")
        self.assertEqual(IntFmt.signed(0), "+0")
        self.assertEqual(IntFmt.signed_hex(5), "+0x5")
        self.assertEqual(IntFmt.signed_hex(-5), "-0x5")

    def test_timestamp(self) -> None:
        self.assertEqual(IntFmt.timestamp(123.456789), "[  123.456789]")

    def test_duration(self) -> None:
        self.assertEqual(IntFmt.duration_ns(0), "0ns")
        self.assertEqual(IntFmt.duration_ns(999), "999ns")
        self.assertEqual(IntFmt.duration_ns(1000), "1.00us")
        self.assertEqual(IntFmt.duration_ns(1500), "1.50us")
        self.assertEqual(IntFmt.duration_ns(1_000_000), "1.00ms")
        self.assertEqual(IntFmt.duration_ns(1_500_000_000), "1.50s")
        self.assertEqual(IntFmt.duration_ns(-1500), "-1.50us")


class ByteStringFormatTests(unittest.TestCase):
    def test_bytes_hex(self) -> None:
        self.assertEqual(IntFmt.bytes_hex(b"\xde\xad"), "de ad")
        self.assertEqual(IntFmt.bytes_hex(b""), "")
        self.assertEqual(IntFmt.bytes_hex(b"\xde\xad\xbe\xef", 2),
                         "de ad ...")

    def test_bytes_ascii(self) -> None:
        self.assertEqual(IntFmt.bytes_ascii(b"hello"), "hello")
        self.assertEqual(IntFmt.bytes_ascii(b"a\x00b"), "a.b")
        self.assertEqual(IntFmt.bytes_ascii(b"hello", 2), "he...")

    def test_bytes_cstring(self) -> None:
        self.assertEqual(IntFmt.bytes_cstring(b"hello\x00world"), "hello")
        self.assertEqual(IntFmt.bytes_cstring(b"hello"), "hello")
        self.assertEqual(IntFmt.bytes_cstring(b"\x00abc"), "")
        self.assertEqual(IntFmt.bytes_cstring(b"abc", 2), "ab")

    def test_bytes_hex_zero_limit_truncation(self) -> None:
        self.assertEqual(IntFmt.bytes_hex(b"abc", 0), "...")
        self.assertEqual(IntFmt.bytes_hex(b"abc", 1), "61 ...")

    def test_bytes_negative_limit(self) -> None:
        for formatter in (
            IntFmt.bytes_hex,
            IntFmt.bytes_ascii,
            IntFmt.bytes_cstring,
            IntFmt.bytes_dump,
        ):
            with self.assertRaises(ValueError):
                formatter(b"x", -1)

    def test_bytes_cstring_long_with_nul(self) -> None:
        # Regression: a NUL past the 64-byte default must not make the
        # ASCII formatter add an ellipsis.
        data = b"A" * 80 + b"\x00" + b"B" * 10
        self.assertEqual(IntFmt.bytes_cstring(data, 100), "A" * 80)

    def test_bytes_dump(self) -> None:
        out = IntFmt.bytes_dump(bytes(range(16)))
        self.assertTrue(out.startswith("00000000  "))
        self.assertTrue(out.endswith("|................|"))
        self.assertEqual(len(out.splitlines()), 1)

        out = IntFmt.bytes_dump(bytes(range(16)), base=0x1000)
        self.assertTrue(out.startswith("00001000  "))

    def test_bytes_dump_truncates(self) -> None:
        out = IntFmt.bytes_dump(bytes(range(20)), limit=8)
        lines = out.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].endswith("|........|"))
        self.assertEqual(lines[1], "... (12 more bytes)")

        out = IntFmt.bytes_dump(bytes(range(20)), limit=16)
        self.assertTrue(out.endswith("... (4 more bytes)"))

    def test_u16_array(self) -> None:
        self.assertEqual(
            IntFmt.bytes_u16_array(b"\x01\x00\x02\x00"),
            "0x0001 0x0002",
        )
        self.assertEqual(
            IntFmt.bytes_u16_array(b"\x01\x00\x02\x00", count=1),
            "0x0001",
        )
        self.assertEqual(
            IntFmt.bytes_u16_array(b"\x01\x00\x02\x00", byteorder=BE),
            "0x0100 0x0200",
        )

    def test_u32_array(self) -> None:
        self.assertEqual(
            IntFmt.bytes_u32_array(b"\x01\x00\x00\x00"),
            "0x00000001",
        )
        self.assertEqual(
            IntFmt.bytes_u32_array(b"\x00\x00\x00\x01", byteorder=BE),
            "0x00000001",
        )

    def test_u64_array(self) -> None:
        self.assertEqual(
            IntFmt.bytes_u64_array(b"\x01\x00\x00\x00\x00\x00\x00\x00"),
            "0x0000000000000001",
        )
        self.assertEqual(
            IntFmt.bytes_u64_array(
                b"\x00\x00\x00\x00\x00\x00\x00\x01", byteorder=BE,
            ),
            "0x0000000000000001",
        )


if __name__ == "__main__":
    unittest.main()