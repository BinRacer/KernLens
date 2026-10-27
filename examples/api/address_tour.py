#!/usr/bin/env python3
#
# ruff: noqa: F821
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Carry one address through all nine views KernLens offers.

The nine commands below are not nine ways to ask the same question.
Each answers something the previous one could not, and the order is the
order a reader needs them in:

1. `kl-addr` -- what kind of address is this, and is it even canonical.
2. `kl-page` -- the same question plus the physical translation, which
   `kl-addr` omits because it is not always possible.
3. `kl-pt` -- the four (or five) index tuples.  Pure arithmetic, no
   memory read, so it works on any address including an unmapped one.
4. `kl-walk` -- the real page tables, level by level, reading memory.
5. `kl-pagewalk` -- the same walk in pwndbg's format, for people who
   already read that output.
6. `kl-pte` -- decode one entry by hand, once the walk told you which
   entry to look at.
7. `kl-v2p` -- virtual to physical, with the leaf size stated.
8. `kl-p2v` -- the inverse, which is the only view that works when you
   have a physical address and no virtual one (a crash dump, a DMA log).
9. `kl-pageinfo` -- the `struct page`, which is where the allocator
   keeps its own opinion of the frame.

The interesting detail is step 3 versus step 4: `kl-pt` will happily
compute indices for an unmapped address and `kl-walk` will then report
the first absent entry.  That difference is how a wrong address gets
found -- see the note printed at the end of the run.

Source it after `gdbinit.py` and run `atour`::

    (gdb) source /path/to/KernLens/gdbinit.py
    (gdb) source /path/to/KernLens/examples/api/address_tour.py
    (gdb) atour                 # uses a computed direct-map address
    (gdb) atour 0xffffffff9c61b680

`atour` also accepts `--offset N`, which shifts the address by `N` bytes
before the tour starts -- useful for stepping across a huge-page
boundary and watching `kl-walk` change its answer.
"""

from __future__ import annotations

import argparse
import shlex

try:
    import gdb
except ImportError as exc:  # pragma: no cover - GDB only
    raise SystemExit("address_tour.py must be sourced by GDB") from exc


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


def _direct_map_sample() -> int:
    """A known-good direct-map address on this target.

    The direct map does not start at a fixed address: `page_offset_base`
    is itself randomised, so the textbook `0xFFFF888000000000` from the
    ELF is *not* the runtime base.  Reading the variable is the only way
    to get an address that is genuinely mapped, which is what makes the
    later walk succeed instead of reporting an absent pgd entry.
    """
    base = read_kvar("page_offset_base")  # noqa: F821
    return int(base) + 0x32A1C40


def _page_struct(physical: int) -> int:
    """`struct page` for a physical address, via the vmemmap base.

    `vmemmap_base` is randomised for the same reason `page_offset_base`
    is, so it is read rather than assumed.  The stride is
    `kdbg.page_bytes()`, which is `sizeof(struct page)` -- 64 on this
    target -- and *not* the page size, which is a distinction worth
    getting right the first time.
    """
    vmemmap = read_kvar("vmemmap_base")  # noqa: F821
    pfn = physical >> 12
    return int(vmemmap) + pfn * kdbg.page_bytes()  # noqa: F821


def _run(command: str) -> None:
    """Execute a KernLens command, echoing it.

    Echoing is the whole point of this example: a reader should be able
    to copy any single line below and run it themselves.
    """
    gdb.write(f"-- {command}\n")
    gdb.execute(command)


def _leaf_entry(address: int) -> tuple[int, str]:
    """The raw leaf PTE/PMD value for ``address``, and its level name.

    This uses ``kdbg.walk()`` rather than arithmetic on ``CR3``: the
    walker already resolved the 4-versus-5-level question and already
    knows which level terminated the walk, so asking it again by hand is
    how the first version of this example got `None` -- `pmd_entry_addr`
    wants a pmd *table base*, not the CR3 value.

    Returns ``(value, level_name)``.  Raises when the walk never reached
    a leaf, which is the case the caller is meant to report rather than
    paper over.
    """
    result = kdbg.walk(address)  # noqa: F821
    if not result.ok or not result.levels:
        raise RuntimeError(
            f"no leaf for {address:#x}: {result.note or 'walk produced no levels'}"
        )
    leaf = result.levels[-1]
    return leaf.value, leaf.name


def tour(address: int) -> None:
    """Run one address through every view, in dependency order."""
    # `kl-base` has to come first.  Without it the symbol table is still
    # in link-time addresses, and `kl-walk` would start from a CR3 that
    # belongs to the wrong slide.
    _run("kl-base")

    _section("1. classify (kl-addr)")
    _run(f"kl-addr {address:#x}")

    _section("2. classify + translate (kl-page)")
    _run(f"kl-page {address:#x}")

    _section("3. indices, no memory read (kl-pt)")
    _run(f"kl-pt {address:#x}")

    _section("4. walk the live tables (kl-walk)")
    _run(f"kl-walk {address:#x}")

    _section("5. the same walk, pwndbg format (kl-pagewalk)")
    _run(f"kl-pagewalk {address:#x}")

    _section("6. decode one entry (kl-pte)")
    try:
        value, level = _leaf_entry(address)
    except RuntimeError as exc:
        gdb.write(f"-- skipped: {exc}\n")
    else:
        gdb.write(f"-- leaf level: {level}\n")
        _run(f"kl-pte {value:#x} {address:#x}")

    _section("7. virtual to physical (kl-v2p)")
    _run(f"kl-v2p {address:#x}")

    _section("8. physical to virtual (kl-p2v)")
    # `KAddr.virt_to_phys` takes the direct-map base as an argument, and
    # its default is the *link-time* `PAGE_OFFSET_BASE`.  On a KASLR
    # kernel that default is wrong: `page_offset_base` is itself
    # randomised, so passing it explicitly is the difference between
    # 0x32a1c40 and 0xe63432a1c40.  This is the single most common
    # arithmetic mistake with this API, which is why the example spells
    # it out instead of using the default.
    physical = KAddr.virt_to_phys(  # noqa: F821
        address, read_kvar("page_offset_base")  # noqa: F821
    )
    _run(f"kl-p2v {physical:#x}")

    _section("9. the struct page (kl-pageinfo)")
    _run(f"kl-pageinfo {_page_struct(physical):#x}")

    _section("reading the result")
    gdb.write(
        "Steps 3 and 4 are the pair worth comparing.  `kl-pt` computed\n"
        "indices for any address you give it -- it is arithmetic, so it\n"
        "never fails.  `kl-walk` reads memory, so it stops at the first\n"
        "entry that is not present.  An address that gets indices from\n"
        "step 3 but no walk from step 4 is unmapped: on this target that\n"
        "happens the moment you subtract `page_offset_base` twice, or use\n"
        "the link-time direct-map base instead of the runtime one.\n"
    )


class AddressTourCommand(gdb.Command):
    """atour [address] [--offset N] -- one address, all nine views."""

    def __init__(self) -> None:
        super().__init__("atour", gdb.COMMAND_USER)

    def invoke(self, arg: str, from_tty: bool) -> None:
        parser = argparse.ArgumentParser(prog="atour", add_help=False)
        parser.add_argument("address", nargs="?", default=None)
        parser.add_argument("--offset", type=lambda s: int(s, 0), default=0)
        try:
            # GDB strips the quoting around a two-token argument, so a
            # plain split would mis-handle anything with spaces.  shlex
            # keeps this consistent with how the other examples parse.
            args = parser.parse_args(shlex.split(arg))
        except SystemExit:
            gdb.write("usage: atour [address] [--offset N]\n")
            return

        address = (
            int(args.address, 0) if args.address else _direct_map_sample()
        )
        tour(address + args.offset)


_ATOUR = AddressTourCommand()

gdb.write(
    "address_tour: run 'atour' to walk a direct-map address, "
    "'atour <address>' for your own\n"
)