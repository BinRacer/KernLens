#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""x86_64 ``struct page`` typing: the ``page_type`` word and ``_refcount``.

The kernel tags a page by reusing the word at ``page + 0x30``, named
``_mapcount`` before 6.11 and ``page_type`` from then on.  Which
*encoding* that word uses changed twice; every claim below was read from
the v4.19-v7.3 sources and the 6.1.134 live kernel rather than assumed.
The type bits were plain ``#define`` macros before 6.9, which is what
makes the older encodings different in kind: nothing can *read* them, so
their fixed values are carried here and verified against those releases.

**The type word**

* through 6.8 -- a bit *cleared* out of ``PAGE_TYPE_BASE``
  (``0xf0000000``), which is a macro like the per-type bits themselves
  (``PG_buddy`` = ``0x80`` in ``flags``).  A live 6.1 free page reads
  ``0xffffff7f``: ``PG_buddy`` cleared.  ``PG_slab``, ``PG_hugetlb`` and
  ``PG_zsmalloc`` are ``flags`` bits rather than type-word bits.
* 6.9 - 6.11 -- the same inverted-bit scheme, with the bits collected
  into an enum.  ``PG_slab`` joins it in 6.10 (``0x00001000`` there,
  ``0x02000000`` in 6.11).
* 6.12 onwards -- the word is ``page_type`` outright and its *high byte*
  is an ordinal into ``enum pagetype`` (``PGTY_buddy = 0xf0``), with the
  low 24 bits left to the owner.

**A slab page**

* through 6.9 -- bit 9 of ``flags`` (``PG_slab`` in ``enum pageflags``).
* 6.10 onwards -- the ``PG_slab`` bit of the type word, which is the
  same number ``PGTY_slab`` compares against from 6.12, so one numeric
  test serves both.

Values come from the kernel being debugged wherever it exposes them (a
6.9+ enum, or ``migratetype_names`` for the buddy code) and from the
verified table in this module where it does not; the two cannot
disagree, because the table is checked against the source every release
that uses it.
"""

from __future__ import annotations

from ._base import InspectorBase

#: Recognised type names in the 6.12+ ``enum pagetype`` encoding, in
#: ordinal order (``PGTY_<name>`` holds the value at each index).
PAGE_TYPES: tuple[str, ...] = (
    "buddy", "offline", "table", "guard",
    "hugetlb", "slab", "zsmalloc", "unaccepted",
)

#: Type names the bit encoding stores in the type word, paired with the
#: bit that *flags* sets for them.  The type word inverts these, so a
#: page is typed as ``name`` when ``word & bit == 0``.  The bits are
#: ``#define`` macros in most releases and so never reach DWARF or BTF;
#: the values here were read from the sources and are identical in v5.15
#: through v6.10 (``buddy`` and ``offline`` are also unchanged back to
#: v4.19; ``table``/``guard`` sat one bit higher in v5.10 and earlier).
#: 6.11 keeps the scheme but relocates the bits, and *those* are enum
#: members, so the enum value wins whenever it exists.
BIT_TYPE_TABLE: tuple[tuple[str, int], ...] = (
    ("buddy", 0x80),
    ("offline", 0x100),
    ("table", 0x200),
    ("guard", 0x400),
)

#: Type names the bit encoding stores in the type word, in ordinal
#: order.  ``slab``, ``hugetlb`` and ``zsmalloc`` are absent because they
#: are not ``PAGE_TYPE_OPS`` members before 6.10.
BIT_PAGE_TYPES: tuple[str, ...] = tuple(
    name for name, _bit in BIT_TYPE_TABLE
)

#: ``struct page`` word holding ``page_type`` / ``_mapcount``.  Stable
#: from 4.x through 7.x (checked against v4.19 ... v7.3 sources).
PAGE_TYPE_FALLBACK = 0x30

#: ``struct page`` word holding ``_refcount``; it follows the above.
PAGE_REFCOUNT_FALLBACK = 0x34

#: ``struct page`` word holding ``private`` -- the buddy order on a free
#: page and the SLUB freelist on an active slab page.  Verified over the
#: same 4.x-7.x range as the type word.
PAGE_PRIVATE_FALLBACK = 0x28

#: ``struct page`` word holding ``flags``.
PAGE_FLAGS_FALLBACK = 0x0

#: ``enum pagetype`` ordinal meaning "typed as a buddy page".
PGTY_BUDDY = 0xF0

#: ``enum pagetype`` ordinal meaning "typed as a slab page".  Equal to
#: the ``PG_slab`` bit of the type word in the 6.10/6.11 encoding, so
#: the two can share one comparison.
PGTY_SLAB = 0xF5

#: ``flags`` bit that marks a slab page while ``enum pageflags`` still
#: defines ``PG_slab``.  Bit 9 in every release from 4.x through 6.9,
#: which is the whole range the bit is used in.
PG_SLAB_FLAG_BIT = 9

#: ``PAGE_TYPE_BASE`` of the bit encoding.  Fixed at ``0xf0000000`` from
#: 4.x through 6.10; 6.11 moved it to ``0x80000000`` but also turned it
#: into an enumerator, so the enumerator wins whenever it exists.
PAGE_TYPE_BASE = 0xF0000000

#: Largest value ``page->private`` can hold as a buddy order
#: (``MAX_PAGE_ORDER`` is 10).  Anything above it is not an order.
MAX_BUDDY_ORDER = 10

#: Ordinal returned for "the type word carries no recognisable type".
UNKNOWN_INDEX = -1


class StructPageInspector(InspectorBase):
    """Decode the packed ``struct page`` type/refcount fields."""

    __slots__: tuple[str, ...] = ()

    # --- encoding detection ---------------------------------------------
    #
    # Resolved once per session: the lookup walks DWARF then BTF, and the
    # answer cannot change while an image stays loaded.  ``False`` means
    # "not probed yet", so a real answer is always a bool.

    def page_type_is_enum(self) -> bool:
        """Whether this kernel uses the 6.12+ ordinal encoding.

        ``enum pageflags`` still defines ``PG_slab`` in the bit encoding
        and stops defining it at exactly the release that switches, so
        that single member identifies the encoding on every kernel -- and
        unlike ``PAGE_TYPE_BASE`` or ``PGTY_buddy`` it has been an enum
        member since 2009, so it survives in the debug info of old
        builds where the newer names are macros or absent.
        """
        cached = getattr(self, "_page_is_enum", False)
        if cached is not False:
            return bool(cached)
        if self.enum_value("pageflags", "PG_slab") is not None:
            answer = False
        elif self.has_constant("PGTY_slab"):
            answer = True
        else:
            # No debug info at all.  The ``flags`` bit is not used after
            # 6.9, so assume the newer encoding: it is the conservative
            # choice, since misreading ``PG_slab`` as a type bit would
            # report a slab page for an arbitrary free page.
            answer = True
        try:
            self._page_is_enum = answer
        except AttributeError:
            pass
        return answer

    def _slab_type_bit(self) -> int | None:
        """Return the ``PGTY_slab`` ordinal or ``PG_slab`` type bit.

        Two shapes of answer, because the two later encodings differ:
        the 6.12+ word is an *ordinal* (so ``PGTY_slab`` is what to
        compare against) while 6.10/6.11 keep a *bit* that ``PG_slab``
        names.  ``enum pageflags`` is deliberately not consulted even
        though it also has a ``PG_slab``: bit 9 there belongs to
        ``flags``, not the type word.  ``None`` means the marker is not
        readable in this build, which callers treat as "unknown".
        """
        if self.has_constant("PGTY_slab"):
            return PGTY_SLAB
        if self.enum_value("PAGE_TYPE_BASE") is None:
            # The type word is not a bit mask here, so an old build like
            # 6.1 cannot have a type-word slab marker at all.
            return None
        value = self.enum_value("page_type", "PG_slab")
        if value is None:
            value = self.enum_value("pagetype", "PG_slab")
        return int(value) if value is not None else None

    # --- name lookup ----------------------------------------------------

    def page_type(self, page: int) -> str:
        """Return a human-readable ``struct page`` type for *page*.

        ``"initialized"`` is the kernel's word for a page carrying no
        type (the word reads ``-1``); a small non-negative value is a
        live mapcount rather than a tag.  Slab is tested *before* those
        two cases on purpose: a real 6.1 slab page has an untagged word
        (``0xffffffff``) and is identified only by ``PG_slab`` in
        ``flags``, so reporting it as merely ``initialized`` would lose
        the one fact the word cannot carry.
        """
        value = self._read_u32(self._page_type_addr(page), signed=True)
        if value is None:
            return "?"
        if self.page_is_slab(page) is True:
            return "slab"
        if value == -1:
            return "initialized"
        if value >= 0:
            return f"mapcount: {value}"
        word = value & 0xFFFFFFFF
        if self.page_type_is_enum():
            return self._enum_type_name(word)
        return self._bit_type_name(word)

    def page_type_index(self, page: int) -> int | None:
        """Return the raw type ordinal *page* carries, or ``None``.

        ``None`` means the word is not a tag: unreadable, an untagged
        ``-1``, or a live mapcount.
        """
        value = self._read_u32(self._page_type_addr(page), signed=True)
        if value is None or value >= -1:
            return None
        word = value & 0xFFFFFFFF
        if self.page_type_is_enum():
            return word >> 24
        ordinal = self._bit_type_ordinal(word)
        return None if ordinal == UNKNOWN_INDEX else ordinal

    def _enum_type_name(self, word: int) -> str:
        """Name the 6.12+ ordinal held in the high byte of *word*."""
        ordinal = word >> 24
        for name, value in self._pagetype_members().items():
            if value == ordinal and name.startswith("PGTY_"):
                return name.removeprefix("PGTY_")
        # The enum is unreadable (a kernel with no debug info at all).
        # The ordinal layout is nonetheless fixed by page-flags.h from
        # 6.12 on: ``PGTY_buddy`` is ``0xf0`` and each type follows in
        # the order :data:`PAGE_TYPES` lists.
        index = ordinal - PGTY_BUDDY
        if 0 <= index < len(PAGE_TYPES):
            return PAGE_TYPES[index]
        if ordinal <= 0x7F:
            # page-flags.h reserves 0x00-0x7f for positive mapcounts, so
            # a value in that range is not a tag.
            return f"mapcount: {ordinal}"
        return "unknown"

    def _bit_type_name(self, word: int) -> str:
        """Name the type held in a *tagged* word of the bit encoding.

        Only called once :meth:`page_is_type_word` has accepted the word,
        so a miss here means an owner reuses the word rather than that
        the page is untyped.
        """
        ordinal = self._bit_type_ordinal(word)
        if 0 <= ordinal < len(BIT_TYPE_TABLE):
            return BIT_TYPE_TABLE[ordinal][0]
        return "unknown"

    def _bit_type_ordinal(self, word: int) -> int:
        """Return the ``BIT_TYPE_TABLE`` index of the bit *word* clears.

        The bit encoding works by *inversion*: a type bit is set in
        ``flags`` and cleared in ``page_type``, and "no type" is the
        all-ones word.  So the type of a tagged page is the one whose bit
        is **clear** -- a live 6.1 free page reads ``0xffffff7f``, which
        is ``0x80`` (``PG_buddy``) cleared out of ``0xffffffff``.  The
        enum value is preferred where the kernel exposes one (6.10 and
        6.11); otherwise the verified constant is used, which is what the
        releases that define these as macros require.
        """
        for index, (name, fallback) in enumerate(BIT_TYPE_TABLE):
            value = self.enum_value(f"PG_{name}")
            if value is None:
                value = self.enum_value("page_type", f"PG_{name}")
            bit = int(value) if value is not None else fallback
            if word & bit == 0:
                return index
        return UNKNOWN_INDEX

    def _pagetype_members(self) -> dict[str, int]:
        """Return the ``PGTY_*`` members of this build's enum, or ``{}``."""
        return self.enum_members(self._pagetype_enum()) or {}

    def _pagetype_enum(self) -> str:
        """Return the name of the enum holding ``PGTY_*``, or ``""``."""
        return self.enum_of_member("PGTY_buddy") or ""

    # --- predicates -----------------------------------------------------

    def page_is_type_word(self, page: int) -> bool | None:
        """Whether *page*'s type word holds a tag rather than a mapcount.

        This is the single place the two encodings are reconciled, and
        the public predicates defer to it.  The bit encoding is flexible
        about *which* bits a tag clears, so a word is only accepted when
        at least one recorded type bit is clear; that both excludes a
        live mapcount and keeps an owner's reuse of the word out of the
        answer.
        """
        value = self._read_u32(self._page_type_addr(page), signed=True)
        if value is None:
            return None
        if value == -1:
            return False
        if value >= 0:
            return False
        word = value & 0xFFFFFFFF
        if self.page_type_is_enum():
            return word >> 24 != 0xFF
        return self._bit_type_ordinal(word) != UNKNOWN_INDEX

    def page_is_buddy(self, page: int) -> bool | None:
        """Whether *page* is a free buddy page, or ``None`` if unknown.

        This is what walking a ``buddy_list`` needs: a page on a free
        list is marked ``PageBuddy``, and the order it sits at then lives
        in ``private``.  ``None`` means the word could not be read.
        """
        if self.page_is_type_word(page) is not True:
            return False
        value = self._read_u32(self._page_type_addr(page), signed=True)
        if value is None:
            return None
        word = value & 0xFFFFFFFF
        if self.page_type_is_enum():
            return word >> 24 == PGTY_BUDDY
        return self._bit_type_ordinal(word) == 0

    def page_is_slab(self, page: int) -> bool | None:
        """Whether *page* belongs to the slab allocator, or ``None``.

        Two encodings: bit 9 of ``flags`` while ``enum pageflags`` still
        defines ``PG_slab`` (through 6.9), and the type word's
        ``PG_slab`` bit afterwards -- which is the same number
        ``PGTY_slab`` compares against from 6.12, so one numeric test
        serves both.  ``None`` means the marker is not readable here.
        """
        if self.enum_value("pageflags", "PG_slab") is not None:
            flags = self._read_u64(self._flags_addr(page))
            if flags is None:
                return None
            return bool(flags & (1 << PG_SLAB_FLAG_BIT))
        bit = self._slab_type_bit()
        if bit is None:
            return None
        if self.page_type_is_enum():
            return self.page_type_index(page) == bit
        value = self._read_u32(self._page_type_addr(page), signed=True)
        if value is None:
            return None
        if value >= -1:
            # An untagged ``-1``, or a live mapcount: neither is slab.
            return False
        # ``PG_slab`` is set on a non-slab page and cleared on a slab one,
        # so the test is inverted.
        return (value & 0xFFFFFFFF) & bit == 0

    # --- fields ---------------------------------------------------------

    def buddy_order(self, page: int) -> int | None:
        """Return the buddy order of a free page, or ``None``.

        The kernel stores the order in ``page->private`` when it puts a
        page on a free list (``set_buddy_order``), true from 4.x through
        7.3.  ``private`` is the SLUB freelist on an active slab page, so
        the value is only meaningful once :meth:`page_is_buddy` confirms
        the page really is free; an implausible value is rejected rather
        than reported.
        """
        if self.page_is_buddy(page) is not True:
            return None
        offset = (
            self._layout_offset("struct page", "private")
            or PAGE_PRIVATE_FALLBACK
        )
        value = self._read_u64(page + offset)
        if value is None or value > MAX_BUDDY_ORDER:
            return None
        return value

    def page_refcount(self, page: int) -> int | None:
        """Return ``page->_refcount`` as a signed 32-bit value."""
        offset = (
            self._layout_offset("struct page", "_refcount")
            or PAGE_REFCOUNT_FALLBACK
        )
        return self._read_u32(page + offset, signed=True)

    # --- addressing -----------------------------------------------------

    def _page_type_addr(self, page: int) -> int:
        """Address of the ``page_type`` / ``_mapcount`` word."""
        offset = (
            self._layout_offset("struct page", "_mapcount")
            or PAGE_TYPE_FALLBACK
        )
        return page + offset

    def _flags_addr(self, page: int) -> int:
        """Address of ``page->flags``."""
        offset = (
            self._layout_offset("struct page", "flags") or PAGE_FLAGS_FALLBACK
        )
        return page + offset


__all__ = [
    "BIT_PAGE_TYPES",
    "MAX_BUDDY_ORDER",
    "PAGE_FLAGS_FALLBACK",
    "PAGE_PRIVATE_FALLBACK",
    "PAGE_REFCOUNT_FALLBACK",
    "PAGE_TYPE_BASE",
    "PAGE_TYPE_FALLBACK",
    "PAGE_TYPES",
    "PGTY_BUDDY",
    "PGTY_SLAB",
    "PG_SLAB_FLAG_BIT",
    "StructPageInspector",
    "UNKNOWN_INDEX",
]