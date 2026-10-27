# `kernlens-bt`

Backtrace

**Alias:** `kl-bt`  
**Category:** memory & symbols  
**Synopsis:** `kernlens-bt [-h] [--chain] [depth]`

A kernel-aware backtrace: each frame's return address resolved to a symbol and source line, with the noise of the interrupted context handled.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | (optional) | maximum frames, 1-128 (default 8) |
| `--chain` | — | print the compact caller <- callee chain instead of the frames |

## The whole stack

### Invocation

```gdb
kernlens-bt
```

### Output

```text
bt:
                   #0  0xffffffffaee1263b  native_safe_halt  at ./arch/x86/include/asm/irqflags.h:52
                   #1  0xffffffffaee1248e  default_idle  at ./arch/x86/include/asm/paravirt.h:173
                   #2  0xffffffffaee1248e  default_idle  at ./arch/x86/include/asm/paravirt.h:173
                   #3  0xffffffffadc5a245  arch_cpu_idle  at arch/x86/kernel/process.c:728
                   #4  0xffffffffaee127aa  default_idle_call  at ./arch/x86/include/asm/paravirt.h:699
                   #5  0xffffffffade119bf  do_idle  at kernel/sched/idle.c:192
                   #6  0xffffffffade119bf  do_idle  at kernel/sched/idle.c:192
                   #7  0xffffffffade11c1a  cpu_startup_entry  at kernel/sched/idle.c:400
```

### Reading it

Frames are printed `#N address symbol at file:line`.  Frames 1 and 2 being the same symbol (`default_idle`) is normal in an idle stack: the compiler emitted inlined copies, and both map back to the same out-of-line body.  The stack ends in the idle loop, which tells you the CPU is not running anything interesting.

## Limiting the depth

### Invocation

```gdb
kernlens-bt 4
```

### Output

```text
bt:
                   #0  0xffffffffaee1263b  native_safe_halt  at ./arch/x86/include/asm/irqflags.h:52
                   #1  0xffffffffaee1248e  default_idle  at ./arch/x86/include/asm/paravirt.h:173
                   #2  0xffffffffaee1248e  default_idle  at ./arch/x86/include/asm/paravirt.h:173
                   #3  0xffffffffadc5a245  arch_cpu_idle  at arch/x86/kernel/process.c:728
```

### Reading it

A depth limit keeps the output readable on a deep stack.  The inner frames are the same, so the limit is applied from the innermost frame outward, not by truncating the printed text.

## Notes

`--chain` switches to the one-line form, which is what `kl-chain` prints.  A frame showing `??` is one where the return address did not resolve -- often a stack-corruption artefact, and worth noting rather than hiding.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
