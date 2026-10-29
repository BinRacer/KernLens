# `kernlens-kbpf`

BPF programs and maps

**Alias:** `kl-kbpf`  
**Category:** memory & symbols  
**Synopsis:** `kernlens-kbpf [-h] [-v] [-b NTH] [-p] [-m] [--values]`

Walks the BPF object lists and prints each program and map.  Root-only in a normal kernel, but readable through a debugger regardless of credentials.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
| `-v`, `--verbose` | — | Increase the verbosity. |
| `-b`, `--break` | — | Break at the start of the nth JIT compiled ebpf prog. |
| `-p`, `--progs` | — | Print progs |
| `-m`, `--maps` | — | Print maps |
| `--values` | — | dump array-map element values |

## The default view

### Invocation

```gdb
kernlens-kbpf
```

### Output

```text
bpf progs: 0
bpf maps: 0
```

### Reading it

Two summary lines when nothing is loaded.  The counts come from the `prog_idr`/`map_idr` IDR structures, so they are the kernel's own totals.

## Programs only

### Invocation

```gdb
kernlens-kbpf -p
```

### Output

```text
bpf progs: 0
```

### Reading it

`-p` restricts the output to programs, which is what you want when looking for a hook: each row carries the program type, its `bpf_func` entry point, and the map it uses.

## Maps only

### Invocation

```gdb
kernlens-kbpf -m
```

### Output

```text
bpf maps: 0
```

### Reading it

`-m` restricts to maps.  `--values` additionally dumps each map's contents, which is how a BPF-based keylogger or rootkit is spotted.

## Notes

An empty list is a normal state for a minimal kernel, not a failure.  `-b N` prints the Nth program and sets a breakpoint at its `bpf_func`, which is the practical way to catch a program running.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
