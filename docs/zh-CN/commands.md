# 命令参考

全部命令，顺序与 `kl-help` 打印的一致。`kl-` 形式是在提示符下敲的；规范的 `kernlens-` 形式用于脚本和生成的教程。两者始终都能用。

本页由 `tools/gen_commands.py` 从 `tools/tutorial_meta.json` 生成；要改就改命令的 parser 描述，不要改这张表。每个命令在 [`tutorial/`](tutorial/README.md) 里有一页，附捕获的输出与阅读方法（页面本身保留英文）。

**分类名、命令名与一句话描述保留英文。** 它们就是 `kl-help` 打印的那些字符串，命令只认这一套拼写；把它们翻译一份，只会得到一套没有任何命令响应的名字。

## overview (1)

| 命令 | 别名 | 作用 |
| --- | --- | --- |
| `kernlens-status` | `kl-status` | Shows the KernLens version, color mode, KASLR slide, and layout. |

## kernel base & KASLR (4)

| 命令 | 别名 | 作用 |
| --- | --- | --- |
| `kernlens-base` | `kl-base` | Selects the runtime kernel text base and KASLR slide. |
| `kernlens-kbase` | `kl-kbase` | Finds the kernel virtual base address. |
| `kernlens-kaslr` | `kl-kaslr` | Sets the KASLR slide from a runtime _text address. |
| `kernlens-kaslr-offset` | `kl-kaslr-offset` | Sets the KASLR slide directly. |

## kernel metadata (8)

| 命令 | 别名 | 作用 |
| --- | --- | --- |
| `kernlens-kcmdline` | `kl-kcmdline` | Return the kernel command line (/proc/cmdline). |
| `kernlens-kversion` | `kl-kversion` | Outputs the kernel version (/proc/version). |
| `kernlens-kconfig` | `kl-kconfig` | Outputs the kernel config (/proc/config.gz). |
| `kernlens-kchecksec` | `kl-kchecksec` | Checks for kernel hardening configuration options. |
| `kernlens-kmod` | `kl-kmod` | Displays the loaded Linux kernel modules. |
| `kernlens-ksyscalls` | `kl-ksyscalls` | Displays the Linux syscall table, including names and addresses of syscalls. |
| `kernlens-kdmesg` | `kl-kdmesg` | Displays the kernel ring buffer (dmesg) contents. |
| `kernlens-klookup` | `kl-klookup`, `kl-kallsyms`, `kl-ks` | Lookup kernel symbols |

## addresses & page tables (9)

| 命令 | 别名 | 作用 |
| --- | --- | --- |
| `kernlens-addr` | `kl-addr` | Prints a full KAddr analysis of an address. |
| `kernlens-page` | `kl-page` | Classifies an address and translates direct-map addresses. |
| `kernlens-pte` | `kl-pte` | Decodes page-table entry flags and leaf translations. |
| `kernlens-pt` | `kl-pt` | Shows 4-level/5-level page-table indices for an address. |
| `kernlens-walk` | `kl-walk` | Walks the live page tables and decodes every level. |
| `kernlens-pagewalk` | `kl-pagewalk` | Walks the page tables in pwndbg's pagewalk format. |
| `kernlens-p2v` | `kl-p2v` | Translates a physical address to virtual + struct page. |
| `kernlens-v2p` | `kl-v2p` | Translates a virtual address (live page tables) to physical. |
| `kernlens-pageinfo` | `kl-pageinfo` | Translates a struct page to virtual and physical addresses. |

## memory & symbols (11)

| 命令 | 别名 | 作用 |
| --- | --- | --- |
| `kernlens-buddy` | `kl-buddy` | Locates an address in the buddy allocator: its zone, its free block, and where it sits inside that block. |
| `kernlens-slab` | `kl-slab`, `kl-slabs` | Prints information about the linux kernel's slab allocator SLUB. |
| `kernlens-sym` | `kl-sym` | Resolves an address to a symbol and source location. |
| `kernlens-bt` | `kl-bt` | Prints a formatted kernel backtrace. |
| `kernlens-chain` | `kl-chain` | Prints a compact caller <- callee call chain. |
| `kernlens-read` | `kl-read` | Dumps kernel memory as 64-bit words with symbol annotations. |
| `kernlens-kvar` | `kl-kvar` | Reads a KASLR-aware kernel global variable. |
| `kernlens-read-field` | `kl-read-field` | Reads a struct field (including nested paths) as an integer. |
| `kernlens-kbpf` | `kl-kbpf` | Prints information about the linux kernel bpf progs and maps. |
| `kernlens-buddydump` | `kl-buddydump` | Displays metadata and freelists of the buddy allocator. |
| `kernlens-kdmabuf` | `kl-kdmabuf` | Prints DMA buf info. |

## CPU topology (3)

| 命令 | 别名 | 作用 |
| --- | --- | --- |
| `kernlens-cpu` | `kl-cpu` | Displays CPU topology, the online mask, and per-CPU offsets. |
| `kernlens-percpu` | `kl-percpu` | Resolves a per-CPU symbol to its runtime address for a CPU. |
| `kernlens-msr` | `kl-msr` | Reads or writes x86_64 model-specific registers (via GDB). |

## bit & integer primitives (2)

| 命令 | 别名 | 作用 |
| --- | --- | --- |
| `kernlens-bits` | `kl-bits` | Inspects a 64-bit value; optionally test/set/clear a bit. |
| `kernlens-int` | `kl-int` | Shows signed/unsigned and LE/BE integer views. |

## output (1)

| 命令 | 别名 | 作用 |
| --- | --- | --- |
| `kernlens-color` | `kl-color` | Enable, disable, or toggle ANSI color output. |

## help (1)

| 命令 | 别名 | 作用 |
| --- | --- | --- |
| `kernlens-help` | `kl-help` | Lists every KernLens command, or explains one in detail. |
