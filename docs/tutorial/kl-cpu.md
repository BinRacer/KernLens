# `kernlens-cpu`

CPU topology

**Alias:** `kl-cpu`  
**Category:** CPU topology  
**Synopsis:** `kernlens-cpu [-h] [cpu]`

Reports how many CPUs the kernel has, which are online, and the per-CPU offset each one's data is based at.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | (optional) | CPU id to describe (default: current CPU) |

## The topology summary

### Invocation

```gdb
kernlens-cpu
```

### Output

```text
Topology: nr_cpus=4 nr_nodes=1 current=0
Online: 0-3 (4/4)
    cpu 0
    online: True
    percpu_off: 0xffff8cb887a00000
```

### Reading it

`nr_cpus` is the configured count and `nr_nodes` the NUMA node count.  `Online` is compacted into ranges (`0-3`) rather than four separate numbers, which keeps a 128-CPU machine readable.  `current` is the CPU GDB is stopped on.

## One CPU in detail

### Invocation

```gdb
kernlens-cpu 0
```

### Output

```text
Topology: nr_cpus=4 nr_nodes=1 current=0
Online: 0-3 (4/4)
    cpu 0
    online: True
    percpu_off: 0xffff8cb887a00000
```

### Reading it

The per-CPU offset is the base that a per-CPU symbol's section offset is added to.  It differs between CPUs, which is why a per-CPU symbol cannot be read with a bare `&symbol`.

## Notes

`cur_cpu()` masks GDB's `$gs_base` to 64 bits: the remote target reports it as a negative value, and the unmasked value silently fails the per-CPU range check.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
