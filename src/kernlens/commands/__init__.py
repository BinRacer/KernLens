#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# See the LICENSE file in the top-level directory for details.
"""The ``kernlens-*`` GDB commands, in the pwndbg command style.

Commands are plain functions decorated with
:class:`~kernlens.commands.framework.Command`, which binds an ``argparse``
parser, a category, and aliases.  Importing this package pulls in every
domain module, populating the registry; the bootstrap in ``gdbinit.py``
then calls :func:`register_all` to instantiate the ``gdb.Command`` classes
and their ``kl-`` aliases.
"""

from __future__ import annotations

from .framework import (
    Command,
    CommandCategory,
    CommandDefinition,
    KernLensBaseCommand,
    OnlyWhenPagingEnabled,
    OnlyWithKernelDebugInfo,
    OnlyWithKernelSymbols,
    aliases,
    command_names,
    conflicts,
    lex_args,
    parse_int_arg,
    parse_int_or_str,
    register_all,
    registry,
)
from .help import GROUP_ORDER

# Importing the domain modules runs the ``@Command`` decorators, which
# populate ``registry()`` / ``aliases()``.
from . import (  # noqa: E402,F401  isort:skip
    buddy,
    kernel_base,
    memory,
    metadata,
    misc,
    overview,
    paging,
    primitives,
)

__all__ = [
    "GROUP_ORDER",
    "Command",
    "CommandCategory",
    "CommandDefinition",
    "KernLensBaseCommand",
    "OnlyWhenPagingEnabled",
    "OnlyWithKernelDebugInfo",
    "OnlyWithKernelSymbols",
    "aliases",
    "command_names",
    "conflicts",
    "lex_args",
    "parse_int_arg",
    "parse_int_or_str",
    "register_all",
    "registry",
]