#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Render the tutorial index (``docs/tutorial/README.md``).

The index is generated for the same reason the pages are: it states which
kernel the output came from and links every page, so it must agree with
the capture.  Keeping it hand-written meant the table of facts could go
stale while the pages stayed correct.

Usage::

    python3 tools/gen_tutorial_index.py --capture tools/tutorial_capture.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

#: Category titles, in the order `kl-help` prints them.  The page groups
#: follow the same order so the two views agree.
CATEGORY_ORDER = [
    "help",
    "overview",
    "kernel base & KASLR",
    "kernel metadata",
    "CPU topology",
    "addresses & page tables",
    "memory & symbols",
    "bit & integer primitives",
    "output",
]

#: One line per category saying what the group is for.
CATEGORY_BLURB = {
    "help": "Finding your way around the command set.",
    "overview": "The one command to run first on an unfamiliar session.",
    "kernel base & KASLR": (
        "Where the kernel is loaded, and how KernLens copes with a "
        "randomised base."
    ),
    "kernel metadata": (
        "Configuration and build facts: the command line, the version, "
        "the options, the modules, the syscall table, and the log."
    ),
    "CPU topology": "How many CPUs, and where their per-CPU data lives.",
    "addresses & page tables": (
        "From a raw 64-bit value to the physical page it refers to, in "
        "either direction."
    ),
    "memory & symbols": (
        "Reading the kernel's own memory: symbols, the stack, SLUB, the "
        "buddy allocator, BPF and dma-buf."
    ),
    "bit & integer primitives": (
        "Pure arithmetic on a value you already have.  These are the only "
        "commands that touch no kernel state."
    ),
    "output": "Presentation controls.",
}


def _hex(value: Any) -> str:
    if isinstance(value, int):
        return f"`{value:#x}`"
    return f"`{value}`"


def render_index(
    context: dict[str, Any],
    meta: dict[str, dict[str, Any]],
    pages: list[str],
) -> str:
    """Render the index page."""
    present = set(pages)
    lines: list[str] = []
    lines.append("# KernLens tutorial\n")
    lines.append(
        "A command-by-command walkthrough of KernLens, with output taken "
        "from a real kernel rather than invented examples.\n"
    )
    lines.append(
        "Every page follows the same shape: what the command answers, the "
        "exact invocation, the output it produced on the capture kernel, "
        "how to read that output, and what makes it refuse.  Pages are "
        "grouped by the categories `kl-help` prints.\n"
    )

    lines.append("## The capture kernel\n")
    lines.append("All output in this tutorial was captured from one boot of "
                 "the project's test VM:\n")
    lines.append("| Fact | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Kernel | `{context['kernel']}` (x86_64, DWARF debug "
                 "info) |")
    lines.append(f"| CPUs | {context['nr_cpus']} |")
    lines.append(f"| SLUB caches | {context['cache_count']} |")
    lines.append(f"| KASLR slide | {_hex(context['slide'])} |")
    lines.append(f"| `_text` (link) | {_hex(context['link_text'])} |")
    lines.append(f"| `_text` (runtime) | {_hex(context['text'])} |")
    lines.append(f"| `page_offset_base` | {_hex(context['page_offset_base'])} |")
    lines.append(f"| `vmemmap_base` | {_hex(context['vmemmap_base'])} |")
    lines.append("| A free page (phys) | `0x400000` |")
    lines.append(f"| Its direct-map alias | {_hex(context['direct'])} |")
    lines.append(f"| Its `struct page` | {_hex(context['vmemmap_page'])} |")
    lines.append("")
    lines.append(
        "`page_offset_base` and `vmemmap_base` are kernel **variables** the "
        "boot code fills in, so they change on every boot, and the slide "
        "changes with them.  Everything else here (struct offsets, the zone "
        "list, cache names, symbol names) is stable for this build.  "
        "Anything boot-specific is re-derived by KernLens at run time "
        "rather than assumed, which is why the commands show these numbers "
        "instead of a constant.\n"
    )

    lines.append("### Reproducing the capture\n")
    lines.append("```gdb")
    lines.append("(gdb) source /path/to/KernLens/gdbinit.py")
    lines.append("(gdb) file /path/to/vmlinux")
    lines.append("(gdb) target remote :1234")
    lines.append("(gdb) kl-color off")
    lines.append(
        '(gdb) python exec(open("tools/tutorial_capture.py").read())'
    )
    lines.append("```\n")
    lines.append(
        "`kl-color off` is not cosmetic: it keeps ANSI escapes out of the "
        "captured text, which is what lets these pages diff cleanly.  The "
        "capture script writes `tools/tutorial_capture.json`; "
        "`tools/gen_tutorial.py` then renders the pages from it, and "
        "`--check` fails when a page and the capture disagree.\n"
    )

    lines.append("## Reading the pages\n")
    lines.append("- **Invocation** -- the exact command line.  The `kl-` "
                 "alias is used; every one expands to the `kernlens-` name.")
    lines.append("- **Output** -- verbatim, including alignment.  Two spaces "
                 "of indent under a header line is KernLens' convention for "
                 "a row of one record.")
    lines.append("- **Reading it** -- what each row means and what to "
                 "conclude from the values shown.")
    lines.append("- **Notes** -- where the values come from (DWARF, BTF, a "
                 "registry fallback, or raw memory), and what makes the "
                 "command refuse.\n")

    lines.append("## Pages\n")
    grouped: dict[str, list[tuple[str, str]]] = {}
    for name, entry in meta.items():
        stem = "kl-" + name.removeprefix("kernlens-")
        if stem not in present:
            continue
        grouped.setdefault(entry["category"], []).append(
            (stem, entry["summary"])
        )
    ordered = [c for c in CATEGORY_ORDER if c in grouped]
    ordered += [c for c in sorted(grouped) if c not in CATEGORY_ORDER]
    for category in ordered:
        lines.append(f"### {category.capitalize()}\n")
        blurb = CATEGORY_BLURB.get(category)
        if blurb:
            lines.append(blurb + "\n")
        lines.append("| Command | What it answers |")
        lines.append("| --- | --- |")
        for stem, summary in sorted(grouped[category]):
            lines.append(f"| [`{stem}`]({stem}.md) | {summary} |")
        lines.append("")

    lines.append("## Conventions used in every page\n")
    lines.append(
        "KernLens distinguishes three states in its output, and the "
        "distinction matters when reading these pages:\n"
    )
    lines.append("- a **value** (`Size: 0xc0`) -- read from the live kernel;")
    lines.append(
        "- `?` -- the datum is not available in this build or this state, "
        "and the command says so rather than printing a plausible zero;"
    )
    lines.append(
        "- `<unreadable>` -- the memory could not be read at all (bad "
        "address, unloaded page).\n"
    )
    lines.append(
        "Rows are aligned with two leading spaces per nesting level, and a "
        "label is followed by `: ` (one space) so the values line up in a "
        "column.\n"
    )
    lines.append("---\n")
    lines.append(
        "Generated by `tools/gen_tutorial_index.py` from the same capture "
        "as the pages.  Do not edit by hand: re-run the generator.\n"
    )
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, type=pathlib.Path)
    parser.add_argument("--meta", required=True, type=pathlib.Path)
    parser.add_argument(
        "--out", type=pathlib.Path, default=pathlib.Path("docs/tutorial"),
    )
    parser.add_argument(
        "--check", action="store_true",
        help="report drift instead of writing the file",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    capture = json.loads(args.capture.read_text(encoding="utf-8"))
    meta_entries = json.loads(args.meta.read_text(encoding="utf-8"))
    meta = {entry["name"]: entry for entry in meta_entries}
    pages = sorted(
        p.stem for p in args.out.glob("kl-*.md")
    )
    text = render_index(capture["context"], meta, pages)
    target = args.out / "README.md"
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            print(f"stale: {target}", file=sys.stderr)
            return 1
        print(f"{target} matches the capture")
        return 0
    target.write_text(text, encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())