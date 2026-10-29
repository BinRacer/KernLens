#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""A minimal, self-contained reader for the kernel's BTF type information.

BTF (BPF Type Format) is a compact type database the kernel can embed in
its own image (``CONFIG_DEBUG_INFO_BTF=y``).  It is not a debugging aid
by design, but it records every struct's size and each member's bit
offset, which is exactly what :mod:`kernlens.gdb.layouts` falls back to
when a build carries no DWARF.

This module parses the BTF blob itself (no ``bpftool``, no ``libbpf``),
so the inspectors can use it *inside* GDB: the ``.BTF`` section of the
loaded ``vmlinux`` is read through GDB's memory API, or a host file such
as ``/sys/kernel/btf/vmlinux`` is read directly.

The parse is deliberately defensive: any malformed blob yields ``None``
instead of an exception, because a type resolver must never take the
debugger down.  :class:`BTF` exposes only what the inspectors need --
``offset(type, path)`` and ``sizeof(type)``.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

try:  # The parser is pure Python; only the GDB source needs the module.
    import gdb
except ImportError:  # pragma: no cover - outside GDB (unit tests, tools)
    gdb = None  # type: ignore[assignment]

#: ``btf_header.magic`` (``0xEB9F``) as it appears in the byte stream.
_BTF_MAGIC = 0xEB9F

#: BTF kind numbers (``include/uapi/linux/btf.h``).
_KIND_INT = 1
_KIND_PTR = 2
_KIND_ARRAY = 3
_KIND_STRUCT = 4
_KIND_UNION = 5
_KIND_ENUM = 6
_KIND_FWD = 7
_KIND_TYPEDEF = 8
_KIND_VOLATILE = 9
_KIND_CONST = 10
_KIND_RESTRICT = 11
_KIND_FUNC = 12
_KIND_FUNC_PROTO = 13
_KIND_VAR = 14
_KIND_DATASEC = 15
_KIND_FLOAT = 16
_KIND_DECL_TAG = 17
_KIND_TYPE_TAG = 18
_KIND_ENUM64 = 19

#: Kind -> payload bytes that follow the fixed 12-byte ``btf_type``.
#: ``-1`` means the payload is ``vlen * n``; ``0`` means none.
_EXTRA_FIXED: dict[int, int] = {
    _KIND_PTR: 0, _KIND_FWD: 0, _KIND_TYPEDEF: 0, _KIND_VOLATILE: 0,
    _KIND_CONST: 0, _KIND_RESTRICT: 0, _KIND_FUNC: 0, _KIND_FLOAT: 0,
    _KIND_TYPE_TAG: 0, _KIND_INT: 4, _KIND_ARRAY: 12, _KIND_VAR: 4,
    _KIND_DECL_TAG: 4,
}
_EXTRA_PER_VLEN: dict[int, int] = {
    _KIND_STRUCT: 12, _KIND_UNION: 12, _KIND_ENUM: 8,
    _KIND_FUNC_PROTO: 8, _KIND_DATASEC: 12, _KIND_ENUM64: 12,
}

#: Modifier kinds that wrap another type id in their ``type`` field.
_MODIFIER_KINDS = frozenset({
    _KIND_TYPEDEF, _KIND_VOLATILE, _KIND_CONST, _KIND_RESTRICT,
    _KIND_TYPE_TAG,
})


class BTF:
    """A parsed BTF type database, queried by struct name and field path."""

    __slots__: tuple[str, ...] = (
        "_types", "_struct_ids", "_enums", "_member_index",
    )

    def __init__(
        self,
        types: dict[int, tuple[int, str, int, tuple[tuple[str, int, int], ...]]],
        enums: dict[str, tuple[tuple[str, int], ...]] | None = None,
    ) -> None:
        self._types = types
        self._enums = enums or {}
        self._member_index: dict[str, str] | None = None
        self._struct_ids: dict[str, int] = {}
        for type_id, (kind, name, _size, _members) in types.items():
            if kind in (_KIND_STRUCT, _KIND_UNION) and name:
                # Index under both the bare name and the ``struct`` tag so
                # either spelling of a registry key resolves.
                self._struct_ids.setdefault(name, type_id)
                self._struct_ids.setdefault(f"struct {name}", type_id)

    # --- naming ---------------------------------------------------------

    def _find(self, type_name: str) -> int | None:
        """Return the type id for *type_name* (tolerating a ``struct`` tag)."""
        if type_name in self._struct_ids:
            return self._struct_ids[type_name]
        bare = type_name.removeprefix("struct ").removeprefix("union ")
        return self._struct_ids.get(bare)

    def _strip(self, type_id: int) -> int:
        """Follow modifier types (typedef/const/volatile...) to the target."""
        seen: set[int] = set()
        while type_id in self._types and type_id not in seen:
            seen.add(type_id)
            kind, _name, _size, members = self._types[type_id]
            if kind in (_KIND_STRUCT, _KIND_UNION):
                break
            if kind in _MODIFIER_KINDS and members:
                type_id = members[0][1]
                continue
            break
        return type_id

    # --- queries --------------------------------------------------------

    def has(self, type_name: str) -> bool:
        """Whether the blob defines *type_name* as a struct or union."""
        return self._find(type_name) is not None

    def enum_members(self, enum_name: str) -> dict[str, int] | None:
        """Return ``{member: value}`` for *enum_name*, or ``None``.

        Enum values are what the kernel actually compiled against, so
        they must be read rather than assumed: ``PG_slab`` is bit 9 in
        6.1 but has moved by 7.0, and ``MIGRATE_TYPES`` (the count of
        free-area lists) depends on ``CONFIG_CMA`` / ``CONFIG_MEMORY_ISOLATION``.
        """
        members = self._enums.get(_bare_enum(enum_name))
        return dict(members) if members is not None else None

    def enum_with_member(self, member: str) -> str | None:
        """Return the name of the enum that defines *member*, or ``None``.

        The ABI probe has to be by *member*, not by enum name: the enum
        that carries ``PGTY_buddy`` is declared anonymously and BTF/
        DWARF name it after the fact (``pagetype`` on one kernel, nothing
        on another), so looking it up as ``page_type`` misses.  Asking
        "which enum defines ``PGTY_buddy``" is stable across kernels.
        """
        if self._member_index is None:
            index: dict[str, str] = {}
            for name, entries in self._enums.items():
                for entry, _value in entries:
                    index.setdefault(entry, name)
            self._member_index = index
        return self._member_index.get(member)

    def sizeof(self, type_name: str) -> int | None:
        """Return ``sizeof(type_name)`` in bytes, or ``None``."""
        type_id = self._find(type_name)
        if type_id is None:
            return None
        return self._types[type_id][2]

    def offset(self, type_name: str, path: str) -> int | None:
        """Return ``offsetof(type_name, path)`` in bytes, or ``None``.

        *path* may descend named members (``desc_ring.descs``) and may
        name a field that BTF inlined anonymously (``page.lru`` lives in
        an unnamed union, which is searched as well).  A path that is
        truly absent yields ``None`` rather than a guess.
        """
        type_id = self._find(type_name)
        if type_id is None:
            return None
        return self._path_offset(type_id, path, frozenset())

    def _path_offset(
        self, type_id: int, path: str, seen: frozenset[int],
    ) -> int | None:
        """Resolve *path* relative to *type_id* (guarding cycles)."""
        head, _, tail = path.partition(".")
        found = self._member_offset(type_id, head, seen)
        if found is None:
            return None
        offset, member_type = found
        if not tail:
            return offset
        nested = self._path_offset(member_type, tail, seen)
        return None if nested is None else offset + nested

    def _member_offset(
        self, type_id: int, member: str, seen: frozenset[int] = frozenset(),
    ) -> tuple[int, int] | None:
        """Return ``(byte_offset, member_type_id)`` for one member.

        Named members are matched first; when *member* is not one of
        them the search descends into every anonymous struct/union
        member, because BTF inlines those without a name (``struct
        page`` reaches ``lru`` through an unnamed union).  *seen* guards
        against a self-referential anonymous member.
        """
        type_id = self._strip(type_id)
        if type_id not in self._types or type_id in seen:
            return None
        _kind, _name, _size, members = self._types[type_id]
        for name, member_type, bit_offset in members:
            if name == member:
                return bit_offset // 8, member_type
        inner = seen | {type_id}
        for name, member_type, bit_offset in members:
            if name:
                continue
            nested = self._member_offset(member_type, member, inner)
            if nested is not None:
                return bit_offset // 8 + nested[0], nested[1]
        return None


def parse(data: bytes) -> BTF | None:
    """Parse a BTF blob; return ``None`` when it is malformed."""
    if len(data) < 24:
        return None
    try:
        magic, _version, _flags, hdr_len, type_off, type_len, str_off, str_len = (
            struct.unpack_from("<HBBIIIII", data, 0)
        )
    except struct.error:
        return None
    if magic != _BTF_MAGIC or hdr_len < 24:
        return None
    type_start = hdr_len + type_off
    str_start = hdr_len + str_off
    if type_start + type_len > len(data) or str_start + str_len > len(data):
        return None
    strings = data[str_start:str_start + str_len]
    try:
        types, enums = _parse_types(
            data, type_start, type_start + type_len, strings,
        )
    except (struct.error, IndexError, KeyError, ValueError):
        return None
    if not types:
        return None
    return BTF(types, enums)


#: Prefixes a caller may use when naming an enum.
_ENUM_PREFIX = "enum "


def _bare_enum(name: str) -> str:
    """Strip an ``enum `` prefix so both spellings resolve."""
    return name.removeprefix(_ENUM_PREFIX).strip()


def _parse_types(
    data: bytes, cursor: int, end: int, strings: bytes,
) -> "tuple[dict[int, tuple[int, str, int, tuple[tuple[str, int, int], ...]]], dict[str, tuple[tuple[str, int], ...]]]":
    """Walk the type section.

    Returns ``{id: (kind, name, size, members)}`` plus a separate
    ``{enum_name: ((member, value), ...)}`` map.  Enums are kept apart
    because their layout is a member list, not a struct one, and because
    their *values* are what callers need (the type-id sequence still
    records every enum so the ids stay in sync).
    """
    types: dict[int, tuple[int, str, int, tuple[tuple[str, int, int], ...]]] = {}
    enums: dict[str, tuple[tuple[str, int], ...]] = {}
    type_id = 1
    while cursor < end:
        name_off, info, size = struct.unpack_from("<III", data, cursor)
        cursor += 12
        vlen = info & 0xFFFF
        kind = (info >> 24) & 0x1F
        kind_flag = (info >> 31) & 1
        name = _decode(strings, name_off)
        members: list[tuple[str, int, int]] = []
        if kind in (_KIND_STRUCT, _KIND_UNION):
            for _ in range(vlen):
                m_name, m_type, m_off = struct.unpack_from("<III", data, cursor)
                cursor += 12
                bit_offset = (m_off & 0xFFFFFF) if kind_flag else m_off
                members.append((_decode(strings, m_name), m_type, bit_offset))
        elif kind in (_KIND_ENUM, _KIND_ENUM64):
            entries: list[tuple[str, int]] = []
            for _ in range(vlen):
                if kind == _KIND_ENUM:
                    e_name, e_value = struct.unpack_from("<Ii", data, cursor)
                    cursor += 8
                else:
                    e_name, e_lo, e_hi = struct.unpack_from("<III", data, cursor)
                    e_value = e_lo | (e_hi << 32)
                    cursor += 12
                entries.append((_decode(strings, e_name), e_value))
            if name:
                enums[name] = tuple(entries)
        else:
            cursor += _extra(kind, vlen)
        types[type_id] = (kind, name, size, tuple(members))
        type_id += 1
    return types, enums


def _extra(kind: int, vlen: int) -> int:
    if kind in _EXTRA_FIXED:
        return _EXTRA_FIXED[kind]
    return _EXTRA_PER_VLEN.get(kind, 0) * vlen


def _decode(strings: bytes, offset: int) -> str:
    if offset <= 0 or offset >= len(strings):
        return ""
    end = strings.find(b"\x00", offset)
    if end < 0:
        return ""
    return strings[offset:end].decode("utf-8", "replace")


# ---------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------

def load(path: str | None = None) -> BTF | None:
    """Return a :class:`BTF` for *path*, or the loaded image when omitted.

    *path* may be a raw BTF blob (``/sys/kernel/btf/vmlinux``,
    ``vmlinux.btf``) or an ELF containing a ``.BTF`` section (a full
    ``vmlinux``).  Never raises: an unreadable file, a target with no
    BTF, or a malformed blob all yield ``None``, so callers treat "no
    BTF" the same as "no DWARF".
    """
    if path:
        try:
            data = Path(path).read_bytes()
        except OSError:
            return None
        return parse(extract_btf(data))
    return find_in_gdb()


def extract_btf(data: bytes) -> bytes:
    """Return the BTF payload of *data* (raw blob, or ELF ``.BTF``).

    A raw blob is returned unchanged; an ELF is searched for its
    ``.BTF`` section.  An unknown format yields ``b""`` so :func:`parse`
    fails cleanly.
    """
    if data[:2] == (0xEB9F).to_bytes(2, "little"):
        return data
    return _elf_section(data, ".BTF") or b""


def find_in_gdb() -> BTF | None:
    """Read the ``.BTF`` section of the loaded objfiles, if any.

    The section bytes come from the inferior when one is selected and
    the section is mapped at a readable address; otherwise they come from
    the objfile's file on disk, which is the normal path on GDB releases
    whose ``Objfile`` exposes no ``sections``.  Only the *loaded* image is
    consulted: a build with no BTF yields ``None`` rather than borrowing
    the host's, which would silently describe the wrong kernel.  Returns
    ``None`` outside GDB (the parser is pure Python and unit-tested that
    way).
    """
    if gdb is None:
        return None
    try:
        progspace = gdb.current_progspace()
        if progspace is None:
            return None
        objfiles = list(progspace.objfiles())
    except (AttributeError, gdb.error, TypeError):
        return None
    for objfile in objfiles:
        data = _read_btf_section(objfile)
        if not data:
            continue
        parsed = parse(data)
        if parsed is not None:
            return parsed
    return None


def _read_btf_section(objfile: Any) -> bytes | None:
    """Read the ``.BTF`` section bytes of one objfile, or ``None``."""
    if gdb is None:  # pragma: no cover - callers check first
        return None
    section = _find_section(objfile, ".BTF")
    if section is not None:
        try:
            start = int(section.start)
            end = int(section.end)
        except (AttributeError, TypeError, ValueError):
            start = end = 0
        # A live target maps the section, but at its link-time address:
        # with KASLR the read fails, and the file below is what works.
        if end > start:
            try:
                inferior = gdb.selected_inferior()
                if inferior is not None:
                    return bytes(inferior.read_memory(start, end - start))
            except (AttributeError, gdb.error, TypeError, MemoryError):
                pass
    # GDB 15's ``Objfile`` has no ``sections`` attribute at all, so the
    # file is not a fallback here -- it is the normal path on current
    # releases.  The objfile's own file describes the image it loaded.
    filename = getattr(objfile, "filename", None)
    if not filename:
        return None
    try:
        data = Path(filename).read_bytes()
    except OSError:
        return None
    return _elf_section(data, ".BTF")


def _find_section(objfile: Any, name: str) -> Any:
    if gdb is None:  # pragma: no cover - callers check first
        return None
    sections = getattr(objfile, "sections", None)
    if sections is None:
        return None
    if callable(sections):
        try:
            sections = sections()
        except (gdb.error, TypeError):
            return None
    try:
        iterator = iter(cast("Iterable[Any]", sections))
    except TypeError:
        return None
    for section in iterator:
        if getattr(section, "name", None) == name:
            return section
    return None


def _elf_section(data: bytes, name: str) -> bytes | None:
    """Return the contents of *name* from an ELF image, or ``None``."""
    if len(data) < 0x40 or data[:4] != b"\x7fELF":
        return None
    elf_class = data[4]
    endian = "<" if data[5] == 1 else ">"
    if elf_class == 2:
        # ELF64: e_shoff @0x28, then e_shentsize/shnum/shstrndx @0x3A.
        shoff, = struct.unpack_from(endian + "Q", data, 0x28)
        shentsize, shnum, shstrndx = struct.unpack_from(
            endian + "HHH", data, 0x3A,
        )
        offset_at, size_at = 24, 32
    elif elf_class == 1:
        # ELF32: e_shoff @0x20, then e_shentsize/shnum/shstrndx @0x2E.
        shoff, = struct.unpack_from(endian + "I", data, 0x20)
        shentsize, shnum, shstrndx = struct.unpack_from(
            endian + "HHH", data, 0x2E,
        )
        offset_at, size_at = 16, 20
    else:
        return None
    if shoff == 0 or shnum == 0 or shstrndx >= shnum:
        return None
    sections = []
    for index in range(shnum):
        base = shoff + index * shentsize
        if base + shentsize > len(data):
            return None
        sec_name, = struct.unpack_from(endian + "I", data, base)
        sec_off, = struct.unpack_from(endian + "I", data, base + offset_at)
        sec_size, = struct.unpack_from(endian + "I", data, base + size_at)
        sections.append((sec_name, sec_off, sec_size))
    str_off, str_size = sections[shstrndx][1], sections[shstrndx][2]
    if str_off + str_size > len(data):
        return None
    table = data[str_off:str_off + str_size]
    for sec_name, sec_off, sec_size in sections:
        if _decode(table, sec_name) == name:
            if sec_off + sec_size > len(data):
                return None
            return data[sec_off:sec_off + sec_size]
    return None


__all__ = ["BTF", "extract_btf", "find_in_gdb", "load", "parse"]