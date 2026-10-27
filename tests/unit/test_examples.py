"""Tests for ``tools/check_examples.py`` and its manifest.

The checker exists so that a coverage claim about ``examples/`` can fail
a build.  These tests therefore do two jobs:

* pin the guarantees the checker makes (a claim without the code fails,
  a command that is only mentioned does not count as executed, the
  ratchet cannot be lowered silently), and
* pin the numbers in ``docs/example-coverage-plan.md``, so that document
  cannot drift from the tree the way hand-written coverage prose does.

The negative tests are the important ones.  A checker that only ever
passes is indistinguishable from one that does nothing -- the tutorial
pipeline earned its trust the same way, by being shown to fail when a
page was hand-edited.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import pathlib
import re
import tempfile
import unittest

import check_examples
import example_manifest
from contract_spec import CANONICAL_COMMANDS


class SurfaceNameTests(unittest.TestCase):
    """The one judgement the tool makes about what counts as coverage."""

    def test_methods_are_surface(self) -> None:
        self.assertTrue(check_examples.is_surface_name("byte_swap64"))
        self.assertTrue(check_examples.is_surface_name("walk"))

    def test_upper_case_constants_are_not(self) -> None:
        self.assertFalse(check_examples.is_surface_name("PTE_PRESENT"))
        self.assertFalse(check_examples.is_surface_name("PGD_SHIFT_4"))

    def test_mixed_case_geometry_constants_are_not(self) -> None:
        self.assertFalse(check_examples.is_surface_name("BITS_PER_LEVEL"))
        self.assertFalse(check_examples.is_surface_name("ENTRY_SIZE"))

    def test_private_names_are_not(self) -> None:
        self.assertFalse(check_examples.is_surface_name("_BINDINGS"))


class SurfaceDerivationTests(unittest.TestCase):
    """The surface must come from the code, not from a hand-written list."""

    def test_facade_bindings_match_the_literal(self) -> None:
        bound, free = check_examples.facade_bindings()
        self.assertEqual(len(bound), 140)
        self.assertEqual(len(free), 68)
        self.assertTrue(free <= bound)

    def test_commands_match_the_frozen_contract(self) -> None:
        self.assertEqual(
            set(check_examples.canonical_commands()), set(CANONICAL_COMMANDS)
        )

    def test_core_methods_exclude_constants(self) -> None:
        methods = check_examples.core_methods()
        self.assertNotIn("PTE_PRESENT", methods["KPageTable"])
        self.assertIn("split_4", methods["KPageTable"])
        self.assertNotIn("BITS_PER_LEVEL", methods["KPageTable"])

    def test_surface_groups_merge_qualified_and_bare_spellings(self) -> None:
        groups = check_examples.surface_groups()
        walk = groups["walker"]["walk"]
        self.assertEqual(walk, {"kdbg.walk", "walk"})
        self.assertEqual(len(groups["walker"]), 1)

    def test_surface_groups_count_each_function_once(self) -> None:
        """A free function is one entry, not two."""
        groups = check_examples.surface_groups()
        for component, members in groups.items():
            for canonical, spellings in members.items():
                self.assertTrue(spellings, f"{component}/{canonical} has no spelling")


class ManifestTests(unittest.TestCase):
    """The manifest is the coverage contract; these keep it honest."""

    def test_every_row_lives_under_a_known_root(self) -> None:
        for example in example_manifest.EXAMPLES:
            root = example.path.split("/")[1]
            self.assertIn(root, example_manifest.EXAMPLE_ROOTS, example.path)

    def test_script_rows_declare_something(self) -> None:
        for example in example_manifest.EXAMPLES:
            if example.kind != "script":
                continue
            self.assertTrue(
                example_manifest.declares(example),
                f"{example.path} declares neither surface nor commands",
            )

    def test_paths_are_unique(self) -> None:
        paths = [e.path for e in example_manifest.EXAMPLES]
        self.assertEqual(len(paths), len(set(paths)))

    def test_ratchet_is_not_negative(self) -> None:
        self.assertGreaterEqual(example_manifest.REQUIRED_COMMAND_COVERAGE, 0)


class CheckPassesOnTheCurrentTreeTests(unittest.TestCase):
    """The committed tree satisfies its own manifest."""

    def test_check_all_is_clean(self) -> None:
        failures = check_examples.check_all()
        self.assertEqual([str(f) for f in failures], [])

    def test_every_manifest_file_exists(self) -> None:
        self.assertEqual(check_examples.check_existence(), [])

    def test_every_manifest_file_is_linked_from_its_readme(self) -> None:
        self.assertEqual(check_examples.check_readme_links(), [])

    def test_every_claim_is_referenced(self) -> None:
        self.assertEqual(check_examples.check_claims(), [])


class NegativeTests(unittest.TestCase):
    """A checker that cannot fail is not a checker."""

    def _patched(self, examples: tuple[example_manifest.Example, ...]) -> list:
        original = check_examples.manifest.EXAMPLES
        check_examples.manifest.EXAMPLES = examples
        try:
            return check_examples.check_claims()
        finally:
            check_examples.manifest.EXAMPLES = original

    def test_claim_absent_from_the_file_is_reported(self) -> None:
        """Dropping the code but keeping the claim must fail."""
        broken = example_manifest.Example(
            path="examples/api/hello.py",
            purpose="negative test",
            surface=("KAddr.is_vmalloc",),
            readme="examples/api/README.md",
        )
        failures = self._patched((broken,))
        self.assertEqual(len(failures), 1)
        self.assertIn("never references it", str(failures[0]))

    def test_unknown_surface_name_is_reported(self) -> None:
        broken = example_manifest.Example(
            path="examples/api/hello.py",
            purpose="negative test",
            surface=("KAddr.not_a_real_method",),
            readme="examples/api/README.md",
        )
        failures = self._patched((broken,))
        self.assertEqual(len(failures), 1)
        self.assertIn("unknown surface name", str(failures[0]))

    def test_missing_file_is_reported(self) -> None:
        broken = example_manifest.Example(
            path="examples/api/does_not_exist.py",
            purpose="negative test",
        )
        original = check_examples.manifest.EXAMPLES
        check_examples.manifest.EXAMPLES = (broken,)
        try:
            failures = check_examples.check_existence()
        finally:
            check_examples.manifest.EXAMPLES = original
        self.assertEqual(len(failures), 1)
        self.assertIn("does not exist", str(failures[0]))

    def test_unknown_command_claim_is_reported(self) -> None:
        broken = example_manifest.Example(
            path="examples/api/trace.py",
            purpose="negative test",
            commands=("kl-not-a-command",),
            readme="examples/api/README.md",
        )
        original = check_examples.manifest.EXAMPLES
        check_examples.manifest.EXAMPLES = (broken,)
        try:
            failures = check_examples.check_commands()
        finally:
            check_examples.manifest.EXAMPLES = original
        self.assertEqual(len(failures), 1)
        self.assertIn("unknown command", str(failures[0]))

    def test_mentioned_but_not_executed_command_is_reported(self) -> None:
        """Claiming a command a file only names in prose must fail.

        ``cve_2025_38616_trace.py`` mentions ``kl-kaslr`` in a banner and
        in a docstring but never executes it -- that is exactly the
        distinction this checker exists to draw.
        """
        broken = example_manifest.Example(
            path="examples/tracing/cve_2025_38616_trace.py",
            purpose="negative test",
            commands=("kernlens-kaslr",),
            readme="examples/tracing/README.md",
        )
        original = check_examples.manifest.EXAMPLES
        check_examples.manifest.EXAMPLES = (broken,)
        try:
            failures = check_examples.check_commands()
        finally:
            check_examples.manifest.EXAMPLES = original
        self.assertEqual(len(failures), 1)
        self.assertIn("never executes it", str(failures[0]))

    def test_missing_readme_link_is_reported(self) -> None:
        broken = example_manifest.Example(
            path="examples/api/hello.py",
            purpose="negative test",
            readme="examples/tracing/README.md",
        )
        original = check_examples.manifest.EXAMPLES
        check_examples.manifest.EXAMPLES = (broken,)
        try:
            failures = check_examples.check_readme_links()
        finally:
            check_examples.manifest.EXAMPLES = original
        self.assertEqual(len(failures), 1)
        self.assertIn("does not link to", str(failures[0]))

    def test_ratchet_above_actual_coverage_is_reported(self) -> None:
        original = example_manifest.REQUIRED_COMMAND_COVERAGE
        example_manifest.REQUIRED_COMMAND_COVERAGE = 10_000
        try:
            failures = check_examples.check_coverage()
        finally:
            example_manifest.REQUIRED_COMMAND_COVERAGE = original
        self.assertEqual(len(failures), 1)
        self.assertIn("REQUIRED_COMMAND_COVERAGE", str(failures[0]))


class ExecutionDetectionTests(unittest.TestCase):
    """Only a real ``gdb.execute`` counts as demonstrating a command."""

    def _write(self, source: str) -> pathlib.Path:
        directory = tempfile.mkdtemp()
        path = pathlib.Path(directory) / "sample.py"
        path.write_text(source, encoding="utf-8")
        return path

    def test_literal_execute_counts(self) -> None:
        path = self._write('import gdb\ngdb.execute("kl-base")\n')
        self.assertEqual(
            check_examples.executed_commands(path), {"kernlens-base"}
        )

    def test_canonical_spelling_counts(self) -> None:
        path = self._write('import gdb\ngdb.execute("kernlens-kbase")\n')
        self.assertEqual(
            check_examples.executed_commands(path), {"kernlens-kbase"}
        )

    def test_execute_with_arguments_counts(self) -> None:
        path = self._write('import gdb\ngdb.execute("kl-walk 0xffff888000000000")\n')
        self.assertEqual(
            check_examples.executed_commands(path), {"kernlens-walk"}
        )

    def test_dynamically_built_command_does_not_count(self) -> None:
        """``f"kl-{name}"`` cannot be resolved statically."""
        path = self._write('import gdb\ngdb.execute(f"kl-{name} arg")\n')
        self.assertEqual(check_examples.executed_commands(path), set())

    def test_command_in_a_docstring_does_not_count(self) -> None:
        path = self._write('"""Try kl-walk here."""\nimport gdb\n')
        self.assertEqual(check_examples.executed_commands(path), set())
        self.assertEqual(check_examples.mentioned_commands(path), {"kernlens-walk"})

    def test_command_in_a_banner_does_not_count_as_executed(self) -> None:
        path = self._write(
            'import gdb\n'
            'gdb.write("run kl-slab -v to see the cache\\n")\n'
        )
        self.assertEqual(check_examples.executed_commands(path), set())
        self.assertEqual(check_examples.mentioned_commands(path), {"kernlens-slab"})

    def test_non_command_execute_string_is_ignored(self) -> None:
        path = self._write('import gdb\ngdb.execute("break kfree")\n')
        self.assertEqual(check_examples.executed_commands(path), set())


class WrapperDetectionTests(unittest.TestCase):
    """The ``_run("kl-x")`` pattern the tour examples use must count.

    Without this, every command behind a wrapper would be invisible and
    the coverage number would be wrong in the pessimistic direction --
    the opposite failure from the one that inflated the original
    estimate, and just as misleading.
    """

    def _write(self, source: str) -> pathlib.Path:
        directory = tempfile.mkdtemp()
        path = pathlib.Path(directory) / "sample.py"
        path.write_text(source, encoding="utf-8")
        return path

    def test_forwarding_wrapper_counts(self) -> None:
        path = self._write(
            "import gdb\n"
            "def _run(cmd):\n"
            "    gdb.execute(cmd, to_string=True)\n"
            "_run('kl-base')\n"
        )
        self.assertEqual(
            check_examples.executed_commands(path), {"kernlens-base"}
        )

    def test_wrapper_with_arguments_counts(self) -> None:
        path = self._write(
            "import gdb\n"
            "def _run(cmd):\n"
            "    gdb.execute(cmd)\n"
            "_run(f'kl-walk {0x1000:#x}')\n"
        )
        self.assertEqual(
            check_examples.executed_commands(path), {"kernlens-walk"}
        )

    def test_non_forwarding_function_does_not_count(self) -> None:
        """A function that ignores its argument is not a wrapper."""
        path = self._write(
            "import gdb\n"
            "def _run(cmd):\n"
            "    gdb.execute('kl-base')\n"
            "_run('kl-walk 0x1000')\n"
        )
        # `kl-base` is executed directly inside the function; the call
        # argument is not forwarded, so `kl-walk` must not be counted.
        self.assertEqual(
            check_examples.executed_commands(path), {"kernlens-base"}
        )

    def test_dynamic_wrapper_argument_does_not_count(self) -> None:
        path = self._write(
            "import gdb\n"
            "def _run(cmd):\n"
            "    gdb.execute(cmd)\n"
            "_run(f'kl-{name}')\n"
        )
        self.assertEqual(check_examples.executed_commands(path), set())


class LocalNameTests(unittest.TestCase):
    """A name the script binds itself is not a reference to the API.

    Every tour example has ``args = parser.parse_args(...)``, which made
    all of them appear to use the facade's ``arg()`` -- a register reader
    -- when they use nothing of the sort.  Excluding bound names fixes
    that without dropping ``arg`` from the surface, because an example
    that really calls ``arg("$rdi")`` must still be counted.
    """

    def _write(self, source: str) -> pathlib.Path:
        directory = tempfile.mkdtemp()
        path = pathlib.Path(directory) / "sample.py"
        path.write_text(source, encoding="utf-8")
        return path

    def test_assigned_local_name_is_not_a_reference(self) -> None:
        path = self._write("args = parse()\nprint(args)\n")
        qualified, bare = check_examples._references(path)
        self.assertNotIn("args", bare)

    def test_parameter_name_is_not_a_reference(self) -> None:
        path = self._write("def f(arg):\n    return arg\n")
        qualified, bare = check_examples._references(path)
        self.assertNotIn("arg", bare)

    def test_imported_name_is_not_a_reference(self) -> None:
        path = self._write("import shlex\nshlex.split('a b')\n")
        qualified, bare = check_examples._references(path)
        self.assertNotIn("shlex", bare)

    def test_free_use_of_arg_still_counts(self) -> None:
        """The real facade helper must still be seen when it is used."""
        path = self._write("value = arg('$rdi')\nprint(value)\n")
        surface = check_examples.referenced(path)
        self.assertIn("arg", surface)


class UncoveredCommandsTests(unittest.TestCase):
    """The declared gap must equal the measured gap."""

    def test_declared_gap_is_exactly_the_uninvoked_set(self) -> None:
        measured = set(check_examples.uninvoked_commands())
        declared = set(example_manifest.UNCOVERED_COMMANDS)
        self.assertEqual(measured, declared)

    def test_every_declared_gap_has_a_reason(self) -> None:
        for name, reason in example_manifest.UNCOVERED_COMMANDS.items():
            self.assertTrue(reason.strip(), f"{name} has no reason recorded")

    def test_declared_gaps_are_real_commands(self) -> None:
        for name in example_manifest.UNCOVERED_COMMANDS:
            self.assertIn(name, CANONICAL_COMMANDS)

    def test_ratchet_equals_the_measured_coverage(self) -> None:
        """The ratchet must match reality, not sit below it."""
        measured = len(check_examples.covered_commands())
        self.assertEqual(example_manifest.REQUIRED_COMMAND_COVERAGE, measured)


class ReportTests(unittest.TestCase):
    """The report is what the plan's numbers are regenerated from."""

    def test_report_mentions_every_section(self) -> None:
        text = "\n".join(check_examples.report())
        for heading in ("examples coverage", "per example", "by owning component"):
            self.assertIn(heading, text)

    def test_report_command_line_is_in_range(self) -> None:
        lines = check_examples.report()
        command_line = next(line for line in lines if line.startswith("commands"))
        match = re.search(r"(\d+)\s*/\s*(\d+)", command_line)
        assert match is not None
        covered, total = int(match.group(1)), int(match.group(2))
        self.assertLessEqual(covered, total)
        self.assertEqual(total, len(CANONICAL_COMMANDS))

    def test_uninvoked_plus_covered_is_every_command(self) -> None:
        covered = check_examples.covered_commands()
        uninvoked = set(check_examples.uninvoked_commands())
        self.assertEqual(covered | uninvoked, set(CANONICAL_COMMANDS))
        self.assertEqual(covered & uninvoked, set())


class PureTourTests(unittest.TestCase):
    """The three pure-Python tours must run, and agree with the library.

    These are the only examples that run in full on the host, which makes
    them the only ones whose *output* can be asserted rather than merely
    their presence.  Testing the arithmetic against the library is worth
    more than checking that the file imports: the tours exist to show the
    real semantics, so if the library changes behaviour the tour must
    change with it, and this is what notices.
    """

    #: Entry point each tour exposes, by module name.  The modules guard
    #: their main with ``if __name__ == "__main__"``, which is false when
    #: imported, so the test calls the function rather than relying on
    #: the guard -- that also keeps the test from depending on how the
    #: script is invoked.
    ENTRY: dict[str, str] = {
        "intcodec_tour": "icodec",
        "intfmt_tour": "ifmt",
        "bitops_tour": "btour",
    }

    def _run(self, module: str) -> str:
        """Execute a tour's entry point and capture what it printed."""
        path = pathlib.Path(check_examples._ROOT) / "examples" / "api" / f"{module}.py"
        spec = importlib.util.spec_from_file_location(f"tour_{module}", path)
        assert spec is not None and spec.loader is not None
        loaded = importlib.util.module_from_spec(spec)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            spec.loader.exec_module(loaded)
            getattr(loaded, self.ENTRY[module])()
        return buffer.getvalue()

    def test_intcodec_tour_runs(self) -> None:
        output = self._run("intcodec_tour")
        for heading in (
            "unsigned round trip",
            "signed round trip",
            "range checks",
            "arrays",
            "offsets into one buffer",
        ):
            self.assertIn(heading, output)

    def test_intcodec_tour_reports_the_round_trip_closes(self) -> None:
        output = self._run("intcodec_tour")
        self.assertIn("closed : True", output)

    def test_intcodec_tour_shows_sign_extension(self) -> None:
        """i8 -0x55 read back as unsigned is 171, which is the point."""
        output = self._run("intcodec_tour")
        self.assertIn("as unsigned=", output)
        self.assertIn("171", output)

    def test_intfmt_tour_runs(self) -> None:
        output = self._run("intfmt_tour")
        for heading in ("addresses", "sizes", "the same buffer", "time"):
            self.assertIn(heading, output)

    def test_intfmt_tour_sizes_are_human(self) -> None:
        output = self._run("intfmt_tour")
        self.assertIn("1K", output)
        self.assertIn("1.5K", output)

    def test_bitops_tour_runs(self) -> None:
        output = self._run("bitops_tour")
        for heading in (
            "alignment and orders",
            "field packing",
            "single bits",
            "CPU masks",
            "sign and width",
        ):
            self.assertIn(heading, output)

    def test_bitops_tour_unpacks_the_real_slab_word(self) -> None:
        """The packed counters must decode to what kl-slab details prints."""
        from kernlens.core import BitOps

        counters = (16 << 17) | (16 << 2) | 1
        self.assertEqual(BitOps.extract_bits(counters, 17, 16), 16)
        self.assertEqual(BitOps.extract_bits(counters, 2, 15), 16)
        self.assertEqual(BitOps.extract_bits(counters, 0, 1), 1)

    def test_bitops_tour_round_trip_closes(self) -> None:
        output = self._run("bitops_tour")
        self.assertIn("round trip closes : True", output)

    def test_bitops_tour_sign_extends(self) -> None:
        output = self._run("bitops_tour")
        self.assertIn("sign_extend(0x1f, 5) : -1", output)


class CoreSurfaceCoverageTests(unittest.TestCase):
    """The three primitives are covered completely, and stay that way."""

    def test_bitops_is_fully_covered(self) -> None:
        covered = check_examples.covered_surface()
        groups = check_examples.surface_groups()["BitOps"]
        missing = sorted(c for c, sp in groups.items() if not (sp & covered))
        self.assertEqual(missing, [], f"BitOps uncovered: {missing}")

    def test_intcodec_is_fully_covered(self) -> None:
        covered = check_examples.covered_surface()
        groups = check_examples.surface_groups()["IntCodec"]
        missing = sorted(c for c, sp in groups.items() if not (sp & covered))
        self.assertEqual(missing, [], f"IntCodec uncovered: {missing}")

    def test_intfmt_is_fully_covered(self) -> None:
        covered = check_examples.covered_surface()
        groups = check_examples.surface_groups()["IntFmt"]
        missing = sorted(c for c, sp in groups.items() if not (sp & covered))
        self.assertEqual(missing, [], f"IntFmt uncovered: {missing}")


class CliTests(unittest.TestCase):
    def test_check_exits_zero_on_the_current_tree(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(check_examples.main(["--check"]), 0, out.getvalue())

    def test_report_exits_zero(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(check_examples.main(["--report"]), 0, out.getvalue())

    def test_list_commands_exits_zero(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(
                check_examples.main(["--list-commands"]), 0, out.getvalue()
            )

    def test_modes_are_mutually_exclusive(self) -> None:
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                check_examples.main(["--check", "--report"])

    def test_a_mode_is_required(self) -> None:
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                check_examples.main([])


if __name__ == "__main__":
    unittest.main()