#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# ruff: noqa: F821
"""Show a kernel value as every width the kernel might have stored it in.

`kl-int` exists because the same 32 bits mean different numbers depending
on where they came from.  A value that arrives as ``-1`` from a signed
field and as ``4294967295`` from an unsigned one are the same bytes on the
wire, and telling them apart by hand is how a length field becomes an
overflow.

The example runs the command's own arithmetic on three values that each
break a different assumption, and prints the ``IntCodec`` call that
produced each number.  It needs no debugger: ``IntCodec`` is the pure
half of the package.

It runs in both places::

    $ python examples/api/int_tour.py
    (gdb) source /path/to/KernLens/examples/api/int_tour.py
    (gdb) inttour
"""

from __future__ import annotations

import sys

try:
    IntCodec  # noqa: B018 - probe for the names gdbinit installs
except NameError:  # pragma: no cover - the GDB path never runs this
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[2] / "src"))
    from kernlens.core.codec import IntCodec

from kernlens.core.codec import ByteOrder, IntType  # noqa: E402


#: Three values, each chosen because one width tells a different story.
#:
#: - ``-1``: fits I32, does not fit U32, ends a range check either way.
#: - ``0x40000000``: the 1 GiB boundary where a signed 32-bit length goes
#:   negative if it is ever treated as signed.
#: - ``0xffffffffffffffff``: the canonical "all ones", which is a valid
#:   address mask and an invalid pointer.
CASES: tuple[tuple[str, int, int], ...] = (
    ("-1, the all-ones value", -1, 32),
    ("0x40000000, the signed boundary", 0x40000000, 32),
    ("0xffffffffffffffff, a 64-bit mask", (1 << 64) - 1, 64),
)


def _section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def _walk(label: str, value: int, width: int) -> None:
    """Print the lines `kl-int <value> <width>` prints."""
    ty_u = IntType[f"U{width}"]
    ty_i = IntType[f"I{width}"]
    unsigned = value & ty_u.mask
    # The signed reading is not `unsigned - 2**width` unconditionally:
    # only a set sign bit makes it negative.  Doing this by hand is where
    # the sign is usually lost.
    signed = (
        unsigned - (1 << width) if unsigned & (1 << (width - 1)) else unsigned
    )

    print(f"  {label}")
    print(f"    value        : {value}  hex={unsigned:#0{width // 4 + 2}x}")
    print(f"    view         : unsigned={unsigned}  signed={signed}")
    print(
        f"    in range     : U{width}="
        f"{'yes' if IntCodec.is_in_range(value, ty_u) else 'no'}  "
        f"I{width}={'yes' if IntCodec.is_in_range(value, ty_i) else 'no'}"
    )
    print(
        f"    bounds       : U{width}[{ty_u.min_value}..{ty_u.max_value}]"
    )
    print(
        f"                   I{width}[{ty_i.min_value}..{ty_i.max_value}]"
    )

    # The bytes are what a memory read actually returns; the width only
    # decides how many of them are meaningful.
    le = IntCodec.pack_array([unsigned], ty_u, ByteOrder.LE)
    be = IntCodec.pack_array([unsigned], ty_u, ByteOrder.BE)
    print(f"    LE bytes     : {le.hex()}")
    print(f"    BE bytes     : {be.hex()}")
    if le == be:
        print("                   (palindromic: byte order cannot be "
              "recovered from these bytes)")


def inttour() -> None:
    """Walk the three values and show where a width changes the answer.

    Inside GDB the command form is executed too, so the example proves
    that ``kl-int`` and the arithmetic printed here agree.
    """
    print("Integers: one value, as every width the kernel might store it in")

    for label, value, width in CASES:
        _section(label.split(",")[0])
        _walk(label, value, width)

    _section("Why the width is not cosmetic")
    # A single demonstration that the same bytes decode to two different
    # numbers, which is the whole reason the command exists.
    raw = IntCodec.pack_u32(0xFFFFFFFF)
    print(f"  stored bytes   : {raw.hex()}")
    print(f"  as U32         : {IntCodec.unpack_u32(raw)}")
    print(f"  the same bits, read as I32: {IntCodec.unpack_i32(raw)}")
    print("  A length check written against the first number accepts")
    print("  4294967295; the second is -1.  Neither read is wrong.")

    _section("The same question through the command")
    # Inside GDB the real command runs, so the example demonstrates
    # ``kl-int`` rather than only reimplementing it.  On the host there
    # is nothing to execute and the branch is skipped.
    try:
        import gdb
    except ImportError:
        gdb = None
    if gdb is not None:
        gdb.execute("kl-int -1 32")
    else:
        print("  kl-int -1 32")
        print("    prints exactly the view and bounds lines above; the")
        print("    arithmetic is IntCodec, which reads no memory.")


def _command() -> None:
    """Register `inttour` when running inside GDB."""
    try:
        import gdb  # noqa: F401
    except ImportError:  # pragma: no cover - host path
        return

    class IntTourCommand(gdb.Command):
        """inttour -- one value as every width, the way kl-int does."""

        def __init__(self) -> None:
            super().__init__("inttour", gdb.COMMAND_USER)

        def invoke(self, arg: str, from_tty: bool) -> None:
            inttour()

    _INTTOUR = IntTourCommand()
    gdb.write("int_tour: run 'inttour' to walk the three values\n")


_command()


if __name__ == "__main__":
    inttour()