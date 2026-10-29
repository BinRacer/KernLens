# `kernlens-kchecksec`

Hardening audit

**Alias:** `kl-kchecksec`  
**Category:** kernel metadata  
**Synopsis:** `kernlens-kchecksec [-h]`

Audits the `CONFIG_*` options that decide how hard the kernel is to exploit.  This is the kernel-space counterpart of pwndbg's `checksec`.

## The audit

### Invocation

```gdb
kernlens-kchecksec
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

The options audited are fixed in the command, not configurable: they are the ones that change what an exploit has to do, and a user-supplied list would make two reports incomparable.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
