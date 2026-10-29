"""The generated command reference.

The table moved out of both READMEs so it could stop being maintained
twice.  These tests keep the generated page tied to the metadata and to
``kl-help``'s category order.
"""

from __future__ import annotations

import io
import json
import re
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import gen_commands
from contract_spec import CANONICAL_COMMANDS

ROOT = Path(__file__).resolve().parents[2]


class CommandReferenceTests(unittest.TestCase):
    def test_checked_in_page_matches_the_metadata(self) -> None:
        rendered = gen_commands.build(gen_commands.DEFAULT_META)
        current = gen_commands.DEFAULT_OUTPUT.read_text(encoding="utf-8")
        self.assertEqual(
            current, rendered,
            "docs/en/commands.md is stale; run tools/gen_commands.py",
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
        self.assertEqual(len(meta), len(CANONICAL_COMMANDS))
        self.assertEqual(
            sorted(entry["name"] for entry in meta),
            sorted(CANONICAL_COMMANDS),
            "the metadata must describe exactly the contract surface",
        )
        for entry in meta:
            with self.subTest(command=entry["name"]):
                # The row leads with the spelling a reader types and
                # names the registered spelling beside it; a table that
                # led with the canonical name taught a name no reader
                # types at the prompt.
                primary = gen_commands.interactive(entry["name"])
                self.assertIn(f"| `{primary}` | `{entry['name']}`", text)
                for alias in entry["aliases"]:
                    if alias == primary:
                        continue
                    self.assertIn(f"`{alias}`", text)

    def test_both_languages_are_generated(self) -> None:
        """One table, two frames.

        The command names, aliases, and summaries stay English in both
        pages -- they are the strings ``kl-help`` prints -- but the
        heading, the column labels, and the note are translated, so the
        Chinese page cannot simply be a copy.
        """
        english = gen_commands.DEFAULT_OUTPUT.read_text(encoding="utf-8")
        chinese = gen_commands.LOCALE_OUTPUT.read_text(encoding="utf-8")
        self.assertNotEqual(english, chinese)
        self.assertIn("# Command reference", english)
        self.assertIn("# 命令参考", chinese)
        rows = [
            line for line in english.splitlines()
            if line.startswith("| `kl-")
        ]
        self.assertEqual(len(rows), len(CANONICAL_COMMANDS))
        for row in rows:
            with self.subTest(row=row.split("|")[1].strip()):
                self.assertIn(row, chinese)

    def test_the_readme_quotes_the_real_command_count(self) -> None:
        """The count in prose has to match the registry.

        Both READMEs said "40 commands" while the registry held 30, and
        nothing noticed: the number is written by hand, in two languages,
        in the sentence a reader meets first.  ``docs/zh-CN/architecture.md``
        quoted it a third time as a page count.

        The Chinese README used to promise that a test checked this.  It
        did not, which is why the number drifted.  Now it does, so the
        promise and the check agree.
        """
        expected = len(CANONICAL_COMMANDS)
        quoted = [
            (ROOT / "README.md", rf"\*\*{expected} commands\*\*"),
            (ROOT / "README.zh-CN.md", rf"\*\*{expected} 个命令\*\*"),
        ]
        for path, pattern in quoted:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertRegex(text, pattern)
                # And no other number claims to be the total.
                for wrong in re.findall(r"\*\*(\d+) (?:commands|个命令)\*\*", text):
                    self.assertEqual(int(wrong), expected, path.name)

    def test_the_architecture_page_counts_the_tutorial_pages(self) -> None:
        """The tree diagram names how many tutorial pages are generated.

        It is a third place the same number is written by hand, and it
        was the third place it was wrong.
        """
        pages = len(list((ROOT / "docs" / "en" / "tutorial").glob("kl-*.md")))
        self.assertEqual(pages, len(CANONICAL_COMMANDS))
        for locale in ("en", "zh-CN"):
            with self.subTest(locale=locale):
                text = (ROOT / "docs" / locale / "architecture.md").read_text(
                    encoding="utf-8",
                )
                # The English tree uses ASCII parentheses and the Chinese
                # one full-width; both are hand-written, so both are read.
                self.assertRegex(text, rf"tutorial/.*[(（]{pages}")

    def test_the_package_description_names_no_command_count(self) -> None:
        """The description must not pin a number the project outgrows.

        An earlier version said "30 commands", and a test was written to
        keep that number true.  That was the wrong guard: the command set
        grows, so the number would have to be edited on every release,
        and the README already carries a live count that a test keeps
        honest.  Two copies of a number, one of them stale, is the exact
        failure the README guard was added to prevent.

        So this asserts the opposite.  A digit followed by "command" in
        the description is the shape that goes stale; the description
        says *what the thing is* instead ("GDB commands"), which stays
        true however many there are.
        """
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^description = "(.*)"$', pyproject, re.M)
        self.assertIsNotNone(match, "no description in pyproject.toml")
        description = match.group(1)

        # A count can be written on either side of the word -- "30
        # commands" and "commands (30)" both go stale -- so this looks at
        # a window around every digit rather than at a fixed shape.  A
        # plain `\d+ commands` regex missed "commands (30)", which is why
        # it is written this way.
        #
        # `x86_64` is the reason digits cannot simply be banned; it is
        # 128 characters from the word "commands" in this sentence, so a
        # 40-character window leaves it alone.
        for digit in re.finditer(r"\d+", description):
            window = description[max(0, digit.start() - 40):digit.end() + 40]
            self.assertNotIn(
                "command", window.lower(),
                f"the description pins a count near {digit.group()!r} "
                f"({window.strip()!r}); it will go stale as commands are added",
            )

        # It still has to say what the project is, or the fix for the
        # stale number would be to delete the whole clause.
        self.assertIn("GDB commands", description)

    def test_check_fails_when_a_page_drifts(self) -> None:
        """``--check`` has to notice, whichever language drifted.

        Driven through the real files rather than a temporary directory:
        the generator no longer takes an output path, so the check has to
        be exercised by editing a page and restoring it.  Both locales are
        compared because a stale Chinese page is as wrong as a stale
        English one, and nothing else would report it.
        """
        for locale, page in (
            ("en", gen_commands.DEFAULT_OUTPUT),
            ("zh-CN", gen_commands.LOCALE_OUTPUT),
        ):
            with self.subTest(locale=locale):
                original = page.read_text(encoding="utf-8")
                try:
                    page.write_text("stale\n", encoding="utf-8")
                    with redirect_stdout(io.StringIO()), \
                            redirect_stderr(io.StringIO()):
                        status = gen_commands.main([
                            "--check", "--locale", locale,
                        ])
                finally:
                    page.write_text(original, encoding="utf-8")
                self.assertEqual(status, 1)


if __name__ == "__main__":
    unittest.main()
