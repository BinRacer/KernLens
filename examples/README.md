# Examples

Runnable scripts, grouped by what you are trying to do rather than by
what they import.

| Directory | Use it when you want to |
| --- | --- |
| [`api/`](api/README.md) | write a script against the KernLens API |
| [`tracing/`](tracing/README.md) | trace kernel behaviour over time |
| [`breakpoints/`](breakpoints/README.md) | stop, or notice, at the right moment |

## Which one am I looking for?

The three overlap, so the split is by intent:

- **`api/`** — the script computes something or prints a report.  It may
  call `kdbg` (which needs a target) or only the pure-Python half (which
  does not).  Start here if you are writing your first script, or if you
  want a report you can run outside GDB.
- **`tracing/`** — the script installs one or more breakpoints and prints
  a *log* as the kernel runs.  It does not stop the debuggee; the
  breakpoints' `stop()` returns `False` and the output accumulates.
- **`breakpoints/`** — the script's purpose is to *stop*, or to decide
  whether to.  The interesting moment is a single trap, not a stream of
  events, so the filters live in the breakpoint.

A tracer that stops on a condition belongs in both; put it in
`tracing/` if the log is the product, in `breakpoints/` if the stop is.

## All examples expect the same startup

```gdb
(gdb) source /path/to/KernLens/gdbinit.py
(gdb) file /path/to/vmlinux
(gdb) target remote :1234
```

`gdbinit.py` installs the public names (`kdbg`, `KAddr`, `walk`, ...)
into GDB's `__main__`, which is the namespace a sourced file runs in.
That is why the examples do not `from kernlens import ...`: they use what
is already there.  `api/hello.py` shows the one exception -- a fallback
for running the file from a plain interpreter.

## Conventions

- Every script prints something on load, so sourcing it by accident is
  visible rather than silent.
- Commands a script registers are prefixed `kernlens-tracer-` or
  `kbp-`/`kwatch-` so they cannot shadow a real KernLens command.  This
  matters: an example that registered `kernlens-slab` would replace the
  built one and the difference would be very hard to see.
- The defaults are real values from the project's test kernel
  (Linux 6.1.134 in the pwn4kernel VM), not invented stand-ins.  Where a
  value is boot-specific -- the KASLR slide, `page_offset_base`,
  `vmemmap_base` -- the script reads it instead of assuming it.
- Nothing here is part of the package surface.  These are examples, not
  API guarantees; the stable interface is `gdbinit.py` plus the
  `kernlens-*` / `kl-*` commands.