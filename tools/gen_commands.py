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
DEFAULT_OUTPUT = ROOT / "docs" / "en" / "commands.md"
LOCALE_OUTPUT = ROOT / "docs" / "zh-CN" / "commands.md"

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

#: Chinese heading and column labels for the translated page.
#:
#: Only the frame is translated.  The category names, command names,
#: aliases, and one-line descriptions all come from the command registry,
#: which is English -- they are the strings `kl-help` prints, so a
#: translated copy would be a second set of names that no command answers
#: to.  The page says so in its own note, which is more honest than a
#: table that mixes translated labels with untranslated values and
#: pretends the two are the same kind of thing.
ZH: dict[str, Any] = {
    "title": "# 命令参考",
    "intro": [
        "全部命令，顺序与 `kl-help` 打印的一致。`kl-` 形式是在提示符下敲的；"
        "规范的 `kernlens-` 形式用于脚本和生成的教程。两者始终都能用。",
        "",
        "本页由 `tools/gen_commands.py` 从 `tools/tutorial_meta.json` 生成；"
        "要改就改命令的 parser 描述，不要改这张表。每个命令在 "
        "[`tutorial/`](tutorial/README.md) 里有一页，附捕获的输出与阅读方法"
        "（页面本身保留英文）。",
        "",
        "**分类名、命令名与一句话描述保留英文。** 它们就是 `kl-help` 打印的那些"
        "字符串，命令只认这一套拼写；把它们翻译一份，只会得到一套没有任何命令"
        "响应的名字。",
        "",
    ],
    "columns": ("| 命令 | 别名 | 作用 |", "| --- | --- | --- |"),
}


def _cell(text: str) -> str:
    """Make *text* safe inside a Markdown table cell."""
    return text.replace("|", "\\|").strip()


def render(meta: list[dict[str, Any]], locale: str = "en") -> str:
    """Render the complete command reference.

    *locale* selects the frame (title, intro, column labels), not the
    rows: the rows are the command registry and are the same in every
    language, because they are the strings the commands themselves use.
    """
    by_category: dict[str, list[dict[str, Any]]] = {}
    for entry in meta:
        by_category.setdefault(entry["category"], []).append(entry)

    unknown = sorted(set(by_category) - set(CATEGORY_ORDER))
    if unknown:
        raise SystemExit(
            "unknown command categories: " + ", ".join(unknown)
            + "; add them to CATEGORY_ORDER"
        )

    if locale == "zh-CN":
        header, columns = [ZH["title"], ""] + ZH["intro"], ZH["columns"]
    else:
        header, columns = [
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
        ], ("| Command | Aliases | What it does |", "| --- | --- | --- |")

    lines = list(header)
    for category in CATEGORY_ORDER:
        entries = by_category.get(category, [])
        if not entries:
            continue
        lines.append(f"## {category} ({len(entries)})")
        lines.append("")
        lines.append(columns[0])
        lines.append(columns[1])
        for entry in entries:
            aliases = ", ".join(f"`{alias}`" for alias in entry["aliases"])
            lines.append(
                f"| `{entry['name']}` | {aliases} | {_cell(entry['summary'])} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build(meta_path: Path, locale: str = "en") -> str:
    """Read *meta_path* and return the rendered page."""
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(meta, list):
        raise SystemExit(f"{meta_path} must contain a list of commands")
    return render(meta, locale)


def main(argv: list[str] | None = None) -> int:
    """Write both pages, or compare them with ``--check``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument(
        "--check", action="store_true",
        help="fail when a file differs instead of writing it",
    )
    parser.add_argument(
        "--locale", choices=("en", "zh-CN", "all"), default="all",
        help="which page to write (default: both)",
    )
    args = parser.parse_args(argv)

    targets = {
        "en": DEFAULT_OUTPUT,
        "zh-CN": LOCALE_OUTPUT,
    }
    if args.locale != "all":
        targets = {args.locale: targets[args.locale]}

    status = 0
    for locale, output in targets.items():
        rendered = build(args.meta, locale)
        if args.check:
            try:
                current = output.read_text(encoding="utf-8")
            except OSError as exc:
                print(f"{output}: {exc}", file=sys.stderr)
                status = 1
                continue
            if current != rendered:
                print(
                    f"{output} does not match {args.meta}; "
                    "run tools/gen_commands.py",
                    file=sys.stderr,
                )
                status = 1
                continue
            print(f"{output} matches the command metadata")
            continue

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"wrote {output}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
