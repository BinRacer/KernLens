# `kernlens-kbase`

Find the kernel base

**Alias:** `kl-kbase`  
**Category:** kernel base & KASLR  
**Synopsis:** `kernlens-kbase [-h] [-r] [-v]`

Recovers the kernel's runtime base from the live machine, independently of any symbol table.  This is what makes KernLens usable on a KASLR kernel whose `vmlinux` is loaded at its link-time addresses.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
| `-r`, `--rebase` | — | rebase loaded symbol file |
| `-v`, `--verbose` | — | also print the physical address of the text base |

## The search

### Invocation

```gdb
kernlens-kbase
```

### Output

```text
text base: 0xffffffff91c00000
method: symbol  handler=0xffffffff93000990
symbol: asm_exc_divide_error
idt: base=0xfffffe0000000000 limit=0xfff source=monitor
link _text: 0xffffffff81000000  kaslr=+0x10c00000
hint: kl-kbase --set applies this slide
```

### Reading it

`method: symbol` is the strongest case: the `_text` symbol was resolvable.  When it is not, the fallback reads the IDT and takes the first handler's address, subtracting the handler's known link-time offset -- that is what `handler=` and `symbol=` report.  `idt:` shows the table's own base, limit, and where it was read from (`monitor` means the QEMU monitor, `memory` means the `idt_table` symbol).

## Showing the physical address

### Invocation

```gdb
kernlens-kbase -v
```

### Output

```text
text base: 0xffffffff91c00000
method: symbol  handler=0xffffffff93000990
symbol: asm_exc_divide_error
idt: base=0xfffffe0000000000 limit=0xfff source=monitor
link _text: 0xffffffff81000000  kaslr=+0x10c00000
Physical: 0x1000000
hint: kl-kbase --set applies this slide
```

### Reading it

`-v` adds the physical address the text is loaded at, which is what a bootloader or QEMU command line refers to.  It is derived from the runtime virtual address with the same direct-map base the rest of KernLens uses.

## Dumping the IDT

### Invocation

```gdb
kernlens-kbase -i 4
```

### Output

```text
idt: base=0xfffffe0000000000 limit=0xfff count=256 source=monitor
idt[0]: offset=0xffffffff93000990 sel=0x10 type=0xe ist=0 dpl=0 kernel
idt[1]: offset=0xffffffff93000cd0 sel=0x10 type=0xe ist=3 dpl=0 kernel
idt[2]: offset=0xffffffff930016f0 sel=0x10 type=0xe ist=2 dpl=0 kernel
idt[3]: offset=0xffffffff93000ba0 sel=0x10 type=0xe ist=0 dpl=3 kernel
```

### Reading it

`-i N` prints the first N gate descriptors: offset, segment selector, gate type, IST index, DPL, and whether the address is in the kernel or user range.  The first entries are the CPU exceptions in architectural order, which makes a wrong IST or DPL immediately visible.

## Rebasing the symbol file

### Invocation

```gdb
kernlens-kbase -r
```

### Output

```text
text base: 0xffffffff91c00000
method: symbol  handler=0xffffffff93000990
symbol: asm_exc_divide_error
idt: base=0xfffffe0000000000 limit=0xfff source=monitor
link _text: 0xffffffff81000000  kaslr=+0x10c00000
hint: kl-kbase --set applies this slide
add symbol table from file "/home/bogon/workSpaces/pwn4kernel/kernels/6.1.134/01/vmlinux" at
	.text_addr = 0xffffffff91c00000
rebased /home/bogon/workSpaces/pwn4kernel/kernels/6.1.134/01/vmlinux @ 0xffffffff91c00000
```

### Reading it

`-r` runs `add-symbol-file` for the loaded object at the recovered base, so GDB's own symbol lookups (and `info symbol`, and pwndbg's disassembly) start working at runtime addresses.  Without it GDB's symbol table remains link-time.

## Applying an explicit value

### Invocation

```gdb
kernlens-kbase --offset 0x10c00000
```

### Output

```text
KASLR offset: +0x10c00000
```

### Reading it

`--offset` sets the slide directly and prints nothing else, which is the form to use in a script that already knows the slide.

## Computing a slide from a known address

### Invocation

```gdb
kernlens-kbase --text 0xffffffff81000000
```

### Output

```text
KASLR offset: +0x0
link _text: 0xffffffff81000000 runtime _text: 0xffffffff81000000
```

### Reading it

`--text` takes a runtime `_text` and derives the slide from it.  Passing the link-time address yields `+0x0`, which is a useful sanity check that the inputs are what you think they are.

## Notes

`-s/--set` and `-p/--phys` are KernLens-only additions hidden from `-h`, so the visible surface stays pwndbg's.  The slide is verified against the IDT rather than trusted, because a wrong slide produces plausible-looking garbage everywhere else.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
