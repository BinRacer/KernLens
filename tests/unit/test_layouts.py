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
        self.assertEqual(layouts.sizeof("struct zone"), 0x6C0)
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
    """Every value was read from the BTF of a Linux 7.0.0-38 (x86_64)."""

    def test_verified_kernel_marker(self) -> None:
        self.assertIn("7.0", layouts.VERIFIED_KERNEL)

    def test_kmem_cache(self) -> None:
        entry = layouts.lookup("struct kmem_cache")
        assert entry is not None
        self.assertEqual(
            dict(entry.variants[0].fields),
            {
                "name": 0x58, "size": 0x18, "object_size": 0x1C,
                "offset": 0x28, "oo": 0x30, "align": 0x4C,
                "flags": 0x08, "list": 0x60,
            },
        )

    def test_dma_buf(self) -> None:
        entry = layouts.lookup("struct dma_buf")
        assert entry is not None
        fields = entry.variants[0].fields
        self.assertEqual(fields["priv"], 0x70)
        self.assertEqual(fields["exp_name"], 0x40)
        self.assertEqual(fields["list_node"], 0x60)

    def test_page_and_slab(self) -> None:
        self.assertEqual(layouts.offset("struct page", "lru"), 0x08)
        self.assertEqual(layouts.offset("struct page", "_mapcount"), 0x30)
        self.assertEqual(layouts.offset("struct slab", "slab_cache"), 0x08)

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