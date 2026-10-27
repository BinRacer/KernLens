#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# ruff: noqa: F821
"""Round-trip every integer width, in both byte orders.

`IntCodec` is the smallest part of KernLens and the easiest to get subtly
wrong.  A kernel struct read from memory arrives as `bytes`, and turning
those bytes into an `int` is where a tracer silently reports the wrong
value: pick the wrong width and the top bytes vanish; pick the wrong byte
order and the value is byte-reversed, which for a pointer looks like a
plausible address in the wrong region rather than as an obvious error.

So this example does the one thing that catches both mistakes -- it
**round-trips every width**, and it does it twice, once little-endian and
once big-endian, printing both the encoded bytes and the decoded value:

* `pack_u8` / `unpack_u8` ... `pack_u64` / `unpack_u64`
* the signed forms, where the round trip only closes if sign extension
  is right: `pack_i8(-1)` is `\xff`, and reading it back as unsigned gives
  255, not -1.
* `pack_array` / `unpack_array`, which is what a struct field of `u32[4]`
  actually needs.
* `is_in_range`, the pre-check that lets a caller reading untrusted
  memory reject a value with its own message instead of catching the
  `struct.error` that `pack` raises.

It runs with no debugger at all -- `IntCodec` never reads memory -- so it
works from a plain interpreter, from a test, and from inside GDB without
changing a line::

    $ python examples/api/intcodec_tour.py
    (gdb) source /path/to/KernLens/examples/api/intcodec_tour.py
    (gdb) icodec

The last section reads a real `struct page` from memory when a target is
available, and falls back to a synthetic buffer when it is not, so the
example shows the API being used on actual kernel data without requiring
one to run.
"""

from __future__ import annotations

import sys

try:
    IntCodec  # noqa: B018 - probe for the names gdbinit installs
except NameError:  # pragma: no cover - the GDB path never runs this
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[2] / "src"))
    from kernlens.core.codec import ByteOrder, IntCodec, IntType

# `ByteOrder` and `IntType` are needed in both environments; `gdbinit.py`
# installs classes and helpers rather than the codec enums, so they always
# come from the package.
from kernlens.core.codec import ByteOrder, IntType  # noqa: E402, F811


#: One value per width, chosen so the top byte is non-zero.  A value like
#: `1` would round-trip correctly even with the wrong width, which is
#: exactly the mistake this example exists to catch.
SAMPLES: tuple[tuple[str, int], ...] = (
    ("u8", 0xAB),
    ("u16", 0xABCD),
    ("u32", 0xABCDEF01),
    ("u64", 0xABCDEF0123456789),
)

#: Signed samples: the negative ones are where sign extension shows up.
SIGNED_SAMPLES: tuple[tuple[str, int], ...] = (
    ("i8", -0x55),
    ("i16", -0x5433),
    ("i32", -0x5432_10FF),
    ("i64", -0x5432_10FF_EDCB_A987),
)


def _section(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 58 - len(title)))


def _module() -> object:
    """The `IntCodec` namespace and the enums it needs.

    Inside GDB the names are already installed, so only the enums have to
    be imported; outside it the whole lot comes from the package.
    """
    return IntCodec


def unsigned_round_trip() -> None:
    """Steps 1: every unsigned width, little-endian and big-endian.

    The bytes are printed, not just the decoded value, because the bytes
    are what a tracer actually sees in memory.  Comparing `3f 00 00 00`
    against `00 00 00 3f` is how a byte-order mistake becomes visible
    instead of producing a number that merely looks wrong.

    Each width is written out rather than looped over a `getattr`: a
    reader can copy any line below into their own script, and a static
    read of this file can see which functions are used.  A loop would be
    two lines shorter and prove considerably less.
    """
    _section("1. unsigned round trip")

    for value, pack, unpack_le, unpack_be in (
        (0xAB, IntCodec.pack_u8, IntCodec.unpack_u8, IntCodec.unpack_u8),
        (0xABCD, IntCodec.pack_u16, IntCodec.unpack_u16, IntCodec.unpack_u16),
        (
            0xABCDEF01,
            IntCodec.pack_u32,
            IntCodec.unpack_u32,
            IntCodec.unpack_u32,
        ),
        (
            0xABCDEF0123456789,
            IntCodec.pack_u64,
            IntCodec.unpack_u64,
            IntCodec.unpack_u64,
        ),
    ):
        le = pack(value, ByteOrder.LE)
        be = pack(value, ByteOrder.BE)
        width = len(le)
        print(
            f"u{width * 8:<2d} value={value:#018x}  "
            f"LE={le.hex(' '):<24s} BE={be.hex(' '):<24s}"
            f"  back: LE={unpack_le(le):#x} BE={unpack_be(be, 0, ByteOrder.BE):#x}"
        )


def signed_round_trip() -> None:
    """Steps 2: the signed forms, where a width mistake changes the sign.

    `pack_i8(-0x55)` is a single byte `0xab`.  Reading it back as *unsigned*
    gives 171, not -85 -- and 171 is a perfectly plausible byte, which is
    why the mistake survives review.  Round-tripping through the matching
    signed decoder is the only check that catches it.
    """
    _section("2. signed round trip")

    for label, value, pack, unpack_u, unpack_i in (
        ("i8", -0x55, IntCodec.pack_i8, IntCodec.unpack_u8, IntCodec.unpack_i8),
        (
            "i16",
            -0x5433,
            IntCodec.pack_i16,
            IntCodec.unpack_u16,
            IntCodec.unpack_i16,
        ),
        (
            "i32",
            -0x5432_10FF,
            IntCodec.pack_i32,
            IntCodec.unpack_u32,
            IntCodec.unpack_i32,
        ),
        (
            "i64",
            -0x5432_10FF_EDCB_A987,
            IntCodec.pack_i64,
            IntCodec.unpack_u64,
            IntCodec.unpack_i64,
        ),
    ):
        packed = pack(value)
        print(
            f"{label:4s} value={value:>21d}  bytes={packed.hex(' '):<24s}"
            f"  as unsigned={unpack_u(packed):>21d}"
            f"  as signed={unpack_i(packed):>21d}"
        )


def range_checks() -> None:
    """Steps 3: what `is_in_range` tells you before `pack` refuses.

    `pack` raises `struct.error` for an out-of-range value rather than
    truncating it -- which is the safer choice, since a truncated value
    is a wrong value that looks right.  That makes `is_in_range` a
    *pre-check* rather than a replacement: it lets a caller that reads
    values from untrusted memory reject them with a message of its own,
    instead of catching `struct.error` from somewhere deep in `codec`.
    """
    _section("3. range checks")
    # `IntType` is an enumeration, one member per width and signedness --
    # not a factory.  `IntType.U8` is the value, which is why the loop
    # looks the member up rather than constructing one.
    for member, value in (
        (IntType.U8, 255),
        (IntType.U8, 256),
        (IntType.I8, -128),
        (IntType.I8, -129),
    ):
        ok = IntCodec.is_in_range(value, member)
        try:
            packed = IntCodec.pack(value, member).hex(" ")
            outcome = f"packed={packed}"
        except Exception as exc:  # struct.error, deliberately demonstrated
            outcome = f"pack raises {type(exc).__name__}"
        print(
            f"{member.name:3s} value={value:>6d}  in_range={str(ok):<5s} {outcome}"
        )
    print(
        "  note: pack() raises rather than truncating, so a wrong value can\n"
        "  never be produced silently.  is_in_range is how to reject one\n"
        "  with your own message before that exception is raised."
    )


def arrays() -> None:
    """Steps 4: the array forms, which is what a real struct field needs.

    A `u32[4]` in memory is 16 bytes, not four separate reads.  Doing it
    in one call is both faster and correct-by-construction: the count is
    explicit, so a struct that grew a field is caught here rather than by
    reading into the next field.
    """
    _section("4. arrays")
    values = [0x11223344, 0x55667788, 0x99AABBCC, 0xDDEEFF00]
    packed = IntCodec.pack_array(values, IntType.U32, ByteOrder.LE)
    back = IntCodec.unpack_array(packed, IntType.U32, len(values))
    print(f"values : {[hex(v) for v in values]}")
    print(f"packed : {packed.hex(' ')}")
    print(f"back   : {[hex(v) for v in back]}")
    print(f"closed : {back == values}")

    # Reading only the first two elements is how a bounded read works,
    # and `unpack_array` with a smaller count must not touch the rest.
    partial = IntCodec.unpack_array(packed, IntType.U32, 2)
    print(f"first 2: {[hex(v) for v in partial]}")


def offset_reads() -> None:
    """Steps 5: reading one field out of a larger buffer.

    This is the shape every struct read takes: one `bytes` object for the
    whole struct, then an `offset` per field.  Doing it this way means the
    buffer is read once, which matters in a breakpoint callback where the
    debuggee is stopped and every read is expensive.

    The last two lines use the width-parameterised `unpack`, which is what
    a caller reaches for when the width comes from a layout table rather
    than from the source.
    """
    _section("5. offsets into one buffer")
    buffer = bytes.fromhex("00112233445566778899aabbccddeeff")
    print(f"buffer: {buffer.hex(' ')}")
    for offset in (0, 4, 8, 12):
        le = IntCodec.unpack_u32(buffer, offset)
        be = IntCodec.unpack_u32(buffer, offset, ByteOrder.BE)
        print(f"  offset {offset:2d}: LE={le:#010x}  BE={be:#010x}")

    # `unpack` takes the width as an argument, for the case where the
    # field width is data rather than source.
    print(f"\nunpack(buffer, U16, offset=2) : {IntCodec.unpack(buffer, IntType.U16, 2):#06x}")
    print(f"unpack(buffer, U64, offset=8) : {IntCodec.unpack(buffer, IntType.U64, 8):#018x}")


def live_struct_page() -> None:
    """Step 6: the same API on a real `struct page`, when one is available.

    `struct page` is the right subject because its fields are deliberately
    packed into shared words -- `flags` and the compound head occupy the
    same `unsigned long` -- so reading the wrong width there is not a
    cosmetic error, it is a wrong page.

    The distinction this step makes explicit: with a target attached it
    reads a real page's bytes through `kdbg.reader`; without one it says
    so and shows the same decode on a buffer of the same shape.  An
    example that silently substitutes synthetic data for kernel data is
    worse than one that refuses.
    """
    _section("6. a real struct page, or a stand-in")
    buffer, source = _page_bytes()
    print(f"source: {source}")
    print(f"bytes : {buffer.hex(' ')}")
    print(f"word 0: {IntCodec.unpack_u64(buffer, 0):#018x}")
    print(f"word 1: {IntCodec.unpack_u64(buffer, 8):#018x}")


def _page_bytes() -> tuple[bytes, str]:
    """Raw bytes of one `struct page`, and where they came from.

    Inside GDB the address is a real page: the vmemmap base plus one
    page-frame.  Outside it there is no memory to read, so the stand-in
    carries the same *shape* -- 64 bytes, the compound-head word first --
    and the source string says plainly that it is synthetic.
    """
    try:
        vmemmap = read_kvar("vmemmap_base")  # noqa: F821
        # `read_bytes` is the only reader method that returns a raw
        # buffer; every other one decodes a specific width, which would
        # defeat the point of demonstrating the decoding.
        raw = kdbg.reader.read_bytes(int(vmemmap), 64)  # noqa: F821
        if raw:
            return raw, f"live struct page at {int(vmemmap):#x}"
    except (NameError, AttributeError, TypeError):
        pass
    return (
        IntCodec.pack_u64(0x0000000000004000) + bytes(56),
        "synthetic stand-in (no target attached, or no vmemmap_base)",
    )


def icodec() -> None:
    """Run the whole tour."""
    print("IntCodec tour -- no debugger required")
    unsigned_round_trip()
    signed_round_trip()
    range_checks()
    arrays()
    offset_reads()
    live_struct_page()
    print(
        "\nWhy the round trip is the check: a width mistake drops the top\n"
        "bytes and a byte-order mistake reverses them.  Both produce a\n"
        "number that is plausible at a glance and wrong in fact, which is\n"
        "why printing the bytes -- not just the decoded value -- is the\n"
        "only version of this example that catches them.\n"
    )


def _command() -> None:
    """Register `icodec` when running inside GDB; a no-op elsewhere.

    The `gdb` module being importable is not enough: the test suite
    installs a stub `gdb` that has no `Command` or `COMMAND_USER`, and a
    tour that cannot be imported under those conditions cannot be tested.
    Checking for the attribute is cheap and makes the failure mode
    "silently no command" rather than an `AttributeError` at import time.
    """
    try:
        import gdb
    except ImportError:
        return

    if not hasattr(gdb, "Command") or not hasattr(gdb, "COMMAND_USER"):
        return

    class ICodecCommand(gdb.Command):
        """icodec -- round-trip every integer width, in both byte orders."""

        def __init__(self) -> None:
            super().__init__("icodec", gdb.COMMAND_USER)

        def invoke(self, arg: str, from_tty: bool) -> None:
            icodec()

    _ICODEC = ICodecCommand()
    gdb.write("intcodec_tour: run 'icodec' to round-trip every width\n")


_command()


if __name__ == "__main__":
    icodec()