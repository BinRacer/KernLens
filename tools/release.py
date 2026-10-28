#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Release-time checks and release notes, runnable without a tag.

Three files have to agree before a tag means anything: the version in
``src/kernlens/__init__.py``, the changelog section for that version, and
``CITATION.cff``.  They are written by hand at different moments, so they
drift; ``check`` is the gate that runs before publishing and fails on the
disagreement rather than on PyPI.

``notes`` renders the changelog section as the body of a GitHub Release,
so the release notes are the changelog and not a second summary that
misses an entry.

Usage::

    python tools/release.py check          # against the current version
    python tools/release.py check v0.3.0   # against a tag
    python tools/release.py notes
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
CITATION = ROOT / "CITATION.cff"

_HEADING = re.compile(
    r"^## \[(?P<version>[^\]]+)\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?\s*$"
)
_SECTION_END = re.compile(r"^## ")
_CFF_VERSION = re.compile(r"(?m)^version:\s*(\S+)\s*$")
_CFF_DATE = re.compile(r"(?m)^date-released:\s*(\S+)\s*$")


def _version() -> str:
    import kernlens

    return kernlens.__version__


def section(
    version: str, *, changelog: str | None = None,
) -> tuple[str | None, str] | None:
    """Return ``(date, body)`` for *version*, or ``None`` when absent."""
    text = CHANGELOG.read_text(encoding="utf-8") if changelog is None else changelog
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if match is None or match.group("version") != version:
            continue
        body: list[str] = []
        for following in lines[index + 1:]:
            if _SECTION_END.match(following):
                break
            body.append(following)
        return match.group("date"), "\n".join(body).strip()
    return None


def notes(version: str | None = None, *, changelog: str | None = None) -> str:
    """The changelog body for *version*, as release notes.

    The section headings are one level deeper than a standalone page, so
    ``### Added`` becomes ``## Added``: the body is used as the whole
    document, not as a part of the changelog.
    """
    target = _version() if version is None else version
    found = section(target, changelog=changelog)
    if found is None:
        raise SystemExit(f"CHANGELOG.md has no section for {target}")
    _, body = found
    if not body:
        raise SystemExit(f"the changelog section for {target} is empty")
    return re.sub(r"(?m)^### ", "## ", body) + "\n"


def check(
    tag: str | None = None,
    *,
    changelog: str | None = None,
    citation: str | None = None,
    version: str | None = None,
    today: datetime.date | None = None,
) -> list[str]:
    """Return every reason this tree cannot be released, in order."""
    problems: list[str] = []
    current = _version() if version is None else version
    if tag is not None:
        if not tag.startswith("v"):
            problems.append(f"tag {tag!r} does not start with 'v'")
        elif tag[1:] != current:
            problems.append(
                f"tag {tag} does not match __version__ {current}"
            )

    found = section(current, changelog=changelog)
    if found is None:
        problems.append(f"CHANGELOG.md has no '## [{current}]' section")
    else:
        date, body = found
        if date is None:
            problems.append(
                f"the changelog section for {current} has no release date"
            )
        elif (today or datetime.date.today()) < datetime.date.fromisoformat(
            date,
        ):
            problems.append(f"the changelog date {date} is in the future")
        if "- " not in body:
            problems.append(
                f"the changelog section for {current} has no entries"
            )

    text = CITATION.read_text(encoding="utf-8") if citation is None else citation
    cited = _CFF_VERSION.search(text)
    if cited is None:
        problems.append("CITATION.cff has no version")
    elif cited.group(1) != current:
        problems.append(
            f"CITATION.cff says {cited.group(1)}, the package says {current}"
        )
    released = _CFF_DATE.search(text)
    if released is None:
        problems.append("CITATION.cff has no date-released")
    elif found is not None and found[0] is not None and (
        released.group(1) != found[0]
    ):
        problems.append(
            f"CITATION.cff says {released.group(1)}, the changelog says "
            f"{found[0]}"
        )
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``check`` or print ``notes``."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check_parser = sub.add_parser("check", help="verify the release files")
    check_parser.add_argument("tag", nargs="?", default=None)
    notes_parser = sub.add_parser("notes", help="print the release notes")
    notes_parser.add_argument("version", nargs="?", default=None)
    args = parser.parse_args(argv)

    if args.command == "notes":
        print(notes(args.version), end="")
        return 0

    problems = check(args.tag)
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
