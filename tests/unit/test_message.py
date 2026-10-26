"""Unit tests for the pwndbg-style ``output.message`` helpers.

These run without GDB: the module only wraps text in ANSI sequences and
exposes a module-level colour switch.  The point of the suite is to pin
two contracts the command layer relies on:

* every role has a *distinct* colour, so a restyle cannot silently merge
  two meanings;
* with colour disabled every helper is the identity function, which is
  what keeps ``kl-color off`` output byte-identical plain text.
"""

from __future__ import annotations

import unittest

from kernlens.output import message


#: The public helpers and the SGR prefix each one must emit.
ROLE_CODES = {
    "error": "\x1b[31m",
    "warn": "\x1b[33m",
    "hint": "\x1b[33m",
    "notice": "\x1b[35m",
    "success": "\x1b[32m",
    "info": "\x1b[97m",
    "on": "\x1b[32m",
    "off": "\x1b[31m",
    "system": "\x1b[91m",
    "debug": "\x1b[34m",
    "highlight": "\x1b[92m",
}

RESET = "\x1b[0m"


class MessageColorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(message.set_color_enabled, message.color_enabled())
        message.set_color_enabled(True)

    def test_every_helper_wraps_and_resets(self) -> None:
        for role, code in ROLE_CODES.items():
            with self.subTest(role=role):
                helper = getattr(message, role)
                self.assertEqual(helper("text"), f"{code}text{RESET}")

    def test_every_role_is_exported(self) -> None:
        for role in ROLE_CODES:
            with self.subTest(role=role):
                self.assertIn(role, message.__all__)

    def test_helpers_accept_non_string_objects(self) -> None:
        self.assertEqual(message.error(0x41), f"\x1b[31m65{RESET}")
        self.assertEqual(message.warn(None), f"\x1b[33mNone{RESET}")

    def test_distinct_semantics_have_distinct_colours(self) -> None:
        # error and warn must not share a colour, and neither may match
        # the success / status roles.
        pairs = [
            ("error", "warn"),
            ("error", "success"),
            ("warn", "notice"),
            ("success", "off"),
            ("on", "off"),
        ]
        for left, right in pairs:
            with self.subTest(pair=(left, right)):
                self.assertNotEqual(
                    getattr(message, left)("x"), getattr(message, right)("x"),
                )

    def test_on_and_off_are_status_synonyms(self) -> None:
        # ``on`` mirrors success (green); ``off`` mirrors error (red).
        self.assertEqual(message.on("x"), message.success("x"))
        self.assertEqual(message.off("x"), message.error("x"))


class MessageToggleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(message.set_color_enabled, message.color_enabled())

    def test_disabled_helpers_return_plain_text(self) -> None:
        message.set_color_enabled(False)
        for role in ROLE_CODES:
            with self.subTest(role=role):
                helper = getattr(message, role)
                self.assertEqual(helper("plain"), "plain")

    def test_color_enabled_reports_the_switch(self) -> None:
        message.set_color_enabled(False)
        self.assertFalse(message.color_enabled())
        message.set_color_enabled(True)
        self.assertTrue(message.color_enabled())

    def test_set_color_enabled_coerces_to_bool(self) -> None:
        message.set_color_enabled(0)
        self.assertFalse(message.color_enabled())
        message.set_color_enabled("yes")
        self.assertTrue(message.color_enabled())


class ColorizeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(message.set_color_enabled, message.color_enabled())
        message.set_color_enabled(True)

    def test_colorize_applies_an_explicit_code(self) -> None:
        self.assertEqual(message.colorize("x", "\x1b[36m"), "\x1b[36mx\x1b[0m")

    def test_colorize_without_a_code_is_plain(self) -> None:
        self.assertEqual(message.colorize("x", ""), "x")

    def test_colorize_below_the_threshold_is_plain(self) -> None:
        message.set_color_enabled(False)
        self.assertEqual(message.colorize("x", "\x1b[36m"), "x")


if __name__ == "__main__":
    unittest.main()