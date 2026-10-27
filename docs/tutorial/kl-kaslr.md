# `kernlens-kaslr`

Slide from a runtime address

**Alias:** `kl-kaslr`  
**Category:** kernel base & KASLR  
**Synopsis:** `kernlens-kaslr [-h] runtime_text`

Sets the KASLR slide from a runtime `_text` you already have -- from a leak, from `%pK` output, or from the monitor.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | runtime address of the _text symbol |

## Deriving and applying

### Invocation

```gdb
kernlens-kaslr 0xffffffff91c00000
```

### Output

```text
KASLR offset: +0x10c00000
link _text: 0xffffffff81000000 runtime _text: 0xffffffff91c00000
```

### Reading it

The difference from the link-time `_text` is the slide.  Both values are printed so a typo (an address that is not actually `_text`) shows up as an absurd slide instead of silently shifting every later read.

## Notes

Prefer `kl-kbase` when the machine is live: it derives the same value *and* cross-checks it against the IDT.  This command is for when you already have the address from elsewhere.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
