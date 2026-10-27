<div align="center">
  <a href="https://github.com/BinRacer/KernLens">
    <img src="images/banner.svg" alt="KernLens" style="width:100%; max-width:100%; margin-top:0; margin-bottom:-0.5rem">
  </a>

  <p>
    <a href="./README.md">English</a> | <a href="./README.zh-CN.md">简体中文</a>
  </p>

  <p>
    Read a live Linux kernel from GDB: page tables at every level, SLUB
    caches and object chains, <code>struct page</code>, symbols, KASLR.
  </p>

  <p>
    <a href="https://github.com/BinRacer/KernLens/actions/workflows/ci.yml"><img src="https://github.com/BinRacer/KernLens/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
    <a href="https://github.com/BinRacer/KernLens"><img src="https://img.shields.io/badge/GitHub-KernLens-181717.svg" alt="GitHub: KernLens"></a>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License: GPL v3"></a>
    <img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-informational" alt="Python 3.10-3.13">
    <img src="https://img.shields.io/badge/commands-40-informational" alt="40 commands">
  </p>
</div>

KernLens adds **40 commands** to GDB for reading a running Linux kernel.
Each one reads real memory through a single reader, decodes it with
arithmetic you can check by hand, and prints the answer with the entry it
came from -- so a wrong result looks wrong instead of looking plausible.

`core/` and `output/` are pure Python and run without GDB at all; only
the `gdb/` package needs a debuggee.

## What it looks like

A 2 MiB mapping, walked level by level. The walk stops where the hardware
does:

```text
VA: 0xffff8cb880400000
Paging: 4-level  root=0x6ad2000
pgd      : idx=0x119 entry=0x6ad28c8 value=0x4a01067 -> 0x4a01000
pud      : idx=0xe2 entry=0x4a01710 value=0x4a02067 -> 0x4a02000
pmd      : idx=0x2 entry=0x4a02010 value=0x80000000004000e3 (huge leaf)
Leaf: 2 MiB huge pa=0x400000 offset=0x0
Flags: P RW A D PAT PS NX
```

Each row shows the index, the *address of the entry*, the raw value, and
where the next level is. The `PS` bit at `pmd` is why there is no `pte`
row. Compare with the same address forced to 5-level paging:

```text
pgd      : idx=0x1ff entry=0x6ad2ff8 value=0x3015067 -> 0x3015000
p4d      : idx=0x119 entry=0x30158c8 value=0x0
Note: p4d entry is not present
```

The SLUB allocator, where `Size` and `Obj Size` differ when a cache rounds
up for alignment or adds metadata -- the gap an amplification attack cares
about:

```text
Name                         # Objects  Size  Obj Size  order
ext4_groupinfo_4k            22         184   184       0
AF_VSOCK                     25         1280  1232      3
MPTCPv6                      15         2112  2064      3
```

And the freelist encoding, which is the part a use-after-free tracer has
to get right. The stored word is not a pointer:

```text
cpu 0 first object : 0xffff911c466b5000
  slot address   : 0xffff911c466b5200   (object + offset 512)
  stored word    : 0xfa9c7eb28ed8d5fb
  decoded next   : 0xffff911c466b5800
  the arithmetic : 0xffff911c466b5800 ^ 0x53184e8d4227204 ^ swab(0xffff911c466b5200) = 0xfa9c7eb28ed8d5fb
  check          : 0xfa9c7eb28ed8d5fb
```

## Quickstart

```console
git clone https://github.com/BinRacer/KernLens
echo "source $(pwd)/KernLens/gdbinit.py" >> ~/.gdbinit
```

```gdb
(gdb) file vmlinux
(gdb) target remote :1234
(gdb) kl-base            # recover the KASLR slide and apply it
(gdb) kl-help            # every command, grouped by category
```

`kl-base` first, always: on a KASLR kernel every symbol in the vmlinux is
at its link-time address, and nothing resolved before the slide is
applied. Loading `gdbinit.py` never installs a breakpoint and is safe
before `file vmlinux`.

Running from a checkout needs no install -- `gdbinit.py` puts its own
`src/` on `sys.path`. Contributor setup is in
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## The 40 commands

Grouped exactly as `kl-help` groups them. The `kl-` form is what you
type at the prompt; the canonical `kernlens-` form is what scripts and
the generated tutorial use. Both always work.

### kernel metadata (8)

| Command | Alias | What it prints |
| --- | --- | --- |
| `kernlens-kchecksec` | `kl-kchecksec` | Hardening audit |
| `kernlens-kcmdline` | `kl-kcmdline` | Boot command line |
| `kernlens-kconfig` | `kl-kconfig` | Kernel configuration |
| `kernlens-kdmesg` | `kl-kdmesg` | Kernel log |
| `kernlens-klookup` | `kl-klookup` | Symbol search |
| `kernlens-kmod` | `kl-kmod` | Loaded modules |
| `kernlens-ksyscalls` | `kl-ksyscalls` | Syscall table |
| `kernlens-kversion` | `kl-kversion` | Kernel version |

### addresses & page tables (9)

| Command | Alias | What it prints |
| --- | --- | --- |
| `kernlens-addr` | `kl-addr` | Address analysis |
| `kernlens-p2v` | `kl-p2v` | Physical to virtual |
| `kernlens-page` | `kl-page` | Page for an address |
| `kernlens-pageinfo` | `kl-pageinfo` | Describe a struct page |
| `kernlens-pagewalk` | `kl-pagewalk` | Pagewalk (pwndbg format) |
| `kernlens-pt` | `kl-pt` | Page-table indices |
| `kernlens-pte` | `kl-pte` | Decode a page-table entry |
| `kernlens-v2p` | `kl-v2p` | Virtual to physical |
| `kernlens-walk` | `kl-walk` | Walk the page tables |

### memory & symbols (11)

| Command | Alias | What it prints |
| --- | --- | --- |
| `kernlens-bt` | `kl-bt` | Backtrace |
| `kernlens-buddy` | `kl-buddy` | Locate an address in the buddy allocator |
| `kernlens-buddydump` | `kl-buddydump` | Buddy free-list dump |
| `kernlens-chain` | `kl-chain` | Compact call chain |
| `kernlens-kbpf` | `kl-kbpf` | BPF programs and maps |
| `kernlens-kdmabuf` | `kl-kdmabuf` | dma-buf objects |
| `kernlens-kvar` | `kl-kvar` | Read a kernel variable |
| `kernlens-read` | `kl-read` | Dump memory |
| `kernlens-read-field` | `kl-read-field` | Read a struct field |
| `kernlens-slab` | `kl-slab` | SLUB cache inspection |
| `kernlens-sym` | `kl-sym` | Address to symbol |

### kernel base & KASLR (4)

| Command | Alias | What it prints |
| --- | --- | --- |
| `kernlens-base` | `kl-base` | Active base and slide |
| `kernlens-kaslr` | `kl-kaslr` | Slide from a runtime address |
| `kernlens-kaslr-offset` | `kl-kaslr-offset` | Set the slide directly |
| `kernlens-kbase` | `kl-kbase` | Find the kernel base |

### CPU topology (3)

| Command | Alias | What it prints |
| --- | --- | --- |
| `kernlens-cpu` | `kl-cpu` | CPU topology |
| `kernlens-msr` | `kl-msr` | Model-specific registers |
| `kernlens-percpu` | `kl-percpu` | Per-CPU symbol address |

### bit & integer primitives (2)

| Command | Alias | What it prints |
| --- | --- | --- |
| `kernlens-bits` | `kl-bits` | Bit-level view |
| `kernlens-int` | `kl-int` | Integer view |

### overview (1)

| Command | Alias | What it prints |
| --- | --- | --- |
| `kernlens-status` | `kl-status` | Session status |

### output (1)

| Command | Alias | What it prints |
| --- | --- | --- |
| `kernlens-color` | `kl-color` | Colour control |

### help (1)

| Command | Alias | What it prints |
| --- | --- | --- |
| `kernlens-help` | `kl-help` | Command reference |

Every command has a page in [`docs/tutorial/`](docs/tutorial/) with real
captured output, its options, and a note on how to read the result.

Two things the command list does not show. `kl-help <command>` gives usage
and worked examples, and `--help` works on every command with a guided
error message rather than a bare usage line. And the commands never
`stop()` the debuggee: they read memory and return, so they compose inside
a breakpoint handler.

## Use it as a library

The commands are a thin layer over a Python API. From a sourced script:

```python
# any file you source after gdbinit.py -- the names are already installed
print(split_4(0xffff888000001234))       # KPageTable, no memory read
print(read_kvar("jiffies"))              # live read through the facade
print(LE.unpack_u32(b"\x34\x12\x00\x00"))  # LE is a ByteOrderCodec
```

Or import it normally:

```python
from kernlens import KAddr, KPageTable

# (0x111, 0x0, 0x0, 0x1, 0x234) -- one index per level, outermost first
KPageTable.split_4(0xffff888000001234)
KAddr.is_direct_map(0xffff888000001234)  # True
```

The arithmetic half needs no debugger, which is what makes it testable on
the host. The full reference is [`docs/api.md`](docs/api.md).

## How it stays true

Every claim this repository makes about itself is checked by a machine,
because the alternative is prose that is correct on the day it is written:

- `docs/tutorial/` is **generated** from a capture taken on a running
  kernel; `gen_tutorial.py --check` fails when a page and the capture
  disagree.
- Example coverage is declared in `tools/example_manifest.py` and enforced
  by `tools/check_examples.py --check`: a claim without the code fails,
  and so does a command named in prose but never executed.
- The examples that can run without a debugger are executed in CI; the
  rest are replayed under GDB and recorded, and the record is compared
  against the source on every push.
- The repository tree in `docs/architecture.md` and the numbers in
  `examples/README.md` are checked against the real tree and the real
  measurement, not typed by hand.

The `kl-*` command count on this page is checked against the command
registry by the test suite, so it cannot quietly become false.

## Documentation

| Document | What is in it |
| --- | --- |
| [`docs/tutorial/`](docs/tutorial/) | one page per command, real output |
| [`docs/api.md`](docs/api.md) | the Python API reference |
| [`docs/architecture.md`](docs/architecture.md) | package layout, API map, design notes |
| [`examples/`](examples/README.md) | runnable scripts, grouped by intent |
| [`docs/naming.md`](docs/naming.md) | command and filename conventions |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | setup, tests, the layout generator |
| [`SECURITY.md`](SECURITY.md) | what counts as a vulnerability, and how to report one privately |
| [`CHANGELOG.md`](CHANGELOG.md) | every change, newest first |

## Requirements and license

Python 3.10+ and a GDB built with Python 3.10+. x86_64 kernels only --
the page-table and `struct page` decoding are written against that
architecture. On Python below 3.12 the only runtime dependency is
`typing-extensions`.

GPL-3.0-or-later. See [`LICENSE`](LICENSE); third-party attribution is in
[`CREDITS.md`](CREDITS.md).