#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Keep the coverage numbers in ``examples/README.md`` from drifting.

The README used to state them by hand, and they had already gone stale:
it said ``facade bound 34/140`` when the measured figure was 51.  That is
the ordinary fate of a number typed into prose -- it is correct on the day
it is written and nobody re-checks it, because doing so means running a
tool and squinting at a table.

So the table is generated.  ``--write`` re-renders the block between the
two markers in the README; ``--check`` re-renders it and fails when the
file differs, which is what CI runs.  Adding an example therefore either
updates the numbers or breaks the build, and neither outcome depends on
anyone remembering.

The numbers themselves come from :mod:`tools.check_examples`, so this
script contains no measurement of its own: it formats what the checker
already derives.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import check_examples  # noqa: E402 - after the path fix above

README = pathlib.Path(__file__).resolve().parent.parent / "examples/README.md"

#: The markers the generated block lives between.  They are HTML comments
#: so they do not render, and they are unique so a stray `--write` cannot
#: append a second table.
START = "<!-- coverage:start -->"
END = "<!-- coverage:end -->"


def _table() -> str:
    """The measured table, as Markdown."""
    groups = check_examples.surface_groups()
    covered = check_examples.covered_surface()
    commands_run = check_examples.covered_commands()
    all_commands = check_examples.canonical_commands()

    lines = [
        "| Component | Covered | Size |",
        "| --- | --- | --- |",
        f"| GDB commands | **{len(commands_run)}** | {len(all_commands)} |",
    ]
    for component in sorted(groups):
        total = len(groups[component])
        hit = sum(1 for spellings in groups[component].values()
                  if spellings & covered)
        # A component at 100% is worth seeing at a glance; anything else
        # is a number, not a score, so it is not emboldened.
        cell = f"**{hit}**" if hit == total else str(hit)
        lines.append(f"| `{component}` | {cell} | {total} |")

    uninvoked = check_examples.uninvoked_commands()
    lines.append("")
    if uninvoked:
        lines.append(
            f"{len(uninvoked)} command(s) have no example: "
            + ", ".join(f"`{name}`" for name in uninvoked)
            + ". Each has a reason in `UNCOVERED_COMMANDS`."
        )
    else:
        lines.append("Every command has an example.")
    return "\n".join(lines)


def _render(text: str) -> str:
    """Replace the block between the markers, leaving the rest alone."""
    before, _, rest = text.partition(START)
    _, _, after = rest.partition(END)
    if not rest:
        raise SystemExit(f"{README} has no {END} marker")
    return f"{before}{START}\n{_table()}\n{END}{after}"


def main(argv: list[str]) -> int:
    write = "--write" in argv
    verify = "--check" in argv
    if write == verify:
        print("pass exactly one of --write / --check", file=sys.stderr)
        return 2
    unknown = {a for a in argv if a not in ("--write", "--check")}
    if unknown:
        print(f"unknown option(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2

    current = README.read_text(encoding="utf-8")
    updated = _render(current)
    if write:
        if updated != current:
            README.write_text(updated, encoding="utf-8")
            print(f"updated the coverage block in {README.name}")
        else:
            print(f"{README.name} already matches the measurement")
        return 0
    if updated != current:
        print(
            "the coverage block in examples/README.md is stale:",
            file=sys.stderr,
        )
        print(
            "  run `uv run python tools/gen_examples_readme.py --write` "
            "and commit the result",
            file=sys.stderr,
        )
        # Show the difference in the terms a reviewer needs: which numbers
        # changed, not a line diff of a Markdown table.
        for line in updated.splitlines():
            if line.startswith("| ") and line not in current:
                print(f"  would become: {line}", file=sys.stderr)
        return 1
    print("the coverage block in examples/README.md matches the measurement")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))