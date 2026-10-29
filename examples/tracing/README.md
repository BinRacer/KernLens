# Tracing kernel behaviour

Scripts whose product is a **log**.  Each installs breakpoints that never
stop the debuggee — `stop()` returns `False` — so the kernel keeps
running and the interesting events accumulate in the output.

| File | What it traces |
| --- | --- |
| [`gdb_tracer.py`](gdb_tracer.py) | every `kfree`, printing the slab that owns the argument; also demonstrates registering your own commands |
| [`cve_2025_38616_tracer.py`](cve_2025_38616_tracer.py) | a full CVE-2025-38616 KTLS use-after-free chain, from the skb's refcounts to the double free |
| [`kaslr_retarget_tour.py`](kaslr_retarget_tour.py) | not events: it fixes the slide so a tracer's link-time addresses resolve at all |

## Before you trace anything: `kaslr_retarget_tour.py`

```gdb
(gdb) source /path/to/KernLens/examples/tracing/kaslr_retarget_tour.py
(gdb) retarget
```

Every address in a vmlinux is a link-time address.  On a KASLR kernel
nothing lives there, and the failure is quiet: a breakpoint set on
`0xffffffff81234567` reports success, never fires, and looks like the code
path was not taken.

`retarget` runs the commands that get you unstuck, in the order that gets
you unstuck fastest -- `kl-status` (what KernLens believes),
`kl-base -v` (what the target says, and which of three methods found it),
`kl-base` (apply it -- finding is not applying, and this is the step people
skip), and `kl-base text` / `kl-base offset` (the manual override for when
discovery fails).  It closes with `kl-color` and `kl-help`, which belong to
the same "fix the environment first" family.

Run it before the other two tracers.  A tracer that appears to see no
events is very often a tracer pointed at the wrong slide.

## The shape of a tracer

Two things distinguish a tracer from a breakpoint example:

```python
class SlabFreeBreakpoint(gdb.Breakpoint):
    def stop(self) -> bool:
        kdbg.print_slab(head)   # report
        return False             # never stop
```

1. **`stop()` always returns `False`.**  Returning `True` would suspend
   the kernel and turn the tracer into a debugger.  A tracer that
   accidentally returns `True` is not obviously broken — the session
   simply freezes on the next hit.
2. **The output is the deliverable.**  Which means it has to be readable
   at speed: one line per event, a stable prefix, and no formatting that
   needs a terminal wider than 80 columns.

## `gdb_tracer.py` — the small one

```gdb
(gdb) source /path/to/KernLens/examples/tracing/gdb_tracer.py
```

Reads two environment variables at load time, so it traces your symbol
without editing the file:

| Variable | Default | Meaning |
| --- | --- | --- |
| `KERNLENS_SYMBOL` | `kfree` | function to break on |
| `KERNLENS_ARG` | `$rdi` | GDB expression for the object/page argument |

The defaults are the hook point this project validates against: `kfree`'s
first argument on x86-64 System V is the object head in `$rdi`.  Hooking
`__slab_free` instead would make it `$rdx` (the third argument).

It also shows how to register commands without colliding with KernLens:
`kernlens-tracer-slab` and `kernlens-tracer-color` are prefixed and
tolerate a prior `gdbinit.py` load, because GDB replaces a duplicate
command silently rather than refusing it.

One detail worth noticing: the script adopts
`kdbg.kaslr_slide()` before installing the breakpoint.  A bare symbol
under KASLR is planted at its **link-time** address, so a tracer that
skips this appears to work while never firing.

## `cve_2025_38616_tracer.py` — the large one

A worked example of tracing a specific vulnerability rather than a
function.  It follows one skb through the KTLS path and prints each
refcount transition, so the double free is visible as a sequence:

```
[release] H->dataref 1->0
[defer?]  nodefer
[hold]    clone A_clone->n
[clone]   H->dataref 0->1
[kfree]   of n            <- the same object, freed twice
```

It reuses the commands `gdbinit.py` already installed — `trace-start`
calls the registered `kl-base` for automatic base selection — instead of
carrying its own copy of the KASLR logic.

Load it and start tracing:

```gdb
(gdb) source /path/to/KernLens/examples/tracing/cve_2025_38616_tracer.py
(gdb) trace-start
(gdb) continue
```

`trace-start manual` refuses a zero slide on purpose: a zero slide means
nokaslr addresses, and a tracer planted there looks correct while
watching the wrong memory.  Select a non-zero slide first with
`kl-base text` / `kl-base offset` if you need the manual path.

> This example has one known gap on Linux 6.1: `tcp_eat_recv_skb` is a
> `static` function with no `&`-expressible symbol, so `bp_spec()` cannot
> relocate it and the breakpoint lands at its link-time address.  The
> tracer warns about that rather than pretending it is relocated.

## Writing your own

Copy `gdb_tracer.py`: it is small enough to read in one sitting and it
already has the three things that are easy to get wrong — the KASLR
slide, the command-name prefix, and `return False`.