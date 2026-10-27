#!/usr/bin/env python3
#
# ruff: noqa: F821
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Establish what the target is, before trusting any address.

Every other example in this tree starts from an address or a symbol and
asks what it means.  This one starts from nothing and asks *what am I
looking at* -- because the answer changes what all the other answers
mean.  A config flag decides whether a freed object's first word is a
pointer or an encoded blob; a boot parameter decides whether a 5-level
translation is worth attempting; a module list decides whether
`is_module` can ever be true.

Source it after `gdbinit.py` and run `kfacts`::

    (gdb) source /path/to/KernLens/gdbinit.py
    (gdb) source /path/to/KernLens/examples/api/kernel_facts.py
    (gdb) kfacts                # resolves init_task by default
    (gdb) kfacts kmalloc_caches

The command is named `kfacts`, not `kernlens-facts`, because KernLens
owns the `kernlens-` / `kl-` namespaces: an example that claimed one
would collide the moment a real command of that name shipped.
"""

from __future__ import annotations

try:
    import gdb
except ImportError as exc:  # pragma: no cover - GDB only
    raise SystemExit("kernel_facts.py must be sourced by GDB") from exc


def _bootstrap_if_needed() -> None:
    """Load the public API if this file was not sourced after gdbinit."""
    try:
        kdbg  # type: ignore[used-before-def]  # noqa: B018
    except NameError:
        import sys
        from pathlib import Path

        src = Path(__file__).resolve().parents[2] / "src"
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from kernlens.gdb.api import install_public_api

        install_public_api(globals())


_bootstrap_if_needed()


def _section(title: str) -> None:
    """Print a section header so the output stays navigable.

    These commands each print a lot; a reader scanning a terminal needs
    to know which block they are in.
    """
    gdb.write(f"\n=== {title} " + "=" * max(0, 58 - len(title)) + "\n")


#: The config flags that change how *data* is interpreted, as opposed to
#: where it lives.  This is the subset worth one line each; the full
#: `kl-kchecksec` checklist appears at the end for completeness.
DATA_CONFIGS: tuple[str, ...] = (
    "SLAB_FREELIST_HARDENED",
    "SLAB_FREELIST_RANDOM",
    "INIT_ON_ALLOC_DEFAULT_ON",
    "INIT_ON_FREE_DEFAULT_ON",
    "RANDOMIZE_BASE",
    "HARDENED_USERCOPY",
    "KALLSYMS",
)


def kernel_identity() -> None:
    """What released this kernel, and what was it told at boot.

    The command line is the cheapest thing that can invalidate every
    later assumption: `kaslr` on a kernel whose slide is unresolved makes
    `kdbg.sym()` disagree with the ELF, and `no5lvl` decides whether a
    5-level walk is worth attempting.
    """
    _section("identity")
    gdb.execute("kl-kversion")
    gdb.execute("kl-kcmdline")


def data_semantics() -> None:
    """The flags that make a reader's intuition wrong.

    `SLAB_FREELIST_HARDENED=y` means a freed object's first word is an
    encoded pointer, not the next free object's address -- so a tracer
    that follows it naively walks into garbage.  `INIT_ON_ALLOC_DEFAULT_ON=y`
    means a fresh object is zeroed, so zeros in a slot are expected rather
    than suspicious.  Both change the meaning of a value the later
    examples read.
    """
    _section("config flags that change what a value means")
    for config in DATA_CONFIGS:
        gdb.execute(f"kl-kconfig {config}")


def hardening_checklist() -> None:
    """The same facts in exploitation vocabulary, as one long checklist."""
    _section("hardening checklist")
    gdb.execute("kl-kchecksec")


def runtime_objects() -> None:
    """Whether `is_module` can ever be true on this target."""
    _section("loaded modules")
    gdb.execute("kl-kmod")


def symbol_views(symbol: str) -> None:
    """Three independent views of the text region.

    `kl-ksyscalls <name>` filters rather than printing 451 rows, and
    `kl-klookup` resolves the requested symbol, so the output stays
    readable.  A disagreement between the syscall table, the symbol
    lookup and the boot log is the signature of a wrong KASLR slide.
    """
    _section("syscalls matching 'read'")
    gdb.execute("kl-ksyscalls read")

    _section(f"symbol lookup: {symbol}")
    gdb.execute(f"kl-klookup {symbol}")

    # The boot log is long by nature; `-T` at least renders the
    # timestamps as wall-clock so the lines can be read as a sequence.
    _section("boot log")
    gdb.execute("kl-kdmesg -T")


class KernelFactsCommand(gdb.Command):
    """kfacts [symbol] -- establish what the target kernel is.

    With no argument it resolves `init_task`, which every kernel has and
    which therefore makes the last step work on any target.
    """

    def __init__(self) -> None:
        super().__init__("kfacts", gdb.COMMAND_USER)

    def invoke(self, arg: str, from_tty: bool) -> None:
        symbol = arg.strip() or "init_task"
        # `kaslr_slide()` is a method -- it derives the slide from the
        # current KASLR configuration -- while `kaslr_offset` is a plain
        # attribute that stays 0 until something sets it.  Printing the
        # slide up front is what makes a later disagreement visible.
        gdb.write(f"--- kernel identity (slide {kdbg.kaslr_slide():+#x}) ---\n")
        kernel_identity()
        data_semantics()
        hardening_checklist()
        runtime_objects()
        symbol_views(symbol)


# Instantiating the class is what registers the command: defining a
# `gdb.Command` subclass alone does nothing, which is the most common
# reason a newly written example command is "not found".
_KFACTS = KernelFactsCommand()

gdb.write(
    "kernel_facts: run 'kfacts' to identify the target, "
    "'kfacts <symbol>' to resolve a symbol\n"
)