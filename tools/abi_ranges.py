#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Derive struct-ABI change ranges from the linux-stable git history.

The inspectors resolve struct offsets from the loaded debug info, so the
fallback table in :mod:`kernlens.gdb.layouts` only matters for a build
with none -- but when it is used it must be right, and *right for that
kernel*.  A single variant verified against one kernel is silently wrong
for another: the registry's ``struct slab.slab_cache`` was read from a
7.0 kernel and reports ``0x8`` on every release, while 5.17-6.1 really
has ``0x18``.

This tool answers "which releases need their own row?" by reading the
kernel's own history instead of guessing:

* every release tag in a local ``linux-stable`` clone is resolved, for
  one concrete ``CONFIG_*`` set, into the struct's **flat member list**
  (``#if``/``#ifdef``/``#elif``/``#else``/``#endif`` are evaluated, so
  the guards that change the layout are honoured);
* tags sharing a member list form one **range**, and each boundary
  prints the diff against the previous range, so the *reason* for the
  split is visible;
* ``--with-layouts`` additionally compares the member list the registry
  would use for that release, which turns the output into a work list
  for :mod:`tools.gen_layouts`.

A member list is an **upper bound on change**, not an equivalence: a
reorder inside a union, or a rename, changes the text without moving a
byte (``struct page`` changes its list at roughly forty boundaries while
its tracked offsets never move between v4.19 and v7.3).  The ranges
therefore say *where to probe*, never *what the value is* -- the values
still have to come from a real kernel.

Usage::

    tools/abi_ranges.py                        # slab + kmem_cache
    tools/abi_ranges.py struct zone
    tools/abi_ranges.py --config CONFIG_KASAN=y struct kmem_cache
    tools/abi_ranges.py --config-file .config --since v5.15 struct page
    tools/abi_ranges.py --with-layouts struct slab
"""

from __future__ import annotations

import argparse
import dataclasses
import difflib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from kernlens.gdb import layouts  # noqa: E402  (path set up above)

#: Default clone; override with ``--repo`` or ``$KERNLENS_LINUX_STABLE``.
DEFAULT_REPO = os.environ.get(
    "KERNLENS_LINUX_STABLE", str(Path.home() / "workSpaces" / "linux-stable"),
)

#: struct -> header files to search, in order (structs move between them).
TARGETS: dict[str, tuple[str, ...]] = {
    "struct slab": ("mm/slab.h", "include/linux/mm_types.h"),
    "struct kmem_cache": (
        "include/linux/slub_def.h", "mm/slab.h", "include/linux/slab_def.h",
    ),
    "struct zone": ("include/linux/mmzone.h",),
    "struct page": ("include/linux/mm_types.h",),
    "struct free_area": ("include/linux/mmzone.h",),
    "struct pglist_data": ("include/linux/mmzone.h",),
    "struct per_cpu_pages": ("include/linux/mmzone.h",),
    "struct kmem_cache_cpu": ("include/linux/slub_def.h",),
    "struct kmem_cache_node": ("mm/slab.h",),
}

#: An unknown symbol defaults to **off**.  Most guarded members sit behind
#: ``#ifdef CONFIG_<optional feature>``, and guessing "on" invents a member
#: that shifts everything after it; the options a normal x86_64
#: distribution kernel enables are listed instead.
DEFAULT_CONFIG: dict[str, str] = {
    "CONFIG_64BIT": "y", "CONFIG_X86_64": "y", "CONFIG_SMP": "y",
    "CONFIG_MMU": "y", "CONFIG_NUMA": "y", "CONFIG_BLOCK": "y",
    "CONFIG_PROC_FS": "y", "CONFIG_SYSFS": "y", "CONFIG_SWAP": "y",
    "CONFIG_MEMCG": "y", "CONFIG_COMPACTION": "y", "CONFIG_MIGRATION": "y",
    "CONFIG_MEMORY_ISOLATION": "y", "CONFIG_TRANSPARENT_HUGEPAGE": "y",
    "CONFIG_HUGETLBFS": "y", "CONFIG_ZONE_DEVICE": "y",
    "CONFIG_SPARSEMEM_VMEMMAP": "y",
    "CONFIG_SLUB": "y", "CONFIG_SLAB": "n", "CONFIG_SLOB": "n",
    "CONFIG_SLUB_DEBUG": "y", "CONFIG_SLUB_CPU_PARTIAL": "y",
    "CONFIG_SLAB_FREELIST_HARDENED": "y",
    "CONFIG_SLAB_FREELIST_RANDOM": "y", "CONFIG_HARDENED_USERCOPY": "y",
    "CONFIG_SLAB_MERGE_DEFAULT": "y", "CONFIG_SLUB_TINY": "n",
    "CONFIG_SECURITY": "y", "CONFIG_KASAN": "n", "CONFIG_DEBUG_VM": "n",
}

_CONDITION = re.compile(
    r"^\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b\s*(.*)$"
)
_LEAF = re.compile(r"\b([A-Za-z_]\w*)\s*(\[[^\]]*\])?\s*;")
_WORD = re.compile(r"\b([A-Za-z_]\w*)\b")
_RELEASE = re.compile(r"v\d+\.\d+")


@dataclasses.dataclass(frozen=True, slots=True)
class Span:
    """One run of consecutive releases sharing a member list."""

    first: str
    last: str
    members: tuple[str, ...]

    def label(self) -> str:
        """Return ``"v5.19 .. v6.17"`` (a single tag when it is alone)."""
        return self.first if self.first == self.last else (
            f"{self.first} .. {self.last}"
        )

    def as_range(self) -> tuple[tuple[int, ...] | None, tuple[int, ...] | None]:
        """Return the span as inclusive ``(version_min, version_max)``."""
        return version_of(self.first), version_of(self.last)


# ---------------------------------------------------------------------
# git access
# ---------------------------------------------------------------------

def show(repo: Path, tag: str, path: str) -> str:
    """Return ``tag:path`` from *repo*, or ``""`` when it does not exist."""
    result = subprocess.run(
        ["git", "--no-pager", "show", f"{tag}:{path}"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    return result.stdout if result.returncode == 0 else ""


def release_tags(repo: Path) -> list[str]:
    """Return the ``vX.Y`` tags of *repo*, ordered by version.

    Only the first release of each series is used: a stable backport that
    changed a layout would be a bug in its own right, and the ``vX.Y``
    tag is what the registry's ranges are expressed in.
    """
    result = subprocess.run(
        ["git", "tag", "-l", "v[0-9]*"], cwd=repo,
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"{repo}: not a git clone (git tag failed)")
    tags = [tag for tag in result.stdout.split() if _RELEASE.fullmatch(tag)]
    return sorted(tags, key=version_of)


def version_of(tag: str) -> tuple[int, ...]:
    """Turn ``"v6.17"`` into ``(6, 17)``."""
    return tuple(int(part) for part in tag.lstrip("v").split("."))


def default_repo(explicit: str | None) -> Path:
    """Return the linux-stable clone to read, or explain what is missing."""
    candidate = Path(explicit or DEFAULT_REPO)
    if not (candidate / ".git").exists():
        raise SystemExit(
            f"{candidate} is not a git clone; pass --repo or set "
            "KERNLENS_LINUX_STABLE to a linux-stable checkout"
        )
    if shutil.which("git") is None:
        raise SystemExit("git is not on PATH")
    return candidate


# ---------------------------------------------------------------------
# source parsing
# ---------------------------------------------------------------------

def struct_body(text: str, struct: str) -> str | None:
    """Return the ``{...}`` body of one struct, or ``None``.

    Nested braces are tracked, so a struct with a union member is read
    whole.  The *first* definition wins: a header that defines the same
    struct twice (``struct kmem_cache`` has a ``CONFIG_SLAB`` twin) puts
    the real one first, and callers pick the file so that is the SLUB
    definition they want.
    """
    name = struct.split(" ", 1)[1]
    match = re.search(rf"^struct\s+{re.escape(name)}\s*\{{", text, re.M)
    if match is None:
        return None
    depth, index = 1, match.end()
    while index < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[index], 0)
        index += 1
    return text[match.end():index - 1]


def condition_holds(expr: str, config: dict[str, str]) -> bool:
    """Evaluate a preprocessor condition against *config*.

    ``defined()``, ``&&``/``||`` and ``!`` are translated; anything left
    that is not a number or a boolean operator evaluates to false, which
    is the conservative direction (see :data:`DEFAULT_CONFIG`).
    """
    def value_of(name: str) -> str:
        return "0" if config.get(name, "n") in ("n", "") else "1"

    expr = re.sub(
        r"defined\s*\(?\s*(\w+)\s*\)?", lambda m: value_of(m.group(1)), expr,
    )
    for name in set(_WORD.findall(expr)) - {"and", "or", "not", "True", "False"}:
        if expr.strip().isdigit():
            break
        expr = re.sub(rf"\b{name}\b", value_of(name), expr)
    expr = expr.replace("&&", " and ").replace("||", " or ")
    expr = re.sub(r"!(?!=)", " not ", expr)
    try:
        return bool(eval(expr, {"__builtins__": {}}, {}))  # noqa: S307
    except (SyntaxError, NameError, TypeError, ValueError):
        return False


def members(body: str, config: dict[str, str]) -> tuple[str, ...]:
    """Return the flat member list of *body* as resolved for *config*.

    ``#if``/``#ifdef`` push a condition, ``#elif``/``#else`` take over
    when no earlier branch was taken, ``#endif`` pops; only members whose
    whole condition stack is live are kept.  Members are taken at their
    **leaf** name (the innermost ``name;``), because a union member is a
    slot -- the container declaration around it adds no offset of its
    own and would only add churn.
    """
    out: list[str] = []
    frames: list[list[bool]] = []  # [current-branch-live, any-branch-taken]
    for raw in body.splitlines():
        line = re.sub(r"/\*.*?\*/", "", raw).strip()
        if not line:
            continue
        condition = _CONDITION.match(line)
        if condition:
            keyword, expr = condition.group(1), condition.group(2).strip()
            if keyword in ("if", "ifdef", "ifndef"):
                live = condition_holds(expr, config)
                if keyword == "ifndef":
                    live = not live
                frames.append([live, live])
            elif keyword in ("elif", "else"):
                if frames:
                    taken = frames[-1][1]
                    live = False if taken else (
                        True if keyword == "else"
                        else condition_holds(expr, config)
                    )
                    frames[-1] = [live, taken or live]
            elif keyword == "endif" and frames:
                frames.pop()
            continue
        if all(frame[0] for frame in frames):
            out.extend(
                f"{leaf.group(1)}{leaf.group(2) or ''}"
                for leaf in _LEAF.finditer(line)
            )
    return tuple(out)


def body_for(
    repo: Path, tag: str, struct: str, files: tuple[str, ...],
) -> tuple[str, ...]:
    """Return the member list of *struct* at *tag* (``()`` when absent)."""
    for path in files:
        text = show(repo, tag, path)
        if not text:
            continue
        body = struct_body(text, struct)
        if body is not None:
            return members(body, DEFAULT_CONFIG)
    return ()


# ---------------------------------------------------------------------
# range derivation
# ---------------------------------------------------------------------

def derive(
    repo: Path, struct: str, tags: list[str],
    config: dict[str, str] | None = None,
) -> tuple[Span, ...]:
    """Group *tags* into :class:`Span` runs sharing a member list."""
    files = TARGETS.get(struct, ("include/linux/mm_types.h",))
    active = config or DEFAULT_CONFIG
    spans: list[Span] = []
    for tag in tags:
        found: tuple[str, ...] = ()
        for path in files:
            text = show(repo, tag, path)
            if not text:
                continue
            body = struct_body(text, struct)
            if body is not None:
                found = members(body, active)
                break
        if spans and spans[-1].members == found:
            spans[-1] = dataclasses.replace(spans[-1], last=tag)
        else:
            spans.append(Span(first=tag, last=tag, members=found))
    return tuple(spans)


def registry_notes(struct: str, span: Span, spans: tuple[Span, ...]) -> list[str]:
    """Return what the registry needs to be told about *span*.

    Two facts, deliberately not merged, because they need different
    fixes:

    * **a row is required** -- the registry has an unversioned variant
      while the struct has more than one member list, so the same numbers
      are handed out for releases that differ;
    * **impossible** -- the registry claims a field the span does not
      have, so a row for these releases would have to drop it.

    Members the registry does not track are *not* listed: most of a span's
    members are union alternatives nobody reads, and printing them would
    bury the two notes that matter.  A wrong *value* for a member that
    does exist is also undetectable here -- the member list says which
    offsets moved, never what the new one is.  That still has to come
    from a real kernel, which is why ``tools/gen_layouts.py`` exists.
    """
    entry = layouts.lookup(struct)
    if entry is None:
        return [f"no registry entry for {struct}"]
    notes: list[str] = []
    populated = [s for s in spans if s.members]
    unbounded = all(
        variant.version_min is None and variant.version_max is None
        for variant in entry.variants
    )
    if unbounded and len(populated) > 1:
        notes.append(
            f"registry has one unversioned row but there are {len(populated)} "
            "member lists; these releases need their own row"
        )
    declared = {
        path.split(".")[0].split("[")[0]
        for variant in entry.variants for path in variant.fields
    }
    for path in sorted(declared):
        if path not in span.members:
            notes.append(f"impossible: {path} is not a member of this span")
    return notes


# ---------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------

def render(
    struct: str, spans: tuple[Span, ...], *, conflicts: bool = False,
) -> str:
    """Render the spans as a report, with a diff at every boundary."""
    lines: list[str] = []
    files = TARGETS.get(struct, ("include/linux/mm_types.h",))
    lines.append("=" * 72)
    lines.append(f"{struct}   (searched: {', '.join(files)})")
    lines.append("=" * 72)
    for index, span in enumerate(spans):
        note = "ABSENT" if not span.members else f"{len(span.members)} members"
        lines.append("")
        lines.append(f"--- {span.label():<24} {note}")
        if index and spans[index - 1].members and span.members:
            diff = difflib.unified_diff(
                spans[index - 1].members, span.members, lineterm="", n=0,
            )
            lines.extend(f"      {line}" for line in list(diff)[2:])
        if conflicts and span.members:
            low, high = span.as_range()
            lines.append(
                f"      row candidate: version_min={low} "
                f"version_max={high}"
            )
            lines.extend(
                f"      -> {note}" for note in _notes(struct, span, spans)
            )
    return "\n".join(lines)


def _notes(struct: str, span: Span, spans: tuple[Span, ...]) -> list[str]:
    """Indirection so :func:`render` stays free of registry imports."""
    return registry_notes(struct, span, spans)


def _config_from_file(path: str) -> dict[str, str]:
    """Read a kernel ``.config`` into the evaluator's mapping."""
    config = dict(DEFAULT_CONFIG)
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line.startswith("# CONFIG_") and line.endswith(" is not set"):
            config[line.split()[1]] = "n"
        elif line.startswith("CONFIG_") and "=" in line:
            name, _, value = line.partition("=")
            config[name] = value.strip().strip('"')
    return config


def main(argv: list[str] | None = None) -> int:
    """Run the range derivation; return a process exit code."""
    parser = argparse.ArgumentParser(
        description=(
            "Derive struct-ABI change ranges from a linux-stable clone, so "
            "the fallback registry only grows rows where the kernel really "
            "changed."
        ),
    )
    parser.add_argument(
        "structs", nargs="*", default=["struct slab", "struct kmem_cache"],
        help="struct names to analyse (default: slab and kmem_cache)",
    )
    parser.add_argument(
        "--repo", default=None,
        help=(
            "linux-stable clone to read "
            f"(default: $KERNLENS_LINUX_STABLE or {DEFAULT_REPO})"
        ),
    )
    parser.add_argument(
        "--since", default=None, metavar="TAG",
        help="skip releases older than TAG (e.g. --since v5.15)",
    )
    parser.add_argument(
        "--until", default=None, metavar="TAG",
        help="skip releases newer than TAG",
    )
    parser.add_argument(
        "--config", action="append", default=[], metavar="SYM=VAL",
        help="override one CONFIG_ symbol (repeatable)",
    )
    parser.add_argument(
        "--config-file", default=None, metavar="PATH",
        help="read a kernel .config to seed the CONFIG_ symbols",
    )
    parser.add_argument(
        "--with-layouts", action="store_true",
        help="also report which registry row each range needs",
    )
    parser.add_argument(
        "--list-structs", action="store_true",
        help="list the structs this tool knows how to analyse and exit",
    )
    args = parser.parse_args(argv)

    if args.list_structs:
        for name in sorted(TARGETS):
            print(name)
        return 0

    config = (
        _config_from_file(args.config_file) if args.config_file
        else dict(DEFAULT_CONFIG)
    )
    for item in args.config:
        name, _, value = item.partition("=")
        config[name] = value or "y"

    repo = default_repo(args.repo)
    tags = release_tags(repo)
    if args.since:
        tags = [t for t in tags if version_of(t) >= version_of(args.since)]
    if args.until:
        tags = [t for t in tags if version_of(t) <= version_of(args.until)]
    if not tags:
        raise SystemExit("no release tags left after --since/--until")

    overrides = [
        f"{name}={'y' if value in ('y', '') else value}"
        for name, value in sorted(config.items())
        if DEFAULT_CONFIG.get(name) != value
    ]
    print(
        f"repo: {repo}\nscanned {len(tags)} release tags: "
        f"{tags[0]} .. {tags[-1]}"
    )
    print(
        "config: defaults"
        + (f" + overrides: {', '.join(overrides)}" if overrides else "")
    )
    for struct in args.structs:
        spans = derive(repo, struct, tags, config)
        print()
        print(render(struct, spans, conflicts=args.with_layouts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())