#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Small boundary validators shared by the pure-Python modules."""

from __future__ import annotations

# Validation helpers
# ---------------------------------------------------------------------


def check_bits(bits: int) -> None:
    """Raise ``ValueError`` when *bits* is outside ``1..64``."""
    if not 1 <= bits <= 64:
        raise ValueError(f"bits must be in 1..64, got {bits}")


def check_pow2(alignment: int) -> None:
    """Raise ``ValueError`` when *alignment* is not a positive power of 2."""
    if alignment <= 0 or (alignment & (alignment - 1)) != 0:
        raise ValueError(
            f"alignment must be a positive power of 2, got {alignment}"
        )


def check_nonneg(value: int, name: str) -> None:
    """Raise ``ValueError`` when *value* is negative."""
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}")


__all__ = [
    "check_bits",
    "check_pow2",
    "check_nonneg",
]
