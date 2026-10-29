# Command reference

Every command, in the order `kl-help` prints it.  The `kl-` form is
what you type at the prompt, and what this table and the tutorial
show.  The canonical `kernlens-` form is the registered name: a
script may use it, and it is listed in the second column so it stays
reachable if the aliases are ever renamed.  Both always work.

This page is generated from `tools/tutorial_meta.json` by
`tools/gen_commands.py`; edit the command's parser description, not
this table.  Each command has a page in [`tutorial/`](tutorial/README.md)
with captured output and a note on how to read it.

## overview (1)

| Command | Canonical | What it does |
| --- | --- | --- |
| `kl-status` | `kernlens-status` | Shows the KernLens version, color mode, KASLR slide, and layout. |

## kernel base & KASLR (1)

| Command | Canonical | What it does |
| --- | --- | --- |
| `kl-base` | `kernlens-base` | Reports the runtime kernel text base and KASLR slide. |

## kernel metadata (6)

| Command | Canonical | What it does |
| --- | --- | --- |
| `kl-kcmdline` | `kernlens-kcmdline` | Return the kernel command line (/proc/cmdline). |
| `kl-kversion` | `kernlens-kversion` | Outputs the kernel version (/proc/version). |
| `kl-kconfig` | `kernlens-kconfig` | Outputs the kernel config (/proc/config.gz). |
| `kl-kmod` | `kernlens-kmod` | Displays the loaded Linux kernel modules. |
| `kl-ksyscalls` | `kernlens-ksyscalls` | Displays the Linux syscall table, including names and addresses of syscalls. |
| `kl-kdmesg` | `kernlens-kdmesg` | Displays the kernel ring buffer (dmesg) contents. |

## addresses & page tables (6)

| Command | Canonical | What it does |
| --- | --- | --- |
| `kl-addr` | `kernlens-addr` | Classifies an address and reports where it maps. |
| `kl-pt` | `kernlens-pt` | Splits a virtual address into page-table indices, or decodes a page-table entry. |
| `kl-walk` | `kernlens-walk` | Walks the live page tables and decodes every level. |
| `kl-p2v` | `kernlens-p2v` | Translates a physical address to virtual + struct page. |
| `kl-v2p` | `kernlens-v2p` | Translates a virtual address (live page tables) to physical. |
| `kl-pageinfo` | `kernlens-pageinfo` | Translates a struct page to virtual and physical addresses. |

## memory & symbols (9)

| Command | Canonical | What it does |
| --- | --- | --- |
| `kl-buddy` | `kernlens-buddy` | Locates an address in the buddy allocator: its zone, its free block, and where it sits inside that block. |
| `kl-slab` | `kernlens-slab` (`kl-slabs`) | Prints information about the linux kernel's slab allocator SLUB. |
| `kl-sym` | `kernlens-sym` | Resolves an address to a symbol, or finds symbols by name. |
| `kl-bt` | `kernlens-bt` | Prints a formatted kernel backtrace. |
| `kl-read` | `kernlens-read` | Dumps kernel memory as 64-bit words with symbol annotations. |
| `kl-kvar` | `kernlens-kvar` | Reads a KASLR-aware kernel global variable. |
| `kl-read-field` | `kernlens-read-field` | Reads a struct field (including nested paths) as an integer. |
| `kl-kbpf` | `kernlens-kbpf` | Prints information about the linux kernel bpf progs and maps. |
| `kl-kdmabuf` | `kernlens-kdmabuf` | Prints DMA buf info. |

## CPU topology (3)

| Command | Canonical | What it does |
| --- | --- | --- |
| `kl-cpu` | `kernlens-cpu` | Displays CPU topology, the online mask, and per-CPU offsets. |
| `kl-percpu` | `kernlens-percpu` | Resolves a per-CPU symbol to its runtime address for a CPU. |
| `kl-msr` | `kernlens-msr` | Reads or writes x86_64 model-specific registers (via GDB). |

## bit & integer primitives (2)

| Command | Canonical | What it does |
| --- | --- | --- |
| `kl-bits` | `kernlens-bits` | Inspects a 64-bit value; optionally test/set/clear a bit. |
| `kl-int` | `kernlens-int` | Shows signed/unsigned and LE/BE integer views. |

## output (1)

| Command | Canonical | What it does |
| --- | --- | --- |
| `kl-color` | `kernlens-color` | Enable, disable, or toggle ANSI color output. |

## help (1)

| Command | Canonical | What it does |
| --- | --- | --- |
| `kl-help` | `kernlens-help` | Lists every KernLens command, or explains one in detail. |
