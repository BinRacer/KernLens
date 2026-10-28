"""The README demo is generated from the tutorial capture.

A demo is the one asset a reader is most likely to trust without
checking, so it must not be hand-edited.  These tests pin the two
properties that make it honest: the text comes from the capture, and the
checked-in files are exactly what the generator renders.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import gen_demo

ROOT = Path(__file__).resolve().parents[2]


class DemoTests(unittest.TestCase):
    def test_lines_come_from_the_capture(self) -> None:
        rows = gen_demo.build_lines(gen_demo.DEFAULT_CAPTURE)
        text = "\n".join(line for _, line in rows)
        self.assertIn("huge leaf", text)
        self.assertIn("decoded=", text)
        self.assertIn("kl-walk", text)
        self.assertIn("kl-slab details", text)

    def test_checked_in_assets_match_the_capture(self) -> None:
        rows = gen_demo.build_lines(gen_demo.DEFAULT_CAPTURE)
        self.assertEqual(
            gen_demo.DEFAULT_SVG.read_text(encoding="utf-8"),
            gen_demo.render_svg(rows),
        )
        self.assertEqual(
            gen_demo.DEFAULT_CAST.read_text(encoding="utf-8"),
            gen_demo.render_cast(rows),
        )

    def test_svg_keeps_spaces_and_labels_the_replay(self) -> None:
        rows = gen_demo.build_lines(gen_demo.DEFAULT_CAPTURE)
        svg = gen_demo.render_svg(rows)
        self.assertIn('xml:space="preserve"', svg)
        self.assertIn("replay of the 6.1.134 capture", svg)
        self.assertIn("prefers-reduced-motion", svg)

    def test_svg_is_valid_and_accessible(self) -> None:
        import xml.etree.ElementTree as ET

        root = ET.parse(gen_demo.DEFAULT_SVG).getroot()
        self.assertEqual(root.get("role"), "img")
        ids = root.get("aria-labelledby", "").split()
        self.assertEqual(len(ids), 2)
        present = {element.get("id") for element in root.iter()}
        for name in ids:
            self.assertIn(name, present)

    def test_cast_is_valid_asciinema_v2(self) -> None:
        rows = gen_demo.build_lines(gen_demo.DEFAULT_CAPTURE)
        lines = gen_demo.render_cast(rows).splitlines()
        header = json.loads(lines[0])
        self.assertEqual(header["version"], 2)
        stamps = []
        for line in lines[1:]:
            stamp, event, text = json.loads(line)
            self.assertEqual(event, "o")
            self.assertIn("\r\n", text)
            stamps.append(stamp)
        self.assertEqual(stamps, sorted(stamps))

    def test_check_fails_when_an_asset_drifts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svg = Path(tmp) / "demo.svg"
            cast = Path(tmp) / "demo.cast"
            svg.write_text("stale\n", encoding="utf-8")
            cast.write_text("stale\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                status = gen_demo.main([
                    "--check", "--svg", str(svg), "--cast", str(cast),
                ])
        self.assertEqual(status, 1)


if __name__ == "__main__":
    unittest.main()
