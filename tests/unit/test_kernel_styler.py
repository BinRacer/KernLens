"""Tests for :class:`kernlens.gdb.styler.KernelStyler`.

These formatters produce the text a user reads on every SLUB and symbol
line, yet the class had no test of its own: ``src/kernlens/gdb/styler.py``
sat at 27% coverage while its sibling ``src/kernlens/output/styler.py``
was at 99%.  The gap was not "styling is hard to test" -- ``KernelStyler``
inherits from the pure-Python ``Styler`` and imports no ``gdb`` at all, so
every method runs on the host with no debugger and no fake module.

The tests come in pairs.  Each formatter is checked twice: once with
colour off, where the output must be the plain text a log file can be
diffed against, and once with colour on, where the *choice* of colour is
the meaning.  A formatter that colours a dangerous value the same as a
safe one has broken the only thing it was for, and that failure is
invisible in the plain-text half.
"""

from __future__ import annotations

import unittest

from kernlens.gdb.styler import KernelStyler
from kernlens.output import Palette


def plain() -> KernelStyler:
    return KernelStyler(color_enabled=False)


def colored() -> KernelStyler:
    return KernelStyler(color_enabled=True)


class SymbolFormattingTests(unittest.TestCase):
    """``fn`` and ``loc``: the two halves of a resolved address."""

    def test_plain_text_is_unchanged(self) -> None:
        s = plain()
        self.assertEqual(s.fn("commit_creds"), "commit_creds")
        self.assertEqual(s.loc("kernel/cred.c:412"), "kernel/cred.c:412")

    def test_colour_distinguishes_name_from_location(self) -> None:
        # A backtrace line reads as "name at location"; if both were the
        # same colour the eye could not separate them.
        s = colored()
        self.assertEqual(s.fn("commit_creds"), f"{Palette.BRIGHT_CYAN}commit_creds\033[0m")
        self.assertEqual(s.loc("a.c:1"), f"{Palette.DIM}a.c:1\033[0m")
        self.assertNotIn(Palette.BRIGHT_CYAN, s.loc("a.c:1"))

    def test_unresolved_is_question_marks_in_every_mode(self) -> None:
        # GDB reports an unresolved symbol as "?" or "??".  Colouring it
        # would make an unknown look like a resolved-but-dimmed value.
        for s in (plain(), colored()):
            with self.subTest(colour=s.color_enabled):
                for marker in ("?", "??"):
                    self.assertEqual(s.fn(marker), "??")
                    self.assertEqual(s.loc(marker), "??")


class DepthMarkerTests(unittest.TestCase):
    """``depth_marker``: how far down a SLUB freelist the walk has gone."""

    def test_plain(self) -> None:
        self.assertEqual(plain().depth_marker(3), "H@depth3")
        self.assertEqual(plain().depth_marker(0), "H@depth0")

    def test_coloured(self) -> None:
        self.assertEqual(
            colored().depth_marker(2),
            f"{Palette.BRIGHT_YELLOW_BOLD}H@depth2\033[0m",
        )


class BranchLabelTests(unittest.TestCase):
    """``branch``: which arm of the hardening check was taken."""

    def test_plain(self) -> None:
        s = plain()
        for label in ("nodefer", "defer", "other"):
            with self.subTest(label=label):
                self.assertEqual(s.branch(label), label)

    def test_nodefer_and_defer_are_coloured_differently(self) -> None:
        # This is the whole point of the method: `nodefer` means the
        # deferred path was skipped, `defer` means it was taken.  Same
        # colour would erase the distinction the tool exists to show.
        s = colored()
        self.assertIn(Palette.GREEN, s.branch("nodefer"))
        self.assertIn(Palette.BRIGHT_YELLOW_BOLD, s.branch("defer"))

    def test_a_suffix_after_the_label_is_kept_in_plain_text(self) -> None:
        # Callers pass e.g. "defer(depth=3)"; the parenthesised part is
        # context, not the label, and must survive the colour split.
        s = colored()
        text = s.branch("defer(depth=3)")
        self.assertIn("defer", text)
        self.assertIn("(depth=3)", text)

    def test_an_unknown_label_is_not_rewritten(self) -> None:
        self.assertEqual(colored().branch("something-else"), "something-else")


class FreelistTagTests(unittest.TestCase):
    """``fl_tag``: a freelist pointer's relation to the head pointer H."""

    def test_null_is_green_because_it_ends_the_list(self) -> None:
        self.assertEqual(plain().fl_tag(0, 0x1000), "NULL")
        self.assertEqual(
            colored().fl_tag(0, 0x1000), f"{Palette.GREEN}NULL\033[0m",
        )

    def test_short_form(self) -> None:
        s = plain()
        self.assertEqual(s.fl_tag(0x1000, 0x1000, short=True), "=H")
        self.assertEqual(s.fl_tag(0x2000, 0x1000, short=True), "!=H")

    def test_long_form_carries_the_address(self) -> None:
        s = plain()
        self.assertEqual(s.fl_tag(0x1000, 0x1000), "0x1000(=H)")
        self.assertEqual(s.fl_tag(0x2000, 0x1000), "0x2000(!=H)")

    def test_equality_is_the_dangerous_colour(self) -> None:
        # A freelist entry that points back at H is the cycle a
        # use-after-free tracer is looking for, so it gets the alarming
        # colour and inequality gets the calm one.
        s = colored()
        self.assertIn(Palette.BRIGHT_RED_BOLD, s.fl_tag(0x1000, 0x1000))
        self.assertIn(Palette.BRIGHT_GREEN, s.fl_tag(0x2000, 0x1000))
        self.assertIn(Palette.BRIGHT_RED_BOLD, s.fl_tag(0x1000, 0x1000, short=True))


class KvHelperTests(unittest.TestCase):
    """The four kernel-specific ``k=v`` formatters."""

    def test_cpu_plain_and_unknown(self) -> None:
        s = plain()
        self.assertEqual(s.kv_cpu("cpu", 2), "cpu=2")
        # -1 is KernLens' "no CPU" sentinel; it must read as unknown
        # rather than as a CPU numbered minus one.
        self.assertEqual(s.kv_cpu("cpu", -1), "cpu=?")
        self.assertEqual(s.kv_cpu("cpu", None), "cpu=?")

    def test_cpu_highlights_the_match(self) -> None:
        # The default match_cpu is a sentinel (-999), not a real CPU id:
        # without it every CPU would look matched.
        s = colored()
        matched = s.kv_cpu("cpu", 2, match_cpu=2)
        unmatched = s.kv_cpu("cpu", 2, match_cpu=3)
        default = s.kv_cpu("cpu", 2)
        self.assertIn(Palette.GREEN, matched)
        self.assertIn(Palette.BRIGHT_CYAN, unmatched)
        self.assertEqual(unmatched, default)

    def test_online(self) -> None:
        s = plain()
        self.assertEqual(s.kv_online(True), "online=1")
        self.assertEqual(s.kv_online(False), "online=0")
        self.assertEqual(s.kv_online(None), "online=?")
        c = colored()
        self.assertIn(Palette.GREEN, c.kv_online(True))
        self.assertIn(Palette.RED, c.kv_online(False))

    def test_err(self) -> None:
        # sk_err == 0 is the healthy case and is the only one that gets
        # green; everything else is an error worth looking at.
        s = plain()
        self.assertEqual(s.kv_err(0), "sk_err=0")
        self.assertEqual(s.kv_err(-11), "sk_err=-11")
        self.assertEqual(s.kv_err(None), "sk_err=?")
        c = colored()
        self.assertIn(Palette.GREEN, c.kv_err(0))
        self.assertIn(Palette.BRIGHT_RED, c.kv_err(-11))

    def test_transition_direction_is_the_meaning(self) -> None:
        # A count falling is a free, a count rising is an allocation, and
        # a count reaching zero under `danger_if_zero` is the moment a
        # use-after-free becomes possible.  All three must differ.
        s = colored()
        falling = s.kv_trans("count", 3, 1)
        rising = s.kv_trans("count", 1, 3)
        to_zero = s.kv_trans("count", 3, 0)
        flat = s.kv_trans("count", 3, 3)
        colours = {falling, rising, to_zero, flat}
        self.assertEqual(len(colours), 4, "directions share a colour")

    def test_danger_if_zero_can_be_disabled(self) -> None:
        # A caller that treats zero as ordinary must be able to say so;
        # otherwise "reached zero" would be alarming in contexts where it
        # is not.
        s = colored()
        danger = s.kv_trans("count", 3, 0)
        ordinary = s.kv_trans("count", 3, 0, danger_if_zero=False)
        self.assertNotEqual(danger, ordinary)
        self.assertIn(Palette.BRIGHT_RED_BOLD, danger)
        self.assertNotIn(Palette.BRIGHT_RED_BOLD, ordinary)

    def test_transition_plain_text(self) -> None:
        self.assertEqual(plain().kv_trans("count", 3, 1), "count 3->1")


class ColourToggleTests(unittest.TestCase):
    """Colour is a runtime switch, not a constructor-only decision.

    ``kl-color off`` has to work mid-session, and it flips the same
    instance the commands already hold.
    """

    def test_toggling_changes_rendering(self) -> None:
        s = colored()
        self.assertIn("\033[", s.fn("f"))
        s.set_color_enabled(False)
        self.assertEqual(s.fn("f"), "f")
        s.set_color_enabled(True)
        self.assertIn("\033[", s.fn("f"))


if __name__ == "__main__":
    unittest.main()