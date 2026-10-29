"""Integration tests for the GDB-side facade.

The tests run outside GDB by installing a small fake ``gdb`` module
before :mod:`kernlens.gdb.facade` is imported.  The fake models the few
GDB APIs the adapter uses: expression evaluation, symbol/line lookup,
memory reads, and stack frames.
"""

from __future__ import annotations

import importlib
import io
import struct
import sys
import types
import unittest
from types import SimpleNamespace

from kernlens import KPageTable, Logger
from kernlens.gdb import layouts


#: Real banner of the test kernel (Linux 6.1.134 as built for the
#: pwn4kernel VM).  The banner is an environment fact, unlike the
#: scratch addresses these tests invent for their own fake memory.
REAL_BANNER = (
    "Linux version 6.1.134 (bogon@bogon) (gcc (Ubuntu 14.2.0-4ubuntu2~24.04.1) "
    "14.2.0, GNU ld (GNU Binutils for Ubuntu) 2.42) #1 SMP PREEMPT_DYNAMIC"
)


class FakeGdbError(Exception):
    """Stand-in for :class:`gdb.error`."""


class FakeFrame:
    def __init__(self, pc: int, older: FakeFrame | None = None) -> None:
        self._pc = pc
        self._older = older

    def pc(self) -> int:
        return self._pc

    def older(self) -> FakeFrame:
        if self._older is None:
            raise FakeGdbError("no older frame")
        return self._older


class EndingFrame:
    """Real GDB returns None from ``Frame.older()`` at the oldest frame."""

    def __init__(self, pc: int) -> None:
        self._pc = pc

    def pc(self) -> int:
        return self._pc

    def older(self) -> None:
        return None


class BadIntValue:
    """A ``gdb.Value``-like object that cannot be converted to int."""

    def __int__(self) -> int:
        raise FakeGdbError("Cannot convert value to long.")


class FakeType:
    """The slice of ``gdb.Type`` that ``MemoryReader.field_value`` reads.

    Only ``code``, ``name``, ``sizeof`` and ``target()`` are used, and
    ``sizeof`` on an array is the WHOLE array -- GDB reports the total,
    not the element size, which is why ``_describe_array`` divides by the
    target's size instead of trusting this number twice.
    """

    def __init__(
        self,
        code: int,
        name: str = "",
        sizeof: int = 8,
        target: "FakeType | None" = None,
    ) -> None:
        self.code = code
        self.name = name
        self.sizeof = sizeof
        self._target = target

    def target(self) -> "FakeType":
        if self._target is None:
            raise FakeGdbError("not an array or pointer type")
        return self._target

    def __str__(self) -> str:
        return self.name


class FakeValue:
    """A ``gdb.Value`` that knows its type and its address."""

    def __init__(
        self,
        type_: FakeType,
        value: object,
        address: int | None = None,
    ) -> None:
        self.type = type_
        self._value = value
        self.address = address

    def __int__(self) -> int:
        if not isinstance(self._value, int):
            raise FakeGdbError("Cannot convert value to long.")
        return self._value

    def __str__(self) -> str:
        return str(self._value)


class FakeGdb(types.ModuleType):
    """Minimal GDB Python API used by the adapter."""

    error = FakeGdbError

    #: The one type-code constant the adapters compare against
    #: (``gdb.TYPE_CODE_ENUM``).
    TYPE_CODE_ENUM = 3
    #: The rest of ``gdb.TYPE_CODE_*`` that ``field_value`` dispatches on.
    #: Values match GDB's own enum so a real GDB and this fake agree.
    TYPE_CODE_PTR = 1
    TYPE_CODE_ARRAY = 2
    TYPE_CODE_STRUCT = 4
    TYPE_CODE_UNION = 5
    TYPE_CODE_INT = 8
    TYPE_CODE_BOOL = 11
    TYPE_CODE_FLOAT = 7

    def __init__(self) -> None:
        super().__init__("gdb")
        self.values: dict[str, object] = {}
        self.addresses: dict[str, int] = {}
        self.symbols: dict[int, str] = {}
        self.lines: dict[int, tuple[str, int]] = {}
        self.strings: dict[int, str] = {}
        self.frames: list[FakeFrame] = []
        self.monitor_registers = ""
        self.monitor_mem = ""
        self.memory_bytes: dict[int, int] = {}

    def selected_inferior(self) -> SimpleNamespace:
        def read_memory(addr: int, size: int) -> bytes:
            out = bytearray()
            for offset in range(size):
                byte = self.memory_bytes.get(addr + offset)
                if byte is None:
                    raise FakeGdbError(f"unmapped {addr + offset:#x}")
                out.append(byte)
            return bytes(out)

        return SimpleNamespace(read_memory=read_memory)

    # --- expression / command / symbol API -----------------------------

    def parse_and_eval(self, expr: str) -> object:
        if expr in self.values:
            return self.values[expr]
        if expr.startswith("(unsigned long)&"):
            name = expr[len("(unsigned long)&"):]
            if name in self.addresses:
                return self.addresses[name]
        raise FakeGdbError(f"cannot evaluate {expr!r}")

    def execute(self, command: str, to_string: bool = False) -> str:
        del to_string
        if command == "monitor info registers":
            return self.monitor_registers
        if command == "monitor info mem":
            return self.monitor_mem
        if command.startswith("info symbol "):
            addr = int(command.split()[-1], 16)
            name = self.symbols.get(addr)
            if name is None:
                return "No symbol matches 0x0."
            return f"{name} + 16 in section .text"
        if command.startswith("x/s "):
            addr = int(command.split()[-1], 16)
            if addr not in self.strings:
                raise FakeGdbError(f"cannot read string at {addr:#x}")
            return f'{addr:#x}: "{self.strings[addr]}"'
        raise FakeGdbError(f"unsupported command {command!r}")

    def find_pc_line(self, addr: int) -> object | None:
        info = self.lines.get(addr)
        if info is None:
            return None
        filename, line = info
        return SimpleNamespace(
            symtab=SimpleNamespace(filename=filename), line=line,
        )

    def newest_frame(self) -> FakeFrame:
        if not self.frames:
            raise FakeGdbError("no frames")
        return self.frames[0]


fake_gdb = FakeGdb()
sys.modules["gdb"] = fake_gdb

if "kernlens.gdb.facade" in sys.modules:  # pragma: no cover - rerun support
    facade = importlib.reload(sys.modules["kernlens.gdb.facade"])
else:
    from kernlens.gdb import facade  # noqa: E402


class FacadeTestBase(unittest.TestCase):
    def setUp(self) -> None:
        fake_gdb.values.clear()
        fake_gdb.addresses.clear()
        fake_gdb.symbols.clear()
        fake_gdb.lines.clear()
        fake_gdb.strings.clear()
        fake_gdb.frames.clear()
        fake_gdb.monitor_registers = ""
        fake_gdb.monitor_mem = ""
        fake_gdb.memory_bytes.clear()

        self.config = facade.DebugConfig()
        self.stream = io.StringIO()
        self.logger = Logger(color_enabled=False, stream=self.stream)
        self.styler = facade.KernelStyler(color_enabled=False)
        self.reader = facade.MemoryReader(self.config)
        self.cpu = facade.CpuInfo(self.reader)
        self.slub = facade.SlubInspector(
            self.config, self.reader, self.styler, self.logger, self.cpu,
        )

    # --- helpers --------------------------------------------------------

    def set_addr(self, name: str, value: int) -> None:
        fake_gdb.addresses[name] = value

    def set_mem(self, addr: int, value: int, type_name: str = "unsigned long") -> None:
        fake_gdb.values[f"*({type_name} *){addr:#x}"] = value

    def set_field(
        self, obj: int, type_name: str, field: str, value: int,
    ) -> None:
        # The adapter formats object addresses as hex; older tests wrote
        # them in decimal, so register both spellings.
        for address in {f"{obj}", f"{obj:#x}"}:
            fake_gdb.values[
                f"(({type_name} *){address})->{field}"
            ] = value

    def set_field_hex(
        self, obj: int, type_name: str, field: str, value: int,
    ) -> None:
        self.set_field(obj, type_name, field, value)

    def link_global(self, name: str, link: int) -> None:
        self.set_addr(name, link)


class KernelInspectorTests(FacadeTestBase):
    """The pwndbg-derived kernel metadata reader."""

    def setUp(self) -> None:
        super().setUp()
        self.inspector = facade.KernelInspector(self.reader)
        # The debug-info enum surface is stubbed by default so the page
        # type decoder has a definite encoding to work with.  ``None``
        # means "this build has no such type", which is what the real
        # GDB reports for an absent type; a test that needs a different
        # encoding overrides ``_enum_types`` and clears the cache.
        self._enum_types: dict[str, dict[str, int]] = {
            "pageflags": {"PG_locked": 0, "PG_slab": 9, "PG_head": 16},
        }
        self._install_type_lookup()

    def _install_type_lookup(self) -> None:
        """Wire the fake ``gdb.lookup_type`` to :attr:`_enum_types`."""
        def lookup_type(name: str):
            bare = name.removeprefix("enum ").strip()
            members = self._enum_types.get(bare)
            if members is None:
                raise FakeGdbError(f"No type named {name}.")

            def fields():
                return [
                    SimpleNamespace(name=member, enumval=value)
                    for member, value in members.items()
                ]

            return SimpleNamespace(code=fake_gdb.TYPE_CODE_ENUM, name=bare,
                                   fields=fields)

        fake_gdb.lookup_type = lookup_type

    def _use_enum_encoding(self) -> None:
        """Switch the fixture to the 6.12+ ``enum pagetype`` encoding."""
        self._enum_types = {
            "pageflags": {"PG_locked": 0, "PG_head": 6},
            "pagetype": {
                "PGTY_buddy": 0xF0, "PGTY_slab": 0xF5,
                "PGTY_mapcount_underflow": 0xFF,
            },
        }
        self._install_type_lookup()
        self.inspector.reset()

    def _put_string(self, addr: int, text: str) -> None:
        for index, byte in enumerate(text.encode("ascii") + b"\x00"):
            fake_gdb.memory_bytes[addr + index] = byte
        fake_gdb.strings[addr] = text

    def _put_u64(self, addr: int, value: int) -> None:
        fake_gdb.values[f"*(unsigned long *){addr:#x}"] = value
        for index, byte in enumerate(value.to_bytes(8, "little")):
            fake_gdb.memory_bytes[addr + index] = byte

    def _put_u32(self, addr: int, value: int) -> None:
        fake_gdb.values[f"*(unsigned int *){addr:#x}"] = value

    def _put_u16(self, addr: int, value: int) -> None:
        for index, byte in enumerate(value.to_bytes(2, "little")):
            fake_gdb.memory_bytes[addr + index] = byte

    @staticmethod
    def _off(type_name: str, path: str) -> int:
        """The registry (fallback) offset -- what the fake reads resolve to.

        Deriving from the registry rather than a literal keeps these
        fixtures correct when the table is re-verified against a newer
        kernel; the values themselves are pinned in ``test_layouts.py``.
        """
        value = layouts.offset(type_name, path)
        assert value is not None, f"{type_name}.{path} not in the registry"
        return value

    def test_version_reads_linux_banner(self) -> None:
        self.link_global("linux_banner", 0x1000)
        self._put_string(0x1000, REAL_BANNER)
        self.assertIn("6.1.134", self.inspector.version() or "")

    def test_modules_reads_list(self) -> None:
        # head -> node; node is struct list_head at offset 8 inside
        # struct module.  name lives at module+0x18, mem at module+0x50.
        self.link_global("modules", 0x2000)
        node = 0x3008
        obj = node - 8
        self._put_u64(0x2000, node)  # head->next
        self._put_u64(node, 0x2000)  # node->next == head (single entry)
        fake_gdb.values["(unsigned long)&((struct module *)0)->list"] = 8
        self._put_string(obj + 0x18, "nf_tables")
        fake_gdb.values["((struct module *)0x3000)->refcnt.counter"] = 3
        # MOD_MEM descriptor array at module+0x50, entry size 0x10.
        mem = (
            (0xFFFFFFFFC0000000, 0x20000),
            (0xFFFFFFFFC0020000, 0x4000),
            (0xFFFFFFFFC0024000, 0x1000),
            (0xFFFFFFFFC0025000, 0x1000),
        )
        for mem_type, (base, size) in enumerate(mem):
            ptr = obj + 0x50 + mem_type * 0x10
            self._put_u64(ptr, base)
            fake_gdb.values[f"*(unsigned int *)({ptr + 8:#x})"] = size
        modules = self.inspector.modules()
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0].name, "nf_tables")
        self.assertEqual(modules[0].address, 0xFFFFFFFFC0000000)
        self.assertEqual(modules[0].size, 0x26000)
        self.assertEqual(modules[0].used_by, 2)

    def test_modules_missing_symbol(self) -> None:
        self.assertEqual(self.inspector.modules(), ())

    def test_syscalls_reads_table(self) -> None:
        self.link_global("sys_call_table", 0x4000)
        fake_gdb.values["sizeof(sys_call_table) / sizeof(void *)"] = 2
        self._put_u64(0x4000, 0xFFFFFFFF81234560)
        self._put_u64(0x4008, 0xFFFFFFFF81234600)
        fake_gdb.symbols[0xFFFFFFFF81234560] = "__x64_sys_read"
        fake_gdb.symbols[0xFFFFFFFF81234600] = "__x64_sys_write"
        entries = self.inspector.syscalls()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].symbol, "__x64_sys_read")
        self.assertEqual(entries[0].index, 0)
        filtered = self.inspector.syscalls("write")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].symbol, "__x64_sys_write")

    def test_syscalls_missing_symbol(self) -> None:
        self.assertEqual(self.inspector.syscalls(), ())
        self.assertIsNone(self.inspector.syscall_count())

    def test_reset_clears_syscall_count(self) -> None:
        fake_gdb.values["sizeof(sys_call_table) / sizeof(void *)"] = 3
        self.assertEqual(self.inspector.syscall_count(), 3)
        self.inspector.reset()
        fake_gdb.values.pop("sizeof(sys_call_table) / sizeof(void *)")
        self.assertIsNone(self.inspector.syscall_count())

    def test_page_type_initialized(self) -> None:
        fake_gdb.values["*(unsigned int *)0x10030"] = 0xFFFFFFFF
        self.assertEqual(self.inspector.page_type(0x10000), "initialized")

    def test_page_type_mapcount(self) -> None:
        fake_gdb.values["*(unsigned int *)0x10030"] = 2
        self.assertEqual(self.inspector.page_type(0x10000), "mapcount: 2")

    def test_page_type_free_page_is_buddy(self) -> None:
        # Real value from the 6.1.134 VM: an empty page on a free list.
        # ``PG_buddy`` (0x80) is *cleared* out of the all-ones word.
        fake_gdb.values["*(unsigned int *)0x10030"] = 0xFFFFFF7F
        self.assertEqual(self.inspector.page_type(0x10000), "buddy")
        self.assertIs(self.inspector.page_is_buddy(0x10000), True)

    def test_page_type_bit_encoding_reports_the_other_types(self) -> None:
        # ``PG_offline`` (0x100) cleared; the 6.1 free-list walk found
        # nothing else, but the encoding must name it if it appears.
        for word, name in (
            (0xFFFFFEFF, "offline"),
            (0xFFFFFDFF, "table"),
            (0xFFFFFBFF, "guard"),
        ):
            fake_gdb.values["*(unsigned int *)0x10030"] = word
            self.assertEqual(
                self.inspector.page_type(0x10000), name,
                f"word {word:#x}",
            )

    def test_page_type_slab_comes_from_flags_before_6_10(self) -> None:
        # A slab page keeps ``PG_slab`` (flags bit 9) and has its type
        # word cleared, so ``page_type`` must consult flags.  The word
        # is the one measured on a real 6.1 slab page.
        fake_gdb.values["*(unsigned int *)0x10030"] = 0xFFFFFFFF
        self._put_u64(0x10000, 0xFFFFFC00000200)
        self.assertEqual(self.inspector.page_type(0x10000), "slab")
        self.assertIs(self.inspector.page_is_slab(0x10000), True)

    def test_page_type_enum_encoding_names_the_ordinal(self) -> None:
        self._use_enum_encoding()
        # ``PGTY_slab`` (0xf5) in the high byte.
        fake_gdb.values["*(unsigned int *)0x10030"] = 0xF5000000
        self.assertEqual(self.inspector.page_type(0x10000), "slab")
        self.assertIs(self.inspector.page_is_slab(0x10000), True)
        fake_gdb.values["*(unsigned int *)0x10030"] = 0xF0000000
        self.assertEqual(self.inspector.page_type(0x10000), "buddy")
        self.assertIs(self.inspector.page_is_buddy(0x10000), True)

    def test_page_type_unknown(self) -> None:
        # 0xfe is reserved for mapcount overflow, never a page type.
        fake_gdb.values["*(unsigned int *)0x10030"] = 0xFEFFFFFF
        self.assertEqual(self.inspector.page_type(0x10000), "unknown")

    def test_page_type_unreadable(self) -> None:
        self.assertEqual(self.inspector.page_type(0x10000), "?")

    def test_page_refcount(self) -> None:
        fake_gdb.values["*(unsigned int *)0x10034"] = 7
        self.assertEqual(self.inspector.page_refcount(0x10000), 7)
        fake_gdb.values["*(unsigned int *)0x10034"] = 0xFFFFFFFF
        self.assertEqual(self.inspector.page_refcount(0x10000), -1)

    def test_buddy_order_reads_private_after_the_buddy_check(self) -> None:
        # Real layout: ``private`` at 0x28, the type word at 0x30.
        fake_gdb.values["*(unsigned int *)0x10030"] = 0xFFFFFF7F
        self._put_u64(0x10028, 8)
        self.assertEqual(self.inspector.buddy_order(0x10000), 8)

    def test_buddy_order_is_none_on_a_page_that_is_not_free(self) -> None:
        # An active slab page keeps a freelist pointer in ``private``;
        # it must not be reported as an order.
        self._put_u64(0x10000, 0xFFFFFC00000200)
        self._put_u64(0x10028, 0xFFFFF14040131040)
        self.assertIsNone(self.inspector.buddy_order(0x10000))

    def test_buddy_order_rejects_an_implausible_value(self) -> None:
        fake_gdb.values["*(unsigned int *)0x10030"] = 0xFFFFFF7F
        self._put_u64(0x10028, 0x1F)
        self.assertIsNone(self.inspector.buddy_order(0x10000))

    def test_release_parses_tuple(self) -> None:
        self.link_global("linux_banner", 0x1000)
        self._put_string(0x1000, REAL_BANNER)
        self.assertEqual(self.inspector.release(), (6, 1, 134))

    def test_version_missing_symbol(self) -> None:
        self.assertIsNone(self.inspector.version())
        self.assertIsNone(self.inspector.release())

    def test_cmdline_reads_saved_command_line(self) -> None:
        self.link_global("saved_command_line", 0x2000)
        self.set_mem(0x2000, 0x3000)
        self._put_string(0x3000, "root=/dev/sda1 quiet")
        self.assertEqual(self.inspector.cmdline(), "root=/dev/sda1 quiet")

    def test_cmdline_missing_symbol(self) -> None:
        self.assertIsNone(self.inspector.cmdline())

    def test_kconfig_decompresses_ikcfg(self) -> None:
        import zlib

        plain = b"CONFIG_RANDOMIZE_BASE=y\nCONFIG_SMP=y\n"
        blob = zlib.compress(plain)
        self.link_global("kernel_config_data", 0x4000)
        self.link_global("kernel_config_data_end", 0x4000 + len(blob))
        for index, byte in enumerate(blob):
            fake_gdb.memory_bytes[0x4000 + index] = byte
        config = self.inspector.kconfig()
        self.assertEqual(config["CONFIG_RANDOMIZE_BASE"], "y")
        self.assertEqual(config["CONFIG_SMP"], "y")
        self.assertTrue(self.inspector.config_contains("RANDOMIZE_BASE"))
        self.assertFalse(self.inspector.config_contains("NOPE"))
        self.assertEqual(self.inspector.config_get("SMP"), "y")
        self.assertIsNone(self.inspector.config_get("NOPE"))

    def test_kconfig_empty_without_symbols(self) -> None:
        self.assertEqual(self.inspector.kconfig(), {})
        self.assertFalse(self.inspector.config_contains("SMP"))

    def test_config_update_merges_file(self) -> None:
        import os
        import tempfile

        handle, path = tempfile.mkstemp()
        try:
            with os.fdopen(handle, "w") as fp:
                fp.write("CONFIG_EXTRA=y\n# c\n\n")
            merged = self.inspector.config_update(path)
            self.assertEqual(merged, 1)
            self.assertEqual(self.inspector.config_get("EXTRA"), "y")
        finally:
            os.unlink(path)

    def test_reset_reloads_config(self) -> None:
        self.link_global("kernel_config_data", 0x4000)
        self.link_global("kernel_config_data_end", 0x4000)
        self.assertEqual(self.inspector.kconfig(), {})
        self.inspector.reset()
        self.assertEqual(self.inspector.kconfig(), {})

    def test_config_key(self) -> None:
        self.assertEqual(self.inspector.config_key("smp"), "CONFIG_SMP")

    # --- kallsyms -------------------------------------------------------

    def _build_kallsyms(self) -> None:
        """Lay out a compressed kallsyms table inside one 16 KiB block."""
        base = 0x5000
        for addr in range(base, base + 0x4000):
            fake_gdb.memory_bytes[addr] = 0
        # num_syms = 2 (u32 at names-4).
        for index, byte in enumerate((2).to_bytes(4, "little")):
            fake_gdb.memory_bytes[base + index] = byte
        # names: [2,0,1][2,2,3] -> token streams "T"+"foo", "t"+"bar".
        for index, byte in enumerate((2, 0, 1, 2, 2, 3)):
            fake_gdb.memory_bytes[base + 4 + index] = byte
        # token_table strings (read through x/s) and their offsets.
        fake_gdb.strings[0x6000] = "T"
        fake_gdb.strings[0x6002] = "foo"
        fake_gdb.strings[0x6006] = "t"
        fake_gdb.strings[0x6008] = "bar"
        offset = (0, 2, 6, 8, 12)
        for index in range(256):
            value = offset[min(index, len(offset) - 1)]
            fake_gdb.memory_bytes[0x6400 + index * 2] = value & 0xFF
            fake_gdb.memory_bytes[0x6400 + index * 2 + 1] = value >> 8
        # kallsyms_offsets (s32) + kallsyms_relative_base.
        for index, value in enumerate((0x100, 0x200)):
            for byte_index, byte in enumerate(value.to_bytes(4, "little")):
                fake_gdb.memory_bytes[0x7000 + index * 4 + byte_index] = byte
        base_value = 0xFFFFFFFF81000000
        for index, byte in enumerate(base_value.to_bytes(8, "little")):
            fake_gdb.memory_bytes[0x8000 + index] = byte
        self.link_global("kallsyms_num_syms", base)
        self.link_global("kallsyms_names", base + 4)
        self.link_global("kallsyms_token_table", 0x6000)
        self.link_global("kallsyms_token_index", 0x6400)
        self.link_global("kallsyms_offsets", 0x7000)
        self.link_global("kallsyms_relative_base", 0x8000)

    def test_kallsyms_decodes_table(self) -> None:
        self._build_kallsyms()
        symbols = self.inspector.kallsyms()
        self.assertEqual(len(symbols), 2)
        self.assertEqual(symbols[0].type, "T")
        self.assertEqual(symbols[0].name, "foo")
        self.assertEqual(symbols[0].address, 0xFFFFFFFF81000100)
        self.assertEqual(symbols[1].type, "t")
        self.assertEqual(symbols[1].name, "bar")
        self.assertEqual(symbols[1].address, 0xFFFFFFFF81000200)

    def test_kallsyms_is_cached(self) -> None:
        self._build_kallsyms()
        self.assertIs(self.inspector.kallsyms(), self.inspector.kallsyms())

    def test_kallsyms_missing_symbol(self) -> None:
        self.assertEqual(self.inspector.kallsyms(), ())

    def test_lookup_by_name_and_address(self) -> None:
        self._build_kallsyms()
        by_name = self.inspector.lookup("foo")
        self.assertEqual([s.name for s in by_name], ["foo"])
        by_addr = self.inspector.lookup("0xffffffff81000200")
        self.assertEqual([s.name for s in by_addr], ["bar"])
        self.assertEqual(self.inspector.lookup("nope"), ())

    def test_lookup_without_kallsyms(self) -> None:
        self.assertEqual(self.inspector.lookup("foo"), ())

    # --- dmesg ----------------------------------------------------------

    def _put_bytes(self, addr: int, data: bytes) -> None:
        for index, byte in enumerate(data):
            fake_gdb.memory_bytes[addr + index] = byte

    def test_dmesg_reads_ring(self) -> None:
        prb = 0x9000
        self.link_global("printk_rb_static", prb)
        self._put_u64(prb + 0x00, 2)       # desc_ring.count_bits -> 4 descs
        self._put_u64(prb + 0x08, 0xB000)  # desc_ring.descs
        self._put_u64(prb + 0x10, 0xC000)  # desc_ring.infos
        self._put_u64(prb + 0x18, 1)       # desc_ring.head_id
        self._put_u64(prb + 0x20, 0)       # desc_ring.tail_id
        self._put_u64(prb + 0x30, 12)      # text_data_ring.size_bits
        self._put_u64(prb + 0x38, 0xD000)  # text_data_ring.data
        # descriptor 0 (size 0x18): state_var@0, begin@8, next@0x10.
        self._put_u64(0xB000, 1 << 62)     # state_var: desc_committed
        self._put_u64(0xB000 + 0x08, 8)    # text_blk_lpos.begin
        self._put_u64(0xB000 + 0x10, 24)   # text_blk_lpos.next
        # printk_info 0: seq = 7, ts_nsec = 1e9, text_len = 3.
        self._put_u64(0xC000, 7)
        self._put_u64(0xC000 + 0x08, 1_000_000_000)
        self._put_u16(0xC000 + 0x10, 3)
        self._put_bytes(0xD000 + 16, b"hi\n")  # begin(8)+ptrsize then 3 bytes
        records = self.inspector.dmesg()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].text, "hi")
        self.assertEqual(records[0].seq, 7)
        self.assertEqual(records[0].timestamp, 1.0)

    def test_dmesg_missing_symbol(self) -> None:
        self.assertEqual(self.inspector.dmesg(), ())

    def test_tk_epoch_reads_xtime_sec(self) -> None:
        self.link_global("tk_core", 0xE000)
        self._put_u64(0xE000, 1_700_000_000)
        self.assertEqual(self.inspector.tk_epoch(), 1_700_000_000)

    def test_tk_epoch_missing(self) -> None:
        self.assertIsNone(self.inspector.tk_epoch())

    # --- BPF ------------------------------------------------------------

    def _put_idr(self, name: str, idr: int, head: int) -> None:
        """Lay out a struct idr whose xa_head sits at offset 0."""
        self.link_global(name, idr)
        self._put_u64(idr, head)

    def test_bpf_progs_reads_xarray(self) -> None:
        self._put_idr("prog_idr", 0x10000, 0xFFFF888000020000)
        # xa_node: shift 0, count 1, slots[0] = bpf_prog.
        node = 0xFFFF888000020000
        prog = 0xFFFF888000030000
        fake_gdb.memory_bytes[node] = 0
        fake_gdb.memory_bytes[node + 2] = 1
        self._put_u64(
            node + self._off("struct xa_node", "slots"), prog,
        )
        self._put_u32(prog + self._off("struct bpf_prog", "type"), 1)
        self._put_u32(prog + self._off("struct bpf_prog", "len"), 2)
        self._put_u64(
            prog + self._off("struct bpf_prog", "bpf_func"),
            0xFFFFFFFF81234560,
        )
        progs = self.inspector.bpf_progs()
        self.assertEqual(len(progs), 1)
        self.assertEqual(progs[0].type, "BPF_PROG_TYPE_SOCKET_FILTER")
        self.assertEqual(progs[0].func, 0xFFFFFFFF81234560)

    def test_bpf_progs_missing_symbol(self) -> None:
        self.assertEqual(self.inspector.bpf_progs(), ())

    def test_bpf_maps_reads_xarray(self) -> None:
        self._put_idr("map_idr", 0x40000, 0xFFFF888000050000)
        fake_gdb.memory_bytes[0xFFFF888000050000] = 0
        fake_gdb.memory_bytes[0xFFFF888000050000 + 2] = 1
        self._put_u64(0xFFFF888000050000 + 40, 0xFFFF888000060000)
        base = 0xFFFF888000060000
        self._put_u32(base + self._off("struct bpf_map", "map_type"), 2)
        self._put_u32(base + self._off("struct bpf_map", "key_size"), 4)
        self._put_u32(base + self._off("struct bpf_map", "value_size"), 8)
        self._put_u32(base + self._off("struct bpf_map", "max_entries"), 4)
        maps = self.inspector.bpf_maps()
        self.assertEqual(len(maps), 1)
        self.assertEqual(maps[0].type, "BPF_MAP_TYPE_ARRAY")
        self.assertEqual(maps[0].key_size, 4)
        self.assertEqual(maps[0].value_size, 8)

    def test_bpf_maps_missing_symbol(self) -> None:
        self.assertEqual(self.inspector.bpf_maps(), ())

    def test_bpf_map_value_reads_bytes(self) -> None:
        self._put_bytes(0x70000, b"\x01\x02\x03\x04")
        self.assertEqual(
            self.inspector.bpf_map_value(0x70000, 4), b"\x01\x02\x03\x04",
        )
        self.assertIsNone(self.inspector.bpf_map_value(0x70000, 0))

    # --- buddy allocator -------------------------------------------------

    def test_buddy_zones_walks_freelist(self) -> None:
        self.link_global("node_data", 0x80000)
        self._put_u64(0x80000, 0xFFFFEA0000000000)   # zero page ptr
        # offsetof(page, lru) recovered from zero page's next link.
        self._put_u64(0xFFFFEA0000000000 + 8, 0xFFFFEA0000000000 + 8)
        # zone 0, free_area[0].free_list[0] -> &page0.lru.
        zone = 0x80000
        list_head = zone + 0x100
        page0 = 0xFFFFEA0000000040
        self._put_u64(list_head, page0 + 8)
        self._put_u64(page0 + 8, list_head)
        pages = self.inspector.buddy_zones(page_size=64)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].page, page0)
        self.assertEqual(pages[0].phys, 0x1000)

    def test_buddy_zones_missing_symbol(self) -> None:
        self.assertEqual(self.inspector.buddy_zones(), ())

    # --- SLUB caches ----------------------------------------------------

    def _put_slab_cache(self, node: int) -> None:
        """Lay out a single-entry slab_caches list whose object is *node*.

        The layout uses the inspectors' verified fallback offsets, which
        apply when the loaded objfile has no ``struct kmem_cache`` DWARF.
        """
        list_off = self._off("struct kmem_cache", "list")
        obj = node - list_off
        self._put_u64(0xFFFF888000050000, node)   # head->next
        self._put_u64(node, 0xFFFF888000050000)   # node->next == head
        self._put_u32(obj + self._off("struct kmem_cache", "size"), 0x400)
        self._put_u32(
            obj + self._off("struct kmem_cache", "object_size"), 0x400,
        )
        # oo: order 0, 8 objects (low 16 bits).
        self._put_u32(obj + self._off("struct kmem_cache", "oo"), 8)
        fake_gdb.strings[0xFFFF888000070000] = "kmalloc-1k"
        self._put_u64(
            obj + self._off("struct kmem_cache", "name"),
            0xFFFF888000070000,
        )

    def test_slab_caches_reads_list(self) -> None:
        self.link_global("slab_caches", 0xFFFF888000050000)
        node = 0xFFFF888000060000 + self._off("struct kmem_cache", "list")
        self._put_slab_cache(node)
        caches = self.inspector.slab_caches()
        self.assertEqual(len(caches), 1)
        self.assertEqual(caches[0].name, "kmalloc-1k")
        self.assertEqual(caches[0].size, 0x400)
        self.assertEqual(caches[0].oo_objects, 8)

    def test_slab_caches_missing_symbol(self) -> None:
        self.assertEqual(self.inspector.slab_caches(), ())

    def test_slab_cache_by_name(self) -> None:
        self.link_global("slab_caches", 0xFFFF888000050000)
        node = 0xFFFF888000060000 + self._off("struct kmem_cache", "list")
        self._put_slab_cache(node)
        self.assertIsNotNone(self.inspector.slab_cache("kmalloc-1k"))
        self.assertIsNone(self.inspector.slab_cache("nope"))

    def test_slab_cache_summary_filter(self) -> None:
        self.link_global("slab_caches", 0xFFFF888000050000)
        node = 0xFFFF888000060000 + self._off("struct kmem_cache", "list")
        self._put_slab_cache(node)
        self.assertEqual(len(self.inspector.slab_cache_summary("kmalloc")), 1)
        self.assertEqual(len(self.inspector.slab_cache_summary("nope")), 0)

    def test_slab_cache_uses_dwarf_offsets_when_available(self) -> None:
        """The loaded debug info wins over the built-in fallback layout."""
        for path, offset in (
            ("list", 0x40), ("name", 0x58), ("size", 0x30),
            ("object_size", 0x28), ("oo", 0x38),
        ):
            fake_gdb.values[
                f"(unsigned long)&((struct kmem_cache *)0)->{path}"
            ] = offset
        self.link_global("slab_caches", 0xFFFF888000050000)
        # The object starts 0x40 into the node (offsetof(list) == 0x40).
        node = 0xFFFF888000060040
        obj = node - 0x40
        self._put_u64(0xFFFF888000050000, node)
        self._put_u64(node, 0xFFFF888000050000)
        self._put_u32(obj + 0x30, 0x800)
        self._put_u32(obj + 0x38, 0x000A)
        fake_gdb.strings[0xFFFF888000070000] = "dwarf-cache"
        self._put_u64(obj + 0x58, 0xFFFF888000070000)
        caches = self.inspector.slab_caches()
        self.assertEqual(len(caches), 1)
        self.assertEqual(caches[0].name, "dwarf-cache")
        self.assertEqual(caches[0].size, 0x800)

    def test_slab_object_maps_address(self) -> None:
        # virt 0xFFFF888000003000 -> phys 0x3000 -> page 0xc0 into vmemmap.
        page = 0xFFFFEA0000000000 + (0x3000 >> 12) * 64
        cache = 0xFFFF888000090000
        fake_gdb.values[f"((struct slab *){page})->slab_cache"] = cache
        self._put_u32(cache + self._off("struct kmem_cache", "size"), 0x400)
        self._put_u32(
            cache + self._off("struct kmem_cache", "object_size"), 0x400,
        )
        fake_gdb.strings[0xFFFF888000091000] = "kmalloc-1k"
        self._put_u64(
            cache + self._off("struct kmem_cache", "name"),
            0xFFFF888000091000,
        )
        result = self.inspector.slab_object(0xFFFF888000003000)
        self.assertIsNotNone(result)
        obj, found = result  # type: ignore[misc]
        self.assertEqual(found.name, "kmalloc-1k")
        self.assertEqual(obj, 0xFFFF888000003000)

    def test_slab_object_rejects_user_address(self) -> None:
        self.assertIsNone(self.inspector.slab_object(0x1000))

    # --- dma-buf --------------------------------------------------------

    def test_dmabufs_reads_list(self) -> None:
        self.link_global("debugfs_list", 0xFFFF888000100000)
        base = 0xFFFF888001000000
        list_node = self._off("struct dma_buf", "list_node")
        first = base + list_node
        self._put_u64(0xFFFF888000100000, first)
        self._put_u64(first, 0xFFFF888000100000)   # node->next == head
        self._put_u64(base + self._off("struct dma_buf", "size"), 0x1000)
        self._put_u64(base + self._off("struct dma_buf", "file"),
                      0xFFFF888001100000)
        fake_gdb.strings[0xFFFF888001200000] = "system"
        self._put_u64(base + self._off("struct dma_buf", "exp_name"),
                      0xFFFF888001200000)
        bufs = self.inspector.dmabufs()
        self.assertEqual(len(bufs), 1)
        self.assertEqual(bufs[0].exporter, "system")
        self.assertEqual(bufs[0].size, 0x1000)
        self.assertEqual(bufs[0].address, base)

    def test_dmabufs_missing_symbol(self) -> None:
        self.assertEqual(self.inspector.dmabufs(), ())


class MemoryReaderTests(FacadeTestBase):
    def test_u64(self) -> None:
        fake_gdb.values["(unsigned long)$rax"] = 0x1234
        self.assertEqual(self.reader.u64("(unsigned long)$rax"), 0x1234)
        self.assertIsNone(self.reader.u64("missing"))
        fake_gdb.values["(unsigned long)$bad"] = BadIntValue()
        self.assertIsNone(self.reader.u64("(unsigned long)$bad"))

    def test_read_kvar_and_addr(self) -> None:
        self.config.kaslr_offset = 0x1000
        link = 0xFFFF888000000000
        self.link_global("jiffies", link)
        self.set_mem(link + 0x1000, 0x42)
        self.assertEqual(self.reader.read_kvar("jiffies"), 0x42)
        self.assertEqual(
            self.reader.kvar_addr("jiffies"), link + 0x1000,
        )

    def test_read_kvar_missing(self) -> None:
        self.assertIsNone(self.reader.read_kvar("nope"))
        self.assertIsNone(self.reader.kvar_addr("nope"))
        self.link_global("zero", 0)
        self.assertIsNone(self.reader.read_kvar("zero"))
        self.assertIsNone(self.reader.kvar_addr("zero"))

    def test_arg_and_read_field(self) -> None:
        fake_gdb.values["(unsigned long)$rdi"] = 7
        self.assertEqual(self.reader.arg("missing", "rdi"), 7)
        self.assertIsNone(self.reader.arg("missing", "rsi"))

        fake_gdb.values["((struct task_struct *)4096)->pid"] = 0x1234
        self.assertEqual(
            self.reader.read_field(0x1000, "struct task_struct", "pid"),
            0x1234,
        )
        self.assertIsNone(
            self.reader.read_field(0, "struct task_struct", "pid"),
        )


class FieldValueTests(FacadeTestBase):
    """``field_value`` must not assume the field is an integer.

    ``read_field`` coerces with ``int()``, so on a live 6.1.134 kernel
    ``task_struct::comm`` -- a ``char[16]`` holding ``"swapper/0"`` --
    printed ``<unreadable>`` while GDB itself read the string fine.  The
    integer path could not distinguish "not a scalar" from "unmapped",
    and the command showed both as the same error.  These pin the four
    kinds separately, because a single "it works now" test would have
    passed for the integer case that already worked.
    """

    BASE = 0x2000
    TYPE = "struct task_struct"

    def _value(self, path: str, value: object) -> None:
        key = f"(({self.TYPE} *){self.BASE})->{path}"
        fake_gdb.values[key] = value

    def test_a_scalar_keeps_its_integer(self) -> None:
        self._value("pid", FakeValue(
            FakeType(fake_gdb.TYPE_CODE_INT, "pid_t", 4), 0,
        ))
        found = self.reader.field_value(self.BASE, self.TYPE, "pid")
        assert found is not None
        self.assertEqual(found.integer, 0)
        self.assertEqual(found.text, "0x0")
        self.assertEqual(found.type_name, "pid_t")
        self.assertIsNone(found.string)

    def test_a_null_pointer_is_an_address_not_a_failure(self) -> None:
        # `->mm` is 0 on the idle task.  Reporting <unreadable> for a
        # perfectly readable NULL is the kind of wrong answer that makes
        # a reader distrust every other value on the line.
        self._value("mm", FakeValue(
            FakeType(fake_gdb.TYPE_CODE_PTR, "struct mm_struct *", 8),
            None,
            address=0,
        ))
        found = self.reader.field_value(self.BASE, self.TYPE, "mm")
        assert found is not None
        self.assertTrue(found.is_pointer)
        self.assertEqual(found.type_name, "struct mm_struct *")

    def test_a_char_array_becomes_its_string(self) -> None:
        address = 0x8000
        for offset, byte in enumerate(b"swapper/0\x00\x00\x00\x00\x00\x00\x00"):
            fake_gdb.memory_bytes[address + offset] = byte
        self._value("comm", FakeValue(
            FakeType(
                fake_gdb.TYPE_CODE_ARRAY, "char [16]", 16,
                target=FakeType(fake_gdb.TYPE_CODE_INT, "char", 1),
            ),
            "swapper/0",
            address=address,
        ))
        found = self.reader.field_value(self.BASE, self.TYPE, "comm")
        assert found is not None
        self.assertEqual(found.string, "swapper/0")
        self.assertEqual(found.text, "swapper/0")
        self.assertEqual(found.length, 16)
        self.assertEqual(found.type_name, "char [16]")

    def test_a_non_char_array_is_not_text(self) -> None:
        # A `struct list_head[4]` has a STRUCT element, so decoding it as
        # a string would invent text out of pointers.  Only a one-byte
        # integer element can be text.
        self._value("children", FakeValue(
            FakeType(
                fake_gdb.TYPE_CODE_ARRAY, "struct list_head [4]", 64,
                target=FakeType(fake_gdb.TYPE_CODE_STRUCT, "struct list_head", 16),
            ),
            "[4]",
        ))
        found = self.reader.field_value(self.BASE, self.TYPE, "children")
        assert found is not None
        self.assertIsNone(found.string)
        self.assertEqual(found.length, 4)
        self.assertIn("4 element", found.text or "")

    def test_a_struct_field_keeps_gdbs_rendering(self) -> None:
        # `kuid_t` is `struct {uid_t val;}` -- GDB renders it, and the
        # command shows that text rather than pretending it is an int.
        self._value("cred.uid", FakeValue(
            FakeType(fake_gdb.TYPE_CODE_STRUCT, "kuid_t", 4), "{val = 0}",
        ))
        found = self.reader.field_value(self.BASE, self.TYPE, "cred.uid")
        assert found is not None
        self.assertEqual(found.type_name, "kuid_t")
        self.assertEqual(found.text, "{val = 0}")
        self.assertIsNone(found.integer)
        self.assertIsNone(found.string)

    def test_a_missing_field_is_the_only_none(self) -> None:
        self.assertIsNone(self.reader.field_value(self.BASE, self.TYPE, "nope"))
        self.assertIsNone(self.reader.field_value(0, self.TYPE, "pid"))


class SymbolResolverTests(FacadeTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.symbols = facade.SymbolResolver(
            self.config, self.styler, self.logger,
        )

    def test_sym(self) -> None:
        fake_gdb.symbols[0x1000] = "foo"
        self.assertEqual(self.symbols.sym(0x1000), "foo")
        self.assertEqual(self.symbols.sym(0x2000), "?")
        self.assertEqual(self.symbols.sym(0), "?")

    def test_sym_kaslr_fallback(self) -> None:
        self.config.kaslr_offset = 0x100
        fake_gdb.symbols[0x0F00] = "bar"
        self.assertEqual(self.symbols.sym(0x1000), "bar")

    def test_line(self) -> None:
        fake_gdb.lines[0x0F00] = ("kernel/slub.c", 42)
        self.config.kaslr_offset = 0x100
        self.assertEqual(
            self.symbols.line(0x1000), "kernel/slub.c:42",
        )
        self.assertEqual(self.symbols.line(0x2000), "??")

    def test_backtrace_and_chain(self) -> None:
        fake_gdb.symbols[0x1000] = "foo"
        fake_gdb.symbols[0x2000] = "bar"
        fake_gdb.lines[0x1000] = ("a.c", 1)
        fake_gdb.lines[0x2000] = ("b.c", 2)
        fake_gdb.frames = [
            FakeFrame(0x1000, FakeFrame(0x2000)),
        ]
        self.symbols.backtrace(2)
        out = self.stream.getvalue()
        self.assertIn("bt:", out)
        self.assertIn("#0", out)
        self.assertIn("foo", out)
        self.assertIn("at a.c:1", out)
        self.assertIn("bar", out)
        self.assertIn("at b.c:2", out)

        self.assertEqual(self.symbols.chain(2), "foo <- bar")
        self.assertEqual(
            self.symbols.color_chain("foo <- bar"), "foo <- bar",
        )
        self.assertEqual(self.symbols.color_chain("?"), "?")

    def test_backtrace_unknown_symbol(self) -> None:
        fake_gdb.frames = [FakeFrame(0x3000)]
        self.symbols.backtrace(1)
        self.assertIn("??", self.stream.getvalue())

    def test_backtrace_stops_at_oldest_frame(self) -> None:
        fake_gdb.symbols[0x1000] = "foo"
        fake_gdb.frames = [EndingFrame(0x1000)]
        self.symbols.backtrace(4)
        self.assertIn("foo", self.stream.getvalue())
        self.assertEqual(self.symbols.chain(4), "foo")


class KaslrTests(FacadeTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.kaslr = facade.Kaslr(self.config, self.reader)

    def test_bp_spec_without_slide(self) -> None:
        self.assertEqual(self.kaslr.bp_spec("__slab_free"), "__slab_free")

    def test_bp_spec_with_slide(self) -> None:
        self.config.kaslr_offset = 0x1000
        self.link_global("__slab_free", 0xFFFF888000001000)
        self.assertEqual(
            self.kaslr.bp_spec("__slab_free"), "*0xffff888000002000",
        )

    def test_bp_spec_unknown_symbol(self) -> None:
        self.config.kaslr_offset = 0x1000
        self.assertEqual(self.kaslr.bp_spec("missing"), "missing")

    def test_link_text(self) -> None:
        fake_gdb.values["(unsigned long)&_text"] = 0xFFFFFFFF81000000
        self.assertEqual(self.kaslr.link_text(), 0xFFFFFFFF81000000)


class CpuInfoTests(FacadeTestBase):
    def test_nr_cpus_and_nodes(self) -> None:
        self.link_global("nr_cpu_ids", 0xFFFF888000001000)
        self.set_mem(0xFFFF888000001000, 4, "int")
        self.assertEqual(self.cpu.nr_cpus(), 4)

        self.link_global("nr_node_ids", 0xFFFF888000001008)
        self.set_mem(0xFFFF888000001008, 2, "int")
        self.assertEqual(self.cpu.nr_nodes(), 2)

    def test_nr_nodes_default(self) -> None:
        self.assertEqual(self.cpu.nr_nodes(), 1)

    def test_cpu_online(self) -> None:
        mask = 0xFFFF888000001000
        self.link_global("__cpu_online_mask", mask)
        self.set_field_hex(mask, "struct cpumask", "bits[0]", 1 << 2)
        self.assertTrue(self.cpu.cpu_online(2))
        self.assertFalse(self.cpu.cpu_online(3))
        self.assertIsNone(self.cpu.cpu_online(None))
        self.assertIsNone(self.cpu.cpu_online(-1))

    def test_percpu_off(self) -> None:
        link = 0xFFFF888000001000
        self.link_global("__per_cpu_offset", link)
        self.set_mem(link, 0x100000)
        self.set_mem(link + 8, 0x200000)
        self.assertEqual(self.cpu.percpu_off(0), 0x100000)
        self.assertEqual(self.cpu.percpu_off(1), 0x200000)

    def test_cur_cpu(self) -> None:
        # Modern kernels (>= 6.0) expose the per-CPU ``cpu_number`` directly;
        # ``cur_cpu`` resolves it through ``pcpu_hot.cpu_number`` when that
        # member exists, and through the bare ``cpu_number`` symbol otherwise.
        gs_base = 0xFFFF888000000000
        percpu_start = 0xFFFF888000010000
        fake_gdb.values["$gs_base"] = gs_base
        self.link_global("__per_cpu_start", percpu_start)
        self.link_global("pcpu_hot.cpu_number", percpu_start + 0x20)
        fake_gdb.values[f"*(int *)({gs_base + 0x20:#x})"] = 3
        self.assertEqual(self.cpu.cur_cpu(), 3)

    def test_cur_cpu_prefers_the_modern_member(self) -> None:
        gs_base = 0xFFFF888000000000
        percpu_start = 0xFFFF888000010000
        fake_gdb.values["$gs_base"] = gs_base
        self.link_global("__per_cpu_start", percpu_start)
        self.link_global("pcpu_hot.cpu_number", percpu_start + 0x20)
        self.link_global("cpu_number", percpu_start + 0x20)
        # Value only planted for the bare symbol offset; both names map to
        # the same offset, so the resolved CPU id must be the same.
        fake_gdb.values[f"*(int *)({gs_base + 0x20:#x})"] = 1
        self.assertEqual(self.cpu.cur_cpu(), 1)

    def test_cur_cpu_with_a_zero_based_per_cpu_start(self) -> None:
        # Real x86_64 kernels place __per_cpu_start at a genuine 0, so a
        # symbol's per-CPU offset equals its bare symbol address.  A zero
        # base must not be mistaken for "symbol not found": the CPU number
        # is simply read at ``$gs_base + cpu_number``.  Reproduces the real
        # 6.1.134 layout (cpu_number at link 0x199e0) where the previous
        # code bailed out and every reader-reported CPU was "?".
        gs_base = 0xFFFF932AC7A00000
        cpu_number = 0x199E0
        fake_gdb.values["$gs_base"] = gs_base
        self.link_global("__per_cpu_start", 0)
        self.link_global("cpu_number", cpu_number)
        fake_gdb.values[f"*(int *)({gs_base + cpu_number:#x})"] = 2
        self.assertEqual(self.cpu.cur_cpu(), 2)

    def test_cur_cpu_masks_a_negative_gs_base(self) -> None:
        # GDB reports $gs_base (a high kernel address) as a negative Python
        # int on this host; it must be masked to 64 bits before it is used
        # as an address or the read lands nowhere.
        gs_base = 0xFFFF932AC7A00000
        fake_gdb.values["$gs_base"] = -((1 << 64) - gs_base)
        self.link_global("__per_cpu_start", 0)
        self.link_global("cpu_number", 0x199E0)
        fake_gdb.values[f"*(int *)({gs_base + 0x199E0:#x})"] = 1
        self.assertEqual(self.cpu.cur_cpu(), 1)

    def test_cur_cpu_failure(self) -> None:
        self.assertIsNone(self.cpu.cur_cpu())
        fake_gdb.values["$gs_base"] = 0
        self.assertIsNone(self.cpu.cur_cpu())
        fake_gdb.values["$gs_base"] = BadIntValue()
        self.assertIsNone(self.cpu.cur_cpu())

    def test_percpu_start_reports_a_genuine_zero(self) -> None:
        self.assertIsNone(self.cpu.percpu_start())      # symbol not loaded
        self.link_global("__per_cpu_start", 0)
        self.assertEqual(self.cpu.percpu_start(), 0)


class SlubPageTests(FacadeTestBase):
    def test_page_bytes(self) -> None:
        fake_gdb.values["(unsigned long)sizeof(struct page)"] = 64
        self.assertEqual(self.slub.page_bytes(), 64)
        fake_gdb.values.clear()
        self.assertEqual(self.slub.page_bytes(), 64)

    def test_head_to_page(self) -> None:
        page_offset_base = 0xFFFF888000000000
        vmemmap_base = 0xFFFFEA0000000000
        self.link_global("page_offset_base", 0xFFFF888000100000)
        self.set_mem(0xFFFF888000100000, page_offset_base)
        self.link_global("vmemmap_base", 0xFFFF888000100008)
        self.set_mem(0xFFFF888000100008, vmemmap_base)
        fake_gdb.values["(unsigned long)sizeof(struct page)"] = 64

        self.assertEqual(
            self.slub.head_to_page(0xFFFF888000001000),
            0xFFFFEA0000000040,
        )
        self.assertIsNone(self.slub.head_to_page(0))
        # vmalloc/user addresses are not in the direct map and must not
        # underflow into a huge bogus pfn.
        self.assertIsNone(self.slub.head_to_page(0xFFFFC90000001000))
        self.assertIsNone(self.slub.head_to_page(0x1000))

    def test_compound_head(self) -> None:
        page = 0xFFFFEA0000000040
        self.set_field(page, "struct page", "compound_head", 0x5001)
        self.assertEqual(self.slub.compound_head(page), 0x5000)
        self.set_field(page, "struct page", "compound_head", 0)
        self.assertEqual(self.slub.compound_head(page), page)
        self.assertEqual(self.slub.compound_head(0), 0)

    def test_cache_name(self) -> None:
        cache = 0x1000
        name_ptr = 0x2000
        self.set_field(cache, "struct kmem_cache", "name", name_ptr)
        fake_gdb.strings[name_ptr] = "kmalloc-1k"
        self.assertEqual(self.slub.cache_name(cache), "kmalloc-1k")
        self.assertEqual(self.slub.cache_name(0), "?")
        self.assertEqual(self.slub.cache_name(0x3000), "?")


class SlubFreelistTests(FacadeTestBase):
    def test_cpu_slab_and_freelist(self) -> None:
        cache = 0x1000
        template = 0x2000
        percpu = 0x100000
        cpu_slab = template + percpu
        self.set_field(cache, "struct kmem_cache", "cpu_slab", template)
        self.link_global("__per_cpu_offset", 0x3000)
        self.set_mem(0x3000, percpu)
        self.set_field(cpu_slab, "struct kmem_cache_cpu", "slab", 0x4000)
        self.set_field(cpu_slab, "struct kmem_cache_cpu", "freelist", 0x5000)

        self.assertEqual(self.slub.cpu_slab_ptr(cache), template)
        self.assertEqual(self.slub.cpu_active_slab(cache, 0), 0x4000)
        self.assertEqual(self.slub.cpu_freelist(cache, 0), 0x5000)
        self.assertIsNone(self.slub.cpu_active_slab(0, 0))
        self.assertIsNone(self.slub.cpu_freelist(0, 0))

    def test_freeptr_offset_zero_is_valid(self) -> None:
        cache = 0x1000
        self.set_field(cache, "struct kmem_cache", "offset", 0)
        self.assertEqual(self.slub.freeptr_offset(cache), 0)

        self.set_field(cache, "struct kmem_cache", "offset", 16)
        self.assertEqual(self.slub.freeptr_offset(cache), 16)

        # Clearly outside any real object slot, unlike the old 1 MiB
        # sample, which can be a valid offset for a large cache.
        self.set_field(cache, "struct kmem_cache", "offset", 0xFFFFFFFF)
        self.assertIsNone(self.slub.freeptr_offset(cache))
        self.assertIsNone(self.slub.freeptr_offset(0))

        # A large cache may legitimately place the freeptr past 1 MiB.
        self.set_field(cache, "struct kmem_cache", "size", 2 << 20)
        self.set_field(cache, "struct kmem_cache", "offset", 1 << 20)
        self.assertEqual(self.slub.freeptr_offset(cache), 1 << 20)
        self.set_field(cache, "struct kmem_cache", "offset", (2 << 20) + 8)
        self.assertIsNone(self.slub.freeptr_offset(cache))

    def test_freeptr_random(self) -> None:
        cache = 0x1000
        self.set_field(cache, "struct kmem_cache", "random", 0xABCD)
        self.assertEqual(self.slub.freeptr_random(cache), 0xABCD)
        self.assertIsNone(self.slub.freeptr_random(0x2000))

    def test_decode_freeptr(self) -> None:
        raw = 0x1234567890ABCDEF
        random = 0xDEADBEEF
        ptr_addr = 0xFFFF888000001010
        swab = int.from_bytes(ptr_addr.to_bytes(8, "little"), "big")
        expected = (raw ^ random ^ swab) & 0xFFFFFFFFFFFFFFFF
        self.assertEqual(
            self.slub.decode_freeptr(raw, random, ptr_addr),
            expected,
        )
        self.assertEqual(
            self.slub.decode_freeptr(raw, None, ptr_addr), raw,
        )

    def test_freelist_dist(self) -> None:
        cache = 0x1000
        head = 0xFFFF888000001000
        first = 0xFFFF888000002000
        second = 0xFFFF888000003000
        self.set_field(cache, "struct kmem_cache", "offset", 0)
        self.set_mem(head, first)
        self.set_mem(first, second)
        self.set_mem(second, 0)

        self.assertEqual(self.slub.freelist_dist(cache, head, head), 0)
        self.assertEqual(self.slub.freelist_dist(cache, second, head), 2)
        self.assertEqual(
            self.slub.freelist_dist(cache, 0xDEAD, head), -1,
        )
        self.assertEqual(self.slub.freelist_dist(cache, head, 0), -1)


class SlubPartialTests(FacadeTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.cache = 0x1000
        self.node = 0x2000
        self.partial_off = 0x10
        self.slab_list_off = 0x8
        self.head_list = self.node + self.partial_off
        self.slab_page = 0x3000
        self.slab_list = self.slab_page + self.slab_list_off

        self.set_field(self.cache, "struct kmem_cache", "node[0]", self.node)
        fake_gdb.values[
            "(unsigned long)&((struct kmem_cache_node *)0)->partial"
        ] = self.partial_off
        fake_gdb.values[
            "(unsigned long)&((struct slab *)0)->slab_list"
        ] = self.slab_list_off
        self.set_field_hex(
            self.head_list, "struct list_head", "next", self.slab_list,
        )
        self.set_field_hex(
            self.slab_list, "struct list_head", "next", self.head_list,
        )
        self.set_field(self.slab_page, "struct slab", "freelist", 0x4000)

    def test_partial_info(self) -> None:
        self.assertEqual(
            self.slub.partial_info(self.cache, 0),
            (1, self.node, self.slab_page, 0x4000),
        )

    def test_partial_info_empty(self) -> None:
        self.set_field_hex(
            self.head_list, "struct list_head", "next", self.head_list,
        )
        self.assertEqual(
            self.slub.partial_info(self.cache, 0),
            (0, self.node, None, None),
        )
        self.assertEqual(
            self.slub.partial_info(0, 0), (0, None, None, None),
        )

    def test_partial_cycle_is_bounded(self) -> None:
        self.set_field_hex(
            self.slab_list, "struct list_head", "next", self.slab_list,
        )
        self.assertEqual(
            self.slub.partial_info(self.cache, 0),
            (1, self.node, self.slab_page, 0x4000),
        )
        self.assertTrue(
            self.slub.in_partial(self.cache, self.slab_page, 0),
        )

    def test_in_partial(self) -> None:
        self.assertTrue(
            self.slub.in_partial(self.cache, self.slab_page, 0),
        )
        self.assertFalse(
            self.slub.in_partial(self.cache, 0x5000, 0),
        )
        self.assertFalse(self.slub.in_partial(0, 0, 0))


class BtfOnlySlubTests(FacadeTestBase):
    """Slab inspection on a vmlinux that has BTF but no DWARF.

    GDB 15 cannot read BTF, so no ``struct`` type is available and every
    expression the inspector would normally evaluate fails.  The demo
    image ships exactly this -- ``objcopy --strip-debug`` keeps ``.BTF``
    and the symbol table -- so the member offsets have to come from the
    loaded image instead.
    """

    #: 6.1.134 offsets, as BTF reports them (and DWARF confirms).
    OFFSETS = {
        ("struct kmem_cache", "cpu_slab"): 0x00,
        ("struct kmem_cache", "size"): 0x18,
        ("struct kmem_cache", "offset"): 0x28,
        ("struct kmem_cache", "random"): 0x30,
        ("struct kmem_cache", "name"): 0x60,
        ("struct kmem_cache", "node"): 0xD8,
        ("struct kmem_cache_cpu", "freelist"): 0x00,
        ("struct kmem_cache_cpu", "slab"): 0x10,
        ("struct slab", "slab_list"): 0x08,
        ("struct slab", "slab_cache"): 0x10,
        ("struct slab", "freelist"): 0x18,
        ("struct slab", "counters"): 0x28,
        ("struct kmem_cache_node", "partial"): 0x10,
    }

    def setUp(self) -> None:
        super().setUp()
        self.slub = facade.SlubInspector(
            self.config, self.reader, self.styler, self.logger, self.cpu,
            offset_of=lambda type_name, path: self.OFFSETS.get(
                (type_name, path),
            ),
        )
        self.cache = 0x1000

    def word(self, addr: int, value: int) -> None:
        fake_gdb.values[f"*(unsigned long *){addr:#x}"] = value

    def dword(self, addr: int, value: int) -> None:
        fake_gdb.values[f"*(unsigned int *){addr:#x}"] = value

    def test_cache_name(self) -> None:
        self.word(self.cache + 0x60, 0x2000)
        fake_gdb.strings[0x2000] = "kmalloc-1k"
        self.assertEqual(self.slub.cache_name(self.cache), "kmalloc-1k")

    def test_cpu_slab_and_freelist(self) -> None:
        template = 0x2000
        percpu = 0x100000
        self.word(self.cache, template)
        self.link_global("__per_cpu_offset", 0x3000)
        self.word(0x3000, percpu)
        cpu_slab = template + percpu
        self.word(cpu_slab + 0x10, 0x4000)
        self.word(cpu_slab, 0x5000)
        self.assertEqual(self.slub.cpu_slab_ptr(self.cache), template)
        self.assertEqual(self.slub.cpu_active_slab(self.cache, 0), 0x4000)
        self.assertEqual(self.slub.cpu_freelist(self.cache, 0), 0x5000)

    def test_freeptr_offset_and_random(self) -> None:
        self.dword(self.cache + 0x18, 0x400)
        self.dword(self.cache + 0x28, 0x200)
        self.dword(self.cache + 0x30, 0xABCD)
        self.assertEqual(self.slub.freeptr_offset(self.cache), 0x200)
        self.assertEqual(self.slub.freeptr_random(self.cache), 0xABCD)

    def test_partial_list(self) -> None:
        node = 0x2000
        slab_page = 0x3000
        self.word(self.cache + 0xD8, node)
        head = node + 0x10
        self.word(head, slab_page + 0x08)
        self.word(slab_page + 0x08, head)
        self.word(slab_page + 0x18, 0x4000)
        self.assertEqual(
            self.slub.partial_info(self.cache, 0),
            (1, node, slab_page, 0x4000),
        )
        self.assertTrue(self.slub.in_partial(self.cache, slab_page, 0))
        self.assertFalse(self.slub.in_partial(self.cache, 0x9000, 0))

    def test_slab_counters(self) -> None:
        self.dword(0x3000 + 0x28, 3 | (16 << 16))
        self.assertEqual(self.slub.slab_counters(0x3000), (3, 16, 0))


class SlubPrintTests(FacadeTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.page_offset_base = 0xFFFF888000000000
        self.vmemmap_base = 0xFFFFEA0000000000
        self.link_global("page_offset_base", 0xFFFF888000100000)
        self.set_mem(0xFFFF888000100000, self.page_offset_base)
        self.link_global("vmemmap_base", 0xFFFF888000100008)
        self.set_mem(0xFFFF888000100008, self.vmemmap_base)

        self.head = 0xFFFF888000001000
        self.page = 0xFFFFEA0000000040
        self.cache = 0xFFFF888000002000
        self.name_ptr = 0xFFFF888000003000

        fake_gdb.values["(unsigned long)sizeof(struct page)"] = 64
        self.set_field(self.page, "struct page", "compound_head", 0)
        self.set_field(self.page, "struct slab", "slab_cache", self.cache)
        # SLUB packs inuse:16 | objects:15 | frozen:1.  Keep the sample
        # internally consistent: 3 objects in use out of 8.
        self.set_field(
            self.page, "struct slab", "counters", (8 << 16) | 3,
        )
        self.set_field(self.page, "struct slab", "freelist", 0)
        self.set_field(self.cache, "struct kmem_cache", "name", self.name_ptr)
        fake_gdb.strings[self.name_ptr] = "kmalloc-1k"

        self.link_global("nr_cpu_ids", 0xFFFF888000100010)
        self.set_mem(0xFFFF888000100010, 0, "int")
        self.set_field(
            self.cache, "struct kmem_cache", "node[0]", 0,
        )

    def test_print_slab_full(self) -> None:
        self.slub.print_slab(self.head)
        out = self.stream.getvalue()
        self.assertIn("slab:", out)
        self.assertIn("cache=kmalloc-1k", out)
        self.assertIn("inuse=3", out)
        self.assertIn("frozen=0", out)
        self.assertIn("slab->freelist", out)
        self.assertIn("head(H)", out)
        self.assertIn("node0", out)

    def test_print_slab_zero(self) -> None:
        self.slub.print_slab(0)
        self.assertIn("<head=0>", self.stream.getvalue())

    def test_print_slab_untranslatable(self) -> None:
        fake_gdb.values.clear()
        self.slub.print_slab(self.head)
        self.assertIn("cannot translate head", self.stream.getvalue())


class PageTableWalkerTests(FacadeTestBase):
    """Page-table walks against a synthetic in-memory table tree."""

    ROOT = 0x10000

    def setUp(self) -> None:
        super().setUp()
        self.walker = facade.PageTableWalker(self.reader)

    # --- helpers --------------------------------------------------------

    def link(self, table: int, index: int, next_table: int) -> None:
        """Point *table*[*index*] at *next_table* (present + writable)."""
        self.set_mem(table + index * 8, next_table | 0x3)

    def leaf(self, entry_addr: int, value: int) -> None:
        self.set_mem(entry_addr, value)

    def build_4level(self, va: int) -> None:
        self.link(self.ROOT, KPageTable.pgd_index(va), 0x20000)
        self.link(0x20000, KPageTable.pud_index(va), 0x30000)
        self.link(0x30000, KPageTable.pmd_index(va), 0x40000)

    # --- 4-level --------------------------------------------------------

    def test_walk_4k_leaf(self) -> None:
        va = 0xFFFF888000001234
        self.build_4level(va)
        self.leaf(0x40000 + KPageTable.pte_index(va) * 8, 0x500067)

        walk = self.walker.walk(va, five_level=False, root=self.ROOT)

        self.assertTrue(walk.ok)
        self.assertEqual(walk.va, va)
        self.assertEqual(walk.root, self.ROOT)
        self.assertFalse(walk.five_level)
        self.assertEqual(walk.phys, 0x500234)
        self.assertEqual(walk.page_size, 0x1000)
        self.assertIsNone(walk.note)
        self.assertEqual(
            [level.name for level in walk.levels],
            ["pgd", "pud", "pmd", "pte"],
        )
        self.assertEqual(
            [level.index for level in walk.levels],
            [
                KPageTable.pgd_index(va),
                KPageTable.pud_index(va),
                KPageTable.pmd_index(va),
                KPageTable.pte_index(va),
            ],
        )
        self.assertEqual(walk.levels[-1].value, 0x500067)
        self.assertIsNone(walk.levels[-1].next_table)

    def test_walk_2m_huge_page(self) -> None:
        va = 0xFFFF888000201234
        self.link(self.ROOT, KPageTable.pgd_index(va), 0x20000)
        self.link(0x20000, KPageTable.pud_index(va), 0x30000)
        self.leaf(
            0x30000 + KPageTable.pmd_index(va) * 8,
            0x200000 | 0xE7,
        )

        walk = self.walker.walk(va, five_level=False, root=self.ROOT)

        self.assertTrue(walk.ok)
        self.assertEqual(walk.page_size, 1 << 21)
        self.assertEqual(walk.phys, 0x201234)
        self.assertEqual(walk.levels[-1].name, "pmd")
        self.assertTrue(walk.levels[-1].huge)

    def test_walk_1g_huge_page(self) -> None:
        va = 0xFFFF888040001234
        self.link(self.ROOT, KPageTable.pgd_index(va), 0x20000)
        self.leaf(
            0x20000 + KPageTable.pud_index(va) * 8,
            0x40000000 | 0xE7,
        )

        walk = self.walker.walk(va, five_level=False, root=self.ROOT)

        self.assertTrue(walk.ok)
        self.assertEqual(walk.page_size, 1 << 30)
        self.assertEqual(walk.phys, 0x40001234)
        self.assertEqual(walk.levels[-1].name, "pud")
        self.assertTrue(walk.levels[-1].huge)

    def test_walk_not_present(self) -> None:
        va = 0xFFFF888000001234
        self.leaf(
            self.ROOT + KPageTable.pgd_index(va) * 8, 0,
        )
        walk = self.walker.walk(va, five_level=False, root=self.ROOT)
        self.assertFalse(walk.ok)
        self.assertIsNone(walk.phys)
        self.assertEqual(len(walk.levels), 1)
        self.assertIn("not present", walk.note or "")

    def test_walk_unreadable_entry(self) -> None:
        va = 0xFFFF888000001234
        walk = self.walker.walk(va, five_level=False, root=self.ROOT)
        self.assertFalse(walk.ok)
        self.assertEqual(walk.levels, ())
        self.assertIn("unreadable", walk.note or "")

    def test_walk_entry_without_next_table(self) -> None:
        va = 0xFFFF888000001234
        self.leaf(
            self.ROOT + KPageTable.pgd_index(va) * 8, 0x1,
        )
        walk = self.walker.walk(va, five_level=False, root=self.ROOT)
        self.assertFalse(walk.ok)
        self.assertIn("no next-level table", walk.note or "")

    # --- 5-level --------------------------------------------------------

    def test_walk_5level(self) -> None:
        va = 0xFFFF800000001234
        self.link(self.ROOT, KPageTable.pgd_index(va, True), 0x20000)
        self.link(0x20000, KPageTable.p4d_index(va), 0x30000)
        self.link(0x30000, KPageTable.pud_index(va), 0x40000)
        self.link(0x40000, KPageTable.pmd_index(va), 0x50000)
        self.leaf(0x50000 + KPageTable.pte_index(va) * 8, 0x600067)

        walk = self.walker.walk(va, five_level=True, root=self.ROOT)

        self.assertTrue(walk.ok)
        self.assertEqual(walk.page_size, 0x1000)
        self.assertEqual(walk.phys, 0x600234)
        self.assertEqual(
            [level.name for level in walk.levels],
            ["pgd", "p4d", "pud", "pmd", "pte"],
        )

    def test_walk_uses_cr4_la57(self) -> None:
        va = 0xFFFF800000001234
        fake_gdb.values["$cr3"] = self.ROOT
        fake_gdb.values["$cr4"] = 1 << 12
        self.link(self.ROOT, KPageTable.pgd_index(va, True), 0x20000)
        self.link(0x20000, KPageTable.p4d_index(va), 0x30000)
        self.link(0x30000, KPageTable.pud_index(va), 0x40000)
        self.link(0x40000, KPageTable.pmd_index(va), 0x50000)
        self.leaf(0x50000 + KPageTable.pte_index(va) * 8, 0x600067)

        walk = self.walker.walk(va)

        self.assertTrue(walk.five_level)
        self.assertTrue(walk.ok)
        self.assertEqual(walk.phys, 0x600234)

    # --- roots / mode helpers -------------------------------------------

    def test_read_cr3_and_la57(self) -> None:
        fake_gdb.values["$cr3"] = self.ROOT | 0x8
        fake_gdb.values["$cr4"] = 1 << 12
        self.assertEqual(self.walker.read_cr3(), self.ROOT)
        self.assertTrue(self.walker.la57())
        fake_gdb.values["$cr3"] = BadIntValue()
        fake_gdb.values["$cr4"] = BadIntValue()
        self.assertIsNone(self.walker.read_cr3())
        self.assertIsNone(self.walker.la57())

    def test_paging_mode_unknown(self) -> None:
        self.assertIsNone(self.walker.read_cr3())
        self.assertIsNone(self.walker.la57())

    def test_root_falls_back_to_kernel_top_table(self) -> None:
        self.link_global("init_top_pgt", self.ROOT)
        self.assertEqual(self.walker.root(), self.ROOT)

    def test_root_missing(self) -> None:
        walk = self.walker.walk(0xFFFF888000001234)
        self.assertFalse(walk.ok)
        self.assertIsNone(walk.root)
        self.assertIn("cannot determine", walk.note or "")

    def test_walk_without_root(self) -> None:
        fake_gdb.values["$cr3"] = self.ROOT
        fake_gdb.values["$cr4"] = 0
        va = 0xFFFF888000001234
        self.build_4level(va)
        self.leaf(0x40000 + KPageTable.pte_index(va) * 8, 0x500067)

        walk = self.walker.walk(va)

        self.assertFalse(walk.five_level)
        self.assertEqual(walk.root, self.ROOT)
        self.assertEqual(walk.phys, 0x500234)


class KaslrAdaptationTests(FacadeTestBase):
    """The reader self-heals its KASLR slide instead of needing kl-base."""

    def test_ensure_kaslr_without_hook(self) -> None:
        self.assertEqual(self.config.kaslr_offset, 0)
        self.assertEqual(self.reader.ensure_kaslr(), 0)

    def test_ensure_kaslr_detects_once(self) -> None:
        calls = []
        self.reader.set_kaslr_hooks(
            lambda: calls.append(1) or 0x18E00000,
        )
        self.assertEqual(self.reader.ensure_kaslr(), 0x18E00000)
        self.assertEqual(self.config.kaslr_offset, 0x18E00000)
        # A second call reuses the cached slide, no further detection.
        self.assertEqual(self.reader.ensure_kaslr(), 0x18E00000)
        self.assertEqual(len(calls), 1)

    def test_ensure_kaslr_honours_manual_offset(self) -> None:
        self.config.kaslr_offset = 0x2000
        self.reader.set_kaslr_hooks(lambda: 0x18E00000)
        self.assertEqual(self.reader.ensure_kaslr(), 0x2000)

    def test_kvar_addr_uses_detected_slide(self) -> None:
        self.reader.set_kaslr_hooks(lambda: 0x1000)
        link = 0xFFFF888000000000
        self.link_global("jiffies", link)
        self.set_mem(link + 0x1000, 0x42)    # readable at link+slide
        self.assertEqual(
            self.reader.kvar_addr("jiffies"), link + 0x1000,
        )
        self.assertEqual(self.reader.read_kvar("jiffies"), 0x42)

    def test_kvar_addr_retries_on_read_failure(self) -> None:
        # First detection is stale; the read then fails and forces a
        # fresh detection, whose slide points at the live copy.
        slides = [0x1000, 0x2000]
        self.reader.set_kaslr_hooks(lambda: slides.pop(0) if slides else 0x2000)
        link = 0xFFFF888000000000
        self.link_global("jiffies", link)
        self.set_mem(link + 0x2000, 0x99)    # only the correct slide reads
        self.assertEqual(self.reader.kvar_addr("jiffies"), link + 0x2000)

    def test_kvar_addr_falls_back_to_link_time(self) -> None:
        # Detection fails (None), but GDB already carries the relocation.
        self.reader.set_kaslr_hooks(lambda: None)
        link = 0xFFFF888000001000
        self.link_global("jiffies", link)
        self.set_mem(link, 0x7)              # readable at link-time
        self.config.kaslr_offset = 0x4000    # wrong manual guess
        self.assertEqual(self.reader.kvar_addr("jiffies"), link)
        self.assertEqual(self.reader.read_kvar("jiffies"), 0x7)

    def test_detection_failure_does_not_raise(self) -> None:
        def boom() -> int | None:
            raise RuntimeError("no idt")

        self.reader.set_kaslr_hooks(boom)
        self.assertEqual(self.reader.redetect_kaslr(), 0)
        self.assertEqual(self.config.kaslr_offset, 0)

    def test_the_first_alignment_gives_up_after_three_probes(self) -> None:
        """A session where detection cannot work stops paying for it.

        The old shape retried forever: a read that failed forced another
        probe, and the probe reset the failure memory on the way out, so
        every command in a ``nokaslr`` session spent two IDT scans.  The
        attempt count is the whole point of this latch.
        """
        probes = []
        self.reader.set_kaslr_hooks(lambda: probes.append(1) or None)
        for _ in range(5):
            self.assertEqual(self.reader.ensure_kaslr(), 0)
        self.assertEqual(len(probes), 3)

    def test_a_command_after_the_first_one_probes_nothing(self) -> None:
        probes = []
        self.reader.set_kaslr_hooks(lambda: probes.append(1) or 0x9000)
        self.assertEqual(self.reader.ensure_kaslr(), 0x9000)
        for _ in range(5):
            self.assertEqual(self.reader.ensure_kaslr(), 0x9000)
        self.assertEqual(len(probes), 1)

    def test_a_failed_alignment_is_not_retried(self) -> None:
        probes = []
        self.reader.set_kaslr_hooks(lambda: probes.append(1) or None)
        self.reader.ensure_kaslr()
        self.assertEqual(len(probes), 3)
        self.reader.ensure_kaslr()
        self.assertEqual(len(probes), 3)

    def test_reopen_alignment_spends_a_fresh_set_of_probes(self) -> None:
        """``kl-base`` is the manual retry, and it can be used repeatedly."""
        probes = []
        self.reader.set_kaslr_hooks(lambda: probes.append(1) or None)
        self.reader.ensure_kaslr()
        self.assertEqual(len(probes), 3)
        self.reader.reopen_alignment()
        self.assertEqual(len(probes), 6)
        self.reader.reopen_alignment()
        self.assertEqual(len(probes), 9)

    def test_reopen_alignment_succeeds_when_detection_now_works(self) -> None:
        state = {"ok": False}

        def recover() -> int | None:
            return 0x7000 if state["ok"] else None

        self.reader.set_kaslr_hooks(recover)
        self.assertEqual(self.reader.ensure_kaslr(), 0)
        state["ok"] = True          # the user loaded the matching vmlinux
        self.assertEqual(self.reader.reopen_alignment(), 0x7000)
        self.assertEqual(self.config.kaslr_offset, 0x7000,
        )

    def test_on_change_hook_fires(self) -> None:
        events = []
        self.reader.set_kaslr_hooks(lambda: 0x5000, lambda: events.append(1))
        self.reader.ensure_kaslr()
        self.assertEqual(events, [1])
        # No change -> no event.
        self.reader.redetect_kaslr()
        self.assertEqual(events, [1])


class FacadeTests(FacadeTestBase):
    def test_bound_methods(self) -> None:
        kdbg = facade.KernelDebugger()
        self.assertEqual(kdbg.info.__self__, kdbg.logger)
        self.assertEqual(kdbg.style.__self__, kdbg.styler)
        self.assertEqual(kdbg.u64.__self__, kdbg.reader)
        self.assertEqual(kdbg.sym.__self__, kdbg.symbols)
        self.assertEqual(kdbg.print_slab.__self__, kdbg.slub)
        self.assertEqual(kdbg.walk.__self__, kdbg.walker)
        self.assertTrue(callable(kdbg.fmt_chain))

    def test_facade_exposes_the_frozen_bound_names(self) -> None:
        from contract_spec import FACADE_BOUND_NAMES

        kdbg = facade.KernelDebugger()
        missing = [name for name in FACADE_BOUND_NAMES if not hasattr(kdbg, name)]
        self.assertEqual(missing, [])

    def test_facade_exposes_the_frozen_component_instances(self) -> None:
        from contract_spec import COMPONENT_INSTANCE_NAMES

        kdbg = facade.KernelDebugger()
        for name in COMPONENT_INSTANCE_NAMES:
            with self.subTest(name=name):
                self.assertIsNotNone(getattr(kdbg, name, None))

    def test_bound_names_are_derived_from_one_table(self) -> None:
        """``api`` must derive its tables from the facade's ``_BINDINGS``."""
        from kernlens.gdb import api

        kdbg = facade.KernelDebugger()
        self.assertEqual(
            tuple(facade.BOUND_NAMES),
            tuple(name for name, _, _, _ in facade._BINDINGS),
        )
        for name in facade.BOUND_NAMES:
            with self.subTest(name=name):
                self.assertTrue(hasattr(kdbg, name))
        # ``api`` derives its tables from the facade; compare as sets so
        # the assertion is independent of import order.
        self.assertEqual(
            set(api.FACADE_FUNCTIONS), set(facade.FREE_FUNCTION_NAMES),
        )
        self.assertEqual(
            set(api.INSTANCE_NAMES), set(facade.COMPONENT_NAMES),
        )
        self.assertTrue(
            set(facade.FREE_FUNCTION_NAMES) <= set(facade.BOUND_NAMES)
        )
        self.assertEqual(
            len(facade.BOUND_NAMES), len(set(facade.BOUND_NAMES)),
            "the binding table must not repeat a public name",
        )

    def test_component_names_cover_the_composed_adapters(self) -> None:
        kdbg = facade.KernelDebugger()
        for name in facade.COMPONENT_NAMES:
            with self.subTest(name=name):
                self.assertIsNotNone(getattr(kdbg, name, None))

    def test_color_control(self) -> None:
        kdbg = facade.KernelDebugger()
        self.assertTrue(kdbg.color_enabled)
        kdbg.disable_color()
        self.assertFalse(kdbg.color_enabled)
        self.assertFalse(kdbg.logger.color_enabled)
        self.assertFalse(kdbg.styler.color_enabled)
        kdbg.enable_color()
        self.assertTrue(kdbg.color_enabled)
        kdbg.set_color_enabled(False)
        self.assertFalse(kdbg.color_enabled)
        kdbg.color_enabled = True
        self.assertTrue(kdbg.color_enabled)

    def test_kaslr_and_layout_properties(self) -> None:
        kdbg = facade.KernelDebugger()
        kdbg.kaslr_offset = 0x1000
        self.assertEqual(kdbg.kaslr_offset, 0x1000)
        self.assertEqual(kdbg.header_width, 13)
        self.assertEqual(kdbg.indent_str, " " * 13)
        self.assertEqual(kdbg.indent_nested, " " * 19)
        self.assertEqual(kdbg.indent("x"), "  x")

    def test_logging_through_facade(self) -> None:
        kdbg = facade.KernelDebugger()
        stream = io.StringIO()
        kdbg.logger.set_stream(stream)
        kdbg.disable_color()
        kdbg.info("hello")
        kdbg.warn("careful")
        self.assertEqual(
            stream.getvalue().splitlines(),
            ["[INFO]    hello", "[WARN]    careful"],
        )

    def test_singleton(self) -> None:
        self.assertIsInstance(facade.kdbg, facade.KernelDebugger)

    def test_lazy_package_exports(self) -> None:
        import kernlens.gdb as gdb_pkg

        self.assertIs(gdb_pkg.KernelDebugger, facade.KernelDebugger)
        self.assertIs(gdb_pkg.kdbg, facade.kdbg)


class KbaseTests(FacadeTestBase):
    """IDT decoding and kernel text-base recovery."""

    IDT_BASE = 0xFFFFFE0000000000
    LINK_TEXT = 0xFFFFFFFF81000000
    RUNTIME_BASE = 0xFFFFFFFF99E00000
    HANDLER = RUNTIME_BASE + 0x1234
    LINK_HANDLER = LINK_TEXT + 0x1234

    def _gate(self, handler: int) -> tuple[int, int]:
        low = handler & 0xFFFF
        low |= 0x10 << 16          # selector
        low |= 0xE << 40           # interrupt gate
        low |= 1 << 47             # present
        low |= ((handler >> 16) & 0xFFFF) << 48
        return low, (handler >> 32) & 0xFFFFFFFF

    def _install_gate(self, handler: int = HANDLER) -> None:
        low, high = self._gate(handler)
        fake_gdb.values[
            f"*(unsigned long *){self.IDT_BASE:#x}"
        ] = low
        fake_gdb.values[
            f"*(unsigned long *){self.IDT_BASE + 8:#x}"
        ] = high
        fake_gdb.monitor_registers = (
            f"IDT= {self.IDT_BASE:x} 00000fff\n"
        )

    def test_idt_entry_decode(self) -> None:
        self._install_gate()
        finder = facade.Kbase(self.config, self.reader)
        info = finder.idt()
        self.assertIsNotNone(info)
        assert info is not None
        entry = finder.entry(0, info)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.offset, self.HANDLER)
        self.assertEqual(entry.selector, 0x10)
        self.assertEqual(entry.gate_type, 0xE)
        self.assertTrue(entry.present)
        self.assertTrue(entry.is_kernel_gate)

    def test_base_from_link_symbol(self) -> None:
        self._install_gate()
        fake_gdb.addresses["_text"] = self.LINK_TEXT
        fake_gdb.addresses["asm_exc_divide_error"] = self.LINK_HANDLER
        result = facade.Kbase(self.config, self.reader).find()
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.base, self.RUNTIME_BASE)
        self.assertEqual(result.method, "symbol")
        self.assertEqual(result.handler_symbol, "asm_exc_divide_error")
        self.assertEqual(result.kaslr_offset, 0x18E00000)

    def test_base_from_qemu_mapping(self) -> None:
        self._install_gate()
        fake_gdb.monitor_mem = (
            f"{self.RUNTIME_BASE:x}-{self.RUNTIME_BASE + 0x200000:x} "
            "0000000000000000 r-x\n"
        )
        result = facade.Kbase(self.config, self.reader).find()
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.base, self.RUNTIME_BASE)
        self.assertEqual(result.method, "mapping")

    def test_base_from_alignment_fallback(self) -> None:
        self._install_gate()
        result = facade.Kbase(self.config, self.reader).find()
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.base, self.RUNTIME_BASE)
        self.assertEqual(result.method, "align")

    def test_missing_idt(self) -> None:
        finder = facade.Kbase(self.config, self.reader)
        self.assertIsNone(finder.idt())
        self.assertIsNone(finder.find())


class StructOffsetTests(FacadeTestBase):
    """Field offsets come from the loaded debug info, not hardcoded values.

    Real kernels differ in these offsets with ``CONFIG_*`` (the struct
    layouts the inspectors decode are all configuration-dependent), so
    the resolver must consult DWARF first and fall back only when the
    type is unavailable.
    """

    def setUp(self) -> None:
        super().setUp()
        self.inspector = facade.KernelInspector(self.reader)

    def test_offset_of_reads_the_debug_info(self) -> None:
        fake_gdb.values[
            "(unsigned long)&((struct kmem_cache *)0)->name"
        ] = 0x60
        self.assertEqual(
            self.inspector._offset_of("struct kmem_cache", "name"), 0x60,
        )

    def test_offset_of_returns_the_fallback_when_unavailable(self) -> None:
        self.assertEqual(
            self.inspector._offset_of("struct absent_type", "field", 0x42),
            0x42,
        )
        self.assertIsNone(
            self.inspector._offset_of("struct absent_type", "field")
        )

    def test_offset_of_is_cached(self) -> None:
        fake_gdb.values[
            "(unsigned long)&((struct kmem_cache *)0)->size"
        ] = 0x18
        first = self.inspector._offset_of("struct kmem_cache", "size")
        # A second read must not require the debug info again.
        fake_gdb.values.clear()
        self.assertEqual(
            self.inspector._offset_of("struct kmem_cache", "size"), first,
        )

    def test_sizeof_reads_the_debug_info(self) -> None:
        fake_gdb.values["sizeof(struct zone)"] = 0x600
        self.assertEqual(self.inspector._sizeof("struct zone"), 0x600)

    def test_sizeof_falls_back_when_unknown(self) -> None:
        self.assertIsNone(self.inspector._sizeof("struct absent_type"))
        self.assertEqual(
            self.inspector._sizeof("struct absent_type", 0x100), 0x100,
        )

    def test_reset_drops_the_offset_cache(self) -> None:
        fake_gdb.values[
            "(unsigned long)&((struct kmem_cache *)0)->name"
        ] = 0x60
        self.inspector._offset_of("struct kmem_cache", "name")
        self.inspector.reset()
        fake_gdb.values.clear()
        self.assertIsNone(
            self.inspector._offset_of("struct kmem_cache", "name")
        )


class LayoutFallbackTests(FacadeTestBase):
    """Without debug info, offsets fall back to the built-in registry.

    The registry values are only verified for one kernel build, so their
    use must be recorded (``layout_fallbacks``) for the command layer to
    warn about.
    """

    def setUp(self) -> None:
        super().setUp()
        self.inspector = facade.KernelInspector(self.reader)

    def test_layout_offset_uses_dwarf_when_available(self) -> None:
        fake_gdb.values[
            "(unsigned long)&((struct bpf_map *)0)->map_type"
        ] = 0x18
        self.assertEqual(
            self.inspector._layout_offset("struct bpf_map", "map_type"),
            0x18,
        )
        # DWARF answered, so nothing was recorded as a fallback.
        self.assertEqual(self.inspector.layout_fallbacks(), ())

    def test_layout_offset_uses_registry_without_dwarf(self) -> None:
        fake_gdb.values.clear()
        expected = layouts.offset("struct bpf_map", "map_type")
        self.assertEqual(
            self.inspector._layout_offset("struct bpf_map", "map_type"),
            expected,
        )
        self.assertIn("struct bpf_map", self.inspector.layout_fallbacks())

    def test_registry_for_dma_buf_priv(self) -> None:
        fake_gdb.values.clear()
        self.assertEqual(
            self.inspector._layout_offset("struct dma_buf", "priv"),
            layouts.offset("struct dma_buf", "priv"),
        )

    def test_layout_sizeof_uses_registry(self) -> None:
        fake_gdb.values.clear()
        self.assertEqual(
            self.inspector._layout_sizeof("struct zone"),
            layouts.sizeof("struct zone"),
        )
        self.assertIn("struct zone", self.inspector.layout_fallbacks())

    def test_no_fallback_when_type_unknown_to_both(self) -> None:
        fake_gdb.values.clear()
        self.assertIsNone(
            self.inspector._layout_offset("struct absent_type", "field")
        )

    def test_reset_clears_the_fallback_report(self) -> None:
        fake_gdb.values.clear()
        self.inspector._layout_offset("struct dma_buf", "priv")
        self.assertIn("struct dma_buf", self.inspector.layout_fallbacks())
        self.inspector.reset()
        self.assertEqual(self.inspector.layout_fallbacks(), ())

    def test_multiple_types_are_reported_sorted(self) -> None:
        fake_gdb.values.clear()
        self.inspector._layout_offset("struct zone", "free_area")
        self.inspector._layout_offset("struct dma_buf", "priv")
        self.assertEqual(
            self.inspector.layout_fallbacks(),
            ("struct dma_buf", "struct zone"),
        )


def _btf_blob(structs: dict[str, tuple[int, dict[str, int]]]) -> bytes:
    """Build a BTF blob: ``{name: (size, {field: byte_offset})}``.

    Field offsets are given in bytes and packed as bit offsets, matching
    how the real encoder emits members.
    """
    strings = bytearray(b"\x00")
    offsets: dict[str, int] = {"": 0}

    def intern(text: str) -> int:
        if text not in offsets:
            offsets[text] = len(strings)
            strings.extend(text.encode() + b"\x00")
        return offsets[text]

    types = bytearray()
    ids: dict[str, int] = {}
    for index, (name, (size, fields)) in enumerate(structs.items(), start=1):
        ids[name] = index
    for name, (size, fields) in structs.items():
        info = (4 << 24) | len(fields)  # KIND_STRUCT
        types += struct.pack("<III", intern(name), info, size)
        for field, byte_offset in sorted(fields.items()):
            types += struct.pack(
                "<III", intern(field), 1, byte_offset * 8,
            )
    header = struct.pack(
        "<HBBIIIII", 0xEB9F, 1, 0, 24,
        0, len(types), len(types), len(strings),
    )
    return header + bytes(types) + bytes(strings)


class BtfResolutionTests(FacadeTestBase):
    """BTF is the middle tier: DWARF, then BTF, then the registry."""

    _BLOB = _btf_blob({
        "bpf_map": (0x100, {
            "security": 0x38, "map_type": 0x40, "key_size": 0x44,
            "value_size": 0x48, "max_entries": 0x4C,
        }),
        "zone": (0x888, {"free_area": 0x220}),
    })

    def setUp(self) -> None:
        super().setUp()
        self.inspector = facade.KernelInspector(self.reader)
        self._path = self._write_blob(self._BLOB)
        # Point the resolver at our blob; DWARF is empty in these tests.
        self.reader._config.btf_path = self._path
        self.inspector.reset()

    def _write_blob(self, blob: bytes) -> str:
        import tempfile
        from pathlib import Path

        handle = tempfile.NamedTemporaryFile(
            "wb", suffix=".btf", delete=False,
        )
        handle.write(blob)
        handle.close()
        self.addCleanup(Path(handle.name).unlink, missing_ok=True)
        return handle.name

    def test_btf_supplies_the_offset_when_dwarf_is_absent(self) -> None:
        fake_gdb.values.clear()
        self.assertEqual(
            self.inspector._layout_offset("struct bpf_map", "map_type"),
            0x40,
        )

    def test_btf_value_differs_from_the_registry(self) -> None:
        # The blob's ``free_area``/size deliberately differ from the
        # registry, so a pass proves BTF (not the fallback) answered.
        fake_gdb.values.clear()
        self.assertEqual(
            self.inspector._layout_offset("struct zone", "free_area"),
            0x220,
        )
        self.assertEqual(self.inspector._layout_sizeof("struct zone"), 0x888)
        self.assertEqual(self.inspector.layout_fallbacks(), ())

    def test_btf_is_not_a_fallback(self) -> None:
        # BTF is real debug information, so it must not warn.
        fake_gdb.values.clear()
        self.inspector._layout_offset("struct bpf_map", "map_type")
        self.inspector._layout_sizeof("struct zone")
        self.assertEqual(self.inspector.layout_fallbacks(), ())

    def test_btf_sizeof(self) -> None:
        fake_gdb.values.clear()
        self.assertEqual(self.inspector._layout_sizeof("struct zone"), 0x888)

    def test_dwarf_beats_btf(self) -> None:
        fake_gdb.values[
            "(unsigned long)&((struct bpf_map *)0)->map_type"
        ] = 0x99
        self.assertEqual(
            self.inspector._layout_offset("struct bpf_map", "map_type"),
            0x99,
        )

    def test_registry_used_when_neither_knows_the_type(self) -> None:
        fake_gdb.values.clear()
        # struct dma_buf is in the blob's absence and DWARF is empty.
        self.assertEqual(
            self.inspector._layout_offset("struct dma_buf", "priv"),
            layouts.offset("struct dma_buf", "priv"),
        )
        self.assertIn("struct dma_buf", self.inspector.layout_fallbacks())

    def test_reset_drops_the_btf_cache(self) -> None:
        fake_gdb.values.clear()
        self.inspector._layout_offset("struct bpf_map", "map_type")
        self.inspector.reset()
        # Still resolves: ``reset`` only drops the cache, not the source.
        self.assertEqual(
            self.inspector._layout_offset("struct bpf_map", "map_type"),
            0x40,
        )

    def test_missing_blob_falls_through_to_the_registry(self) -> None:
        self.reader._config.btf_path = "/nonexistent/broken.btf"
        self.inspector.reset()
        fake_gdb.values.clear()
        self.assertEqual(
            self.inspector._layout_offset("struct bpf_map", "map_type"),
            layouts.offset("struct bpf_map", "map_type"),
        )
        self.assertIn("struct bpf_map", self.inspector.layout_fallbacks())


class PagingDirectMapTests(FacadeTestBase):
    """The walker reads page tables through the direct map.

    ``$cr3`` is a physical address, but the tables are only mapped at
    ``page_offset_base + phys``; walking the raw physical address fails
    on a real kernel.
    """

    ROOT = 0x3010000
    PAGE_OFFSET = 0xFFFF888000000000

    def setUp(self) -> None:
        super().setUp()
        self.walker = facade.PageTableWalker(self.reader)
        fake_gdb.values["(unsigned long)&page_offset_base"] = self.PAGE_OFFSET
        fake_gdb.values[
            f"*(unsigned long *){self.PAGE_OFFSET:#x}"
        ] = self.PAGE_OFFSET

    def test_physical_cr3_is_mapped_through_the_direct_map(self) -> None:
        fake_gdb.values["$cr3"] = self.ROOT
        self.assertEqual(self.walker.read_cr3(), self.ROOT)
        self.assertEqual(
            self.walker._mapped(self.ROOT), self.PAGE_OFFSET + self.ROOT,
        )

    def test_virtual_root_is_left_alone(self) -> None:
        virtual = self.PAGE_OFFSET + self.ROOT
        self.assertEqual(self.walker._mapped(virtual), virtual)
        self.assertEqual(self.walker._phys(virtual), self.ROOT)
        self.assertEqual(self.walker._phys(self.ROOT), self.ROOT)

    def test_walk_reads_entries_from_the_direct_map(self) -> None:
        va = 0xFFFF888000001234
        fake_gdb.values["$cr3"] = self.ROOT
        fake_gdb.values["$cr4"] = 0
        mapped = self.PAGE_OFFSET + self.ROOT
        index = KPageTable.pgd_index(va)
        fake_gdb.values[
            f"*(unsigned long *){mapped + index * 8:#x}"
        ] = 0x20003
        # The next level is read through the direct map as well; an
        # absent entry ends the walk cleanly.
        pud = self.PAGE_OFFSET + 0x20000
        fake_gdb.values[
            f"*(unsigned long *){pud + KPageTable.pud_index(va) * 8:#x}"
        ] = 0
        walk = self.walker.walk(va)
        self.assertEqual(walk.root, self.ROOT)
        self.assertEqual(
            [level.name for level in walk.levels], ["pgd", "pud"],
        )
        self.assertEqual(walk.note, "pud entry is not present")


if __name__ == "__main__":
    unittest.main()