#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""Kernel metadata: version banner, boot cmdline, and the embedded config.

Every read is keyed off a *symbol* (``linux_banner``, ``saved_command_line``,
``kernel_config_data``) rather than a fragile struct offset, so the data
keeps resolving once the KASLR slide has been set.
"""

from __future__ import annotations

import re
import zlib

from ._base import InspectorBase

#: The version banner always starts with this prefix.
VERSION_PREFIX = "Linux version"

#: ``Linux version 6.8.0-rc1...`` -> ``(6, 8, 0)``.
VERSION_RE: re.Pattern[str] = re.compile(
    r"Linux version (\d+)\.(\d+)(?:\.(\d+))?"
)


class MetadataInspector(InspectorBase):
    """Kernel version, command line, and ``CONFIG_*`` access."""

    __slots__: tuple[str, ...] = ()

    #: Cached parsed config (``None`` until first read); slot on the
    #: composing :class:`~kernlens.gdb.kernel.KernelInspector`.
    _config: "dict[str, str] | None"

    # --- version --------------------------------------------------------

    def version(self) -> str | None:
        """Return the kernel version banner, or ``None`` when unreadable."""
        addr = self._reader.kvar_addr("linux_banner")
        if not addr:
            return None
        text = self._cstring(addr)
        if not text:
            return None
        return text.strip() or None

    def release(self) -> tuple[int, ...] | None:
        """Return the kernel release as ``(major, minor[, patch])``."""
        text = self.version()
        if text is None:
            return None
        match = VERSION_RE.search(text)
        if match is None:
            return None
        return tuple(int(group) for group in match.groups() if group)

    # --- command line ---------------------------------------------------

    def cmdline(self) -> str | None:
        """Return the boot command line, or ``None`` when unreadable."""
        addr = self._reader.kvar_addr("saved_command_line")
        if not addr:
            return None
        buffer = self._reader.u64(f"*(unsigned long *){addr:#x}")
        if not buffer:
            return None
        return self._cstring(buffer)

    # --- kernel config --------------------------------------------------

    def kconfig(self) -> dict[str, str]:
        """Return the parsed ``CONFIG_*`` mapping (empty when absent)."""
        if self._config is None:
            self._config = self._load_config()
        return self._config

    def _load_config(self) -> dict[str, str]:
        start = self._reader.kvar_addr("kernel_config_data")
        end = self._reader.kvar_addr("kernel_config_data_end")
        if not start or not end or start >= end:
            return {}
        blob = self._read_bytes(start, end - start)
        if not blob:
            return {}
        plain = self._decompress(blob)
        if plain is None:
            return {}
        result: dict[str, str] = {}
        for line in plain.split(b"\n"):
            if b"=" not in line:
                continue
            name, _, value = line.partition(b"=")
            result[name.decode("ascii", "replace")] = value.decode(
                "ascii", "replace"
            )
        return result

    @staticmethod
    def _decompress(blob: bytes) -> bytes | None:
        """Inflate the ``IKCFG`` image (gzip, then zlib, then raw)."""
        for wbits in (16, 15, 31, -15):
            try:
                return zlib.decompress(blob, wbits)
            except zlib.error:
                continue
        return None

    def config_key(self, name: str) -> str:
        """Return ``CONFIG_`` + upper-cased *name*."""
        return "CONFIG_" + name.upper()

    def config_get(self, name: str) -> str | None:
        """Look up a config value, accepting ``X``, ``X`` upper, or the key."""
        data = self.kconfig()
        for candidate in (
            self.config_key(name),
            name.upper(),
            name,
        ):
            if candidate in data:
                return data[candidate]
        return None

    def config_contains(self, name: str) -> bool:
        """Return ``True`` when the kernel sets *name*."""
        return self.config_get(name) is not None

    def config_update(self, path: str) -> int:
        """Merge ``CONFIG_*`` lines from *path*; return the lines merged."""
        merged = 0
        with open(path, encoding="utf-8") as handle:
            for line in handle.read().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                self.kconfig()[name.strip()] = value.strip()
                merged += 1
        return merged


__all__ = ["MetadataInspector", "VERSION_PREFIX", "VERSION_RE"]