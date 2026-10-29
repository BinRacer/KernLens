# `kl-base`

Kernel base and KASLR slide

**Canonical:** `kernlens-base`  
**Category:** kernel base & KASLR  
**Synopsis:** `kl-base [-h] [-v] [-r] [command ...]`

Reports where the kernel text is loaded, and corrects the slide when the automatic answer is wrong.  These are four operations that used to be four commands (`kl-base`, `kl-kbase`, `kl-kaslr`, `kl-kaslr-offset`): there is one slide, so there is one command that reads and writes it.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | command | show \| text <runtime _text> \| offset <slide> \| idt [count] \| rebase \| <runtime _text> |
| `-v`, `--verbose` | — | also print the physical address of the text base (with show) |
| `-r`, `--rebase` | — | reload the symbol file at the detected base |

## The report

### Invocation

```gdb
kl-base
```

### Output

```text
kernel base: 0xffffffffae800000 (runtime)
KASLR offset: +0x2d800000
link _text: 0xffffffff81000000
method: symbol
status: kernel running
```

### Reading it

`kernel base` is the runtime `_text`; `KASLR offset` is the difference from the link-time address.  `method` names the source -- `symbol` means the `_text` symbol resolved, which is the strongest evidence available.  `status` reports whether there is a live inferior at all, since the slide can also be known from a core file.

## Reading the method

### Invocation

```gdb
kl-base show
```

### Output

```text
kernel base: 0xffffffffae800000 (runtime)
KASLR offset: +0x2d800000
link _text: 0xffffffff81000000
method: symbol
status: kernel running
```

### Reading it

When `_text` does not resolve, the fallback reads the IDT and takes the first handler's address, subtracting the handler's known link-time offset -- that is what `handler=` and `symbol=` report, and `idt:` shows the table's own base, limit, and where it was read from (`monitor` means the QEMU monitor, `memory` means the `idt_table` symbol).  The slide is verified against the IDT rather than trusted, because a wrong slide produces plausible-looking garbage everywhere else.

## Showing the physical address

### Invocation

```gdb
kl-base -v
```

### Output

```text
kernel base: 0xffffffffae800000 (runtime)
KASLR offset: +0x2d800000
link _text: 0xffffffff81000000
method: symbol
Physical: 0x1000000
status: kernel running
```

### Reading it

`-v` adds the physical address the text is loaded at, which is what a bootloader or QEMU command line refers to.  It is derived from the runtime virtual address with the same direct-map base the rest of KernLens uses.

## Dumping the IDT

### Invocation

```gdb
kl-base idt 4
```

### Output

```text
idt: base=0xfffffe0000000000 limit=0xfff count=256 source=monitor
idt[0]: offset=0xffffffffafc00990 sel=0x10 type=0xe ist=0 dpl=0 kernel
idt[1]: offset=0xffffffffafc00cd0 sel=0x10 type=0xe ist=3 dpl=0 kernel
idt[2]: offset=0xffffffffafc016f0 sel=0x10 type=0xe ist=2 dpl=0 kernel
idt[3]: offset=0xffffffffafc00ba0 sel=0x10 type=0xe ist=0 dpl=3 kernel
```

### Reading it

`idt N` prints the first N gate descriptors: offset, segment selector, gate type, IST index, DPL, and whether the address is in the kernel or user range.  The first entries are the CPU exceptions in architectural order, which makes a wrong IST or DPL immediately visible.

## Rebasing the symbol file

### Invocation

```gdb
kl-base rebase
```

### Output

```text
add symbol table from file "/home/bogon/workSpaces/pwn4kernel/kernels/6.1.134/01/vmlinux" at
	.text_addr = 0xffffffffae800000
rebased /home/bogon/workSpaces/pwn4kernel/kernels/6.1.134/01/vmlinux @ 0xffffffffae800000
```

### Reading it

`rebase` runs `add-symbol-file` for the loaded object at the recovered base, so GDB's own symbol lookups (and `info symbol`, and pwndbg's disassembly) start working at runtime addresses.  Without it GDB's symbol table remains link-time.  `--rebase` does the same after the report.

The path is whatever `file` loaded -- `rebase` never guesses one -- and a session with no symbol file is told so instead of being handed a default.  Each rebase first drops the relocated copy the previous one added, because `add-symbol-file` only ever adds: two rebases used to leave two copies, and `info symbol` at the newer base then answered with the *older* copy's nearest symbol.  The `(dropped N stale copy)` suffix counts what went; a first rebase prints none, because there was nothing stale to drop.

## Setting the slide directly

### Invocation

```gdb
kl-base offset 0x2d800000
```

### Output

```text
KASLR offset: +0x2d800000
status: applied
```

### Reading it

`offset` applies a slide you were given, with no derivation and no verification; `0` means a non-KASLR kernel.  The value is echoed back so a mistyped slide is visible immediately -- nothing here is compared with the target, which is why the echoed line matters.  A wrong value makes every later read wrong in a plausible way, so `kl-status` is the quick check afterwards: its `_text` row shows link and runtime side by side.

## Computing a slide from a known address

### Invocation

```gdb
kl-base text 0xffffffffae800000
```

### Output

```text
KASLR offset: +0x2d800000
link _text: 0xffffffff81000000 runtime _text: 0xffffffffae800000
status: applied
```

### Reading it

`text` takes a runtime `_text` -- from a leak, from `%pK` output, or from the monitor -- and derives the slide from it.  Both values are printed so a typo (an address that is not actually `_text`) shows up as an absurd slide instead of silently shifting every later read.  A bare address means the same thing: `kl-base 0xffffffff83000000` is `kl-base text ...`.

## Notes

12+ call sites add the slide to a link-time address themselves, which is why `link_text()` keeps returning the link-time value and this command is what reports the runtime one.  Prefer the default report on a live machine: it derives the slide *and* cross-checks it against the IDT.  The explicit subcommands are for when the address came from somewhere else.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
