# `kl-percpu`

Per-CPU symbol address

**Canonical:** `kernlens-percpu`  
**Category:** CPU topology  
**Synopsis:** `kl-percpu [-h] symbol [cpu]`

Resolves a per-CPU symbol to the address the given CPU actually uses.  This is the fix for the classic mistake of taking `&current_task` and getting a section offset that is not any CPU's copy.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | a per-CPU symbol (e.g. current_task) |
|  | (optional) | CPU id (default: current CPU) |

## The current CPU

### Invocation

```gdb
kl-percpu current_task
```

### Output

```text
Symbol: current_task (cpu 0)
Address: 0xffff9762c7a1fb80
percpu_off: 0xffff9762c7a00000
```

### Reading it

The bare value of a per-CPU symbol *is* its offset within the per-CPU section, zero-based, so the runtime address is `__per_cpu_offset[cpu] + offset`.  Both parts are printed, which is what makes a mismatch obvious.

## Another CPU

### Invocation

```gdb
kl-percpu current_task 1
```

### Output

```text
Symbol: current_task (cpu 1)
Address: 0xffff9762c7a9fb80
percpu_off: 0xffff9762c7a80000
```

### Reading it

Different CPU, different base, same offset.  Comparing two CPUs' output is the quickest way to confirm the offsets are being applied rather than ignored.

## Notes

The per-CPU base is read from `__per_cpu_offset[]` rather than derived, because the linker only guarantees the section is zero-based; where it lands at run time is the kernel's choice.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
