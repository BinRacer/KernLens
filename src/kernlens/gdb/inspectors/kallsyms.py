#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""Decode the in-kernel ``kallsyms`` symbol table.

Unlike ``info symbol`` this enumerates *every* symbol the running kernel
carries by reading the ``kallsyms_*`` tables GDB knows from the loaded
``vmlinux`` and expanding the compressed name stream in place.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ._base import MASK64, _ByteReader, InspectorBase

#: Chunk size for the on-demand kallsyms byte reader.
KALLSYMS_CHUNK = 1 << 14

#: Upper bound on decoded kallsyms entries (guards against bad reads).
KALLSYMS_LIMIT = 1 << 21

#: Size read when slurping the 256-entry ``kallsyms_token_table``.
TOKEN_TABLE_READ = 0x1000


@dataclass(frozen=True, slots=True)
class Kallsym:
    """One decoded ``kallsyms`` symbol."""

    name: str
    type: str
    address: int


class KallsymsInspector(InspectorBase):
    """The decoded ``kallsyms`` symbol table and lookups over it."""

    __slots__: tuple[str, ...] = ()

    #: Cached decoded table (``None`` means not yet built).
    _kallsyms: "tuple[Kallsym, ...] | None"

    def kallsyms(self) -> tuple[Kallsym, ...]:
        """Return every ``kallsyms`` symbol, or ``()`` when unavailable.

        The ``kallsyms_*`` tables are resolved through the loaded
        ``vmlinux`` symbols and decoded in place: a 256-entry token
        table expands the length-prefixed name stream, and either the
        base-relative ``kallsyms_offsets`` (+ ``kallsyms_relative_base``)
        or the absolute ``kallsyms_addresses`` array supplies addresses.
        """
        if self._kallsyms is not None:
            return self._kallsyms
        self._kallsyms = ()

        num_addr = self._reader.kvar_addr("kallsyms_num_syms")
        names_addr = self._reader.kvar_addr("kallsyms_names")
        if not num_addr or not names_addr:
            return self._kallsyms

        blob = _ByteReader(self._read_bytes, KALLSYMS_CHUNK)
        raw = blob.read(num_addr, 4)
        if raw is None:
            return self._kallsyms
        count = int.from_bytes(raw, "little")
        if not 0 < count <= KALLSYMS_LIMIT:
            return self._kallsyms

        tokens = self._kallsyms_tokens(blob)
        if tokens is None:
            return self._kallsyms
        names = self._kallsyms_names(blob, names_addr, count, tokens)
        addresses = self._kallsyms_addresses(count)

        result: list[Kallsym] = []
        for name, address in zip(names, addresses):
            if not name:
                continue
            result.append(
                Kallsym(name=name[1:], type=name[0], address=address)
            )
        self._kallsyms = tuple(result)
        return self._kallsyms

    def _kallsyms_tokens(self, blob: _ByteReader) -> list[str] | None:
        """Return the 256 expansion tokens (identity when uncompressed)."""
        table = self._reader.kvar_addr("kallsyms_token_table")
        if not table:
            # Uncompressed kallsyms: byte value is the character itself.
            return [chr(i) for i in range(256)]
        index = self._reader.kvar_addr("kallsyms_token_index")
        if index:
            raw = blob.read(index, 512)
            if raw is None:
                return None
            tokens: list[str] = []
            for i in range(256):
                offset = int.from_bytes(raw[i * 2 : i * 2 + 2], "little")
                tokens.append(self._cstring(table + offset) or "")
            return tokens
        raw = blob.read(table, TOKEN_TABLE_READ)
        if raw is None:
            # Fall back to per-token ``x/s`` reads.
            tokens = []
            position = 0
            for _ in range(256):
                token = self._cstring(table + position) or ""
                tokens.append(token)
                position += len(token) + 1
            return tokens
        fields = raw.split(b"\x00")[:256]
        return [field.decode("latin-1") for field in fields]

    def _kallsyms_names(
        self, blob: _ByteReader, base: int, count: int, tokens: list[str],
    ) -> list[str]:
        """Decode ``count`` length-prefixed names from the token stream."""
        names: list[str] = []
        cursor = base
        for _ in range(count):
            length = blob.u8(cursor)
            if length is None:
                break
            cursor += 1
            raw = blob.read(cursor, length)
            if raw is None:
                break
            cursor += length
            try:
                names.append("".join(tokens[byte] for byte in raw))
            except (IndexError, TypeError):
                names.append("")
        return names

    def _kallsyms_addresses(self, count: int) -> list[int]:
        """Return symbol addresses (base-relative offsets or absolutes)."""
        offsets = self._reader.kvar_addr("kallsyms_offsets")
        if offsets:
            raw = self._read_bytes(offsets, count * 4)
            if raw is None:
                return []
            values = [v[0] for v in struct.iter_unpack("<i", raw)]
            base_addr = self._reader.kvar_addr("kallsyms_relative_base")
            base = self._read_u64(base_addr) if base_addr else None
            if base is None:
                return []
            negative = sum(1 for value in values if value < 0)
            abs_percpu = (not values) or (negative / len(values) >= 0.5)
            addresses: list[int] = []
            for value in values:
                if abs_percpu and value < 0:
                    addresses.append((base - 1 - value) & MASK64)
                else:
                    addresses.append((base + value) & MASK64)
            return addresses
        absolutes = self._reader.kvar_addr("kallsyms_addresses")
        if absolutes:
            raw = self._read_bytes(absolutes, count * 8)
            if raw is None:
                return []
            return [v[0] for v in struct.iter_unpack("<Q", raw)]
        return []

    def lookup(self, query: str) -> tuple[Kallsym, ...]:
        """Return symbols matching *query* (an address or a substring)."""
        symbols = self.kallsyms()
        if not symbols:
            return ()
        try:
            address = int(query, 0)
        except (TypeError, ValueError):
            return tuple(symbol for symbol in symbols if query in symbol.name)
        return tuple(symbol for symbol in symbols if symbol.address == address)


__all__ = [
    "KALLSYMS_CHUNK",
    "KALLSYMS_LIMIT",
    "TOKEN_TABLE_READ",
    "Kallsym",
    "KallsymsInspector",
]