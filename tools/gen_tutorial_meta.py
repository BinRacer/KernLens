#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Regenerate ``tools/tutorial_meta.json`` from the live command registry.

The metadata is a dump of each command's ``argparse`` parser: name,
aliases, category, summary, usage line, and options.  It used to be
refreshed by hand, which is how it came to hold six commands' worth of
text that disagreed with the modules they described -- nothing compared
the copy with the source, so the copy could not be caught drifting.

Usage::

    gdb -q -nx -batch -ex 'source gdbinit.py' \\
        -x tools/gen_tutorial_meta.py

It must run **inside GDB** because the registry is populated by importing
the command modules, and those import ``gdb``.  ``--check`` re-derives the
dump and exits non-zero when the file on disk differs, which is what CI
runs.

The ``usage`` field is the parser's own ``format_usage()``, so it carries
the spelling ``parser.prog`` holds -- the interactive ``kl-`` name since
the display preference changed.  ``name`` stays canonical because it is
the key the tutorial prose and the tutorial pages are filed under.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

#: The dump lives beside this script.
#:
#: ``__file__`` is absent when GDB loads this through
#: ``exec(open(...).read())``, which is the documented way to run it --
#: the sibling ``tutorial_capture.py`` solved the same problem the same
#: way, and this file did not, so the command in the docstring raised
#: ``NameError`` at import time.  The override lets a caller point it at
#: a checkout that is not the working directory.
_TOOLS = pathlib.Path(
    os.environ.get("KERNLENS_TOOLS")
    or (pathlib.Path(__file__).resolve().parent if "__file__" in globals()
        else "tools")
).resolve()
TARGET = _TOOLS / "tutorial_meta.json"


def _flags(action: argparse.Action) -> list[str]:
    """The option strings of *action*, or ``[]`` for a positional."""
    return list(action.option_strings)


def _default(action: argparse.Action) -> str | None:
    """Serialise *action*'s default the way the checked-in dump does.

    ``None`` stays ``None``; anything else becomes ``str()``.  The
    distinction matters because the renderer treats a ``None`` default as
    "no default" and prints nothing, while ``False`` and ``0`` are real
    values a reader may want to see.  ``argparse.SUPPRESS`` stringifies to
    ``==SUPPRESS==``, which is what the renderer filters on.
    """
    if action.default is None:
        return None
    return str(action.default)


def _choices(action: argparse.Action) -> list[str] | None:
    """``action.choices`` as a list, or ``None``."""
    if action.choices is None:
        return None
    return [str(choice) for choice in action.choices]


def _options(parser: argparse.ArgumentParser) -> list[dict]:
    """Serialize every argument the parser declares."""
    return [
        {
            "flags": _flags(action),
            "dest": action.dest,
            "help": action.help or "",
            "metavar": action.metavar,
            "nargs": str(action.nargs),
            "default": _default(action),
            "choices": _choices(action),
        }
        for action in parser._actions
    ]


def dump() -> list[dict]:
    """Dump every registered command, in registry order."""
    from kernlens.commands.framework import registry

    return [
        {
            "name": definition.command_name,
            "aliases": list(definition.aliases),
            "category": definition.category.value,
            "summary": definition.summary,
            "usage": definition.parser.format_usage().strip().removeprefix(
                "usage: "
            ),
            "options": _options(definition.parser),
        }
        for definition in registry()
    ]


def render(entries: list[dict]) -> str:
    """Render *entries* as the checked-in JSON text."""
    return json.dumps(entries, indent=1) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write the dump, or compare it with ``--check``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="fail when the file on disk differs instead of writing it",
    )
    parser.add_argument(
        "--out", type=pathlib.Path, default=TARGET,
        help="where to write the dump (default: tools/tutorial_meta.json)",
    )
    options = parser.parse_args(argv)

    text = render(dump())
    if options.check:
        current = (
            options.out.read_text(encoding="utf-8")
            if options.out.exists() else ""
        )
        if current != text:
            print(
                f"{options.out} does not match the command registry; "
                "run tools/gen_tutorial_meta.py inside GDB",
                file=sys.stderr,
            )
            return 1
        print(f"{options.out} matches the command registry")
        return 0

    options.out.write_text(text, encoding="utf-8")
    print(f"wrote {options.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())