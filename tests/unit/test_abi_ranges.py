"""Unit tests for ``tools/abi_ranges.py`` (the struct-ABI range deriver).

The derivation itself needs a linux-stable clone and is skipped when one
is absent, so a bare checkout still runs the suite.  What is asserted
here without the clone is the part that is easy to get wrong and that
everything else depends on:

* the preprocessor evaluator (:func:`condition_holds`), including the
  *direction* an unknown symbol takes -- the bug that first made this
  tool wrongly drop ``cpu_slab``;
* the member flattening (:func:`members`), including ``#elif`` taking
  over from a failed ``#ifdef``;
* the two facts the real 6.1.134 DWARF pins: the derived member list for
  ``struct slab`` at v6.1/absolutely matches, and the *order* that makes
  ``slab_cache`` land at 0x18 there and 0x8 from v6.2 on.
"""

from __future__ import annotations

import unittest

import abi_ranges


class ConditionTests(unittest.TestCase):
    """The evaluator decides which members exist, so its default matters."""

    def test_unknown_symbol_is_off(self) -> None:
        # The direction: a guarded member must not appear just because the
        # option is unlisted.  `#ifndef UNLISTED` is therefore *true*...
        self.assertTrue(abi_ranges.condition_holds(
            "!defined(UNLISTED_OPTION)", abi_ranges.DEFAULT_CONFIG,
        ))
        # ...and `#ifdef UNLISTED_OPTION` is false, so nothing is invented.
        self.assertFalse(abi_ranges.condition_holds(
            "defined(UNLISTED_OPTION)", abi_ranges.DEFAULT_CONFIG,
        ))

    def test_configured_symbols_are_respected(self) -> None:
        config = {"CONFIG_SLUB": "y", "CONFIG_SLAB": "n"}
        self.assertTrue(abi_ranges.condition_holds("CONFIG_SLUB", config))
        self.assertFalse(abi_ranges.condition_holds("CONFIG_SLAB", config))
        self.assertTrue(abi_ranges.condition_holds(
            "defined(CONFIG_SLUB) && !defined(CONFIG_SLAB)", config,
        ))

    def test_defined_of_an_unset_option_is_false(self) -> None:
        config = {"CONFIG_SLUB_TINY": "n"}
        self.assertFalse(abi_ranges.condition_holds(
            "defined(CONFIG_SLUB_TINY)", config,
        ))
        # `#ifndef CONFIG_SLUB_TINY` is the real 6.2 guard on cpu_slab.
        self.assertTrue(abi_ranges.condition_holds(
            "!defined(CONFIG_SLUB_TINY)", config,
        ))

    def test_a_nonsense_expression_is_false_not_an_exception(self) -> None:
        self.assertFalse(abi_ranges.condition_holds(
            "defined(CONFIG_X) && ???", abi_ranges.DEFAULT_CONFIG,
        ))


class MembersTests(unittest.TestCase):
    """Member extraction, including the branch rules that bit the draft."""

    def test_simple_members_in_order(self) -> None:
        body = "\n    unsigned long flags;\n    int count;\n"
        self.assertEqual(
            abi_ranges.members(body, {}), ("flags", "count"),
        )

    def test_ifdef_members_are_gated(self) -> None:
        body = (
            "    int always;\n"
            "#ifdef CONFIG_NUMA\n"
            "    int numa_only;\n"
            "#endif\n"
            "    int tail;\n"
        )
        self.assertEqual(
            abi_ranges.members(body, {}), ("always", "tail"),
        )
        self.assertEqual(
            abi_ranges.members(body, {"CONFIG_NUMA": "y"}),
            ("always", "numa_only", "tail"),
        )

    def test_elif_takes_over_when_the_first_branch_is_out(self) -> None:
        body = (
            "#if defined(CONFIG_SLAB)\n"
            "    int slab_way;\n"
            "#elif defined(CONFIG_SLUB)\n"
            "    int slub_way;\n"
            "#endif\n"
        )
        self.assertEqual(
            abi_ranges.members(body, {"CONFIG_SLUB": "y", "CONFIG_SLAB": "n"}),
            ("slub_way",),
        )
        self.assertEqual(
            abi_ranges.members(body, {"CONFIG_SLAB": "y"}),
            ("slab_way",),
        )

    def test_else_is_not_taken_when_a_branch_matched(self) -> None:
        body = (
            "#if defined(CONFIG_A)\n"
            "    int a_way;\n"
            "#else\n"
            "    int fallback;\n"
            "#endif\n"
        )
        self.assertEqual(
            abi_ranges.members(body, {"CONFIG_A": "y"}), ("a_way",),
        )
        self.assertEqual(
            abi_ranges.members(body, {}), ("fallback",),
        )

    def test_union_alternatives_all_appear(self) -> None:
        # A union is one slot; every alternative is a leaf of the same
        # offset, which is why the tool treats the list as an upper bound.
        body = (
            "    union {\n"
            "        struct list_head lru;\n"
            "        struct list_head buddy_list;\n"
            "        unsigned long private;\n"
            "    };\n"
        )
        self.assertEqual(
            abi_ranges.members(body, {}),
            ("lru", "buddy_list", "private"),
        )

    def test_nested_branches_respect_the_outer_condition(self) -> None:
        body = (
            "#ifdef CONFIG_SLUB\n"
            "#  ifdef CONFIG_SLUB_CPU_PARTIAL\n"
            "    int cpu_partial;\n"
            "#  endif\n"
            "#endif\n"
        )
        self.assertEqual(abi_ranges.members(body, {}), ())
        self.assertEqual(
            abi_ranges.members(
                body, {"CONFIG_SLUB": "y", "CONFIG_SLUB_CPU_PARTIAL": "y"},
            ),
            ("cpu_partial",),
        )
        self.assertEqual(
            abi_ranges.members(body, {"CONFIG_SLUB_CPU_PARTIAL": "y"}),
            (),
        )


class StructBodyTests(unittest.TestCase):
    """The body reader, so a union member cannot truncate the struct."""

    def test_body_stops_at_the_matching_brace(self) -> None:
        text = (
            "struct page {\n"
            "    unsigned long flags;\n"
            "    union { int a; int b; };\n"
            "};\n"
            "struct other { int x; };\n"
        )
        body = abi_ranges.struct_body(text, "struct page")
        self.assertIsNotNone(body)
        assert body is not None
        self.assertIn("flags", body)
        self.assertNotIn("struct other", body)

    def test_absent_struct_is_none(self) -> None:
        self.assertIsNone(abi_ranges.struct_body("int x;\n", "struct page"))


class VersionTests(unittest.TestCase):
    def test_version_of_a_release_tag(self) -> None:
        self.assertEqual(abi_ranges.version_of("v6.17"), (6, 17))
        self.assertEqual(abi_ranges.version_of("v3.0"), (3, 0))

    def test_tags_sort_by_number_not_text(self) -> None:
        tags = ["v6.9", "v6.10", "v5.17", "v7.3"]
        self.assertEqual(
            sorted(tags, key=abi_ranges.version_of),
            ["v5.17", "v6.9", "v6.10", "v7.3"],
        )


class SpanTests(unittest.TestCase):
    def test_label_hides_a_repeated_boundary(self) -> None:
        one = abi_ranges.Span(first="v7.0", last="v7.0", members=("a",))
        many = abi_ranges.Span(first="v7.1", last="v7.3", members=("a",))
        self.assertEqual(one.label(), "v7.0")
        self.assertEqual(many.label(), "v7.1 .. v7.3")

    def test_range_is_inclusive(self) -> None:
        span = abi_ranges.Span(first="v5.17", last="v6.1", members=())
        self.assertEqual(span.as_range(), ((5, 17), (6, 1)))


class GitBackedTests(unittest.TestCase):
    """Assertions that need a linux-stable clone; skipped without one.

    These pin what the derivation is for on the kernel the repo actually
    tests against: the member list at v6.1 and the ordering that fixes
    ``struct slab.slab_cache``.  The offsets themselves were measured
    from the 6.1.134 and 7.0 debug info (see the repo notes); this suite
    only checks the *source-derived* facts they depend on.
    """

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.repo = abi_ranges.default_repo(None)
        except SystemExit as exc:  # pragma: no cover - environment dependent
            raise unittest.SkipTest(str(exc)) from exc
        cls.tags = abi_ranges.release_tags(cls.repo)

    def test_the_clone_covers_the_releases_the_registry_claims(self) -> None:
        versions = {abi_ranges.version_of(tag) for tag in self.tags}
        for needed in ((5, 17), (6, 1), (6, 2), (7, 0)):
            self.assertIn(needed, versions)

    def test_slab_appears_at_5_17_and_not_before(self) -> None:
        spans = abi_ranges.derive(self.repo, "struct slab", self.tags)
        first = next(span for span in spans if span.members)
        self.assertEqual(first.first, "v5.17")

    def test_the_registry_slab_offsets_split_at_v6_2(self) -> None:
        # The order of the two fields is what the offsets follow:
        # list before cache -> cache is the second word (0x18 in 6.1);
        # cache before list -> cache is the first (0x8 from 6.2).
        order = {}
        for tag in ("v6.1", "v6.2", "v7.0"):
            members = abi_ranges.body_for(
                self.repo, tag, "struct slab", abi_ranges.TARGETS["struct slab"],
            )
            self.assertIn("slab_cache", members, tag)
            self.assertIn("slab_list", members, tag)
            order[tag] = (
                members.index("slab_cache") < members.index("slab_list")
            )
        self.assertFalse(order["v6.1"], "6.1 keeps slab_list first (0x18)")
        self.assertTrue(order["v6.2"], "6.2 moves slab_cache first (0x8)")
        self.assertTrue(order["v7.0"])

    def test_the_kmem_cache_band_covering_6_1_is_one_span(self) -> None:
        # 6.6 and 6.12 must land in the same span as 6.1, which is what
        # makes a single registry row enough for all three.
        members = {
            tag: abi_ranges.body_for(
                self.repo, tag, "struct kmem_cache",
                abi_ranges.TARGETS["struct kmem_cache"],
            )
            for tag in ("v6.1", "v6.6", "v6.12")
        }
        self.assertEqual(members["v6.1"], members["v6.6"])
        self.assertEqual(members["v6.1"], members["v6.12"])
        # ...and the first member changes at 6.18, so the row cannot run on.
        after = abi_ranges.body_for(
            self.repo, "v6.18", "struct kmem_cache",
            abi_ranges.TARGETS["struct kmem_cache"],
        )
        self.assertNotEqual(members["v6.1"], after)

    def test_free_area_never_changes(self) -> None:
        spans = abi_ranges.derive(self.repo, "struct free_area", self.tags)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].first, "v3.0")
        self.assertEqual(spans[0].last, "v7.3")

    def test_the_registry_is_told_it_needs_a_row_for_old_slab(self) -> None:
        spans = abi_ranges.derive(self.repo, "struct slab", self.tags)
        notes = abi_ranges.registry_notes("struct slab", spans[1], spans)
        self.assertTrue(
            any("need their own row" in note for note in notes), notes,
        )


if __name__ == "__main__":
    unittest.main()