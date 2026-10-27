"""Integration tests for the pwndbg-style command layer and the bootstrap.

``gdbinit.py`` is sourced directly by GDB, so it cannot be imported in a
normal test run.  These tests execute the real file in a module namespace
with two fakes installed:

* a fake ``gdb`` module that records command registration and provides the
  primitives the framework needs (``parse_and_eval``, ``error``,
  ``Command``, ...);
* a stub ``kernlens.gdb.facade`` module providing a ``FakeKdbg`` with
  canned answers.

Captured stdout (the pwndbg ``print`` idiom) is routed into the fake
``gdb.write`` buffer, so every assertion reads one string regardless of
whether a command prints directly or through the logger.

**Test parameters come from the real environment.**  The command
arguments and the fixture's canned answers are the values the test
kernel actually has -- Linux 6.1.134 as built for the ``pwn4kernel`` VM
-- not invented stand-ins.  The authoritative constants live in the
"Real-environment parameters" block below; this way a fixture that no
longer matches the kernel the code targets shows up as a failure here
instead of as a surprise on a live session.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import re
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

from contract_spec import CANONICAL_COMMANDS


GDBINIT_PATH = Path(__file__).resolve().parents[2] / "gdbinit.py"


#: Matches one SGR sequence: ``ESC [ params m``.
_SGR = re.compile(r"\x1b\[[0-9;]*m")


def plain(text: str | None) -> str:
    """Strip ANSI colour from *text*, so assertions can name real words.

    ``message.notice`` colourises the ``Examples:`` / ``Notes:`` / ``Alias:``
    labels, which means the raw epilog is ``"\x1b[35mNotes:\x1b[0m ..."``.
    Three assertions in this file compared that against plain strings and
    only passed when an earlier test had switched colour off for the whole
    process -- they failed whenever the class ran on its own, which is how
    a suite quietly becomes order-dependent.  Stripping first makes each
    test independent of whatever ran before it.
    """
    return _SGR.sub("", text or "")


# =========================================================================
# Real-environment parameters
# =========================================================================
#
# Every argument and canned answer below is taken from the real test
# kernel -- Linux 6.1.134 as built for the pwn4kernel VM
# (``kernels/6.1.134/01/{vmlinux,System.map,.config}``) -- instead of an
# invented value, so a fixture that stops matching the kernel the code
# was developed against is visible here.
#
# Two kinds of number appear below:
#
#   * **boot-invariant facts**, verified against the live kernel on
#     successive boots: the link-time symbol offsets (`LINK_*`, from
#     `System.map`), the `sizeof(struct page)`, the banner/release, the
#     `CONFIG_*` values and the `syscall` count.  The per-CPU segments
#     are **zero-based** (`__per_cpu_start` is a genuine 0, `current_task`
#     is only `0x1fb80`), which is why `kl-percpu` needs the zero
#     special case.
#   * **one sample boot** for everything that is chosen at boot -- the
#     KASLR slide, the direct-map/vmemmap bases (`page_offset_base` and
#     `vmemmap_base` are kernel *variables* filled in from the physical
#     memory map, so their contents change on every boot just like the
#     slide) and the derived `__per_cpu_offset[0]`.  The values below
#     were all actually observed on one boot; every runtime address is
#     then derived with the kernel's own formula `runtime = link + slide`
#     (`_text` included), and every direct-map address as
#     `PAGE_OFFSET_BASE + phys`, so the fixtures stay internally
#     consistent with whichever values the fake reports.

LINK_TEXT = 0xFFFFFFFF81000000
#: A KASLR slide observed on a real boot (2 MiB-aligned, as the kernel
#: requires).  It is a sample, not a fixed property of the kernel.
KASLR_SLIDE = 0x1A600000
RUNTIME_TEXT = LINK_TEXT + KASLR_SLIDE          # 0xffffffffa0600000
IDT_BASE = 0xFFFFFE0000000000
IDT_LIMIT = 0xFFF
#: real per-CPU symbol offsets (System.map), zero-based on x86_64.
LINK_CURRENT_TASK = 0x1FB80
LINK_PER_CPU_START = 0x0000000000000000
LINK_PER_CPU_END = 0x0000000000035000
#: real ``__per_cpu_offset[0]``, the live per-CPU area base for CPU 0.
#: Like the direct-map base it is filled in at boot, so it moves with
#: the physical memory map; this is a sample boot's value.
PER_CPU_OFFSET0 = 0xFFFF9A0D47A00000
#: what ``kl-percpu current_task 0`` must resolve to on the real kernel.
CURRENT_TASK_CPU0 = PER_CPU_OFFSET0 + LINK_CURRENT_TASK
#: real text/data symbols (System.map), and their runtime addresses.
LINK_DIVIDE_ERROR = 0xFFFFFFFF82400990
LINK_KFREE = 0xFFFFFFFF81424770
LINK_COMMIT_CREDS = 0xFFFFFFFF811DD800
LINK_SYS_READ = 0xFFFFFFFF814EE280
LINK_SYS_WRITE = 0xFFFFFFFF814EE3E0
LINK_SYS_OPEN = 0xFFFFFFFF814E9D30
LINK_SYS_CALL_TABLE = 0xFFFFFFFF82800300
LINK_MODULES = 0xFFFFFFFF831E30A0
LINK_JIFFIES = 0xFFFFFFFF830079C0
RUNTIME_DIVIDE_ERROR = LINK_DIVIDE_ERROR + KASLR_SLIDE
RUNTIME_COMMIT_CREDS = LINK_COMMIT_CREDS + KASLR_SLIDE
RUNTIME_SYS_READ = LINK_SYS_READ + KASLR_SLIDE
RUNTIME_SYS_WRITE = LINK_SYS_WRITE + KASLR_SLIDE
RUNTIME_SYS_OPEN = LINK_SYS_OPEN + KASLR_SLIDE
RUNTIME_SYS_CALL_TABLE = LINK_SYS_CALL_TABLE + KASLR_SLIDE
RUNTIME_MODULES = LINK_MODULES + KASLR_SLIDE
RUNTIME_JIFFIES = LINK_JIFFIES + KASLR_SLIDE
#: real *values* of ``page_offset_base`` / ``vmemmap_base``.  These are
#: kernel variables, so their contents depend on the physical memory map
#: chosen at boot -- they are NOT ``link address + slide``, and they are
#: therefore sample-boot values too.
PAGE_OFFSET_BASE = 0xFFFF9A0D40000000
VMEMMAP_BASE = 0xFFFFDC5E40000000
#: `sizeof(struct page)` on this kernel is 64, so a page's struct is cheap
#: to compute: `struct page = VMEMMAP_BASE + pfn*64`, and its direct-map
#: address is `PAGE_OFFSET_BASE + pfn*4096`.  Physical 0x1000 is PFN 1.
PAGE_PFN = 1
PAGE_PHYS = PAGE_PFN * 0x1000
STRUCT_PAGE = VMEMMAP_BASE + PAGE_PFN * 64       # struct page for phys 0x1000
DIRECT_VIRT = PAGE_OFFSET_BASE + PAGE_PHYS       # its direct-map address
#: a buddy free page the harvesting session found (phys/virt/page are
#: consistent with the bases above).
BUDDY_PHYS = 0x120000
BUDDY_PAGE = VMEMMAP_BASE + BUDDY_PHYS // 0x1000 * 64
BUDDY_VIRT = PAGE_OFFSET_BASE + BUDDY_PHYS
#: a real kmem_cache (kmalloc-1k) address + shape on this kernel.
KMALLOC_1K_ADDR = 0xFFFF9A0D44C42B00
KMALLOC_1K_SIZE = 0x400
KMALLOC_1K_OBJECTS = 16
KMALLOC_1K_ORDER = 2
KMALLOC_64_ADDR = 0xFFFF9A0D44C42500
KMALLOC_64_SIZE = 0x40
#: kernel modules region (x86_64 is fixed, not randomised): the real
#: addresses a loaded module would sit at.
MODULE_ADDR = 0xFFFFFFFFC0000000
MODULE_ADDR2 = 0xFFFFFFFFC0020000
#: real kernel banner / release / boot command line of the test kernel.
KVERSION = (
    "Linux version 6.1.134 (bogon@bogon) (gcc (Ubuntu 14.2.0-4ubuntu2~24.04.1) "
    "14.2.0, GNU ld (GNU Binutils for Ubuntu) 2.42) #1 SMP PREEMPT_DYNAMIC"
)
KRELEASE = (6, 1, 134)
KCMDLINE = (
    "root=/dev/sda console=ttyS0 rw loglevel=3 oops=panic panic=1 "
    "net.ifnames=0 biosdevname=0 no5lvl kaslr pti=on"
)
#: real CONFIG_* values for this kernel.
KCONFIG = {
    "CONFIG_RANDOMIZE_BASE": "y",
    "CONFIG_SMP": "y",
    "CONFIG_MODULES": "y",
    "CONFIG_SECURITY": "y",
    "CONFIG_KALLSYMS": "y",
    "CONFIG_SLAB_FREELIST_HARDENED": "y",
    "CONFIG_STACKPROTECTOR": "y",
    "CONFIG_DEBUG_INFO": "y",
}
#: real syscall table entry count on this kernel (unfiltered table).
SYSCALL_COUNT = 451


class FakeGdbError(Exception):
    """Stand-in for ``gdb.error`` / ``gdb.GdbError``."""


class FakeCommand:
    """Stand-in for ``gdb.Command`` with a per-module registry."""

    def __init__(self, name: str, command_class: int) -> None:
        owner = FakeCommand.current
        assert owner is not None
        if name in owner.registry:
            raise FakeGdbError(
                f"Error creating command {name!r}: already exists"
            )
        owner.registry[name] = type(self)
        owner.instances[name] = self
        self.command_name = name
        self.command_class = command_class

    current: FakeGdb | None = None


class FakeGdb(types.ModuleType):
    """Minimal GDB Python API used by the command framework."""

    error = FakeGdbError
    GdbError = FakeGdbError
    MemoryError = FakeGdbError
    COMMAND_USER = 0
    Command = FakeCommand

    def __init__(self) -> None:
        super().__init__("gdb")
        self.output: list[str] = []
        self.expressions: dict[str, object] = {}
        self.registry: dict[str, type[FakeCommand]] = {}
        self.instances: dict[str, FakeCommand] = {}
        self.executed: list[str] = []
        FakeCommand.current = self

    def write(self, text: str) -> None:
        self.output.append(text)

    def parse_and_eval(self, expression: str) -> object:
        if expression in self.expressions:
            return self.expressions[expression]
        try:  # numeric literals, e.g. ``0xffff888000001234``
            return int(expression, 0)
        except ValueError:
            pass
        raise FakeGdbError(f"cannot evaluate {expression!r}")

    def execute(self, command: str, to_string: bool = False) -> str:
        del to_string
        self.executed.append(command)
        if command == "help user-defined":
            # ``register_all`` snapshots the pre-existing user commands
            # this way (``help <name>`` is unusable: GDB matches prefixes,
            # so ``kernlens-pt`` would also hit ``kernlens-pte``).  Emit
            # the exact list in GDB's ``name -- help`` form.
            lines = [
                "User-defined commands.",
                "The commands in this class are those defined by the user.",
                "",
                "List of commands:",
                "",
            ]
            lines += [f"{name} -- This command is not documented."
                      for name in sorted(self.registry)]
            return "\n".join(lines) + "\n"
        if command.startswith("set "):
            name, _, value = command[4:].partition(" = ")
            self.expressions[name.strip()] = int(value, 0)
            return ""
        if command.startswith("add-symbol-file "):
            return ""
        raise FakeGdbError(f"unsupported command {command!r}")

    def newest_frame(self) -> object:
        return SimpleNamespace(pc=lambda: 0)

    def current_progspace(self) -> object:
        return SimpleNamespace(filename=None)

    def selected_inferior(self) -> object:
        return SimpleNamespace(pid=1)


class FakeLogger:
    """The only ``Logger`` method the bootstrap calls at load time."""

    def __init__(self) -> None:
        self.show_tag = True

    def set_show_tag(self, enabled: bool) -> None:
        self.show_tag = enabled


def _runtime_kbase_result() -> SimpleNamespace:
    """Canonical fake result used by the base/kbase command tests.

    Every number is taken from the real test kernel (Linux 6.1.134,
    KASLR on): KASLR relocates the link-time ``_text`` of
    ``0xffffffff81000000`` by ``+0x1a600000`` to ``0xffffffffa0600000``,
    and the IDT's #DE gate points at ``asm_exc_divide_error``.
    """
    return SimpleNamespace(
        base=RUNTIME_TEXT,
        handler=RUNTIME_DIVIDE_ERROR,
        handler_symbol="asm_exc_divide_error",
        idt=SimpleNamespace(
            base=IDT_BASE,
            limit=IDT_LIMIT,
            source="monitor",
        ),
        method="symbol",
        link_text=LINK_TEXT,
        kaslr_offset=KASLR_SLIDE,
    )


class FakeKdbg:
    """Canned answers for every ``kdbg`` attribute used by the commands."""

    def __init__(self, fake_gdb: FakeGdb) -> None:
        self._gdb = fake_gdb
        self.logger = FakeLogger()
        self.styler = SimpleNamespace()
        self.kbase = SimpleNamespace(
            find=self.find_kbase, idt=self.idt, entry=self.idt_entry,
        )
        self.reset()

    def reset(self) -> None:
        """Restore every canned answer; tests mutate these in place."""
        self.color_enabled = False
        self.indent_nested = "    "
        self.kbase_result = _runtime_kbase_result()
        self.kaslr_offset = 0
        self.link_text_value: int | None = LINK_TEXT
        #: Optional stand-in for ``kdbg.kernel`` (fallback-layout warning).
        self.kernel: object | None = None
        self.kernel_u64: dict[str, int] = {
            "page_offset_base": PAGE_OFFSET_BASE,
            "vmemmap_base": VMEMMAP_BASE,
        }
        self.kernel_addrs: dict[str, int] = {
            "sys_call_table": RUNTIME_SYS_CALL_TABLE,
            "modules": RUNTIME_MODULES,
        }
        self.sym_map: dict[int, str] = {RUNTIME_TEXT: "startup_64", 0x2000: "bar"}
        self.line_map: dict[int, str] = {RUNTIME_TEXT: "head_64.S:1", 0x2000: "b.c:3"}
        #: Per-CPU symbols are **zero-based**: their bare value IS the
        #: offset inside the per-CPU section, so they are reachable only
        #: through the raw expression -- ``kvar_addr`` adds the KASLR
        #: slide and is deliberately *not* how ``kl-percpu`` reads them.
        #: Keeping them out of ``kernel_addrs`` makes a regression to the
        #: KASLR-adjusted lookup fail here.
        self.words: dict[str, int] = {
            "(unsigned long)&__per_cpu_start": LINK_PER_CPU_START,
            "(unsigned long)&__per_cpu_end": LINK_PER_CPU_END,
            "(unsigned long)&current_task": LINK_CURRENT_TASK,
            "*(unsigned long *)(0x1000)": 0xDEADBEEF,
            "*(unsigned char *)(0x1000)": 0x41,
            "*(unsigned char *)(0x1001)": 0x42,
        }
        self.chain_value = "func_a <- func_b"
        self.walk_value: SimpleNamespace | None = None
        self.nr_cpus_value = 4
        self.nr_nodes_value = 1
        self.cur_cpu_value: int | None = 0
        self.online: set[int] = {0, 1, 2, 3}
        self.percpu_off_base: int | None = PER_CPU_OFFSET0
        self.fields: dict[tuple[int, str, str], int | None] = {}
        self.page_bytes_value = 64
        self.cache_name_value = "kmalloc-1k"
        self.freeptr_offset_value: int | None = 0
        self.freeptr_random_value: int | None = 0
        self.decode_map: dict[tuple[int, int | None, int], int] = {}
        self.cpu_slab: dict[tuple[str, int], int | None] = {}
        self.partial: dict[tuple[int, int], tuple[int, int | None, int | None, int | None]] = {}
        self.in_partial_set: set[tuple[object, ...]] = set()
        self.idt_info: SimpleNamespace | None = None
        self.idt_entries: dict[int, SimpleNamespace] = {}
        self.kversion_value: str | None = KVERSION
        self.krelease_value: tuple[int, ...] | None = KRELEASE
        self.kcmdline_value: str | None = KCMDLINE
        self.kconfig_data: dict[str, str] = dict(KCONFIG)
        self.modules_value: list[SimpleNamespace] = [
            SimpleNamespace(
                address=MODULE_ADDR, name="nf_tables",
                size=0x20000, used_by=2,
            ),
            SimpleNamespace(
                address=MODULE_ADDR2, name="kvm",
                size=0x40000, used_by=0,
            ),
        ]
        self.syscall_table: list[tuple[str, int]] = [
            ("__x64_sys_read", RUNTIME_SYS_READ),
            ("__x64_sys_write", RUNTIME_SYS_WRITE),
            ("__x64_sys_open", RUNTIME_SYS_OPEN),
        ]
        self.syscalls_empty = False
        self.page_type_value = "initialized"
        self.page_refcount_value: int | None = 1
        self.kallsyms_value: list[tuple[str, str, int]] = [
            ("commit_creds", "T", RUNTIME_COMMIT_CREDS),
            ("__x64_sys_read", "T", RUNTIME_SYS_READ),
        ]
        self.dmesg_value: list[SimpleNamespace] = [
            SimpleNamespace(seq=0, timestamp=1.0, text="Booting Linux"),
            SimpleNamespace(seq=1, timestamp=2.5, text="hello\nworld"),
        ]
        self.tk_epoch_value: int | None = 1_700_000_000
        self.bpf_progs_value: list[SimpleNamespace] = [
            SimpleNamespace(
                index=0, address=0xFFFF888000100000,
                type="BPF_PROG_TYPE_SOCKET_FILTER",
                attach_type="BPF_CGROUP_INET_INGRESS",
                func=0xFFFFFFFF81234560, aux=0xFFFF888000110000,
                jited_len=0x40, insn_count=2, insns=b"\x18\x00\x00\x00\x00",
            ),
        ]
        self.bpf_maps_value: list[SimpleNamespace] = [
            SimpleNamespace(
                index=0, address=0xFFFF888000200000,
                type="BPF_MAP_TYPE_ARRAY", key_size=4, value_size=8,
                max_entries=4, array_addr=0xFFFF888000200100,
            ),
        ]
        self.bpf_values: dict[tuple[int, int], bytes] = {
            (0xFFFF888000200100, 8): bytes.fromhex("0102030405060708"),
        }
        self.buddy_value: list[SimpleNamespace] = [
            SimpleNamespace(
                index=0, page=BUDDY_PAGE,
                phys=BUDDY_PHYS, virt=BUDDY_VIRT,
            ),
            SimpleNamespace(
                index=1, page=VMEMMAP_BASE + 0x140000 // 0x1000 * 64,
                phys=0x140000, virt=PAGE_OFFSET_BASE + 0x140000,
            ),
        ]
        #: One zone, the shape the 6.1.134 test VM reports for DMA:
        #: `node 0, zone DMA, spanned 4095, present 3998, start_pfn 1`.
        self.zone_spans_value: list[SimpleNamespace] = [
            SimpleNamespace(
                name="DMA", node=0, address=0xFFFF888000500000,
                start_pfn=0x1, spanned_pages=4095, present_pages=3998,
                end_pfn=0x1000,
            ),
        ]
        #: A free order-10 block at pfn 0x400 (the VM's real first DMA
        #: block: 1024 pages = 4 MiB, base phys 0x400000).
        self.block_value: SimpleNamespace = SimpleNamespace(
            page=0xFFFFEA0000100000, order=10, base_pfn=0x400,
            block_virt=PAGE_OFFSET_BASE + 0x400000,
        )
        #: ``nr_free`` is the per-order total, so one row per order --
        #: the shape `kl-buddy list` prints and the tidiest fixture for
        #: asserting the column layout.
        self.free_area_value: list[tuple[str, int, int, int]] = [
            ("DMA", 0, 0, 3),
            ("DMA", 0, 10, 3),
        ]
        self.freelist_value: dict[tuple[str, int, str], tuple] = {
            ("DMA", 10, "Movable"): (
                SimpleNamespace(
                    index=0, page=0xFFFFEA0000100000,
                    phys=0x400000, virt=PAGE_OFFSET_BASE + 0x400000,
                ),
                SimpleNamespace(
                    index=1, page=0xFFFFEA0000200000,
                    phys=0x800000, virt=PAGE_OFFSET_BASE + 0x800000,
                ),
                SimpleNamespace(
                    index=2, page=0xFFFFEA0000300000,
                    phys=0xC00000, virt=PAGE_OFFSET_BASE + 0xC00000,
                ),
            ),
        }
        self.buddy_order_value: int | None = 10
        self.slab_caches_value: list[SimpleNamespace] = [
            SimpleNamespace(
                address=KMALLOC_1K_ADDR, name="kmalloc-1k",
                size=KMALLOC_1K_SIZE, object_size=KMALLOC_1K_SIZE,
                offset=0x200,
                oo_order=KMALLOC_1K_ORDER, oo_objects=KMALLOC_1K_OBJECTS,
                align=KMALLOC_1K_SIZE,
                flags=(),
                # PAGE_SIZE << order = 0x1000 << 2, read from the 6.1.134
                # test VM.  A plain kmalloc cache has no dedicated usercopy
                # window, which the kernel records as the WHOLE object
                # (useroffset=0, usersize=object_size) -- `usersize=0`
                # would mean "nothing is copyable".
                slab_size=0x4000, inuse=KMALLOC_1K_SIZE,
                useroffset=0, usersize=KMALLOC_1K_SIZE,
            ),
            SimpleNamespace(
                address=KMALLOC_64_ADDR, name="kmalloc-64",
                size=KMALLOC_64_SIZE, object_size=KMALLOC_64_SIZE,
                offset=0x20, oo_order=0, oo_objects=64, align=KMALLOC_64_SIZE,
                flags=(),
                slab_size=0x1000, inuse=KMALLOC_64_SIZE,
                useroffset=0, usersize=KMALLOC_64_SIZE,
            ),
        ]
        self.slab_object_value: SimpleNamespace | None = SimpleNamespace(
            obj=KMALLOC_1K_ADDR, cache=self.slab_caches_value[0],
        )
        #: `struct slab.counters` for the fixture slab: SLUB packs
        #: inuse:16 | objects:15 | frozen:1, so this is "3 of 16, not
        #: frozen" -- the shape the 6.1 VM reports for a partial slab.
        self.slab_counters_value: tuple[int, int, int] | None = (3, 16, 0)
        self.object_index_value: tuple[int, int] | None = (7, 16)
        self.neighbour_value: tuple[int | None, int | None] = (
            KMALLOC_1K_ADDR - KMALLOC_1K_SIZE,
            KMALLOC_1K_ADDR + KMALLOC_1K_SIZE,
        )
        self.dmabufs_value: list[SimpleNamespace] = [
            SimpleNamespace(
                index=0, address=0xFFFF888000400000, size=0x1000,
                file=0xFFFF888000400100, exporter="system",
                name="dmabuf0", exporter_name="system",
                name_field="dmabuf0", priv=0xFFFF888000410000,
                sg_entries=(
                    SimpleNamespace(
                        index=0, page=0xFFFFEA0000000040,
                        virt=0xFFFF888000001000,
                        phys=0x1000, offset=0, length=0x1000,
                    ),
                ),
            ),
        ]

    # --- logging / styling ---------------------------------------------

    def style(self, text: str, color: object) -> str:
        if not color or not self.color_enabled:
            return text
        return f"\x1b[99m{text}\x1b[0m"

    def addr(self, value: int) -> str:
        return f"0x{value & 0xFFFFFFFFFFFFFFFF:016x}"

    def fn(self, name: str) -> str:
        return name

    def loc(self, location: str) -> str:
        return location

    def enable_color(self) -> None:
        self.color_enabled = True

    def disable_color(self) -> None:
        self.color_enabled = False

    # --- kernel reads ---------------------------------------------------

    def read_kvar(self, name: str, type_name: str = "unsigned long") -> int | None:
        del type_name
        return self.kernel_u64.get(name)

    def kvar_addr(self, name: str) -> int | None:
        return self.kernel_addrs.get(name)

    def kaslr_slide(self) -> int:
        """The slide the reader is using (fake: the canned ``kaslr_offset``)."""
        return self.kaslr_offset

    def link_text(self) -> int | None:
        return self.link_text_value

    def find_kbase(self) -> SimpleNamespace | None:
        return self.kbase_result

    def u64(self, expression: str) -> int | None:
        return self.words.get(expression)

    # --- topology / symbols ---------------------------------------------

    def nr_cpus(self) -> int:
        return self.nr_cpus_value

    def nr_nodes(self) -> int:
        return self.nr_nodes_value

    def cpu_online(self, cpu: int | None) -> bool | None:
        if cpu is None or cpu < 0:
            return None
        return cpu in self.online

    def cur_cpu(self) -> int | None:
        return self.cur_cpu_value

    def percpu_off(self, cpu: int) -> int | None:
        if self.percpu_off_base is None:
            return None
        return self.percpu_off_base + cpu * 0x4000

    def sym(self, pc: int) -> str:
        return self.sym_map.get(pc, "?")

    def line(self, pc: int) -> str:
        return self.line_map.get(pc, "??")

    def backtrace(self, depth: int) -> None:
        self._gdb.write(f"bt: {depth} frames\n")

    def chain(self, depth: int) -> str:
        del depth
        return self.chain_value

    def color_chain(self, chain: str) -> str:
        return chain

    def print_slab(self, head: int) -> None:
        self._gdb.write(f"slab: head=0x{head:x}\n")

    def read_field(self, obj: int, type_name: str, path: str) -> int | None:
        return self.fields.get((obj, type_name, path))

    # --- kernel metadata ------------------------------------------------

    def kversion(self) -> str | None:
        return self.kversion_value

    def krelease(self) -> tuple[int, ...] | None:
        return self.krelease_value

    def kcmdline(self) -> str | None:
        return self.kcmdline_value

    def kconfig(self) -> dict[str, str]:
        return self.kconfig_data

    def config_key(self, name: str) -> str:
        return "CONFIG_" + name.upper()

    def kconfig_get(self, name: str) -> str | None:
        for candidate in (self.config_key(name), name.upper(), name):
            if candidate in self.kconfig_data:
                return self.kconfig_data[candidate]
        return None

    def kconfig_contains(self, name: str) -> bool:
        return self.kconfig_get(name) is not None

    def kconfig_update(self, path: str) -> int:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        merged = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            self.kconfig_data[name.strip()] = value.strip()
            merged += 1
        return merged

    def modules(self) -> tuple[SimpleNamespace, ...]:
        return tuple(self.modules_value)

    def syscalls(self, name_filter: str | None = None) -> tuple[SimpleNamespace, ...]:
        if self.syscalls_empty:
            return ()
        entries = []
        for index, (name, addr) in enumerate(self.syscall_table):
            if name_filter is not None and name_filter not in name:
                continue
            entries.append(
                SimpleNamespace(index=index, address=addr, symbol=name)
            )
        return tuple(entries)

    def syscall_count(self) -> int | None:
        # The real kernel's ``sys_call_table`` has this many slots.
        return SYSCALL_COUNT

    def page_type(self, page: int) -> str:
        return self.page_type_value

    def page_refcount(self, page: int) -> int | None:
        return self.page_refcount_value

    def lookup(self, query: str) -> tuple[SimpleNamespace, ...]:
        result = []
        for name, sym_type, address in self.kallsyms_value:
            if query == f"{address:#x}" or query in name:
                result.append(
                    SimpleNamespace(name=name, type=sym_type, address=address)
                )
        return tuple(result)

    def dmesg(self) -> tuple[SimpleNamespace, ...]:
        return tuple(self.dmesg_value)

    def tk_epoch(self) -> int | None:
        return self.tk_epoch_value

    def bpf_progs(self) -> tuple[SimpleNamespace, ...]:
        return tuple(self.bpf_progs_value)

    def bpf_maps(self) -> tuple[SimpleNamespace, ...]:
        return tuple(self.bpf_maps_value)

    def bpf_map_value(self, addr: int, value_size: int) -> bytes | None:
        return self.bpf_values.get((addr, min(value_size, 0x20)))

    def buddy_zones(
        self, *, zone: str | None = None, order: int | None = None,
        mtype: str | None = None, page_size: int = 64, node: int | None = None,
    ) -> tuple[SimpleNamespace, ...]:
        del order, mtype, page_size, node
        if zone is not None and zone != "Normal":
            return ()
        return tuple(self.buddy_value)

    def zone_spans(self) -> tuple[SimpleNamespace, ...]:
        return tuple(self.zone_spans_value)

    def zone_of_pfn(
        self, pfn: int, spans: object = None,
    ) -> tuple[SimpleNamespace | None, bool]:
        del spans
        for span in self.zone_spans_value:
            if span.start_pfn <= pfn < span.end_pfn:
                hole = not (
                    span.start_pfn <= pfn
                    < span.start_pfn + span.present_pages
                )
                return span, hole
        return None, False

    def block_of_pfn(
        self, pfn: int, phys: int, *, spans: object = None,
        page_size: int = 64,
    ) -> SimpleNamespace:
        del spans, page_size
        span, hole = self.zone_of_pfn(pfn)
        template = self.block_value
        if (
            self.buddy_order_value is not None
            and template.order is not None
            and template.base_pfn is not None
        ):
            size = 1 << template.order
            if template.base_pfn <= pfn < template.base_pfn + size:
                position = pfn - template.base_pfn
                return SimpleNamespace(
                    phys=phys, pfn=pfn, page=template.page + position * 64,
                    zone=span, hole=hole, order=template.order,
                    size_pages=size, base_pfn=template.base_pfn,
                    position=position, block_page=template.page,
                    block_phys=template.base_pfn << 12,
                    block_virt=template.block_virt,
                    is_block_head=position == 0,
                    managed=span is not None,
                    free=True,
                )
        return SimpleNamespace(
            phys=phys, pfn=pfn, page=0xFFFFEA0000000000 + pfn * 64,
            zone=span, hole=hole, order=None, size_pages=None,
            base_pfn=None, position=None, block_page=None, block_phys=None,
            block_virt=None, is_block_head=False,
            managed=span is not None, free=False,
        )

    def block_range(
        self, location: SimpleNamespace, page_size: int = 64,
    ) -> tuple[int, int, int, int] | None:
        del page_size
        if location.base_pfn is None or location.size_pages is None:
            return None
        first = location.base_pfn
        last = first + location.size_pages - 1
        return first, last, first << 12, (last << 12) | 0xFFF

    def buddy_pfn(
        self, location: SimpleNamespace,
    ) -> tuple[int, int] | None:
        if location.base_pfn is None or location.size_pages is None:
            return None
        pfn = location.base_pfn ^ location.size_pages
        return pfn, pfn << 12

    def free_area_counts(
        self, *, zone: str | None = None, order: int | None = None,
        mtype: str | None = None, node: int | None = None,
        spans: object = None,
    ) -> tuple[tuple[str, int, int, int], ...]:
        del spans
        rows = []
        for label, node_index, area_order, count in self.free_area_value:
            if zone is not None and zone.lower() != label.lower():
                continue
            if order is not None and order != area_order:
                continue
            if node is not None and node != node_index:
                continue
            if mtype is not None and not self.freelist_value.get(
                (label, area_order, mtype)
            ):
                continue
            rows.append((label, node_index, area_order, count))
        return tuple(rows)

    def freelist_blocks(
        self, zone_name: str, order: int, mtype: str, *, node: int = 0,
        limit: int = 64, page_size: int = 64,
    ) -> tuple[SimpleNamespace, ...]:
        del node, page_size
        return tuple(
            self.freelist_value.get((zone_name, order, mtype), ())
        )[:limit]

    def freelist_count(
        self, zone_name: str, order: int, mtype: str, *, node: int = 0,
        limit: int = 4096, page_size: int = 64,
    ) -> int:
        return len(
            self.freelist_blocks(
                zone_name, order, mtype, node=node, limit=limit,
                page_size=page_size,
            )
        )

    def buddy_order(self, page: int) -> int | None:
        return self.buddy_order_value

    def page_is_buddy(self, page: int) -> bool | None:
        return self.buddy_order_value is not None

    def slab_caches(self) -> tuple[SimpleNamespace, ...]:
        return tuple(self.slab_caches_value)

    def slab_cache(self, name: str) -> SimpleNamespace | None:
        for cache in self.slab_caches_value:
            if cache.name == name:
                return cache
        return None

    def slab_object(self, addr: int) -> tuple[int, SimpleNamespace] | None:
        value = self.slab_object_value
        if value is None:
            return None
        return value.obj, value.cache

    def dmabufs(self) -> tuple[SimpleNamespace, ...]:
        return tuple(self.dmabufs_value)

    def table(self, headers: object, rows: object) -> str:
        out = ["  ".join(str(cell) for cell in headers)]
        for row in rows:  # type: ignore[union-attr]
            out.append("  ".join(str(cell) for cell in row))  # type: ignore[union-attr]
        return "\n".join(out)

    # --- SLUB granular --------------------------------------------------

    def page_bytes(self) -> int:
        return self.page_bytes_value

    def head_to_page(self, head: int) -> int | None:
        return self.fields.get((head, "__head_to_page__", "page"))

    def compound_head(self, page: int) -> int:
        return page

    def cache_name(self, cache: int) -> str:
        return self.cache_name_value

    def slab_counters(self, page: int) -> tuple[int, int, int] | None:
        return self.slab_counters_value

    def slab_state(self, page: int) -> str:
        counters = self.slab_counters_value
        if counters is None:
            return "unknown"
        inuse, objects, frozen = counters
        if frozen:
            return "frozen"
        if objects == 0:
            return "unknown"
        if inuse >= objects:
            return "full"
        if inuse == 0:
            return "empty"
        return "partial"

    def object_index(
        self, head: int, obj: int, cache: int, page_size: int = 64,
    ) -> tuple[int, int] | None:
        del head, cache, page_size
        return self.object_index_value

    def neighbour_objects(
        self, cache: int, obj: int, head: int, page_size: int = 64,
    ) -> tuple[int | None, int | None]:
        del cache, head, page_size
        return self.neighbour_value

    def freeptr_offset(self, cache: int) -> int | None:
        return self.freeptr_offset_value

    def freeptr_random(self, cache: int) -> int | None:
        return self.freeptr_random_value

    def decode_freeptr(self, raw: int, random: int | None, ptr_addr: int) -> int:
        return self.decode_map.get((raw, random, ptr_addr), raw)

    def cpu_active_slab(self, cache: int, cpu: int) -> int | None:
        return self.cpu_slab.get(("active", cpu))

    def cpu_freelist(self, cache: int, cpu: int) -> int | None:
        return self.cpu_slab.get(("freelist", cpu))

    def partial_info(
        self, cache: int, node_id: int,
    ) -> tuple[int, int | None, int | None, int | None]:
        return self.partial.get((cache, node_id), (0, None, None, None))

    def in_partial(self, cache: int, page: int, node_id: int) -> bool:
        return ("in", cache, page, node_id) in self.in_partial_set

    # --- IDT dump -------------------------------------------------------

    def idt(self) -> SimpleNamespace | None:
        return self.idt_info

    def idt_entry(
        self, index: int, info: SimpleNamespace | None = None,
    ) -> SimpleNamespace | None:
        del info
        return self.idt_entries.get(index)

    # --- page tables ----------------------------------------------------

    def walk(
        self, va: int, *, five_level: bool | None = None,
        root: int | None = None,
    ) -> SimpleNamespace:
        if self.walk_value is None:
            raise AssertionError("walk_value was not configured")
        if five_level is not None:
            self.walk_value.five_level = five_level
        if root is not None:
            self.walk_value.root = root
        return self.walk_value


def _load_gdbinit() -> tuple[
    types.ModuleType, FakeGdb, FakeKdbg,
    types.ModuleType, types.ModuleType, types.ModuleType,
]:
    """Execute the real ``gdbinit.py`` against the fakes.

    Returns the bootstrap module, the two fakes, and the live
    ``commands.framework`` / ``commands.help`` / ``commands.formatting``
    modules captured while the fakes were installed (the module cache is
    cleaned afterwards, so they must be grabbed here).
    """
    fake_gdb = FakeGdb()
    fake_kdbg = FakeKdbg(fake_gdb)
    stub = types.ModuleType("kernlens.gdb.facade")
    stub.kdbg = fake_kdbg
    stub.KernelDebugger = type("KernelDebugger", (), {})
    stub.COMPONENT_NAMES = (
        "config", "logger", "styler", "reader", "symbols", "kaslr",
        "kbase", "cpu", "walker", "kernel", "slub",
    )
    stub.BOUND_NAMES = ()
    stub.FREE_FUNCTION_NAMES = ()

    missing = object()
    saved_gdb = sys.modules.get("gdb", missing)
    saved_facade = sys.modules.get("kernlens.gdb.facade", missing)
    gdb_pkg = sys.modules.get("kernlens.gdb")
    saved_attr = getattr(gdb_pkg, "facade", missing) if gdb_pkg else missing
    before = set(sys.modules)

    stub.__is_stub__ = True
    sys.modules["gdb"] = fake_gdb
    sys.modules["kernlens.gdb.facade"] = stub
    module = types.ModuleType("kernlens_gdbinit_under_test")
    module.__file__ = str(GDBINIT_PATH)
    code = compile(
        GDBINIT_PATH.read_text(encoding="utf-8"), str(GDBINIT_PATH), "exec",
    )
    try:
        exec(code, module.__dict__)
    except BaseException:
        raise
    else:
        # Grab the live command modules before the cache is cleaned; a
        # later re-import would need a ``gdb`` module again.
        framework = sys.modules["kernlens.commands.framework"]
        help_module = sys.modules["kernlens.commands.help"]
        formatting = sys.modules["kernlens.commands.formatting"]
    finally:
        # Every ``kernlens``/``gdb`` module imported while the fakes were
        # installed captured them in a module global; drop those (and the
        # parent-package attributes that would otherwise keep handing the
        # stale module back) so a later test re-imports against its own
        # ``gdb``.
        for name in set(sys.modules) - before:
            if name == "gdb" or name.split(".")[0] == "kernlens":
                del sys.modules[name]
                parent_name, _, child = name.rpartition(".")
                parent = sys.modules.get(parent_name)
                if parent is not None and getattr(parent, child, None) is not None:
                    try:
                        delattr(parent, child)
                    except AttributeError:
                        pass
        pkg = sys.modules.get("kernlens.gdb")
        if pkg is not None:
            if saved_attr is missing:
                if getattr(pkg, "facade", missing) is stub:
                    delattr(pkg, "facade")
            else:
                pkg.facade = saved_attr
        if saved_gdb is missing:
            sys.modules.pop("gdb", None)
        else:
            sys.modules["gdb"] = saved_gdb
        if saved_facade is missing:
            sys.modules.pop("kernlens.gdb.facade", None)
        else:
            sys.modules["kernlens.gdb.facade"] = saved_facade
    return module, fake_gdb, fake_kdbg, framework, help_module, formatting


(
    gdbinit, fake_gdb, fake_kdbg, framework, help_module, formatting,
) = _load_gdbinit()


class GdbinitTestBase(unittest.TestCase):
    def setUp(self) -> None:
        fake_gdb.output.clear()
        fake_gdb.expressions.clear()
        fake_gdb.registry.clear()
        fake_gdb.instances.clear()
        # Drop the session owner map too: it lives on the ``gdb`` module
        # by design, so it would otherwise leak between tests.
        setattr(fake_gdb, framework._OWNERS_ATTR, {})
        framework._conflicts.clear()
        # Restore every canned answer the previous test may have mutated.
        fake_kdbg.reset()
        # Re-register the commands the tests cleared.
        gdbinit._register_all()

    # --- helpers --------------------------------------------------------

    def invoke(self, name: str, argument: str = "") -> str:
        name, _, trailing = name.partition(" ")
        argument = f"{trailing} {argument}".strip()
        fake_gdb.output.clear()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            fake_gdb.instances[name].invoke(argument, False)
        return "".join(fake_gdb.output) + out.getvalue() + err.getvalue()

    def walk(self, **overrides: object) -> SimpleNamespace:
        levels = [
            SimpleNamespace(
                name="pgd", index=0x111, entry_addr=0x10888,
                value=0x20003, next_table=0x20000, huge=False,
            ),
            SimpleNamespace(
                name="pud", index=0x000, entry_addr=0x20000,
                value=0x30003, next_table=0x30000, huge=False,
            ),
            SimpleNamespace(
                name="pmd", index=0x000, entry_addr=0x30000,
                value=0x40003, next_table=0x40000, huge=False,
            ),
            SimpleNamespace(
                name="pte", index=0x123, entry_addr=0x40000 + 0x123 * 8,
                value=0x500067, next_table=None, huge=False,
            ),
        ]
        result = SimpleNamespace(
            va=0xFFFF888000001234, root=0x10000, five_level=False,
            levels=levels, phys=0x500234, page_size=1 << 12,
            note="", ok=True,
        )
        for key, value in overrides.items():
            setattr(result, key, value)
        return result


class RegistrationTests(GdbinitTestBase):
    def _canonical(self) -> set[str]:
        return {
            name for name in fake_gdb.registry if name.startswith("kernlens-")
        }

    def test_registers_every_command_and_alias(self) -> None:
        for name in CANONICAL_COMMANDS:
            with self.subTest(command=name):
                self.assertIn(name, fake_gdb.registry)
                self.assertIn("kl-" + name[len("kernlens-"):], fake_gdb.registry)

    def test_aliases_subclass_their_canonical_command(self) -> None:
        for name in CANONICAL_COMMANDS:
            alias = "kl-" + name[len("kernlens-"):]
            with self.subTest(alias=alias):
                self.assertTrue(
                    issubclass(fake_gdb.registry[alias], fake_gdb.registry[name])
                )

    def test_register_all_is_idempotent(self) -> None:
        gdbinit._register_all()
        self.assertEqual(len(self._canonical()), len(CANONICAL_COMMANDS))

    def test_reloading_owns_its_own_names_without_conflicts(self) -> None:
        # Sourcing ``gdbinit.py`` twice is a normal reload: the second
        # pass re-registers the same names and must not report them as
        # taken by "another plugin".  This is the regression guard for the
        # prefix-matching trap -- ``help kl-ks`` also matches
        # ``kl-ksyscalls``, so a per-name ``help`` probe used to flag our
        # own commands as squatters.
        before = dict(framework._owners())
        try:
            framework.register_all()
            self.assertEqual(framework.conflicts(), frozenset())
        finally:
            framework._owners().clear()
            framework._owners().update(before)

    def test_a_foreign_registration_is_reported(self) -> None:
        # A name owned by anything that is not this module instance is a
        # real shadow -- GDB would silently run the other definition.
        framework._owners()["kernlens-bits"] = "some-other-plugin"
        try:
            fake_gdb.output.clear()
            framework.register_all()
            self.assertIn("kernlens-bits", framework.conflicts())
            self.assertIn("kernlens-bits", "".join(fake_gdb.output))
        finally:
            framework._owners()["kernlens-bits"] = framework.__name__

    def test_a_name_taken_before_load_is_reported(self) -> None:
        # A plugin that loaded *before* KernLens leaves no trace in the
        # owner map, so the snapshot from ``help user-defined`` is the
        # only thing that can catch it.
        class Foreign(fake_gdb.Command):  # type: ignore[misc, valid-type]
            def __init__(self) -> None:  # pragma: no cover - not invoked
                super().__init__("kl-quux", fake_gdb.COMMAND_USER)

        framework._owners().pop("kl-quux", None)
        try:
            fake_gdb.output.clear()
            registered = framework._instantiate(
                Foreign, "kl-quux", "alias", frozenset({"kl-quux"}),
            )
            self.assertFalse(registered)
            self.assertIn("kl-quux", framework.conflicts())
            self.assertIn("kl-quux", "".join(fake_gdb.output))
        finally:
            framework._conflicts.discard("kl-quux")
            framework._owners().pop("kl-quux", None)

    def test_the_snapshot_lists_exact_names_only(self) -> None:
        # Regression guard for the probe itself.  ``help <name>`` matches
        # abbreviations and prefixes differently (``help kl-ks`` also
        # reports ``kl-ksyscalls``, ``help pt`` reports the built-in
        # ``ptype``), so a per-name probe flagged our own commands as
        # squatters.  ``help user-defined`` must yield exactly the
        # registered names.
        self.assertEqual(
            framework._user_commands(), frozenset(fake_gdb.registry),
        )

    def test_a_foreign_registration_is_not_claimed(self) -> None:
        framework._owners()["kernlens-bits"] = "some-other-plugin"
        try:
            framework.register_all()
            # ``command_names`` feeds ``kl-help``; listing a name KernLens
            # does not actually own would send users to the wrong help.
            self.assertNotIn("kernlens-bits", framework.command_names)
        finally:
            framework._owners()["kernlens-bits"] = framework.__name__
            gdbinit._register_all()

    def test_load_disables_logger_tags(self) -> None:
        self.assertFalse(fake_kdbg.logger.show_tag)

    def test_alias_dispatch_reaches_command_body(self) -> None:
        self.assertIn("popcount=8", self.invoke("kl-bits", "0xff 3"))

    def test_every_command_exposes_argparse_help(self) -> None:
        out = self.invoke("kl-walk", "--help")
        self.assertIn("usage:", out)
        self.assertIn("--help", out)

    def test_kbase_help_keeps_the_pwndbg_surface(self) -> None:
        # ``kbase`` is a pwndbg port, so every KernLens-only flag has to
        # stay hidden: the help must show exactly pwndbg's options.  The
        # extras are advertised in the Notes instead.
        out = self.invoke("kl-kbase", "--help")
        for option in ("-r, --rebase", "-v, --verbose"):
            self.assertIn(option, out)
        for option in ("--text", "--offset", "--set", "--phys", "--idt"):
            self.assertNotIn(option, out.split("Examples:")[0])

    def test_kbase_notes_advertise_the_hidden_extras(self) -> None:
        out = self.invoke("kl-kbase", "--help")
        self.assertIn("--text", out)
        self.assertIn("--offset", out)

    def test_walk_and_bt_help_show_their_new_flags(self) -> None:
        # ``walk`` and ``bt`` are not pwndbg commands, so their new flags
        # are ordinary, visible options.
        self.assertIn("--pgd", self.invoke("kl-walk", "--help"))
        self.assertIn("--chain", self.invoke("kl-bt", "--help"))


class StatusTests(GdbinitTestBase):
    def test_status(self) -> None:
        out = self.invoke("kl-status")
        self.assertIn("KernLens", out)
        self.assertIn("color", out)
        self.assertIn("_text", out)
        self.assertIn("page_offset", out)
        self.assertIn("nr_cpus=4", out)
        self.assertIn("kl-help", out)

    def test_status_reports_the_slide_the_reader_is_using(self) -> None:
        # ``kl-status`` must ask for the derived slide, not the raw
        # ``kaslr_offset`` attribute that stays 0 until a command sets it.
        fake_kdbg.kaslr_offset = KASLR_SLIDE
        out = self.invoke("kl-status")
        self.assertIn(f"KASLR slide: +{KASLR_SLIDE:#x}", out)
        self.assertIn(f"runtime={RUNTIME_TEXT:#x}", out)


class PagingTests(GdbinitTestBase):
    def test_pte_decode_and_all_leaf_views(self) -> None:
        out = self.invoke("kl-pte", f"0x8000000000123067 {DIRECT_VIRT:#x}")
        self.assertIn("present", out)
        self.assertIn("bit7=PS/PAT", out)
        self.assertIn("P RW US A D NX", out)
        self.assertIn("4k leaf", out)
        self.assertIn("2m leaf", out)
        self.assertIn("1g leaf", out)

    def test_pt_indices(self) -> None:
        out = self.invoke("kl-pt", f"{DIRECT_VIRT:#x}")
        # Index 0x1000 in a 4-level walk: pgd=308 (0x134), pud=53, pte=1.
        self.assertIn("pgd=308", out)
        self.assertIn("pte=1", out)
        self.assertIn("5-level", out)
        self.assertIn(f"2m_base={PAGE_OFFSET_BASE:#x}", out)

    def test_page_direct_map(self) -> None:
        out = self.invoke("kl-page", DIRECT_VIRT)
        self.assertIn("direct=True", out)
        self.assertIn("0x1000", out)
        self.assertIn("pfn=1", out)
        self.assertIn(f"{STRUCT_PAGE:#x}", out)

    def test_page_user_address(self) -> None:
        self.assertIn("user=True", self.invoke("kl-page", "0x1000"))

    def test_addr_analysis_with_tags(self) -> None:
        out = self.invoke("kl-addr", f"{DIRECT_VIRT} 0xfff")
        self.assertIn("Canonical", out)
        self.assertIn("direct=True", out)
        self.assertIn("Tags", out)
        self.assertIn("tags", out.lower())

    def test_addr_error_pointer(self) -> None:
        out = self.invoke("kl-addr", "0xfffffffffffffff2")
        self.assertIn("ERR_PTR", out)
        self.assertIn("errno=14", out)

    def test_walk(self) -> None:
        fake_kdbg.walk_value = self.walk()
        out = self.invoke("kl-walk", f"{DIRECT_VIRT:#x}")
        self.assertIn("pgd", out)
        self.assertIn("Leaf", out)
        self.assertIn("4 KiB", out)

    def test_walk_forwards_an_explicit_root(self) -> None:
        # ``--pgd`` must reach ``kdbg.walk(root=...)`` so a foreign or
        # saved root can be followed without switching to its task.
        fake_kdbg.walk_value = self.walk()
        out = self.invoke("kl-walk", f"{DIRECT_VIRT:#x} --pgd 0x20000")
        self.assertIn("root=0x20000", out)

    def test_walk_short_pgd_matches_pagewalk(self) -> None:
        fake_kdbg.walk_value = self.walk()
        self.assertIn("root=0x30000", self.invoke("kl-walk", f"{DIRECT_VIRT:#x} -p 0x30000"))

    def test_walk_without_pgd_uses_the_live_root(self) -> None:
        # The pre-existing behaviour: the fixture root is the live CR3.
        fake_kdbg.walk_value = self.walk()
        self.assertIn("root=0x10000", self.invoke("kl-walk", f"{DIRECT_VIRT:#x}"))

    def test_page_verbose_delegates_to_addr(self) -> None:
        out = self.invoke("kl-page", f"{DIRECT_VIRT:#x} --verbose")
        self.assertIn("Canonical", out)
        self.assertIn("Alignment", out)

    def test_page_without_verbose_stays_compact(self) -> None:
        # The default must not change: no Canonical/Alignment rows.
        out = self.invoke("kl-page", f"{DIRECT_VIRT:#x}")
        self.assertIn("Class", out)
        self.assertNotIn("Canonical", out)

    def test_pagewalk(self) -> None:
        fake_kdbg.walk_value = self.walk()
        out = self.invoke("kl-pagewalk", f"{DIRECT_VIRT:#x}")
        self.assertIn("pagewalk result", out)

    def test_p2v_and_v2p(self) -> None:
        fake_kdbg.walk_value = self.walk(phys=0x1000)
        out = self.invoke("kl-p2v", "0x1000")
        self.assertIn("Virtual", out)
        self.assertIn("page", out)
        out = self.invoke("kl-v2p", f"{DIRECT_VIRT:#x}")
        self.assertIn("Physical", out)

    def test_pageinfo(self) -> None:
        out = self.invoke("kl-pageinfo", f"{STRUCT_PAGE:#x}")
        self.assertIn("Virtual", out)
        self.assertIn("initialized", out)


class PrimitiveTests(GdbinitTestBase):
    def test_bits(self) -> None:
        out = self.invoke("kl-bits", "0xff 3")
        self.assertIn("popcount=8", out)
        self.assertIn("test=True", out)
        self.assertIn("clear=0xf7", out)
        self.assertIn("toggle=0xf7", out)

    def test_bits_without_bit(self) -> None:
        self.assertIn("popcount=0", self.invoke("kl-bits", "0x0"))

    def test_int(self) -> None:
        out = self.invoke("kl-int", "0x1234 16")
        self.assertIn("unsigned=4660", out)
        self.assertIn("signed=4660", out)
        self.assertIn("LE bytes: 34 12", out)
        self.assertIn("BE bytes: 12 34", out)

    def test_int_signed_view(self) -> None:
        self.assertIn("signed=-1", self.invoke("kl-int", "0xffff 16"))

    def test_bits_rejects_an_out_of_range_bit(self) -> None:
        out = self.invoke("kl-bits", "0xff 64")
        self.assertIn("bit must be between 0 and 63", out)

    def test_bits_negative_bit_is_rejected(self) -> None:
        out = self.invoke("kl-bits", "0xff -1")
        self.assertIn("bit must be between 0 and 63", out)

    def test_bits_zero_value_marks_the_logs_unknown(self) -> None:
        out = self.invoke("kl-bits", "0x0")
        self.assertIn("log2_floor=?", out)

    def test_bits_all_ones_is_not_a_power_of_two(self) -> None:
        out = self.invoke("kl-bits", "0xffffffffffffffff")
        self.assertIn("is_power_of_2=False", out)

    def test_bits_power_of_two(self) -> None:
        out = self.invoke("kl-bits", "0x100")
        self.assertIn("is_power_of_2=True", out)
        self.assertIn("log2_floor=8", out)

    def test_int_rejects_an_unsupported_width(self) -> None:
        out = self.invoke("kl-int", "0x1 7")
        self.assertIn("width must be one of 8, 16, 32, 64", out)

    def test_int_width_boundaries(self) -> None:
        out = self.invoke("kl-int", "255 8")
        self.assertIn("U8[0..255]", out)
        out = self.invoke("kl-int", "0xffffffffffffffff 64")
        self.assertIn("signed=-1", out)


class MemoryTests(GdbinitTestBase):
    def test_sym(self) -> None:
        out = self.invoke("kl-sym", f"{RUNTIME_TEXT:#x}")
        self.assertIn("startup_64", out)
        self.assertIn("head_64.S:1", out)

    def test_read_words(self) -> None:
        out = self.invoke("kl-read", "0x1000 1")
        self.assertIn("0x1000:", out)
        self.assertIn("0x00000000deadbeef", out)

    def test_read_unreadable_stops(self) -> None:
        out = self.invoke("kl-read", "0x1000 2")
        self.assertIn("<unreadable>", out)

    def test_read_ascii(self) -> None:
        out = self.invoke("kl-read", "0x1000 2 --mode ascii")
        self.assertIn("byte(s)", out)
        self.assertIn("41", out)

    def test_kvar(self) -> None:
        fake_kdbg.kernel_addrs["jiffies"] = 0xFFFF888000010000
        fake_kdbg.words["*(unsigned long *)(0xffff888000010000)"] = 0x42
        out = self.invoke("kl-kvar", "jiffies")
        self.assertIn("jiffies", out)
        self.assertIn("0xffff888000010000", out)

    def test_read_field(self) -> None:
        fake_kdbg.fields[(0x1000, "struct slab", "slab_cache")] = 0x2000
        out = self.invoke("kl-read-field", "0x1000 'struct slab' slab_cache")
        self.assertIn("slab_cache", out)

    def test_slab_basic(self) -> None:
        self.assertIn("slab: head=0x1000", self.invoke("kl-slab", "0x1000"))

    def test_slab_detail(self) -> None:
        fake_kdbg.fields[(0x1000, "__head_to_page__", "page")] = 0x2000
        fake_kdbg.fields[(0x2000, "struct slab", "slab_cache")] = 0x3000
        fake_kdbg.fields[(0x2000, "struct slab", "freelist")] = 0x0
        out = self.invoke("kl-slab", "0x1000 --detail")
        self.assertIn("kmalloc-1k", out)
        self.assertIn("freelist", out)

    def test_slabs_list(self) -> None:
        out = self.invoke("kl-slab", "list")
        self.assertIn("kmalloc-1k", out)
        self.assertIn("cache(s) shown", out)

    def test_slabs_info(self) -> None:
        out = self.invoke("kl-slab", "info kmalloc-1k")
        self.assertIn("Slab Cache", out)
        self.assertIn("kmalloc-1k", out)

    def test_slabs_info_matches_the_pwndbg_rows(self) -> None:
        # pwndbg's `slab info` prints these exact labels, in this order;
        # `Slab size` (= PAGE_SIZE << oo_order) used to be missing.
        out = self.invoke("kl-slab", "info kmalloc-1k")
        labels = [
            "Name", "Flags", "Offset", "Slab size",
            "Size (including metadata)", "Align", "Object Size",
        ]
        positions = [out.find(label) for label in labels]
        for label, pos in zip(labels, positions):
            with self.subTest(label=label):
                self.assertNotEqual(pos, -1, label)
        self.assertEqual(positions, sorted(positions))

    def test_slabs_info_slab_size_is_pagesize_shifted_by_order(self) -> None:
        # kmalloc-1k is order 2, so one slab spans 0x1000 << 2 = 0x4000.
        out = self.invoke("kl-slab", "info kmalloc-1k")
        self.assertIn("Slab size: 0x4000", out)
        out = self.invoke("kl-slab", "info kmalloc-64")
        self.assertIn("Slab size: 0x1000", out)

    def test_slabs_info_prints_the_usercopy_window(self) -> None:
        out = self.invoke("kl-slab", "info kmalloc-1k")
        self.assertIn("Usercopy region offset: 0", out)
        self.assertIn(f"Usercopy region size: {KMALLOC_1K_SIZE}", out)

    def test_slabs_info_default_has_no_extra_rows(self) -> None:
        # The default block must stay pwndbg's, row for row: the extras
        # only ever appear when their flag is given.
        out = self.invoke("kl-slab", "info kmalloc-1k")
        for label in ("inuse:", "random:", "reclaim:", "ctor:"):
            with self.subTest(label=label):
                self.assertNotIn(label, out)

    def test_slabs_info_extra_flags_append_rows(self) -> None:
        out = self.invoke(
            "kl-slab", "info kmalloc-1k -i -r --reclaim --ctor",
        )
        self.assertIn("inuse:", out)
        self.assertIn("random:", out)
        self.assertIn("reclaim:", out)
        self.assertIn("ctor:", out)

    def test_slabs_info_inuse_flag_reports_the_stride(self) -> None:
        out = self.invoke("kl-slab", "info kmalloc-1k -i")
        self.assertIn(f"inuse: {KMALLOC_1K_SIZE}", out)

    def test_slabs_info_reclaim_flag_reads_the_flag_bits(self) -> None:
        cache = fake_kdbg.slab_cache("kmalloc-1k")
        cache.flags = ("SLAB_RECLAIM_ACCOUNT",)
        self.assertIn(
            "reclaim: set", self.invoke("kl-slab", "info kmalloc-1k --reclaim"),
        )
        cache.flags = ()
        self.assertIn(
            "reclaim: clear",
            self.invoke("kl-slab", "info kmalloc-1k --reclaim"),
        )

    def test_slabs_info_ctor_flag_reports_absence(self) -> None:
        # `--ctor` must say "none" rather than print a zero address.
        out = self.invoke("kl-slab", "info kmalloc-1k --ctor")
        self.assertIn("ctor: none", out)

    def test_slabs_contains(self) -> None:
        out = self.invoke("kl-slab", f"contains {KMALLOC_1K_ADDR:#x}")
        self.assertIn("kmalloc-1k", out)

    def test_slabs_contains_plain_form_matches_pwndbg(self) -> None:
        # The default must stay pwndbg's single line; `-v` is the extra.
        out = self.invoke("kl-slab", f"contains {KMALLOC_1K_ADDR:#x}")
        self.assertIn("size=", out)
        self.assertIn("object_size=", out)
        self.assertNotIn("Slab head", out)

    def test_slabs_contains_verbose_reports_the_slot(self) -> None:
        fake_kdbg.fields[
            (KMALLOC_1K_ADDR, "__head_to_page__", "page")
        ] = 0xFFFFEA0000000040
        out = self.invoke(
            "kl-slab", f"contains {KMALLOC_1K_ADDR:#x} -v",
        )
        self.assertIn("Slab head", out)
        self.assertIn("Object #: 7 / 16", out)
        self.assertIn("Slab state: partial", out)
        self.assertIn("inuse=3 objects=16 frozen=0", out)

    def test_slabs_contains_verbose_reports_neighbours(self) -> None:
        fake_kdbg.fields[
            (KMALLOC_1K_ADDR, "__head_to_page__", "page")
        ] = 0xFFFFEA0000000040
        out = self.invoke(
            "kl-slab", f"contains {KMALLOC_1K_ADDR:#x} -v",
        )
        self.assertIn(f"{KMALLOC_1K_ADDR - KMALLOC_1K_SIZE:#x}", out)
        self.assertIn(f"{KMALLOC_1K_ADDR + KMALLOC_1K_SIZE:#x}", out)

    def test_slabs_contains_verbose_marks_a_missing_neighbour(self) -> None:
        fake_kdbg.fields[
            (KMALLOC_1K_ADDR, "__head_to_page__", "page")
        ] = 0xFFFFEA0000000040
        fake_kdbg.neighbour_value = (None, None)
        out = self.invoke(
            "kl-slab", f"contains {KMALLOC_1K_ADDR:#x} -v",
        )
        self.assertIn("Neighbours: - / -", out)

    def test_slabs_contains_verbose_reports_a_frozen_slab(self) -> None:
        # A frozen slab is on NO list, so list membership cannot be used
        # to classify it -- only the counters can.
        fake_kdbg.fields[
            (KMALLOC_1K_ADDR, "__head_to_page__", "page")
        ] = 0xFFFFEA0000000040
        fake_kdbg.slab_counters_value = (16, 16, 1)
        out = self.invoke(
            "kl-slab", f"contains {KMALLOC_1K_ADDR:#x} -v",
        )
        self.assertIn("Slab state: frozen", out)

    def test_legacy_kl_slabs_alias_still_routes(self) -> None:
        # ``kl-slabs`` was the old command name; it is kept as an alias of
        # ``kl-slab`` so existing scripts keep working.
        out = self.invoke("kl-slabs", "list")
        self.assertIn("kmalloc-1k", out)

    def test_kl_slab_info_accepts_several_names(self) -> None:
        out = self.invoke("kl-slab", "info kmalloc-1k kmalloc-2k")
        self.assertIn("Slab Cache", out)

    def test_kl_slab_details(self) -> None:
        fake_kdbg.fields[(0x1000, "__head_to_page__", "page")] = 0x2000
        fake_kdbg.fields[(0x2000, "struct slab", "slab_cache")] = 0x3000
        fake_kdbg.fields[(0x2000, "struct slab", "freelist")] = 0x0
        out = self.invoke("kl-slab", "details 0x1000")
        self.assertIn("freelist", out)

    def test_kl_slab_details_reports_the_slab_occupancy(self) -> None:
        # `objects`/`inuse`/`frozen` come from one packed word, so they
        # must be unpacked rather than read as separate fields.
        fake_kdbg.fields[(0x1000, "__head_to_page__", "page")] = 0x2000
        fake_kdbg.fields[(0x2000, "struct slab", "slab_cache")] = 0x3000
        fake_kdbg.fields[(0x2000, "struct slab", "freelist")] = 0x0
        out = self.invoke("kl-slab", "details 0x1000")
        self.assertIn("objects: 16", out)
        self.assertIn("inuse=3", out)
        self.assertIn("frozen=0", out)
        self.assertIn("state: partial", out)

    def test_kl_slab_details_focuses_one_cpu(self) -> None:
        fake_kdbg.fields[(0x1000, "__head_to_page__", "page")] = 0x2000
        fake_kdbg.fields[(0x2000, "struct slab", "slab_cache")] = 0x3000
        fake_kdbg.fields[(0x2000, "struct slab", "freelist")] = 0x0
        out = self.invoke("kl-slab", "details 0x1000 -c 1")
        self.assertIn("cpu 1", out)
        self.assertNotIn("cpu 0", out)

    def test_kl_slab_info_reads_the_cpu_freelists(self) -> None:
        # pwndbg turns both lists on for `info`, so the per-CPU walk runs
        # even when neither -p nor -a is given.
        out = self.invoke("kl-slab", "info kmalloc-1k")
        self.assertIn("cpu 0", out)
        self.assertIn("active=", out)

    def test_kl_slab_requires_arguments(self) -> None:
        self.assertIn("usage:", self.invoke("kl-slab"))

    def test_kl_slab_rejects_an_unknown_subcommand(self) -> None:
        # A bogus token falls through to the bare-address form; the
        # converter raises and the framework must report it like argparse
        # instead of letting it abort the session.
        out = self.invoke("kl-slab", "bogus-command")
        self.assertIn("usage :", out)
        self.assertIn("kl-help kl-slab", out)
        self.assertIn("is not an integer or a resolvable expression", out)

    def test_kl_slab_info_reports_the_node_partial(self) -> None:
        cache = fake_kdbg.slab_cache("kmalloc-1k")
        fake_kdbg.partial[(cache.address, 0)] = (3, 0x3000, 0x4000, 0x5000)
        out = self.invoke("kl-slab", "info kmalloc-1k")
        # pwndbg shows the count against the cache's watermark, and both
        # are hex (indent.aux_hex), so `nr_partial=0x3`.
        self.assertIn("nr_partial=0x3", out)
        self.assertIn("min_partial=", out)
        self.assertIn("0x4000", out)

    def test_kl_slab_info_shows_the_min_partial_watermark(self) -> None:
        # `min_partial` lives on struct kmem_cache; reading it from the
        # node would land on a different field.  The 6.1 VM reports 5.
        cache = fake_kdbg.slab_cache("kmalloc-1k")
        fake_kdbg.partial[(cache.address, 0)] = (3, 0x3000, 0x4000, 0x5000)
        fake_kdbg.words[
            "(unsigned long)&((struct kmem_cache *)0)->min_partial"
        ] = 0x10
        fake_kdbg.words[f"*(unsigned long *)({cache.address + 0x10:#x})"] = 5
        out = self.invoke("kl-slab", "info kmalloc-1k")
        self.assertIn("min_partial=0x5", out)

    def test_kl_slab_info_partial_skips_the_cpu_caches(self) -> None:
        out = self.invoke("kl-slab", "info kmalloc-1k -p")
        self.assertNotIn("active=", out)
        self.assertIn("Partial Slabs", out)

    def test_kl_slab_info_active_skips_the_node_lists(self) -> None:
        out = self.invoke("kl-slab", "info kmalloc-1k -a")
        self.assertIn("active=", out)
        self.assertNotIn("nr_partial", out)

    def test_lookup(self) -> None:
        out = self.invoke("kl-klookup", "commit_creds")
        self.assertIn("commit_creds", out)
        self.assertIn("symbol(s) found", out)

    def test_kbpf(self) -> None:
        out = self.invoke("kl-kbpf", "--progs")
        self.assertIn("BPF_PROG_TYPE_SOCKET_FILTER", out)
        out = self.invoke("kl-kbpf", "--maps --values")
        self.assertIn("BPF_MAP_TYPE_ARRAY", out)

    def test_kbpf_accepts_the_short_pwndbg_options(self) -> None:
        out = self.invoke("kl-kbpf", "-p")
        self.assertIn("BPF_PROG_TYPE_SOCKET_FILTER", out)
        out = self.invoke("kl-kbpf", "-m --values")
        self.assertIn("BPF_MAP_TYPE_ARRAY", out)

    def test_buddydump(self) -> None:
        out = self.invoke("kl-buddydump")
        self.assertIn("free page(s)", out)
        self.assertIn(f"{BUDDY_VIRT:#x}", out)

    # --- kl-buddy: the address -> block locator ------------------------

    def test_kl_buddy_list_prints_one_row_per_order(self) -> None:
        # `nr_free` is the kernel's per-ORDER total (one counter per
        # `free_area`), so the table must not carry a migratetype column.
        out = self.invoke("kl-buddy", "list")
        self.assertIn("nr_free", out)
        self.assertIn("pages(1<<order)", out)
        self.assertNotIn("migratetype", out)
        self.assertIn("2 non-empty order(s)", out)

    def test_kl_buddy_list_multiplies_pages_by_order(self) -> None:
        out = self.invoke("kl-buddy", "list")
        # DMA order 10 with 3 blocks = 3072 pages.
        self.assertIn("3072", out)

    def test_kl_buddy_list_filters_by_order(self) -> None:
        out = self.invoke("kl-buddy", "list -o 0")
        self.assertIn("1 non-empty order(s)", out)
        self.assertNotIn("3072", out)

    def test_kl_buddy_info_reports_the_block_head(self) -> None:
        out = self.invoke("kl-buddy", "info pfn:0x400")
        self.assertIn("DMA", out)
        self.assertIn("Status: free", out)
        self.assertIn("Order: 10", out)
        self.assertIn("0 / 1024 pages", out)
        self.assertIn("(block head)", out)
        self.assertIn("Own block head: order 10", out)

    def test_kl_buddy_info_reports_a_position_inside_the_block(self) -> None:
        out = self.invoke("kl-buddy", "info pfn:0x425")
        self.assertIn("37 / 1024 pages", out)
        self.assertIn("0x25000 bytes into the block", out)
        # A page inside someone else's block is NOT its own head.
        self.assertIn("Own block head: none", out)

    def test_kl_buddy_order_is_per_order_not_per_migratetype(self) -> None:
        # The regression this guards: summing per-migratetype "counters"
        # used to read the next free_area's list pointers and report
        # impossible values (111 blocks in a 128 MiB guest).
        out = self.invoke("kl-buddy", "list -o 10")
        self.assertNotIn("111", out)

    def test_kl_buddy_info_without_an_order_reports_no_position(self) -> None:
        fake_kdbg.buddy_order_value = None
        out = self.invoke("kl-buddy", "info pfn:0x500")
        self.assertIn("Status: allocated", out)
        self.assertIn("the order is only recorded while a block is free", out)
        # Position must not be invented for an allocated page.
        self.assertNotIn("Position: 0", out)
        self.assertIn("Position: -", out)

    def test_kl_buddy_info_rejects_an_unresolvable_address(self) -> None:
        out = self.invoke("kl-buddy", "info")
        self.assertIn("usage:", out)

    def test_kl_buddy_info_marks_an_unmanaged_pfn(self) -> None:
        out = self.invoke("kl-buddy", "info pfn:0x9000000")
        self.assertIn("not managed", out)

    def test_kl_buddy_freelist_expands_one_list(self) -> None:
        out = self.invoke(
            "kl-buddy", "freelist -z DMA -o 10 -m Movable -v",
        )
        self.assertIn("free_area[order 10]", out)
        self.assertIn("mtype=Movable", out)
        self.assertIn("nr_free=3", out)
        self.assertIn("#0", out)
        self.assertIn("#2", out)

    def test_kl_buddy_freelist_reports_an_empty_list(self) -> None:
        out = self.invoke(
            "kl-buddy", "freelist -z DMA -o 10 -m Unmovable -v",
        )
        self.assertIn("this migratetype list is empty", out)

    def test_kl_buddy_freelist_requires_a_full_list_spec(self) -> None:
        out = self.invoke("kl-buddy", "freelist -v")
        self.assertIn("needs -z/--zone, -o/--order and -m/--mtype", out)

    def test_kl_buddy_bare_address_is_info(self) -> None:
        # `kl-slab` accepts a bare address; so does `kl-buddy`.
        out = self.invoke("kl-buddy", "pfn:0x400")
        self.assertIn("Status: free", out)

    def test_kl_buddy_accepts_a_direct_map_address(self) -> None:
        # A direct-map address must translate exactly once.  The
        # regression this guards: `_address_forms` already subtracts
        # page_offset_base, but the caller used to re-prefix the result
        # with ``virt:``, which subtracted the base a second time and
        # reported a negative physical address.
        free_virt = PAGE_OFFSET_BASE + 0x400000   # pfn 0x400, the fixture block
        out = self.invoke("kl-buddy", f"info {free_virt:#x}")
        self.assertNotIn("-0x", out)
        self.assertIn("phys=0x400000", out)
        self.assertIn("Status: free", out)
        self.assertIn("Order: 10", out)

    def test_kl_buddy_accepts_a_vmemmap_page_address(self) -> None:
        # The other transformed form: a ``struct page`` pointer.  It sits
        # above page_offset_base, so the vmemmap reading must be tried
        # first or the address is mistaken for a direct-map one.
        page = VMEMMAP_BASE + 0x400 * 64
        out = self.invoke("kl-buddy", f"info {page:#x}")
        self.assertIn("phys=0x400000", out)
        self.assertIn("Status: free", out)

    def test_kl_buddy_rejects_a_wild_physical_address(self) -> None:
        # Below every base and far past any RAM: no reading is plausible,
        # so the command reports that it cannot resolve the value rather
        # than guessing at a page.
        out = self.invoke("kl-buddy", f"info {1 << 60:#x}")
        self.assertIn("cannot resolve", out)

    def test_kdmabuf(self) -> None:
        out = self.invoke("kl-kdmabuf")
        self.assertIn("DMA-buf", out)
        self.assertIn("system", out)
        self.assertIn("system_heap_buffer", out)

    def test_bt_and_chain(self) -> None:
        self.assertIn("bt: 5 frames", self.invoke("kl-bt", "5"))
        self.assertIn("func_a <- func_b", self.invoke("kl-chain"))

    def test_bt_defaults_to_eight_frames(self) -> None:
        self.assertIn("bt: 8 frames", self.invoke("kl-bt"))

    def test_bt_rejects_an_out_of_range_depth(self) -> None:
        out = self.invoke("kl-bt", "0")
        self.assertIn("depth must be between 1 and 128", out)
        out = self.invoke("kl-bt", "129")
        self.assertIn("depth must be between 1 and 128", out)

    def test_chain_defaults_to_eight_frames(self) -> None:
        self.assertIn("func_a <- func_b", self.invoke("kl-chain"))

    def test_bt_chain_selects_the_compact_view(self) -> None:
        out = self.invoke("kl-bt", "5 --chain")
        self.assertIn("func_a <- func_b", out)
        # It is the chain view, not the framed backtrace.
        self.assertNotIn("bt: 5 frames", out)

    def test_bt_chain_validates_the_depth(self) -> None:
        out = self.invoke("kl-bt", "0 --chain")
        self.assertIn("depth must be between 1 and 128", out)

    def test_sym_reports_an_unknown_address(self) -> None:
        out = self.invoke("kl-sym", "0x9999")
        self.assertIn("?", out)

    def test_read_of_an_unreadable_range_stops_early(self) -> None:
        out = self.invoke("kl-read", "0x9999 2")
        self.assertIn("<unreadable>", out)

    def test_read_ascii_mode(self) -> None:
        out = self.invoke("kl-read", "0x1000 1 --mode ascii")
        self.assertIn("A", out)

    def test_kvar_reports_an_unknown_symbol(self) -> None:
        out = self.invoke("kl-kvar", "no_such_var")
        self.assertIn("cannot resolve", out)

    def test_read_field_reports_an_unreadable_field(self) -> None:
        out = self.invoke(
            "kl-read-field", "0x1000 'struct slab' no_such_field",
        )
        self.assertIn("no_such_field", out)

    def test_slabs_list_is_empty_without_caches(self) -> None:
        fake_kdbg.slab_caches_value = []
        out = self.invoke("kl-slab", "list")
        self.assertIn("no kmem_cache found", out)

    def test_slabs_info_reports_an_unknown_cache(self) -> None:
        out = self.invoke("kl-slab", "info nope")
        self.assertIn("nope", out)

    def test_slabs_contains_reports_an_unknown_object(self) -> None:
        fake_kdbg.slab_object_value = None
        out = self.invoke("kl-slab", "contains 0x0")
        self.assertIn("does not belong to a SLUB cache", out)

    def test_slab_detail_without_a_page(self) -> None:
        out = self.invoke("kl-slab", "0x1000 --detail")
        self.assertIn("0x1000", out)

    def test_klookup_reports_no_match(self) -> None:
        out = self.invoke("kl-klookup", "definitely_not_a_symbol")
        self.assertIn("no symbol matches", out)

    def test_klookup_apply_explains_the_pwndbg_only_path(self) -> None:
        out = self.invoke("kl-klookup", "commit_creds --apply")
        self.assertIn("commit_creds", out)
        self.assertIn("already current", out)

    def test_klookup_short_apply_alias(self) -> None:
        out = self.invoke("kl-klookup", "commit_creds -a")
        self.assertIn("already current", out)

    def test_klookup_by_address(self) -> None:
        out = self.invoke("kl-klookup", f"{RUNTIME_COMMIT_CREDS:#x}")
        self.assertIn("commit_creds", out)

    def test_kbpf_defaults_to_programs(self) -> None:
        out = self.invoke("kl-kbpf")
        self.assertIn("prog", out.lower())

    def test_buddydump_empty_zone(self) -> None:
        out = self.invoke("kl-buddydump", "--zone none")
        self.assertIn("no free pages matched", out)

    def test_buddydump_find_accepts_hex(self) -> None:
        # ``-f/--find`` is an address, so it must parse ``0x...`` (pwndbg
        # uses ``type=int`` so it only accepts decimal).
        out = self.invoke("kl-buddydump", f"-f {BUDDY_PHYS:#x}")
        self.assertNotIn("invalid int value", out)
        self.assertIn(f"{BUDDY_VIRT:#x}", out)

    def test_kdmabuf_without_buffers(self) -> None:
        fake_kdbg.dmabufs_value = []
        out = self.invoke("kl-kdmabuf")
        self.assertIn("no dma-bufs found", out)


class CpuTests(GdbinitTestBase):
    def test_cpu(self) -> None:
        out = self.invoke("kl-cpu")
        self.assertIn("nr_cpus=4", out)
        self.assertIn("0-3 (4/4)", out)

    def test_cpu_with_holes(self) -> None:
        fake_kdbg.online = {0, 1, 3}
        out = self.invoke("kl-cpu", "2")
        self.assertIn("0-1,3 (3/4)", out)

    def test_cpu_rejects_out_of_range(self) -> None:
        out = self.invoke("kl-cpu", "9")
        self.assertIn("out of range", out)

    def test_percpu(self) -> None:
        # ``current_task`` exists on 6.1 (pcpu_hot is 6.8+); use a symbol the
        # target actually has so the test matches the real kernel.
        out = self.invoke("kl-percpu", "current_task 0")
        self.assertIn("current_task", out)
        self.assertIn(f"{CURRENT_TASK_CPU0:#x}", out)

    def test_percpu_rejects_kernel_symbol(self) -> None:
        fake_kdbg.words["(unsigned long)&jiffies"] = 0xFFFFFFFF81000000
        out = self.invoke("kl-percpu", "jiffies 0")
        self.assertIn("not a per-CPU symbol", out)

    def test_msr_list_and_read(self) -> None:
        fake_gdb.expressions["$lstar"] = 0xFFFFFFFF81000000
        out = self.invoke("kl-msr", "--list")
        self.assertIn("MSR_LSTAR", out)
        out = self.invoke("kl-msr", "MSR_LSTAR")
        self.assertIn("0xc0000082", out)

    def test_msr_write(self) -> None:
        out = self.invoke("kl-msr", "MSR_TSC_AUX --write 1")
        self.assertIn("wrote", out)

    def test_msr_range(self) -> None:
        fake_gdb.expressions["$efer"] = 0xD01
        fake_gdb.expressions["$star"] = 0x0
        out = self.invoke("kl-msr", "--range 0xc0000080-0xc0000081")
        self.assertIn("0xc0000080", out)

    def test_msr_positional_wins_over_range(self) -> None:
        # pwndbg checks the explicit MSR first (`if msr: ... elif msr_range:`),
        # so only one value is printed when both are given.
        fake_gdb.expressions["$efer"] = 0xD01
        fake_gdb.expressions["$star"] = 0x0
        out = self.invoke("kl-msr", "MSR_EFER --range 0xc0000080-0xc0000081")
        self.assertIn("0xc0000080", out)
        self.assertNotIn("0xc0000081", out)

    def test_msr_write_without_a_register_prints_usage(self) -> None:
        self.assertIn("usage:", self.invoke("kl-msr", "-w 1"))

    def test_msr_without_arguments_prints_help(self) -> None:
        self.assertIn("usage:", self.invoke("kl-msr"))

    def test_msr_rejects_a_bad_range(self) -> None:
        out = self.invoke("kl-msr", "--range 0xc0000080")
        self.assertIn("range must look like", out)

    def test_msr_rejects_a_reversed_range(self) -> None:
        out = self.invoke("kl-msr", "--range 0xc0000103-0xc0000080")
        self.assertIn("must not exceed", out)

    def test_msr_unknown_register_has_no_gdb_variable(self) -> None:
        out = self.invoke("kl-msr", "0x1234")
        self.assertIn("no GDB register", out)

    def test_msr_write_unknown_register(self) -> None:
        out = self.invoke("kl-msr", "0x1234 --write 1")
        self.assertIn("no GDB register to write", out)

    def test_cpu_defaults_to_the_current_cpu(self) -> None:
        fake_kdbg.cur_cpu_value = 2
        out = self.invoke("kl-cpu")
        self.assertIn("current=2", out)

    def test_cpu_reports_an_offline_cpu(self) -> None:
        fake_kdbg.online = {0, 1, 3}
        out = self.invoke("kl-cpu", "2")
        self.assertIn("off", out)

    def test_cpu_rejects_a_negative_id(self) -> None:
        out = self.invoke("kl-cpu", "-1")
        self.assertIn("cpu must be >= 0", out)

    def test_cpu_handles_an_unknown_current_cpu(self) -> None:
        fake_kdbg.cur_cpu_value = None
        out = self.invoke("kl-cpu")
        self.assertIn("current=?", out)

    def test_percpu_rejects_an_empty_symbol(self) -> None:
        out = self.invoke("kl-percpu", "& 0")
        self.assertIn("must not be empty", out)

    def test_percpu_rejects_an_out_of_range_cpu(self) -> None:
        out = self.invoke("kl-percpu", "current_task 9")
        self.assertIn("out of range", out)

    def test_percpu_reports_an_unresolvable_symbol(self) -> None:
        out = self.invoke("kl-percpu", "no_such_symbol 0")
        self.assertIn("cannot resolve", out)

    def test_percpu_reports_a_missing_cpu_offset(self) -> None:
        fake_kdbg.percpu_off_base = None
        out = self.invoke("kl-percpu", "current_task 0")
        self.assertIn("cannot read __per_cpu_offset", out)

    def test_percpu_accepts_a_zero_based_symbol(self) -> None:
        # A per-CPU symbol's bare value is its offset in the section
        # (``0x1fb80`` for ``current_task``), because ``__per_cpu_start``
        # is a genuine zero.  ``kvar_addr`` adds the KASLR slide, which
        # would turn that offset into an address far outside the section;
        # the command must read the raw bare value instead.  This asserts
        # the exact address the real kernel resolves.
        out = self.invoke("kl-percpu", "current_task 0")
        self.assertIn(f"{CURRENT_TASK_CPU0:#x}", out)
        self.assertNotIn("cannot resolve", out)


class KernelBaseTests(GdbinitTestBase):
    def test_base_runtime(self) -> None:
        out = self.invoke("kl-base")
        self.assertIn("kernel base", out)
        self.assertIn(f"{RUNTIME_TEXT:#x}", out)
        self.assertIn("runtime", out)

    def test_base_default_when_not_running(self) -> None:
        fake_kdbg.kbase_result = None
        out = self.invoke("kl-base")
        self.assertIn("could not be detected", out)

    def test_kbase(self) -> None:
        out = self.invoke("kl-kbase")
        self.assertIn("text base", out)
        self.assertIn(f"{LINK_TEXT:#x}", out)

    def test_kbase_set(self) -> None:
        out = self.invoke("kl-kbase", "--set")
        self.assertIn("KASLR", out)
        self.assertEqual(fake_kdbg.kaslr_offset, KASLR_SLIDE)

    def test_kaslr(self) -> None:
        out = self.invoke("kl-kaslr", f"{RUNTIME_TEXT:#x}")
        self.assertIn("KASLR offset", out)

    def test_kaslr_offset(self) -> None:
        out = self.invoke("kl-kaslr-offset", f"{KASLR_SLIDE:#x}")
        self.assertIn("KASLR offset", out)
        self.assertEqual(fake_kdbg.kaslr_offset, KASLR_SLIDE)

    def test_kbase_idt(self) -> None:
        fake_kdbg.idt_info = SimpleNamespace(
            base=0xFFFFFE0000000000, limit=0xFFF, count=2, source="monitor",
        )
        fake_kdbg.idt_entries[0] = SimpleNamespace(
            offset=0xFFFFFFFF81000000, selector=0x10, gate_type=0xE,
            ist=0, dpl=0, present=True, is_kernel_gate=True,
        )
        out = self.invoke("kl-kbase", "--idt 1")
        self.assertIn("idt", out)
        self.assertIn("kernel", out)

    def test_kbase_idt_marks_present_and_absent_gates(self) -> None:
        fake_kdbg.idt_info = SimpleNamespace(
            base=0xFFFFFE0000000000, limit=0xFFF, count=3, source="monitor",
        )
        fake_kdbg.idt_entries[0] = SimpleNamespace(
            offset=0xFFFFFFFF81000000, selector=0x10, gate_type=0xE,
            ist=0, dpl=0, present=True, is_kernel_gate=True,
        )
        fake_kdbg.idt_entries[1] = SimpleNamespace(
            offset=0xFFFFFFFF81000100, selector=0x10, gate_type=0xE,
            ist=0, dpl=0, present=True, is_kernel_gate=False,
        )
        fake_kdbg.idt_entries[2] = SimpleNamespace(
            offset=0, selector=0, gate_type=0,
            ist=0, dpl=0, present=False, is_kernel_gate=False,
        )
        out = self.invoke("kl-kbase", "--idt 0")
        self.assertIn("idt[0]", out)
        self.assertIn("absent", out)

    def test_kbase_idt_without_tables(self) -> None:
        fake_kdbg.idt_info = None
        out = self.invoke("kl-kbase", "--idt 4")
        self.assertIn("cannot locate the IDT", out)

    def test_base_without_link_text_uses_the_kaslr_guess(self) -> None:
        # No ``kaslr_offset`` on the result forces the derived fallback.
        fake_kdbg.kbase_result = SimpleNamespace(
            base=RUNTIME_TEXT, handler=None, handler_symbol=None,
            idt=None, method="symbol", link_text=None, kaslr_offset=None,
        )
        out = self.invoke("kl-base")
        self.assertIn("runtime", out)
        self.assertEqual(fake_kdbg.kaslr_offset, KASLR_SLIDE)

    def test_kaslr_without_link_text_reports_an_error(self) -> None:
        fake_kdbg.link_text_value = None
        out = self.invoke("kl-kaslr", f"{RUNTIME_TEXT:#x}")
        self.assertIn("cannot resolve &_text", out)

    def test_kbase_phys_translates_the_base(self) -> None:
        fake_kdbg.walk_value = self.walk(phys=0x1000)
        out = self.invoke("kl-kbase", "--verbose")
        self.assertIn("0x1000", out)

    def test_kbase_legacy_phys_alias_still_works(self) -> None:
        # ``--phys`` was renamed to pwndbg's ``--verbose``; it stays as a
        # hidden alias so older scripts keep working.
        fake_kdbg.walk_value = self.walk(phys=0x1000)
        out = self.invoke("kl-kbase", "--phys")
        self.assertIn("0x1000", out)

    def test_kbase_rebase_without_a_symbol_file(self) -> None:
        # The fake progspace reports no filename.
        out = self.invoke("kl-kbase", "--rebase")
        self.assertIn("no symbol file is loaded", out)

    def test_kbase_verbose_reports_the_physical_address(self) -> None:
        fake_kdbg.walk_value = self.walk(phys=0x1000)
        out = self.invoke("kl-kbase", "--verbose")
        self.assertIn("Physical", out)
        self.assertIn("0x1000", out)

    def test_kbase_short_verbose_alias(self) -> None:
        fake_kdbg.walk_value = self.walk(phys=0x1000)
        out = self.invoke("kl-kbase", "-v")
        self.assertIn("Physical", out)

    def test_kbase_set_without_a_derived_offset(self) -> None:
        fake_kdbg.kbase_result = SimpleNamespace(
            base=RUNTIME_TEXT, handler=None, handler_symbol=None,
            idt=None, method="symbol", link_text=None, kaslr_offset=None,
        )
        # Give ``kl-base`` nothing to derive from, then ask ``--set``.
        fake_kdbg.link_text_value = None
        out = self.invoke("kl-kbase", "--set")
        self.assertIn("cannot derive", out)

    def test_kaslr_offset_masks_to_64_bits(self) -> None:
        self.invoke("kl-kaslr-offset", "0xffffffffffffffff")
        self.assertEqual(fake_kdbg.kaslr_offset, 0xFFFFFFFFFFFFFFFF)

    def test_kbase_text_sets_the_slide(self) -> None:
        # ``--text`` is the folded-in ``kl-kaslr``: the slide can be
        # corrected where kbase reports it.
        out = self.invoke("kl-kbase", f"--text {RUNTIME_TEXT:#x}")
        self.assertIn("KASLR offset", out)
        self.assertEqual(fake_kdbg.kaslr_offset, KASLR_SLIDE)

    def test_kbase_offset_sets_the_slide(self) -> None:
        out = self.invoke("kl-kbase", f"--offset {KASLR_SLIDE:#x}")
        self.assertIn("KASLR offset", out)
        self.assertEqual(fake_kdbg.kaslr_offset, KASLR_SLIDE)

    def test_kbase_text_and_offset_are_mutually_exclusive(self) -> None:
        fake_gdb.output.clear()
        out = self.invoke("kl-kbase", "--text 0x1 --offset 0x2")
        self.assertIn("not allowed with argument", out)

    def test_kaslr_reports_a_hint_when_a_slide_exists(self) -> None:
        out = self.invoke("kl-kbase")
        self.assertIn("--set", out)


class MetadataTests(GdbinitTestBase):
    def test_kcmdline(self) -> None:
        self.assertIn(KCMDLINE, self.invoke("kl-kcmdline"))

    def test_kversion(self) -> None:
        out = self.invoke("kl-kversion")
        self.assertIn(KVERSION, out)
        self.assertIn("6.1.134", out)

    def test_kconfig_all(self) -> None:
        out = self.invoke("kl-kconfig")
        self.assertIn("CONFIG_RANDOMIZE_BASE", out)

    def test_kconfig_one(self) -> None:
        self.assertIn("CONFIG_SMP", self.invoke("kl-kconfig", "SMP"))

    def test_kconfig_missing(self) -> None:
        self.assertIn("not set", self.invoke("kl-kconfig", "NOPE"))

    def test_kconfig_reports_a_missing_table(self) -> None:
        fake_kdbg.kconfig_data = {}
        out = self.invoke("kl-kconfig")
        self.assertIn("cannot read kernel_config_data", out)

    def test_kcmdline_reports_a_missing_cmdline(self) -> None:
        fake_kdbg.kcmdline_value = None
        out = self.invoke("kl-kcmdline")
        self.assertIn("cannot read", out)

    def test_kversion_reports_a_missing_banner(self) -> None:
        fake_kdbg.kversion_value = None
        out = self.invoke("kl-kversion")
        self.assertIn("cannot read", out)

    def test_kmod_reports_no_modules(self) -> None:
        fake_kdbg.modules_value = []
        out = self.invoke("kl-kmod")
        self.assertIn("no kernel modules are loaded", out)

    def test_kmod_reports_an_unreadable_list(self) -> None:
        del fake_kdbg.kernel_addrs["modules"]
        out = self.invoke("kl-kmod")
        self.assertIn("cannot read the modules list", out)

    def test_kmod_reports_an_unknown_name(self) -> None:
        out = self.invoke("kl-kmod", "no_such_module")
        self.assertIn("0 of 2 module(s) shown", out)

    def test_kmod_load_without_a_match(self) -> None:
        out = self.invoke("kl-kmod", "no_such_module -l /tmp/nope.ko")
        self.assertIn("No modules detected with the given filter", out)

    def test_kmod_load_uses_add_symbol_file(self) -> None:
        out = self.invoke("kl-kmod", "kvm -l /tmp/kvm.ko")
        self.assertEqual(
            fake_gdb.executed[-1],
            "add-symbol-file /tmp/kvm.ko 0xffffffffc0020000",
        )
        self.assertIn("loaded /tmp/kvm.ko", out)

    def test_kmod_load_rejects_several_matches(self) -> None:
        out = self.invoke("kl-kmod", "-l /tmp/kvm.ko")
        self.assertIn("Multiple modules detected", out)

    def test_ksyscalls_reports_an_empty_table(self) -> None:
        # An unreadable table: no entries resolved (the real kernel with
        # no debug info behaves this way).
        fake_kdbg.syscalls_empty = True
        out = self.invoke("kl-ksyscalls")
        self.assertIn("cannot read", out)

    def test_kdmesg_reports_an_empty_ring(self) -> None:
        fake_kdbg.dmesg_value = []
        out = self.invoke("kl-kdmesg")
        self.assertIn("no printk records", out)

    def test_kchecksec(self) -> None:
        out = self.invoke("kl-kchecksec")
        self.assertIn("CONFIG_STACKPROTECTOR", out)

    def test_kmod(self) -> None:
        out = self.invoke("kl-kmod")
        self.assertIn("nf_tables", out)
        self.assertIn("kvm", out)

    def test_kmod_filter(self) -> None:
        out = self.invoke("kl-kmod", "kvm")
        self.assertIn("kvm", out)
        self.assertNotIn("nf_tables", out)

    def test_ksyscalls(self) -> None:
        out = self.invoke("kl-ksyscalls")
        self.assertIn("__x64_sys_read", out)
        # The count is a real property of the kernel's sys_call_table.
        self.assertIn(f"{SYSCALL_COUNT} entries found at", out)

    def test_ksyscalls_filter(self) -> None:
        out = self.invoke("kl-ksyscalls", "open")
        self.assertIn("__x64_sys_open", out)
        self.assertNotIn("__x64_sys_read", out)

    def test_kdmesg(self) -> None:
        out = self.invoke("kl-kdmesg")
        self.assertIn("Booting Linux", out)
        self.assertIn("hello", out)

    def test_kdmesg_ctime(self) -> None:
        out = self.invoke("kl-kdmesg", "--ctime")
        self.assertIn("Booting Linux", out)


class ColorTests(GdbinitTestBase):
    def test_color_toggle(self) -> None:
        out = self.invoke("kl-color", "on")
        self.assertTrue(fake_kdbg.color_enabled)
        self.assertIn("on", out)
        out = self.invoke("kl-color", "off")
        self.assertFalse(fake_kdbg.color_enabled)
        self.assertIn("off", out)


class HelpTests(GdbinitTestBase):
    def test_help_overview(self) -> None:
        out = self.invoke("kl-help")
        self.assertIn("KernLens", out)
        self.assertIn("kernel metadata", out)
        self.assertIn("kernlens-status", out)

    def test_help_lists_every_category(self) -> None:
        out = self.invoke("kl-help")
        for definition in gdbinit._ALL_COMMANDS:
            with self.subTest(category=definition.category.value):
                self.assertIn(definition.category.value, out)

    def test_help_lists_every_command(self) -> None:
        out = self.invoke("kl-help")
        for name in CANONICAL_COMMANDS:
            with self.subTest(command=name):
                self.assertIn(name, out)


class ContractTests(GdbinitTestBase):
    def test_registered_commands(self) -> None:
        from contract_spec import CANONICAL_COMMANDS as FROZEN

        registered = {
            name for name in fake_gdb.registry if name.startswith("kernlens-")
        }
        self.assertEqual(registered, set(FROZEN))

    def test_every_command_has_a_kl_alias(self) -> None:
        from contract_spec import CANONICAL_COMMANDS as FROZEN

        for name in FROZEN:
            with self.subTest(command=name):
                self.assertIn("kl-" + name[len("kernlens-"):], fake_gdb.registry)


class PublicApiTests(GdbinitTestBase):
    def test_public_names_are_installed(self) -> None:
        for name in (
            "KAddr", "KPageTable", "IntFmt", "kdbg", "byte_swap64",
            "popcount", "pack_u16", "virt_to_phys", "split_4",
            "KERNLENS_API", "KERNLENS_QUALIFIED", "KERNLENS_PREFIXED",
            "KERNLENS_CLASSES", "KERNLENS_INSTANCES",
        ):
            self.assertIn(name, gdbinit.__dict__, name)


class HelperTests(unittest.TestCase):
    def test_parse_int(self) -> None:
        self.assertEqual(gdbinit._parse_int("0x10"), 16)
        self.assertEqual(gdbinit._parse_int("ff"), 255)

    def test_format_cpu_ranges(self) -> None:
        self.assertEqual(gdbinit._fmt_cpu_ranges([]), "-")
        self.assertEqual(gdbinit._fmt_cpu_ranges([0, 2, 3, 5]), "0,2-3,5")

    def test_parse_depth(self) -> None:
        self.assertEqual(gdbinit._parse_depth(""), 8)
        with self.assertRaises(FakeGdbError):
            gdbinit._parse_depth("0")


class FrameworkHelperTests(GdbinitTestBase):
    """The pwndbg-style argument helpers, exercised against the fake gdb."""

    def test_lex_args_splits_on_whitespace(self) -> None:
        self.assertEqual(
            framework.lex_args("kl-read 0x1000 4 --mode ascii"),
            ["kl-read", "0x1000", "4", "--mode", "ascii"],
        )

    def test_lex_args_preserves_quoted_types(self) -> None:
        self.assertEqual(
            framework.lex_args("0x1000 'struct slab' slab_cache"),
            ["0x1000", "struct slab", "slab_cache"],
        )

    def test_lex_args_falls_back_on_unbalanced_quotes(self) -> None:
        self.assertEqual(
            framework.lex_args("a 'unterminated"),
            ["a", "'unterminated"],
        )

    def test_lex_args_of_empty_line_is_empty(self) -> None:
        self.assertEqual(framework.lex_args(""), [])

    def test_parse_int_arg_accepts_gdb_expressions(self) -> None:
        fake_gdb.expressions["$rsp"] = 0xFFFF888000001234
        self.assertEqual(
            framework.parse_int_arg("$rsp"), 0xFFFF888000001234,
        )

    def test_parse_int_arg_accepts_literals_and_bare_hex(self) -> None:
        self.assertEqual(framework.parse_int_arg("0x10"), 16)
        self.assertEqual(framework.parse_int_arg("42"), 42)
        self.assertEqual(framework.parse_int_arg("ff"), 255)

    def test_parse_int_arg_rejects_garbage(self) -> None:
        import argparse

        with self.assertRaises(argparse.ArgumentTypeError):
            framework.parse_int_arg("not-an-int")

    def test_parse_int_or_str_keeps_unparseable_tokens(self) -> None:
        self.assertEqual(framework.parse_int_or_str("0x10"), 16)
        self.assertEqual(
            framework.parse_int_or_str("kmalloc-1k"), "kmalloc-1k",
        )

    def test_func_name_replaces_underscores(self) -> None:
        def kernlens_kaslr_offset() -> None:
            """Stub."""

        self.assertEqual(
            framework.func_name(kernlens_kaslr_offset),
            "kernlens-kaslr-offset",
        )

    def test_slug_builds_a_class_name(self) -> None:
        self.assertEqual(
            framework._slug("kernlens-kaslr-offset"),
            "KernlensKaslrOffset",
        )

    def test_command_category_values_are_display_strings(self) -> None:
        self.assertEqual(
            framework.CommandCategory.HELP.value, "help",
        )
        self.assertEqual(
            framework.CommandCategory.KERNEL_BASE.value,
            "kernel base & KASLR",
        )

    def test_registry_matches_the_contract(self) -> None:
        self.assertEqual(
            {d.command_name for d in framework.registry()},
            set(CANONICAL_COMMANDS),
        )

    def test_aliases_map_every_kl_name_to_its_command(self) -> None:
        lookup = framework.aliases()
        for name in CANONICAL_COMMANDS:
            alias = "kl-" + name[len("kernlens-"):]
            with self.subTest(alias=alias):
                self.assertEqual(lookup[alias], name)

    def test_every_definition_has_a_summary_and_usage(self) -> None:
        for definition in framework.registry():
            with self.subTest(command=definition.command_name):
                self.assertTrue(definition.summary)
                self.assertTrue(definition.usage)
                self.assertNotIn("usage:", definition.usage)

    def test_epilog_folds_examples_and_aliases(self) -> None:
        definition = help_module.resolve_command("kernlens-help")
        epilog = plain(definition.parser.epilog)
        self.assertIn("Examples:", epilog)
        self.assertIn("kl-help", epilog)

    def test_single_alias_uses_the_singular_label(self) -> None:
        parser = argparse.ArgumentParser(description="stub")
        definition = framework.CommandDefinition(
            lambda: None, parser, framework.CommandCategory.HELP,
            ["kl-stub"], "", "",
        )
        self.assertIn("Alias: kl-stub", plain(definition.parser.epilog))

    def test_no_metadata_leaves_the_epilog_empty(self) -> None:
        parser = argparse.ArgumentParser(description="stub")
        definition = framework.CommandDefinition(
            lambda: None, parser, framework.CommandCategory.HELP,
            [], "", "",
        )
        self.assertIsNone(definition.parser.epilog)

    def test_definition_normalises_examples_and_notes(self) -> None:
        parser = argparse.ArgumentParser(description="stub")
        definition = framework.CommandDefinition(
            lambda: None, parser, framework.CommandCategory.HELP,
            [], "  example  ", "\n note \n",
        )
        self.assertEqual(definition.examples, "example")
        self.assertEqual(definition.notes, "note")

    def test_usage_strips_the_prefix(self) -> None:
        parser = argparse.ArgumentParser(description="stub")
        definition = framework.CommandDefinition(
            lambda: None, parser, framework.CommandCategory.HELP,
            [], "", "",
        )
        self.assertFalse(definition.usage.startswith("usage:"))
        self.assertIn("[-h]", definition.usage)

    def test_summary_is_empty_without_a_description(self) -> None:
        parser = argparse.ArgumentParser()
        definition = framework.CommandDefinition(
            lambda: None, parser, framework.CommandCategory.HELP,
            [], "", "",
        )
        self.assertEqual(definition.summary, "")

    def test_notes_only_uses_the_notice_label(self) -> None:
        parser = argparse.ArgumentParser(description="stub")
        definition = framework.CommandDefinition(
            lambda: None, parser, framework.CommandCategory.HELP,
            [], "", "see the docs",
        )
        epilog = plain(definition.parser.epilog)
        self.assertIn("Notes:", epilog)
        self.assertIn("see the docs", epilog)

    def test_print_help_writes_the_parser(self) -> None:
        definition = help_module.resolve_command("kl-slab")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            definition.print_help()
        self.assertIn("usage:", out.getvalue())


class HelpRenderingTests(unittest.TestCase):
    """The help a user reads must keep the shape its author wrote.

    Every assertion above checks that a string is *present* in the epilog,
    and all of them passed while the rendered help was wrong.  ``argparse``
    re-wraps ``epilog`` as running prose by default, so four example lines
    came out as one:

        Examples: kl-buddy list -o 10 kl-buddy info 0xffff8880032a1000 ...

    and the blank line separating ``Notes:`` from the examples was gone.
    The strings were all there; the output was unusable.  These tests
    render the parser and read the text, which is the only way to see it.
    """

    @staticmethod
    def _rendered(definition: framework.CommandDefinition) -> list[str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            definition.print_help()
        # The section labels are emitted through ``message.notice``, which
        # colourises them, so a rendered line can be "\x1b[35mNotes:\x1b[0m".
        # Strip escapes before asserting on text, or the test fails on the
        # colour rather than on the formatting it is meant to check.
        return plain(out.getvalue()).splitlines()

    def test_examples_keep_one_line_per_invocation(self) -> None:
        # `kl-buddy` has the longest example block, so it is the one that
        # exposes the collapse most clearly.
        definition = help_module.resolve_command("kl-buddy")
        lines = self._rendered(definition)
        self.assertIn("Examples:", lines)
        expected = [
            "kl-buddy list -o 10",
            "kl-buddy info 0xffff8880032a1000",
            "kl-buddy info pfn:0x7400 -v",
            "kl-buddy freelist -o 10 -m Movable -v",
        ]
        for invocation in expected:
            with self.subTest(invocation=invocation):
                self.assertIn(invocation, lines)

    def test_no_line_joins_two_invocations(self) -> None:
        # The specific symptom: two `kl-buddy` invocations on one line.
        for definition in framework.registry():
            if not definition.examples:
                continue
            with self.subTest(command=definition.command_name):
                for line in self._rendered(definition):
                    body = line.strip()
                    if not body.startswith(definition.prog):
                        continue
                    self.assertLessEqual(
                        body.count(definition.prog), 1, line,
                    )

    def test_notes_block_is_separated_from_examples(self) -> None:
        # A blank line before `Notes:` is what makes the two sections
        # distinguishable; without it the label reads as one more example.
        for name in ("kl-buddy", "kl-kbase", "kl-help"):
            with self.subTest(command=name):
                definition = help_module.resolve_command(name)
                lines = self._rendered(definition)
                notes_at = lines.index("Notes:") if "Notes:" in lines else -1
                self.assertGreater(notes_at, 0, "\n".join(lines))
                self.assertEqual(lines[notes_at - 1], "")

    def test_an_option_help_still_wraps(self) -> None:
        # Preserving the epilog must not turn into "never wrap": a long
        # `--help` string has to stay inside the terminal.
        definition = help_module.resolve_command("kl-buddy")
        lines = self._rendered(definition)
        help_lines = [
            i for i, line in enumerate(lines) if "--limit LIMIT" in line
        ]
        self.assertTrue(help_lines, "\n".join(lines))
        index = help_lines[0]
        self.assertLess(index + 1, len(lines))
        self.assertTrue(
            lines[index + 1].startswith(" " * 10),
            f"option help did not wrap or indent: {lines[index + 1]!r}",
        )

    def test_full_help_uses_the_plural_alias_label(self) -> None:
        parser = argparse.ArgumentParser(description="stub")
        definition = framework.CommandDefinition(
            lambda: None, parser, framework.CommandCategory.HELP,
            ["kl-a", "kl-b"], "", "",
        )
        self.assertIn("Aliases: kl-a, kl-b", plain(definition.parser.epilog))


class FormattingHelperTests(GdbinitTestBase):
    """The live ``commands.formatting`` helpers used by the command bodies."""

    def test_parse_int_accepts_hex_and_bare_hex(self) -> None:
        self.assertEqual(formatting.parse_int("0x10"), 16)
        self.assertEqual(formatting.parse_int("ff"), 255)

    def test_parse_int_rejects_garbage(self) -> None:
        with self.assertRaises(FakeGdbError):
            formatting.parse_int("nope")

    def test_parse_int_names_the_field_in_the_error(self) -> None:
        with self.assertRaises(FakeGdbError) as ctx:
            formatting.parse_int("nope", "depth")
        self.assertIn("depth", str(ctx.exception))

    def test_parse_depth_defaults_and_bounds(self) -> None:
        self.assertEqual(formatting.parse_depth(""), 8)
        self.assertEqual(formatting.parse_depth("", default=4), 4)
        self.assertEqual(formatting.parse_depth(" 12 "), 12)
        with self.assertRaises(FakeGdbError):
            formatting.parse_depth("0")
        with self.assertRaises(FakeGdbError):
            formatting.parse_depth("129")

    def test_fmt_cpu_ranges_compacts_runs(self) -> None:
        self.assertEqual(formatting.fmt_cpu_ranges([]), "-")
        self.assertEqual(formatting.fmt_cpu_ranges([3]), "3")
        self.assertEqual(
            formatting.fmt_cpu_ranges([0, 2, 3, 5]), "0,2-3,5",
        )

    def test_module_constants(self) -> None:
        self.assertEqual(formatting.MASK64, 0xFFFFFFFFFFFFFFFF)
        self.assertTrue(issubclass(formatting.GDB_MEMORY_ERROR, Exception))

    def test_page_and_vmemmap_fall_back_to_constants(self) -> None:
        from kernlens import PAGE_OFFSET_BASE, VMEMAP_BASE

        fake_kdbg.kernel_u64 = {}
        self.assertEqual(formatting.page_offset_base(), PAGE_OFFSET_BASE)
        self.assertEqual(formatting.vmemmap_base(), VMEMAP_BASE)

    def test_page_and_vmemmap_use_the_runtime_values(self) -> None:
        fake_kdbg.kernel_u64 = {
            "page_offset_base": 0xFFFF888000000000,
            "vmemmap_base": 0xFFFFEA0000000000,
        }
        self.assertEqual(
            formatting.page_offset_base(), 0xFFFF888000000000,
        )
        self.assertEqual(formatting.vmemmap_base(), 0xFFFFEA0000000000)

    def test_default_base_prefers_link_text(self) -> None:
        from kernlens import KERNEL_BASE

        fake_kdbg.link_text_value = 0xFFFFFFFF81000000
        self.assertEqual(
            formatting.default_base(), 0xFFFFFFFF81000000,
        )
        fake_kdbg.link_text_value = None
        self.assertEqual(formatting.default_base(), KERNEL_BASE)

    def test_kernel_running_reads_the_inferior_pid(self) -> None:
        # The fake inferior always reports pid 1.
        self.assertTrue(formatting.kernel_running())

    def test_writeln_goes_through_gdb_write(self) -> None:
        formatting.writeln("hello")
        self.assertIn("hello\n", "".join(fake_gdb.output))

    def test_style_is_plain_when_colour_is_off(self) -> None:
        from kernlens.output import colors

        fake_kdbg.color_enabled = False
        self.assertEqual(formatting.style("x", colors.LABEL), "x")


class GuardTests(GdbinitTestBase):
    """``OnlyWith*`` guards print an error and skip the body on failure."""

    def test_kernel_symbol_guard_blocks_without_symbols(self) -> None:
        fake_kdbg.link_text_value = None
        out = self.invoke("kl-kmod")
        self.assertIn("needs kernel symbols", out)
        self.assertIn("kernlens-kmod", out)

    def test_kernel_symbol_guard_passes_with_symbols(self) -> None:
        fake_kdbg.link_text_value = 0xFFFFFFFF81000000
        out = self.invoke("kl-kmod")
        self.assertIn("nf_tables", out)
        self.assertNotIn("needs kernel symbols", out)

    def test_debug_info_guard_uses_the_config_fallback(self) -> None:
        # ``kl-kdmesg`` accepts either DEBUG_INFO or a loaded vmlinux.
        fake_kdbg.link_text_value = None
        fake_kdbg.kconfig_data = {"CONFIG_RANDOMIZE_BASE": "y"}
        out = self.invoke("kl-kdmesg")
        self.assertIn("needs kernel debug info", out)

    def test_debug_info_guard_passes_with_debug_info(self) -> None:
        fake_kdbg.link_text_value = None
        fake_kdbg.kconfig_data = {"CONFIG_DEBUG_INFO": "y"}
        out = self.invoke("kl-kdmesg")
        self.assertNotIn("needs kernel debug info", out)
        self.assertIn("Booting Linux", out)

    def test_guard_message_names_the_command(self) -> None:
        fake_kdbg.link_text_value = None
        for command, argument in (
            ("kl-kmod", ""), ("kl-kconfig", ""), ("kl-percpu", "current_task 0"),
        ):
            with self.subTest(command=command):
                out = self.invoke(command, argument)
                self.assertIn("needs kernel", out)
                self.assertIn("kernlens-", out)

    def test_guard_reports_the_canonical_name_not_the_alias(self) -> None:
        fake_kdbg.link_text_value = None
        out = self.invoke("kl-kmod")
        self.assertIn("kernlens-kmod:", out)


class FrameworkInvokeTests(GdbinitTestBase):

    def test_help_flag_prints_the_parser(self) -> None:
        out = self.invoke("kl-walk", "--help")
        self.assertIn("usage:", out)
        self.assertIn("Examples:", out)

    def test_short_help_flag_is_honoured(self) -> None:
        self.assertIn("usage:", self.invoke("kl-walk", "-h"))

    def test_help_shows_the_alias_list(self) -> None:
        # Every command declares exactly one ``kl-`` alias, so the
        # epilog uses the singular label.
        self.assertIn("Alias:", self.invoke("kl-walk", "--help"))
        self.assertIn("kl-walk", self.invoke("kl-walk", "--help"))

    def test_unknown_option_prints_a_guided_error(self) -> None:
        out = self.invoke("kl-walk", "--nope")
        self.assertIn("usage :", out)
        self.assertIn("kl-help kl-walk", out)

    def test_missing_required_argument_prints_a_guided_error(self) -> None:
        out = self.invoke("kl-walk")
        self.assertIn("kl-walk: error:", out)
        self.assertIn("usage :", out)
        self.assertIn("try   : kl-help kl-walk", out)

    def test_argparse_help_writes_to_stdout_only(self) -> None:
        out = self.invoke("kl-walk", "--help")
        self.assertIn("usage:", out)
        self.assertNotIn("error:", out)

    def test_body_receives_parsed_keywords(self) -> None:
        fake_kdbg.kernel_addrs["jiffies"] = 0xFFFF888000010000
        fake_kdbg.words["*(unsigned long *)(0xffff888000010000)"] = 0x42
        self.assertIn("jiffies", self.invoke("kl-kvar", "jiffies"))

    def test_invoke_syncs_colour_state(self) -> None:
        # With the facade colour off, the body must not emit ANSI codes.
        fake_kdbg.color_enabled = False
        self.assertNotIn("\x1b[", self.invoke("kl-bits", "0xff 3"))
        fake_kdbg.color_enabled = True
        self.assertIn("\x1b[", self.invoke("kl-bits", "0xff 3"))

    def test_invoke_of_a_body_error_does_not_raise(self) -> None:
        # ``kl-msr --write`` with an unknown register prints, never raises.
        out = self.invoke("kl-msr", "0x1234 --write 1")
        self.assertIn("no GDB register", out)

    def test_blank_line_uses_the_defaults(self) -> None:
        # ``kl-color`` has only optional arguments; a bare invocation
        # runs the body with its defaults and reports the current state.
        # Assert on the body's own phrasing: the rejection path prints
        # "kl-color: error: argument state: invalid choice ... (choose
        # from 'on', 'off', 'toggle')", which also contains "color:"
        # and "off", so a looser assertion cannot tell them apart.
        out = self.invoke("kl-color")
        self.assertIn("KernLens color:", out)
        self.assertNotIn("invalid choice", out)
        self.assertNotIn("usage :", out)


class LayoutFallbackWarningTests(GdbinitTestBase):
    """A command warns once when a struct layout came from a fallback."""

    def setUp(self) -> None:
        super().setUp()
        framework._warned_layouts.clear()

    def _fake_kernel(self, *types: str) -> SimpleNamespace:
        return SimpleNamespace(layout_fallbacks=lambda: types)

    def _run(self) -> str:
        # ``kl-bits`` has a valid body that always completes, so the
        # post-invoke warning hook is reached.
        return self.invoke("kl-bits", "0xff 3")

    def test_no_warning_when_dwarf_resolved_everything(self) -> None:
        fake_kdbg.kernel = self._fake_kernel()
        out = self._run()
        self.assertNotIn("fallback layouts", out)

    def test_warns_when_a_fallback_was_used(self) -> None:
        fake_kdbg.kernel = self._fake_kernel("struct bpf_map")
        out = self._run()
        self.assertIn("struct bpf_map", out)
        self.assertIn("fallback layouts", out)

    def test_warning_is_emitted_only_once_per_type(self) -> None:
        fake_kdbg.kernel = self._fake_kernel("struct bpf_map")
        self.assertIn("fallback layouts", self._run())
        self.assertNotIn("fallback layouts", self._run())

    def test_new_type_warns_again(self) -> None:
        fake_kdbg.kernel = self._fake_kernel("struct bpf_map")
        self._run()
        fake_kdbg.kernel = self._fake_kernel("struct bpf_map", "struct zone")
        out = self._run()
        self.assertIn("struct zone", out)


class HelpDispatchTests(GdbinitTestBase):
    def test_help_with_a_command_shows_its_parser(self) -> None:
        out = self.invoke("kl-help", "kl-slab")
        self.assertIn("usage:", out)
        self.assertIn("kernlens-slab", out)

    def test_help_accepts_a_canonical_name(self) -> None:
        self.assertIn("usage:", self.invoke("kl-help", "kernlens-walk"))

    def test_help_accepts_an_alias(self) -> None:
        self.assertIn("usage:", self.invoke("kl-help", "kl-walk"))

    def test_help_rejects_a_leading_dash_form(self) -> None:
        # argparse sees a leading-dash token as an option; ``kl-help``
        # never accepted it (the old assertion only matched the usage
        # line argparse printed on its way out).
        out = self.invoke("kl-help", "-kl-slab")
        self.assertNotIn("positional arguments", out)
        self.assertIn("usage :", out)

    def test_help_rejects_a_bare_command_name(self) -> None:
        # Names are namespaced: a bare word would read like a query about
        # a GDB command, and ``kl-help print`` would answer "no command
        # matches" while GDB's own ``help print`` works.
        out = self.invoke("kl-help", "slab")
        self.assertIn("names are namespaced", out)
        self.assertIn("'kl-slab'", out)
        self.assertNotIn("usage:", out)

    def test_help_bare_name_hint_names_the_alias(self) -> None:
        out = self.invoke("kl-help", "walk")
        self.assertIn("'kl-walk'", out)

    def test_help_reports_an_unknown_command(self) -> None:
        out = self.invoke("kl-help", "does-not-exist")
        self.assertIn("no command matches", out)

    def test_help_lists_the_help_command_itself(self) -> None:
        self.assertIn("kernlens-help", self.invoke("kl-help"))

    def test_resolve_command_returns_none_for_empty(self) -> None:
        self.assertIsNone(help_module.resolve_command(""))
        self.assertIsNone(help_module.resolve_command("  "))

    def test_resolve_command_rejects_a_bare_name(self) -> None:
        self.assertIsNone(help_module.resolve_command("slab"))
        self.assertIsNone(help_module.resolve_command("print"))

    def test_suggested_name_maps_a_bare_name_to_its_alias(self) -> None:
        self.assertEqual(help_module.suggested_name("slab"), "kl-slab")
        self.assertEqual(help_module.suggested_name("-walk"), "kl-walk")

    def test_suggested_name_is_silent_when_there_is_nothing_to_suggest(self) -> None:
        self.assertIsNone(help_module.suggested_name("nope"))
        self.assertIsNone(help_module.suggested_name("kernlens-walk"))
        self.assertIsNone(help_module.suggested_name(""))

    def test_resolve_command_finds_every_canonical_command(self) -> None:
        for name in CANONICAL_COMMANDS:
            with self.subTest(command=name):
                definition = help_module.resolve_command(name)
                self.assertIsNotNone(definition)
                self.assertEqual(definition.command_name, name)

    def test_resolve_command_finds_every_alias(self) -> None:
        for name in CANONICAL_COMMANDS:
            alias = "kl-" + name[len("kernlens-"):]
            with self.subTest(alias=alias):
                definition = help_module.resolve_command(alias)
                self.assertIsNotNone(definition)
                self.assertEqual(definition.command_name, name)

    def test_render_overview_omits_empty_categories(self) -> None:
        fake_kdbg.color_enabled = False
        text = help_module.render_overview([])
        headings = set(text.splitlines())
        for category in help_module.GROUP_ORDER:
            with self.subTest(category=category.value):
                self.assertNotIn(category.value, headings)

    def test_render_overview_groups_by_category(self) -> None:
        text = help_module.render_overview(framework.registry())
        for category in help_module.GROUP_ORDER:
            with self.subTest(category=category.value):
                self.assertIn(category.value, text)

    def test_render_command_help_has_no_trailing_blank(self) -> None:
        definition = help_module.resolve_command("kl-slab")
        rendered = help_module.render_command_help(definition)
        self.assertEqual(rendered, rendered.rstrip())
        self.assertIn("usage:", rendered)


class DocumentationTests(unittest.TestCase):
    """The command tables must match what the framework registers."""

    def _documented(self, name: str) -> set[str]:
        text = (GDBINIT_PATH.parent / name).read_text(encoding="utf-8")
        return set(re.findall(r"\| `(kernlens-[a-z0-9-]+)", text))

    def test_english_readme_lists_every_command(self) -> None:
        from contract_spec import CANONICAL_COMMANDS as FROZEN

        self.assertEqual(self._documented("README.md"), set(FROZEN))

    def test_chinese_readme_lists_every_command(self) -> None:
        from contract_spec import CANONICAL_COMMANDS as FROZEN

        self.assertEqual(self._documented("README.zh-CN.md"), set(FROZEN))


class TutorialTests(unittest.TestCase):
    """The generated tutorial must match the capture it was built from.

    The tutorial shows real output, so it is generated rather than
    written: ``tools/tutorial_capture.py`` records what the commands
    printed on a live kernel, and ``tools/gen_tutorial.py`` renders one
    page per command.  These tests re-render and compare, which is what
    catches the two failures that matter -- a page drifting from the
    capture, and a command that has no page at all.
    """

    TUTORIAL = GDBINIT_PATH.parent / "docs" / "tutorial"
    CAPTURE = GDBINIT_PATH.parent / "tools" / "tutorial_capture.json"
    META = GDBINIT_PATH.parent / "tools" / "tutorial_meta.json"

    def _render(self, module: str, extra: tuple[str, ...] = ()) -> int:
        """Run a generator's ``--check`` mode and return its exit code."""
        sys.path.insert(0, str(GDBINIT_PATH.parent))
        try:
            generator = importlib.import_module(f"tools.{module}")
            return generator.main([
                "--capture", str(self.CAPTURE),
                "--meta", str(self.META),
                "--out", str(self.TUTORIAL),
                "--check",
                *extra,
            ])
        finally:
            sys.path.pop(0)

    def test_pages_match_the_capture(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self._render("gen_tutorial"), 0, out.getvalue())

    def test_index_matches_the_capture(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = self._render("gen_tutorial_index")
        self.assertEqual(code, 0, out.getvalue())

    def test_every_command_has_a_page(self) -> None:
        from contract_spec import CANONICAL_COMMANDS as FROZEN

        pages = {p.stem for p in self.TUTORIAL.glob("kl-*.md")}
        expected = {
            "kl-" + name.removeprefix("kernlens-") for name in FROZEN
        }
        self.assertEqual(pages, expected)

    def test_every_page_is_linked_from_the_index(self) -> None:
        index = (self.TUTORIAL / "README.md").read_text(encoding="utf-8")
        linked = set(re.findall(r"\]\((kl-[a-z0-9-]+)\.md\)", index))
        pages = {p.stem for p in self.TUTORIAL.glob("kl-*.md")}
        self.assertEqual(linked, pages)

    def test_no_capture_raised(self) -> None:
        # A capture is a record of what really happened; an invocation
        # that raised means the page would document a broken command.
        capture = json.loads(self.CAPTURE.read_text(encoding="utf-8"))
        failing = [
            row["invocation"] for row in capture["cases"]
            if row["output"].startswith("<EXCEPTION>")
        ]
        self.assertEqual(failing, [])

    def test_pages_have_no_hidden_option_leak(self) -> None:
        # KernLens-only flags are hidden with argparse.SUPPRESS; the
        # tutorial renders the visible surface only, so the sentinel must
        # never reach a page.
        for page in self.TUTORIAL.glob("kl-*.md"):
            with self.subTest(page=page.name):
                self.assertNotIn(
                    "SUPPRESS", page.read_text(encoding="utf-8"),
                )

    def test_tables_are_well_formed(self) -> None:
        # A help string containing a literal pipe would otherwise split a
        # row into extra columns.
        for page in self.TUTORIAL.glob("*.md"):
            columns = None
            for number, line in enumerate(
                page.read_text(encoding="utf-8").splitlines(), 1,
            ):
                if not line.startswith("|"):
                    columns = None
                    continue
                count = len(re.findall(r"(?<!\\)\|", line))
                if columns is None:
                    columns = count
                else:
                    with self.subTest(page=page.name, line=number):
                        self.assertEqual(count, columns, line)

    def test_metadata_carries_only_what_the_renderer_reads(self) -> None:
        """The snapshot must not duplicate text the renderer never uses.

        ``tutorial_meta.json`` is a hand-refreshed dump of each command's
        parser.  It once also carried ``examples`` and ``notes`` -- copies
        of strings that live in the command modules and are rendered from
        there.  Nothing read those copies, so nothing could notice them
        going stale, and they did: six commands disagreed with their own
        source, one of them still containing the typo ``inf`o`` and a
        notes block with its newlines flattened.  Reading the snapshot to
        answer "what does this command say?" gave a different answer from
        reading the command.
    """
        #: Exactly the fields ``render_page`` consumes.
        used = {"name", "aliases", "category", "summary", "usage", "options"}
        for entry in json.loads(self.META.read_text(encoding="utf-8")):
            with self.subTest(command=entry.get("name")):
                self.assertEqual(
                    set(entry), used,
                    "tutorial_meta.json may only carry what the renderer "
                    "reads; text duplicated from the command modules goes "
                    "stale silently because nothing compares it",
                )


class TutorialPlaceholderTests(unittest.TestCase):
    """The tutorial must be regenerable on a *different* boot.

    The prose is hand-written but the addresses it invokes are not
    constants: the KASLR slide, ``page_offset_base`` and ``vmemmap_base``
    all change on every boot.  Twenty-five invocations were typed as
    literals, so re-running the capture on a new boot produced a file
    that no longer matched the prose and the generator refused to write
    anything at all -- the tutorial could only be rebuilt on the machine
    that first produced it, which is the same thing as not being
    rebuildable.

    Invocations now name those values as ``{placeholders}`` filled from
    the capture's own context block.  These tests pin that: no literal
    may reappear, and every placeholder must resolve.
    """

    ROOT = GDBINIT_PATH.parent
    PROSE = ROOT / "tools" / "tutorial_prose.py"
    CAPTURE = ROOT / "tools" / "tutorial_capture.json"

    def _prose(self):
        sys.path.insert(0, str(self.ROOT))
        try:
            return importlib.import_module("tools.tutorial_prose")
        finally:
            sys.path.pop(0)

    def _context(self) -> dict:
        return json.loads(
            self.CAPTURE.read_text(encoding="utf-8")
        )["context"]

    def test_no_invocation_hardcodes_a_boot_value(self) -> None:
        context = self._context()
        # Only the values that actually move between boots; struct
        # offsets and physical addresses are stable for a build.
        boot_values = {
            f"{context[key]:#x}"
            for key in ("slide", "direct", "text", "text_addr",
                        "text_sym", "vmemmap_page", "slab_object")
            if key in context
        }
        offenders = []
        for name, page in self._prose().PAGES.items():
            for section in page.get("sections", []):
                invocation = section.get("invocation") or ""
                for value in boot_values:
                    if value in invocation:
                        offenders.append(
                            f"{name}: {section.get('heading')!r} "
                            f"hardcodes {value}"
                        )
        self.assertEqual(offenders, [])

    def test_every_placeholder_resolves(self) -> None:
        # A typo would otherwise surface as a SystemExit during a capture
        # that takes a live kernel to reproduce.
        context = self._context()
        unknown = []
        for name, page in self._prose().PAGES.items():
            for section in page.get("sections", []):
                invocation = section.get("invocation") or ""
                for key in re.findall(r"\{([a-z_]+)\}", invocation):
                    if key not in context:
                        unknown.append(f"{name}: {{{key}}}")
        self.assertEqual(unknown, [])

    def test_the_context_carries_every_placeholder(self) -> None:
        # The reverse direction: a key the prose never uses is dead
        # weight, and a key that disappears from the capture breaks a
        # page.  Both are worth seeing in one place.
        context = self._context()
        used = set()
        for page in self._prose().PAGES.values():
            for section in page.get("sections", []):
                used |= set(re.findall(
                    r"\{([a-z_]+)\}", section.get("invocation") or "",
                ))
        self.assertTrue(used, "no placeholders found; the test is inert")
        self.assertLessEqual(used, set(context))


if __name__ == "__main__":
    unittest.main()