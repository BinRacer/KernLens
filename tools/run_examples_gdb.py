#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Replay every example that needs a target, and record what it printed.

This is the third and last piece of the examples contract.  The other two:

* ``tools/check_examples.py`` — static: does each example reference the
  API it claims?
* ``tests/integration/test_examples_pure.py`` — dynamic, on the host:
  do the ``runs_on="host"`` examples actually run?

Neither can execute an example that needs a live kernel, which is most of
them.  A static check cannot tell that ``slub_cache("dentry")`` now
returns ``None`` on a rebuilt kernel, and the host suite cannot reach
memory at all.  So the remaining half needs a debugger, and that is this.

Run it from GDB, the same way ``tools/tutorial_capture.py`` is run::

    (gdb) source /path/to/KernLens/gdbinit.py
    (gdb) file /path/to/vmlinux
    (gdb) target remote :1234
    (gdb) kl-color off
    (gdb) python exec(open("tools/run_examples_gdb.py").read())

It writes ``tools/examples_capture.json`` and exits with a non-zero
status if any example failed, so it can be used as a gate rather than as
a logging step.  ``--check`` compares against the committed capture
without rewriting it, which is what CI would run if it had a kernel.

Two things are deliberately *not* asserted here:

* **Byte-for-byte output.**  Every example prints addresses, and the
  KASLR slide -- and therefore every direct-map and vmemmap address --
  changes on each boot.  Comparing text would fail on a different boot
  for a reason that has nothing to do with the code.  What is compared is
  the *shape*: exit status, the section headings, and the absence of the
  markers this harness adds for a crash.
* **That a command printed the right thing.**  That is the tutorial's
  job, and it is already frozen in ``tools/tutorial_capture.json``.
  Here the question is only "did the example survive contact with a
  real kernel".
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sys

#: Directory holding this script.  ``__file__`` is absent when the file is
#: run through ``exec(open(...).read())``, which is how GDB is told to load
#: it, so the path comes from the environment instead and defaults to the
#: repository's ``tools/`` directory.
_TOOLS = pathlib.Path(os.environ.get("KERNLENS_TOOLS", "tools")).resolve()

#: Make the manifest importable.  ``exec()`` of a file's text does not put
#: that file's directory on ``sys.path`` the way running it as a script
#: would, so this has to be done by hand -- the same reason
#: ``tutorial_capture.py`` reads ``KERNLENS_TOOLS``.
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import example_manifest  # noqa: E402 - after the path fix above

#: Where the recorded run is written.
CAPTURE = _TOOLS / "examples_capture.json"

#: Punctuation a section heading is made of, stripped before comparison.
_HEADING_JUNK = re.compile(r"^[=\-\s]+|[=\-\s]+$")


#: One or more hex digits, with an optional ``0x``.  Headings embed
#: addresses and offsets that change on every boot.
_HEX = re.compile(r"0x[0-9a-fA-F]+|\b[0-9a-fA-F]{8,}\b")

#: A decimal number, which covers counts and indices.
_DECIMAL = re.compile(r"\b\d+\b")


def _stable(title: str) -> str:
    """A heading with the per-boot values removed.

    This is the fix for a real false negative: the shape digest used to
    include the headings verbatim, so a *different boot* reported a
    mismatch on ``kernel identity (slide +0x16200000)`` -- because the
    slide had changed, which is the one thing guaranteed to change.  A
    check that fails for that reason is worse than no check: it teaches
    the reader to ignore it.

    What is left is the part a person wrote, which is the part that should
    not move when the code is unchanged.
    """
    return _DECIMAL.sub("N", _HEX.sub("H", title))


def _headings(text: str) -> list[str]:
    """The section titles an example printed, in order.

    Both heading styles in the tree are recognised -- ``=== title ===``
    from ``_section()`` and ``--- title ---`` from the banner -- so an
    example is free to choose either without updating a table here.

    Values are replaced with placeholders: see :func:`_stable`.
    """
    found: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not (
            stripped.startswith("===")
            or stripped.startswith("---")
        ):
            continue
        title = _HEADING_JUNK.sub("", stripped.strip("=-"))
        if title:
            found.append(_stable(title))
    return found


def _invocations() -> list[tuple[str, list[str]]]:
    """The GDB-invocation form of every example that needs a target.

    Derived from the manifest, not listed again here.  A second list would
    be a second thing to keep in step, and the whole reason
    ``tools/example_manifest.py`` exists is that the first list rotted.

    The invocation is ``probe`` when the row declares one, and otherwise
    the example's own registered command.  The override exists because
    several of these commands are not meaningful bare: some raise without
    an argument, and some install a breakpoint whose absence of output
    proves nothing.
    """
    cases: list[tuple[str, list[str]]] = []
    for example in example_manifest.EXAMPLES:
        if example.runs_on != "gdb" or example.kind != "script":
            continue
        if example.probe == "-":
            # Opted out on purpose: this command installs breakpoints and
            # waits for the kernel to reach them, which in a batch run
            # means blocking until the harness is killed.  Sourcing the
            # file still happens below, so a crash on load is caught.
            continue
        invocation = example.probe or _registered_command(example.path)
        if invocation is None:
            # A GDB-only example that registers no command runs at source
            # time.  Record the sourcing so a crash in it is still caught.
            cases.append((f"source {example.path}", [f"source {example.path}"]))
            continue
        cases.append((f"source {example.path}", [invocation]))
    return cases


def _registered_command(path: str) -> str | None:
    """The command name an example registers, if it registers one.

    ``gdb.Command`` registers itself in ``__init__``, so the name lives in
    a ``super().__init__("<name>", gdb.COMMAND_*)`` call rather than in
    the class statement or in a decorator.  A file that only defines the
    class and never instantiates it registers nothing -- the commentary in
    ``kernel_facts_tour.py`` calls that the most common mistake with this API,
    and it is why this looks for the name in the string literal rather
    than trusting the class to exist.
    """
    source_path = _TOOLS.parent / path
    if not source_path.is_file():
        return None
    text = source_path.read_text(encoding="utf-8")
    match = re.search(
        r'super\(\)\.__init__\(\s*"([\w-]+)"\s*,\s*gdb\.COMMAND_', text,
    )
    return match.group(1) if match else None


def _run(cases: list[tuple[str, list[str]]]) -> list[dict]:
    """Source each example, run its command, keep failures as data."""
    import gdb  # noqa: PLC0415 - only importable inside GDB

    results: list[dict] = []
    for source, invocations in cases:
        try:
            gdb.execute(source, to_string=True)
        except Exception as exc:  # noqa: BLE001 - reported verbatim
            results.append({
                "source": source,
                "invocation": source,
                "output": f"<EXCEPTION> {type(exc).__name__}: {exc}",
            })
            continue
        for invocation in invocations:
            try:
                output = gdb.execute(invocation, to_string=True)
            except Exception as exc:  # noqa: BLE001 - reported verbatim
                output = f"<EXCEPTION> {type(exc).__name__}: {exc}"
            results.append({
                "source": source,
                "invocation": invocation,
                "output": output,
            })
    return results


def _failures(results: list[dict]) -> list[str]:
    """Reasons a run is not acceptable, in the words of the output."""
    problems: list[str] = []
    for row in results:
        output: str = row["output"]
        name = row["invocation"]
        if output.startswith("<EXCEPTION>"):
            problems.append(f"{name}: raised -- {output.splitlines()[0]}")
            continue
        # An example that prints nothing has not demonstrated anything,
        # and would otherwise look like a pass.
        if not output.strip():
            problems.append(f"{name}: printed nothing")
            continue
        # A traceback that GDB swallowed into the output is still a
        # failure; `to_string=True` does not turn one into an exception.
        if "Traceback (most recent call last)" in output:
            last = output.strip().splitlines()[-1]
            problems.append(f"{name}: traceback -- {last}")
    return problems


def _digest(rows: list[dict]) -> str:
    """A fingerprint of the *shape* of a run, not of its addresses.

    Addresses change every boot, so a hash over the raw text would differ
    for a reason unrelated to the code.  Hashing the headings and the
    exit status gives something a ``--check`` can compare across boots
    while still noticing that a section disappeared.
    """
    shape = json.dumps(
        [
            {
                "invocation": row["invocation"],
                "headings": _headings(row["output"]),
                "ok": not row["output"].startswith("<EXCEPTION>"),
            }
            for row in rows
        ],
        sort_keys=True,
    )
    return hashlib.sha256(shape.encode("utf-8")).hexdigest()[:16]


def write(results: list[dict]) -> None:
    """Record the run, then report what failed."""
    CAPTURE.write_text(
        json.dumps(
            {
                "shape": _digest(results),
                "examples": [
                    {
                        "source": row["source"],
                        "invocation": row["invocation"],
                        "headings": _headings(row["output"]),
                        "ok": not row["output"].startswith("<EXCEPTION>"),
                    }
                    for row in results
                ],
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"recorded {len(results)} run(s) -> {CAPTURE}")


def check(results: list[dict]) -> int:
    """Compare this run's shape against the recorded one."""
    if not CAPTURE.is_file():
        print(f"no recorded run at {CAPTURE}; run this without --check first")
        return 1
    recorded = json.loads(CAPTURE.read_text(encoding="utf-8"))
    actual = _digest(results)
    if actual == recorded["shape"]:
        print(f"{len(results)} run(s) match the recorded shape ({actual})")
        return 0
    # Name the sections that moved, because the digest cannot.
    before = {
        row["invocation"]: row["headings"] for row in recorded["examples"]
    }
    after = {row["invocation"]: _headings(row["output"]) for row in results}
    print("the examples do not match the recorded run:")
    for invocation in before.keys() | after.keys():
        old = before.get(invocation, [])
        new = after.get(invocation, [])
        if old != new:
            print(f"  {invocation}:")
            print(f"    recorded: {old}")
            print(f"    now     : {new}")
    return 1


#: Set by ``main()`` so GDB can report the status without a traceback.
#: ``raise SystemExit`` inside a ``gdb.execute``-driven ``exec`` surfaces
#: as "Python Exception <class 'SystemExit'>" rather than as an exit, which
#: reads like a crash next to a run that succeeded.  GDB is told to carry
#: on either way; the status is in ``LAST_STATUS``.
LAST_STATUS = 0


def main(argv: list[str]) -> int:
    global LAST_STATUS
    status = _main(argv)
    LAST_STATUS = status
    return status


def _main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    verify = "--check" in argv
    unknown = {a for a in argv if a not in ("--check", "--record", "--help", "-h")}
    if unknown:
        print(f"unknown option(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2

    results = _run(_invocations())
    problems = _failures(results)
    if problems:
        print(f"{len(problems)} example(s) failed:")
        for problem in problems:
            print(f"  {problem}")
        return 1

    if verify:
        return check(results)
    write(results)
    return 0


#: The entry point for the ``exec(open(...).read())`` workflow.
#:
#: `tutorial_capture.py` ends with a bare `main()`, which works because
#: nothing imports it.  This module *is* imported -- by a test that pins
#: the parts that can be checked without a kernel -- so the top-level call
#: has to be conditional.  The condition is "was this run as a program, or
#: is a debugger present", which is true in both supported contexts.
#:
#: Arguments come from ``KERNLENS_EXAMPLES_ARGV`` rather than ``sys.argv``
#: because GDB owns ``sys.argv`` and editing it would affect the debugger.
#:
#: Nothing is raised.  A ``SystemExit`` escaping ``exec`` prints as
#: "Python Exception <class 'SystemExit'>" in the middle of a run that
#: otherwise succeeded, which reads like a crash; the status is left in
#: ``LAST_STATUS`` for the caller -- a shell via ``sys.exit``, or GDB via
#: the printed line.
if __name__ == "__main__" or "gdb" in sys.modules:
    LAST_STATUS = _main(os.environ.get("KERNLENS_EXAMPLES_ARGV", "").split())
    print(f"examples: status {LAST_STATUS}")
    if "gdb" not in sys.modules:
        sys.exit(LAST_STATUS)
