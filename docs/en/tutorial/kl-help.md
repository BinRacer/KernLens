# `kl-help`

Command reference

**Canonical:** `kernlens-help`  
**Category:** help  
**Synopsis:** `kl-help [-h] [COMMAND]`

`kl-help` is the only command that needs no debuggee: it reads the command registry that `@Command` decorated functions populate.  A bare invocation lists every command grouped by category; giving a name prints that command's full help.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | COMMAND | kernlens-* name or kl-* alias to describe (default: list all) |

## Listing every command

### Invocation

```gdb
kl-help
```

### Output

```text
KernLens 0.3.0 — command reference
  type kl-help kl-<command> for usage, options, and examples

overview
  kl-status [-h] [--doctor]           Shows the KernLens version, color mode, KASLR slide, and layout.

kernel base & KASLR
  kl-base [-h] [-v] [-r] [command ...]  Reports the runtime kernel text base and KASLR slide.

kernel metadata
  kl-kcmdline [-h]                    Return the kernel command line (/proc/cmdline).
  kl-kversion [-h]                    Outputs the kernel version (/proc/version).
  kl-kconfig [-h] [-l FILE_PATH] [-c] [config_name]  Outputs the kernel config (/proc/config.gz).
  kl-kmod [-h] [-l PATH] [module_name]  Displays the loaded Linux kernel modules.
  kl-ksyscalls [-h] [syscall_name]    Displays the Linux syscall table, including names and addresses of syscalls.
  kl-kdmesg [-h] [-T]                 Displays the kernel ring buffer (dmesg) contents.

addresses & page tables
  kl-addr [-h] [-b] address [tag_mask]  Classifies an address and reports where it maps.
  kl-pt [-h] [-e] [--paging {4,5}] [VALUE ...]  Splits a virtual address into page-table indices, or decodes a page-table entry.
  kl-walk [-h] [-p ROOT] [-s {levels,pwndbg}] va [{4,5}]  Walks the live page tables and decodes every level.
  kl-p2v [-h] paddr                   Translates a physical address to virtual + struct page.
  kl-v2p [-h] vaddr                   Translates a virtual address (live page tables) to physical.
  kl-pageinfo [-h] page               Translates a struct page to virtual and physical addresses.

memory & symbols
  kl-buddy [-h] [-z ZONE] [-o ORDER] [-m MTYPE] [-n NODE] [-v]
                [--limit LIMIT] [-p] [-c CPU] [-f FIND]
                [--MIGRATE_TYPES COUNT]
                [command ...]  Locates an address in the buddy allocator: its zone, its free block, and where it sits inside that block.
  kl-slab [-h] [-v] [-c CPU] [-n NODE] [-p] [-a] [-i] [-r] [--reclaim]
               [--ctor]
               [command ...]  Prints information about the linux kernel's slab allocator SLUB.
  kl-sym [-h] [-f] [-a] [query]       Resolves an address to a symbol, or finds symbols by name.
  kl-bt [-h] [--chain] [depth]        Prints a formatted kernel backtrace.
  kl-read [-h] [-m {ascii}] address [count]  Dumps kernel memory as 64-bit words with symbol annotations.
  kl-kvar [-h] symbol                 Reads a KASLR-aware kernel global variable.
  kl-read-field [-h] address type path  Reads a struct field (including nested paths) as an integer.
  kl-kbpf [-h] [-v] [-b NTH] [-p] [-m] [--values]  Prints information about the linux kernel bpf progs and maps.
  kl-kdmabuf [-h]                     Prints DMA buf info.

CPU topology
  kl-cpu [-h] [cpu]                   Displays CPU topology, the online mask, and per-CPU offsets.
  kl-percpu [-h] symbol [cpu]         Resolves a per-CPU symbol to its runtime address for a CPU.
  kl-msr [-h] [-w [write_value]] [-l] [-r [MSR_RANGE]] [msr]  Reads or writes x86_64 model-specific registers (via GDB).

bit & integer primitives
  kl-bits [-h] value [bit]            Inspects a 64-bit value; optionally test/set/clear a bit.
  kl-int [-h] value [width]           Shows signed/unsigned and LE/BE integer views.

output
  kl-color [-h] [{on,off,toggle}]     Enable, disable, or toggle ANSI color output.

help
  kl-help [-h] [COMMAND]              Lists every KernLens command, or explains one in detail.
```

### Reading it

Commands are grouped by the category the decorator declared.  The usage column is the command's own `argparse` usage string, so it always matches what the parser accepts.  Each row shows the `kl-` name, which is the one you type; the `kernlens-` spelling still works and is what a script should call, because it is the registered name and an alias could be renamed.

## Explaining one command

### Invocation

```gdb
kl-help kl-walk
```

### Output

```text
usage: kl-walk [-h] [-p ROOT] [-s {levels,pwndbg}] va [{4,5}]

Walks the live page tables and decodes every level.

positional arguments:
  va                    virtual address to translate
  {4,5}                 force 4-level or 5-level paging (default: auto)

options:
  -h, --help            show this help message and exit
  -p ROOT, --pgd ROOT   top-level table to start from (default: the live CR3)
  -s {levels,pwndbg}, --style {levels,pwndbg}
                        presentation: one row per level, or pwndbg's pagewalk
                        order (default: levels)

Examples:
kl-walk 0xffff888000001234
kl-walk 0xffff800000201234 5
kl-walk 0xffff888000001234 --pgd 0x10000
kl-walk 0xffff888000001234 --style pwndbg

Notes:
``-p/--pgd`` walks a table other than the live CR3 -- a saved or
foreign root, so a page table of another task can be followed
without switching to it.

``-s/--style pwndbg`` prints the deepest level first, in
pwndbg's ``vmmap``-style layout; ``levels`` (the default) prints
one row per level from the top down.  It is one walk either way,
so it is one command.

Canonical: kernlens-walk

Alias: kl-walk
```

### Reading it

The argument must be namespaced.  `kl-help walk` is rejected with a hint to try `kl-walk`, because the bare names exist in pwndbg and GDB but never in KernLens' registry -- accepting them would make the help depend on what else happens to be loaded.

## A command with subcommands

### Invocation

```gdb
kl-help kernlens-slab
```

### Output

```text
usage: kl-slab [-h] [-v] [-c CPU] [-n NODE] [-p] [-a] [-i] [-r] [--reclaim]
               [--ctor]
               [command ...]

Prints information about the linux kernel's slab allocator SLUB.

positional arguments:
  command               list [filter] | info <name>... | contains <addr>... |
                        details <addr>... | <addr>

options:
  -h, --help            show this help message and exit
  -v, --verbose         display more detailed information (with `info`)
  -c CPU, --cpu CPU     CPU to display
  -n NODE, --node NODE
  -p, --partial         displays partial lists
  -a, --active          displays the active list
  -i, --inuse           also show the object stride including metadata (with
                        `info`)
  -r, --random          also show the freelist randomisation key (with `info`)
  --reclaim             also show whether SLAB_RECLAIM_ACCOUNT is set (with
                        `info`)
  --ctor                also show the cache's constructor symbol (with `info`)

Examples:
kl-slab list
kl-slab list kmalloc
kl-slab info kmalloc-1k -v
kl-slab contains 0xffff8880032a1c40
kl-slab details 0xffff8880032a1c40 -c 0
kl-slab 0xffff8880032a1c40            # legacy bare-address form

Canonical: kernlens-slab

Aliases: kl-slab, kl-slabs
```

### Reading it

Subcommands appear in the positional argument's help text rather than as argparse subparsers, because KernLens dispatches them itself to keep pwndbg's `slab list` / `slab info` spellings working.

## Notes

The `Examples:` and `Notes:` lines at the bottom of each page come from the decorator, not from the parser, so they can carry the longer explanation that would clutter `--help`.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
