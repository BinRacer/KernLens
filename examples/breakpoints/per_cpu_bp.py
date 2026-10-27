#!/usr/bin/env python3
#
# ruff: noqa: F821
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Read the right CPU's copy of a per-CPU variable from a breakpoint.

A per-CPU variable has one copy per CPU, and which copy is live depends
on which CPU is running.  GDB shows you a single "current" thread, so the
naive thing -- poking the symbol GDB knows -- reads CPU 0's copy no matter
which CPU actually took the breakpoint.  On a 4-CPU target that is wrong
three times out of four, and it is wrong silently.

This example demonstrates the three commands that get it right, and the
one GDB facility that makes the target decide rather than the reader:

1. `kl-cpu` -- the topology: how many CPUs, which are online, and each
   one's `percpu_off`.  The offset is what turns a per-CPU symbol into an
   address, so it has to come first.
2. `kl-percpu <symbol> <cpu>` -- one symbol, one CPU, resolved.
3. `kl-msr -l` -- the MSR numbers, which are the other half of per-CPU
   state: `GS_BASE` is how the kernel finds the per-CPU area at all, and
   `TSC_AUX` carries the CPU number in user space.

The breakpoint part is `pbreak`, which stops in `schedule` and reports
which CPU took it *and* the correct `current` for that CPU.  The CPU
number comes from the target through `kl-percpu current_task`, not from
`gdb.selected_thread()`, because a thread id is not a CPU id.

Source it after `gdbinit.py`::

    (gdb) source /path/to/KernLens/gdbinit.py
    (gdb) source /path/to/KernLens/examples/breakpoints/per_cpu_bp.py
    (gdb) pbreak                # break in schedule, report per-CPU state
    (gdb) pbreak --cpu 2        # only stop when CPU 2 is the one running
    (gdb) pbreak --off          # remove it

This is in `breakpoints/` rather than `api/` because the point is not the
commands -- it is that a breakpoint callback has to resolve per-CPU state
for the CPU it landed on, and that decision cannot be made outside one.
"""

from __future__ import annotations

import argparse
import shlex

try:
    import gdb
except ImportError as exc:  # pragma: no cover - GDB only
    raise SystemExit("per_cpu_bp.py must be sourced by GDB") from exc


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
    gdb.write(f"\n=== {title} " + "=" * max(0, 58 - len(title)) + "\n")


def _run(command: str) -> None:
    gdb.write(f"-- {command}\n")
    gdb.execute(command)


def topology() -> None:
    """Steps 1-3: the CPU set, one per-CPU resolution, and the MSRs."""
    _run("kl-base")

    _section("1. which CPUs exist (kl-cpu)")
    _run("kl-cpu")

    _section("2. one per-CPU symbol, resolved per CPU (kl-percpu)")
    # `current_task` is per-CPU by definition, so resolving it for every
    # CPU at once is the clearest possible demonstration: four different
    # addresses, and only one of them is the task actually running.
    for cpu in range(min(kdbg.nr_cpus(), 4)):
        _run(f"kl-percpu current_task {cpu}")

    _section("3. the MSRs behind per-CPU addressing (kl-msr -l)")
    _run("kl-msr -l")


class PerCpuBreakpoint(gdb.Breakpoint):
    """Stop in `schedule` and report the *correct* per-CPU state.

    The interesting line is `_cpu_for_this_hit()`.  There is no GDB
    expression that answers "which CPU am I on"; the only reliable way is
    to read a per-CPU value and see which CPU's copy matches.  When
    `--cpu N` is given, hits on other CPUs are passed through silently so
    the user sees only the one they asked about.
    """

    def __init__(self, symbol: str, only_cpu: int | None) -> None:
        super().__init__(symbol, gdb.BP_BREAKPOINT, internal=False)
        self.symbol = symbol
        self.only_cpu = only_cpu

    def _cpu_for_this_hit(self) -> int | None:
        """Which CPU's copy of `current_task` is live right now.

        The trick is that `current_task` is the *address* of the running
        task, and exactly one per-CPU copy holds a plausible task
        pointer.  Comparing the resolved addresses against the value the
        kernel's own `current` resolves to is what makes this correct
        without needing a `$gs_base` GDB cannot give us over QEMU's
        gdbstub.
        """
        try:
            expected = int(gdb.parse_and_eval("(unsigned long)current_task"))
        except gdb.error:
            return None
        for cpu in range(kdbg.nr_cpus()):
            copy = kdbg.percpu_off(cpu) + int(
                gdb.parse_and_eval("(unsigned long)&current_task")
            )
            if copy == expected:
                return cpu
        return None

    def stop(self) -> bool:
        cpu = self._cpu_for_this_hit()
        if self.only_cpu is not None and cpu != self.only_cpu:
            return False
        gdb.write(
            f"\npbreak: {self.symbol} on cpu "
            f"{cpu if cpu is not None else 'unknown'}\n"
        )
        if cpu is not None:
            gdb.execute(f"kl-percpu current_task {cpu}")
            gdb.execute(f"kl-cpu {cpu}")
        return False


class PerCpuCommand(gdb.Command):
    """pbreak [--cpu N] [--off] -- break in schedule, report per-CPU state."""

    def __init__(self) -> None:
        super().__init__("pbreak", gdb.COMMAND_USER)
        self._installed: PerCpuBreakpoint | None = None

    def invoke(self, arg: str, from_tty: bool) -> None:
        parser = argparse.ArgumentParser(prog="pbreak", add_help=False)
        parser.add_argument("--cpu", type=int, default=None)
        parser.add_argument("--off", action="store_true")
        try:
            args = parser.parse_args(shlex.split(arg))
        except SystemExit:
            gdb.write("usage: pbreak [--cpu N] [--off]\n")
            return

        if args.off:
            if self._installed is not None:
                self._installed.delete()
                self._installed = None
                gdb.write("pbreak: removed\n")
            else:
                gdb.write("pbreak: no breakpoint was installed\n")
            return

        if self._installed is not None:
            self._installed.delete()
        topology()
        self._installed = PerCpuBreakpoint("schedule", args.cpu)
        gdb.write(
            f"pbreak: installed on schedule, "
            f"{'cpu ' + str(args.cpu) if args.cpu is not None else 'any cpu'}\n"
        )


_PBREAK = PerCpuCommand()

gdb.write(
    "per_cpu: run 'pbreak' to watch schedule with correct per-CPU reads, "
    "'pbreak --off' to remove\n"
)