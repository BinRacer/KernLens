"""Unit tests for :mod:`kernlens.gdb.layouts`.

The registry holds the *fallback* struct layouts used when a kernel has
no debug info, so it imports no ``gdb``; these tests pin the values that
were read from a real Linux 6.1.134 (x86_64) ``vmlinux`` and exercise the
``CONFIG_*``/version gating.
"""

from __future__ import annotations

import unittest

from kernlens.gdb import layouts


class ParseVersionTests(unittest.TestCase):
    def test_banner(self) -> None:
        self.assertEqual(
            layouts.parse_version("Linux version 6.1.134 (gcc)"),
            (6, 1, 134),
        )

    def test_two_components(self) -> None:
        self.assertEqual(layouts.parse_version("Linux version 6.6"), (6, 6))

    def test_missing(self) -> None:
        self.assertIsNone(layouts.parse_version(None))
        self.assertIsNone(layouts.parse_version(""))
        self.assertIsNone(layouts.parse_version("no digits here"))


class RegistryLookupTests(unittest.TestCase):
    def test_known_type(self) -> None:
        self.assertIsNotNone(layouts.lookup("struct kmem_cache"))
        self.assertIn("struct bpf_map", layouts.type_names())

    def test_unknown_type(self) -> None:
        self.assertIsNone(layouts.lookup("struct not_a_struct"))
        self.assertIsNone(layouts.offset("struct not_a_struct", "field"))

    def test_offset_prefers_matching_config(self) -> None:
        # CONFIG_SECURITY inserts a `security` pointer before map_type.
        with_security = layouts.offset(
            "struct bpf_map", "map_type", (6, 1, 134),
            {"CONFIG_SECURITY": "y"},
        )
        without = layouts.offset(
            "struct bpf_map", "map_type", (6, 1, 134),
            {"CONFIG_SECURITY": "n"},
        )
        self.assertEqual(with_security, 0x40)
        self.assertEqual(without, 0x38)

    def test_offset_without_config_falls_back_to_first_variant(self) -> None:
        # No CONFIG data: the first variant that declares the field wins.
        self.assertEqual(
            layouts.offset("struct bpf_map", "map_type", None, {}), 0x40,
        )

    def test_sizeof(self) -> None:
        self.assertEqual(layouts.sizeof("struct zone", (7, 0, 0)), 0x6C0)
        self.assertEqual(layouts.sizeof("struct prb_desc"), 0x18)
        self.assertEqual(layouts.sizeof("struct printk_info"), 0x70)
        self.assertIsNone(layouts.sizeof("struct not_a_struct"))

    def test_sizeof_absent(self) -> None:
        # struct bpf_map has no recorded `sizeof`.
        self.assertIsNone(layouts.sizeof("struct bpf_map"))

    def test_describe(self) -> None:
        text = layouts.describe("struct kmem_cache")
        self.assertIn("struct kmem_cache", text)
        self.assertIn("include", text.replace("mm/", "include/"))


class VerifiedValueTests(unittest.TestCase):
    """Every value carries the kernel it was read from.

    Bands are ordered **newest first**, so the unversioned lookup (no
    debug info, no banner) returns the most recent layout instead of the
    oldest.  Each band is pinned against its own probe below.
    """

    def test_verified_kernel_marker_names_both_probes(self) -> None:
        self.assertIn("6.1.134", layouts.VERIFIED_KERNEL)
        self.assertIn("7.0", layouts.VERIFIED_KERNEL)

    def test_kmem_cache_7_0_band(self) -> None:
        # Host BTF, and the band the unversioned lookup must pick.
        entry = layouts.lookup("struct kmem_cache")
        assert entry is not None
        self.assertTrue(entry.variants[0].matches((7, 0, 0), None))
        self.assertEqual(
            dict(entry.variants[0].fields),
            {
                "name": 0x58, "size": 0x18, "object_size": 0x1C,
                "offset": 0x28, "oo": 0x30, "align": 0x4C,
                "flags": 0x08, "list": 0x60,
            },
        )

    def test_kmem_cache_6_1_band(self) -> None:
        # 6.1.134 DWARF: the four fields that moved after the reorder.
        self.assertEqual(
            layouts.offset("struct kmem_cache", "name", (6, 1, 134)),
            0x60,
        )
        self.assertEqual(
            layouts.offset("struct kmem_cache", "oo", (6, 1, 134)), 0x34,
        )
        self.assertEqual(
            layouts.offset("struct kmem_cache", "align", (6, 1, 134)),
            0x54,
        )
        self.assertEqual(
            layouts.offset("struct kmem_cache", "list", (6, 1, 134)),
            0x68,
        )

    def test_kmem_cache_versions_in_one_band_agree(self) -> None:
        # 6.6 and 6.12 share 6.1's layout, so one row describes all three.
        for version in ((6, 1, 134), (6, 6, 0), (6, 12, 0), (6, 17, 0)):
            self.assertEqual(
                layouts.offset("struct kmem_cache", "name", version), 0x60,
                version,
            )

    def test_kmem_cache_cpu_slab_band(self) -> None:
        # slub.py reads this slot to reach the per-CPU area; it is the
        # first member through 6.19 and gone at 7.0.
        for version in ((5, 19, 0), (6, 1, 134), (6, 17, 0), (6, 19, 0)):
            self.assertEqual(
                layouts.offset("struct kmem_cache", "cpu_slab", version),
                0x00, version,
            )
        self.assertIsNone(
            layouts.offset("struct kmem_cache", "cpu_slab", (7, 0, 0)),
        )

    def test_kmem_cache_cpu_band(self) -> None:
        # 6.1.134 DWARF; `slab` and `freelist` held those slots all through
        # 5.17-6.19, so the two bands differ only in provenance.
        for version in ((6, 1, 134), (6, 12, 0), (6, 19, 0)):
            self.assertEqual(
                layouts.offset("struct kmem_cache_cpu", "slab", version),
                0x10, version,
            )
            self.assertEqual(
                layouts.offset("struct kmem_cache_cpu", "freelist", version),
                0x00, version,
            )
        self.assertIsNone(
            layouts.offset("struct kmem_cache_cpu", "slab", (7, 0, 0)),
        )

    def test_kmem_cache_node_band(self) -> None:
        # 6.1.134 DWARF and 7.0 host BTF agree on both offsets.
        for version in ((6, 1, 134), (7, 0, 0)):
            self.assertEqual(
                layouts.offset(
                    "struct kmem_cache_node", "nr_partial", version,
                ),
                0x08, version,
            )
            self.assertEqual(
                layouts.offset("struct kmem_cache_node", "partial", version),
                0x10, version,
            )

    def test_node_row_needs_slub(self) -> None:
        # The SLUB branch of a dual CONFIG_SLAB/CONFIG_SLUB definition.
        self.assertIsNone(
            layouts.offset(
                "struct kmem_cache_node", "partial", (6, 1, 134),
                {"CONFIG_SLUB": "n"},
            ),
        )

    def test_dma_buf(self) -> None:
        entry = layouts.lookup("struct dma_buf")
        assert entry is not None
        fields = entry.variants[0].fields
        self.assertEqual(fields["priv"], 0x70)
        self.assertEqual(fields["exp_name"], 0x40)
        self.assertEqual(fields["list_node"], 0x60)

    def test_page_never_moved(self) -> None:
        for version in ((4, 19, 0), (6, 1, 134), (7, 0, 0)):
            self.assertEqual(
                layouts.offset("struct page", "lru", version), 0x08,
            )
            self.assertEqual(
                layouts.offset("struct page", "_mapcount", version), 0x30,
                version,
            )

    def test_slab_moved_at_6_2(self) -> None:
        # The bug this table had: one unversioned row said 0x08 everywhere.
        self.assertEqual(
            layouts.offset("struct slab", "slab_cache", (6, 1, 134)),
            0x18,
        )
        for version in ((6, 2, 0), (6, 6, 0), (7, 0, 0)):
            self.assertEqual(
                layouts.offset("struct slab", "slab_cache", version), 0x08,
                version,
            )

    def test_zone_size_is_banded(self) -> None:
        # The buddy walk strides by this, so a wrong value is not cosmetic.
        self.assertEqual(layouts.sizeof("struct zone", (6, 1, 134)), 0x600)
        self.assertEqual(layouts.sizeof("struct zone", (7, 0, 0)), 0x6C0)

    def test_zone_band_starts_where_the_member_list_changed(self) -> None:
        # 5.14 renamed `pageset` to `per_cpu_pageset`/`per_cpu_zonestats`, so
        # 5.14-6.3 share 6.1's layout and 6.1's size cannot speak for 5.13.
        self.assertEqual(layouts.sizeof("struct zone", (5, 14, 0)), 0x600)
        self.assertEqual(layouts.sizeof("struct zone", (6, 3, 0)), 0x600)

    def test_a_banded_size_is_not_answered_outside_its_bands(self) -> None:
        # 5.13 is below every band; the neighbouring band's stride must not
        # be handed out (a wrong stride is worse than none).
        self.assertIsNone(layouts.sizeof("struct zone", (5, 13, 0)))

    def test_printk_nested_paths(self) -> None:
        self.assertEqual(
            layouts.offset(
                "struct printk_ringbuffer", "desc_ring.descs",
            ),
            0x08,
        )
        self.assertEqual(
            layouts.offset(
                "struct printk_ringbuffer", "text_data_ring.data",
            ),
            0x38,
        )
        self.assertEqual(
            layouts.offset("struct prb_desc", "text_blk_lpos.begin"), 0x08,
        )


class VariantMatchingTests(unittest.TestCase):
    def test_version_bounds(self) -> None:
        variant = layouts.StructVariant(
            note="", fields={"x": 1},
            version_min=(5, 10), version_max=(6, 5),
        )
        self.assertTrue(variant.matches((6, 1, 0), {}))
        self.assertFalse(variant.matches((5, 9, 0), {}))
        self.assertFalse(variant.matches((6, 5, 0), {}))
        # An unknown version is treated as matching.
        self.assertTrue(variant.matches(None, {}))

    def test_config_predicates(self) -> None:
        variant = layouts.StructVariant(
            note="", fields={"x": 1},
            config=(("CONFIG_SECURITY", "y"), ("CONFIG_SMP", "n")),
        )
        self.assertTrue(
            variant.matches(None, {"CONFIG_SECURITY": "y"}),
        )
        self.assertFalse(variant.matches(None, {}))
        self.assertFalse(
            variant.matches(None, {"CONFIG_SECURITY": "y", "CONFIG_SMP": "y"}),
        )

    def test_exact_config_value(self) -> None:
        variant = layouts.StructVariant(
            note="", fields={"x": 1}, config=(("CONFIG_HZ", "250"),),
        )
        self.assertTrue(variant.matches(None, {"CONFIG_HZ": "250"}))
        self.assertFalse(variant.matches(None, {"CONFIG_HZ": "1000"}))


if __name__ == "__main__":
    unittest.main()