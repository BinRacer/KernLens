# 命令参考

全部命令，顺序与 `kl-help` 打印的一致。`kl-` 形式是你在提示符下敲的，也是本表和教程展示的形式；规范的 `kernlens-` 形式是注册名，脚本可以用它，第二列也列出它，以防将来别名被改名。两者始终都能用。

本页由 `tools/gen_commands.py` 从 `tools/tutorial_meta.json` 生成；要改就改命令的 parser 描述，不要改这张表。每个命令在 [`tutorial/`](tutorial/README.md) 里有一页，附捕获的输出与阅读方法（页面本身保留英文）。

**分类名、命令名与一句话描述保留英文。** 它们就是 `kl-help` 打印的那些字符串，命令只认这一套拼写；把它们翻译一份，只会得到一套没有任何命令响应的名字。

## overview (1)

| 命令 | 规范名 | 作用 |
| --- | --- | --- |
| `kl-status` | `kernlens-status` | Shows the KernLens version, color mode, KASLR slide, and layout. |

## kernel base & KASLR (1)

| 命令 | 规范名 | 作用 |
| --- | --- | --- |
| `kl-base` | `kernlens-base` | Reports the runtime kernel text base and KASLR slide. |

## kernel metadata (6)

| 命令 | 规范名 | 作用 |
| --- | --- | --- |
| `kl-kcmdline` | `kernlens-kcmdline` | Return the kernel command line (/proc/cmdline). |
| `kl-kversion` | `kernlens-kversion` | Outputs the kernel version (/proc/version). |
| `kl-kconfig` | `kernlens-kconfig` | Outputs the kernel config (/proc/config.gz). |
| `kl-kmod` | `kernlens-kmod` | Displays the loaded Linux kernel modules. |
| `kl-ksyscalls` | `kernlens-ksyscalls` | Displays the Linux syscall table, including names and addresses of syscalls. |
| `kl-kdmesg` | `kernlens-kdmesg` | Displays the kernel ring buffer (dmesg) contents. |

## addresses & page tables (6)

| 命令 | 规范名 | 作用 |
| --- | --- | --- |
| `kl-addr` | `kernlens-addr` | Classifies an address and reports where it maps. |
| `kl-pt` | `kernlens-pt` | Splits a virtual address into page-table indices, or decodes a page-table entry. |
| `kl-walk` | `kernlens-walk` | Walks the live page tables and decodes every level. |
| `kl-p2v` | `kernlens-p2v` | Translates a physical address to virtual + struct page. |
| `kl-v2p` | `kernlens-v2p` | Translates a virtual address (live page tables) to physical. |
| `kl-pageinfo` | `kernlens-pageinfo` | Translates a struct page to virtual and physical addresses. |

## memory & symbols (9)

| 命令 | 规范名 | 作用 |
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

| 命令 | 规范名 | 作用 |
| --- | --- | --- |
| `kl-cpu` | `kernlens-cpu` | Displays CPU topology, the online mask, and per-CPU offsets. |
| `kl-percpu` | `kernlens-percpu` | Resolves a per-CPU symbol to its runtime address for a CPU. |
| `kl-msr` | `kernlens-msr` | Reads or writes x86_64 model-specific registers (via GDB). |

## bit & integer primitives (2)

| 命令 | 规范名 | 作用 |
| --- | --- | --- |
| `kl-bits` | `kernlens-bits` | Inspects a 64-bit value; optionally test/set/clear a bit. |
| `kl-int` | `kernlens-int` | Shows signed/unsigned and LE/BE integer views. |

## output (1)

| 命令 | 规范名 | 作用 |
| --- | --- | --- |
| `kl-color` | `kernlens-color` | Enable, disable, or toggle ANSI color output. |

## help (1)

| 命令 | 规范名 | 作用 |
| --- | --- | --- |
| `kl-help` | `kernlens-help` | Lists every KernLens command, or explains one in detail. |
