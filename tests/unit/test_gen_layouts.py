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


class ProbeBtfTests(unittest.TestCase):
    """``--btf`` reads a blob with the project's own parser.

    This is what makes the tool usable on CI: the Ubuntu ``bpftool``
    package installs a wrapper that dispatches to a per-kernel tools
    package and fails on a cloud runner, and the project already has a
    self-contained parser (no ``bpftool``, no ``libbpf``).
    """

    def test_absent_file_raises(self) -> None:
        with self.assertRaises(OSError):
            gen_layouts.probe_btf("/nonexistent/btf")

    def test_resolves_a_direct_member(self) -> None:
        import tempfile

        from kernlens.gdb import btf

        blob = _make_btf(
            {"struct kmem_cache": 0x2100},
            {"struct kmem_cache": [("flags", 5, 0)]},
        )
        with tempfile.NamedTemporaryFile(suffix=".btf") as handle:
            handle.write(blob)
            handle.flush()
            report = gen_layouts.probe_btf(handle.name)
        self.assertEqual(report["struct kmem_cache"]["fields"]["flags"], 0)
        self.assertEqual(report["struct kmem_cache"]["sizeof"], 0x2100)
        self.assertTrue(btf.parse(blob).has("struct kmem_cache"))

    def test_unresolved_field_is_skipped(self) -> None:
        import tempfile

        blob = _make_btf(
            {"struct kmem_cache": 0x2100},
            {"struct kmem_cache": [("flags", 5, 0)]},
        )
        with tempfile.NamedTemporaryFile(suffix=".btf") as handle:
            handle.write(blob)
            handle.flush()
            report = gen_layouts.probe_btf(handle.name)
        self.assertEqual(
            set(report["struct kmem_cache"]["fields"]), {"flags"},
        )

    def test_structs_outside_the_spec_are_omitted(self) -> None:
        import tempfile

        blob = _make_btf(
            {"struct kmem_cache": 0x2100, "struct unrelated": 0x8},
            {"struct kmem_cache": [("flags", 5, 0)],
             "struct unrelated": [("x", 5, 0)]},
        )
        with tempfile.NamedTemporaryFile(suffix=".btf") as handle:
            handle.write(blob)
            handle.flush()
            report = gen_layouts.probe_btf(handle.name)
        # ``struct unrelated`` is not a registry type, so it is absent.
        self.assertEqual(set(report), {"struct kmem_cache"})


def _make_btf(
    sizes: dict[str, int],
    members: dict[str, list[tuple[str, int, int]]],
) -> bytes:
    """Build a minimal BTF blob: ``INT`` filler + one STRUCT per name.

    Kept local so this suite does not depend on the test helpers in
    ``tests/unit/test_btf.py``.
    """
    import struct as _struct

    strings = bytearray(b"\x00")
    offsets: dict[str, int] = {"": 0}

    def string(text: str) -> int:
        if text in offsets:
            return offsets[text]
        offsets[text] = len(strings)
        strings.extend(text.encode() + b"\x00")
        return offsets[text]

    names = list(sizes)
    for type_name in names:
        for member_name, _member_type, _bits in members.get(type_name, []):
            string(member_name)
        string(type_name.removeprefix("struct "))

    # INT (id 1, kind 1, size 4) carries a 4-byte payload; then the STRUCTs
    # (kind 4, bits 24-28).
    body = bytearray(_struct.pack("<III", 0, (1 << 24) | 1, 4) + b"\x00" * 4)
    for type_name in names:
        rows = members.get(type_name, [])
        body += _struct.pack(
            "<III",
            string(type_name.removeprefix("struct ")),
            (4 << 24) | (len(rows) & 0xFFFF),
            sizes[type_name],
        )
        for member_name, member_type, bits in rows:
            body += _struct.pack(
                "<III", string(member_name), member_type, bits,
            )

    # ``type_off`` / ``str_off`` are relative to the header, so the string
    # section starts right after the type section.
    header = _struct.pack(
        "<HBBIIIII",
        0xEB9F, 1, 0, 24, 0, len(body),
        len(body), len(strings),
    )
    return header + bytes(body) + bytes(strings)


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