#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Typing compatibility helpers for the output package."""

try:  # Python 3.12+
    from typing import override
except ImportError:  # Python < 3.12
    from typing_extensions import override  # type: ignore[assignment]

__all__ = ["override"]
