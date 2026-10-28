"""Render ``docs/commands.md`` from the command metadata.

The README used to carry a 40-row table, and so did its Chinese
counterpart: two hand-maintained copies of the command surface, kept
honest by a frozen list in the test suite.  The metadata captured for the
tutorial already contains every name, alias, category, and summary, so
the table can be generated from it instead.  One source, one output, and
``--check`` fails when the two drift.

Usage::

    python tools/gen_commands.py
    python tools/gen_commands.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_META = ROOT / "tools" / "tutorial_meta.json"
DEFAULT_OUTPUT = ROOT / "docs" / "commands.md"

#: The order ``kl-help`` prints, so the page and the prompt agree.
CATEGORY_ORDER: tuple[str, ...] = (
    "overview",
    "kernel base & KASLR",
    "kernel metadata",
    "addresses & page tables",
    "memory & symbols",
    "CPU topology",
    "bit & integer primitives",
    "output",
    "help",
)


def _cell(text: str) -> str:
    """Make *text* safe inside a Markdown table cell."""
    return text.replace("|", "\\|").strip()


def render(meta: list[dict[str, Any]]) -> str:
    """Render the complete command reference."""
    by_category: dict[str, list[dict[str, Any]]] = {}
    for entry in meta:
        by_category.setdefault(entry["category"], []).append(entry)

    unknown = sorted(set(by_category) - set(CATEGORY_ORDER))
    if unknown:
        raise SystemExit(
            "unknown command categories: " + ", ".join(unknown)
            + "; add them to CATEGORY_ORDER"
        )

    lines = [
        "# Command reference",
        "",
        "Every command, in the order `kl-help` prints it.  The `kl-` form is",
        "what you type at the prompt; the canonical `kernlens-` form is what",
        "scripts and the generated tutorial use.  Both always work.",
        "",
        "This page is generated from `tools/tutorial_meta.json` by",
        "`tools/gen_commands.py`; edit the command's parser description, not",
        "this table.  Each command has a page in [`tutorial/`](tutorial/README.md)",
        "with captured output and a note on how to read it.",
        "",
    ]
    for category in CATEGORY_ORDER:
        entries = by_category.get(category, [])
        if not entries:
            continue
        lines.append(f"## {category} ({len(entries)})")
        lines.append("")
        lines.append("| Command | Aliases | What it does |")
        lines.append("| --- | --- | --- |")
        for entry in entries:
            aliases = ", ".join(f"`{alias}`" for alias in entry["aliases"])
            lines.append(
                f"| `{entry['name']}` | {aliases} | {_cell(entry['summary'])} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build(meta_path: Path) -> str:
    """Read *meta_path* and return the rendered page."""
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(meta, list):
        raise SystemExit(f"{meta_path} must contain a list of commands")
    return render(meta)


def main(argv: list[str] | None = None) -> int:
    """Write the page, or compare it with ``--check``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check", action="store_true",
        help="fail when the file differs instead of writing it",
    )
    args = parser.parse_args(argv)

    rendered = build(args.meta)
    if args.check:
        try:
            current = args.output.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"{args.output}: {exc}", file=sys.stderr)
            return 1
        if current != rendered:
            print(
                f"{args.output} does not match {args.meta}; "
                "run tools/gen_commands.py",
                file=sys.stderr,
            )
            return 1
        print(f"{args.output} matches the command metadata")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
