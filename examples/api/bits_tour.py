#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# ruff: noqa: F821
"""Read a word the way the kernel packs one, with and without the command.

`kl-bits` answers a narrow question -- what is in this 64-bit value -- and
it answers it with `BitOps`, which needs no debugger.  That makes it the
easiest command in the tool to exercise end to end, and the one where a
wrong answer is hardest to notice: every field is a plausible number.

The example walks three words taken from the test kernel, and for each one
shows the `BitOps` call behind the line `kl-bits` prints.  A reader can
check the arithmetic by hand, which is the only way to trust the output of
a tool that is supposed to be telling you about memory you cannot see.

It runs in both places::

    $ python examples/api/bits_tour.py
    (gdb) source /path/to/KernLens/examples/api/bits_tour.py
    (gdb) bittour

The `kl-bits` command form is what a user types at the prompt; this file is
the same arithmetic with the receipts attached.
"""

from __future__ import annotations

import sys

try:
    BitOps  # noqa: B018 - probe for the names gdbinit installs
except NameError:  # pragma: no cover - the GDB path never runs this
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[2] / "src"))
    from kernlens.core.bitops import BitOps


#: A page-table entry with PS (bit 7) and NX (bit 63) set: the 2 MiB huge
#: leaf the tutorial walks to.  `kl-pte` decodes it; `kl-bits` shows the
#: raw bit positions underneath.
HUGE_PTE = 0x80000000004000E3

#: The packed slab counters from the test kernel, laid out as the kernel
#: lays them out: ``frozen`` in bit 0, ``objects`` in bits 1..15, and
#: ``inuse`` from bit 16 up.  Here 16 objects are in use of 15 available
#: -- the over-count a stale pointer leaves behind.
SLAB_COUNTERS = (16 << 16) | (15 << 1) | 1

#: `cpu_online_mask` on a 4-CPU VM: four CPUs, no holes.
ONLINE_MASK = 0b1111


def _section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def _show(label: str, value: int) -> None:
    """Print the lines `kl-bits <value>` prints, using the same calls."""
    print(f"  {label:<16} {value:#018x}")
    # `first_set` / `last_set` are 1-based, following the kernel's own
    # ffs/fls convention: bit 0 reports as 1, and an empty word as 0.
    # A 64 here means bit 63 is set, not that there are 65 bits.
    print(
        f"    scan         : popcount={BitOps.popcount(value)} "
        f"first_set={BitOps.first_set(value)} "
        f"last_set={BitOps.last_set(value)}"
    )
    print(
        f"    power        : is_power_of_2="
        f"{'on' if BitOps.is_power_of_2(value) else 'off'} "
        f"log2_floor={BitOps.log2_floor(value) if value else '?'}"
    )


def bittour() -> None:
    """Walk the three words and check the framing arithmetic.

    Inside GDB the command form is run too, so this file demonstrates
    ``kl-bits`` rather than only reimplementing it: printing the same
    numbers twice would let the two drift apart, and the point of the
    example is that the command and the arithmetic agree.
    """
    print("Bits: what kl-bits prints, and the calls behind each line")

    _section("A page-table entry")
    _show("huge leaf PTE", HUGE_PTE)
    # The two bits that decide whether the walk stops here.
    print(
        f"    PS (bit 7)   : {BitOps.bit_test(HUGE_PTE, 7)}  "
        f"-> {'huge page, no pte level' if BitOps.bit_test(HUGE_PTE, 7) else 'recurse'}"
    )
    print(
        f"    NX (bit 63)  : {BitOps.bit_test(HUGE_PTE, 63)}  "
        f"-> {'not executable' if BitOps.bit_test(HUGE_PTE, 63) else 'executable'}"
    )

    _section("Packed slab counters")
    _show("counters", SLAB_COUNTERS)
    # The field boundaries are the kernel's: frozen in bit 0, objects in
    # bits 1..15, inuse from bit 16.  Getting a shift or width wrong here
    # produces plausible numbers, which is why the layout is stated.
    inuse = BitOps.extract_bits(SLAB_COUNTERS, 16, 16)
    objects = BitOps.extract_bits(SLAB_COUNTERS, 1, 15)
    frozen = BitOps.extract_bits(SLAB_COUNTERS, 0, 1)
    print(f"    inuse        : {inuse}")
    print(f"    objects      : {objects}")
    print(f"    frozen       : {frozen}")
    # The check that matters: more in use than exist is impossible, and
    # that contradiction is what a double-free looks like in the counters.
    print(
        f"    inuse > obj  : {'yes' if inuse > objects else 'no'}"
        f"  -> {'counters disagree with reality' if inuse > objects else 'consistent'}"
    )

    _section("A CPU mask")
    _show("online mask", ONLINE_MASK)
    # `cpumask_next` takes the mask first and the CPU to start after
    # second; reversing them silently returns -1 for a non-empty mask.
    print(
        f"    cpus         : {BitOps.cpumask_count(ONLINE_MASK)} online, "
        f"first={BitOps.cpumask_first(ONLINE_MASK)}"
    )
    print(
        f"    next after 1 : {BitOps.cpumask_next(ONLINE_MASK, 1)}"
        f"  (kl-cpu prints this as the 'Online:' range)"
    )

    _section("The same question through the command")
    # Inside GDB, run the real command rather than describing it.  On the
    # host there is no ``kl-bits`` to run, so the branch is skipped and
    # the file still works as a plain script.
    try:
        import gdb
    except ImportError:
        gdb = None
    if gdb is not None:
        gdb.execute(f"kl-bits {HUGE_PTE:#x}")
    else:
        print(f"  kl-bits {HUGE_PTE:#x}")
        print("    prints the value, the scan line, and the bit string;")
        print("    every number above is one of those fields.")
    print("\n  No debugger is needed: BitOps reads no memory.")


def _command() -> None:
    """Register `bittour` when running inside GDB."""
    try:
        import gdb  # noqa: F401
    except ImportError:  # pragma: no cover - host path
        return

    class BitTourCommand(gdb.Command):
        """bittour -- decode words with BitOps, the way kl-bits does."""

        def __init__(self) -> None:
            super().__init__("bittour", gdb.COMMAND_USER)

        def invoke(self, arg: str, from_tty: bool) -> None:
            bittour()

    _BITTOUR = BitTourCommand()
    gdb.write("bits_tour: run 'bittour' to walk the three words\n")


_command()


if __name__ == "__main__":
    bittour()