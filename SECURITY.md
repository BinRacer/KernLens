# Security policy

KernLens reads kernel memory from a debugger. It is a diagnostic tool
for targets you already control, and it is also a tool people point at
kernels they do not control, so both kinds of report matter here.

## Reporting a vulnerability

**Do not open a public issue.**  Report privately, by either:

- GitHub's [private vulnerability reporting][ghsa] (Security tab ->
  "Report a vulnerability"), which keeps the thread private and gives us
  a place to draft the advisory; or
- email to `native.lab@outlook.com` with `KERNLENS SECURITY` in the
  subject line.

[ghsa]: https://github.com/BinRacer/KernLens/security/advisories/new

Include what you have: the kernel version and config, the command or API
call, and the output.  A reproducer against a stock kernel is ideal but
not required -- a wrong answer with the inputs that produced it is
already useful, because wrong answers are the failure mode this project
cares about most.

Expect an acknowledgement within a few days.  This is a single-maintainer
project, so please allow time before escalating.

## What counts

**Bugs that produce a confident wrong answer.**  A page walk that
reports a present mapping that is not there, a SLUB decode that names
the wrong cache, a symbol resolve that silently falls back to a nearby
address.  These are the most serious class: the tool exists to be
trusted about memory, and a plausible wrong number is worse than an
error, because a researcher will build on it.

**Unsafe behaviour against the target.**  KernLens installs no
breakpoint at load time, and every command but one only reads: it walks
tables, decodes structures, resolves symbols, and returns.  The
exception is `kl-msr --write`, which sets an MSR through GDB's register
interface, and it is the only path in the tool that changes the target.
Anything else that writes target memory, corrupts a target structure, or
stops a debuggee the user did not ask to stop is a security bug, not a
feature request.

**Crash or hang of GDB.**  An unhandled exception escaping a command
turns a debugging session into a lost session, which on a live target
can mean an unrecoverable machine.

**Incorrect `kl-kchecksec` output.**  This command reports mitigations.
Reporting a mitigation as *present* when it is absent is the dangerous
direction; report that first.

## What does not

- **A wrong answer you were warned about.**  Commands refuse rather than
  guess, and print why: `not present`, `unknown`, `unresolved`, or a
  `-` in a field.  A value the tool explicitly marks as unconfirmed is
  documented behaviour, not a vulnerability -- though a case where the
  marker is missing is a bug worth reporting.
- **Needing a debuggee.**  Most of the tool requires a `vmlinux` with
  debug info and a `target remote`.  That is the design.
- **Kernels other than x86_64.**  The page-table and `struct page`
  decoding are written against x86_64.  Other architectures are not
  supported, and results on them are not claims.
- **A struct offset that moved between kernel versions.**  Layouts are
  resolved from DWARF, then BTF, then a verified fallback registry; a
  kernel whose layout is not resolvable is refused.  If it is *not*
  refused and prints a wrong field, that is the first category above.

## Supported versions

Fixes land on `main` and in the newest release.  Older releases are not
back-patched; the tool is a development aid, not a long-lived service.

| Version | Supported |
| --- | --- |
| `main` | yes |
| newest tag | yes |
| older tags | no |

The environments that have actually been exercised, and the ones that are
only expected to work, are in [`docs/en/compatibility.md`](docs/en/compatibility.md).