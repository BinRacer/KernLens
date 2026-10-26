"""Unit tests for ``tools/gen_layouts.py`` (the layout verifier).

Only the pure helpers are exercised: the two probes shell out to ``gdb``
and ``bpftool`` and are covered by the manual verification in the repo
notes, not by the unit suite.
"""

from __future__ import annotations

import unittest

from kernlens.gdb import layouts

import gen_layouts


class BuildSpecTests(unittest.TestCase):
    def test_covers_every_registry_type(self) -> None:
        spec = gen_layouts.build_spec()
        self.assertEqual(set(spec), set(layouts.type_names()))

    def test_paths_are_the_declared_fields(self) -> None:
        spec = gen_layouts.build_spec()
        self.assertIn("map_type", spec["struct bpf_map"])
        self.assertIn("desc_ring.descs", spec["struct printk_ringbuffer"])

    def test_paths_are_sorted_and_deduplicated(self) -> None:
        spec = gen_layouts.build_spec()
        for paths in spec.values():
            self.assertEqual(paths, sorted(set(paths)))


class CompareTests(unittest.TestCase):
    """A report that matches the registry produces no differences."""

    def _full_report(self) -> dict:
        report: dict = {}
        for entry in layouts.entries():
            paths = {
                path for v in entry.variants for path in v.fields
            }
            fields = {}
            for path in sorted(paths):
                value = layouts.offset(entry.type_name, path)
                if value is not None:
                    fields[path] = value
            item: dict = {"fields": fields}
            size = layouts.sizeof(entry.type_name)
            if size is not None:
                item["sizeof"] = size
            report[entry.type_name] = item
        return report

    def test_identical_report_matches(self) -> None:
        self.assertEqual(gen_layouts.compare(self._full_report()), [])

    def test_missing_struct_is_reported(self) -> None:
        report = self._full_report()
        del report["struct bpf_map"]
        diffs = gen_layouts.compare(report)
        self.assertTrue(any("struct bpf_map: not found" in d for d in diffs))

    def test_missing_field_is_reported(self) -> None:
        report = self._full_report()
        del report["struct dma_buf"]["fields"]["priv"]
        diffs = gen_layouts.compare(report)
        self.assertTrue(any("dma_buf.priv: not found" in d for d in diffs))

    def test_wrong_offset_is_reported(self) -> None:
        report = self._full_report()
        report["struct dma_buf"]["fields"]["priv"] = 0x10
        diffs = gen_layouts.compare(report)
        self.assertTrue(
            any("dma_buf.priv" in d and "0x10" in d for d in diffs)
        )

    def test_wrong_sizeof_is_reported(self) -> None:
        report = self._full_report()
        report["struct zone"]["sizeof"] = 0xC00
        diffs = gen_layouts.compare(report)
        self.assertTrue(any("sizeof(struct zone)" in d for d in diffs))

    def test_config_gates_the_expected_value(self) -> None:
        report = self._full_report()
        # A build with no LSM pointer has the map block 8 bytes lower.
        report["struct bpf_map"]["fields"].update(
            {"map_type": 0x38, "key_size": 0x3C,
             "value_size": 0x40, "max_entries": 0x44},
        )
        # With CONFIG_SECURITY=n the registry expects those, so it matches.
        self.assertEqual(
            gen_layouts.compare(report, None, {"CONFIG_SECURITY": "n"}), [],
        )
        # With CONFIG_SECURITY=y the registry expects 0x40-0x4c, so it differs.
        diffs = gen_layouts.compare(report, None, {"CONFIG_SECURITY": "y"})
        self.assertEqual(len(diffs), 4)


class RenderTests(unittest.TestCase):
    def test_renders_fields_and_size(self) -> None:
        report = {
            "struct demo": {"fields": {"b": 0x10, "a": 0x08}, "sizeof": 0x40},
        }
        text = gen_layouts.render(report)
        self.assertIn("'a': 0x8,", text)
        self.assertIn("'b': 0x10,", text)
        self.assertIn("sizeof = 0x40", text)

    def test_handles_a_missing_sizeof(self) -> None:
        text = gen_layouts.render({"struct demo": {"fields": {"a": 0}}})
        self.assertIn("'a': 0x0,", text)
        self.assertNotIn("sizeof", text)


class ParseBpftoolTests(unittest.TestCase):
    """The BTF names are bare, so the probe keys by the registry name."""

    SAMPLE = """\
[1] PTR '(anon)' type_id=3
[130103] STRUCT 'struct kmem_cache' size=8400 vlen=3
        'name' type_id=1 bits_offset=704
        'list' type_id=131192 bits_offset=768
        'flags' type_id=154050 bits_offset=64
[130104] STRUCT 'struct printk_ringbuffer' size=88 vlen=2
        'desc_ring' type_id=131200 bits_offset=384
        'text_data_ring' type_id=131210 bits_offset=384
[131200] STRUCT 'prb_desc_ring' size=48 vlen=1
        'descs' type_id=5 bits_offset=64
"""

    def test_bare_tag_name_resolves(self) -> None:
        spec = {"struct kmem_cache": ["name", "list", "flags"]}
        report = gen_layouts.parse_bpftool(self.SAMPLE, spec)
        self.assertEqual(
            report["struct kmem_cache"]["fields"],
            {"name": 0x58, "list": 0x60, "flags": 0x08},
        )
        self.assertEqual(report["struct kmem_cache"]["sizeof"], 8400)

    def test_nested_path_resolves(self) -> None:
        spec = {"struct printk_ringbuffer": ["desc_ring.descs"]}
        report = gen_layouts.parse_bpftool(self.SAMPLE, spec)
        # desc_ring @ 0x30, descs @ 0x08 inside it.
        self.assertEqual(
            report["struct printk_ringbuffer"]["fields"]["desc_ring.descs"],
            0x38,
        )

    def test_unknown_struct_is_skipped(self) -> None:
        report = gen_layouts.parse_bpftool(self.SAMPLE, {"struct nope": ["x"]})
        self.assertEqual(report, {})

    def test_unresolved_field_is_skipped(self) -> None:
        spec = {"struct kmem_cache": ["name", "not_a_field"]}
        report = gen_layouts.parse_bpftool(self.SAMPLE, spec)
        self.assertEqual(
            set(report["struct kmem_cache"]["fields"]), {"name"},
        )

    def test_takes_the_first_struct_of_a_duplicated_tag(self) -> None:
        sample = (
            "[1] STRUCT 'struct dup' size=8 vlen=1\n"
            "        'a' type_id=1 bits_offset=0\n"
            "[2] STRUCT 'struct dup' size=16 vlen=1\n"
            "        'a' type_id=1 bits_offset=64\n"
        )
        report = gen_layouts.parse_bpftool(sample, {"struct dup": ["a"]})
        self.assertEqual(report["struct dup"]["fields"]["a"], 0x0)
        self.assertEqual(report["struct dup"]["sizeof"], 8)


class CliTests(unittest.TestCase):
    def test_requires_a_source(self) -> None:
        with self.assertRaises(SystemExit):
            gen_layouts._parse_args([])

    def test_sources_are_mutually_exclusive(self) -> None:
        with self.assertRaises(SystemExit):
            gen_layouts._parse_args(["--vmlinux", "a", "--btf", "b"])

    def test_load_config(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".config"
            path.write_text(
                "# comment\nCONFIG_SECURITY=y\nCONFIG_HZ=250\n",
                encoding="utf-8",
            )
            config = gen_layouts._load_config(str(path))
        self.assertEqual(config, {"CONFIG_SECURITY": "y", "CONFIG_HZ": "250"})

    def test_load_config_none(self) -> None:
        self.assertIsNone(gen_layouts._load_config(None))


if __name__ == "__main__":
    unittest.main()