#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""CPU topology, MSR, and output commands (pwndbg-style).

``kernlens-cpu`` / ``percpu`` / ``msr`` / ``color``.
"""

from __future__ import annotations

import argparse

import gdb  # type: ignore[import-not-found]

from ..gdb.facade import kdbg
from ..output import message
from ..output.tree import IndentContextManager
from .formatting import fmt_cpu_ranges
from .framework import (
    Command,
    CommandCategory,
    OnlyWithKernelSymbols,
    parse_int_arg,
    parse_msr_range,
)

_MASK64 = 0xFFFFFFFFFFFFFFFF


# =========================================================================
# cpu
# =========================================================================

_cpu_parser = argparse.ArgumentParser(
    description="Displays CPU topology, the online mask, and per-CPU offsets."
)
_cpu_parser.add_argument(
    "cpu", nargs="?", type=int, default=None,
    help="CPU id to describe (default: current CPU)",
)


@Command(
    _cpu_parser,
    category=CommandCategory.CPU,
    aliases=["kl-cpu"],
    examples="kl-cpu\nkl-cpu 3",
)
def kernlens_cpu(cpu: int | None = None) -> None:
    if cpu is None:
        try:
            cpu = kdbg.cur_cpu()
        except (gdb.error, gdb.MemoryError):
            cpu = None
    if cpu is not None and cpu < 0:
        print(message.error("cpu must be >= 0"))
        return
    nr_cpus = kdbg.nr_cpus()
    if cpu is not None and nr_cpus > 0 and cpu >= nr_cpus:
        print(
            message.error(f"cpu {cpu} is out of range (nr_cpus={nr_cpus})")
        )
        return
    indent = IndentContextManager()
    indent.print(
        indent.prefix("Topology") + f": nr_cpus={nr_cpus} "
        f"nr_nodes={kdbg.nr_nodes()} current={cpu if cpu is not None else '?'}"
    )
    if nr_cpus > 0:
        online = [
            index for index in range(nr_cpus)
            if kdbg.cpu_online(index) is True
        ]
        indent.print(
            indent.prefix("Online") + f": {fmt_cpu_ranges(online)} "
            f"({len(online)}/{nr_cpus})"
        )
    if cpu is not None:
        is_online = kdbg.cpu_online(cpu)
        offset = kdbg.percpu_off(cpu)
        with indent:
            indent.print(
                message.on(f"cpu {cpu}")
                if is_online
                else message.off(f"cpu {cpu}")
            )
            indent.print(
                indent.prefix("online")
                + ": "
                + (message.on("True") if is_online else message.off("False"))
            )
            indent.print(
                indent.prefix("percpu_off")
                + ": "
                + (
                    indent.addr_hex(offset)
                    if offset is not None
                    else message.warn("?")
                )
            )


# =========================================================================
# percpu
# =========================================================================

_percpu_parser = argparse.ArgumentParser(
    description="Resolves a per-CPU symbol to its runtime address for a CPU."
)
_percpu_parser.add_argument(
    "symbol", type=str, help="a per-CPU symbol (e.g. current_task)",
)
_percpu_parser.add_argument(
    "cpu", nargs="?", type=int, default=None,
    help="CPU id (default: current CPU)",
)


def _percpu_link(name: str) -> int | None:
    """Return the *bare* (link-time) value of a per-CPU symbol.

    Per-CPU section symbols are **zero-based** on x86_64: because
    ``__per_cpu_start`` is the first thing in the section, GDB reports
    its address as ``0``, so each symbol's bare value *is* its offset
    inside the per-CPU area (``0x1fb80`` for ``current_task``).  The
    KASLR slide must **not** be added -- ``kvar_addr`` does add it and
    would turn the offset into a bogus address -- so the raw expression
    is used directly.  ``None`` means the symbol is absent (the raw
    ``parse_and_eval`` raises); ``0`` is a genuine value, not a failure.
    """
    return kdbg.u64(f"(unsigned long)&{name}")


@Command(
    _percpu_parser,
    category=CommandCategory.CPU,
    aliases=["kl-percpu"],
    examples="kl-percpu current_task\nkl-percpu current_task 2",
)
@OnlyWithKernelSymbols
def kernlens_percpu(symbol: str, cpu: int | None = None) -> None:
    symbol = symbol.lstrip("&")
    if not symbol:
        print(message.error("per-CPU symbol must not be empty"))
        return
    if cpu is None:
        try:
            cpu = kdbg.cur_cpu()
        except (gdb.error, gdb.MemoryError):
            cpu = None
    if cpu is None:
        print(
            message.error(
                "cannot determine the current CPU; pass an explicit cpu"
            )
        )
        return
    if cpu < 0:
        print(message.error("cpu must be >= 0"))
        return
    nr_cpus = kdbg.nr_cpus()
    if nr_cpus > 0 and cpu >= nr_cpus:
        print(message.error(f"cpu {cpu} is out of range (nr_cpus={nr_cpus})"))
        return
    # A per-CPU symbol's *bare* value is its offset into the per-CPU
    # area, so both ends come from the raw expression (never the
    # KASLR-adjusted ``kvar_addr``: adding the slide to an offset would
    # produce an address far outside the section).
    symbol_addr = _percpu_link(symbol)
    start_addr = _percpu_link("__per_cpu_start")
    end_addr = _percpu_link("__per_cpu_end")
    cpu_offset = kdbg.percpu_off(cpu)
    if symbol_addr is None:
        print(
            message.error(
                f"cannot resolve {symbol!r}; load a matching vmlinux first"
            )
        )
        return
    if cpu_offset is None:
        print(message.error(f"cannot read __per_cpu_offset[{cpu}]"))
        return
    if start_addr is None:
        print(
            message.error(
                "cannot determine the start of the per-CPU area; the "
                "vmlinux has no __per_cpu_start symbol"
            )
        )
        return
    if symbol_addr < start_addr or (
        end_addr is not None and symbol_addr >= end_addr
    ):
        print(message.error(f"{symbol!r} is not a per-CPU symbol"))
        return
    runtime = (cpu_offset + (symbol_addr - start_addr)) & _MASK64
    indent = IndentContextManager()
    indent.print(
        indent.prefix("Symbol") + f": {symbol} (cpu {cpu})"
    )
    indent.print(indent.prefix("Address") + ": " + indent.addr_hex(runtime))
    indent.print(
        indent.prefix("percpu_off") + ": " + indent.aux_hex(cpu_offset)
    )


# =========================================================================
# msr
# =========================================================================

X86_MSRS: dict[str, int] = {
    "MSR_EFER": 0xC0000080,
    "MSR_STAR": 0xC0000081,
    "MSR_LSTAR": 0xC0000082,
    "MSR_CSTAR": 0xC0000083,
    "MSR_SYSCALL_MASK": 0xC0000084,
    "MSR_FS_BASE": 0xC0000100,
    "MSR_GS_BASE": 0xC0000101,
    "MSR_KERNEL_GS_BASE": 0xC0000102,
    "MSR_TSC_AUX": 0xC0000103,
}

MSR_REGS: dict[int, str] = {
    0xC0000080: "$efer",
    0xC0000081: "$star",
    0xC0000082: "$lstar",
    0xC0000083: "$cstar",
    0xC0000084: "$fmask",
    0xC0000100: "$fs_base",
    0xC0000101: "$gs_base",
    0xC0000102: "$kernel_gs_base",
    0xC0000103: "$tsc_aux",
}


def _msr_parse(text: str) -> int:
    """Resolve an MSR name or numeric value."""
    named = X86_MSRS.get(text.strip().upper())
    if named is not None:
        return named
    return parse_int_arg(text)


def cpu_limitcheck(text: str) -> int:
    """argparse type for pwndbg's ``-c/--cpu`` (must be < nr_cpu_ids).

    Mirrors pwndbg's check so ``buddydump -c`` rejects an out-of-range CPU
    with the same message instead of silently walking a bogus index.
    """
    value = int(text, 0)
    nr_cpus = kdbg.nr_cpus()
    if value < nr_cpus:
        return value
    raise argparse.ArgumentTypeError(
        "The --cpu option takes in a number less than nr_cpu_ids "
        f"({nr_cpus})."
    )


def _msr_value(register: str) -> int | None:
    """Read an MSR pseudo-register, or ``None`` when unavailable.

    Some remote targets expose ``$lstar`` as a value that cannot be cast
    to ``long``; :meth:`gdb.Frame.read_register` reads the raw register
    instead, so both paths are tried before giving up.
    """
    try:
        return int(gdb.parse_and_eval(register)) & _MASK64
    except (gdb.error, gdb.MemoryError, TypeError, ValueError):
        pass
    try:
        frame = gdb.newest_frame()
        return int(frame.read_register(register.lstrip("$"))) & _MASK64
    except (gdb.error, gdb.MemoryError, AttributeError, TypeError, ValueError):
        return None


def _msr_read(number: int) -> None:
    """Print one MSR's value from GDB's register set."""
    register = MSR_REGS.get(number)
    if register is None:
        print(
            message.error(
                f"MSR {number:#x} has no GDB register; use a bare value "
                "only for the MSRs in kl-msr --list"
            )
        )
        return
    value = _msr_value(register)
    if value is None:
        print(
            message.error(
                f"cannot read {register}; the remote target does not "
                "expose this MSR"
            )
        )
        return
    print(f"{number:#010x}: {value:#018x}")


def _msr_write(number: int, value: int) -> None:
    """Write one MSR through GDB's convenience register."""
    register = MSR_REGS.get(number)
    if register is None:
        print(message.error(f"MSR {number:#x} has no GDB register to write"))
        return
    try:
        gdb.execute(f"set {register} = {value & _MASK64:#x}")
    except (gdb.error, gdb.MemoryError) as exc:
        print(message.error(f"cannot write {register}: {exc}"))
        return
    print(message.success(f"wrote {number:#014x} = {value:#018x}"))


_msr_parser = argparse.ArgumentParser(
    description="Reads or writes x86_64 model-specific registers (via GDB)."
)
_msr_parser.add_argument(
    "msr", nargs="?", type=_msr_parse, default=None,
    help="MSR value or name",
)
_msr_parser.add_argument(
    "-w", "--write", metavar="write_value", type=int, nargs="?",
    default=None, help="value to write in MSR",
)
_msr_parser.add_argument(
    "-l", "--list", dest="list_msr", action="store_true",
    default=False, help="list common MSRs for the current arch",
)
_msr_parser.add_argument(
    "-r", "--range", type=parse_msr_range, nargs="?", default=None,
    dest="msr_range", help="dash separated range of MSRs to read",
)
# Legacy alias: earlier KernLens used bare ``--range``; it is the same
# option, so nothing extra is registered here beyond the help text.


@Command(
    _msr_parser,
    category=CommandCategory.CPU,
    aliases=["kl-msr"],
    examples=(
        "kl-msr --list\n"
        "kl-msr MSR_LSTAR\n"
        "kl-msr 0xc0000082\n"
        "kl-msr MSR_TSC_AUX --write 0x1\n"
        "kl-msr --range 0xc0000080-0xc0000103"
    ),
)
def kernlens_msr(
    msr: int | None = None,
    write: int | None = None,
    list_msr: bool = False,
    msr_range: tuple[int, int] | None = None,
) -> None:
    # pwndbg evaluates the explicit MSR before the range, so a positional
    # wins when both are given (`if msr: ... elif msr_range: ...`).
    if msr is not None:
        if write is not None:
            _msr_write(msr, write)
            return
        _msr_read(msr)
        return
    if list_msr:
        width = max(len(name) for name in X86_MSRS)
        for name, value in X86_MSRS.items():
            print(f"{name.ljust(width)} = {value:#010x}")
        return
    if msr_range is not None:
        for value in range(msr_range[0], msr_range[1] + 1):
            _msr_read(value)
        return
    _msr_parser.print_usage()


# =========================================================================
# color
# =========================================================================

_color_parser = argparse.ArgumentParser(
    description="Enable, disable, or toggle ANSI color output."
)
_color_parser.add_argument(
    "state", nargs="?", choices=["on", "off", "toggle"], default="",
    help="explicit state; no argument prints the current state",
)


@Command(
    _color_parser,
    category=CommandCategory.OUTPUT,
    aliases=["kl-color"],
    examples="kl-color on\nkl-color off\nkl-color toggle",
)
def kernlens_color(state: str = "") -> None:
    if state == "on":
        kdbg.enable_color()
    elif state == "off":
        kdbg.disable_color()
    elif state == "toggle":
        kdbg.color_enabled = not kdbg.color_enabled
    enabled = kdbg.color_enabled
    print(
        message.notice("KernLens color:")
        + " "
        + (message.on("on") if enabled else message.off("off"))
    )


__all__ = ["MSR_REGS", "X86_MSRS"]