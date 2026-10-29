#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Check the recorded GDB run against the tree, without a debuggee.

``tools/run_examples_gdb.py`` produces ``tools/examples_capture.json`` by
actually running every target-dependent example.  Reproducing that needs
a kernel, which CI does not have.  What CI *can* do is check the cheaper
half of the same claim: that the sections the record says each example
printed still exist in the source that printed them.

That is worth doing because the failure it catches is the common one.  An
example is edited -- a section renamed, a section deleted, a function
pulled out and not re-called -- and the record silently becomes a
description of a file that no longer exists.  Nobody would notice until
someone next ran the harness on a kernel, which is rare.  A renamed
heading is exactly what `--check` reported the last time a section moved,
so this check catches that class of change on every push instead.

The check is deliberately one-directional: every heading in the record
must still appear somewhere in its example's source.  It does *not*
require the reverse, because an example that gained a section is fine and
will simply produce a new record next time the harness runs.  Failing on
that would make adding a section to an example a two-step commit for no
benefit.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

_TOOLS = pathlib.Path(__file__).resolve().parent
_ROOT = _TOOLS.parent
CAPTURE = _TOOLS / "examples_capture.json"


def _load() -> dict[str, list[dict]]:
    """The record, grouped by the example that produced it."""
    data = json.loads(CAPTURE.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = {}
    for row in data["examples"]:
        grouped.setdefault(row["source"], []).append(row)
    return grouped


def _source_of(name: str) -> pathlib.Path | None:
    """``"source examples/api/x.py"`` -> the path, if it is a file."""
    parts = name.split()
    if len(parts) != 2 or parts[0] != "source":
        return None
    path = _ROOT / parts[1]
    return path if path.is_file() else None


#: A run of words that can only have been written by hand: letters, spaces
#: and the punctuation that appears inside a phrase.  Anything with a hex
#: address, a decimal number or a bracket is excluded, because those are
#: produced by the f-string and do not appear in the source.
_PROSE = re.compile(r"[A-Za-z][A-Za-z ,'\-]{9,}")

#: The placeholders ``run_examples_gdb`` substitutes for per-boot values.
#: They are not in any source file, so they have to be removed before the
#: remaining text is looked for there.
_PLACEHOLDER = re.compile(r"\b[HN]\b")

#: A parenthesised aside, which in these headings is a command line or an
#: address and is therefore *never* verbatim in the source: the cache name
#: inside ``kl-slab info {name} -v`` only exists at run time.
_ASIDE = re.compile(r"\([^)]*\)")

#: A ``kl-*``/``kernlens-*`` spelling inside an aside.  The rest of the
#: aside is runtime text, but a command name is not: it has to be a name
#: the registry actually publishes, or the record is describing a command
#: that no longer exists.
_COMMAND = re.compile(r"\b(?:kl|kernlens)-[a-z0-9][a-z0-9-]*")

#: Names the record is allowed to use, read from the metadata snapshot
#: rather than from the live registry (which needs ``gdb``).
_META = _TOOLS / "tutorial_meta.json"


def _known_commands() -> set[str]:
    """Every canonical name and alias the registry publishes.

    ``tutorial_meta.json`` is generated from that registry, so it is a
    faithful stand-in for CI, which has no debugger.
    """
    names: set[str] = set()
    if not _META.is_file():  # pragma: no cover - the file is committed
        return names
    for entry in json.loads(_META.read_text(encoding="utf-8")):
        names.add(entry["name"])
        names.update(entry.get("aliases") or ())
    return names


def _bad_commands(heading: str, known: set[str]) -> list[str]:
    """Command spellings in *heading* that the registry does not publish.

    This is the half the prose check cannot see.  ``_template`` strips
    the asides on purpose -- their contents are mostly runtime text --
    but the command name inside one is exactly what goes stale: the
    record named ``kl-klookup``, ``kl-pagewalk``, ``kl-pte`` and
    ``kl-kbase`` for a whole release after those spellings were merged,
    and every heading still passed because the words around them were
    unchanged.  Measured: with the stale record, the prose half reported
    43 headings fine.
    """
    if not known:
        return []
    found: list[str] = []
    for aside in _ASIDE.findall(heading):
        for name in _COMMAND.findall(aside):
            if name not in known:
                found.append(name)
    return found


def _template(heading: str) -> str:
    """The longest fragment of a runtime heading that came from the source.

    Headings are built by f-strings, so the source contains the literal
    text *between* the substitutions.  Three kinds of material have to be
    discounted before the comparison is honest:

    * the parenthesised aside -- always a command line or an address;
    * an embedded number -- ``slide +0x16200000``;
    * a substituted bare word -- ``kmalloc-1k cpu 0: ...``, where only the
      cache name varies but it sits right next to literal text.

    Stripping the asides first, then taking the longest run of letters and
    spaces, leaves something that could only have been typed by hand.  A
    heading with nothing left is skipped rather than guessed at.
    """
    prose_only = _PLACEHOLDER.sub(" ", _ASIDE.sub("", heading))
    candidates = [
        candidate.strip()
        for candidate in _PROSE.findall(prose_only)
    ]
    if not candidates:
        return ""
    best = max(candidates, key=len)
    return best if len(best) >= 10 else ""


def check() -> int:
    if not CAPTURE.is_file():
        print(f"no recorded run at {CAPTURE}")
        return 1
    problems: list[str] = []
    checked = 0
    skipped = 0
    known = _known_commands()
    for source, rows in sorted(_load().items()):
        path = _source_of(source)
        if path is None:
            problems.append(f"{source}: recorded, but no such file")
            continue
        text = path.read_text(encoding="utf-8")
        for row in rows:
            for heading in row["headings"]:
                stale = _bad_commands(heading, known)
                if stale:
                    problems.append(
                        f"{source}: the record lists {heading!r}, which "
                        f"invokes {', '.join(sorted(set(stale)))} -- not a "
                        "command or alias the registry publishes"
                    )
                template = _template(heading)
                if not template:
                    skipped += 1
                    continue
                checked += 1
                if template not in text:
                    problems.append(
                        f"{source}: the record lists {heading!r}, whose "
                        f"text {template!r} is not in the source any more"
                    )
    if problems:
        print("the recorded run no longer matches the examples:")
        for problem in problems:
            print(f"  {problem}")
        print(
            "\nRe-run tools/run_examples_gdb.py against a kernel to refresh "
            f"{CAPTURE.name}, or restore the section."
        )
        return 1
    note = f" ({skipped} purely-runtime heading(s) skipped)" if skipped else ""
    print(
        f"{checked} recorded heading(s) still present across "
        f"{len(_load())} example(s){note}"
    )
    return 0


def main() -> int:
    unknown = [a for a in sys.argv[1:] if a not in ("--check",)]
    if unknown:
        print(f"unknown option(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    return check()


if __name__ == "__main__":
    raise SystemExit(main())