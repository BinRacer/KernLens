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
        + style("kl-help <command>", colors.LABEL)
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
    """Render the detailed help for one command (argparse format + colour)."""
    return definition.parser.format_help().rstrip()


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
    help="canonical or kl- alias name to describe (default: list all)",
)


@Command(
    _help_parser,
    category=CommandCategory.HELP,
    aliases=["kl-help"],
    examples="kl-help\n  list every command\nkl-help slab\n  explain kl-slab",
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
                f"kernlens-help: no command matches {command!r}; "
                "run 'kl-help' for the full list",
                colors.MISSING,
            )
        )
        return
    for line in render_command_help(definition).splitlines():
        writeln(line)


def resolve_command(query: str) -> CommandDefinition | None:
    """Resolve a canonical name or ``kl-`` alias to its definition."""
    name = query.strip().lstrip("-").strip()
    if not name:
        return None
    lookup = aliases()
    if name in lookup:
        name = lookup[name]
    elif not name.startswith("kernlens-"):
        name = f"kernlens-{name}"
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
]