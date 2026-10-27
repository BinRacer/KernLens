#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Verify that the examples exercise the surface they claim.

The examples are the only place a reader sees the API used end to end,
and nothing checked them: no test imported them, no CI step ran them, and
no table said what they were supposed to cover.  A claim like "the
examples show the allocator API" was therefore unfalsifiable.

This tool makes it falsifiable.  It has three jobs:

``--check``
    Assert that every example listed in :mod:`tools.example_manifest`
    exists, is linked from its directory README, references every
    surface name it claims, and that the commands it claims are real
    commands.  Also enforce the ratchet
    ``REQUIRED_COMMAND_COVERAGE``.

``--report``
    Print the coverage table -- per file and per component -- so the
    numbers in ``docs/example-coverage-plan.md`` can be regenerated
    instead of trusted.

``--list-commands``
    Print the commands no example invokes yet.  This is the work list
    Phase 1 of the plan draws from.

The surface it measures against is derived, never hand-written:

* the facade bindings are the ``_BINDINGS`` literal in
  ``src/kernlens/gdb/facade.py``, read with :mod:`ast` so importing the
  module (and therefore ``gdb``) is unnecessary;
* the core class methods come from ``kernlens.core``, which imports
  without ``gdb``;
* the commands come from ``tests/contract_spec.py``.

Constants are excluded on purpose: ``KPageTable``'s 21 constant names are
already a table in the README, so an example "covering" them would be a
transcription.  :func:`is_surface_name` draws that line in one place.

Usage::

    tools/check_examples.py --report           # coverage table
    tools/check_examples.py --check            # CI guard
    tools/check_examples.py --list-commands    # commands still uninvoked
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys
from collections.abc import Iterator

_ROOT = pathlib.Path(__file__).resolve().parent.parent

if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import example_manifest as manifest  # noqa: E402
from kernlens.core import (  # noqa: E402
    BitOps,
    IntCodec,
    IntFmt,
    KAddr,
    KPageTable,
)

#: The five stateless namespaces whose public methods are part of the
#: surface a script can call.
CORE_CLASSES: dict[str, type] = {
    "BitOps": BitOps,
    "IntCodec": IntCodec,
    "IntFmt": IntFmt,
    "KAddr": KAddr,
    "KPageTable": KPageTable,
}

#: Stateful components composed into the shared ``kdbg`` facade.  A call
#: like ``kdbg.info(...)`` reaches ``logger.info``; scripts may equally
#: reach it as ``logger.info(...)``.
COMPONENTS: tuple[str, ...] = (
    "config", "logger", "styler", "reader", "symbols", "kaslr",
    "kbase", "cpu", "walker", "kernel", "slub",
)

#: ``KPageTable`` spells its geometry constants in upper case, and
#: ``BitOps`` has a few mixed-case ones.  Both are documented as tables in
#: ``README.md`` and are not something an example can meaningfully show.
_MIXED_CASE_CONSTANTS = frozenset({"BITS_PER_LEVEL", "ENTRIES_PER_LEVEL", "ENTRY_SIZE"})


def is_surface_name(name: str) -> bool:
    """Whether ``name`` is a callable surface rather than a constant.

    Dropping constants is the one judgement this tool makes about what
    counts as coverage, so it is stated once, here, and tested.
    """
    if name.startswith("_"):
        return False
    if name in _MIXED_CASE_CONSTANTS:
        return False
    return not name.isupper()


def core_methods() -> dict[str, set[str]]:
    """``{class_name: {method_name, ...}}`` for the five core classes."""
    return {
        cname: {n for n in dir(cls) if is_surface_name(n)}
        for cname, cls in CORE_CLASSES.items()
    }


def facade_bindings() -> tuple[set[str], set[str]]:
    """``(bound_names, free_names)`` read from the facade literal.

    Parsed rather than imported because ``facade`` imports ``gdb``.
    """
    path = _ROOT / "src" / "kernlens" / "gdb" / "facade.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if getattr(target, "id", "") == "_BINDINGS":
                rows = ast.literal_eval(node.value)
                bound = {row[0] for row in rows}
                free = {row[0] for row in rows if row[3]}
                return bound, free
    raise RuntimeError(f"no _BINDINGS literal found in {path}")


def canonical_commands() -> tuple[str, ...]:
    """The frozen command list from ``tests/contract_spec.py``."""
    path = _ROOT / "tests" / "contract_spec.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            name = getattr(node.target, "id", "")
            if name == "CANONICAL_COMMANDS":
                return tuple(ast.literal_eval(node.value))
    raise RuntimeError(f"no CANONICAL_COMMANDS found in {path}")


# ---------------------------------------------------------------------
# What a file references
# ---------------------------------------------------------------------

def _leading_token(node: ast.AST) -> str:
    """The literal prefix of a string or f-string expression.

    ``"kl-base"`` yields ``kl-base``; ``f"kl-{cmd} {arg}"`` yields ``kl-``.
    Used to recover the command name from an ``gdb.execute`` argument.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip().split(" ", 1)[0] if node.value.strip() else ""
    if isinstance(node, ast.JoinedStr):
        prefix = ""
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                prefix += part.value
            else:
                break
        return prefix.strip().split(" ", 1)[0] if prefix.strip() else ""
    return ""


def _executing_wrappers(tree: ast.AST) -> set[str]:
    """Local functions that forward a string argument to ``gdb.execute``.

    Examples wrap the call in a helper so each invocation can be echoed
    before it runs -- ``_run("kl-base")`` reads better than the raw call
    and, more importantly, a reader can copy the echoed line.  Without
    this, every command behind a wrapper would be invisible and the
    coverage number would be wrong in the pessimistic direction, which is
    the opposite failure from the one that inflated the original estimate.

    Only the direct, one-hop pattern is recognised: a function whose body
    contains ``gdb.execute(<name>)`` for one of its own parameter names.
    A wrapper that builds its command from other data is not guessed at.
    """
    wrappers: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = {a.arg for a in node.args.args + node.args.kwonlyargs}
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "execute"
                and sub.args
                and isinstance(sub.args[0], ast.Name)
                and sub.args[0].id in params
            ):
                wrappers.add(node.name)
    return wrappers


def executed_commands(path: pathlib.Path) -> set[str]:
    """Commands the script actually *runs*, not merely names.

    Two call shapes count: a direct ``gdb.execute("kl-x")``, and a call
    to a local wrapper that forwards its argument to ``gdb.execute``
    (the ``_run("kl-x")`` pattern the tour examples use).

    This is deliberately narrow.  An example whose banner prints "try
    ``kl-walk``" has not demonstrated ``kl-walk``, and treating the two
    the same is how the earlier "23 of 40 commands are covered" number
    was inflated.  A command assembled dynamically (``f"kl-{name}"``)
    cannot be resolved statically and is therefore not counted.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    canonical = set(canonical_commands())
    alias_to_canonical = {
        alias: name for name in canonical for alias in command_aliases(name)
    }
    wrappers = _executing_wrappers(tree)
    found: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and node.args):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "execute":
            token = _leading_token(node.args[0])
        elif isinstance(func, ast.Name) and func.id in wrappers:
            token = _leading_token(node.args[0])
        else:
            continue
        if token in alias_to_canonical:
            found.add(alias_to_canonical[token])
    return found


def mentioned_commands(path: pathlib.Path) -> set[str]:
    """Command names appearing in any string literal, docstrings included.

    Docstrings count here on purpose: this set is the superset of
    :func:`executed_commands`, so ``mentioned - executed`` is exactly the
    set of commands the file talks about without running.  That is the
    number the report shows, and it is why the earlier "23 of 40
    commands are covered" reading was wrong.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    canonical = set(canonical_commands())
    alias_to_canonical = {
        alias: name for name in canonical for alias in command_aliases(name)
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for match in _COMMAND_TOKEN.finditer(node.value):
                canonical_name = alias_to_canonical.get(match.group(1))
                if canonical_name:
                    found.add(canonical_name)
    return found


def _local_names(tree: ast.AST) -> set[str]:
    """Names bound by the script itself, rather than taken from the API.

    A bare name is only a reference to a free function if the script did
    not bind it first.  Without this the tour examples all appear to use
    ``arg`` -- the facade's ``arg()`` helper for reading a register -- when
    what they actually have is ``args = parser.parse_args(...)``, a local.
    That false positive is worth excluding carefully rather than by
    dropping the name from the surface, because ``arg()`` really is part
    of the API and an example using it should be counted.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
            for argument in (
                node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            ):
                names.add(argument.arg)
            if node.args.vararg:
                names.add(node.args.vararg.arg)
            if node.args.kwarg:
                names.add(node.args.kwarg.arg)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.Global):
            names.update(node.names)
    return names


def _references(path: pathlib.Path) -> tuple[set[str], set[str]]:
    """Return ``(qualified, bare)`` surface names referenced by a script.

    ``qualified`` holds ``Class.member`` / ``kdbg.member`` strings and
    ``bare`` holds free-function and core-method names used unqualified.

    Builtins are not filtered from ``bare``: a name only reaches the
    result if it is already a known surface name, so ``list`` and ``hex``
    are excluded by construction rather than by a builtin list.  Names the
    script binds itself are excluded too -- see :func:`_local_names`.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bound = _local_names(tree)
    qualified: set[str] = set()
    bare: set[str] = set()

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
        ):
            base = node.value.id
            if base in CORE_CLASSES or base == "kdbg" or base in COMPONENTS:
                qualified.add(f"{base}.{node.attr}")
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in bound:
                bare.add(node.id)

    return qualified, bare


#: A command name inside a string: the canonical form or the ``kl-``
#: alias.  Anchored on a word boundary so ``kernlens-slab-state`` (a
#: made-up name in prose) does not match as ``kernlens-slab``.
_COMMAND_TOKEN = re.compile(r"(?<![\w-])(kernlens-[a-z0-9-]+|kl-[a-z0-9-]+)(?![\w-])")


def referenced(path: pathlib.Path) -> set[str]:
    """The surface names one example file references."""
    qualified, bare = _references(path)
    known_qualified = _known_qualified()
    surface = {n for n in qualified if n in known_qualified}
    surface |= {n for n in bare if n in _known_bare()}
    return surface


def _known_qualified() -> set[str]:
    """Every ``Class.method`` / ``kdbg.name`` spelling on the surface.

    Only ``kdbg`` is offered as a qualifier: the facade methods are also
    reachable as ``logger.info`` or ``slub.print_slab``, but those are the
    *component* namespaces and counting them separately would inflate the
    surface without adding a way to reach anything new.  The report
    groups by owning component instead (see :func:`surface_owners`).
    """
    known: set[str] = set()
    for cname, methods in core_methods().items():
        known |= {f"{cname}.{m}" for m in methods}
    bound, _ = facade_bindings()
    known |= {f"kdbg.{n}" for n in bound}
    return known


def surface_groups() -> dict[str, dict[str, set[str]]]:
    """``{component: {canonical_name: {spellings}}}`` for reporting.

    A facade binding is attributed to the component that implements it,
    which is the grouping a reader thinks in, even though the qualifier
    used in source is ``kdbg``.  ``kdbg.walk`` and the bare ``walk`` are
    the same function reached two ways, so they collapse into one entry
    with two spellings rather than counting twice.
    """
    groups: dict[str, dict[str, set[str]]] = {}

    def add(component: str, canonical: str, spelling: str) -> None:
        groups.setdefault(component, {}).setdefault(canonical, set()).add(spelling)

    for cname, methods in core_methods().items():
        for method in methods:
            add(cname, f"{cname}.{method}", f"{cname}.{method}")
            add(cname, f"{cname}.{method}", method)

    path = _ROOT / "src" / "kernlens" / "gdb" / "facade.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and getattr(node.target, "id", "") == "_BINDINGS"
        ):
            for public, component, _member, free in ast.literal_eval(node.value):
                add(component, public, f"kdbg.{public}")
                if free:
                    add(component, public, public)
            return groups
    raise RuntimeError(f"no _BINDINGS literal found in {path}")


def _known_bare() -> set[str]:
    """Every free-function and core-method name callable unqualified."""
    _, free = facade_bindings()
    known = set(free)
    for methods in core_methods().values():
        known |= methods
    return known


def command_aliases(name: str) -> Iterator[str]:
    """The spellings a canonical command may take in source or prose."""
    yield name
    yield "kl-" + name.removeprefix("kernlens-")


# ---------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------

class Failure:
    """One problem, with enough context to fix it."""

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def check_existence() -> list[Failure]:
    """Every manifest row names a file that exists."""
    failures: list[Failure] = []
    for example in manifest.EXAMPLES:
        if not (_ROOT / example.path).is_file():
            failures.append(Failure(example.path, "listed but does not exist"))
    return failures


def check_readme_links() -> list[Failure]:
    """Every script is reachable from its directory README."""
    failures: list[Failure] = []
    for example in manifest.EXAMPLES:
        if not example.readme:
            continue
        readme = _ROOT / example.readme
        if not readme.is_file():
            failures.append(Failure(example.readme, "README is missing"))
            continue
        text = readme.read_text(encoding="utf-8")
        name = pathlib.PurePosixPath(example.path).name
        if f"({name})" not in text and f"({example.path})" not in text:
            failures.append(
                Failure(example.readme, f"does not link to {name}")
            )
    return failures


def check_claims() -> list[Failure]:
    """Every claimed surface name is actually referenced by the file."""
    failures: list[Failure] = []
    known = _known_qualified() | _known_bare()
    for example in manifest.EXAMPLES:
        if example.kind != "script":
            continue
        path = _ROOT / example.path
        if not path.is_file():
            continue  # already reported by check_existence
        surface = referenced(path)
        for claim in example.surface:
            if claim not in known:
                failures.append(
                    Failure(example.path, f"claims unknown surface name {claim!r}")
                )
            elif claim not in surface:
                failures.append(
                    Failure(example.path, f"claims {claim!r} but never references it")
                )
    return failures


def check_commands() -> list[Failure]:
    """Every claimed command is real, and is executed by the file."""
    failures: list[Failure] = []
    canonical = set(canonical_commands())
    for example in manifest.EXAMPLES:
        for claim in example.commands:
            if claim not in canonical:
                failures.append(
                    Failure(example.path, f"claims unknown command {claim!r}")
                )
                continue
            path = _ROOT / example.path
            if not path.is_file():
                continue
            if claim not in executed_commands(path):
                failures.append(
                    Failure(
                        example.path,
                        f"claims command {claim!r} but never executes it",
                    )
                )
    return failures


def check_coverage() -> list[Failure]:
    """The ratchet holds: enough distinct commands are demonstrated."""
    covered = covered_commands()
    if len(covered) < manifest.REQUIRED_COMMAND_COVERAGE:
        return [Failure(
            "tools/example_manifest.py",
            f"REQUIRED_COMMAND_COVERAGE is "
            f"{manifest.REQUIRED_COMMAND_COVERAGE} but the examples cover "
            f"{len(covered)}; add an example or lower the ratchet",
        )]
    return []


def check_all() -> list[Failure]:
    """Run every check, in the order a reader would fix them."""
    failures: list[Failure] = []
    failures += check_existence()
    failures += check_readme_links()
    failures += check_claims()
    failures += check_commands()
    failures += check_coverage()
    return failures


# ---------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------

def covered_commands() -> set[str]:
    """Commands executed by at least one example, in canonical spelling."""
    covered: set[str] = set()
    for example in manifest.EXAMPLES:
        path = _ROOT / example.path
        if example.kind != "script" or not path.is_file():
            continue
        covered |= executed_commands(path)
    return covered


def covered_surface() -> set[str]:
    """Surface names referenced by at least one example."""
    covered: set[str] = set()
    for example in manifest.EXAMPLES:
        path = _ROOT / example.path
        if example.kind != "script" or not path.is_file():
            continue
        covered |= referenced(path)
    return covered


def report() -> list[str]:
    """The coverage table, ready to print."""
    bound, free = facade_bindings()
    canonical = canonical_commands()
    covered_cmd = covered_commands()
    covered = covered_surface()
    groups = surface_groups()

    lines = [
        "examples coverage",
        "",
        f"commands            {len(covered_cmd):3d}/{len(canonical):3d}",
        f"facade bound        "
        f"{len({n for n in covered if n.startswith('kdbg.')}):3d}/{len(bound):3d}",
        f"facade free         "
        f"{len(covered & free):3d}/{len(free):3d}",
    ]

    lines += ["", "per example"]
    for example in manifest.EXAMPLES:
        path = _ROOT / example.path
        if example.kind != "script" or not path.is_file():
            lines.append(f"  {example.path:<46s} (config)")
            continue
        surface = referenced(path)
        ran = executed_commands(path)
        mentioned = mentioned_commands(path)
        lines.append(
            f"  {example.path:<46s} {len(surface):3d} name, "
            f"{len(ran):2d} run, {len(mentioned - ran):2d} prose"
        )

    lines += ["", "by owning component"]
    for component in sorted(groups):
        members = groups[component]
        used = sum(1 for spellings in members.values() if spellings & covered)
        lines.append(f"  {component:<12s}{used:3d}/{len(members):3d}")

    lines += ["", f"ratchet            {manifest.REQUIRED_COMMAND_COVERAGE}"
                  f" (covered {len(covered_cmd)})"]
    return lines


def uninvoked_commands() -> list[str]:
    """Commands no example invokes yet, in canonical spelling."""
    covered = covered_commands()
    return [name for name in canonical_commands() if name not in covered]


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that the examples exercise the surface they claim, "
            "and report the coverage they actually reach."
        ),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check", action="store_true",
        help="exit non-zero when a claim is unmet or the ratchet is missed",
    )
    mode.add_argument(
        "--report", action="store_true",
        help="print the coverage table",
    )
    mode.add_argument(
        "--list-commands", action="store_true",
        help="print the commands no example invokes",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.report:
        for line in report():
            print(line)
        return 0
    if args.list_commands:
        missing = uninvoked_commands()
        print(f"{len(missing)} command(s) with no example:")
        for name in missing:
            print(f"  {name}")
        return 0
    failures = check_all()
    if failures:
        print("examples do not match their manifest:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print(
        f"examples match their manifest "
        f"({len(manifest.EXAMPLES)} file(s), "
        f"{len(covered_surface())} surface name(s), "
        f"{len(covered_commands())}/{len(canonical_commands())} command(s))"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())