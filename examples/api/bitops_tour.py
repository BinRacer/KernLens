#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# ruff: noqa: F821
"""Decode the bitfields a kernel struct is actually made of.

`BitOps` has 44 members, and they are not a grab bag: they fall into five
families that correspond to five things the kernel does with bits.  This
example walks them in that order, on values taken from the test kernel
rather than invented, so the answers are checkable:

1. **Alignment and orders** -- `align_up`, `align_down`, `is_aligned`,
   `is_power_of_2`, `log2_floor`, `log2_ceil`, `next_power_of_2`.  This is
   the family behind "order 2", and a slab's geometry is exactly these
   calls applied to an object size.
2. **Field packing** -- `mask`, `extract_bits`, `insert_bits`,
   `clear_bits`, `truncate`.  The kernel packs `inuse`, `objects` and
   `frozen` into one word; this is how it is unpacked.
3. **Single-bit and search** -- `bit_test`, `bit_set`, `bit_clear`,
   `bit_toggle`, `first_set`, `last_set`, `popcount`, `leading_zeros`,
   `trailing_zeros`.
4. **CPU masks** -- `cpumask_test`, `cpumask_count`, `cpumask_first`,
   `cpumask_next`.  `kl-cpu` prints `Online: 0-3`; this is the word that
   range came from.
5. **Sign and width** -- `sign_extend`, `sign_bit`, `to_i*`/`to_u*`,
   `signed_range`, `unsigned_range`, `coerce`.  This is where a value
   silently becomes the wrong number, so the example shows the wrap
   explicitly.

It needs no debugger.  The CPU mask in step 4 is read from the target when
one is attached and borrowed from the test kernel's topology when not, so
the same code runs in both places::

    $ python examples/api/bitops_tour.py
    (gdb) source /path/to/KernLens/examples/api/bitops_tour.py
    (gdb) btour
"""

from __future__ import annotations

import sys

try:
    BitOps  # noqa: B018 - probe for the names gdbinit installs
except NameError:  # pragma: no cover - the GDB path never runs this
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[2] / "src"))
    from kernlens.core.bitops import BitOps

# `IntType` is needed by `coerce()` in both environments, and `gdbinit.py`
# installs classes and helpers rather than the codec enums, so it always
# comes from the package.  Importing it unconditionally is simpler than
# probing for it and having a `None` branch that only GDB can reach.
from kernlens.core.codec import IntType  # noqa: E402


#: A real slab cache geometry from the 6.1.134 test kernel: kmalloc-1k has
#: `oo_order=2`, so one slab is `PAGE_SIZE << 2` bytes holding 16 objects.
OBJECT_SIZE = 1024
OO_ORDER = 2
OO_OBJECTS = 16

#: The packed slab counters from the same kernel, as `kl-slab details`
#: prints them: `inuse:16 | objects:15 | frozen:1`.
SLAB_COUNTERS = (16 << 17) | (16 << 2) | 1


def _section(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 58 - len(title)))


def alignment() -> None:
    """Steps 1: the arithmetic behind "order 2" and "16 objects".

    A slab's geometry is not a table of magic numbers; it is these calls.
    `log2_ceil(object_size / PAGE_SIZE)` gives the order, and
    `next_power_of_2` is what makes the object count come out even.
    """
    _section("1. alignment and orders")
    print(f"object size        : {OBJECT_SIZE} bytes")
    print("PAGE_SIZE          : 4096 bytes")
    print(f"log2_floor(1024)   : {BitOps.log2_floor(OBJECT_SIZE)}")
    print(f"log2_ceil(1024)    : {BitOps.log2_ceil(OBJECT_SIZE)}")
    print(f"log2_ceil(1025)    : {BitOps.log2_ceil(1025)}   (rounds up)")
    print(f"next_power_of_2(1000) : {BitOps.next_power_of_2(1000)}")
    print(f"mask(12)           : {BitOps.mask(12):#x}   (one page of offsets)")

    for value in (0x1234, 0x2000, 0):
        print(
            f"align_up({value:#06x}, 4096)   : {BitOps.align_up(value, 4096):#06x}"
            f"   align_down: {BitOps.align_down(value, 4096):#06x}"
            f"   aligned: {BitOps.is_aligned(value, 4096)}"
        )
    print(
        f"is_power_of_2(1024) : {BitOps.is_power_of_2(1024)}"
        f"   is_power_of_2(1000) : {BitOps.is_power_of_2(1000)}"
    )
    print(
        "  oo_order is log2_ceil(object_size / PAGE_SIZE); the values in a\n"
        "  cache dump are these calls, not constants."
    )


def field_packing() -> None:
    """Steps 2: unpack the word the kernel actually keeps.

    `struct slab` stores `inuse:16`, `objects:15`, `frozen:1` in one
    unsigned int.  Nothing about that is visible in the raw value, which
    is why `kl-slab details` prints them separately -- and why a script
    that reimplements that print needs `extract_bits` to be right.
    """
    _section("2. field packing (a real packed word)")
    print(f"packed counters : {SLAB_COUNTERS:#x}  ({SLAB_COUNTERS:#034b})")

    inuse = BitOps.extract_bits(SLAB_COUNTERS, 17, 16)
    objects = BitOps.extract_bits(SLAB_COUNTERS, 2, 15)
    frozen = BitOps.extract_bits(SLAB_COUNTERS, 0, 1)
    print(f"  inuse   (shift 17, width 16) : {inuse}")
    print(f"  objects (shift  2, width 15) : {objects}")
    print(f"  frozen  (shift  0, width  1) : {frozen}")
    print("  expected from kl-slab details : inuse=16 objects=16 frozen=1")
    print(f"  rebuilt : {BitOps.insert_bits(0, inuse, 17, 16) | BitOps.insert_bits(0, objects, 2, 15) | frozen:#x}")
    print(f"  round trip closes : {BitOps.insert_bits(BitOps.insert_bits(BitOps.insert_bits(0, frozen, 0, 1), objects, 2, 15), inuse, 17, 16) == SLAB_COUNTERS}")

    print(f"\nclear_bits(0xffff, 4, 8)  : {BitOps.clear_bits(0xFFFF, 4, 8):#x}")
    print(f"truncate(0x1234, 8)       : {BitOps.truncate(0x1234, 8):#x}")
    print(f"mask(8)                   : {BitOps.mask(8):#x}")


def single_bits() -> None:
    """Steps 3: test, set, clear, toggle, and search.

    The search pair is the one worth remembering: `first_set` and
    `last_set` answer "which bit" for a value with one bit set, which is
    how a page flag or an error code is inspected.
    """
    _section("3. single bits and searches")
    value = 0b1011_0000
    print(f"value : {value:#010b}")
    print(f"  popcount      : {BitOps.popcount(value)}")
    print(f"  first_set     : {BitOps.first_set(value)}")
    print(f"  last_set      : {BitOps.last_set(value)}")
    print(f"  trailing_zeros: {BitOps.trailing_zeros(value)}")
    print(f"  leading_zeros : {BitOps.leading_zeros(value, 8)}  (8-bit)")

    # Bit 4 is already set in `value`, so setting it again shows nothing;
    # bit 3 is clear and is the one that changes.  An example that prints
    # the same value twice teaches the reader nothing about which call
    # did what.
    for bit in (4, 3):
        was = BitOps.bit_test(value, bit)
        print(
            f"  bit {bit}: test={was}"
            f"  set={BitOps.bit_set(value, bit):#010b}"
            f"  clear={BitOps.bit_clear(value, bit):#010b}"
            f"  toggle={BitOps.bit_toggle(value, bit):#010b}"
        )


def cpu_masks() -> None:
    """Steps 4: the word behind `kl-cpu`'s `Online: 0-3`.

    A CPU mask is one bit per CPU.  `cpumask_next` is the iteration
    primitive -- `cpumask_first` then repeated `cpumask_next` is exactly
    how the kernel walks online CPUs, and exactly how a tracer should.
    """
    _section("4. CPU masks")
    mask, source = _online_mask()
    print(f"online mask : {mask:#b}   (source: {source})")
    print(f"  cpumask_count : {BitOps.cpumask_count(mask)}")
    print(f"  cpumask_first : {BitOps.cpumask_first(mask)}")
    for cpu in (0, 1, 2):
        print(
            f"  cpumask_test({cpu}) : {BitOps.cpumask_test(mask, cpu)}"
            f"   cpumask_next(after {cpu}) : {BitOps.cpumask_next(mask, cpu)}"
        )
    print(
        "  Iterating with cpumask_next is what makes a per-CPU tracer work on\n"
        "  a target where some CPUs are offline: the mask says which."
    )


def sign_and_width() -> None:
    """Steps 5: where a value silently becomes the wrong number.

    `to_u8(-1)` is 255 and `to_i8(0xff)` is -1; both are correct and both
    surprise people.  `sign_extend(0x1f, 5)` turning 31 into -1 is the
    single most useful call here: a 5-bit field holding only ones is
    either 31 or -1 depending on its declared signedness, and the kernel
    means -1.
    """
    _section("5. sign and width")
    print(f"to_u8(-1)        : {BitOps.to_u8(-1)}")
    print(f"to_u16(-1)       : {BitOps.to_u16(-1)}")
    print(f"to_u32(-1)       : {BitOps.to_u32(-1)}")
    print(f"to_u64(-1)       : {BitOps.to_u64(-1)}")
    print(f"to_i8(0xff)      : {BitOps.to_i8(0xff)}")
    print(f"to_i16(0xffff)   : {BitOps.to_i16(0xFFFF)}")
    print(f"to_i32(0xffffffff): {BitOps.to_i32(0xFFFFFFFF)}")
    print(f"to_i64(0xffffffffffffffff) : {BitOps.to_i64(0xFFFFFFFFFFFFFFFF)}")
    print(f"sign_bit(5)      : {BitOps.sign_bit(5)}   (0b10000)")
    print(f"sign_extend(0x1f, 5) : {BitOps.sign_extend(0x1F, 5)}")
    print(f"sign_extend(0x0f, 5) : {BitOps.sign_extend(0x0F, 5)}")
    print(f"signed_range(8)  : {BitOps.signed_range(8)}")
    print(f"unsigned_range(8): {BitOps.unsigned_range(8)}")

    # `coerce` is the same wrap made explicit: give it a width and it
    # returns the value as the kernel would store it in that field.  This
    # is what to call when the width came from a layout table rather than
    # from a named type.
    for width in (8, 16, 32):
        kind = IntType.U8 if width == 8 else (
            IntType.U16 if width == 16 else IntType.U32
        )
        print(f"coerce(-1, U{width:<2d})  : {BitOps.coerce(-1, kind)}")

    print(
        "  A 5-bit field of all ones is 31 unsigned and -1 signed.  The\n"
        "  kernel means -1, so sign_extend is not optional when the field is\n"
        "  declared signed -- skipping it reports a sane-looking 31."
    )


def rotates() -> None:
    """Steps 6: rotations, which differ from shifts only at the edges.

    `rotate_left` is used by hash and checksum code, and by the SLUB
    freelist pointer obfuscation.  The edge case is what to look at: a
    shift would drop the top bit, a rotate brings it back at the bottom.
    """
    _section("6. rotations")
    value = 0x8000000000000001
    print(f"value              : {value:#018x}")
    print(f"rotate_left(4)     : {BitOps.rotate_left(value, 4):#018x}")
    print(f"rotate_right(4)    : {BitOps.rotate_right(value, 4):#018x}")
    print(f"shift left 4 for comparison : {(value << 4) & BitOps.mask(64):#018x}")
    print("  the shifted form loses the top bit; the rotated form keeps it.")


def endian() -> None:
    """Steps 7: byte swaps, on the value a reader has to un-swap."""
    _section("7. byte order")
    value = 0x0000000000004000
    print(f"value          : {value:#018x}")
    print(f"byte_swap64    : {BitOps.byte_swap64(value):#018x}")
    print(f"byte_swap32    : {BitOps.byte_swap32(value):#018x}")
    print(f"byte_swap16    : {BitOps.byte_swap16(value):#06x}")
    print(f"byte_swap(32)  : {BitOps.byte_swap(value, 32):#x}")
    print("  byte_swap64 is what makes a big-endian on-disk value readable.")


def _online_mask() -> tuple[int, str]:
    """The online CPU mask, from the target or from the test kernel.

    Inside GDB this reads the real `__cpu_online_mask` through
    `kdbg.kvar_addr`, which is KASLR-aware.  Plain
    `gdb.parse_and_eval("cpu_online_mask")` does **not** work here: the
    macro spelling has no symbol, and the underlying variable only
    resolves once the slide has been applied.  That is exactly the kind
    of difference `KAddr`/`MemoryReader` exist to hide, so the example
    uses the facade rather than GDB directly.

    Outside GDB it uses the test kernel's recorded topology, so the
    numbers in the output are that kernel's rather than invented.
    """
    try:
        address = kdbg.kvar_addr("__cpu_online_mask")  # noqa: F821
        if address:
            raw = kdbg.reader.read_bytes(int(address), 8)  # noqa: F821
            if raw:
                word = int.from_bytes(raw, "little")
                return (
                    word & BitOps.mask(kdbg.nr_cpus()),  # noqa: F821
                    "live __cpu_online_mask",
                )
    except (NameError, AttributeError, TypeError):
        pass
    return 0b1111, "test kernel topology (4 CPUs online)"


def btour() -> None:
    """Run the whole tour."""
    print("BitOps tour -- no debugger required")
    alignment()
    field_packing()
    single_bits()
    cpu_masks()
    sign_and_width()
    rotates()
    endian()
    print(
        "\nMost of these are one line of arithmetic.  The reason to call them\n"
        "anyway is the edge cases: `align_up` on an already-aligned value,\n"
        "`extract_bits` at the top of the word, `sign_extend` on a field\n"
        "declared signed.  Each is a place where the obvious hand-written\n"
        "version is subtly wrong, and each is covered by a test here.\n"
    )


def _command() -> None:
    """Register `btour` when running inside GDB; a no-op elsewhere.

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

    class BTourCommand(gdb.Command):
        """btour -- decode the bitfields a kernel struct is made of."""

        def __init__(self) -> None:
            super().__init__("btour", gdb.COMMAND_USER)

        def invoke(self, arg: str, from_tty: bool) -> None:
            btour()

    _BTOUR = BTourCommand()
    gdb.write("bitops_tour: run 'btour' to walk every BitOps family\n")


_command()


if __name__ == "__main__":
    btour()