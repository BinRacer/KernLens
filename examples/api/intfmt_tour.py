#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# ruff: noqa: F821
"""Format the values a kernel reader actually produces.

`IntCodec` turns bytes into integers; `IntFmt` turns integers into
something a human can scan.  The second half sounds cosmetic and is not:
the whole point of a tracer's output is that a reader can tell at a
glance whether a value is plausible, and `0x4000` versus `16K` versus
`order 2` are three different questions about the same number.

This example is organised by *what the value is*, because that is the
decision a script actually faces:

1. **An address** -- `addr`, `hex8`/`hex16`/`hex32`/`hex64`, `pfn`,
   `page_off`.  Fixed width matters: a zero-padded address column lines
   up, an unpadded one does not, and a misaligned dump is read wrong.
2. **A size** -- `size`, which picks `K`/`M`/`G` from the magnitude.
   `kl-slab` prints `Object Size: 0x400` next to `Size: 0x400`; `size()`
   is how a script would say `1K` instead.
3. **A span of bytes** -- the `bytes_*` family: `hex`, `dump`, `ascii`,
   `cstring`, and the typed `bytes_u16/u32/u64_array` readers.  This is
   the family a hexdump-style tracer needs, and it is the one most worth
   seeing side by side on the same buffer.
4. **A signed or masked value** -- `signed`, `signed_hex`, `mask`,
   `bits`, `flags`.  `signed(-1)` is `-1`, `signed_hex(-1)` is `-0x1`;
   printing a `long` error code as unsigned hex hides the fact that it is
   negative, which is how `IS_ERR()` mistakes happen.
5. **A time** -- `timestamp`, `duration_ns`.  `kl-kdmesg -T` uses the
   first; a tracer printing latency uses the second.

It runs with no debugger; the buffer examples use a synthetic 64-byte
block shaped like a `struct page`, and the same code inside GDB reads a
real one::

    $ python examples/api/intfmt_tour.py
    (gdb) source /path/to/KernLens/examples/api/intfmt_tour.py
    (gdb) ifmt
"""

from __future__ import annotations

import sys

try:
    IntFmt  # noqa: B018 - probe for the names gdbinit installs
except NameError:  # pragma: no cover - the GDB path never runs this
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[2] / "src"))
    from kernlens.core.fmt import IntFmt

    try:
        from kernlens.core.codec import ByteOrder
    except ImportError:  # pragma: no cover
        ByteOrder = None  # type: ignore[assignment]


#: The address used throughout: a real 6.1.134 direct-map address, so the
#: numbers below are the ones a reader would actually see.
ADDRESS = 0xFFFF96E3432A1C40

#: The *physical* address that direct-map address maps to, on the same
#: kernel.  `pfn()` and `page_off()` take a physical address and do not
#: translate -- the docstrings say so -- so passing `ADDRESS` to either
#: produces a number that looks like a PFN and is not.  Keeping both
#: constants here is the point of step 1.
PHYSICAL = 0x32A1C40

#: PTE flag names, covering the bits this example sets.  Bits 9-11 are
#: software-available and stay unnamed here on purpose: that is what makes
#: `flags()` print `0xc00` at the end, which is the behaviour worth
#: showing -- an unnamed field is reported, not dropped.
PTE_FLAGS: dict[int, str] = {
    0: "P",
    1: "RW",
    2: "US",
    3: "PWT",
    4: "PCD",
    5: "A",
    6: "D",
    7: "PS",
    8: "G",
    63: "NX",
}


def _section(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 58 - len(title)))


def addresses() -> None:
    """Steps 1: fixed-width address forms, and which take a physical address.

    `hex` prints the minimum digits, so `0x400` and `0x4000` do not line
    up in a column.  `hex16` always prints sixteen, which is what a dump
    wants.  `addr` is the default for a kernel pointer and matches what
    the commands print.

    The trap in this section is `pfn()` and `page_off()`: both take a
    **physical** address and do not translate.  Handing them a virtual
    address produces `0xffff96e3432a1` -- a number shaped like a PFN, off
    by the whole direct-map base, and wrong in a way that looks fine.
    """
    _section("1. addresses")
    print(f"virtual     : {ADDRESS:#x}")
    print(f"physical    : {PHYSICAL:#x}")
    print(f"addr        : {IntFmt.addr(ADDRESS)}")
    print(f"hex64       : {IntFmt.hex64(ADDRESS)}")
    print(f"hex32       : {IntFmt.hex32(ADDRESS)}")
    print(f"hex16       : {IntFmt.hex16(0x1234)}")
    print(f"hex8        : {IntFmt.hex8(0x12)}")
    print(f"hex         : {IntFmt.hex(ADDRESS)}   (minimum digits)")

    # The physical-address pair, used correctly and then deliberately
    # wrongly, so the difference is visible rather than described.
    print(f"\npfn({PHYSICAL:#x})      : {IntFmt.pfn(PHYSICAL)}")
    print(f"page_off({PHYSICAL:#x}) : {IntFmt.page_off(PHYSICAL)}")
    print(
        f"pfn({ADDRESS:#x})  : {IntFmt.pfn(ADDRESS)}"
        "   <- wrong: this is a virtual address"
    )
    print(
        "  hex16 on a small value is how a column stays aligned; hex is for\n"
        "  prose, where the padding is just noise.  And pfn/page_off take a\n"
        "  physical address: translate first (`kl-v2p`), or the result is a\n"
        "  plausible number off by the direct-map base."
    )


def sizes() -> None:
    """Steps 2: a byte count in the unit a reader thinks in."""
    _section("2. sizes")
    for count in (0, 8, 512, 1024, 1536, 1 << 20, 3 * (1 << 30)):
        print(f"{count:>12d} bytes -> {IntFmt.size(count)}")
    print(
        "  `kl-slab` prints raw hex; size() is what a script would use to\n"
        "  say 1K rather than 0x400."
    )


def byte_views() -> None:
    """Steps 3: five views of the same 64-byte buffer.

    This is the section to read if you are writing anything hexdump-ish.
    The buffer is a real `struct page` when a target is attached, so the
    flags word and the list pointers are visible in the right places.
    """
    _section("3. the same buffer, five ways")
    buffer, source = _page_bytes()
    print(f"source: {source}")
    print(f"length: {len(buffer)} bytes")
    print("\n-- bytes_hex (compact)")
    print(f"  {IntFmt.bytes_hex(buffer)}")
    print("\n-- bytes_dump (offset, hex, ascii)")
    for line in IntFmt.bytes_dump(buffer).splitlines():
        print(f"  {line}")
    print("\n-- bytes_ascii (printable only)")
    print(f"  {IntFmt.bytes_ascii(buffer)!r}")
    print("\n-- bytes_cstring (stops at the first NUL)")
    print(f"  {IntFmt.bytes_cstring(buffer)!r}")
    print("\n-- bytes_u64_array (typed)")
    print(f"  {IntFmt.bytes_u64_array(buffer, 4)}")
    print("\n-- bytes_u32_array (typed)")
    print(f"  {IntFmt.bytes_u32_array(buffer, 4)}")
    print("\n-- bytes_u16_array (typed)")
    print(f"  {IntFmt.bytes_u16_array(buffer, 8)}")


def signed_and_masked() -> None:
    """Steps 4: negative values, masks, bitfields, flag sets.

    `signed(-1)` is `-1` and `signed_hex(-1)` is `-0x1`; printing an
    error code through an unsigned formatter hides that it is negative,
    and `IS_ERR()` mistakes follow.  `flags()` is the inverse of building
    a bitfield by hand: pass a name table, get `0x5(A|C)`.
    """
    _section("4. signed, masked, and flagged")
    for value in (-1, -5, 0, 5):
        print(
            f"value={value:>4d}  signed={IntFmt.signed(value):>6s}"
            f"  signed_hex={IntFmt.signed_hex(value):>8s}"
            f"  mask={IntFmt.mask(value)}"
        )
    print(f"\nbits(0b1010, 4) : {IntFmt.bits(0b1010, 4)}")
    print(f"bits(0xff, 8)   : {IntFmt.bits(0xFF, 8)}")

    # A real PTE from the test kernel.  The low bits are the flags; the
    # upper bits are the frame address, which `flags()` reports as a
    # leftover hex group -- that is deliberate, since silently dropping
    # unnamed bits would hide a field the caller forgot to name.
    pte = 0x80000000032A1C67
    low = pte & 0xFFF
    print(f"\nPTE {pte:#x}")
    print(f"  low 12 bits : {low:#x}")
    print(f"  flags()     : {IntFmt.flags(low, PTE_FLAGS)}")
    print(f"  whole entry : {IntFmt.flags(pte, PTE_FLAGS)}")
    print(
        "  flags() is what turns a bitfield into a name list; the table is\n"
        "  the caller's, because only the caller knows which struct it is.\n"
        "  Unnamed bits are reported as a hex group rather than dropped, so\n"
        "  a field you forgot to name is visible instead of silent."
    )


def offsets_and_spans() -> None:
    """Steps 5: offsets relative to a base, the way a disassembly shows them.

    `field_off` prints a struct field offset, `off` prints `base+delta`,
    and `page_off` prints the offset inside a page.  They are small, but
    a tracer that prints `+0x18` instead of `0xffff...b698` is readable in
    a way that the absolute form is not.
    """
    _section("5. offsets and spans")
    print(f"field_off(0x18)          : {IntFmt.field_off(0x18)}")
    print(f"off(0xffff888000001000, 0x18) : {IntFmt.off(0xFFFF888000001000, 0x18)}")
    # `page_off` takes a physical address, like `pfn` above.
    print(f"page_off({PHYSICAL:#x})   : {IntFmt.page_off(PHYSICAL)}")
    print(f"percent(3, 7)            : {IntFmt.percent(3, 7)}")


def times() -> None:
    """Steps 6: wall-clock and elapsed, which are different questions.

    `timestamp` takes seconds since the epoch and prints what `-T` prints
    in `kl-kdmesg`.  `duration_ns` takes nanoseconds and prints a human
    span -- the two are not interchangeable, and a tracer that mixes them
    reports a boot time as a latency.
    """
    _section("6. time")
    print(f"timestamp(1700000000.0) : {IntFmt.timestamp(1700000000.0)}")
    print(f"duration_ns(1_500)      : {IntFmt.duration_ns(1_500)}")
    print(f"duration_ns(1_234_567)  : {IntFmt.duration_ns(1_234_567)}")
    print(f"duration_ns(1_234_567_890) : {IntFmt.duration_ns(1_234_567_890)}")


def _page_bytes() -> tuple[bytes, str]:
    """Raw bytes of one `struct page`, and where they came from.

    Inside GDB this is a real page from the vmemmap; outside it is a
    stand-in of the same shape.  The source string says which, because an
    example that silently substitutes synthetic data for kernel data is
    worse than one that refuses to run.
    """
    try:
        vmemmap = read_kvar("vmemmap_base")  # noqa: F821
        raw = kdbg.reader.read_bytes(int(vmemmap), 64)  # noqa: F821
        if raw:
            return raw, f"live struct page at {int(vmemmap):#x}"
    except (NameError, AttributeError, TypeError):
        pass
    # Same shape: a flags word, then pointers that look like addresses.
    stand_in = (
        (0x0007FFFFC0001000).to_bytes(8, "little")
        + (0xFFFF96E340000008).to_bytes(8, "little")
        + bytes(48)
    )
    return stand_in, "synthetic stand-in (no target attached)"


def ifmt() -> None:
    """Run the whole tour."""
    print("IntFmt tour -- no debugger required")
    addresses()
    sizes()
    byte_views()
    signed_and_masked()
    offsets_and_spans()
    times()
    print(
        "\nThe reason this is not cosmetic: a tracer's output is read by\n"
        "someone deciding whether a value is plausible.  `16K` says a slab\n"
        "is two pages; `0x4000` says nothing until it is divided by 4096.\n"
        "Pick the form that answers the question the reader has.\n"
    )


def _command() -> None:
    """Register `ifmt` when running inside GDB; a no-op elsewhere.

    The attribute check matters: a stub `gdb` module is importable but has
    no `Command`/`COMMAND_USER`, and the tour must still be importable for
    its output to be tested on the host.
    """
    try:
        import gdb
    except ImportError:
        return

    if not hasattr(gdb, "Command") or not hasattr(gdb, "COMMAND_USER"):
        return

    class IFmtCommand(gdb.Command):
        """ifmt -- every IntFmt form, on realistic values."""

        def __init__(self) -> None:
            super().__init__("ifmt", gdb.COMMAND_USER)

        def invoke(self, arg: str, from_tty: bool) -> None:
            ifmt()

    _IFMT = IFmtCommand()
    gdb.write("intfmt_tour: run 'ifmt' to see every formatting form\n")


_command()


if __name__ == "__main__":
    ifmt()