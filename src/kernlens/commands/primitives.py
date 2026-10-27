#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# See the LICENSE file in the top-level directory for details.
"""The stateless bit/integer commands: ``kl-bits`` and ``kl-int``."""

from __future__ import annotations

import argparse

from .. import BitOps, ByteOrder, IntCodec, IntFmt, IntType
from ..output import message
from ..output.tree import IndentContextManager
from .formatting import fmt_onoff, parse_int
from .framework import Command, CommandCategory

_MASK64 = 0xFFFFFFFFFFFFFFFF


_bits_parser = argparse.ArgumentParser(
    description="Inspects a 64-bit value; optionally test/set/clear a bit."
)
_bits_parser.add_argument(
    "value", type=parse_int, help="value to inspect (0x hex, decimal, bare hex)",
)
_bits_parser.add_argument(
    "bit", nargs="?", type=int, default=None,
    help="bit index 0-63 to test/set/clear/toggle",
)


@Command(
    _bits_parser,
    category=CommandCategory.PRIMITIVES,
    aliases=["kl-bits"],
    examples="kl-bits 0xff\nkl-bits 0xff 3",
)
def kernlens_bits(value: int, bit: int | None = None) -> None:
    value &= _MASK64
    if bit is not None and not 0 <= bit < 64:
        print(message.error("bit must be between 0 and 63"))
        return
    indent = IndentContextManager()
    indent.print(
        indent.prefix("value") + ": " + indent.addr_hex(value)
        + "  " + message.hint(IntFmt.bits(value, 64))
    )
    indent.print(
        indent.prefix("scan")
        + f": popcount={BitOps.popcount(value)} "
        + f"leading_zeros={BitOps.leading_zeros(value)} "
        + f"trailing_zeros={BitOps.trailing_zeros(value)} "
        + f"first_set={BitOps.first_set(value)} "
        + f"last_set={BitOps.last_set(value)}"
    )
    indent.print(
        indent.prefix("power")
        + ": is_power_of_2=" + fmt_onoff(BitOps.is_power_of_2(value))
        + "  log2_floor="
        + (str(BitOps.log2_floor(value)) if value > 0 else message.warn("?"))
        + "  log2_ceil="
        + (str(BitOps.log2_ceil(value)) if value > 0 else message.warn("?"))
    )
    if bit is not None:
        indent.print(
            indent.prefix(f"bit {bit}")
            + ": test=" + fmt_onoff(BitOps.bit_test(value, bit))
            + "  set=" + indent.aux_hex(BitOps.bit_set(value, bit))
            + "  clear=" + indent.aux_hex(BitOps.bit_clear(value, bit))
            + "  toggle=" + indent.aux_hex(BitOps.bit_toggle(value, bit))
        )


_int_parser = argparse.ArgumentParser(
    description="Shows signed/unsigned and LE/BE integer views."
)
_int_parser.add_argument("value", type=parse_int, help="integer to inspect")
_int_parser.add_argument(
    "width", nargs="?", type=int, default=64,
    help="width in bits: 8, 16, 32, or 64 (default 64)",
)


@Command(
    _int_parser,
    category=CommandCategory.PRIMITIVES,
    aliases=["kl-int"],
    examples="kl-int 0x1234 16\nkl-int -1 32",
)
def kernlens_int(value: int, width: int = 64) -> None:
    if width not in (8, 16, 32, 64):
        print(message.error("width must be one of 8, 16, 32, 64"))
        return
    ty_u = IntType[f"U{width}"]
    ty_i = IntType[f"I{width}"]
    unsigned = value & ty_u.mask
    signed = (
        unsigned - (1 << width) if unsigned & (1 << (width - 1)) else unsigned
    )
    packed_le = IntCodec.pack_array([unsigned], ty_u, ByteOrder.LE)
    packed_be = IntCodec.pack_array([unsigned], ty_u, ByteOrder.BE)
    indent = IndentContextManager()
    indent.print(
        indent.prefix("value")
        + f": {value}  hex={unsigned:#0{width // 4 + 2}x}"
        + "  " + message.hint(IntFmt.bits(unsigned, width))
    )
    indent.print(
        indent.prefix("view")
        + f": unsigned={unsigned}  signed={signed}"
        + "  in_u=" + fmt_onoff(IntCodec.is_in_range(value, ty_u))
        + "  in_i=" + fmt_onoff(IntCodec.is_in_range(value, ty_i))
    )
    indent.print(
        indent.prefix("range")
        + f": U{width}[{ty_u.min_value}..{ty_u.max_value}]"
        + f"  I{width}[{ty_i.min_value}..{ty_i.max_value}]"
    )
    indent.print(
        indent.prefix("LE bytes") + ": " + message.hint(IntFmt.bytes_hex(packed_le))
    )
    indent.print(
        indent.prefix("BE bytes") + ": " + message.hint(IntFmt.bytes_hex(packed_be))
    )


__all__ = ["kernlens_bits", "kernlens_int"]