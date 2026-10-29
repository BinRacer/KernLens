#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Render the tutorial index (``docs/<locale>/tutorial/README.md``).

The index is generated for the same reason the pages are: it states which
kernel the output came from and links every page, so it must agree with
the capture.  Keeping it hand-written meant the table of facts could go
stale while the pages stayed correct.

Usage::

    python3 tools/gen_tutorial_index.py --capture tools/tutorial_capture.json \
        --meta tools/tutorial_meta.json --out docs/en/tutorial

The per-command pages are not translated, so every language links to the
English set: ``LINK_DIR`` holds the relative path from a locale's
``tutorial/`` directory to that set.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

#: Relative source path from a locale's ``tutorial/`` directory to the
#: directory holding the generated command pages.
LINK_DIR = {"en": "", "zh-CN": "../../en/tutorial/"}

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

#: Chinese frame text.  Same shape as :data:`CATEGORY_BLURB`: the page's
#: prose is translated, the command names and summaries are not, because
#: those are the strings `kl-help` prints.
ZH_BLURB = {
    "help": "在命令集里找到方向。",
    "overview": "在陌生的会话上第一个该跑的命令。",
    "kernel base & KASLR": "内核被加载到哪里，以及 KernLens 如何应对随机化的基址。",
    "kernel metadata": (
        "配置与构建信息：命令行、版本、选项、模块、系统调用表，以及日志。"
    ),
    "CPU topology": "有多少 CPU，它们的 per-CPU 数据在哪里。",
    "addresses & page tables": (
        "从一个原始 64 位值到它指向的物理页，两个方向都有。"
    ),
    "memory & symbols": (
        "读内核自己的内存：符号、栈、SLUB、buddy 分配器、BPF 与 dma-buf。"
    ),
    "bit & integer primitives": (
        "对手上已有的值做纯算术。这是仅有的几个完全不碰内核状态的命令。"
    ),
    "output": "输出呈现控制。",
}

#: Per-locale table labels and prose.  Keeping them in one place means a
#: new sentence cannot be added to one language and forgotten in the
#: other -- the renderer reads a key, and a missing key is a KeyError.
TEXT: dict[str, dict[str, str]] = {
    "en": {
        "title": "# KernLens tutorial",
        "lede": (
            "A command-by-command walkthrough of KernLens, with output "
            "taken from a real kernel rather than invented examples."
        ),
        "shape": (
            "Every page follows the same shape: what the command answers, "
            "the exact invocation, the output it produced on the capture "
            "kernel, how to read that output, and what makes it refuse.  "
            "Pages are grouped by the categories `kl-help` prints."
        ),
        "kernel_heading": "## The capture kernel",
        "kernel_lede": (
            "All output in this tutorial was captured from one boot of the "
            "project's test VM:"
        ),
        "facts": "| Fact | Value |",
        "fact_kernel": "Kernel",
        "fact_cpus": "CPUs",
        "fact_caches": "SLUB caches",
        "fact_slide": "KASLR slide",
        "fact_text_link": "`_text` (link)",
        "fact_text_run": "`_text` (runtime)",
        "fact_page_offset": "`page_offset_base`",
        "fact_vmemmap": "`vmemmap_base`",
        "fact_free": "A free page (phys)",
        "fact_alias": "Its direct-map alias",
        "fact_struct_page": "Its `struct page`",
        "volatile": (
            "`page_offset_base` and `vmemmap_base` are kernel **variables** "
            "the boot code fills in, so they change on every boot, and the "
            "slide changes with them.  Everything else here (struct "
            "offsets, the zone list, cache names, symbol names) is stable "
            "for this build.  Anything boot-specific is re-derived by "
            "KernLens at run time rather than assumed, which is why the "
            "commands show these numbers instead of a constant."
        ),
        "reproduce": "### Reproducing the capture",
        "reproduce_note": (
            "`kl-color off` is not cosmetic: it keeps ANSI escapes out of "
            "the captured text, which is what lets these pages diff "
            "cleanly.  The capture script writes "
            "`tools/tutorial_capture.json`; `tools/gen_tutorial.py` then "
            "renders the pages from it, and `--check` fails when a page and "
            "the capture disagree."
        ),
        "reading": "## Reading the pages",
        "reading_items": [
            "- **Invocation** -- the exact command line.  The `kl-` alias "
            "is used; every one expands to the `kernlens-` name.",
            "- **Output** -- verbatim, including alignment.  Two spaces of "
            "indent under a header line is KernLens' convention for a row "
            "of one record.",
            "- **Reading it** -- what each row means and what to conclude "
            "from the values shown.",
            "- **Notes** -- where the values come from (DWARF, BTF, a "
            "registry fallback, or raw memory), and what makes the command "
            "refuse.",
        ],
        "pages": "## Pages",
        "table": ("| Command | What it answers |", "| --- | --- |"),
        "conventions": "## Conventions used in every page",
        "conventions_lede": (
            "KernLens distinguishes three states in its output, and the "
            "distinction matters when reading these pages:"
        ),
        "conventions_items": [
            "- a **value** (`Size: 0xc0`) -- read from the live kernel;",
            "- `?` -- the datum is not available in this build or this "
            "state, and the command says so rather than printing a "
            "plausible zero;",
            "- `<unreadable>` -- the memory could not be read at all (bad "
            "address, unloaded page).",
        ],
        "align": (
            "Rows are aligned with two leading spaces per nesting level, "
            "and a label is followed by `: ` (one space) so the values "
            "line up in a column."
        ),
        "footer": (
            "Generated by `tools/gen_tutorial_index.py` from the same "
            "capture as the pages.  Do not edit by hand: re-run the "
            "generator."
        ),
    },
    "zh-CN": {
        "title": "# KernLens 教程",
        "lede": (
            "逐个命令走一遍 KernLens，输出取自真实内核，而不是编造的例子。"
        ),
        "shape": (
            "每页结构一致：命令回答什么、确切的调用、它在捕获内核上产生的输出、"
            "如何读这段输出，以及它在什么情况下会拒绝。页面按 `kl-help` 打印的"
            "分类分组。"
        ),
        # The explicit id keeps the anchor the English command pages
        # link to (``README.md#the-capture-kernel``) resolving under this
        # locale too; without it the Chinese slug differs and the
        # cross-language link dangles.
        "kernel_heading": "## 捕获内核 {#the-capture-kernel}",
        "kernel_lede": "本教程的全部输出来自项目测试虚拟机的一次启动：",
        "facts": "| 事实 | 值 |",
        "fact_kernel": "内核",
        "fact_cpus": "CPU 数",
        "fact_caches": "SLUB 缓存数",
        "fact_slide": "KASLR 偏移",
        "fact_text_link": "`_text`（链接时）",
        "fact_text_run": "`_text`（运行时）",
        "fact_page_offset": "`page_offset_base`",
        "fact_vmemmap": "`vmemmap_base`",
        "fact_free": "一个空闲页（物理）",
        "fact_alias": "它的直接映射别名",
        "fact_struct_page": "它的 `struct page`",
        "volatile": (
            "`page_offset_base` 与 `vmemmap_base` 是启动代码填进去的内核"
            "**变量**，所以每次启动都会变，偏移也随之变化。这里其余的"
            "（结构体偏移、zone 列表、缓存名、符号名）对本次构建是稳定的。凡是"
            "与启动相关的，KernLens 都在运行时重新推导而不是假定，这就是命令显示"
            "这些数字而不是某个常量的原因。"
        ),
        "reproduce": "### 复现这份捕获",
        "reproduce_note": (
            "`kl-color off` 不是装饰：它让捕获文本里没有 ANSI 转义序列，"
            "这些页面才能干净地 diff。捕获脚本写出 "
            "`tools/tutorial_capture.json`；`tools/gen_tutorial.py` 再从它渲染"
            "页面，页面与捕获不一致时 `--check` 会失败。"
        ),
        "reading": "## 怎么读这些页面",
        "reading_items": [
            "- **调用** —— 确切的命令行。用的是 `kl-` 别名；每一个都展开为 "
            "`kernlens-` 名。",
            "- **输出** —— 原样，包括对齐。表头行下缩进两格是 KernLens 表示"
            "“该记录的一行”的约定。",
            "- **读法** —— 每一行是什么意思，以及从这些值能得出什么结论。",
            "- **说明** —— 这些值从哪来（DWARF、BTF、注册表兜底，还是裸内存），"
            "以及命令在什么情况下拒绝。",
        ],
        "pages": "## 页面",
        "table": ("| 命令 | 它回答什么 |", "| --- | --- |"),
        "conventions": "## 每页通用的约定",
        "conventions_lede": (
            "KernLens 的输出区分三种状态，读这些页面时这个区分很重要："
        ),
        "conventions_items": [
            "- 一个**值**（`Size: 0xc0`）—— 从活动内核读出；",
            "- `?` —— 该数据在本次构建或当前状态下不可得，命令如实说明，"
            "而不是打印一个看似合理的 0；",
            "- `<unreadable>` —— 内存完全读不出来（坏地址、页未加载）。",
        ],
        "align": (
            "每层嵌套缩进两格对齐，标签后面跟 `: `（一个空格），这样值能排成一列。"
        ),
        "footer": (
            "由 `tools/gen_tutorial_index.py` 从与页面相同的捕获生成。"
            "不要手改：重新运行生成器。"
        ),
    },
}


def _hex(value: Any) -> str:
    if isinstance(value, int):
        return f"`{value:#x}`"
    return f"`{value}`"


def render_index(
    context: dict[str, Any],
    meta: dict[str, dict[str, Any]],
    pages: list[str],
    locale: str = "en",
) -> str:
    """Render the index page for *locale*.

    The frame is translated; the command names and one-line summaries are
    not, for the same reason the command reference does not translate
    them: they are the strings the commands print.
    """
    if locale not in TEXT:
        raise SystemExit(f"no frame text for locale {locale!r}")
    t = TEXT[locale]
    blurb = ZH_BLURB if locale == "zh-CN" else CATEGORY_BLURB
    link_dir = LINK_DIR[locale]

    present = set(pages)
    lines: list[str] = []
    lines.append(t["title"] + "\n")
    lines.append(t["lede"] + "\n")
    lines.append(t["shape"] + "\n")

    lines.append(t["kernel_heading"] + "\n")
    lines.append(t["kernel_lede"] + "\n")
    lines.append(t["facts"])
    lines.append("| --- | --- |")
    lines.append(f"| {t['fact_kernel']} | `{context['kernel']}` (x86_64, DWARF "
                 "debug info) |")
    lines.append(f"| {t['fact_cpus']} | {context['nr_cpus']} |")
    lines.append(f"| {t['fact_caches']} | {context['cache_count']} |")
    lines.append(f"| {t['fact_slide']} | {_hex(context['slide'])} |")
    lines.append(f"| {t['fact_text_link']} | {_hex(context['link_text'])} |")
    lines.append(f"| {t['fact_text_run']} | {_hex(context['text'])} |")
    lines.append(
        f"| {t['fact_page_offset']} | {_hex(context['page_offset_base'])} |"
    )
    lines.append(f"| {t['fact_vmemmap']} | {_hex(context['vmemmap_base'])} |")
    lines.append(f"| {t['fact_free']} | `0x400000` |")
    lines.append(f"| {t['fact_alias']} | {_hex(context['direct'])} |")
    lines.append(f"| {t['fact_struct_page']} | {_hex(context['vmemmap_page'])} |")
    lines.append("")
    lines.append(t["volatile"] + "\n")

    lines.append(t["reproduce"] + "\n")
    lines.append("```gdb")
    lines.append("(gdb) source /path/to/KernLens/gdbinit.py")
    lines.append("(gdb) file /path/to/vmlinux")
    lines.append("(gdb) target remote :1234")
    lines.append("(gdb) kl-color off")
    lines.append(
        '(gdb) python exec(open("tools/tutorial_capture.py").read())'
    )
    lines.append("```\n")
    lines.append(t["reproduce_note"] + "\n")

    lines.append(t["reading"] + "\n")
    lines.extend(t["reading_items"])
    lines.append("")

    lines.append(t["pages"] + "\n")
    grouped: dict[str, list[tuple[str, str]]] = {}
    for name, entry in meta.items():
        stem = "kl-" + name.removeprefix("kernlens-")
        if stem not in present:
            continue
        grouped.setdefault(entry["category"], []).append(
            (stem, entry["summary"]))
    ordered = [c for c in CATEGORY_ORDER if c in grouped]
    ordered += [c for c in sorted(grouped) if c not in CATEGORY_ORDER]
    for category in ordered:
        lines.append(f"### {category.capitalize()}\n")
        group_blurb = blurb.get(category)
        if group_blurb:
            lines.append(group_blurb + "\n")
        lines.append(t["table"][0])
        lines.append(t["table"][1])
        for stem, summary in sorted(grouped[category]):
            lines.append(f"| [`{stem}`]({link_dir}{stem}.md) | {summary} |")
        lines.append("")

    lines.append(t["conventions"] + "\n")
    lines.append(t["conventions_lede"] + "\n")
    lines.extend(t["conventions_items"])
    lines.append("")
    lines.append(t["align"] + "\n")
    lines.append("---\n")
    lines.append(t["footer"] + "\n")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, type=pathlib.Path)
    parser.add_argument("--meta", required=True, type=pathlib.Path)
    parser.add_argument(
        "--out", type=pathlib.Path, default=pathlib.Path("docs/en/tutorial"),
        help="directory to write README.md into (default: docs/en/tutorial)",
    )
    parser.add_argument(
        "--pages", type=pathlib.Path,
        default=pathlib.Path("docs/en/tutorial"),
        help=(
            "directory holding the generated command pages; the index lists "
            "these regardless of language (default: docs/en/tutorial)"
        ),
    )
    parser.add_argument(
        "--locale", choices=sorted(TEXT), default="en",
        help="which language's frame to render (default: en)",
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
    pages = sorted(p.stem for p in args.pages.glob("kl-*.md"))
    if not pages:
        print(f"no kl-*.md under {args.pages}", file=sys.stderr)
        return 1
    text = render_index(capture["context"], meta, pages, args.locale)
    target = args.out / "README.md"
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
