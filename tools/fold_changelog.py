"""Fold the changelog's three undeclared releases into one real one.

The file described three releases: ``Unreleased`` (952 lines), ``0.2.0``
and ``0.1.0``.  Only the first was true.  ``pyproject.toml`` has read
``0.2.0`` since the day it was created and was never ``0.1.0``; the
``0.1.0`` heading carries the date 2026-10-25, a day whose only commit
was the licence bootstrap, while the section claims a test suite, CI
configuration and nine modules.  Neither version was ever tagged or
published.

So this script does not invent boundaries.  It merges the three sections
into the single release that actually exists -- everything up to HEAD --
and says in the file that the two older headings were development
milestones rather than releases.  No entry is dropped: every bullet is
moved with its wrapping intact and consolidated by category, which is
what "one release" means when the work happened in three days.

Usage::

    python tools/fold_changelog.py [--check]

``--check`` reports what it would change and exits non-zero when the file
is not yet folded, so the result can be verified the same way the other
generators are.
"""

from __future__ import annotations

import pathlib
import re
import sys

CHANGELOG = pathlib.Path(__file__).resolve().parent.parent / "CHANGELOG.md"

RELEASE = "## [0.3.0] - 2026-10-28"

#: The order the categories appear in.  A category not listed here is kept
#: and appended in the order it was first seen, so an unfamiliar heading is
#: preserved rather than silently dropped.
CATEGORY_ORDER = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")

#: Marks a file that has already been folded, so a second run is a no-op.
NOTE_HEADING = "## Version history note"

NOTE = """\
## Version history note

Earlier revisions of this file carried `0.1.0` and `0.2.0` headings.
Neither was ever tagged or published, and neither was ever the version in
`pyproject.toml`, which has read `0.2.0` since the file was created.  The
`0.1.0` heading was dated 2026-10-25 -- a day whose only commit was the
licence bootstrap -- while listing modules that first appeared on the
26th.  They were development milestones written after the fact, not
release records.

Their entries are folded into the release above, in their original
wording.  `0.3.0` is the first tagged release, and every entry in it
describes code that exists at the tag.
"""


def _is_item_start(line: str) -> bool:
    return line.startswith("- ") or line.startswith("* ")


def parse(text: str) -> tuple[list[str], list[tuple[str, list[list[str]]]]]:
    """Split the file into (preamble, [(category, [item, ...])]).

    An item is a ``- `` line plus every following continuation line, so a
    wrapped bullet stays one item.  Release headings and their surrounding
    prose are discarded once collected: merging them is the whole point.
    """
    preamble: list[str] = []
    sections: list[tuple[str, list[list[str]]]] = []

    items: list[list[str]] | None = None
    category: str | None = None
    seen_release = False

    def flush() -> None:
        nonlocal items, category
        if items is not None and category is not None:
            sections.append((category, items))
        items, category = None, None

    for raw in text.splitlines():
        line = raw.rstrip()

        if line.startswith("## ") and NOTE_HEADING in line:
            # The note is the folded marker.  Stop here so a second run
            # treats its prose as a note rather than as bullet text.
            break
        if line.startswith("## "):
            flush()
            seen_release = True
            continue
        if line.startswith("### "):
            flush()
            category = line[4:].strip()
            items = []
            continue
        if not seen_release:
            preamble.append(line)
            continue
        if items is None:
            continue
        if _is_item_start(line):
            items.append([line])
        elif line and items:
            items[-1].append(line)
    flush()
    return preamble, sections


def fold(sections: list[tuple[str, list[list[str]]]]) -> dict[str, list[list[str]]]:
    """Merge every section by category, preserving item order and text."""
    merged: dict[str, list[list[str]]] = {}
    for category, items in sections:
        merged.setdefault(category, []).extend(items)
    return merged


def render(preamble: list[str], merged: dict[str, list[list[str]]]) -> str:
    order = [c for c in CATEGORY_ORDER if c in merged]
    order += [c for c in merged if c not in CATEGORY_ORDER]

    out = list(preamble)
    while out and not out[-1].strip():
        out.pop()
    out += ["", RELEASE, ""]
    for category in order:
        out.append(f"### {category}")
        out.append("")
        for item in merged[category]:
            out.extend(item)
        out.append("")
    while out and not out[-1].strip():
        out.pop()
    out += ["", NOTE]
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    original = CHANGELOG.read_text(encoding="utf-8")
    preamble, sections = parse(original)
    merged = fold(sections)
    rendered = render(preamble, merged)

    releases = re.findall(r"^## \[(.+?)\]", rendered, re.M)
    total = sum(len(v) for v in merged.values())
    print(f"sections folded : {len(sections)}")
    print(f"categories      : {', '.join(merged)}")
    print(f"items           : {total}")
    print(f"release heading : {', '.join(releases) or '(none)'}")

    if rendered == original:
        print("changelog is already folded")
        return 0
    if check:
        print("changelog still describes more than one release; run without --check")
        return 1
    CHANGELOG.write_text(rendered, encoding="utf-8")
    print(f"wrote {CHANGELOG.name}: {len(rendered.splitlines())} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))