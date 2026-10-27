"""Unit tests for :mod:`kernlens.gdb.btf`.

The parser is pure Python (``gdb`` is imported defensively), so it is
tested here against hand-built blobs.  ``make_blob`` emits a real BTF
image, so the tests exercise the actual byte layout rather than a mock.
"""

from __future__ import annotations

import struct
import unittest

from kernlens.gdb import btf

# --- blob construction -------------------------------------------------

_MAGIC = 0xEB9F
_KIND_STRUCT = 4
_KIND_UNION = 5
_KIND_INT = 1
_KIND_PTR = 2
_KIND_TYPEDEF = 8


class StringTable:
    def __init__(self) -> None:
        self._data = bytearray(b"\x00")
        self._offsets: dict[str, int] = {"": 0}

    def add(self, text: str) -> int:
        if text in self._offsets:
            return self._offsets[text]
        offset = len(self._data)
        self._data += text.encode() + b"\x00"
        self._offsets[text] = offset
        return offset

    @property
    def data(self) -> bytes:
        return bytes(self._data)


def _type_header(name_off: int, info: int, size: int) -> bytes:
    return struct.pack("<III", name_off, info, size)


def _info(kind: int, vlen: int, kind_flag: int = 0) -> int:
    return (kind_flag << 31) | (kind << 24) | vlen


def _struct(name_off: int, size: int, members: list[tuple[int, int, int]]) -> bytes:
    return _aggregate(_KIND_STRUCT, name_off, size, members)


def _union(name_off: int, size: int, members: list[tuple[int, int, int]]) -> bytes:
    return _aggregate(_KIND_UNION, name_off, size, members)


def _aggregate(
    kind: int, name_off: int, size: int, members: list[tuple[int, int, int]],
) -> bytes:
    out = bytearray(_type_header(name_off, _info(kind, len(members)), size))
    for member_name, member_type, bit_offset in members:
        out.extend(struct.pack("<III", member_name, member_type, bit_offset))
    return bytes(out)


def make_blob() -> bytes:
    """Build a small BTF image:

    id 1  struct inner { int a; int b; }             (b at +4)
    id 2  union hidden { int hidden; }              (an anonymous member)
    id 3  struct outer { int id; struct inner in; int tail;
                         union { int hidden; }; }
        (in at +4, tail at +16, the union at +20)
    """
    strings = StringTable()
    types = bytearray()

    # id 1: struct inner
    types += _struct(
        strings.add("inner"), 8,
        [(strings.add("a"), 0, 0), (strings.add("b"), 0, 32)],
    )
    # id 2: the anonymous union (name offset 0 = unnamed)
    types += _union(
        strings.add(""), 4,
        [(strings.add("hidden"), 0, 0)],
    )
    # id 3: struct outer; ``in`` references id 1, the trailing anonymous
    # union references id 2 and shares its member's name.
    types += _struct(
        strings.add("outer"), 24,
        [
            (strings.add("id"), 0, 0),
            (strings.add("in"), 1, 32),
            (strings.add("tail"), 0, 128),
            (strings.add(""), 2, 160),
        ],
    )

    type_bytes = bytes(types)
    str_bytes = strings.data
    header = struct.pack(
        "<HBBIIIII", _MAGIC, 1, 0, 24,
        0, len(type_bytes), len(type_bytes), len(str_bytes),
    )
    return header + type_bytes + str_bytes


# --- tests -------------------------------------------------------------

class ParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = btf.parse(make_blob())

    def test_parses(self) -> None:
        self.assertIsNotNone(self.db)
        assert self.db is not None
        self.assertTrue(self.db.has("struct outer"))

    def test_has_tolerates_the_tag(self) -> None:
        assert self.db is not None
        self.assertTrue(self.db.has("outer"))
        self.assertTrue(self.db.has("struct outer"))

    def test_sizeof(self) -> None:
        assert self.db is not None
        self.assertEqual(self.db.sizeof("struct outer"), 24)
        self.assertEqual(self.db.sizeof("struct inner"), 8)

    def test_direct_member(self) -> None:
        assert self.db is not None
        self.assertEqual(self.db.offset("struct outer", "id"), 0)
        self.assertEqual(self.db.offset("struct outer", "tail"), 16)

    def test_nested_member(self) -> None:
        assert self.db is not None
        # ``in`` at +4, ``b`` at +4 inside it -> +8.
        self.assertEqual(self.db.offset("struct outer", "in.a"), 4)
        self.assertEqual(self.db.offset("struct outer", "in.b"), 8)

    def test_member_inside_an_anonymous_union(self) -> None:
        # ``struct page.lru`` (and ``slab.freelist``, ``slab.counters``,
        # ``bpf_prog.insns``) live in a member BTF inlines without a name,
        # so a lookup must descend into unnamed struct/union members.
        # The anonymous union sits at +20 and ``hidden`` at +0 inside it.
        assert self.db is not None
        self.assertEqual(self.db.offset("struct outer", "hidden"), 20)

    def test_anonymous_descent_prefers_a_named_member(self) -> None:
        # ``id`` is a direct member at +0; the anonymous union also holds
        # ``hidden`` at +20, so the direct member must win for its name.
        assert self.db is not None
        self.assertEqual(self.db.offset("struct outer", "id"), 0)
        self.assertIsNone(self.db.offset("struct outer", "a"))

    def test_nested_path_inside_an_anonymous_member(self) -> None:
        # The inner struct ``in`` is named, but the path still descends a
        # named member inside it; both forms must resolve.
        assert self.db is not None
        self.assertEqual(self.db.offset("struct inner", "b"), 4)
        self.assertIsNone(self.db.offset("struct inner", "hidden"))

    def test_unknown_type_is_none(self) -> None:
        assert self.db is not None
        self.assertIsNone(self.db.offset("struct nope", "a"))
        self.assertIsNone(self.db.sizeof("struct nope"))
        self.assertFalse(self.db.has("struct nope"))

    def test_unknown_member_is_none(self) -> None:
        assert self.db is not None
        self.assertIsNone(self.db.offset("struct outer", "absent"))
        self.assertIsNone(self.db.offset("struct outer", "id.absent"))


class MalformedTests(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertIsNone(btf.parse(b""))

    def test_short_header(self) -> None:
        self.assertIsNone(btf.parse(b"\x9f\xeb" + b"\x00" * 8))

    def test_bad_magic(self) -> None:
        blob = bytearray(make_blob())
        blob[0] = 0
        self.assertIsNone(btf.parse(bytes(blob)))

    def test_truncated_type_section(self) -> None:
        blob = make_blob()
        # Header claims a type section longer than the buffer holds.
        broken = bytearray(blob)
        struct.pack_into("<I", broken, 16, len(blob) * 2)
        self.assertIsNone(btf.parse(bytes(broken)))

    def test_truncated_payload(self) -> None:
        # Cut the final member off; the walker must fail, not loop.
        blob = make_blob()[:24 + 4]
        self.assertIsNone(btf.parse(blob))


class ExtractTests(unittest.TestCase):
    def test_raw_blob_passthrough(self) -> None:
        blob = make_blob()
        self.assertEqual(btf.extract_btf(blob), blob)

    def test_non_elf_is_empty(self) -> None:
        self.assertEqual(btf.extract_btf(b"not an elf"), b"")

    def test_elf64_section(self) -> None:
        blob = make_blob()
        elf = _make_elf64({".BTF": blob, ".text": b"\x90"})
        self.assertEqual(btf.extract_btf(elf), blob)

    def test_elf64_without_btf(self) -> None:
        elf = _make_elf64({".text": b"\x90"})
        self.assertEqual(btf.extract_btf(elf), b"")

    def test_elf32_section(self) -> None:
        blob = make_blob()
        elf = _make_elf32({".BTF": blob})
        self.assertEqual(btf.extract_btf(elf), blob)


class LoadTests(unittest.TestCase):
    def test_load_missing_file(self) -> None:
        self.assertIsNone(btf.load("/nonexistent/path/to/blob"))

    def test_load_elf_with_btf(self) -> None:
        import tempfile
        from pathlib import Path

        blob = make_blob()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "vmlinux.btf"
            path.write_bytes(_make_elf64({".BTF": blob}))
            db = btf.load(str(path))
        self.assertIsNotNone(db)
        assert db is not None
        self.assertEqual(db.offset("struct outer", "in.b"), 8)

    def test_find_in_gdb_without_gdb_is_none(self) -> None:
        # The parser is imported outside GDB in the unit suite.
        self.assertIsNone(btf.find_in_gdb())


# --- minimal ELF builders ---------------------------------------------

def _name_table(sections: dict[str, bytes]) -> tuple[bytearray, dict[str, int]]:
    table = bytearray(b"\x00")
    offsets = {"": 0}
    for name in (".shstrtab", *sections):
        offsets[name] = len(table)
        table += name.encode() + b"\x00"
    return table, offsets


def _make_elf64(sections: dict[str, bytes]) -> bytes:
    table, offsets = _name_table(sections)
    header_size = 64
    payload = bytearray()
    data_offsets: dict[str, int] = {}
    for name, data in sections.items():
        data_offsets[name] = header_size + len(payload)
        payload += data
    data_offsets[".shstrtab"] = header_size + len(payload)
    payload += table
    shoff = header_size + len(payload)
    shdrs = bytearray(bytes(64))  # null section header
    shdrs += _shdr64(
        offsets[".shstrtab"], 3, data_offsets[".shstrtab"], len(table),
    )
    for name, data in sections.items():
        shdrs += _shdr64(offsets[name], 1, data_offsets[name], len(data))
    header = struct.pack(
        "<4sBBBBB7xHHIQQQIHHHHHH",
        b"\x7fELF", 2, 1, 1, 0, 0,
        2, 62, 1, 0, 0, shoff, 0, header_size, 0, 0, header_size,
        len(offsets), 1,
    )
    return bytes(header) + bytes(payload) + bytes(shdrs)


def _shdr64(name: int, type_: int, offset: int, size: int) -> bytes:
    return struct.pack(
        "<IIQQQQIIQQ", name, type_, 0, 0, offset, size, 1, 0, 0, 0,
    )


def _make_elf32(sections: dict[str, bytes]) -> bytes:
    table, offsets = _name_table(sections)
    header_size = 52
    payload = bytearray()
    data_offsets: dict[str, int] = {}
    for name, data in sections.items():
        data_offsets[name] = header_size + len(payload)
        payload += data
    data_offsets[".shstrtab"] = header_size + len(payload)
    payload += table
    shoff = header_size + len(payload)
    shdrs = bytearray(bytes(40))  # null section header
    shdrs += _shdr32(
        offsets[".shstrtab"], 3, data_offsets[".shstrtab"], len(table),
    )
    for name, data in sections.items():
        shdrs += _shdr32(offsets[name], 1, data_offsets[name], len(data))
    header = struct.pack(
        "<4sBBBBB7xHHIIIIIHHHHHH",
        b"\x7fELF", 1, 1, 1, 0, 0,
        2, 3, 1, 0, 0, shoff, 0, header_size, 0, 0, 40,
        len(offsets), 1,
    )
    return bytes(header) + bytes(payload) + bytes(shdrs)


def _shdr32(name: int, type_: int, offset: int, size: int) -> bytes:
    return struct.pack(
        "<IIIIIIIIII", name, type_, 0, 0, offset, size, 1, 0, 0, 0,
    )


if __name__ == "__main__":
    unittest.main()