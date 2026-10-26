"""Unit tests for ``output.tree.IndentContextManager``.

The context manager only touches ``print`` and the ``message`` helpers,
so these tests run without GDB.  They pin the depth accounting (which
drives the indentation) and the colour roles the commands depend on.
"""

from __future__ import annotations

import contextlib
import io
import unittest

from kernlens.output import message
from kernlens.output.tree import IndentContextManager


class IndentDepthTests(unittest.TestCase):
    def test_starts_at_depth_zero(self) -> None:
        indent = IndentContextManager()
        self.assertEqual(indent.depth, 0)
        self.assertEqual(indent.unit, "    ")

    def test_enter_increments_and_exit_decrements(self) -> None:
        indent = IndentContextManager()
        with indent:
            self.assertEqual(indent.depth, 1)
            with indent:
                self.assertEqual(indent.depth, 2)
            self.assertEqual(indent.depth, 1)
        self.assertEqual(indent.depth, 0)

    def test_exit_decrements_even_on_error(self) -> None:
        indent = IndentContextManager()
        with self.assertRaises(RuntimeError):
            with indent:
                raise RuntimeError("boom")
        self.assertEqual(indent.depth, 0)

    def test_custom_unit_is_used(self) -> None:
        indent = IndentContextManager("\t")
        self.assertEqual(indent.unit, "\t")
        indent.set_unit("--")
        self.assertEqual(indent.unit, "--")

    def test_print_prepends_one_unit_per_depth(self) -> None:
        indent = IndentContextManager("..")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            indent.print("root")
            with indent:
                indent.print("child")
                with indent:
                    indent.print("grandchild")
        self.assertEqual(
            buffer.getvalue(),
            "root\n..child\n....grandchild\n",
        )

    def test_print_forwards_print_keywords(self) -> None:
        indent = IndentContextManager()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            indent.print("a", "b", sep="-", end="!")
        self.assertEqual(buffer.getvalue(), "a-b!")


class IndentColorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(message.set_color_enabled, message.color_enabled())
        message.set_color_enabled(True)

    def test_print_without_arguments_emits_just_the_indent(self) -> None:
        indent = IndentContextManager("..")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            with indent:
                indent.print()
        self.assertEqual(buffer.getvalue(), "..\n")

    def test_addr_hex_is_an_unpadded_hex_string(self) -> None:
        indent = IndentContextManager()
        message.set_color_enabled(False)
        self.assertEqual(indent.addr_hex(0xDEAD), "0xdead")
        self.assertEqual(indent.aux_hex(0xDEAD), "0xdead")

    def test_aux_hex_paints_red_and_addr_hex_yellow(self) -> None:
        indent = IndentContextManager()
        self.assertTrue(indent.addr_hex(0x10).startswith("\x1b[33m"))
        self.assertTrue(indent.aux_hex(0x10).startswith("\x1b[31m"))

    def test_prefix_alternates_by_depth(self) -> None:
        indent = IndentContextManager()
        even = indent.prefix("Label")
        with indent:
            odd = indent.prefix("Label")
        self.assertNotEqual(even, odd)
        self.assertTrue(even.startswith("\x1b[34m"))  # blue at depth 0
        self.assertTrue(odd.startswith("\x1b[32m"))   # green at depth 1

    def test_helpers_are_plain_when_colour_is_off(self) -> None:
        indent = IndentContextManager()
        message.set_color_enabled(False)
        self.assertEqual(indent.addr_hex(0x10), "0x10")
        self.assertEqual(indent.aux_hex(0x10), "0x10")
        self.assertEqual(indent.prefix("Label"), "Label")


if __name__ == "__main__":
    unittest.main()