#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""pwndbg-style command framework: argparse parsers + decorator guards.

Commands are plain functions decorated with :func:`Command`, which binds a
``argparse`` parser, a category, aliases, and shared examples/notes::

    parser = argparse.ArgumentParser(description="Displays the loaded modules.")

    @Command(parser, category=CommandCategory.KERNEL, aliases=["kl-kmod"])
    @OnlyWithKernelSymbols
    def kmod(module_name: str | None = None) -> None:
        ...

The framework reproduces pwndbg's behaviour:

* ``-h`` / ``--help`` print the parser's help (examples, notes, and the
  alias list are folded into the epilog);
* a guard that fails prints ``message.error(...)`` and returns instead of
  raising, so the command never aborts the session;
* any ``gdb.GdbError`` from the body is reported as ``message.error`` and
  swallowed, matching pwndbg's ``CommandObj.__call__``.

Registration is lazy: decoration records a :class:`CommandDefinition`;
:func:`register_all` instantiates the ``gdb.Command`` classes (and their
aliases) so sourcing ``gdbinit.py`` twice stays idempotent.
"""

from __future__ import annotations

import argparse
import functools
import shlex
from collections.abc import Callable
from enum import Enum
from typing import Any, TypeVar, cast

import gdb  # type: ignore[import-not-found]

from ..gdb.facade import kdbg
from ..output import message

P = TypeVar("P")
T = TypeVar("T")


class CommandCategory(str, Enum):
    """The grouping shown by ``kl-help``."""

    OVERVIEW = "overview"
    KERNEL_BASE = "kernel base & KASLR"
    KERNEL_METADATA = "kernel metadata"
    PAGING = "addresses & page tables"
    MEMORY = "memory & symbols"
    CPU = "CPU topology"
    PRIMITIVES = "bit & integer primitives"
    OUTPUT = "output"
    HELP = "help"


#: Canonical command *definitions*, appended in decoration order.
_COMMANDS: list["CommandDefinition"] = []

#: ``kl-`` alias name -> canonical command name.
_ALIASES: dict[str, str] = {}

#: Registered canonical command names.
command_names: set[str] = set()

#: Name -> the id of the module that registered it in this GDB session.
#:
#: GDB keeps no record of who owns a command, and re-sourcing ``gdbinit.py``
#: silently *replaces* the previous registration (last writer wins, no
#: error).  Because a reload creates a fresh instance of this module, the
#: map cannot live here -- it has to survive on the ``gdb`` module itself
#: (a singleton for the session) so a second ``register_all()`` can tell
#: "the existing ``kl-bits`` is still mine" from "something else took
#: ``kl-bits``".  Without that distinction a reload would either warn
#: spuriously about its own leftovers or, worse, stay silent when another
#: plugin really did squat the name.
_OWNERS_ATTR = "_kernlens_command_owners"


def _owners() -> dict[str, str]:
    """Return this session's command-owner map (created on first use)."""
    owners = getattr(gdb, _OWNERS_ATTR, None)
    if not isinstance(owners, dict):
        owners = {}
        setattr(gdb, _OWNERS_ATTR, owners)
    return owners


# =========================================================================
# Argument helpers
# =========================================================================

def lex_args(argument: str) -> list[str]:
    """Split a command line into argv-style tokens.

    Uses :mod:`shlex` so quoted addresses survive; falls back to a plain
    whitespace split when the line has unbalanced quotes.
    """
    try:
        return shlex.split(argument)
    except ValueError:
        return argument.split()


def parse_int_arg(arg: str) -> int:
    """Coerce a CLI token to an int via GDB, then bare hex.

    Accepts ``0x...``/decimal/octal literals, GDB expressions such as
    ``$rsp`` or ``&jiffies``, and bare hexadecimal strings (``ff``).  Used
    as the ``type=`` for ``int`` argparse arguments.
    """
    try:
        return int(gdb.parse_and_eval(arg))
    except (gdb.error, TypeError, ValueError):
        pass
    try:
        return int(arg, 0)
    except ValueError:
        pass
    try:
        return int(arg, 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{arg!r} is not an integer or a resolvable expression"
        ) from exc


def parse_int_or_str(arg: str) -> int | str:
    """Coerce to an int when possible, else keep the string (pwndbg idiom)."""
    try:
        return parse_int_arg(arg)
    except argparse.ArgumentTypeError:
        return arg


def hide(argument: argparse.Action) -> argparse.Action:
    """Hide an argument from ``--help`` while keeping it functional.

    Used for the legacy spellings kept for backward compatibility with
    earlier KernLens releases: pwndbg parity renames the option, but the
    old form must keep working, so it is registered as a suppressed
    alias rather than dropped.
    """
    argument.help = argparse.SUPPRESS
    return argument


def parse_msr_range(text: str) -> "tuple[int, int]":
    """Parse a dash-separated MSR range like pwndbg's ``--range``.

    Requires exactly ``A-B`` (inclusive, both endpoints an MSR name or a
    number) and ``A <= B``; anything else raises
    :class:`argparse.ArgumentTypeError`, matching pwndbg's "invalid
    range" behaviour.
    """
    parts = text.split("-")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(
            "range must look like 0xc0000080-0xc0000103"
        )
    start = _msr_endpoint(parts[0])
    end = _msr_endpoint(parts[1])
    if start > end:
        raise argparse.ArgumentTypeError("range start must not exceed its end")
    return start, end


def _msr_endpoint(text: str) -> int:
    """Parse one MSR range endpoint (name or number)."""
    name = text.strip()
    if not name:
        raise argparse.ArgumentTypeError("empty MSR range endpoint")
    try:
        return int(name, 0)
    except ValueError:
        pass
    try:
        return int(name, 16)
    except ValueError:
        pass
    from ..commands.misc import X86_MSRS  # local import: avoid a cycle

    if name.upper() in X86_MSRS:
        return X86_MSRS[name.upper()]
    if name in X86_MSRS:
        return X86_MSRS[name]
    raise argparse.ArgumentTypeError(f"{name!r} is not a known MSR")


def func_name(function: Callable[..., Any]) -> str:
    """Return the ``kernlens-`` command name for a command function."""
    return function.__name__.replace("_", "-")


# =========================================================================
# Guards (pwndbg's Only* decorators)
# =========================================================================

def _guard(
    predicate: Callable[[], bool], failure: Callable[[str], str],
) -> Callable[[Callable[..., T]], Callable[..., T | None]]:
    """Build a decorator that prints *failure* and returns when *predicate* fails."""

    def decorate(function: Callable[..., T]) -> Callable[..., T | None]:
        @functools.wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> T | None:
            if predicate():
                return function(*args, **kwargs)
            print(message.error(failure(func_name(function))))
            return None

        return wrapper

    return decorate


#: A matching ``vmlinux`` / kernel symbol file is loaded.
OnlyWithKernelSymbols = _guard(
    lambda: kdbg.link_text() is not None,
    lambda name: (
        f"{name}: this command needs kernel symbols; load a matching "
        "vmlinux (or use kl-kbase --rebase)."
    ),
)

#: The kernel release can be read (a minimal debug-info proxy).
OnlyWithKernelDebugInfo = _guard(
    lambda: kdbg.kconfig_get("DEBUG_INFO") is not None
    or kdbg.link_text() is not None,
    lambda name: (
        f"{name}: this command needs kernel debug info; load a matching "
        "vmlinux."
    ),
)

#: Paging is enabled (a CR3 is available).
OnlyWhenPagingEnabled = _guard(
    lambda: kdbg.link_text() is not None,
    lambda name: f"{name}: this command needs paging to be enabled.",
)


#: Struct types already reported as using fallback layouts this session.
_warned_layouts: set[str] = set()


def warn_fallback_layouts() -> None:
    """Warn once when struct layouts came from a fallback table.

    Every offset is normally resolved from the loaded ``vmlinux`` DWARF.
    A build without debug info falls back to the verified table in
    :mod:`kernlens.gdb.layouts`, but those values are only known-good for
    one kernel configuration (``CONFIG_*`` changes the layout), so the
    user is told the result may be wrong and to prefer DWARF.
    """
    kernel = getattr(kdbg, "kernel", None)
    reporter = getattr(kernel, "layout_fallbacks", None)
    if reporter is None:
        return
    try:
        types = set(reporter())
    except (gdb.error, TypeError, ValueError, AttributeError):
        return
    if not types:
        _warned_layouts.clear()
        return
    new = types - _warned_layouts
    if not new:
        return
    _warned_layouts.update(new)
    names = ", ".join(sorted(new))
    print(message.warn(
        f"{names}: no debug info; using built-in fallback layouts that "
        "may not match this kernel. Load a matching vmlinux for exact "
        "struct offsets."
    ))


# =========================================================================
# Command definition + decorator
# =========================================================================

class CommandDefinition:
    """A decorated command: body, parser, category, aliases, and metadata."""

    __slots__: tuple[str, ...] = (
        "aliases", "category", "command_name", "examples", "function",
        "notes", "parser",
    )

    def __init__(
        self,
        function: Callable[..., Any],
        parser: argparse.ArgumentParser,
        category: CommandCategory,
        aliases: list[str],
        examples: str,
        notes: str,
    ) -> None:
        self.function = function
        self.parser = parser
        self.command_name = func_name(function)
        self.category = category
        self.aliases = aliases
        self.examples = examples.strip()
        self.notes = notes.strip()
        # ``prog`` drives the usage line; use the canonical command name.
        self.parser.prog = self.command_name
        self.setup_epilog()

    @property
    def summary(self) -> str:
        """The one-line description shown in ``kl-help``."""
        return (self.parser.description or "").strip()

    @property
    def usage(self) -> str:
        """The ``usage:`` text without the ``usage: `` prefix."""
        text = self.parser.format_usage().strip()
        if text.startswith("usage:"):
            text = text[len("usage:"):].strip()
        return text

    def setup_epilog(self) -> None:
        """Fold examples, notes, and aliases into the parser epilog."""
        parts: list[str] = []
        if self.examples:
            parts.append(message.notice("Examples:") + "\n" + self.examples)
        if self.notes:
            parts.append(message.notice("Notes:") + "\n" + self.notes)
        if self.aliases:
            label = "Alias:" if len(self.aliases) == 1 else "Aliases:"
            parts.append(message.notice(label) + " " + ", ".join(self.aliases))
        if parts:
            self.parser.epilog = "\n\n".join(parts)

    def invoke(self, argument: str, from_tty: bool) -> None:
        """Run the command: parse argv, then call the body (pwndbg semantics)."""
        del from_tty
        # Keep the message/tree colours in sync with the facade so
        # ``kl-color off`` yields byte-identical plain text.
        message.set_color_enabled(kdbg.color_enabled)
        arg_list = lex_args(argument)
        if "-h" in arg_list or "--help" in arg_list:
            self.parser.print_help()
            return
        try:
            kwargs = vars(self.parser.parse_args(arg_list))
        except SystemExit:
            # argparse already printed usage / help; do not call the body.
            return
        except argparse.ArgumentError as exc:
            # A ``type=`` converter that itself raises ArgumentTypeError
            # (instead of argparse doing it) would otherwise abort the
            # whole session: GDB turns an uncaught Python exception
            # inside ``invoke`` into a fatal error that stops sourced
            # scripts.  Report it the way argparse would.
            self.parser.print_usage()
            print(
                message.error(
                    f"{self.command_name}: error: {exc.message}"
                )
            )
            return
        try:
            self.function(**kwargs)
        except gdb.GdbError as exc:
            print(message.error(f"{self.command_name}: {exc}"))
        except argparse.ArgumentTypeError as exc:
            # Same guard for converters called from the command *body*.
            self.parser.print_usage()
            print(
                message.error(
                    f"{self.command_name}: error: {exc}"
                )
            )
        else:
            warn_fallback_layouts()

    def print_help(self) -> None:
        """Print the argparse help for this command."""
        self.parser.print_help()


class Command:
    """Decorator binding a parser and metadata to a command function."""

    def __init__(
        self,
        parser: argparse.ArgumentParser,
        category: CommandCategory,
        aliases: list[str] | None = None,
        examples: str = "",
        notes: str = "",
    ) -> None:
        self.parser = parser
        self.category = category
        self.aliases = list(aliases or [])
        self.examples = examples
        self.notes = notes

    def __call__(self, function: Callable[..., Any]) -> Callable[..., Any]:
        definition = CommandDefinition(
            function,
            self.parser,
            self.category,
            self.aliases,
            self.examples,
            self.notes,
        )
        _COMMANDS.append(definition)
        for alias in self.aliases:
            _ALIASES[alias] = definition.command_name
        return function


# =========================================================================
# Registration
# =========================================================================

class KernLensBaseCommand(gdb.Command):
    """The ``gdb.Command`` wrapper that dispatches to a definition."""

    command_name: str = ""
    definition: CommandDefinition

    def __init__(self) -> None:
        super().__init__(self.command_name, gdb.COMMAND_USER)

    def invoke(self, argument: str, from_tty: bool) -> None:
        self.definition.invoke(argument, from_tty)

    def print_help(self) -> None:
        self.definition.parser.print_help()


def _slug(command_name: str) -> str:
    """Turn ``kernlens-kaslr-offset`` into ``KernlensKaslrOffset``."""
    return "".join(part.capitalize() for part in command_name.split("-"))


#: Names taken over by something that is not this module instance.
_conflicts: set[str] = set()


def conflicts() -> frozenset[str]:
    """Names that were already registered by something else.

    Populated by :func:`register_all`; a non-empty result means one of our
    commands is *shadowed* -- calling the name runs the other definition.
    """
    return frozenset(_conflicts)


def _user_commands() -> frozenset[str]:
    """The exact names GDB currently lists as user-defined commands.

    ``gdb.execute("help <name>")`` must *not* be used to test one name:
    GDB's ``help`` resolves abbreviations and prefixes (``kernlens-pt``
    also matches ``kernlens-pte``, and a bare ``pt`` matches the built-in
    ``ptype``), which would report false conflicts between our own
    commands.  ``help user-defined`` prints the exact list instead, and it
    covers every command a plugin -- or we -- registered as
    ``gdb.Command``.
    """
    try:
        text = gdb.execute("help user-defined", to_string=True)
    except Exception:  # noqa: BLE001 - no list is safer than a wrong one
        return frozenset()
    names = set()
    for line in text.splitlines():
        name, sep, _ = line.partition(" -- ")
        name = name.strip()
        if sep and name and " " not in name:
            names.add(name)
    return frozenset(names)


def _notify(text: str) -> None:
    """Emit a load-time notice, preferring ``gdb.write``.

    The bootstrap registers commands before anything can be printed
    colour-aware, and GDB halts a sourced *script* when an exception
    escapes Python.  ``gdb.write`` is always available, so a notice can
    never abort the load; ``print`` is only the fallback.
    """
    message.set_color_enabled(True)
    text = message.error(text)
    try:
        gdb.write(text + "\n")
    except (gdb.error, AttributeError, TypeError):  # pragma: no cover
        print(text)


def _instantiate(
    command_type: type[gdb.Command], name: str, kind: str,
    taken: frozenset[str],
) -> bool:
    """Register one name, reporting a shadowed registration.

    Returns ``True`` when *name* ends up bound to this module instance.
    *kind* is ``"command"`` for a canonical ``kernlens-*`` name or
    ``"alias"`` for a ``kl-*`` one, and only calibrates the wording.
    *taken* is the snapshot of pre-existing user commands from before the
    loop, so a name we just registered is never mistaken for a squatter.

    Three cases are distinguished:

    * the name was recorded as *ours* -- a reload; re-register silently;
    * the name was recorded as *someone else's* -- report and leave it;
    * nothing is recorded yet (first load into this session) -- consult
      *taken*, because a plugin that loaded *before* us left no trace in
      our map.
    """
    owner = _owners().get(name)
    if owner == __name__:
        foreign = False
    elif owner is not None:
        foreign = True
    else:
        foreign = name in taken
    if foreign:
        _conflicts.add(name)
        _notify(
            f"kernlens: {kind} {name!r} is already defined by another "
            f"plugin; the built-in definition is shadowed. Load KernLens "
            "last, or rename the conflicting definition."
        )
        return False
    try:
        command_type()
    except gdb.error as exc:
        # A GDB that refuses duplicates outright is benign; anything else
        # is a real bug and must surface.
        if "already exists" not in str(exc).lower():
            raise
    else:
        _owners()[name] = __name__
    return True


def registry() -> tuple[CommandDefinition, ...]:
    """Return the canonical command definitions in definition order."""
    return tuple(_COMMANDS)


def aliases() -> dict[str, str]:
    """Return the ``kl-`` alias -> canonical command name mapping."""
    return dict(_ALIASES)


def register_all() -> None:
    """Instantiate every command and its ``kl-`` alias.

    Idempotent: sourcing ``gdbinit.py`` twice re-owns the names instead of
    reporting them as conflicts, because GDB replaces a duplicate command
    silently rather than refusing it.  A name held by anything other than
    this module instance is left alone and reported via :func:`conflicts`.
    """
    command_names.clear()
    _conflicts.clear()
    taken = _user_commands()
    for definition in _COMMANDS:
        base = cast(
            "type[KernLensBaseCommand]",
            type(
                f"KernLens{_slug(definition.command_name)}Command",
                (KernLensBaseCommand,),
                {
                    "command_name": definition.command_name,
                    "definition": definition,
                },
            ),
        )
        if _instantiate(base, definition.command_name, "command", taken):
            command_names.add(definition.command_name)
        for alias in definition.aliases:
            _instantiate(
                type(
                    f"{base.__name__}Alias",
                    (base,),
                    {"command_name": alias},
                ),
                alias,
                "alias",
                taken,
            )


__all__ = [
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
    "func_name",
    "lex_args",
    "parse_int_arg",
    "parse_int_or_str",
    "register_all",
    "registry",
]