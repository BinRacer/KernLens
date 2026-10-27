#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Render the tutorial pages from captured command output.

The tutorial under ``docs/tutorial/`` must show what KernLens really
prints, not what it was thought to print.  Copying output by hand rots
the moment a command changes, so the pages are generated: this script
reads a JSON capture (produced by running every command against a live
kernel) plus the per-page prose, and writes one Markdown file per
command.

Usage::

    python3 tools/gen_tutorial.py --capture capture.json \
        --prose tools/tutorial_prose.py --out docs/tutorial

The prose lives in a separate module so this renderer stays a pure
formatter: it never decides what a command means, only how a page is
laid out.  ``--check`` re-renders and exits non-zero when the files on
disk differ from what the capture would produce, which is what CI runs.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any

#: Breadcrumbs and footer appended to every generated page.
FOOTER = (
    "\n---\n\n"
    "Part of the [KernLens tutorial](README.md).  "
    "Every output block on this page was captured from the kernel "
    "described in the [tutorial index](README.md#the-capture-kernel).\n"
)

#: Placeholder for an option that takes no argument.  Named rather than
#: inlined because a `\N{EM DASH}` escape is illegal inside an f-string on
#: Python 3.10, which this project still supports.
EM_DASH = "\N{EM DASH}"


def _code_block(text: str, language: str = "text") -> str:
    """Return *text* as a fenced block, crate-style."""
    body = text.rstrip("\n")
    return f"```{language}\n{body}\n```\n"


def _truncate(text: str, limit: int | None) -> tuple[str, int, int]:
    """Clip *text* to *limit* lines, reporting ``(body, shown, total)``.

    A tutorial page cannot show nine thousand configuration lines, but it
    must not silently pretend it showed them either -- the caller names
    the real total and how to see the rest.
    """
    lines = text.rstrip("\n").splitlines()
    total = len(lines)
    if limit is None or total <= limit:
        return "\n".join(lines), total, total
    shown = lines[:limit]
    shown.append(f"... ({total - limit} more line(s), {total} total)")
    return "\n".join(shown), limit, total


def render_page(
    name: str,
    meta: dict[str, Any],
    prose: dict[str, Any],
    cases: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> str:
    """Render one command page.

    *meta* is the command's own metadata (usage, aliases, options), so
    the "Synopsis" section cannot drift from the parser.  *prose* is the
    hand-written half of the page.

    *context* is the capture's environment block.  A prose invocation may
    name a boot-dependent value as ``{key}`` -- ``{direct}``,
    ``{text_addr}``, ``{slide}`` -- and it is filled from here.  Without
    this the tutorial could only be regenerated on the boot that first
    produced it: the prose is hand-written, the addresses are not
    constants, and the two used to disagree the moment the machine
    rebooted.
    """
    context = context or {}

    def boot(value: str) -> str:
        return fill_context(value, context, name)

    title = prose.get("title", meta["summary"])
    alias = ", ".join(f"`{a}`" for a in meta["aliases"]) or "(none)"
    lines: list[str] = []

    lines.append(f"# `{name}`\n")
    lines.append(f"{title}\n")
    lines.append(
        f"**Alias:** {alias}  \n"
        f"**Category:** {meta['category']}  \n"
        f"**Synopsis:** `{meta['usage']}`\n"
    )

    if prose.get("intro"):
        lines.append(prose["intro"].strip() + "\n")

    options = [
        o for o in meta["options"]
        if o["dest"] != "help" and o["help"] != "==SUPPRESS=="
    ]
    if options:
        lines.append("## Options\n")
        lines.append("| Option | Argument | Meaning |")
        lines.append("| --- | --- | --- |")
        for option in options:
            flags = ", ".join(f"`{f}`" for f in option["flags"])
            argument = option.get("metavar") or ""
            if option.get("choices"):
                argument = " \\| ".join(f"`{c}`" for c in option["choices"])
            if option["nargs"] == "?" and not argument:
                argument = "(optional)"
            meaning = option["help"].replace("|", "\\|") or "_(no help text)_"
            shown = argument or EM_DASH
            lines.append(f"| {flags} | {shown} | {meaning} |")
        lines.append("")

    for section in prose.get("sections", []):
        if section.get("invocation"):
            section = {**section, "invocation": boot(section["invocation"])}
        lines.append(f"## {section['heading']}\n")
        if section.get("text"):
            lines.append(section["text"].strip() + "\n")
        if section.get("invocation"):
            lines.append("### Invocation\n")
            lines.append(_code_block(section["invocation"], "gdb"))
        output = _find_case(cases, section.get("invocation"))
        if output is not None:
            body, shown, total = _truncate(output, section.get("output_lines"))
            lines.append("### Output\n")
            lines.append(_code_block(body))
            if shown < total:
                lines.append(
                    f"*The capture has {total} lines; the first {shown} are "
                    "shown.  Run the command to see the rest.*\n"
                )
        if section.get("reading"):
            lines.append("### Reading it\n")
            lines.append(section["reading"].strip() + "\n")

    if prose.get("notes"):
        lines.append("## Notes\n")
        lines.append(prose["notes"].strip() + "\n")

    return "\n".join(lines).rstrip("\n") + "\n" + FOOTER


def _find_case(
    cases: list[dict[str, Any]], invocation: str | None,
) -> str | None:
    """Return the captured output for *invocation*, or ``None``.

    An invocation that was never captured is a documentation bug: the
    page would claim an example it cannot show.  Returns ``None`` so the
    renderer can omit the block, and :func:`check_pages` reports it.
    """
    if not invocation:
        return None
    wanted = invocation.strip()
    for case in cases:
        if case["invocation"].strip() == wanted:
            return case["output"]
    return None


def fill_context(value: str, context: dict[str, Any], where: str = "") -> str:
    """Fill ``{name}`` placeholders from the capture's context block.

    Prose invocations name boot-dependent values symbolically --
    ``kernlens-walk {direct}`` -- because the prose is hand-written while
    the addresses change on every boot.  Without this the tutorial could
    only be regenerated on the machine that first produced it.
    """
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise SystemExit(
                f"{where or 'tutorial prose'} names unknown context key "
                f"{key!r}; add it to tools/tutorial_capture.py"
            )
        raw = context[key]
        return f"{raw:#x}" if isinstance(raw, int) else str(raw)

    return re.sub(r"\{([a-z_]+)\}", replace, value)


def missing_captures(
    prose_by_command: dict[str, dict[str, Any]],
    cases: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> list[str]:
    """List every section whose invocation has no captured output."""
    context = context or {}
    missing: list[str] = []
    for name, prose in prose_by_command.items():
        for section in prose.get("sections", []):
            invocation = section.get("invocation")
            if not invocation:
                continue
            filled = fill_context(invocation, context, name)
            if _find_case(cases, filled) is None:
                heading = section.get("heading", "?")
                missing.append(f"{name}: {heading!r} -> {filled!r}")
    return missing


def load_capture(path: pathlib.Path) -> tuple[dict[str, Any], list[dict]]:
    """Load a capture file produced by the collector."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["context"], data["cases"]


def load_metadata(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    """Load the command metadata dump, keyed by canonical name."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {entry["name"]: entry for entry in data}


def build_pages(
    meta: dict[str, dict[str, Any]],
    prose_module: Any,
    cases: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Render every page, keyed by file name."""
    pages: dict[str, str] = {}
    for name, prose in prose_module.PAGES.items():
        if name not in meta:
            raise SystemExit(
                f"tutorial prose names unknown command {name!r}"
            )
        stem = name.removeprefix("kernlens-")
        pages[f"kl-{stem}.md"] = render_page(
            name, meta[name], prose, cases, context,
        )
    return pages


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, type=pathlib.Path)
    parser.add_argument("--meta", required=True, type=pathlib.Path)
    parser.add_argument("--prose", default="tools.tutorial_prose")
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path(
        "docs/tutorial",
    ))
    parser.add_argument(
        "--check", action="store_true",
        help="report drift instead of writing files",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    prose_module = __import__(args.prose, fromlist=["PAGES"])

    _context, cases = load_capture(args.capture)
    meta = load_metadata(args.meta)
    pages = build_pages(meta, prose_module, cases, _context)

    missing = missing_captures(prose_module.PAGES, cases, _context)
    if missing:
        print("error: sections without captured output:", file=sys.stderr)
        for entry in missing:
            print(f"  {entry}", file=sys.stderr)
        return 1

    if args.check:
        drift = 0
        for filename, text in sorted(pages.items()):
            path = args.out / filename
            if not path.exists():
                print(f"missing: {path}", file=sys.stderr)
                drift += 1
            elif path.read_text(encoding="utf-8") != text:
                print(f"stale: {path}", file=sys.stderr)
                drift += 1
        if drift:
            return 1
        print(f"{len(pages)} tutorial page(s) match the capture")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    for filename, text in sorted(pages.items()):
        (args.out / filename).write_text(text, encoding="utf-8")
    print(f"wrote {len(pages)} tutorial page(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())