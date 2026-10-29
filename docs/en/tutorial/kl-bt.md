# `kernlens-bt`

Backtrace

**Alias:** `kl-bt`  
**Category:** memory & symbols  
**Synopsis:** `kernlens-bt [-h] [--chain] [depth]`

A kernel-aware backtrace: each frame's return address resolved to a symbol and source line, with the noise of the interrupted context handled.  `--chain` collapses the same stack to one line, which is the form `kl-chain` used to print.

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
                   #0  0xffffffffa881263b  native_safe_halt  at ./arch/x86/include/asm/irqflags.h:52
                   #1  0xffffffffa881248e  default_idle  at ./arch/x86/include/asm/paravirt.h:173
                   #2  0xffffffffa881248e  default_idle  at ./arch/x86/include/asm/paravirt.h:173
                   #3  0xffffffffa765a245  arch_cpu_idle  at arch/x86/kernel/process.c:728
                   #4  0xffffffffa88127aa  default_idle_call  at ./arch/x86/include/asm/paravirt.h:699
                   #5  0xffffffffa78119bf  do_idle  at kernel/sched/idle.c:192
                   #6  0xffffffffa78119bf  do_idle  at kernel/sched/idle.c:192
                   #7  0xffffffffa7811c1a  cpu_startup_entry  at kernel/sched/idle.c:400
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
                   #0  0xffffffffa881263b  native_safe_halt  at ./arch/x86/include/asm/irqflags.h:52
                   #1  0xffffffffa881248e  default_idle  at ./arch/x86/include/asm/paravirt.h:173
                   #2  0xffffffffa881248e  default_idle  at ./arch/x86/include/asm/paravirt.h:173
                   #3  0xffffffffa765a245  arch_cpu_idle  at arch/x86/kernel/process.c:728
```

### Reading it

A depth limit keeps the output readable on a deep stack.  The inner frames are the same, so the limit is applied from the innermost frame outward, not by truncating the printed text.

## The chain form

### Invocation

```gdb
kernlens-bt --chain
```

### Output

```text
native_safe_halt <- default_idle <- default_idle <- arch_cpu_idle <- default_idle_call <- do_idle <- do_idle <- cpu_startup_entry
```

### Reading it

Innermost first, joined by `<-`, symbol names only -- no addresses, no source lines -- which is what makes it fit on one line.  Repeated inlined symbols are kept rather than deduplicated, because collapsing them would misrepresent the depth.  `init_thread_union` appearing between frames is a known artefact of the kernel's stack layout, not a bad unwind.

## Notes

A frame showing `??` is one where the return address did not resolve -- often a stack-corruption artefact, and worth noting rather than hiding.  For anything where the addresses matter, do not use `--chain`: it deliberately drops them.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
