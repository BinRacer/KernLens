"""Tests for ``tools/check_examples.py`` and its manifest.

The checker exists so that a coverage claim about ``examples/`` can fail
a build.  These tests therefore do two jobs:

* pin the guarantees the checker makes (a claim without the code fails,
  a command that is only mentioned does not count as executed, the
  ratchet cannot be lowered silently), and
* pin the numbers that ``examples/README.md`` advertises, so the published
  coverage cannot drift from the tree the way hand-written prose does.

The negative tests are the important ones.  A checker that only ever
passes is indistinguishable from one that does nothing -- the tutorial
pipeline earned its trust the same way, by being shown to fail when a
page was hand-edited.
"""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import pathlib
import re
import tempfile
import unittest

import check_examples
import example_manifest
import gen_examples_readme
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
        # Pinned on purpose: the examples' coverage claim is a fraction
        # of this surface, so a binding added without an example would
        # quietly lower the denominator.  `field_value` was added when
        # `kl-read-field` stopped assuming every field is an integer.
        bound, free = check_examples.facade_bindings()
        self.assertEqual(len(bound), 141)
        self.assertEqual(len(free), 69)
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
            path="examples/api/hello_sample.py",
            purpose="negative test",
            surface=("KAddr.is_vmalloc",),
            readme="examples/api/README.md",
        )
        failures = self._patched((broken,))
        self.assertEqual(len(failures), 1)
        self.assertIn("never references it", str(failures[0]))

    def test_unknown_surface_name_is_reported(self) -> None:
        broken = example_manifest.Example(
            path="examples/api/hello_sample.py",
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
            path="examples/api/installed_api_tour.py",
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

        ``bits_tour.py`` mentions ``kl-cpu`` in a printed annotation --
        "(kl-cpu prints this as the 'Online:' range)" -- but only ever
        executes ``kl-bits``.  That is exactly the distinction this
        checker exists to draw.
        """
        broken = example_manifest.Example(
            path="examples/api/bits_tour.py",
            purpose="negative test",
            commands=("kernlens-cpu",),
            readme="examples/api/README.md",
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
            path="examples/api/hello_sample.py",
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
        path = self._write('import gdb\ngdb.execute("kernlens-status")\n')
        self.assertEqual(
            check_examples.executed_commands(path), {"kernlens-status"}
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


class RunnerDeclarationTests(unittest.TestCase):
    """The manifest's ``runs_on`` claim is checked, and can fail.

    ``runs_on="host"`` is the promise ``tests/integration/
    test_examples_pure.py`` relies on to know what to execute.  These
    tests pin the checks that make the promise safe to depend on -- the
    schema check, the import check, and the guard check -- each against a
    temporary tree, because the real one is supposed to pass.
    """

    def _tree(self, body: str) -> pathlib.Path:
        """Write ``body`` as an example in a scratch directory tree."""
        root = pathlib.Path(tempfile.mkdtemp())
        target = root / "examples/api/scratch.py"
        target.parent.mkdir(parents=True)
        target.write_text(body, encoding="utf-8")
        (root / "examples/api/README.md").write_text(
            "[scratch](scratch.py)\n", encoding="utf-8",
        )
        self.addCleanup(lambda: __import__("shutil").rmtree(root, True))
        return root

    def _failures(self, root: pathlib.Path, **kwargs: object) -> list[str]:
        """Run the runner check against a scratch manifest."""
        example = example_manifest.Example(
            path="examples/api/scratch.py",
            purpose="scratch",
            readme="examples/api/README.md",
            **kwargs,  # type: ignore[arg-type]
        )
        original_root = check_examples._ROOT
        original = example_manifest.EXAMPLES
        try:
            check_examples._ROOT = root
            example_manifest.EXAMPLES = (example,)
            return [f.message for f in check_examples.check_runner_declarations()]
        finally:
            check_examples._ROOT = original_root
            example_manifest.EXAMPLES = original

    def test_a_host_claim_with_an_unconditional_gdb_import_fails(self) -> None:
        root = self._tree("import gdb\nprint('hi')\n")
        messages = self._failures(root, runs_on="host")
        self.assertTrue(
            any("without a fallback" in m for m in messages), messages,
        )

    def test_a_host_claim_reaching_for_kdbg_unguarded_fails(self) -> None:
        root = self._tree("print(kdbg.nr_cpus())\n")
        messages = self._failures(root, runs_on="host")
        self.assertTrue(
            any("outside a try" in m for m in messages), messages,
        )

    def test_the_same_call_inside_a_nameerror_guard_is_accepted(self) -> None:
        """Which is the whole point: the handler makes it safe, not the call."""
        root = self._tree(
            "try:\n"
            "    n = kdbg.nr_cpus()\n"
            "except NameError:\n"
            "    n = 1\n"
            "print(n)\n"
        )
        self.assertEqual(self._failures(root, runs_on="host"), [])

    def test_a_narrow_handler_does_not_count_as_safe(self) -> None:
        """`gdb.error` would let a missing target escape on the host."""
        root = self._tree(
            "try:\n"
            "    n = kdbg.nr_cpus()\n"
            "except gdb.error:\n"
            "    n = 1\n"
            "print(n)\n"
        )
        self.assertTrue(self._failures(root, runs_on="host"))

    def test_an_unknown_runner_fails(self) -> None:
        root = self._tree("print('hi')\n")
        messages = self._failures(root, runs_on="windows")
        self.assertTrue(any("neither 'host' nor 'gdb'" in m for m in messages))

    def test_argv_on_a_gdb_example_fails(self) -> None:
        root = self._tree("print('hi')\n")
        messages = self._failures(root, argv=("--flag",))
        self.assertTrue(any("host-run example" in m for m in messages))

    def test_a_config_file_cannot_claim_the_host(self) -> None:
        root = self._tree("")
        messages = self._failures(root, kind="config", runs_on="host")
        self.assertTrue(any("not executable" in m for m in messages))


class GeneratedCoverageTests(unittest.TestCase):
    """The README's coverage block is generated, and provably so.

    The block used to be typed by hand and had already gone stale.  Now it
    is rendered from the measurement, so the only way it can be wrong is
    if nobody re-ran the generator -- which is what these tests notice.
    """

    def test_the_block_matches_the_measurement(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(gen_examples_readme.main(["--check"]), 0)

    def test_the_block_lists_every_component(self) -> None:
        """A component missing from the table is a silent coverage hole."""
        text = gen_examples_readme._table()
        for component in check_examples.surface_groups():
            self.assertIn(f"`{component}`", text)

    def test_a_stale_block_fails(self) -> None:
        """Editing a number in the README must break the check."""
        original = gen_examples_readme._table
        gen_examples_readme._table = lambda: "| Component | Covered | Size |"
        try:
            with contextlib.redirect_stderr(io.StringIO()) as err:
                status = gen_examples_readme.main(["--check"])
        finally:
            gen_examples_readme._table = original
        self.assertEqual(status, 1)
        self.assertIn("stale", err.getvalue())

    def test_one_mode_is_required(self) -> None:
        """Neither zero modes nor both: the two would disagree silently."""
        for argv in ([], ["--write", "--check"]):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(gen_examples_readme.main(argv), 2)
            self.assertIn("exactly one", err.getvalue())


class ExampleNameTests(unittest.TestCase):
    """Every example filename says what kind of example it is.

    Enforced by ``check_examples.check_example_names()``.  The negative
    cases matter more than the positive one: a rule that only ever passes
    is indistinguishable from a rule that is not applied, and this tree
    had four parallel conventions before the rule existed.
    """

    def test_the_current_tree_classifies_every_example(self) -> None:
        self.assertEqual(check_examples.check_example_names(), [])

    def test_an_unclassified_name_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "examples/api").mkdir(parents=True)
            (root / "examples/api/whatever.py").write_text(
                "# probe\n", encoding="utf-8",
            )
            failures = check_examples.check_example_names(root)
            self.assertEqual(len(failures), 1, failures)
            self.assertIn("does not end with a kind", failures[0].message)

    def test_a_kind_without_a_subject_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "examples/api").mkdir(parents=True)
            (root / "examples/api/_tour.py").write_text(
                "# probe\n", encoding="utf-8",
            )
            failures = check_examples.check_example_names(root)
            self.assertEqual(len(failures), 1, failures)
            self.assertIn("no subject", failures[0].message)

    def test_every_kind_in_the_rule_is_used_by_a_real_file(self) -> None:
        """No aspirational kinds: the list describes the tree.

        A kind nobody uses is either a file that was never written or a
        classification that stopped being true, and both make
        ``docs/naming.md`` read as a plan rather than a description.
        """
        used = set()
        for path in (check_examples._ROOT / "examples").rglob("*.py"):
            for kind in check_examples.EXAMPLE_KINDS:
                if path.stem.endswith(kind):
                    used.add(kind)
        self.assertEqual(
            sorted(set(check_examples.EXAMPLE_KINDS) - used), [],
            "kind(s) declared in EXAMPLE_KINDS that no example uses",
        )


class ExampleCaptureShapeTests(unittest.TestCase):
    """The recorded run's shape must not depend on the boot.

    ``tools/run_examples_gdb.py`` compares a live run against the recorded
    one.  Its first version hashed the section headings verbatim, so a
    different boot reported a mismatch on
    ``kernel identity (slide +0x16200000)`` -- because the slide had
    changed, which is the one thing that always changes.  A check that
    fails for that reason teaches the reader to ignore it, so the
    normalization is pinned here rather than trusted.

    These run on the host: the heading extractor takes text and returns
    text, and nothing about it needs a debugger.
    """

    def test_addresses_and_offsets_become_placeholders(self) -> None:
        import run_examples_gdb

        self.assertEqual(
            run_examples_gdb._headings(
                "=== kernel identity (slide +0x16200000) ===\n"
            ),
            ["kernel identity (slide +H)"],
        )
        self.assertEqual(
            run_examples_gdb._headings(
                "--- 4. which cache owns 0xffff8b02c66bfc00 "
                "(kl-slab contains) ---\n"
            ),
            ["N. which cache owns H (kl-slab contains)"],
        )

    def test_two_boots_produce_the_same_shape(self) -> None:
        import run_examples_gdb

        boot_a = (
            "=== kernel identity (slide +0x16200000) ===\n"
            "=== kmalloc-1k cpu 0: the chain ===\n"
        )
        boot_b = (
            "=== kernel identity (slide +0x23000000) ===\n"
            "=== kmalloc-1k cpu 0: the chain ===\n"
        )
        self.assertEqual(
            run_examples_gdb._headings(boot_a),
            run_examples_gdb._headings(boot_b),
        )

    def test_a_renamed_section_still_differs(self) -> None:
        """Normalization must not have flattened the thing being checked."""
        import run_examples_gdb

        self.assertNotEqual(
            run_examples_gdb._headings("=== chain depth and the partial list ===\n"),
            run_examples_gdb._headings("=== depth notes ===\n"),
        )


class RecordedCommandNameTests(unittest.TestCase):
    """The record may only name commands the registry still publishes.

    ``tools/check_example_capture.py`` compares the recorded headings
    against the example sources, and to do that honestly it throws away
    the parenthesised asides -- they hold addresses and cache names that
    only exist at run time.  The side effect was that it threw away the
    command name too, which is the part that goes stale: the record named
    ``kl-klookup``, ``kl-pagewalk``, ``kl-pte``, ``kl-chain`` and
    ``kl-kbase -v`` for a whole release after those spellings were
    merged, and every heading passed because the prose around them was
    unchanged.

    Measured with the stale record and the old checker: 43 headings
    "fine", exit 0.  The names are checked against
    ``tools/tutorial_meta.json``, which is the registry snapshot, because
    CI has no ``gdb`` to import the registry itself.
    """

    def setUp(self) -> None:
        import check_example_capture

        self.tool = check_example_capture
        self.known = check_example_capture._known_commands()

    def test_the_snapshot_yields_the_whole_registry(self) -> None:
        # Both spellings of every command, so neither form is reported.
        self.assertEqual(len(self.known), 2 * len(CANONICAL_COMMANDS) + 1)
        self.assertIn("kl-help", self.known)
        self.assertIn("kernlens-help", self.known)

    def test_a_published_name_passes(self) -> None:
        for heading in (
            "N. classify (kl-addr)",
            "N. decode one entry (kl-pt --entry)",
            "N. the same walk, pwndbg format (kl-walk --style pwndbg)",
            "N. discover the slide from the target (kl-base --verbose)",
        ):
            with self.subTest(heading=heading):
                self.assertEqual(self.tool._bad_commands(heading, self.known), [])

    def test_a_spelling_that_was_merged_away_fails(self) -> None:
        # Each of these is in the record that shipped, and each one is
        # only visible once the asides are no longer discarded.
        for heading, stale in (
            ("N. substring search (kl-klookup init_task)", "kl-klookup"),
            ("N. the same walk, pwndbg format (kl-pagewalk)", "kl-pagewalk"),
            ("N. decode one entry (kl-pte)", "kl-pte"),
            ("N. the current stack (kl-bt, kl-chain)", "kl-chain"),
            ("N. discover the slide (kl-kbase -v)", "kl-kbase"),
            ("N. classify + translate (kl-page)", "kl-page"),
        ):
            with self.subTest(heading=heading):
                self.assertEqual(
                    self.tool._bad_commands(heading, self.known), [stale],
                )

    def test_a_name_outside_the_aside_is_left_to_the_prose_check(self) -> None:
        # ``_template`` keeps text outside the parentheses, so a command
        # named there is already compared against the source; checking it
        # twice would report one problem under two descriptions.
        self.assertEqual(
            self.tool._bad_commands("N. kl-klookup is gone", self.known), [],
        )

    def test_the_committed_record_passes(self) -> None:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            status = self.tool.check()
        self.assertEqual(status, 0, buffer.getvalue())


class FreelistWalkRegressions(unittest.TestCase):
    """Three defects in ``api/freelist_walk.py`` that only a target showed.

    The file needs a live GDB, so it cannot be executed here the way the
    pure tours can -- the stubbed ``gdb`` in the test environment has no
    memory to read.  What *can* be asserted is the shape of the code that
    went wrong, because each defect was a wrong-but-plausible expression
    rather than a typo, and each one silently produced confident output.

    These are deliberately narrow.  They pin the specific mistake and the
    reason it was a mistake; anything broader would be a second
    implementation of the example, and would fail for unrelated reasons.
    """

    PATH = pathlib.Path(check_examples._ROOT) / "examples/api/freelist_walk.py"

    def _tree(self) -> ast.Module:
        return ast.parse(self.PATH.read_text(encoding="utf-8"))

    def _source(self) -> str:
        return self.PATH.read_text(encoding="utf-8")

    def test_config_value_is_not_used_as_a_boolean(self) -> None:
        """`config_get()` returns "y"/"n"/"m"/None, never a bool.

        Testing the return for truthiness reported every option set to
        ``n`` as ``y``.  On this target that claimed freed objects are
        zeroed while the chain was visibly intact -- the one section
        written to prevent that misreading, giving it.
        """
        tree = self._tree()
        bool_tested: list[int] = []
        for node in ast.walk(tree):
            # `if kdbg.kconfig_get(...)` / `x = kdbg.kconfig_get(...)`
            # followed by `if x` -- catch the direct form, which is the
            # one that was written and the one that reads as correct.
            if isinstance(node, ast.If):
                for sub in ast.walk(node.test):
                    if not isinstance(sub, ast.Call):
                        continue
                    func = sub.func
                    name = getattr(func, "attr", getattr(func, "id", ""))
                    if name == "kconfig_get":
                        bool_tested.append(node.lineno)
        self.assertEqual(
            bool_tested, [],
            "kconfig_get() returns a string; only `is None` separates "
            "an option that is off from one missing from the map",
        )
        # The value is compared against None, which is the only test that
        # distinguishes "off" from "not in the map".
        self.assertIn("if value is None:", self._source())

    def test_cpu_count_sentinel_is_handled(self) -> None:
        """`nr_cpus()` returns -1 on failure, and `range(-1)` is empty.

        That skipped every chain *and* indexed ``cpus[0]``, so a single
        unreadable symbol turned the whole example into a stack trace.
        """
        source = self._source()
        self.assertIn("total = kdbg.nr_cpus()", source)
        self.assertIn("if total <= 0:", source)
        self.assertNotIn("list(range(kdbg.nr_cpus()))", source)

    def test_decoded_link_is_checked_against_its_own_cache(self) -> None:
        """A link into another cache decodes fine and is still wrong.

        `slab_object()` answers "is this a slab object" *and* which cache
        owns it.  Keeping only the first answer let a stale link that
        happens to point at another cache's slab pass the check.
        """
        source = self._source()
        self.assertIn("resolved = kdbg.slab_object(nxt)", source)
        self.assertIn("resolved[1].address != cache.address", source)
        self.assertNotIn("if not kdbg.slab_object(nxt):", source)

    def test_chain_is_bounded_by_the_slab_object_count(self) -> None:
        """The walk must stop when the chain outlives the slab.

        Both the module docstring and `walk()`'s own docstring promised
        this stop condition, and neither claimed binding list mentioned
        it -- so it was documented and absent.  A corrupted freelist that
        still points at readable slab memory is exactly the case it
        catches, and the only one of the two original stops that misses
        it.
        """
        source = self._source()
        self.assertIn("depth >= objects", source)
        self.assertIn("longer than the slab", source)


if __name__ == "__main__":
    unittest.main()