# `kernlens-chain`

Compact call chain

**Alias:** `kl-chain`  
**Category:** memory & symbols  
**Synopsis:** `kernlens-chain [-h] [depth]`

The same stack as `kl-bt` collapsed to one line of `caller <- callee`, for pasting into a report.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | (optional) | maximum frames, 1-128 (default 8) |

## The chain

### Invocation

```gdb
kernlens-chain
```

### Output

```text
native_safe_halt <- default_idle <- default_idle <- arch_cpu_idle <- default_idle_call <- do_idle <- do_idle <- cpu_startup_entry
```

### Reading it

Innermost first, joined by `<-`.  Only symbol names appear -- no addresses, no source lines -- which is what makes it fit on one line.  Repeated inlined symbols are kept rather than deduplicated, because collapsing them would misrepresent the depth.

## A longer chain

### Invocation

```gdb
kernlens-chain 12
```

### Output

```text
native_safe_halt <- default_idle <- default_idle <- arch_cpu_idle <- default_idle_call <- do_idle <- do_idle <- cpu_startup_entry <- rest_init <- start_kernel <- x86_64_start_reservations
```

### Reading it

The optional argument is a depth.  `init_thread_union` appearing between frames is a known artefact of the kernel's stack layout, not a bad unwind.

## Notes

For anything where the addresses matter, use `kl-bt`: this form deliberately drops them.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
