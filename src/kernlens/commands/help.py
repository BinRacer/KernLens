#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# See the LICENSE file in the top-level directory for details.
"""The ``kl-help`` overview and per-command detail rendering.

Help is derived from the command definitions (:class:`CommandDefinition`
carries the argparse parser, the category, and the aliases), so there is
no separate metadata table to keep in sync.  ``argparse`` renders the
detailed, colourised help for one command; this module only builds the
grouped overview.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable

from .. import __version__
from ..output import colors
from .formatting import style, writeln
from .framework import (
    Command,
    CommandCategory,
    CommandDefinition,
    aliases,
    registry,
)

#: The canonical namespace every command name carries.
_CANONICAL_PREFIX = "kernlens-"

#: The short alias namespace.
_ALIAS_PREFIX = "kl-"

#: Display order for the ``kl-help`` overview.
GROUP_ORDER: tuple[CommandCategory, ...] = (
    CommandCategory.OVERVIEW,
    CommandCategory.KERNEL_BASE,
    CommandCategory.KERNEL_METADATA,
    CommandCategory.PAGING,
    CommandCategory.MEMORY,
    CommandCategory.CPU,
    CommandCategory.PRIMITIVES,
    CommandCategory.OUTPUT,
    CommandCategory.HELP,
)


def render_overview(definitions: Iterable[CommandDefinition]) -> str:
    """Render the grouped ``kl-help`` command table."""
    universe = list(definitions)
    lines = [
        style("KernLens", colors.BOLD)
        + f" {__version__} — command reference",
        "  type "
        + style("kl-help kl-<command>", colors.LABEL)
        + " for usage, options, and examples",
        "",
    ]
    for group in GROUP_ORDER:
        members = [d for d in universe if d.category == group]
        if not members:
            continue
        lines.append(style(group.value, colors.LABEL))
        for definition in members:
            lines.append(
                f"  {definition.usage:<34}  {definition.summary}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def render_command_help(definition: CommandDefinition) -> str:
    """Render the detailed help for one command (argparse format + colour).

    Through the definition rather than ``parser.format_help()``: the
    epilog's section labels are painted on demand, so rendering it any
    other way reuses whatever colour state the import left behind.
    """
    return definition.format_help().rstrip()


def print_help_for(definition: CommandDefinition) -> None:
    """Print the detailed help for one command."""
    for line in render_command_help(definition).splitlines():
        writeln(line)


# =========================================================================
# The help command
# =========================================================================

_help_parser = argparse.ArgumentParser(
    description="Lists every KernLens command, or explains one in detail.",
)
_help_parser.add_argument(
    "command", nargs="?", default=None, metavar="COMMAND",
    help="kernlens-* name or kl-* alias to describe (default: list all)",
)


@Command(
    _help_parser,
    category=CommandCategory.HELP,
    aliases=["kl-help"],
    examples=(
        "kl-help\n"
        "  list every command\n"
        "kl-help kl-slab\n"
        "  explain kl-slab"
    ),
    notes=(
        "The argument must be namespaced: ``kl-help kl-slab`` or\n"
        "``kl-help kernlens-slab``.  A bare ``kl-help slab`` is rejected,\n"
        "because KernLens commands live in their own namespace and a bare\n"
        "name would read like a query about a GDB command."
    ),
)
def kernlens_help(command: str | None = None) -> None:
    """List the commands, or print the detailed help for one."""
    if not command:
        for line in render_overview(registry()).splitlines():
            writeln(line)
        return
    definition = resolve_command(command)
    if definition is None:
        print(
            style(
                f"kernlens-help: no command matches {command!r}"
                f"{_hint(command)}; run 'kl-help' for the full list",
                colors.MISSING,
            )
        )
        return
    for line in render_command_help(definition).splitlines():
        writeln(line)


def _hint(query: str) -> str:
    """Suggest the namespaced spelling for a rejected query."""
    suggestion = suggested_name(query)
    if suggestion is None:
        return ""
    return f" -- names are namespaced, so try {suggestion!r}"


def suggested_name(query: str) -> str | None:
    """The ``kl-`` spelling to try for *query*, when one exists.

    Turns "no command matches 'walk'" into a message that names the form
    that does work.
    """
    name = query.strip().lstrip("-").strip()
    if not name or name.startswith(_CANONICAL_PREFIX):
        return None
    candidate = f"{_ALIAS_PREFIX}{name}"
    return candidate if candidate in aliases() else None


def resolve_command(query: str) -> CommandDefinition | None:
    """Resolve a ``kernlens-*`` name or a ``kl-*`` alias to its definition.

    The query must be namespaced.  A bare name is rejected on purpose:
    KernLens registers ``kernlens-*`` and ``kl-*`` only, precisely so that
    its commands never collide with GDB's own, and accepting ``slab``
    here would undo that in the help text -- ``kl-help slab`` reads like a
    question about GDB, and ``kl-help print`` would have to answer "no
    command matches" while GDB's own ``help print`` works.
    """
    name = query.strip().lstrip("-").strip()
    if not name:
        return None
    lookup = aliases()
    if name in lookup:
        name = lookup[name]
    elif not name.startswith(_CANONICAL_PREFIX):
        return None
    for definition in registry():
        if definition.command_name == name:
            return definition
    return None


__all__ = [
    "GROUP_ORDER",
    "print_help_for",
    "render_command_help",
    "render_overview",
    "resolve_command",
    "suggested_name",
]