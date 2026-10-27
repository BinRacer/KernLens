<div align="center">
  <a href="https://github.com/BinRacer/KernLens">
    <img src="images/banner.svg" alt="KernLens" style="width:100%; max-width:100%; margin-top:0; margin-bottom:-0.5rem">
  </a>

  <p>
    <a href="./README.md">English</a> | <a href="./README.zh-CN.md">简体中文</a>
  </p>

  <p>
    Linux kernel introspection for GDB — from raw memory and page tables to SLUB internals and symbol resolution.
  </p>

  <p>
    <a href="https://github.com/BinRacer/KernLens"><img src="https://img.shields.io/badge/GitHub-KernLens-181717.svg" alt="GitHub: KernLens"></a>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License: GPL v3"></a>
    <img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-informational" alt="Python 3.10-3.13">
    <img src="https://img.shields.io/badge/GDB-introspection-informational" alt="GDB introspection">
  </p>
</div>

## Overview

KernLens is a pure-Python toolkit for Linux kernel debugging: byte-order
encoding, bit operations, x86_64 address classification, page-table math,
integer formatting, and structured logging.  `core/` and `output/`
run without gdb; the `gdb/` package is the companion that wires the
same logger and styler to live-memory inspection.

## Layout

```
kernlens/                          # repository root
├── src/kernlens/
│   ├── __init__.py               # re-exports the public API
│   ├── core/                     # pure Python: constants, bitops, codec, fmt, addr, paging
│   ├── output/                   # palette, levels, logger, styler
│   ├── gdb/                      # one module per adapter component
│   │   ├── config.py ... facade.py
│   │   ├── api.py                # public API for sourced scripts
│   │   └── __init__.py           # lazy component exports
│   └── py.typed                  # PEP 561 marker
├── tests/
│   ├── unit/                     # pure-Python tests
│   └── integration/              # adapter + gdbinit tests against fakes
├── examples/                     # slab_snapshot, gdb_tracer, trace, cve_2025_38616_trace
├── gdbinit.py                    # optional ~/.gdbinit entry point
├── docs/
│   ├── architecture.md           # layout, API map, and design notes
│   └── naming.md                 # command and Python naming rules
├── images/banner.svg
├── pyproject.toml
├── uv.lock
├── MANIFEST.in
└── CHANGELOG.md
```

Dependency graph: `core.constants` / `core.validation` → the rest of
`core`; `core.bitops` and `core.fmt` → `core.codec`; `output` is
independent of `core`; every `gdb` component → `core.paging` and/or
`output`, and `gdb.facade` → all components.  No cycles.

## Install

Development is managed with [uv](https://docs.astral.sh/uv/).  From a
checkout:

```console
uv sync
uv run python -c "import kernlens; print(kernlens.__version__)"
```

`uv sync` creates `.venv`, installs the project in editable mode, and
installs the `dev` dependency group resolved in `uv.lock`.  Commit
`uv.lock` so local and CI environments use the same versions.

For a runtime-only editable install:

```console
uv pip install -e .
```

Alternatively, copy `src/kernlens/` into your project and import it:

```python
from kernlens import BITS, LE, BE, IntFmt, KAddr, KPageTable, Logger, Styler
```

Python 3.10+ is required.  On Python < 3.12 the only runtime dependency
is `typing-extensions` (for `typing.override`).

The package ships `src/kernlens/py.typed`, so type checkers treat it as a
PEP 561 typed distribution.  The marker is intentionally empty (not
`partial`): every public module is annotated, and the module is included
in both wheels and source distributions.

For gdb, add the package directory to `sys.path` and import the
facade:

```python
import sys
sys.path.insert(0, "/path/to/repo/src")

from kernlens.gdb.facade import kdbg
```

`import kernlens.gdb` itself is safe outside gdb; component names are
resolved lazily.  GDB must be built with Python 3.10 or newer.

## GDB startup file

Add one line to `~/.gdbinit` to make KernLens available in every GDB
session:

```gdb
source /path/to/KernLens/gdbinit.py
```

From a checkout, install it into the user startup file with:

```console
echo "source $(pwd)/gdbinit.py" >> ~/.gdbinit
```

The checkout's `src/` directory is added to `sys.path` automatically, so
this also works without installing the package into GDB's Python.  The
startup file registers commands and installs the public Python API; it
never installs a breakpoint and can be loaded before `file vmlinux`.

### Python API for sourced trace scripts

`gdbinit.py` is sourced into GDB's `__main__` namespace.  It exposes the
package's public classes/constants (`KAddr`, `KPageTable`, `IntFmt`,
`BitOps`, ...), the `KernelDebugger` class and its shared `kdbg` object,
the facade free functions such as `read_kvar`, `kvar_addr`, `walk`,
`sym`, `head_to_page`, `print_slab`, `find_kbase`, and the stateless core
helpers as free functions (`byte_swap64`, `popcount`, `pack_u16`,
`virt_to_phys`, `split_4`, ...).  A script sourced afterwards can use
them directly, without an explicit `from kernlens import ...`:

```gdb
# ~/.gdbinit
source /path/to/KernLens/gdbinit.py
```

```python
# trace.py
print(byte_swap64(0x1122334455667788))
print(popcount(0xFF))
print(split_4(0xFFFF888000001234))
print(pack_u16(0x1234))
print(virt_to_phys(0xFFFF888000001234))
print(read_kvar("jiffies"))
```

```gdb
(gdb) source /path/to/trace.py
```

For names that could collide, prefer the class-qualified form:

```python
BitOps.byte_swap64(value)
KAddr.virt_to_phys(addr)
KPageTable.split_4(addr)
IntCodec.pack_u16(value)
IntFmt.size(1024)
```

`BitOps_byte_swap64(...)` is an identifier-safe alias, and
`KERNLENS_QUALIFIED["BitOps.byte_swap64"]` exposes the same mapping
with dotted keys.  Bare aliases such as `byte_swap64(...)` remain for
short trace scripts.

Stateful components are installed as the same default instances used by
`kdbg`:

```python
logger.info("trace hit")
styler.addr(address)
reader.u64("$rdi")
symbols.sym(pc)
slub.print_slab(head)
```

`KERNLENS_INSTANCES` maps these names (`config`, `logger`, `styler`,
`reader`, `symbols`, `kaslr`, `cpu`, `walker`, `slub`, `kdbg`) to their
objects.  Constructors remain available through `KERNLENS_CLASSES` when
independent state is needed:

```python
local_logger = KERNLENS_CLASSES["Logger"]()
local_styler = KERNLENS_CLASSES["Styler"]()
local_config = KERNLENS_CLASSES["DebugConfig"]()
```

Each constructor creates an independent object; changing
`local_logger`, `local_styler`, or `local_config` does not modify the
global `logger`, `styler`, or `config` instances.

`KERNLENS_API` is a mapping of every installed name for discovery.
Facade free functions are listed in `FACADE_FUNCTIONS`; stateless core
aliases come from `BitOps`, `IntCodec`, `KAddr`, `KPageTable`, and
`IntFmt`.  `kdbg` remains the preferred object-oriented entry point.
See [`examples/trace.py`](examples/trace.py) for a runnable example.

### Getting help

Every command supports discovery from inside GDB:

```gdb
(gdb) kl-help            # list every command, grouped by category
(gdb) kl-help walk       # usage, options, and examples for one command
(gdb) kl-walk --help     # the same detail; -h, help, and ? also work
```

Invalid arguments print a guided message instead of a bare usage line:

```gdb
(gdb) kl-walk
kl-walk: invalid arguments
usage : kl-walk <virtual-address> [4|5]
try   : kl-help walk   (detailed help and examples)
```

`help kl-walk` (GDB's native help) shows the same summary, usage,
arguments, and examples.  The full command table follows.

| Command | Short alias | Purpose |
|---------|-------------|---------|
| `kernlens-help [command]` | `kl-help` | list commands or explain one in detail |
| `kernlens-status` | `kl-status` | version, color, KASLR, `_text`, layout bases, topology |
| `kernlens-slab <list\|info\|contains\|details> [arg] [--verbose] [--cpu <id>] [--node <id>] [--partial] [--active]` | `kl-slab` | SLUB caches: `list`/`info`/`contains` (pwndbg form), `details` for the granular inspector; a bare address prints a cache's slab |
| `kernlens-page <address>` | `kl-page` | classify an address; translate direct-map addresses |
| `kernlens-pte <page-table-entry> [virtual-address]` | `kl-pte` | decode PTE flags; show 4K/2M/1G leaf translations |
| `kernlens-sym <address>` | `kl-sym` | resolve an address to symbol and source line |
| `kernlens-bt [depth]` | `kl-bt` | formatted kernel backtrace |
| `kernlens-chain [depth]` | `kl-chain` | compact `caller <- callee` chain |
| `kernlens-read <address> [count] [--mode ascii]` | `kl-read` | dump 64-bit words with symbols; `--mode ascii` for bytes |
| `kernlens-kvar <symbol>` | `kl-kvar` | read a KASLR-aware kernel global |
| `kernlens-read-field <address> <type> <path>` | `kl-read-field` | read a struct field as an integer |
| `kernlens-addr <address> [tag-mask]` | `kl-addr` | full KAddr analysis, including ERR_PTR/tags |
| `kernlens-pt <virtual-address>` | `kl-pt` | 4/5-level page-table indices and huge-page bases |
| `kernlens-walk <virtual-address> [4\|5]` | `kl-walk` | walk live page tables (CR3) and decode every level |
| `kernlens-pagewalk <vaddr> [--pgd <table>]` | `kl-pagewalk` | pwndbg-style page walk (deepest level first) |
| `kernlens-bits <value> [bit-index]` | `kl-bits` | BitOps popcount/scan and bit operations |
| `kernlens-int <value> [width]` | `kl-int` | signed/unsigned and LE/BE integer views |
| `kernlens-cpu [cpu]` | `kl-cpu` | CPU topology, online mask, current CPU, per-CPU offset |
| `kernlens-percpu <symbol> [cpu]` | `kl-percpu` | resolve a per-CPU symbol to a runtime address |
| `kernlens-msr [name] [--write <v>] [--list] [--range A-B]` | `kl-msr` | read/write x86_64 model-specific registers (via GDB's `$` pseudo-registers) |
| `kernlens-base` | `kl-base` | auto-select the runtime kernel base and KASLR slide |
| `kernlens-kbase [--rebase] [--verbose]` | `kl-kbase` | recover the kernel text base |
| `kernlens-p2v <paddr>` | `kl-p2v` | physical to virtual + `struct page` info |
| `kernlens-v2p <vaddr>` | `kl-v2p` | virtual to physical (pagewalk) + page info |
| `kernlens-pageinfo <struct-page>` | `kl-pageinfo` | `struct page` to virtual/physical + type/refcount |
| `kernlens-kcmdline` | `kl-kcmdline` | print the kernel boot command line |
| `kernlens-kversion` | `kl-kversion` | print the kernel version banner and release |
| `kernlens-kconfig [name] [--load <file>]` | `kl-kconfig` | print kernel `CONFIG_*` options |
| `kernlens-kchecksec` | `kl-kchecksec` | audit kernel hardening `CONFIG_*` options |
| `kernlens-kmod [name] [--load <path>]` | `kl-kmod` | list loaded kernel modules |
| `kernlens-ksyscalls [name]` | `kl-ksyscalls` | list the syscall table |
| `kernlens-kdmesg [--ctime]` | `kl-kdmesg` | print the kernel ring buffer (dmesg) |
| `kernlens-klookup [symbol] [--apply]` | `kl-klookup` | look up kernel symbols from the kallsyms tables |
| `kernlens-kbpf [--verbose] [--break n] [--progs] [--maps] [--values]` | `kl-kbpf` | list BPF programs and maps |
| `kernlens-buddydump [--zone z] [--order n] [--mtype m] [--pcp-only] [--cpu c] [--node n] [--find a]` | `kl-buddydump` | buddy-allocator free lists |
| `kernlens-kdmabuf` | `kl-kdmabuf` | list dma-bufs and their scatterlist chains |
| `kernlens-kaslr <runtime-text-address>` | `kl-kaslr` | set the KASLR slide from runtime `_text` |
| `kernlens-kaslr-offset <offset>` | `kl-kaslr-offset` | set the KASLR slide directly |
| `kernlens-color [on\|off\|toggle]` | `kl-color` | control ANSI color output |

```gdb
(gdb) kl-sym $pc
(gdb) kl-bt 12
(gdb) kl-chain 8
(gdb) kl-read 0xffff8880032a1c40 8
(gdb) kl-kvar jiffies
(gdb) kl-addr 0xffff888000001000
(gdb) kl-pt 0xffff888000001234
(gdb) kl-walk 0xffff888000001234
(gdb) kl-bits 0xff 3
(gdb) kl-int 0x1234 16
(gdb) kl-cpu
(gdb) kl-percpu current_task 0
(gdb) kl-base
(gdb) kl-kbase
```

Both `kl-status` and `kl-kbase` derive the KASLR slide from the live IDT,
so they agree with the slide the reader is using even before `kl-base`
runs.

`kl-msr` reads an MSR through GDB's `$` pseudo-registers (`$efer`,
`$lstar`, `$fs_base`, ...), which is enough for the common MSRs and needs
no code injection.  A remote target only exposes the registers it
implements, so on a kernel that does not export `$lstar` the command
reports `the remote target does not expose this MSR` instead of
inventing a value.  pwndbg gets the rest by executing an `rdmsr`/`wrmsr`
shellcode stub on the debuggee; KernLens deliberately does not run code
in the target, so `--list`, the registers a target does expose, and
`--write` on those registers are the supported surface.

These commands are thin GDB frontends to the pure-Python API:
`KAddr` → `addr`/`page`, `KPageTable`/`PageTableWalker` →
`pt`/`pte`/`walk`, `BitOps` → `bits`, `IntCodec`/`IntFmt` → `int`,
`MemoryReader`/`SymbolResolver`/`CpuInfo` → `kvar`/`read`/`sym`/
`bt`/`chain`/`cpu`/`percpu`, `SlubInspector` → `slab`,
`Kaslr` → `kaslr`/`status`, `Kbase` → `kbase`, and `Styler` → `color`.

### Kernel text base recovery

`kl-base` is the automatic convenience command.  With no running kernel it
prints the default link-time base and clears the KASLR slide.  With a live
kernel it recovers the runtime base (via IDT), immediately applies the
detected slide to `kdbg.kaslr_offset`, and can be run again after a reboot
or re-attach to refresh the value:

```gdb
(gdb) kl-base
kernel base : 0xffffffff99e00000  (runtime)
KASLR offset: +0x18e00000
link _text  : 0xffffffff81000000
method      : symbol
status      : kernel running
```

`kl-kbase` is the lower-level diagnostic form of the same detector: it
prints the base without changing state unless `--set` is given, and can
also print the physical address with `--verbose` (pwndbg's name for the
same output).  The manual overrides `kl-kaslr` and `kl-kaslr-offset`
remain available for cases where the IDT cannot be read.

The detector follows the same idea as pwndbg's `kbase`: the live IDT gate
for exception 0 points at `asm_exc_divide_error` in kernel `.text`.
KernLens reads `IDT` from QEMU's `monitor info registers` (or `$idt` /
`idt_table`), decodes the 16-byte gate, and recovers the base by:

1. comparing the handler with the link-time `asm_exc_divide_error`
   symbol and adding the delta to link-time `_text` (exact with vmlinux);
2. finding the containing QEMU mapping via `monitor info mem`;
3. rounding the handler down to the 2 MiB kernel text alignment.

`kl-kbase --set` applies the detected slide to `kdbg.kaslr_offset`;
`kl-kbase --verbose` prints the physical address of the text base (the
older `--phys` spelling still works but is hidden).  This does not
require pwndbg.

**KASLR is self-healing.**  You do not have to run `kl-base` first: the
memory reader detects the slide on the first KASLR-aware read, and if a
read fails at the current slide (for example after a reboot or
re-attach) it re-detects it and retries.  A debugger that already
carries the relocation (`add-symbol-file vmlinux <runtime>`) is handled
too, because a link-time read is tried last.  Whenever the slide
changes, the reader drops the inspector's address-derived caches, so the
ported commands (kallsyms, modules, syscalls, dmesg, BPF, buddy, SLUB,
dma-buf, ...) keep working across a KASLR change.  `kl-base` and
`kl-kbase --set` remain the explicit way to pin the slide.

The original `kernlens-*` names are kept; `kl-*` is only an alias.
See [`examples/gdbinit.example`](examples/gdbinit.example) for a sample
`~/.gdbinit`.  Loading `gdbinit.py` twice is safe, and the example
`examples/gdb_tracer.py` registers its own commands under the
`kernlens-tracer-` prefix so they never clash with the shipped
`kernlens-slab` / `kernlens-color`.

## Constants

`from kernlens import ...`

| Name | Value | Meaning |
|------|-------|---------|
| `PAGE_SHIFT` | 12 | page-frame shift |
| `PAGE_SIZE` | 4096 | page size in bytes |
| `PAGE_MASK` | 0xFFF | page-offset mask |
| `PTR_BITS` | 64 | pointer width |
| `PTR_HEX_DIGITS` | 16 | hex digits in a full pointer |
| `KERNEL_BASE` | 0xFFFFFFFF81000000 | link-time `_text` |
| `KERNEL_OFFSET` | 0 | default KASLR slide |
| `PAGE_OFFSET_BASE` | 0xFFFF888000000000 | direct-map start |
| `VMEMAP_BASE` | 0xFFFFEA0000000000 | `struct page` array start |
| `USER_TOP` | 0x00007FFFFFFFFFFF | top of user half |
| `KERNEL_BOTTOM` | 0xFFFF800000000000 | bottom of kernel half |
| `VMALLOC_START` | 0xFFFFC90000000000 | vmalloc start |
| `VMALLOC_END` | 0xFFFFE8FFFFFFFFFF | vmalloc end |
| `MODULE_START` | 0xFFFFFFFFC0000000 | module region start |
| `MODULE_END` | 0xFFFFFFFFFEFFFFFF | module region end |
| `MAX_ERRNO` | 4095 | `ERR_PTR` range endpoint |

## BitOps / BITS

All-static namespace; `BITS = BitOps()` is a short alias.  Every
method tolerates arbitrary Python ints and masks its input to width.

| Family | Methods |
|--------|---------|
| byte swap | `byte_swap(v, bits)`, `byte_swap16`, `byte_swap32`, `byte_swap64` |
| width reinterpret | `sign_extend(v, bits)`, `truncate(v, bits)`, `to_u8/16/32/64`, `to_i8/16/32/64`, `coerce(v, int_type)` |
| width metadata | `mask(bits)`, `sign_bit(bits)`, `unsigned_range(bits)`, `signed_range(bits)` |
| population / scan | `popcount`, `leading_zeros(v, bits=64)`, `trailing_zeros`, `first_set`, `last_set` |
| power-of-two | `is_power_of_2`, `next_power_of_2`, `log2_floor`, `log2_ceil` |
| rotate | `rotate_left(v, shift, bits=64)`, `rotate_right(v, shift, bits=64)` |
| align | `align_up`, `align_down`, `is_aligned` |
| single bit | `bit_test`, `bit_set`, `bit_clear`, `bit_toggle` |
| bit field | `extract_bits(v, shift, width)`, `insert_bits(v, field, shift, width)`, `clear_bits` |
| cpumask | `cpumask_test`, `cpumask_count`, `cpumask_first`, `cpumask_next` |

```python
BitOps.byte_swap32(0xdeadbeef)          # 0xefbeadde
BitOps.sign_extend(0x8000, 16)          # -32768
BitOps.popcount(0xff)                   # 8
BitOps.align_up(0x1234, 0x1000)         # 0x2000
BitOps.extract_bits(0x12345678, 8, 8)   # 0x56
BitOps.cpumask_next(0b1010, 1)          # 3
```

## IntCodec / ByteOrderCodec / LE / BE

`IntCodec` is all-static; every multi-byte method takes
`byteorder: ByteOrder = ByteOrder.LE` as its trailing keyword.
`ByteOrderCodec` binds one byte order to the statics so the call site
reads `LE.pack_u16(...)`.

```python
from kernlens import IntCodec, ByteOrder, IntType, LE, BE

IntCodec.pack_u16(0x1234)                          # b'\x34\x12'
IntCodec.pack_u16(0x1234, ByteOrder.BE)            # b'\x12\x34'
IntCodec.unpack_u16(b'\x12\x34', 0, ByteOrder.BE)  # 0x1234
IntCodec.pack_array([1, 2, 3], IntType.U32)        # 12 bytes LE
IntCodec.unpack_array(b'\x01\x00\x02\x00', IntType.U16, 2)  # [1, 2]
IntCodec.is_in_range(-1, IntType.I16)              # True

LE.pack_u16(0x1234)          # b'\x34\x12'
BE.pack_u16(0x1234)          # b'\x12\x34'
BE.unpack_u16(b'\x12\x34')   # 0x1234
```

`ByteOrder.LE.prefix` → `"<"`; `ByteOrder.BE.prefix` → `">"`.
`IntType.<T>` exposes `.code .width .bits .signed .mask .min_value .max_value`.
Every `byteorder` parameter accepts either a `ByteOrder` member or a
bound `ByteOrderCodec`, so `IntCodec.pack_u16(0x1234, BE)` and
`IntFmt.bytes_u16_array(data, byteorder=LE)` are valid.

## IntFmt

All-static; returns plain `str`; never touches color or the logger.

| Family | Methods |
|--------|---------|
| integers | `addr`, `hex`, `hex8/16/32/64`, `off(base, delta)`, `field_off(delta)`, `size`, `pfn`, `page_off`, `mask`, `bits(v, bits=8)`, `flags(v, names)`, `percent(num, den)`, `signed`, `signed_hex`, `timestamp`, `duration_ns` |
| byte strings | `bytes_hex(data, limit=64)`, `bytes_ascii`, `bytes_cstring`, `bytes_dump(data, limit=64, base=0)`, `bytes_u16_array(data, count=None, byteorder=LE)`, `bytes_u32_array`, `bytes_u64_array` |

```python
IntFmt.addr(-1)                        # '0xffffffffffffffff'
IntFmt.size(1536)                      # '1.5K'
IntFmt.off(0xffff888000001000, 0x40)   # '0xffff888000001000+0x40'
IntFmt.flags(0x5, {0: "A", 2: "C"})    # '0x5(A|C)'
IntFmt.bytes_hex(b'\xde\xad')          # 'de ad'
IntFmt.bytes_u16_array(b'\x01\x00\x02\x00')  # '0x0001 0x0002'
```

## KAddr

All-static; masks its input to 64 bits first, so negative Python ints
behave like the unsigned kernel values.

| Family | Methods |
|--------|---------|
| classify | `is_user`, `is_kernel`, `is_canonical(addr, bits=48)`, `is_direct_map(addr, base, size)`, `is_vmemmap`, `is_vmalloc`, `is_module`, `is_text(addr, base=KERNEL_BASE)` |
| translate | `virt_to_phys`, `phys_to_virt`, `phys_to_pfn`, `pfn_to_phys`, `phys_to_page(phys, vmemmap, page_size=64)`, `virt_to_page(addr, ...)`, `page_align`, `page_align_up` |
| KASLR | `kaslr_runtime(link, offset)`, `kaslr_link(runtime, offset)` |
| ERR_PTR | `is_err(ptr)`, `ptr_err(ptr)`, `err_ptr(err)` |
| tags | `ptr_tag(addr, mask)`, `strip_tag(addr, mask)` |

```python
KAddr.is_kernel(0xffff888000000000)        # True
KAddr.virt_to_phys(0xffff888000001000)     # 0x1000
KAddr.phys_to_page(0x1000)                 # 0xffffea0000000040
KAddr.ptr_err(0xfffffffffffffff2)          # 14
KAddr.err_ptr(-14)                         # 0xfffffffffffffff2
```

## KPageTable

All-static; computes addresses and decodes PTE bits, never reads
memory.  4-level and 5-level paging supported; 5-level entry points
take `five_level=True`.

| Family | Methods |
|--------|---------|
| index | `pgd_index(va, five_level=False)`, `p4d_index`, `pud_index`, `pmd_index`, `pte_index`, `page_offset` |
| split | `split_4(va)` → `(pgd, pud, pmd, pte, off)`, `split_5(va)` → `(pgd, p4d, pud, pmd, pte, off)`, `split(va, five_level=False)`, `split_2m`, `split_1g` |
| huge page | `huge_2m_base`, `huge_1g_base`, `is_2m_aligned`, `is_1g_aligned` |
| canonicalize | `canonicalize(va, five_level=False)` |
| entry address | `entry_addr(table_base, index)`, `pgd/p4d/pud/pmd/pte_entry_addr`, `next_table(entry)` |
| PTE decode | `pte_present/writable/user/accessed/dirty/global/nx`, `pte_is_huge`, `pte_phys`, `pte_pfn`, `pte_flags`, `make_pte(phys, flags=0)` |
| leaf → PA | `pte_to_phys`, `pmd_to_phys`, `pud_to_phys` |

Class constants: `PTE_PRESENT RW USER PWT PCD ACCESSED DIRTY PAT GLOBAL PS NX`, `PTE_ADDR_MASK`, and the geometry constants (`BITS_PER_LEVEL`, `ENTRY_SIZE`, `PTE_SHIFT`, `HUGE_2M_SHIFT`, `HUGE_1G_SHIFT`, `PGD_SHIFT_4/5`, `PHYS_BITS`).

```python
KPageTable.split_4(0xffff888000001234)
# (0x111, 0x000, 0x000, 0x001, 0x234)

KPageTable.split_5(0xffff800000001234)
# (0x1ff, 0x100, 0x000, 0x000, 0x001, 0x234)

pte = 0x8000000000123067
KPageTable.pte_present(pte)   # True
KPageTable.pte_phys(pte)      # 0x123000
KPageTable.pte_pfn(pte)       # 0x123
KPageTable.pte_flags(pte)     # ['P', 'RW', 'US', 'A', 'D', 'NX']

KPageTable.pte_to_phys(pte, 0xffff888000001abc)   # 0x123abc
```

`KPageTable` only does arithmetic.  To translate a live address,
`kernlens.gdb.walker.PageTableWalker` (bound as `kdbg.walk`)
walks the real tables from `CR3` and reports every level; the
`kernlens-walk` command prints it.  A walk stops cleanly with a `note`
on an unreadable, absent, or non-present entry.

## Logger / LogLevel / Palette

`Palette` is a `str` enum; every value is the SGR sequence.

```python
Palette.RED           # '\x1b[31m'
f"{Palette.RED}"      # '\x1b[31m'
Palette.BRIGHT_RED_BOLD
```

`LogLevel` carries a fixed-width 9-char tag and a `Palette`:

```python
LogLevel.INFO.tag     # '[INFO]   '
LogLevel.INFO.color   # Palette.CYAN
```

`Logger`:

```python
log = Logger()                                # color, tags, stdout
log = Logger(color_enabled=False, show_time=True)
log = Logger(min_level=LogLevel.WARN, stream=io.StringIO())

log.debug("raw=0xdeadbeef")
log.info("hooked __slab_free")
log.success("stage 3 reached")
log.warn("freelist head is stale")
log.error("head_to_page failed")
```

| Method | Purpose |
|--------|---------|
| `set_color_enabled(bool)` / `enable_color()` / `disable_color()` | color toggle |
| `set_min_level(level)` / `is_enabled(level)` | level filter |
| `set_show_tag(bool)` / `set_show_time(bool)` | prefix control |
| `set_stream(stream)` | redirect; `None` restores stdout |
| `once(key, msg, level=INFO) -> bool` | emit once per key |
| `reset_once()` | forget all once keys |
| `throttle(key, interval, msg, level=INFO) -> bool` | emit at most every `interval` seconds |
| `reset_throttle()` | forget all throttle timestamps |
| `counter(key, delta=1) -> int` | accumulate |
| `counters()` / `reset_counters()` | snapshot / clear |
| `summary(*, level=INFO, sort_by="key")` | print all counters |
| `check(cond, ok_msg, *, fail_msg=None, fail_level=WARN) -> bool` | conditional emit |
| `assert_(cond, msg) -> bool` | record `ASSERT: msg` on failure, never raises |
| `fmt_line(level, msg) -> str` | build line without printing |
| `banner(title, *, char="=", width=80, color=CYAN)` | INFO-level banner |
| `rule(*, char="-", width=80, color=DIM)` | INFO-level rule |
| `reset()` | clear once / counters / throttle |

## Styler

Instance methods; construct with optional `color_enabled`,
`key_color`, `value_color`.  Every color argument accepts a
`Palette` member or a raw SGR string.

```python
sty = Styler()
sty = Styler(color_enabled=False)
sty = Styler(key_color=Palette.BRIGHT_YELLOW, value_color=Palette.GREEN)
sty.disable_color(); sty.enable_color()
sty.set_key_color(Palette.BRIGHT_CYAN); sty.set_value_color(Palette.DIM)
sty.set_kv_colors(Palette.CYAN, Palette.GREEN)
```

| Family | Methods |
|--------|---------|
| primitives | `style(text, color)`, `addr(value)` |
| numeric (colored) | `hex(v, *, digits=None, color=DIM)`, `hex8/16/32/64`, `dec(v, color="")`, `size`, `pfn`, `percent`, `bits(v, *, width=8, color=DIM)` |
| align / truncate | `ljust/rjust/center(text, width, *, fill=" ", color="")`, `pad(text, width, *, align="left", fill=" ", color="")`, `truncate(text, width, *, ellipsis="...", color="")` |
| k=v | `kv`, `kv_int`, `kv_hex`, `kv_bool(label, value, *, true_color=None, false_color=None)` |
| containers | `seq`, `list`, `tuple`, `set`, `dict`, `pairs`, `range`, `named(name, items, *, style="[]", ...)`, `kv_seq(label, items, *, style="[]", ...)` |
| layout | `table`, `box`, `chain`, `cols`, `block` |
| transforms | `highlight(text, pattern, *, color=BRIGHT_YELLOW_BOLD)`, `indent(text, *, level=1, width=2)` |
| groups | `fields(pairs, *, sep="  ", ...)`, `kv_group(pairs, *, assign=" = ", ...)` |
| symbols | `tick()`, `cross()`, `bullet()`, `arrow()` |
| progress | `bar(value, max_value, *, width=20, ...)` |

### Layout signatures

```python
sty.table(headers, rows, *, header_color=CYAN, item_color=None,
          bracket_color=DIM, col_sep="  ", rule="-", fill=" ",
          aligns=None, max_col_width=None)

sty.box(headers, rows, *, header_color=CYAN, item_color=None,
        border_color=DIM, chars="┌┐└┘─│", joints="┬┴┼├┤",
        fill=" ", aligns=None, max_col_width=None)

sty.cols(items, n, *, item_color=None, col_sep="  ", pad=2,
         fill=" ", aligns=None, max_col_width=None)

sty.block(title, lines, *, width=0, border_color=DIM,
          title_color=CYAN, chars="┌┐└┘─", vertical="│")
```

`aligns` accepts one token (`"l"` / `"r"` / `"c"` / `"left"` /
`"right"` / `"center"`) for all columns, or a list for per-column
alignment.  `fill` must be a single character.  `max_col_width`
truncates each cell with `"..."` before sizing the column.

```python
sty.kv("pid", "1234", value_color=Palette.GREEN)   # pid=1234
sty.kv_hex("page", 0xffffea0000a1c000)             # page=0x… (dim)
sty.kv_bool("ready", True)                         # ready=true

sty.list([1, 2, 3])                                # [1, 2, 3]
sty.dict({"pid": 1, "cpu": 0})                     # {pid: 1, cpu: 0}
sty.named("cpus", [0, 1, 2])                       # cpus[0, 1, 2]
sty.kv_seq("slab", {"page": "0xea00"}, style="{}") # slab={page: 0xea00}

print(sty.table(
    ["name", "inuse", "frozen"],
    [["kmalloc-1k", 3, 0], ["kmalloc-64", 7, 1]],
    aligns=["l", "r", "c"],
    max_col_width=20,
))
print(sty.cols(range(6), 3))
print(sty.block("slab", ["page=0xea00", "inuse=3"]))
print(sty.bar(4, 8, width=8))           # [████░░░░] 4/8
```

## gdb/ (gdb side)

Not imported at package level.  Load inside gdb with a normal import
(see [Install](#install)).  The package exposes
`DebugConfig`, `KernelStyler`, `MemoryReader`, `SymbolResolver`,
`Kaslr`, `Kbase`, `IdtEntry`, `IdtInfo`, `KbaseResult`, `CpuInfo`,
`PageTableWalker`, `PageWalk`, `WalkLevel`, `SlubInspector`,
`KernelDebugger`, and the singleton `kdbg`.  Every method listed on
`kdbg` below is also available as a component accessor (`kdbg.logger.*`,
`kdbg.styler.*`, `kdbg.reader.*`, ...).

| Group | Facade methods |
|-------|----------------|
| logging | `debug info success warn error once throttle counter summary check assert_ banner rule` |
| styler | `style addr hex hex8 hex16 hex32 hex64 dec size pfn percent bits ljust rjust center pad truncate kv kv_int kv_hex kv_bool seq list tuple set dict pairs range named kv_seq table box cols block highlight indent fields kv_group tick cross bullet arrow bar` |
| kernel styler | `fn loc depth_marker branch fl_tag kv_cpu kv_online kv_err kv_trans` |
| reader | `u64 read_kvar kvar_addr arg read_field` |
| symbols | `sym line backtrace chain color_chain` |
| kaslr | `bp_spec link_text find_kbase` |
| cpu | `nr_cpus nr_nodes cpu_online cur_cpu percpu_off` |
| page tables | `walk` |
| slub | `page_bytes head_to_page compound_head cache_name cpu_slab_ptr cpu_active_slab cpu_freelist freeptr_offset freeptr_random decode_freeptr freelist_dist partial_info in_partial print_slab` |

```python
kdbg.kaslr_offset = 0x1e000000
text = kdbg.link_text()
if text is not None:
    kdbg.info("_text runtime = " + kdbg.addr(
        text + kdbg.kaslr_offset
    ))
kdbg.print_slab(head)
kdbg.disable_color()           # both logger and styler
```

`KernelDebugger.indent` is bound to the `Styler.indent` text formatter;
the configuration prefix is available separately as `indent_str`.

## Examples

- [`examples/slab_snapshot.py`](examples/slab_snapshot.py) renders a
  slab report with no gdb dependency, using the real test-kernel values
  (a direct-map page and the PTE its live page tables hold, plus the
  real `kmalloc-1k` shape); `--head`, `--page-offset-base`, and
  `--vmemmap-base` point it at any kernel.
- [`examples/gdb_tracer.py`](examples/gdb_tracer.py) installs a
  `kfree` breakpoint plus the `kernlens-tracer-slab` and
  `kernlens-tracer-color` commands inside gdb (prefixed so they do not
  shadow the KernLens commands of the same purpose).
- [`examples/trace.py`](examples/trace.py) is sourced after
  `gdbinit.py` and uses the installed public API directly, without
  `from kernlens import ...`.
- [`examples/cve_2025_38616_trace.py`](examples/cve_2025_38616_trace.py)
  is a CVE-2025-38616 KTLS use-after-free tracer that reuses the API and
  commands already installed by `gdbinit.py`; `trace-start` calls the
  registered `kl-base` command for automatic base selection; it refuses
  to install a manual zero-slide configuration (which would use nokaslr
  addresses), so use `trace-start manual` only after a non-zero
  `kl-kaslr` / `kl-kaslr-offset` selection.  The old
  `kaslr-text` / `kaslr-offset` names remain as thin wrappers around
  those registered commands.
- [`examples/gdbinit.example`](examples/gdbinit.example) is a sample
  `~/.gdbinit` that loads the project-level `gdbinit.py`.

## Combined example

```python
from kernlens import IntFmt, KAddr, KPageTable, Logger, Palette, Styler

log = Logger()
sty = Styler()

head = 0xffff8880032a1c40
phys = KAddr.virt_to_phys(head)
page = KAddr.virt_to_page(head)

log.info(sty.table(
    ["field", "value"],
    [
        ["head",  IntFmt.addr(head)],
        ["phys",  IntFmt.hex64(phys)],
        ["page",  IntFmt.addr(page)],
        ["pfn",   IntFmt.pfn(phys)],
        ["split", str(KPageTable.split_4(head))],
    ],
    aligns=["l", "r"],
))
```

## Testing and development

The test suite is `unittest`-compatible and also runs under pytest.
All development commands go through uv:

```console
uv sync
uv run pytest --cov=kernlens --cov-report=term-missing
uv run ruff check .
```

The stdlib runner remains available inside the uv environment:

```console
uv run python -m unittest discover -s tests/unit
uv run python -m unittest discover -s tests/integration
```

The integration tests install a fake `gdb` module, so no debugger or
kernel is required.  `tests/integration/test_gdbinit.py` additionally
runs the real `gdbinit.py` against a fake `gdb` and a stub facade, so
command registration, argument parsing, and output formatting are
covered without GDB.  `uv sync` installs the package, so `uv run`
commands import the installed distribution rather than relying on
`PYTHONPATH`; `pyproject.toml` also sets `pythonpath = ["src"]` so a
bare `pytest` run works from a checkout.

See [`docs/architecture.md`](docs/architecture.md) for the public API
map, module responsibilities, the SLUB inspection model, and GDB
loading details.  [`docs/naming.md`](docs/naming.md) defines the
command and Python naming rules.  Release history lives in
[`CHANGELOG.md`](CHANGELOG.md).

### Struct layouts: DWARF, then BTF, then a verified fallback

Every struct field offset is resolved on first use through a three-tier
chain, so the inspectors track the exact kernel image they run against --
offsets shift with the kernel version and with `CONFIG_*` (for example
`CONFIG_SECURITY` inserts a `void *security` before
`struct bpf_map::map_type`):

1. **DWARF** -- the loaded `vmlinux`'s debug info (`gdb.parse_and_eval`),
   exact for the build at hand;
2. **BTF** -- the type database embedded in the image
   (`CONFIG_DEBUG_INFO_BTF`), parsed directly by `kernlens.gdb.btf`
   (no `bpftool`, no `libbpf`), for a build whose DWARF is absent;
3. **the fallback registry** in `kernlens/gdb/layouts.py` -- only when
   neither is available.

Each registry entry records where the struct is defined and which kernel
it was verified against (`layouts.VERIFIED_KERNEL`, currently Linux
7.0), and gates its variants on the version and `CONFIG_*`.  Because
those values are only known-good for one configuration, every command
prints a one-time warning when the fallback tier is used:

```console
kl-kbpf: struct bpf_map, struct dma_buf: no debug info; using built-in
fallback layouts that may not match this kernel. Load a matching vmlinux
for exact struct offsets.
```

A BTF blob can also be supplied explicitly (for a remote target with no
usable `.BTF` section) by setting `kdbg.reader.config.btf_path` to a raw
blob or to a `vmlinux` carrying a `.BTF` section.

`tools/gen_layouts.py` keeps the registry honest.  It probes a real
kernel -- a `vmlinux` through GDB's DWARF, or a BTF blob through the
project's own parser (no `bpftool`, no `libbpf`) -- and can verify the
registry against it:

```console
uv run python tools/gen_layouts.py --vmlinux /path/to/vmlinux --check
uv run python tools/gen_layouts.py --btf /sys/kernel/btf/vmlinux --check
uv run python tools/gen_layouts.py --vmlinux /path/to/vmlinux   # report
```

`--check` exits non-zero on any drift, so it can guard a table update in
CI.

## License

GPL-3.0-or-later.  See [`LICENSE`](LICENSE).

## Conventions

- Table-like layout methods (`table`, `box`, `cols`) share `fill` /
  `aligns` / `max_col_width`; `box` and `block` also accept custom
  border characters (`joints`, `vertical`).
- `Styler` output is plain text when `color_enabled=False`; the
  structure is unchanged.
- `IntCodec` and the `IntFmt.bytes_*_array` helpers accept either a
  `ByteOrder` or a `ByteOrderCodec` for their `byteorder` argument.
- `KAddr` / `KPageTable` mask their input to 64 bits; negative Python
  ints behave like unsigned values.
- `Logger.once` / `throttle` / `counter` state lives on the instance;
  `reset()` clears all three at once.
- GDB commands stay short (`kernlens-walk`, `kl-walk`); Python names
  follow [`docs/naming.md`](docs/naming.md) — readable, but no longer
  than necessary, with one spelling per concept.
