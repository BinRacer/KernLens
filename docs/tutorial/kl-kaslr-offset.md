# `kernlens-kaslr-offset`

Set the slide directly

**Alias:** `kl-kaslr-offset`  
**Category:** kernel base & KASLR  
**Synopsis:** `kernlens-kaslr-offset [-h] offset`

Applies a slide you were given, with no derivation and no verification.  `0` means a non-KASLR kernel.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | KASLR slide (e.g. 0x18e00000) |

## Applying a numeric slide

### Invocation

```gdb
kernlens-kaslr-offset 0x17400000
```

### Output

```text
KASLR offset: +0x17400000
```

### Reading it

One line, echoing the value that was set.  The slide is a plain attribute on the facade, so this returns immediately; nothing is read from the target.

## Notes

Because nothing is verified, a wrong value here makes every later read wrong in a plausible way.  `kl-status` is the quick check afterwards: its `_text` row shows link and runtime side by side.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
