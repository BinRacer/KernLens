# `kl-kvar`

Read a kernel variable

**Canonical:** `kernlens-kvar`  
**Category:** memory & symbols  
**Synopsis:** `kl-kvar [-h] symbol`

Reads a named kernel global, applying the KASLR slide and re-deriving it if the read fails.  This is the command for `page_offset_base` and friends, where `&symbol` under KASLR reads nothing useful.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | kernel global name (e.g. jiffies), with optional leading & |

## A base variable

### Invocation

```gdb
kl-kvar page_offset_base
```

### Output

```text
symbol: page_offset_base
address: 0xffffffffb05893a8
value: 0xffff90c340000000
```

### Reading it

Three rows: the symbol name, the runtime address it lives at, and its value.  The distinction is the whole point -- the address is in `.data` near `_text`, while the value is a direct-map base far away.  Both are KASLR-shifted, and KernLens re-derives the slide once if the first read returns nothing.

## A numeric variable

### Invocation

```gdb
kl-kvar nr_online_nodes
```

### Output

```text
symbol: nr_online_nodes
address: 0xffffffffb0c68384
value: 0x100000001
```

### Reading it

For an `int` the value is read at its natural width, not as eight bytes: reading a 4-byte variable as 8 bytes picks up the neighbouring field and produces a large, plausible-looking wrong number.

## Notes

Anonymous symbols (`static` functions, some kallsyms entries) have no `&`-expressible symbol, so a read through the symbol name fails even though the address exists.  That is a DWARF limitation, and the command reports it rather than returning zero.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
