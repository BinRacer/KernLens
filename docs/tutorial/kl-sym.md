# `kernlens-sym`

Address to symbol

**Alias:** `kl-sym`  
**Category:** memory & symbols  
**Synopsis:** `kernlens-sym [-h] address`

Resolves an address to the symbol that covers it and its source location, using the loaded debug info.  Equivalent to GDB's `info symbol` but KASLR-aware.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | address to resolve |

## A text address

### Invocation

```gdb
kernlens-sym 0xffffffff98400100
```

### Output

```text
0xffffffff98400100  secondary_startup_64 at arch/x86/kernel/head_64.S:282
```

### Reading it

The symbol, its section, and `file:line` -- the line comes from DWARF, so it is exact for this build.  The address printed first is the one that was queried, unchanged.

## A data address

### Invocation

```gdb
kernlens-sym 0xffff992880400000
```

### Output

```text
0xffff992880400000  ?? at ??
```

### Reading it

`?? at ??` means nothing covers the address.  For a direct-map address that is the correct answer -- the direct map is not a symbol, it is a mapping -- and it is worth seeing so you do not mistake it for a broken symbol table.

## Notes

GDB's symbol table is link-time.  KernLens subtracts the slide before asking GDB, which is why this resolves on a KASLR kernel where a plain `info symbol` would miss.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
