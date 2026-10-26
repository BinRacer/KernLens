"""Unit tests for :mod:`kernlens.output.logger`."""

from __future__ import annotations

import importlib
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from kernlens import LogLevel, Logger, Palette, Styler

logger_module = importlib.import_module("kernlens.output.logger")


class PaletteTests(unittest.TestCase):
    def test_sgr_values(self) -> None:
        self.assertEqual(Palette.RED.value, "\x1b[31m")
        self.assertEqual(str(Palette.RED), "\x1b[31m")
        self.assertEqual(f"{Palette.RED}", "\x1b[31m")
        self.assertEqual(format(Palette.RED, ""), "\x1b[31m")
        self.assertEqual(Palette.RESET.value, "\x1b[0m")


class LogLevelTests(unittest.TestCase):
    def test_tags_and_colors(self) -> None:
        self.assertEqual(LogLevel.DEBUG.tag, "[DEBUG]  ")
        self.assertEqual(LogLevel.INFO.tag, "[INFO]   ")
        self.assertEqual(LogLevel.SUCCESS.tag, "[SUCCESS]")
        self.assertEqual(LogLevel.WARN.tag, "[WARN]   ")
        self.assertEqual(LogLevel.ERROR.tag, "[ERROR]  ")

        for level in LogLevel:
            with self.subTest(level=level):
                self.assertEqual(len(level.tag), 9)
                self.assertIsInstance(level.color, Palette)

        self.assertIs(LogLevel.INFO.color, Palette.CYAN)
        self.assertIs(LogLevel.ERROR.color, Palette.BRIGHT_RED_BOLD)


class LoggerSettingsTests(unittest.TestCase):
    def test_defaults(self) -> None:
        log = Logger()
        self.assertTrue(log.color_enabled)
        self.assertIs(log.min_level, LogLevel.DEBUG)
        self.assertTrue(log.show_tag)
        self.assertFalse(log.show_time)

    def test_color_toggle(self) -> None:
        log = Logger()
        log.disable_color()
        self.assertFalse(log.color_enabled)
        log.enable_color()
        self.assertTrue(log.color_enabled)
        log.set_color_enabled(False)
        self.assertFalse(log.color_enabled)

    def test_min_level_and_is_enabled(self) -> None:
        log = Logger(min_level=LogLevel.WARN)
        self.assertTrue(log.is_enabled(LogLevel.WARN))
        self.assertTrue(log.is_enabled(LogLevel.ERROR))
        self.assertFalse(log.is_enabled(LogLevel.INFO))
        self.assertFalse(log.is_enabled(LogLevel.DEBUG))
        log.set_min_level(LogLevel.DEBUG)
        self.assertTrue(log.is_enabled(LogLevel.DEBUG))

    def test_prefix_toggles(self) -> None:
        stream = io.StringIO()
        log = Logger(
            color_enabled=False, show_tag=False, show_time=False, stream=stream,
        )
        log.info("plain")
        self.assertEqual(stream.getvalue(), "plain\n")

        log.set_show_tag(True)
        log.info("tagged")
        self.assertEqual(stream.getvalue(), "plain\n[INFO]    tagged\n")

        log.set_show_time(True)
        with patch.object(logger_module.time, "time", return_value=123.456789):
            log.info("timed")
        self.assertIn("[  123.456789] [INFO]    timed", stream.getvalue())

    def test_set_stream(self) -> None:
        first = io.StringIO()
        second = io.StringIO()
        log = Logger(color_enabled=False, stream=first)
        log.info("one")
        log.set_stream(second)
        log.info("two")
        self.assertEqual(first.getvalue(), "[INFO]    one\n")
        self.assertEqual(second.getvalue(), "[INFO]    two\n")

        log.set_stream(None)
        out = io.StringIO()
        with redirect_stdout(out):
            log.info("three")
        self.assertEqual(out.getvalue(), "[INFO]    three\n")


class LoggerEmitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stream = io.StringIO()
        self.log = Logger(color_enabled=False, stream=self.stream)

    def test_all_levels(self) -> None:
        self.log.debug("d")
        self.log.info("i")
        self.log.success("s")
        self.log.warn("w")
        self.log.error("e")
        self.assertEqual(
            self.stream.getvalue().splitlines(),
            [
                "[DEBUG]   d",
                "[INFO]    i",
                "[SUCCESS] s",
                "[WARN]    w",
                "[ERROR]   e",
            ],
        )

    def test_level_filtering(self) -> None:
        self.log.set_min_level(LogLevel.WARN)
        self.log.debug("d")
        self.log.info("i")
        self.log.warn("w")
        self.assertEqual(
            self.stream.getvalue().splitlines(), ["[WARN]    w"],
        )

    def test_color_output(self) -> None:
        log = Logger(color_enabled=True, stream=self.stream)
        log.info("hello")
        out = self.stream.getvalue()
        self.assertIn("\x1b[36m[INFO]   \x1b[0m", out)
        self.assertTrue(out.endswith("hello\n"))

    def test_fmt_line(self) -> None:
        self.assertEqual(
            self.log.fmt_line(LogLevel.ERROR, "boom"),
            "[ERROR]   boom",
        )
        log = Logger(color_enabled=False, show_tag=False)
        self.assertEqual(log.fmt_line(LogLevel.INFO, "x"), "x")

    def test_banner_and_rule(self) -> None:
        self.log.banner("T", char="=", width=10)
        self.log.banner("wide banner", char="=", width=5)
        self.log.rule(char="-", width=6)
        self.assertEqual(
            self.stream.getvalue().splitlines(),
            [
                "[INFO]    === T ====",
                "[INFO]    wide banner",
                "[INFO]    ------",
            ],
        )


class LoggerStatefulTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stream = io.StringIO()
        self.log = Logger(color_enabled=False, stream=self.stream)

    def test_once(self) -> None:
        self.assertTrue(self.log.once("k", "first"))
        self.assertFalse(self.log.once("k", "second"))
        self.assertTrue(self.log.once("other", "third"))
        self.assertEqual(
            self.stream.getvalue().splitlines(),
            ["[INFO]    first", "[INFO]    third"],
        )
        self.log.reset_once()
        self.assertTrue(self.log.once("k", "again"))

    def test_throttle_zero_interval_always_emits(self) -> None:
        self.assertTrue(self.log.throttle("k", 0, "a"))
        self.assertTrue(self.log.throttle("k", 0, "b"))
        self.assertEqual(len(self.stream.getvalue().splitlines()), 2)

    def test_throttle_interval(self) -> None:
        with patch.object(
            logger_module.time,
            "monotonic",
            side_effect=[100.0, 100.5, 102.0],
        ):
            self.assertTrue(self.log.throttle("k", 1.0, "a"))
            self.assertFalse(self.log.throttle("k", 1.0, "b"))
            self.assertTrue(self.log.throttle("k", 1.0, "c"))
        self.assertEqual(
            self.stream.getvalue().splitlines(),
            ["[INFO]    a", "[INFO]    c"],
        )
        self.log.reset_throttle()
        with patch.object(logger_module.time, "monotonic", return_value=103.0):
            self.assertTrue(self.log.throttle("k", 1.0, "d"))

    def test_counters_and_summary(self) -> None:
        self.assertEqual(self.log.counter("a"), 1)
        self.assertEqual(self.log.counter("a"), 2)
        self.assertEqual(self.log.counter("b", 5), 5)
        self.assertEqual(self.log.counters(), {"a": 2, "b": 5})

        counters = self.log.counters()
        counters["a"] = 999
        self.assertEqual(self.log.counters()["a"], 2)

        self.log.summary()
        out = self.stream.getvalue()
        self.assertIn("counters: 2", out)
        self.assertIn("  a: 2", out)
        self.assertIn("  b: 5", out)

        self.stream.truncate(0)
        self.stream.seek(0)
        self.log.summary(sort_by="value")
        lines = self.stream.getvalue().splitlines()
        self.assertIn("  b: 5", lines[1])
        self.assertIn("  a: 2", lines[2])

        self.log.reset_counters()
        self.assertEqual(self.log.counters(), {})

    def test_summary_empty(self) -> None:
        self.log.summary()
        self.assertEqual(
            self.stream.getvalue().splitlines(),
            ["[INFO]    counters: <empty>"],
        )

    def test_check_and_assert(self) -> None:
        self.assertTrue(self.log.check(True, "ok"))
        self.assertFalse(self.log.check(False, "ok"))
        self.assertFalse(
            self.log.check(False, "ok", fail_msg="custom", fail_level=LogLevel.ERROR),
        )
        self.assertTrue(self.log.assert_(True, "fine"))
        self.assertFalse(self.log.assert_(False, "broken"))

        lines = self.stream.getvalue().splitlines()
        self.assertIn("[INFO]    ok", lines)
        self.assertIn("[WARN]    FAIL: ok", lines)
        self.assertIn("[ERROR]   custom", lines)
        self.assertIn("[ERROR]   ASSERT: broken", lines)

    def test_reset(self) -> None:
        self.log.once("once", "x")
        self.log.counter("count")
        with patch.object(logger_module.time, "monotonic", return_value=1.0):
            self.log.throttle("throttle", 100.0, "y")
        self.log.reset()
        self.assertTrue(self.log.once("once", "again"))
        self.assertEqual(self.log.counters(), {})
        with patch.object(logger_module.time, "monotonic", return_value=1.0):
            self.assertTrue(self.log.throttle("throttle", 100.0, "again"))


class StylerColorTests(unittest.TestCase):
    def test_plain_output(self) -> None:
        sty = Styler(color_enabled=False)
        self.assertEqual(sty.style("x", Palette.RED), "x")
        self.assertEqual(sty.addr(0x1234), "0x1234")
        self.assertEqual(sty.kv("pid", "1"), "pid=1")

    def test_colored_output(self) -> None:
        sty = Styler(color_enabled=True)
        self.assertEqual(
            sty.style("x", Palette.RED), "\x1b[31mx\x1b[0m",
        )
        self.assertEqual(
            sty.addr(0x1234), "\x1b[2m0x1234\x1b[0m",
        )
        sty.disable_color()
        self.assertEqual(sty.addr(0x1234), "0x1234")
        sty.enable_color()
        self.assertEqual(
            sty.addr(0x1234), "\x1b[2m0x1234\x1b[0m",
        )

    def test_kv_color_defaults(self) -> None:
        sty = Styler(color_enabled=True)
        self.assertEqual(
            sty.kv("pid", "1"),
            "\x1b[36mpid\x1b[0m=1",
        )
        self.assertEqual(
            sty.kv("pid", "1", value_color=Palette.GREEN),
            "\x1b[36mpid\x1b[0m=\x1b[32m1\x1b[0m",
        )
        sty.set_kv_colors(Palette.RED, Palette.BLUE)
        self.assertEqual(
            sty.kv("pid", "1"),
            "\x1b[31mpid\x1b[0m=\x1b[34m1\x1b[0m",
        )
        self.assertEqual(sty.key_color, "\x1b[31m")
        self.assertEqual(sty.value_color, "\x1b[34m")
        sty.set_key_color(Palette.YELLOW)
        sty.set_value_color(Palette.GREEN)
        self.assertEqual(sty.key_color, "\x1b[33m")
        self.assertEqual(sty.value_color, "\x1b[32m")


class StylerNumericTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sty = Styler(color_enabled=False)

    def test_hex(self) -> None:
        self.assertEqual(self.sty.hex(0x1234), "0x1234")
        self.assertEqual(self.sty.hex(0x1234, digits=2), "0x34")
        self.assertEqual(self.sty.hex(0x1234, digits=4), "0x1234")
        self.assertEqual(
            self.sty.hex(0x1234, digits=16), "0x0000000000001234",
        )
        self.assertEqual(self.sty.hex8(0x1234), "0x34")
        self.assertEqual(self.sty.hex16(0x1234), "0x1234")
        self.assertEqual(self.sty.hex32(0x1234), "0x00001234")
        self.assertEqual(self.sty.hex64(0x1234), "0x0000000000001234")

    def test_dec_size_pfn_percent_bits(self) -> None:
        self.assertEqual(self.sty.dec(42), "42")
        self.assertEqual(self.sty.size(1536), "1.5K")
        self.assertEqual(self.sty.size((1 << 20) - 1), "1M")
        self.assertEqual(self.sty.size((1 << 30) - 1), "1G")
        self.assertEqual(self.sty.pfn(0x123456), "0x123")
        self.assertEqual(self.sty.percent(1, 2), "50.0%")
        self.assertEqual(self.sty.percent(1, 0), "?")
        self.assertEqual(self.sty.bits(0b1010, width=8), "00001010")
        self.assertEqual(self.sty.bits(0b1010, width=0), "")


class StylerAlignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sty = Styler(color_enabled=False)

    def test_justify(self) -> None:
        self.assertEqual(self.sty.ljust("abc", 5), "abc  ")
        self.assertEqual(self.sty.rjust("abc", 5), "  abc")
        self.assertEqual(self.sty.center("abc", 6), " abc  ")
        self.assertEqual(self.sty.center("abc", 5), " abc ")
        self.assertEqual(self.sty.ljust("abcdef", 3), "abcdef")
        self.assertEqual(self.sty.ljust("x", 3, fill="."), "x..")
        self.assertEqual(self.sty.rjust("x", 3, fill="."), "..x")
        self.assertEqual(self.sty.center("x", 3, fill="."), ".x.")

    def test_pad(self) -> None:
        self.assertEqual(self.sty.pad("x", 3, align="left"), "x  ")
        self.assertEqual(self.sty.pad("x", 3, align="right"), "  x")
        self.assertEqual(self.sty.pad("x", 3, align="center"), " x ")
        with self.assertRaises(ValueError):
            self.sty.pad("x", 3, align="bogus")

    def test_truncate(self) -> None:
        self.assertEqual(self.sty.truncate("abcdef", 5), "ab...")
        self.assertEqual(self.sty.truncate("abcdef", 3), "abc")
        self.assertEqual(self.sty.truncate("abcdef", 2), "ab")
        self.assertEqual(self.sty.truncate("abcdef", 4, ellipsis=".."), "ab..")
        with self.assertRaises(ValueError):
            self.sty.truncate("abc", -1)

    def test_fill_validation(self) -> None:
        for method in (self.sty.ljust, self.sty.rjust, self.sty.center):
            with self.subTest(method=method.__name__):
                with self.assertRaises(ValueError):
                    method("x", 3, fill="..")


class StylerKvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sty = Styler(color_enabled=False)

    def test_kv_family(self) -> None:
        self.assertEqual(self.sty.kv("pid", "1234"), "pid=1234")
        self.assertEqual(self.sty.kv_int("pid", 1234), "pid=1234")
        self.assertEqual(self.sty.kv_hex("page", 0xEA00), "page=0xea00")
        self.assertEqual(self.sty.kv_bool("ready", True), "ready=true")
        self.assertEqual(self.sty.kv_bool("ready", False), "ready=false")

    def test_fields_and_group(self) -> None:
        self.assertEqual(
            self.sty.fields([("pid", 1), ("cpu", 0)]),
            "pid=1  cpu=0",
        )
        self.assertEqual(
            self.sty.kv_group([("pid", 1), ("comm", "bash")]),
            " pid = 1\ncomm = bash",
        )
        self.assertEqual(
            self.sty.kv_group([("a", 1)], assign=": "),
            "a: 1",
        )
        self.assertEqual(self.sty.kv_group([]), "")


class StylerContainerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sty = Styler(color_enabled=False)

    def test_seq_family(self) -> None:
        self.assertEqual(self.sty.seq([1, 2, 3]), "[1, 2, 3]")
        self.assertEqual(self.sty.list([1, 2, 3]), "[1, 2, 3]")
        self.assertEqual(self.sty.tuple([1, 2, 3]), "(1, 2, 3)")
        self.assertEqual(self.sty.set([1, 2, 3]), "{1, 2, 3}")
        self.assertEqual(
            self.sty.seq(["a", "b"], open="<", close=">", sep="|"),
            "<a|b>",
        )

    def test_dict_and_pairs(self) -> None:
        self.assertEqual(
            self.sty.dict({"pid": 1, "cpu": 0}), "{pid: 1, cpu: 0}",
        )
        self.assertEqual(
            self.sty.dict([("pid", 1)]), "{pid: 1}",
        )
        self.assertEqual(
            self.sty.pairs({"pid": 1, "cpu": 0}), "{pid=1, cpu=0}",
        )

    def test_range(self) -> None:
        self.assertEqual(self.sty.range(0, 16), "[0x0, 0x10)")
        self.assertEqual(
            self.sty.range(0, 16, hex_fmt=False), "[0, 16)",
        )

    def test_named(self) -> None:
        self.assertEqual(self.sty.named("cpus", [0, 1, 2]), "cpus[0, 1, 2]")
        self.assertEqual(
            self.sty.named("cpus", [0, 1, 2], style="{}"),
            "cpus{0, 1, 2}",
        )
        with self.assertRaises(ValueError):
            self.sty.named("x", [1], style="<>")

    def test_kv_seq(self) -> None:
        self.assertEqual(
            self.sty.kv_seq("slab", ["a", "b"]), "slab=[a, b]",
        )
        self.assertEqual(
            self.sty.kv_seq("slab", {"page": "0xea00"}, style="{}"),
            "slab={page: 0xea00}",
        )


class StylerLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sty = Styler(color_enabled=False)

    def test_table(self) -> None:
        table = self.sty.table(
            ["name", "inuse"],
            [["kmalloc-1k", 3], ["kmalloc-64", 7]],
            aligns=["l", "r"],
        )
        self.assertEqual(
            table,
            "\n".join(
                [
                    "name        inuse",
                    "----------  -----",
                    "kmalloc-1k      3",
                    "kmalloc-64      7",
                ]
            ),
        )

    def test_table_rule_none_and_fill(self) -> None:
        table = self.sty.table(
            ["a", "b"], [["1", "2"]], rule=None, fill=".",
        )
        self.assertEqual(table, "a  b\n1  2")
        table = self.sty.table(["a", "b"], [["1", "2"]], fill=".")
        self.assertEqual(table, "a  b\n-  -\n1  2")

    def test_table_truncation_and_alignment(self) -> None:
        table = self.sty.table(
            ["name", "count"],
            [["kmalloc-1024", 12345]],
            max_col_width=5,
            aligns="r",
        )
        self.assertEqual(
            table,
            "\n".join(
                [
                    " name  count",
                    "-----  -----",
                    "km...  12345",
                ]
            ),
        )

    def test_table_errors(self) -> None:
        with self.assertRaises(ValueError):
            self.sty.table(["a"], [["1"]], aligns="x")
        with self.assertRaises(ValueError):
            self.sty.table(["a"], [["1"]], fill="..")
        with self.assertRaises(ValueError):
            self.sty.table(["a"], [["1"]], rule="--")
        with self.assertRaises(ValueError):
            self.sty.table(["a"], [["1"]], max_col_width=0)
        self.assertEqual(self.sty.table([], []), "")

    def test_box(self) -> None:
        self.assertEqual(
            self.sty.box(["a", "b"], [["1", "2"]]),
            "\n".join(
                [
                    "┌───┬───┐",
                    "│ a │ b │",
                    "├───┼───┤",
                    "│ 1 │ 2 │",
                    "└───┴───┘",
                ]
            ),
        )

    def test_box_custom_chars(self) -> None:
        self.assertEqual(
            self.sty.box(
                ["a", "b"],
                [["1", "2"]],
                chars="++++-|",
                joints="+++++",
            ),
            "\n".join(
                [
                    "+---+---+",
                    "| a | b |",
                    "+---+---+",
                    "| 1 | 2 |",
                    "+---+---+",
                ]
            ),
        )

    def test_box_errors(self) -> None:
        with self.assertRaises(ValueError):
            self.sty.box(["a"], [["1"]], chars="++++-")
        with self.assertRaises(ValueError):
            self.sty.box(["a"], [["1"]], joints="++++")
        self.assertEqual(self.sty.box([], []), "")

    def test_chain(self) -> None:
        self.assertEqual(self.sty.chain([1, 2, 3]), "1 -> 2 -> 3")
        self.assertEqual(
            self.sty.chain(["a", "b"], sep=" <- "), "a <- b",
        )

    def test_cols(self) -> None:
        self.assertEqual(
            self.sty.cols(range(6), 3), "0    1    2\n3    4    5",
        )
        self.assertEqual(self.sty.cols([], 2), "")
        with self.assertRaises(ValueError):
            self.sty.cols([1], 0)
        with self.assertRaises(ValueError):
            self.sty.cols([1], 1, max_col_width=0)
        with self.assertRaises(ValueError):
            self.sty.cols([1], 1, pad=-1)

    def test_cols_alignment_and_truncation(self) -> None:
        self.assertEqual(
            self.sty.cols(["a", "bbb"], 2, aligns="r", max_col_width=2),
            "   a    bb",
        )

    def test_block(self) -> None:
        self.assertEqual(
            self.sty.block("slab", ["page=0xea00", "inuse=3"]),
            "\n".join(
                [
                    "┌ slab ───────┐",
                    "│ page=0xea00 │",
                    "│ inuse=3     │",
                    "└─────────────┘",
                ]
            ),
        )

    def test_block_width_and_empty(self) -> None:
        block = self.sty.block("t", ["a"], width=10)
        lines = block.splitlines()
        self.assertTrue(all(len(line) == 12 for line in lines))
        self.assertEqual(
            self.sty.block("t", []),
            "┌ t ┐\n└───┘",
        )

    def test_block_errors(self) -> None:
        with self.assertRaises(ValueError):
            self.sty.block("t", [], chars="┌┐└┘")
        with self.assertRaises(ValueError):
            self.sty.block("t", [], vertical="ab")


class StylerTransformTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sty = Styler(color_enabled=False)

    def test_highlight(self) -> None:
        self.assertEqual(self.sty.highlight("a b a", "a"), "a b a")
        self.assertEqual(self.sty.highlight("abc", ""), "abc")

    def test_indent(self) -> None:
        self.assertEqual(self.sty.indent("a\nb"), "  a\n  b")
        self.assertEqual(
            self.sty.indent("a", level=2, width=4), "        a",
        )
        self.assertEqual(self.sty.indent("a", level=0), "a")

    def test_symbols(self) -> None:
        self.assertEqual(self.sty.tick(), "✓")
        self.assertEqual(self.sty.cross(), "✗")
        self.assertEqual(self.sty.bullet(), "•")
        self.assertEqual(self.sty.arrow(), "→")

    def test_bar(self) -> None:
        self.assertEqual(self.sty.bar(4, 8, width=8), "[████░░░░] 4/8")
        self.assertEqual(self.sty.bar(0, 8, width=4), "[░░░░] 0/8")
        self.assertEqual(self.sty.bar(8, 8, width=4), "[████] 8/8")
        self.assertEqual(self.sty.bar(9, 8, width=4), "[████] 9/8")
        self.assertEqual(self.sty.bar(1, 0, width=4), "[░░░░] 1/0")
        self.assertEqual(
            self.sty.bar(2, 4, width=4, show_ratio=False), "[██░░]",
        )
        self.assertEqual(self.sty.bar(1, 1, width=0), "")


if __name__ == "__main__":
    unittest.main()