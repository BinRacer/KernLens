"""Unit tests for :mod:`kernlens.core.paging`."""

from __future__ import annotations

import unittest

from kernlens import KPageTable


class IndexAndSplitTests(unittest.TestCase):
    def test_indices_4_level(self) -> None:
        va = 0xFFFF888000001234
        self.assertEqual(KPageTable.pgd_index(va), 0x111)
        self.assertEqual(KPageTable.pud_index(va), 0)
        self.assertEqual(KPageTable.pmd_index(va), 0)
        self.assertEqual(KPageTable.pte_index(va), 1)
        self.assertEqual(KPageTable.page_offset(va), 0x234)

    def test_split_4(self) -> None:
        self.assertEqual(
            KPageTable.split_4(0xFFFF888000001234),
            (0x111, 0, 0, 1, 0x234),
        )
        self.assertEqual(
            KPageTable.split_4(0xFFFF800000001234),
            (0x100, 0, 0, 1, 0x234),
        )
        self.assertEqual(
            KPageTable.split(0xFFFF888000001234),
            KPageTable.split_4(0xFFFF888000001234),
        )

    def test_split_5(self) -> None:
        self.assertEqual(
            KPageTable.split_5(0xFFFF800000001234),
            (0x1FF, 0x100, 0, 0, 1, 0x234),
        )
        self.assertEqual(
            KPageTable.split_5(0xFFFF888000001234),
            (0x1FF, 0x111, 0, 0, 1, 0x234),
        )
        self.assertEqual(
            KPageTable.split(0xFFFF800000001234, five_level=True),
            KPageTable.split_5(0xFFFF800000001234),
        )

    def test_pgd_index_5_level(self) -> None:
        va = 0xFFFF800000001234
        self.assertEqual(KPageTable.pgd_index(va), 0x100)
        self.assertEqual(KPageTable.pgd_index(va, five_level=True), 0x1FF)
        self.assertEqual(KPageTable.p4d_index(va), 0x100)

    def test_split_errors(self) -> None:
        with self.assertRaises(ValueError):
            KPageTable.entry_addr(0xFFFF888000000000, -1)
        with self.assertRaises(ValueError):
            KPageTable.entry_addr(0xFFFF888000000000, 512)


class HugePageTests(unittest.TestCase):
    def test_split_2m_1g(self) -> None:
        self.assertEqual(
            KPageTable.split_2m(0xFFFF8880003FFFFF), (1, 0x1FFFFF),
        )
        self.assertEqual(
            KPageTable.split_1g(0xFFFF88807FFFFFFF), (1, 0x3FFFFFFF),
        )

    def test_huge_bases(self) -> None:
        self.assertEqual(
            KPageTable.huge_2m_base(0xFFFF8880003FFFFF),
            0xFFFF888000200000,
        )
        self.assertEqual(
            KPageTable.huge_1g_base(0xFFFF88807FFFFFFF),
            0xFFFF888040000000,
        )

    def test_alignment_predicates(self) -> None:
        self.assertTrue(KPageTable.is_2m_aligned(0xFFFF888000200000))
        self.assertFalse(KPageTable.is_2m_aligned(0xFFFF888000200001))
        self.assertTrue(KPageTable.is_1g_aligned(0xFFFF888040000000))
        self.assertFalse(KPageTable.is_1g_aligned(0xFFFF888040000001))


class CanonicalizeTests(unittest.TestCase):
    def test_4_level(self) -> None:
        self.assertEqual(
            KPageTable.canonicalize(0x0000800000001234),
            0xFFFF800000001234,
        )
        self.assertEqual(
            KPageTable.canonicalize(0x00007FFFFFFFFFFF),
            0x00007FFFFFFFFFFF,
        )

    def test_5_level(self) -> None:
        self.assertEqual(
            KPageTable.canonicalize(0x0080000000001234, five_level=True),
            0x0080000000001234,
        )
        self.assertEqual(
            KPageTable.canonicalize(0x0100000000000000, five_level=True),
            0xFF00000000000000,
        )
        self.assertEqual(
            KPageTable.canonicalize(0x00FFFFFFFFFFFFFF, five_level=True),
            0x00FFFFFFFFFFFFFF,
        )


class EntryAddressTests(unittest.TestCase):
    def test_entry_addr(self) -> None:
        self.assertEqual(
            KPageTable.entry_addr(0xFFFF888000000000, 1),
            0xFFFF888000000008,
        )
        self.assertEqual(
            KPageTable.entry_addr(0xFFFF888000001FFF, 1),
            0xFFFF888000001008,
        )

    def test_level_entry_addr(self) -> None:
        va = 0xFFFF888000001234
        base = 0xFFFF888000000000
        self.assertEqual(
            KPageTable.pgd_entry_addr(base, va), 0xFFFF888000000888,
        )
        self.assertEqual(
            KPageTable.p4d_entry_addr(base, va), 0xFFFF888000000888,
        )
        self.assertEqual(
            KPageTable.pud_entry_addr(base, va), base,
        )
        self.assertEqual(
            KPageTable.pmd_entry_addr(base, va), base,
        )
        self.assertEqual(
            KPageTable.pte_entry_addr(base, va), 0xFFFF888000000008,
        )
        self.assertEqual(
            KPageTable.pgd_entry_addr(base, va, five_level=True),
            0xFFFF888000000FF8,
        )

    def test_next_table(self) -> None:
        self.assertEqual(
            KPageTable.next_table(0x0000000000123067), 0x123000,
        )


class PteDecodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pte = 0x8000000000123067

    def test_bits(self) -> None:
        pte = self.pte
        self.assertTrue(KPageTable.pte_present(pte))
        self.assertTrue(KPageTable.pte_writable(pte))
        self.assertTrue(KPageTable.pte_user(pte))
        self.assertTrue(KPageTable.pte_accessed(pte))
        self.assertTrue(KPageTable.pte_dirty(pte))
        self.assertTrue(KPageTable.pte_nx(pte))
        self.assertFalse(KPageTable.pte_global(pte))
        self.assertFalse(KPageTable.pte_is_huge(pte))

    def test_phys_and_pfn(self) -> None:
        self.assertEqual(KPageTable.pte_phys(self.pte), 0x123000)
        self.assertEqual(KPageTable.pte_pfn(self.pte), 0x123)

    def test_flags(self) -> None:
        self.assertEqual(
            KPageTable.pte_flags(self.pte),
            ["P", "RW", "US", "A", "D", "NX"],
        )

    def test_global_and_huge(self) -> None:
        pte = self.pte | KPageTable.PTE_GLOBAL
        self.assertTrue(KPageTable.pte_global(pte))
        huge = self.pte | KPageTable.PTE_PS
        self.assertTrue(KPageTable.pte_is_huge(huge))

    def test_leaf_to_phys(self) -> None:
        self.assertEqual(
            KPageTable.pte_to_phys(self.pte, 0xFFFF888000001ABC),
            0x123ABC,
        )
        # A 2 MiB leaf must have a 2 MiB-aligned physical base.
        pmd_entry = 0x00000000002000E7
        self.assertEqual(
            KPageTable.pmd_to_phys(pmd_entry, 0xFFFF8880003FFFFF),
            0x003FFFFF,
        )
        # A 1 GiB leaf must have a 1 GiB-aligned physical base.
        pud_entry = 0x00000000400000E7
        self.assertEqual(
            KPageTable.pud_to_phys(pud_entry, 0xFFFF88807FFFFFFF),
            0x7FFFFFFF,
        )

    def test_make_pte(self) -> None:
        pte = KPageTable.make_pte(
            0x123000,
            KPageTable.PTE_PRESENT | KPageTable.PTE_RW | KPageTable.PTE_NX,
        )
        self.assertEqual(pte, 0x8000000000123003)
        self.assertEqual(
            KPageTable.make_pte(0x123FFF, 0),
            0x123000,
        )
        with self.assertRaises(ValueError):
            KPageTable.make_pte(-1)


class GeometryTests(unittest.TestCase):
    def test_constants(self) -> None:
        self.assertEqual(KPageTable.BITS_PER_LEVEL, 9)
        self.assertEqual(KPageTable.ENTRIES_PER_LEVEL, 512)
        self.assertEqual(KPageTable.ENTRY_SIZE, 8)
        self.assertEqual(KPageTable.PTE_SHIFT, 12)
        self.assertEqual(KPageTable.HUGE_2M_SHIFT, 21)
        self.assertEqual(KPageTable.HUGE_1G_SHIFT, 30)
        self.assertEqual(KPageTable.PGD_SHIFT_4, 39)
        self.assertEqual(KPageTable.PGD_SHIFT_5, 48)
        self.assertEqual(KPageTable.PTE_ADDR_MASK, 0x000FFFFFFFFFF000)
        self.assertEqual(KPageTable.PTE_NX, 1 << 63)


if __name__ == "__main__":
    unittest.main()