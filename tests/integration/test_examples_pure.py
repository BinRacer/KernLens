"""Run every example that claims to work without a debugger.

``tools/check_examples.py`` verifies that an example *references* the API
it claims.  That is a static check, and a static check cannot notice that
a file imports a name that no longer exists, that two function bodies
were concatenated by a bad edit, or that a fallback branch raises on the
very path it exists to protect.  All three have happened in this tree.

This suite is the other half: it executes each ``runs_on="host"`` row for
real and fails if the file exits non-zero.  The manifest is the only
input, so adding an example there is what puts it under test -- and a
file that quietly stops being portable fails here rather than keeping a
claim nobody checks.

Everything is asserted on *output*, not on exit status alone.  A script
that prints nothing and returns 0 would pass an exit-status check while
being useless, so each row also declares a heading its output must
contain.  Those headings are the section titles the files print, which
means renaming a section is a deliberate act that updates this table.

The examples that need a live target are covered by
``tools/run_examples_gdb.py`` instead; that one is opt-in because CI has
no kernel to attach to.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import unittest

import example_manifest

#: Repository root, derived from this file rather than the cwd.
_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Section headings each host-runnable example must print.
#:
#: Kept here rather than in the manifest because it is a test's job to
#: say what "worked" looks like; the manifest says where a file runs, not
#: what it should say.  Keyed by manifest path so a rename fails loudly.
EXPECTED_OUTPUT: dict[str, tuple[str, ...]] = {
    "examples/api/hello.py": (
        "address",
        "popcount",
        "canonical 48",
        "4-level",
    ),
    "examples/api/slab_snapshot.py": (
        "slab",
        "cache",
    ),
    "examples/api/intcodec_tour.py": (
        "unsigned round trip",
        "signed round trip",
        "range checks",
        "arrays",
        "offsets into one buffer",
    ),
    "examples/api/intfmt_tour.py": (
        "addresses",
        "sizes",
        "time",
    ),
    "examples/api/bitops_tour.py": (
        "alignment and orders",
        "field packing",
        "single bits",
        "CPU masks",
        "sign and width",
    ),
}


class HostExampleTests(unittest.TestCase):
    """One test per row, generated so the manifest is the only list."""

    def _run(self, example: example_manifest.Example) -> subprocess.CompletedProcess[str]:
        """Execute an example in a fresh interpreter, as a reader would.

        A subprocess rather than an in-process import, deliberately: the
        failure this suite has to catch is "the script does not run", and
        an import inside the test process would share its state -- the
        stub ``gdb`` module the rest of the suite installs, for one.  A
        separate interpreter is also what a reader has.
        """
        path = _ROOT / example.path
        env = dict(os.environ)
        # `hello.py` documents a `PYTHONPATH=src` fallback, so the source
        # tree must be importable the same way the README says it is.
        env["PYTHONPATH"] = str(_ROOT / "src")
        return subprocess.run(
            [sys.executable, str(path), *example.argv],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
            check=False,
        )

    def test_every_host_row_is_covered_by_this_file(self) -> None:
        """A new ``runs_on="host"`` row must declare what it prints.

        Without this, adding a host-runnable example to the manifest would
        silently do nothing: the generated tests iterate over the manifest,
        but ``EXPECTED_OUTPUT`` is what each one asserts.
        """
        declared = {
            e.path for e in example_manifest.EXAMPLES if e.runs_on == "host"
        }
        self.assertEqual(
            sorted(declared - set(EXPECTED_OUTPUT)), [],
            "host-runnable example(s) with no expected output declared",
        )
        self.assertEqual(
            sorted(set(EXPECTED_OUTPUT) - declared), [],
            "expected output declared for a file that does not claim "
            "runs_on='host'",
        )

    def test_expected_output_exceeds_exit_status(self) -> None:
        """Every declared row must assert something.

        An empty tuple would make the generated test below pass on a
        script that prints nothing, which is the failure mode this suite
        exists to prevent -- so the table itself is checked.
        """
        for path, headings in EXPECTED_OUTPUT.items():
            self.assertTrue(headings, f"{path} declares no heading to check")

    def test_hello_py_names_are_available_outside_gdb(self) -> None:
        """The smallest example is the one that proves the fallback works.

        `hello.py` is the file the README tells a new reader to start
        with, and its whole point is that the four calls it makes give the
        same answer with and without a debugger.  If this test fails, the
        first thing anyone tries is broken.
        """
        example = next(
            e for e in example_manifest.EXAMPLES
            if e.path == "examples/api/hello.py"
        )
        result = self._run(example)
        self.assertEqual(result.returncode, 0, result.stderr)
        for heading in EXPECTED_OUTPUT[example.path]:
            self.assertIn(heading, result.stdout)


def _make_test(example: example_manifest.Example) -> None:
    """Attach one test method per host-runnable example."""

    def test(self: HostExampleTests) -> None:
        result = self._run(example)
        # A non-zero exit is reported with the tail of stderr, because a
        # traceback's *last* line is the one that says what broke.
        tail = "\n".join(result.stderr.strip().splitlines()[-8:])
        self.assertEqual(
            result.returncode, 0,
            f"{example.path} exited {result.returncode}\n{tail}",
        )
        self.assertTrue(
            result.stdout.strip(),
            f"{example.path} printed nothing",
        )
        for heading in EXPECTED_OUTPUT[example.path]:
            self.assertIn(
                heading, result.stdout,
                f"{example.path} output is missing {heading!r}",
            )

    test.__name__ = "test_" + example.path.replace("/", "_").removesuffix(".py")
    test.__doc__ = f"{example.path} runs on the host and prints its sections."
    setattr(HostExampleTests, test.__name__, test)


for _example in example_manifest.EXAMPLES:
    if _example.runs_on == "host" and _example.path in EXPECTED_OUTPUT:
        _make_test(_example)


if __name__ == "__main__":
    unittest.main()