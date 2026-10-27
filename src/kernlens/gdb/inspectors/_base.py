#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Shared base for the kernel subsystem inspectors.

``InspectorBase`` owns the reader reference plus the primitives and
memory-layout helpers that more than one subsystem needs (byte/word
reads, C strings, list walks, ``vmemmap_base`` / ``page_offset_base``).
Putting them here keeps each subsystem module focused on its own
kernel structures and avoids cross-domain coupling.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast, final

import gdb  # type: ignore[import-not-found]

from .._types import _IntConvertible, _StrLike
from .. import btf, layouts
from ..reader import MemoryReader

#: Mask for a 64-bit value.
MASK64 = 0xFFFFFFFFFFFFFFFF

#: Pointer-sized word (x86_64).
PTRSIZE = 8

#: Bound on generic ``list_head`` walks so a corrupted list cannot spin.
LIST_LIMIT = 4096

#: Fallback ``vmemmap_base`` when the runtime symbol is unreadable.
VMEMAP_BASE_DEFAULT = 0xFFFFEA0000000000

#: Fallback ``page_offset_base`` when the runtime symbol is unreadable.
PAGE_OFFSET_BASE_DEFAULT = 0xFFFF888000000000

#: Sentinel for "offset not resolved yet" in the per-inspector cache.
_MISSING = object()


@final
class _ByteReader:
    """On-demand, chunked byte reader over kernel memory.

    Tables are read through a moving cursor; pulling blocks keeps the
    number of GDB memory reads small even when the source is several
    megabytes.  A failed block shrinks and retries, because a GDB memory
    read fails when *any* byte is unmapped: the tail of a section can be
    followed by a gap even though the table itself is contiguous.
    """

    __slots__: tuple[str, ...] = ("_chunk", "_read", "_base", "_data")

    def __init__(
        self,
        read: Callable[[int, int], bytes | None],
        chunk: int = 1 << 14,
    ) -> None:
        self._read: Callable[[int, int], bytes | None] = read
        self._chunk: int = chunk
        self._base: int = -1
        self._data: bytes = b""

    def _load(self, addr: int) -> bool:
        if self._base <= addr < self._base + len(self._data):
            return True
        size = self._chunk
        while size >= 64:
            block = self._read(addr, size)
            if block:
                self._base = addr
                self._data = block
                return True
            size //= 2
        return False

    def read(self, addr: int, size: int) -> bytes | None:
        """Read *size* bytes at *addr*, spanning blocks as needed."""
        if size <= 0:
            return b""
        out = bytearray()
        while size > 0:
            if not self._load(addr):
                return None
            start = addr - self._base
            take = min(size, len(self._data) - start)
            if take <= 0:
                return None
            out += self._data[start : start + take]
            addr += take
            size -= take
        return bytes(out)

    def u8(self, addr: int) -> int | None:
        """Read one byte at *addr*, or ``None``."""
        data = self.read(addr, 1)
        return data[0] if data else None


class InspectorBase:
    """Reader reference plus the shared read primitives.

    The concrete :class:`~kernlens.gdb.kernel.KernelInspector` supplies
    ``_reader`` and declares the cache slots; each subsystem mixin only
    adds its own methods.
    """

    __slots__: tuple[str, ...] = (
        "_reader", "_offsets", "_fallbacks", "_btf",
    )

    _reader: MemoryReader

    #: Cached ``(type, path) -> offset`` results; see :meth:`_offset_of`.
    _offsets: "dict[tuple[str, str], int | None]"

    #: ``(type, path)`` keys whose value came from a fallback, not DWARF.
    _fallbacks: "set[tuple[str, str]]"

    #: Lazily loaded BTF database; ``False`` means "not looked up yet".
    _btf: "btf.BTF | None | bool"

    # --- enum / constant probes -----------------------------------------

    def enum_value(
        self, enum_or_member: str, member: str | None = None,
    ) -> int | None:
        """Return the value of an enumerator, or ``None`` when unknown.

        Call it as ``enum_value("PG_buddy")`` (find the enum by the
        member name, the spelling the kernel source guarantees) or as
        ``enum_value("pageflags", "PG_buddy")`` when the enum is already
        known.  The value comes from the running kernel's own
        enumeration -- DWARF first, then BTF -- because these numbers are
        compiled in and do move between builds: ``PG_slab`` is bit 9 in
        6.1, and 7.0's ``PGTY_*`` values are byte constants rather than
        bits.
        """
        if member is None:
            member = enum_or_member
            dwarf = self._dwarf_constant(member)
            if dwarf is not None:
                return dwarf
            found = self._dwarf_member_in_enums(member)
            return found if found is not None else self._btf_constant(member)
        members = self.enum_members(enum_or_member)
        return members.get(member) if members else None

    #: Enums a bare member name is looked up in when the debug info does
    #: not expose it as a global symbol.  Deliberately short: it is a
    #: fallback for the constants this package asks about, not a search
    #: of every enum in the kernel (which would cost thousands of type
    #: lookups on the first use).
    _ENUM_SEARCH: tuple[str, ...] = (
        "pageflags", "pagetype", "page_type", "migratetype", "zone_type",
    )

    def _dwarf_member_in_enums(self, member: str) -> int | None:
        """Find *member* in one of :attr:`_ENUM_SEARCH`'s enums.

        ``gdb.parse_and_eval`` resolves an enumerator only when its enum
        was emitted into the enclosing scope; for a type-enumerated
        build the member is reachable through the enum type instead, so
        the type is consulted directly.
        """
        for enum_name in self._ENUM_SEARCH:
            members = self._dwarf_enum_members(enum_name)
            if members and member in members:
                return members[member]
        return None

    def has_constant(self, member: str) -> bool:
        """Whether an enumerator called *member* exists in this kernel.

        This, not an enum name, is the dependable ABI probe: 6.1 has no
        ``PGTY_*`` enumerator at all while 7.0 has one per page type, so
        the presence of ``PGTY_buddy`` separates the two encodings
        unconditionally.
        """
        return self.enum_value(member) is not None

    def enum_members(self, enum_name: str) -> "dict[str, int] | None":
        """Return ``{member: value}`` for *enum_name*, or ``None``.

        DWARF is read first (exact for the debuggable build); BTF
        answers when there is no debug info, so a stripped kernel still
        gets real values rather than a table.  A missing enum yields
        ``None`` -- never a guess.
        """
        members = self._dwarf_enum_members(enum_name)
        if members is not None:
            return members
        database = self._btf_database()
        return database.enum_members(enum_name) if database else None

    def enum_of_member(self, member: str) -> str | None:
        """Return the BTF enum that defines *member*, or ``None``.

        Only BTF answers this cheaply: DWARF resolves an enumerator to
        its value but not to its owning enum, and recovering the name
        would mean walking every enum in the debug info.  The probe is
        by member on purpose -- see :meth:`has_constant`.
        """
        database = self._btf_database()
        return database.enum_with_member(member) if database else None

    @staticmethod
    def _dwarf_constant(member: str) -> int | None:
        """Evaluate one enumerator against the loaded debug info."""
        try:
            value = int(cast(_IntConvertible, gdb.parse_and_eval(member)))
        except (gdb.error, TypeError, ValueError, AttributeError):
            return None
        return value

    def _btf_constant(self, member: str) -> int | None:
        """Look one enumerator up in BTF, or ``None``."""
        enum_name = self.enum_of_member(member)
        if enum_name is None:
            return None
        members = self.enum_members(enum_name)
        return members.get(member) if members else None

    def _dwarf_enum_members(self, enum_name: str) -> "dict[str, int] | None":
        """Read an enum's enumerators from DWARF, or ``None``.

        Both spellings resolve (``pageflags`` and ``enum pageflags``).
        The members are taken from the type the debug info carries, so
        the numbers match the kernel being debugged even when the host
        headers disagree.
        """
        enum_type = self._lookup_enum(enum_name)
        if enum_type is None:
            return None
        fields = getattr(enum_type, "fields", None)
        if not fields:
            return None
        members: dict[str, int] = {}
        for field in fields():
            if field.name is None:
                continue
            # GDB exposes an enumerator's value as ``enumval``; ``bitpos``
            # is the struct-member attribute and is absent here.  Both are
            # tried so the reader works across GDB versions that set one
            # or the other.
            value = getattr(field, "enumval", None)
            if value is None:
                value = getattr(field, "bitpos", None)
            if value is None:
                continue
            members[field.name] = int(value)
        return members or None

    @staticmethod
    def _lookup_enum(enum_name: str) -> "gdb.Type | None":
        """Resolve *enum_name* to its DWARF type, or ``None``."""
        bare = enum_name.removeprefix("enum ").strip()
        code_enum = getattr(gdb, "TYPE_CODE_ENUM", None)
        for spelling in (bare, f"enum {bare}"):
            try:
                found = gdb.lookup_type(spelling)
            except (gdb.error, AttributeError, TypeError, ValueError):
                continue
            if getattr(found, "code", None) == code_enum:
                return found
        return None

    # --- struct offsets -------------------------------------------------

    def _offset_of(
        self, type_name: str, path: str, default: int | None = None,
    ) -> int | None:
        """Return ``offsetof(type_name, path)`` from the best available source.

        Resolution is a three-tier chain:

        1. **DWARF** -- the loaded ``vmlinux``'s debug info, which is
           exact for the running build;
        2. **BTF** -- the type database embedded in the image
           (``CONFIG_DEBUG_INFO_BTF``), read directly through
           :mod:`kernlens.gdb.btf` when DWARF is absent;
        3. **the registry** -- *default*, the verified table in
           :mod:`kernlens.gdb.layouts`, whose use is recorded so the
           command layer can warn that it may be wrong for this build.

        The result is cached per process, so each source is consulted at
        most once per ``(type, path)``.
        """
        key = (type_name, path)
        cached = self._offsets.get(key, _MISSING)
        if cached is _MISSING:
            cached = self._resolve_offset(type_name, path)
            self._offsets[key] = cached
            # Record a fallback once per cache lifetime, so the command
            # layer can warn without repeating on every invocation.
            if cached is None and default is not None:
                self._note_fallback(key)
        # The default is applied per call so a caller can supply a
        # fallback without poisoning the cache for the next one.
        return cast("int", cached) if cached is not None else default

    def _resolve_offset(self, type_name: str, path: str) -> int | None:
        """Try DWARF, then BTF, for ``offsetof(type_name, path)``."""
        value = self._dwarf_offset(type_name, path)
        if value is not None:
            return value
        database = self._btf_database()
        return database.offset(type_name, path) if database else None

    @staticmethod
    def _dwarf_offset(type_name: str, path: str) -> int | None:
        """Resolve an offset from the loaded debug info, or ``None``."""
        try:
            value = gdb.parse_and_eval(
                f"(unsigned long)&(({type_name} *)0)->{path}"
            )
            return int(cast(_IntConvertible, value))
        except (gdb.error, TypeError, ValueError, AttributeError):
            return None

    @staticmethod
    def _array_length(type_name: str, path: str) -> int | None:
        """Return how many elements the array member *path* holds.

        Read from the type's layout rather than a constant, because
        several kernel arrays are sized by a ``CONFIG_*`` knob that is
        invisible to symbols and enums -- ``struct zone.free_area`` has
        one entry per ``MAX_ORDER``, which ``CONFIG_ARCH_FORCE_MAX_ORDER``
        can move.  Returns ``None`` when the member is absent or is not
        an array.
        """
        size = f"sizeof((({type_name} *)0)->{path})"
        try:
            value = gdb.parse_and_eval(
                f"{size} / sizeof((({type_name} *)0)->{path}[0])"
            )
            return int(cast(_IntConvertible, value))
        except (gdb.error, TypeError, ValueError, AttributeError, ZeroDivisionError):
            return None

    def _sizeof(
        self, type_name: str, default: int | None = None,
    ) -> int | None:
        """Return ``sizeof(type_name)``: DWARF, then BTF, then *default*."""
        key = (type_name, "#sizeof")
        cached = self._offsets.get(key, _MISSING)
        if cached is _MISSING:
            cached = self._resolve_sizeof(type_name)
            self._offsets[key] = cached
            if cached is None and default is not None:
                self._note_fallback(key)
        return cast("int", cached) if cached is not None else default

    def _resolve_sizeof(self, type_name: str) -> int | None:
        """Try DWARF, then BTF, for ``sizeof(type_name)``."""
        try:
            value = gdb.parse_and_eval(f"sizeof({type_name})")
            return int(cast(_IntConvertible, value))
        except (gdb.error, TypeError, ValueError):
            pass
        database = self._btf_database()
        return database.sizeof(type_name) if database else None

    def _btf_database(self) -> "btf.BTF | None":
        """Return the BTF database for this session, loading it once.

        Prefers an explicit ``reader.config.btf_path``, then the ``.BTF``
        section of the *loaded image*.  Nothing else is consulted: using
        the host's BTF while debugging another kernel would silently
        describe the wrong build.  The result (including a negative one)
        is cached, so a build with no BTF never pays the lookup twice.
        """
        if self._btf is not False:
            return cast("btf.BTF | None", self._btf)
        database = self._load_btf()
        self._btf = database if database is not None else None
        return database

    def _load_btf(self) -> "btf.BTF | None":
        configured = getattr(
            getattr(self, "_reader", None), "_config", None,
        )
        path = getattr(configured, "btf_path", None)
        if path:
            return btf.load(path)
        return btf.find_in_gdb()

    def _note_fallback(self, key: tuple[str, str]) -> None:
        """Record that *key* was resolved from a table, not the debug info."""
        self._fallbacks.add(key)

    def layout_fallbacks(self) -> tuple[str, ...]:
        """Return the struct types whose layout fell back to a table.

        Empty when every offset resolved from the loaded DWARF or BTF.
        The command layer prints a warning listing these types, because
        the fallback values are only verified for one kernel build and
        may be silently wrong for another (``CONFIG_*`` changes the
        layout).
        """
        types = {type_name for type_name, _ in self._fallbacks}
        return tuple(sorted(types))

    def clear_layout_fallbacks(self) -> None:
        """Forget which layouts fell back (called by ``reset``)."""
        self._fallbacks.clear()
        self._btf = False

    # --- registry-backed fallbacks --------------------------------------

    def _version_hint(self) -> "layouts.Version | None":
        """Return the running kernel's version, for variant selection.

        Derived from the version banner; ``None`` when unreadable, in
        which case a variant's version bounds are treated as matching
        (the caller is already on the no-debug-info path).
        """
        text = getattr(self, "version", None)
        if text is None:
            return None
        try:
            raw = text()
        except (gdb.error, TypeError, ValueError):
            return None
        return layouts.parse_version(raw)

    def _config_hint(self) -> "dict[str, str]":
        """Return the live ``CONFIG_*`` mapping, or ``{}`` when absent.

        The values gate the registry variants (for example
        ``CONFIG_SECURITY`` decides whether ``struct bpf_map`` carries a
        ``security`` pointer), so a layout must only be chosen when its
        predicates hold.
        """
        getter = getattr(self, "kconfig", None)
        if getter is None:
            return {}
        try:
            return dict(getter())
        except (gdb.error, TypeError, ValueError):
            return {}

    def _fallback_offset(self, type_name: str, path: str) -> int | None:
        """Return a registry fallback for ``offsetof(type_name, path)``."""
        return layouts.offset(
            type_name, path, self._version_hint(), self._config_hint(),
        )

    def _fallback_sizeof(self, type_name: str) -> int | None:
        """Return a registry fallback for ``sizeof(type_name)``."""
        return layouts.sizeof(
            type_name, self._version_hint(), self._config_hint(),
        )

    def _layout_offset(self, type_name: str, path: str) -> int | None:
        """Resolve ``offsetof(type_name, path)``: DWARF, BTF, then registry.

        This is the call the inspectors use.  The loaded debug info wins
        whenever the type is present; a build without DWARF is served by
        its embedded BTF; only when neither knows the type does the value
        come from :mod:`kernlens.gdb.layouts`, whose use is recorded so
        the command layer can warn that it may be wrong for this build.
        """
        return self._offset_of(
            type_name, path, self._fallback_offset(type_name, path),
        )

    def _layout_sizeof(self, type_name: str) -> int | None:
        """Resolve ``sizeof(type_name)``: DWARF, BTF, then registry."""
        return self._sizeof(type_name, self._fallback_sizeof(type_name))

    # --- word reads -----------------------------------------------------

    def _read_u64(self, addr: int) -> int | None:
        """Read a little-endian 64-bit word, or ``None``."""
        raw = self._read_bytes(addr, 8)
        if raw is None:
            return None
        return int.from_bytes(raw, "little")

    def _read_u32(self, addr: int, *, signed: bool) -> int | None:
        """Read a 32-bit word (optionally signed), or ``None``.

        Uses the reader's expression form so a loaded objfile's type
        information is honoured, matching :meth:`page_type`.
        """
        value = self._reader.u64(f"*(unsigned int *){addr:#x}")
        if value is None:
            return None
        value &= 0xFFFFFFFF
        if signed and value & 0x80000000:
            return value - (1 << 32)
        return value

    def _read_u16(self, addr: int) -> int | None:
        """Read a little-endian 16-bit word, or ``None``."""
        raw = self._read_bytes(addr, 2)
        if raw is None:
            return None
        return int.from_bytes(raw, "little")

    def _read_u8(self, addr: int) -> int | None:
        """Read one byte at *addr*, or ``None``."""
        raw = self._read_bytes(addr, 1)
        return raw[0] if raw else None

    # --- strings / bytes ------------------------------------------------

    def _cstring(self, addr: int) -> str | None:
        """Read a NUL-terminated string at *addr* via GDB's ``x/s``."""
        if not addr:
            return None
        try:
            raw = gdb.execute(f"x/s {addr:#x}", to_string=True)
        except (gdb.error, TypeError, ValueError):
            return None
        text = cast(_StrLike, raw)
        if '"' in text:  # pyright: ignore[reportOperatorIssue]
            return text.split('"')[1]  # pyright: ignore[reportOperatorIssue]
        return None

    def _read_bytes(self, addr: int, size: int) -> bytes | None:
        """Read *size* bytes at *addr*, or ``None`` when unreadable."""
        if size <= 0:
            return None
        try:
            inferior = gdb.selected_inferior()
            return bytes(inferior.read_memory(addr, size))
        except (gdb.error, AttributeError, MemoryError, TypeError, ValueError):
            return None

    # --- helpers --------------------------------------------------------

    @staticmethod
    def _is_kernel(addr: int) -> bool:
        """Whether *addr* falls inside the kernel address half."""
        return bool(addr) and addr >= 0xFFFF800000000000

    def _walk_list(self, head: int, offset: int, limit: int) -> list[int]:
        """Walk a ``list_head`` list, returning each container object."""
        first = self._read_u64(head)
        if not first or first == head:
            return []
        result: list[int] = []
        seen: set[int] = set()
        node = first
        while node and node != head and len(result) < limit:
            if node in seen:
                break
            seen.add(node)
            result.append((node - offset) & MASK64)
            node = self._read_u64(node) or 0
        return result

    # --- memory layout --------------------------------------------------

    def _vmemmap_base(self) -> int:
        """Return the runtime ``vmemmap_base`` (fallback: constant)."""
        value = self._reader.read_kvar("vmemmap_base")
        return value if value else VMEMAP_BASE_DEFAULT

    def _page_offset_base(self) -> int:
        """Return the runtime ``page_offset_base`` (fallback: constant)."""
        value = self._reader.read_kvar("page_offset_base")
        return value if value else PAGE_OFFSET_BASE_DEFAULT


__all__ = [
    "InspectorBase",
    "LIST_LIMIT",
    "MASK64",
    "PAGE_OFFSET_BASE_DEFAULT",
    "PTRSIZE",
    "VMEMAP_BASE_DEFAULT",
    "_ByteReader",
]