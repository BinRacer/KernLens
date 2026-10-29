# `kl-read`

Dump memory

**Canonical:** `kernlens-read`  
**Category:** memory & symbols  
**Synopsis:** `kl-read [-h] [-m {ascii}] address [count]`

Reads memory as 64-bit words with a symbol annotation per word, or as a hex+ASCII dump.  The counterpart of pwndbg's `x` for kernel memory.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | address to read |
|  | (optional) | number of 8-byte words, 1-64 (default 8) |
| `-m`, `--mode` | `ascii` | dump raw bytes with an ASCII sidebar |

## Words

### Invocation

```gdb
kl-read 0xffff9762c0400000
```

### Output

```text
0xffff9762c0400000: 0x636a231695c3cf14  ?? ??
0xffff9762c0400008: 0xc12c6d9a92ffae4c  ?? ??
0xffff9762c0400010: 0xb2c4dbfaf38c07f1  ?? ??
0xffff9762c0400018: 0x288e866676519973  ?? ??
0xffff9762c0400020: 0x161db5c53977a300  ?? ??
0xffff9762c0400028: 0x86808d4cc91c9499  ?? ??
0xffff9762c0400030: 0x462e739c293d3ae8  ?? ??
0xffff9762c0400038: 0xa85a0c31a79c42e2  ?? ??
```

### Reading it

Each row is `address: value symbol`.  The values here are the contents of a free page, so they are leftover data -- an uninitialised page keeps whatever was there before, which is precisely why `CONFIG_INIT_ON_ALLOC_DEFAULT_ON` exists.  The `??` annotations mean no symbol covers the value, which is correct for a data word.

## Hex and ASCII

### Invocation

```gdb
kl-read 0xffff9762c0400000 16 -m ascii
```

### Output

```text
16 byte(s) at 0xffff9762c0400000
ffff9762c0400000  14 cf c3 95 16 23 6a 63  4c ae ff 92 9a 6d 2c c1  |.....#jcL....m,.|
```

### Reading it

`-m ascii` switches to the `hexdump -C` style: eight bytes of hex, then the printable rendering, with non-printable bytes as `.`.  The byte count is the second positional, so `16` means two rows of eight.

## Notes

An unreadable address is reported per row instead of aborting, so a partially valid range still yields data.  The word size follows the 64-bit model: KernLens is x86_64-only.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
