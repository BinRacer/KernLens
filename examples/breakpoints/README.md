# Breakpoint debugging

Scripts whose purpose is to **stop**, or to decide whether to.  The
interesting moment is one trap, not a stream of events — for the
streaming case see [`../tracing/`](../tracing/README.md).

| File | Stops when |
| --- | --- |
| [`conditional.py`](conditional.py) | `kfree` is called on one specific object, and only then; it reports every other hit silently |
| [`watchfield.py`](watchfield.py) | a struct field *becomes* a chosen value, e.g. a refcount reaches zero |

Both are commands, so they are used after the file is sourced, not by
sourcing alone.

## `conditional.py` — break, test, decide

```gdb
(gdb) source /path/to/KernLens/examples/breakpoints/conditional.py
(gdb) kbp-object 0xffff9a0d44c42b00
(gdb) continue
```

The point is the filter: stopping at every `kfree` and reading output by
hand is not debugging, it is scrolling.  Here every hit is evaluated and
passed through unless it concerns the target, so the single interesting
hit is the only one that stops.

Two details that matter in practice:

- The comparison is on the **object start**, not the raw argument.
  `kfree` may legitimately receive a pointer inside an object and rounds
  down to the slab head, so trapping on the exact argument would miss
  exactly the interior-pointer frees that a use-after-free produces.
  `kdbg.slab_object()` returns `(object_addr, cache)`, and its first
  element is that object start.
- The breakpoint **disables itself after the first match** unless
  `--keep` is given.  A v2 of your script that hits in a loop should not
  require a manual `delete breakpoints` to get the prompt back.

`kdbg.bp_spec("kfree")` is used rather than the bare symbol: under KASLR
the bare name would be planted at its link-time address.

## `watchfield.py` — field watchpoint with a value filter

```gdb
(gdb) source /path/to/KernLens/examples/breakpoints/watchfield.py
(gdb) kwatch-field 'struct page' _refcount.counter 0xffffea0000004800 --expect 0
(gdb) continue
```

Breaking on a function tells you it was called.  Watching a *field* tells
you it changed, which is usually the real question: a refcount, a state
enum, a pointer that must stay NULL while an object is on a list.

The filter is the useful part.  A hardware watchpoint fires on every
write to the address; `--expect N` reports only the transition *into* that
value, printing what it was before:

```
struct page._refcount.counter: 0x1 -> 0x0 (change 7, pc=0xffffffff81...)
```

That line is the whole reason for the example: "refcount reached zero
while the object is still on a list" is a use-after-free, and it is
invisible if you watch the callers instead.

One thing to notice: the watchpoint expression keeps the **struct type**
(`((struct page *)ADDR)->_refcount.counter`) instead of casting to
`unsigned long`.  For a nested field a raw cast reads the whole
containing struct and reports a plausible wrong number — the same trap
that makes `kl-read-field 'struct page' _refcount` fail (ask for
`_refcount.counter`).

### It needs a target with hardware watchpoints

This is the one example that cannot be demonstrated on the project's
QEMU test VM.  QEMU's gdbstub does not implement hardware watchpoints,
so `kwatch-field` reports:

```
cannot set a hardware watchpoint on ((struct page *)(0x...))->_refcount.counter:
Do not understand breakpoint type to set.; this target may not support them --
use a software breakpoint on the writing function instead
```

That is the honest answer rather than a stack trace, and it names the
workaround: a software breakpoint on the function that writes the field,
filtered the way `conditional.py` does it.  On a target with debug
registers available (bare metal, KVM with gdbstub support, or a physical
machine) the watchpoint works as written.

Also note that x86 provides only four hardware watchpoints per CPU, which
is why this is a `breakpoints/` tool and not a tracer: watching many
fields needs a different mechanism.

## Choosing between the two

| Question | Use |
| --- | --- |
| "is this object freed, and from where?" | `conditional.py` |
| "when did this value change?" | `watchfield.py` |
| "what happens over the next thousand calls?" | a tracer from `../tracing/` |

Hardware watchpoints are a scarce resource (four per CPU on x86), so
watching more than a couple of fields at once needs a tracer instead.