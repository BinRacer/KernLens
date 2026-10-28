"""The generated command reference.

The table moved out of both READMEs so it could stop being maintained
twice.  These tests keep the generated page tied to the metadata and to
``kl-help``'s category order.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import gen_commands

ROOT = Path(__file__).resolve().parents[2]


class CommandReferenceTests(unittest.TestCase):
    def test_checked_in_page_matches_the_metadata(self) -> None:
        rendered = gen_commands.build(gen_commands.DEFAULT_META)
        current = gen_commands.DEFAULT_OUTPUT.read_text(encoding="utf-8")
        self.assertEqual(
            current, rendered,
            "docs/commands.md is stale; run tools/gen_commands.py",
        )

    def test_every_category_is_in_kl_help_order(self) -> None:
        text = gen_commands.DEFAULT_OUTPUT.read_text(encoding="utf-8")
        positions = [
            text.index(f"## {category} (")
            for category in gen_commands.CATEGORY_ORDER
        ]
        self.assertEqual(positions, sorted(positions))

    def test_every_command_has_a_row(self) -> None:
        meta = json.loads(gen_commands.DEFAULT_META.read_text(encoding="utf-8"))
        text = gen_commands.DEFAULT_OUTPUT.read_text(encoding="utf-8")
        self.assertEqual(len(meta), 40)
        for entry in meta:
            with self.subTest(command=entry["name"]):
                self.assertIn(f"| `{entry['name']}` |", text)
                for alias in entry["aliases"]:
                    self.assertIn(f"`{alias}`", text)

    def test_check_fails_when_the_page_drifts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "commands.md"
            output.write_text("stale\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                status = gen_commands.main([
                    "--check", "--output", str(output),
                ])
        self.assertEqual(status, 1)


if __name__ == "__main__":
    unittest.main()
