"""Unit tests for :mod:`kernlens.core.addr`."""

from __future__ import annotations

import unittest

from kernlens import (
    KERNEL_BASE,
    KERNEL_BOTTOM,
    MAX_ERRNO,
    MODULE_END,
    MODULE_START,
    PAGE_OFFSET_BASE,
    PAGE_SIZE,
    USER_TOP,
    VMALLOC_END,
    VMALLOC_START,
    VMEMAP_BASE,
    KAddr,
)


class ClassificationTests(unittest.TestCase):
    def test_user_and_kernel(self) -> None:
        self.assertTrue(KAddr.is_user(0))
        self.assertTrue(KAddr.is_user(USER_TOP))
        self.assertFalse(KAddr.is_user(USER_TOP + 1))
        self.assertFalse(KAddr.is_user(-1))

        self.assertFalse(KAddr.is_kernel(KERNEL_BOTTOM - 1))
        self.assertTrue(KAddr.is_kernel(KERNEL_BOTTOM))
        self.assertTrue(KAddr.is_kernel(0xFFFF888000000000))
        self.assertTrue(KAddr.is_kernel(-1))

    def test_canonical_48_bit(self) -> None:
        self.assertTrue(KAddr.is_canonical(0))
        self.assertTrue(KAddr.is_canonical(USER_TOP))
        self.assertTrue(KAddr.is_canonical(KERNEL_BOTTOM))
        self.assertTrue(KAddr.is_canonical(0xFFFFFFFFFFFFFFFF))
        self.assertFalse(KAddr.is_canonical(0x0000800000000000))
        self.assertFalse(KAddr.is_canonical(0xFFFF7FFFFFFFFFFF))

    def test_canonical_57_bit(self) -> None:
        self.assertTrue(KAddr.is_canonical(0x00FFFFFFFFFFFFFF, 57))
        self.assertTrue(KAddr.is_canonical(0xFF00000000000000, 57))
        self.assertFalse(KAddr.is_canonical(0x0100000000000000, 57))
        self.assertFalse(KAddr.is_canonical(0xFEFFFFFFFFFFFFFF, 57))

    def test_canonical_rejects_bad_width(self) -> None:
        for bits in (0, 47, 49, 64):
            with self.subTest(bits=bits):
                with self.assertRaises(ValueError):
                    KAddr.is_canonical(0, bits)

    def test_direct_map_and_vmemmap(self) -> None:
        self.assertTrue(KAddr.is_direct_map(PAGE_OFFSET_BASE))
        self.assertTrue(
            KAddr.is_direct_map(PAGE_OFFSET_BASE + (1 << 46) - 1),
        )
        self.assertFalse(KAddr.is_direct_map(PAGE_OFFSET_BASE + (1 << 46)))
        self.assertTrue(
            KAddr.is_direct_map(0xFFFF888000000FFF, 0xFFFF888000000000, 0x1000),
        )
        self.assertFalse(
            KAddr.is_direct_map(0xFFFF888000001000, 0xFFFF888000000000, 0x1000),
        )

        self.assertTrue(KAddr.is_vmemmap(VMEMAP_BASE))
        self.assertTrue(KAddr.is_vmemmap(VMEMAP_BASE + (1 << 40) - 1))
        self.assertFalse(KAddr.is_vmemmap(VMEMAP_BASE + (1 << 40)))
        self.assertTrue(
            KAddr.is_vmemmap(0xFFFFEA0000001000, VMEMAP_BASE, 0x2000),
        )
        self.assertFalse(
            KAddr.is_vmemmap(0xFFFFEA0000002000, VMEMAP_BASE, 0x2000),
        )

    def test_vmalloc_and_module(self) -> None:
        self.assertTrue(KAddr.is_vmalloc(VMALLOC_START))
        self.assertTrue(KAddr.is_vmalloc(VMALLOC_END))
        self.assertFalse(KAddr.is_vmalloc(VMALLOC_START - 1))
        self.assertFalse(KAddr.is_vmalloc(VMALLOC_END + 1))

        self.assertTrue(KAddr.is_module(MODULE_START))
        self.assertTrue(KAddr.is_module(MODULE_END))
        self.assertFalse(KAddr.is_module(MODULE_START - 1))
        self.assertFalse(KAddr.is_module(MODULE_END + 1))

    def test_text(self) -> None:
        self.assertTrue(KAddr.is_text(KERNEL_BASE))
        self.assertTrue(KAddr.is_text(KERNEL_BASE + 0x1000))
        self.assertFalse(KAddr.is_text(KERNEL_BASE - 1))
        self.assertFalse(KAddr.is_text(MODULE_START))
        self.assertTrue(KAddr.is_text(0xFFFFFFFFA0000000, 0xFFFFFFFFA0000000))


class TranslationTests(unittest.TestCase):
    def test_virt_to_phys(self) -> None:
        self.assertEqual(
            KAddr.virt_to_phys(PAGE_OFFSET_BASE + 0x1000), 0x1000,
        )
        self.assertEqual(
            KAddr.virt_to_phys(0xFFFF888000001234), 0x1234,
        )
        with self.assertRaises(ValueError):
            KAddr.virt_to_phys(0)
        # Addresses above the direct map are not translatable by simple
        # subtraction: doing so wraps to a bogus huge physical address.
        with self.assertRaises(ValueError):
            KAddr.virt_to_phys(PAGE_OFFSET_BASE + (1 << 46))
        self.assertEqual(
            KAddr.virt_to_phys(PAGE_OFFSET_BASE + 0x1000, size=1 << 47),
            0x1000,
        )

    def test_phys_to_virt(self) -> None:
        self.assertEqual(
            KAddr.phys_to_virt(0x1000), PAGE_OFFSET_BASE + 0x1000,
        )
        self.assertEqual(KAddr.phys_to_virt(0), PAGE_OFFSET_BASE)
        with self.assertRaises(ValueError):
            KAddr.phys_to_virt(-1)

    def test_pfn_conversions(self) -> None:
        self.assertEqual(KAddr.phys_to_pfn(0x123456), 0x123)
        self.assertEqual(KAddr.pfn_to_phys(0x123), 0x123000)
        self.assertEqual(KAddr.phys_to_pfn(PAGE_SIZE - 1), 0)
        with self.assertRaises(ValueError):
            KAddr.phys_to_pfn(-1)
        with self.assertRaises(ValueError):
            KAddr.pfn_to_phys(-1)

    def test_phys_to_page(self) -> None:
        self.assertEqual(
            KAddr.phys_to_page(0x1000), 0xFFFFEA0000000040,
        )
        self.assertEqual(
            KAddr.phys_to_page(0x1000, 0xFFFFEA0000000000, 128),
            0xFFFFEA0000000080,
        )
        with self.assertRaises(ValueError):
            KAddr.phys_to_page(0x1000, page_size=0)
        with self.assertRaises(ValueError):
            KAddr.phys_to_page(-1)

    def test_virt_to_page(self) -> None:
        self.assertEqual(
            KAddr.virt_to_page(PAGE_OFFSET_BASE + 0x1000),
            0xFFFFEA0000000040,
        )

    def test_page_to_phys_roundtrip(self) -> None:
        page = KAddr.phys_to_page(0x123000)
        self.assertEqual(KAddr.page_to_phys(page), 0x123000)
        self.assertEqual(
            KAddr.page_to_phys(KAddr.phys_to_page(0x1000, VMEMAP_BASE, 128), page_size=128),
            0x1000,
        )

    def test_page_to_phys_rejects_below_vmemmap(self) -> None:
        with self.assertRaises(ValueError):
            KAddr.page_to_phys(0x1000)
        with self.assertRaises(ValueError):
            KAddr.page_to_phys(VMEMAP_BASE, page_size=0)

    def test_page_to_virt_roundtrip(self) -> None:
        page = KAddr.phys_to_page(0x5000)
        self.assertEqual(
            KAddr.page_to_virt(page), PAGE_OFFSET_BASE + 0x5000,
        )

    def test_page_alignment(self) -> None:
        self.assertEqual(KAddr.page_align(0x1234), 0x1000)
        self.assertEqual(KAddr.page_align(0x1000), 0x1000)
        self.assertEqual(KAddr.page_align(-1), 0xFFFFFFFFFFFFF000)
        self.assertEqual(KAddr.page_align_up(0x1234), 0x2000)
        self.assertEqual(KAddr.page_align_up(0x1000), 0x1000)
        self.assertEqual(KAddr.page_align_up(0), 0)


class KaslrTests(unittest.TestCase):
    def test_runtime_and_link(self) -> None:
        link = 0xFFFFFFFF81000000
        offset = 0x1E000000
        runtime = 0xFFFFFFFF9F000000
        self.assertEqual(KAddr.kaslr_runtime(link, offset), runtime)
        self.assertEqual(KAddr.kaslr_link(runtime, offset), link)
        self.assertEqual(KAddr.kaslr_runtime(-1, 1), 0)


class ErrPtrTests(unittest.TestCase):
    def test_encode_decode_all_errnos(self) -> None:
        for errno in range(1, MAX_ERRNO + 1):
            with self.subTest(errno=errno):
                ptr = KAddr.err_ptr(-errno)
                self.assertTrue(KAddr.is_err(ptr))
                self.assertEqual(KAddr.ptr_err(ptr), errno)

    def test_boundaries(self) -> None:
        self.assertTrue(KAddr.is_err(0xFFFFFFFFFFFFFFFF))
        self.assertTrue(KAddr.is_err(0xFFFFFFFFFFFFF001))
        self.assertFalse(KAddr.is_err(0xFFFFFFFFFFFFF000))
        self.assertFalse(KAddr.is_err(0))
        self.assertEqual(KAddr.err_ptr(-1), 0xFFFFFFFFFFFFFFFF)
        self.assertEqual(KAddr.err_ptr(-MAX_ERRNO), 0xFFFFFFFFFFFFF001)

    def test_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError):
            KAddr.ptr_err(0)
        for err in (0, 1, -MAX_ERRNO - 1):
            with self.subTest(err=err):
                with self.assertRaises(ValueError):
                    KAddr.err_ptr(err)


class TagTests(unittest.TestCase):
    def test_ptr_tags(self) -> None:
        addr = 0xFFFF888000001A5C
        self.assertEqual(KAddr.ptr_tag(addr), 0xA5C)
        self.assertEqual(KAddr.strip_tag(addr), 0xFFFF888000001000)
        self.assertEqual(KAddr.ptr_tag(addr, 0xF), 0xC)
        self.assertEqual(KAddr.strip_tag(addr, 0xF), 0xFFFF888000001A50)


if __name__ == "__main__":
    unittest.main()