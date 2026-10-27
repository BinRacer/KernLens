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
├── examples/                     # runnable scripts, grouped by intent
│   ├── api/                      #   write a script against the API
│   ├── tracing/                  #   trace behaviour as the kernel runs
│   └── breakpoints/              #   stop, or notice, at the right moment
├── gdbinit.py                    # optional ~/.gdbinit entry point
├── docs/
│   ├── architecture.md           # layout, API map, and design notes
│   ├── naming.md                 # command and Python naming rules
│   └── tutorial/                 # one generated page per command, real output
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
# my_script.py -- any file you source afterwards
print(byte_swap64(0x1122334455667788))
print(popcount(0xFF))
print(split_4(0xFFFF888000001234))
print(pack_u16(0x1234))
print(virt_to_phys(0xFFFF888000001234))
print(read_kvar("jiffies"))
```

```gdb
(gdb) source /path/to/my_script.py
```

[`examples/api/installed_api_tour.py`](examples/api/installed_api_tour.py)
is a working version of that file.

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
See [`examples/api/installed_api_tour.py`](examples/api/installed_api_tour.py) for a runnable
example, or [`examples/api/hello_sample.py`](examples/api/hello_sample.py) for the
smallest starting point.

### Getting help

Every command supports discovery from inside GDB:

```gdb
(gdb) kl-help            # list every command, grouped by category
(gdb) kl-help kl-walk    # usage, options, and examples for one command
(gdb) kl-walk --help     # the same detail; -h, help, and ? also work
```

The argument is namespaced: ``kl-help kl-walk`` or ``kl-help
kernlens-walk``.  A bare ``kl-help walk`` is rejected with a hint,
because KernLens deliberately lives in its own ``kl-``/``kernlens-``
namespace -- a bare name would read like a query about a GDB command.

Invalid arguments print a guided message instead of a bare usage line:

```gdb
(gdb) kl-walk
kl-walk: error: the following arguments are required: va
usage : kernlens-walk [-h] [-p ROOT] va [{4,5}]
try   : kl-help kl-walk  (detailed help and examples)
```

`help kl-walk` (GDB's native help) shows the same summary, usage,
arguments, and examples.  The full command table follows.

| Command | Short alias | Purpose |
|---------|-------------|---------|
| `kernlens-help [command]` | `kl-help` | list commands or explain one in detail |
| `kernlens-status` | `kl-status` | version, color, KASLR, `_text`, layout bases, topology |
| `kernlens-slab <list\|info\|contains\|details> [arg] [--verbose] [--cpu <id>] [--node <id>] [--partial] [--active] [--inuse] [--random] [--reclaim] [--ctor]` | `kl-slab` | SLUB caches: `list`/`info`/`contains` (pwndbg form), `details` for the granular inspector; a bare address prints a cache's slab |
| `kernlens-page <address> [--verbose]` | `kl-page` | classify an address; translate direct-map addresses |
| `kernlens-pte <page-table-entry> [virtual-address]` | `kl-pte` | decode PTE flags; show 4K/2M/1G leaf translations |
| `kernlens-sym <address>` | `kl-sym` | resolve an address to symbol and source line |
| `kernlens-bt [depth] [--chain]` | `kl-bt` | formatted kernel backtrace; `--chain` for the compact view |
| `kernlens-chain [depth]` | `kl-chain` | compact `caller <- callee` chain |
| `kernlens-read <address> [count] [--mode ascii]` | `kl-read` | dump 64-bit words with symbols; `--mode ascii` for bytes |
| `kernlens-kvar <symbol>` | `kl-kvar` | read a KASLR-aware kernel global |
| `kernlens-read-field <address> <type> <path>` | `kl-read-field` | read a struct field as an integer |
| `kernlens-addr <address> [tag-mask]` | `kl-addr` | full KAddr analysis, including ERR_PTR/tags |
| `kernlens-pt <virtual-address>` | `kl-pt` | 4/5-level page-table indices and huge-page bases |
| `kernlens-walk <virtual-address> [4\|5] [--pgd <table>]` | `kl-walk` | walk live page tables (CR3) and decode every level |
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
| `kernlens-buddy {list\|info\|freelist} [addr] [--zone z] [--order n] [--mtype m] [--node n] [--verbose]` | `kl-buddy` | locate an address in the buddy allocator: zone, free block, position in that block |
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
same output).  The hidden `--text <addr>` and `--offset <slide>` extras
set the slide here, at the point where the report already shows
`kaslr=+0x...`; they are the equivalents of the manual overrides
`kl-kaslr` and `kl-kaslr-offset`, which remain available for cases where
the IDT cannot be read.

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
See [`examples/api/gdbinit.example`](examples/api/gdbinit.example) for a
sample `~/.gdbinit`.  Loading `gdbinit.py` twice is safe, and the
example [`examples/tracing/gdb_tracer.py`](examples/tracing/gdb_tracer.py)
registers its own commands under the `kernlens-tracer-` prefix so they
never clash with the shipped `kernlens-slab` / `kernlens-color`.

## License

GPL-3.0-or-later.  See [`LICENSE`](LICENSE).
