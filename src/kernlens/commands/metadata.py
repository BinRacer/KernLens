#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""Kernel metadata commands, styled after pwndbg's ``k``-family.

``kernlens-kcmdline`` / ``kversion`` / ``kconfig`` / ``kchecksec`` /
``kmod`` / ``ksyscalls`` / ``kdmesg`` / ``klookup``.  Soft failures print
``message.warn`` / ``message.error`` and return, exactly as pwndbg does.
"""

from __future__ import annotations

import argparse
import time
from typing import NamedTuple

import gdb  # type: ignore[import-not-found]

from ..gdb.facade import kdbg
from ..output import message
from .framework import (
    Command,
    CommandCategory,
    OnlyWithKernelDebugInfo,
    OnlyWithKernelSymbols,
)


# =========================================================================
# kcmdline / kversion
# =========================================================================

_kcmdline_parser = argparse.ArgumentParser(
    description="Return the kernel command line (/proc/cmdline)."
)


@Command(
    _kcmdline_parser,
    category=CommandCategory.KERNEL_METADATA,
    aliases=["kl-kcmdline"],
    examples="kl-kcmdline\n  print the boot command line",
)
@OnlyWithKernelSymbols
def kernlens_kcmdline() -> None:
    cmdline = kdbg.kcmdline()
    if not cmdline:
        print(
            message.error(
                "cannot read saved_command_line; load a matching vmlinux / "
                "set the KASLR slide"
            )
        )
        return
    print(cmdline)


_kversion_parser = argparse.ArgumentParser(
    description="Outputs the kernel version (/proc/version)."
)


@Command(
    _kversion_parser,
    category=CommandCategory.KERNEL_METADATA,
    aliases=["kl-kversion"],
    examples="kl-kversion\n  print the banner and the parsed release",
)
@OnlyWithKernelSymbols
def kernlens_kversion() -> None:
    version = kdbg.kversion()
    if not version:
        print(
            message.error(
                "cannot read linux_banner; load a matching vmlinux / "
                "set the KASLR slide"
            )
        )
        return
    print(version)
    release = kdbg.krelease()
    if release is not None:
        print(
            message.notice("release:")
            + " "
            + ".".join(str(part) for part in release)
        )


# =========================================================================
# kconfig
# =========================================================================

_kconfig_parser = argparse.ArgumentParser(
    description="Outputs the kernel config (/proc/config.gz)."
)
_kconfig_parser.add_argument(
    "config_name", nargs="?", type=str, default=None,
    help="a config name to search for (e.g. RANDOMIZE_BASE)",
)
_kconfig_parser.add_argument(
    "-l", "--load", type=str, dest="file_path", default=None,
    help="merge CONFIG_* lines from a kernel config file",
)


@Command(
    _kconfig_parser,
    category=CommandCategory.KERNEL_METADATA,
    aliases=["kl-kconfig"],
    examples=(
        "kl-kconfig\n"
        "  dump every CONFIG_* option\n"
        "kl-kconfig RANDOMIZE_BASE\n"
        "  look up one option\n"
        "kl-kconfig --load /boot/config-$(uname -r)\n"
        "  merge a config file"
    ),
)
@OnlyWithKernelSymbols
def kernlens_kconfig(config_name: str | None, file_path: str | None) -> None:
    if file_path is not None:
        try:
            merged = kdbg.kconfig_update(file_path)
        except OSError as exc:
            print(message.error(f"cannot read {file_path!r}: {exc}"))
            return
        print(
            message.success(f"loaded {merged} config line(s)")
            + f" from {file_path}"
        )
        return
    config = kdbg.kconfig()
    if not config:
        print(
            message.error(
                "cannot read kernel_config_data; load a matching vmlinux / "
                "set the KASLR slide"
            )
        )
        return
    if config_name:
        value = kdbg.kconfig_get(config_name)
        key = kdbg.config_key(config_name)
        if value is None:
            print(f"Config {key} not set")
        else:
            print(f"{key} = {value}")
        return
    for name in sorted(config):
        print(f"{name} = {config[name]}")


# =========================================================================
# kchecksec
# =========================================================================

class Option(NamedTuple):
    """One hardening option and the state that counts as hardened."""

    name: str
    desired: bool = True


#: Hardening options pwndbg tracks (behaviour adapted from pwndbg, MIT).
_HARDENING_OPTIONS: tuple[Option, ...] = (
    Option("STACKPROTECTOR"),
    Option("STACKPROTECTOR_STRONG"),
    Option("SHADOW_CALL_STACK"),
    Option("STRICT_KERNEL_RWX"),
    Option("STRICT_MODULE_RWX"),
    Option("DEBUG_WX"),
    Option("RANDOMIZE_BASE"),
    Option("RANDOMIZE_KSTACK_OFFSET_DEFAULT"),
    Option("RANDOMIZE_MODULE_REGION_FULL"),
    Option("KALLSYMS", False),
    Option("SLAB_FREELIST_HARDENED"),
    Option("SLAB_FREELIST_RANDOM"),
    Option("KFENCE"),
    Option("INIT_ON_ALLOC_DEFAULT_ON"),
    Option("INIT_STACK_ALL_ZERO"),
    Option("INIT_ON_FREE_DEFAULT_ON"),
    Option("CFI_CLANG"),
    Option("CFI_PERMISSIVE", False),
    Option("SECURITY"),
    Option("SECURITY_YAMA"),
    Option("SECURITY_SELINUX_DISABLE", False),
    Option("SECURITY_SELINUX_BOOTPARAM", False),
    Option("SECURITY_SELINUX_DEVELOP", False),
    Option("KPROBES", False),
    Option("FTRACE", False),
    Option("KPROBE_EVENTS", False),
    Option("UPROBE_EVENTS", False),
    Option("GENERIC_TRACER", False),
    Option("FUNCTION_TRACER", False),
    Option("STACK_TRACER", False),
    Option("STRICT_DEVMEM"),
    Option("DEVMEM", False),
    Option("DEVKMEM", False),
    Option("DEBUG_FS", False),
    Option("PTDUMP_DEBUGFS", False),
    Option("BUG"),
    Option("MODULES", False),
    Option("USERFAULTFD", False),
    Option("FORTIFY_SOURCE"),
    Option("STATIC_USERMODEHELPER"),
    Option("HARDENED_USERCOPY"),
    Option("RODATA_FULL_DEFAULT_ENABLED"),
    Option("RANDSTRUCT_FULL"),
    Option("TRIM_UNUSED_KSYMS"),
    Option("SECURITY_DMESG_RESTRICT"),
    Option("PROC_KCORE", False),
    Option("PROC_VMCORE", False),
    Option("COMPAT_VDSO", False),
    Option("BINFMT_MISC", False),
)

#: x86_64-specific hardening options (this port is x86_64 only).
_X86_HARDENING_OPTIONS: tuple[Option, ...] = (
    Option("X86_SMAP"),
    Option("IA32_EMULATION", False),
    Option("X86_X32", False),
)

_kchecksec_parser = argparse.ArgumentParser(
    description="Checks for kernel hardening configuration options."
)


@Command(
    _kchecksec_parser,
    category=CommandCategory.KERNEL_METADATA,
    aliases=["kl-kchecksec"],
    examples="kl-kchecksec\n  audit the hardening CONFIG_* options",
)
@OnlyWithKernelSymbols
def kernlens_kchecksec() -> None:
    if not kdbg.kconfig():
        print(
            message.error(
                "cannot read kernel_config_data; load a matching vmlinux / "
                "set the KASLR slide"
            )
        )
        return
    for option in _HARDENING_OPTIONS + _X86_HARDENING_OPTIONS:
        value = kdbg.kconfig_get(option.name)
        enabled = value is not None
        good = enabled == option.desired
        color = message.success if good else message.error
        if enabled:
            text = f"CONFIG_{option.name} = {value}"
        else:
            text = f"CONFIG_{option.name} not set"
        print(color(text))


# =========================================================================
# kmod
# =========================================================================

_kmod_parser = argparse.ArgumentParser(
    description="Displays the loaded Linux kernel modules."
)
_kmod_parser.add_argument(
    "module_name", nargs="?", type=str, default=None,
    help="A module name to search for",
)
_kmod_parser.add_argument(
    "-l", "--load", dest="path", type=str, default=None,
    help="the path of the module to load",
)


@Command(
    _kmod_parser,
    category=CommandCategory.KERNEL_METADATA,
    aliases=["kl-kmod"],
    examples="kl-kmod\n  list every module\nkl-kmod nf_tables\n  filter by name",
)
@OnlyWithKernelSymbols
def kernlens_kmod(module_name: str | None = None, path: str | None = None) -> None:
    head = kdbg.kvar_addr("modules")
    if head is None:
        print(
            message.error(
                "cannot read the modules list; load a matching vmlinux / "
                "set the KASLR slide"
            )
        )
        return
    modules = kdbg.modules()
    if not modules:
        print(message.warn("no kernel modules are loaded"))
        return
    if head is not None:
        print(f"Kernel modules address found at {head:#x}.\n")
    shown = [m for m in modules if not module_name or module_name in m.name]
    rows = [
        [
            f"{module.address:#x}",
            module.name,
            module.size,
            "?" if module.used_by is None else str(module.used_by),
        ]
        for module in shown
    ]
    print(kdbg.table(("Address", "Name", "Size", "Used by"), rows))
    print()
    print(f"{len(shown)} of {len(modules)} module(s) shown")
    if path is not None:
        _kmod_load(path, shown)


def _kmod_load(path: str, shown: list) -> None:
    """Load a module's symbols at its runtime base (pwndbg ``kmod -l``)."""
    if not shown:
        print(message.warn("No modules detected with the given filter."))
        return
    if len(shown) > 1:
        print(message.warn("Multiple modules detected with the given filter"))
        return
    module = shown[0]
    try:
        gdb.execute(f"add-symbol-file {path} {module.address:#x}")
    except (gdb.error, gdb.MemoryError) as exc:
        print(message.error(f"cannot load {path!r}: {exc}"))
        return
    print(
        message.success(
            f"loaded {path} at {module.address:#x} ({module.name})"
        )
    )


# =========================================================================
# ksyscalls
# =========================================================================

_ksyscalls_parser = argparse.ArgumentParser(
    description=(
        "Displays the Linux syscall table, including names and addresses "
        "of syscalls."
    )
)
_ksyscalls_parser.add_argument(
    "syscall_name", nargs="?", type=str, default=None,
    help="a syscall name to search for",
)


@Command(
    _ksyscalls_parser,
    category=CommandCategory.KERNEL_METADATA,
    aliases=["kl-ksyscalls"],
    examples="kl-ksyscalls\n  list the whole table\nkl-ksyscalls open",
)
@OnlyWithKernelSymbols
def kernlens_ksyscalls(syscall_name: str | None = None) -> None:
    entries = kdbg.syscalls(syscall_name)
    if not entries:
        print(
            message.error(
                "cannot read sys_call_table; load a matching vmlinux "
                "(with debug info) first"
            )
        )
        return
    table = kdbg.kvar_addr("sys_call_table")
    count = kdbg.syscall_count()
    if table is not None:
        print(f"Syscall table address with {count} entries found at {table:#x}.\n")
    print(f"{'':>4} {'Address':>18} {'Symbol'}")
    for entry in entries:
        print(
            f"{entry.index:>4} {entry.address:#018x} "
            f"{entry.symbol or '<unknown>'}"
        )


# =========================================================================
# kdmesg
# =========================================================================

_kdmesg_parser = argparse.ArgumentParser(
    description="Displays the kernel ring buffer (dmesg) contents."
)
_kdmesg_parser.add_argument(
    "-T", "--ctime", action="store_true",
    help="print human-readable (wall-clock) timestamps",
)


@Command(
    _kdmesg_parser,
    category=CommandCategory.KERNEL_METADATA,
    aliases=["kl-kdmesg"],
    examples="kl-kdmesg\n  print the ring buffer\nkl-kdmesg --ctime",
)
@OnlyWithKernelDebugInfo
def kernlens_kdmesg(ctime: bool = False) -> None:
    records = kdbg.dmesg()
    if not records:
        print(
            message.warn(
                "no printk records found (needs a >= 5.10 kernel that "
                "exposes printk_rb_static)"
            )
        )
        return
    epoch = None
    if ctime:
        epoch = kdbg.tk_epoch()
        if epoch is None:
            print(
                message.warn(
                    "--ctime needs tk_core (the timekeeper) to be readable"
                )
            )
            return
    for record in records:
        label = (
            time.ctime(epoch + record.timestamp)
            if epoch is not None
            else f"{record.timestamp:12.6f}"
        )
        for line in (record.text or "").splitlines() or [""]:
            print(f"[{label}] {line}")


# =========================================================================
# klookup
# =========================================================================

_klookup_parser = argparse.ArgumentParser(
    description="Lookup kernel symbols"
)
_klookup_parser.add_argument(
    "symbol", nargs="?", type=str, default="",
    help="Address or symbol name to lookup",
)
_klookup_parser.add_argument(
    "-a", "--apply", action="store_true",
    help="applies all the symbols that satisfy the filter",
)
# Legacy alias: earlier kernlens documented ``query`` for the same
# positional; the dest stays ``symbol`` to match pwndbg.


@Command(
    _klookup_parser,
    category=CommandCategory.KERNEL_METADATA,
    aliases=["kl-klookup", "kl-kallsyms", "kl-ks"],
    examples="kl-klookup commit_creds\nkl-klookup 0xffffffff81000000",
)
@OnlyWithKernelSymbols
def kernlens_klookup(symbol: str = "", apply: bool = False) -> None:  # noqa: A002
    query = symbol
    symbols = kdbg.lookup(query)
    if not symbols:
        if not query:
            print(
                message.warn(
                    "kallsyms is unavailable or empty (load a vmlinux that "
                    "carries the kallsyms_* symbols)"
                )
            )
        else:
            print(message.warn(f"no symbol matches {query!r}"))
        return
    for entry in symbols:
        print(f"{entry.address:#x} {entry.type or '?'} {entry.name}")
    print(message.notice(f"{len(symbols)} symbol(s) found"))
    if apply:
        _kallsyms_apply()


def _kallsyms_apply() -> None:
    """Report that ``--apply`` needs an ELF symbol table (pwndbg parity).

    pwndbg reconstructs a symbol table from the kallsyms and loads it into
    the debugger; kernlens reads symbols live, so there is nothing to
    apply.  The option is accepted so scripts written for pwndbg keep
    working, and the limitation is reported instead of failing silently.
    """
    print(
        message.warn(
            "--apply is a pwndbg-only symbol-table rebuild; kernlens reads "
            "kallsyms live, so the loaded symbols are already current"
        )
    )


__all__ = ["Option"]