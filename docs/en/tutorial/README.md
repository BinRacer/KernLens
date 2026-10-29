# KernLens tutorial

A command-by-command walkthrough of KernLens, with output taken from a real kernel rather than invented examples.

Every page follows the same shape: what the command answers, the exact invocation, the output it produced on the capture kernel, how to read that output, and what makes it refuse.  Pages are grouped by the categories `kl-help` prints.

## The capture kernel

All output in this tutorial was captured from one boot of the project's test VM:

| Fact | Value |
| --- | --- |
| Kernel | `6.1.134` (x86_64, DWARF debug info) |
| CPUs | 4 |
| SLUB caches | 170 |
| KASLR slide | `0x19200000` |
| `_text` (link) | `0xffffffff81000000` |
| `_text` (runtime) | `0xffffffff9a200000` |
| `page_offset_base` | `0xffff9762c0000000` |
| `vmemmap_base` | `0xffffd4fe00000000` |
| A free page (phys) | `0x400000` |
| Its direct-map alias | `0xffff9762c0400000` |
| Its `struct page` | `0xffffd4fe00010000` |

`page_offset_base` and `vmemmap_base` are kernel **variables** the boot code fills in, so they change on every boot, and the slide changes with them.  Everything else here (struct offsets, the zone list, cache names, symbol names) is stable for this build.  Anything boot-specific is re-derived by KernLens at run time rather than assumed, which is why the commands show these numbers instead of a constant.

### Reproducing the capture

```gdb
(gdb) source /path/to/KernLens/gdbinit.py
(gdb) file /path/to/vmlinux
(gdb) target remote :1234
(gdb) kl-color off
(gdb) python exec(open("tools/tutorial_capture.py").read())
```

`kl-color off` is not cosmetic: it keeps ANSI escapes out of the captured text, which is what lets these pages diff cleanly.  The capture script writes `tools/tutorial_capture.json`; `tools/gen_tutorial.py` then renders the pages from it, and `--check` fails when a page and the capture disagree.

## Reading the pages

- **Invocation** -- the exact command line.  The `kl-` alias is used; every one expands to the `kernlens-` name.
- **Output** -- verbatim, including alignment.  Two spaces of indent under a header line is KernLens' convention for a row of one record.
- **Reading it** -- what each row means and what to conclude from the values shown.
- **Notes** -- where the values come from (DWARF, BTF, a registry fallback, or raw memory), and what makes the command refuse.

## Pages

### Help

Finding your way around the command set.

| Command | What it answers |
| --- | --- |
| [`kl-help`](kl-help.md) | Lists every KernLens command, or explains one in detail. |

### Overview

The one command to run first on an unfamiliar session.

| Command | What it answers |
| --- | --- |
| [`kl-status`](kl-status.md) | Shows the KernLens version, color mode, KASLR slide, and layout. |

### Kernel base & kaslr

Where the kernel is loaded, and how KernLens copes with a randomised base.

| Command | What it answers |
| --- | --- |
| [`kl-base`](kl-base.md) | Reports the runtime kernel text base and KASLR slide. |

### Kernel metadata

Configuration and build facts: the command line, the version, the options, the modules, the syscall table, and the log.

| Command | What it answers |
| --- | --- |
| [`kl-kcmdline`](kl-kcmdline.md) | Return the kernel command line (/proc/cmdline). |
| [`kl-kconfig`](kl-kconfig.md) | Outputs the kernel config (/proc/config.gz). |
| [`kl-kdmesg`](kl-kdmesg.md) | Displays the kernel ring buffer (dmesg) contents. |
| [`kl-kmod`](kl-kmod.md) | Displays the loaded Linux kernel modules. |
| [`kl-ksyscalls`](kl-ksyscalls.md) | Displays the Linux syscall table, including names and addresses of syscalls. |
| [`kl-kversion`](kl-kversion.md) | Outputs the kernel version (/proc/version). |

### Cpu topology

How many CPUs, and where their per-CPU data lives.

| Command | What it answers |
| --- | --- |
| [`kl-cpu`](kl-cpu.md) | Displays CPU topology, the online mask, and per-CPU offsets. |
| [`kl-msr`](kl-msr.md) | Reads or writes x86_64 model-specific registers (via GDB). |
| [`kl-percpu`](kl-percpu.md) | Resolves a per-CPU symbol to its runtime address for a CPU. |

### Addresses & page tables

From a raw 64-bit value to the physical page it refers to, in either direction.

| Command | What it answers |
| --- | --- |
| [`kl-addr`](kl-addr.md) | Classifies an address and reports where it maps. |
| [`kl-p2v`](kl-p2v.md) | Translates a physical address to virtual + struct page. |
| [`kl-pageinfo`](kl-pageinfo.md) | Translates a struct page to virtual and physical addresses. |
| [`kl-pt`](kl-pt.md) | Splits a virtual address into page-table indices, or decodes a page-table entry. |
| [`kl-v2p`](kl-v2p.md) | Translates a virtual address (live page tables) to physical. |
| [`kl-walk`](kl-walk.md) | Walks the live page tables and decodes every level. |

### Memory & symbols

Reading the kernel's own memory: symbols, the stack, SLUB, the buddy allocator, BPF and dma-buf.

| Command | What it answers |
| --- | --- |
| [`kl-bt`](kl-bt.md) | Prints a formatted kernel backtrace. |
| [`kl-buddy`](kl-buddy.md) | Locates an address in the buddy allocator: its zone, its free block, and where it sits inside that block. |
| [`kl-kbpf`](kl-kbpf.md) | Prints information about the linux kernel bpf progs and maps. |
| [`kl-kdmabuf`](kl-kdmabuf.md) | Prints DMA buf info. |
| [`kl-kvar`](kl-kvar.md) | Reads a KASLR-aware kernel global variable. |
| [`kl-read`](kl-read.md) | Dumps kernel memory as 64-bit words with symbol annotations. |
| [`kl-read-field`](kl-read-field.md) | Reads a struct field (including nested paths), whatever its type. |
| [`kl-slab`](kl-slab.md) | Prints information about the linux kernel's slab allocator SLUB. |
| [`kl-sym`](kl-sym.md) | Resolves an address to a symbol, or finds symbols by name. |

### Bit & integer primitives

Pure arithmetic on a value you already have.  These are the only commands that touch no kernel state.

| Command | What it answers |
| --- | --- |
| [`kl-bits`](kl-bits.md) | Inspects a 64-bit value; optionally test/set/clear a bit. |
| [`kl-int`](kl-int.md) | Shows signed/unsigned and LE/BE integer views. |

### Output

Presentation controls.

| Command | What it answers |
| --- | --- |
| [`kl-color`](kl-color.md) | Enable, disable, or toggle ANSI color output. |

## Conventions used in every page

KernLens distinguishes three states in its output, and the distinction matters when reading these pages:

- a **value** (`Size: 0xc0`) -- read from the live kernel;
- `?` -- the datum is not available in this build or this state, and the command says so rather than printing a plausible zero;
- `<unreadable>` -- the memory could not be read at all (bad address, unloaded page).

Rows are aligned with two leading spaces per nesting level, and a label is followed by `: ` (one space) so the values line up in a column.

---

Generated by `tools/gen_tutorial_index.py` from the same capture as the pages.  Do not edit by hand: re-run the generator.
