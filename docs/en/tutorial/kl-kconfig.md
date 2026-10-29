# `kernlens-kconfig`

Kernel configuration

**Alias:** `kl-kconfig`  
**Category:** kernel metadata  
**Synopsis:** `kernlens-kconfig [-h] [-l FILE_PATH] [-c] [config_name]`

Reads the `CONFIG_*` options out of the kernel image itself -- no `/boot/config-$(uname -r)` needed, so this works on a target whose headers you do not have.  `--check` narrows the same lookup to the hardening options; that audit was `kl-kchecksec`.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | (optional) | a config name to search for (e.g. RANDOMIZE_BASE) |
| `-l`, `--load` | — | merge CONFIG_* lines from a kernel config file |
| `-c`, `--check` | — | audit the hardening options instead of printing the config |

## One option

### Invocation

```gdb
kernlens-kconfig RANDOMIZE_BASE
```

### Output

```text
CONFIG_RANDOMIZE_BASE = y
```

### Reading it

The image stores a compressed `IKCFG` blob; KernLens inflates it and answers from that.  `= y` is built in, `= m` is a module allowed to be built in, and `not set` means compiled out -- which is not the same as `n`, because unimplemented symbols leave no line at all.

## The hardening audit

### Invocation

```gdb
kernlens-kconfig --check
```

### Output

```text
CONFIG_STACKPROTECTOR = y
CONFIG_STACKPROTECTOR_STRONG = y
CONFIG_SHADOW_CALL_STACK not set
CONFIG_STRICT_KERNEL_RWX = y
CONFIG_STRICT_MODULE_RWX = y
CONFIG_DEBUG_WX = y
CONFIG_RANDOMIZE_BASE = y
CONFIG_RANDOMIZE_KSTACK_OFFSET_DEFAULT = y
CONFIG_RANDOMIZE_MODULE_REGION_FULL not set
CONFIG_KALLSYMS = y
CONFIG_SLAB_FREELIST_HARDENED = y
CONFIG_SLAB_FREELIST_RANDOM = y
CONFIG_KFENCE = y
CONFIG_INIT_ON_ALLOC_DEFAULT_ON = y
CONFIG_INIT_STACK_ALL_ZERO = y
CONFIG_INIT_ON_FREE_DEFAULT_ON not set
CONFIG_CFI_CLANG not set
CONFIG_CFI_PERMISSIVE not set
CONFIG_SECURITY = y
CONFIG_SECURITY_YAMA = y
... (32 more line(s), 52 total)
```

*The capture has 52 lines; the first 20 are shown.  Run the command to see the rest.*

### Reading it

Three states appear: `= y` (enabled), `= m` (module), and `not set` (compiled out).  The list is ordered from the stack to the allocator, so a quick scan tells you whether the machine is a realistic target or a debugging build.  Note that `SLAB_FREELIST_RANDOM` and `SLAB_FREELIST_HARDENED` are separate: the first shuffles object order, the second encodes the free pointer.

## Notes

The audit's option list is fixed in the command, not configurable: they are the ones that change what an exploit has to do, and a user-supplied list would make two reports incomparable.  It reads the same `CONFIG_*` image this command prints, so the two cannot disagree.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
