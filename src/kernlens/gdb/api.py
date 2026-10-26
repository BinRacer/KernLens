#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Stable public API for Python scripts sourced inside GDB.

``gdbinit.py`` runs in GDB's ``__main__`` namespace.  Scripts loaded
later with GDB's ``source`` command run in the same namespace, so the
startup file calls :func:`install_public_api` there.  A script can then
use the host-side API and the facade directly, without imports::

    # source /path/to/KernLens/gdbinit.py
    # source /path/to/trace.py

    print(KAddr.is_direct_map(0xFFFF888000001000))
    print(kdbg.nr_cpus())
    print(read_kvar("jiffies"))
    print(walk(0xFFFF888000001234))

The names installed here are deliberately a documented surface: the
public package exports, ``KernelDebugger`` / ``kdbg``, the facade
methods listed in :data:`FACADE_FUNCTIONS`, and the stateless core
helpers such as ``byte_swap64``, ``popcount``, ``pack_u16``,
``virt_to_phys``, and ``split_4``.  ``KERNLENS_API`` is the complete
installed mapping for discovery and tooling; ``KERNLENS_QUALIFIED`` and
``KERNLENS_PREFIXED`` hold class-qualified aliases for collision-free
access.  ``KERNLENS_INSTANCES`` and ``KERNLENS_CLASSES`` expose the
stateful defaults and their constructors.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from typing import Any, MutableMapping

import kernlens as _kernlens
from .. import (
    BitOps,
    IntCodec,
    IntFmt,
    KAddr,
    KPageTable,
)
from .. import __all__ as _PACKAGE_EXPORTS
from . import __all__ as _GDB_EXPORTS
from .facade import (
    COMPONENT_NAMES,
    FREE_FUNCTION_NAMES,
    KernelDebugger,
    kdbg,
)


#: Facade methods that are useful as free functions in tracer code.
#: Derived from the facade's single ``_BINDINGS`` table so the two can
#: never drift apart.
FACADE_FUNCTIONS: tuple[str, ...] = FREE_FUNCTION_NAMES


#: Stateless core namespaces whose public static methods become free
#: functions (for example ``BitOps.byte_swap64`` -> ``byte_swap64``).
CORE_FUNCTION_CLASSES: tuple[type, ...] = (
    BitOps,
    IntCodec,
    KAddr,
    KPageTable,
    IntFmt,
)

#: Stateful components composed into the shared ``kdbg`` facade.  They
#: are installed as default instances so tracer code can use
#: ``logger.info(...)`` or ``styler.addr(...)`` immediately; use
#: ``KERNLENS_CLASSES`` to construct independent instances instead.
#: Derived from the facade's component table.
INSTANCE_NAMES: tuple[str, ...] = COMPONENT_NAMES


def core_functions() -> dict[str, Callable[..., Any]]:
    """Return public static methods from the core namespaces.

    Tracer code can call ``byte_swap64(...)``, ``popcount(...)``,
    ``pack_u16(...)``, ``virt_to_phys(...)``, ``split_4(...)``, and the
    rest of the stateless helpers without spelling the class name.  The
    explicit facade free functions remain available through ``kdbg``
    when a name collides (for example ``bits`` / ``addr`` / ``size``).
    """
    functions: dict[str, Callable[..., Any]] = {}
    for namespace in CORE_FUNCTION_CLASSES:
        for name, member in vars(namespace).items():
            if name.startswith("_") or not isinstance(member, staticmethod):
                continue
            functions.setdefault(name, getattr(namespace, name))
    return functions


def qualified_functions() -> dict[str, Callable[..., Any]]:
    """Return ``"ClassName.method"`` keys for class-qualified access.

    The values are the same functions as :func:`core_functions`, but the
    dot in the key makes the owner explicit and prevents a tracer from
    depending on an ambiguous global name.  Typical use::

        KERNLENS_QUALIFIED["BitOps.byte_swap64"](value)
    """
    functions: dict[str, Callable[..., Any]] = {}
    for namespace in CORE_FUNCTION_CLASSES:
        for name, member in vars(namespace).items():
            if name.startswith("_") or not isinstance(member, staticmethod):
                continue
            key = f"{namespace.__name__}.{name}"
            functions.setdefault(key, getattr(namespace, name))
    return functions


def prefixed_functions() -> dict[str, Callable[..., Any]]:
    """Return identifier-safe ``ClassName_method`` aliases.

    These are convenient when a dotted lookup is awkward inside a GDB
    expression::

        BitOps_byte_swap64(value)
    """
    return {
        key.replace(".", "_"): function
        for key, function in qualified_functions().items()
    }


def public_api() -> dict[str, Any]:
    """Return the names exposed to sourced GDB scripts.

    The package's public classes and constants are included first, then
    the stateless core helpers, the facade object, and its selected
    free-function aliases.  Methods that a facade implementation does
    not provide are skipped, which keeps the bootstrap usable with a
    reduced test double.
    """
    names: dict[str, Any] = {
        name: getattr(_kernlens, name) for name in _PACKAGE_EXPORTS
    }
    gdb_package = importlib.import_module("kernlens.gdb")
    names.update(
        {
            "kernlens": _kernlens,
            "kernlens_gdb": gdb_package,
            "KernelDebugger": KernelDebugger,
            "kdbg": kdbg,
        }
    )
    for name in _GDB_EXPORTS:
        if name in names:
            continue
        try:
            names[name] = getattr(gdb_package, name)
        except (AttributeError, ImportError):
            # A reduced test double may not provide every adapter.
            continue
    names["KERNLENS_CLASSES"] = {
        name: value
        for name, value in names.items()
        if isinstance(value, type) and not name.startswith("_")
    }
    instances: dict[str, Any] = {"kdbg": kdbg}
    for name in INSTANCE_NAMES:
        value = getattr(kdbg, name, None)
        if value is not None:
            instances[name] = value
            names.setdefault(name, value)
    names["KERNLENS_INSTANCES"] = instances
    for name, function in core_functions().items():
        # Core statics are installed before facade aliases so plain
        # helpers keep their documented signatures (for example
        # ``bits(value, bits=8)`` rather than the styler's
        # keyword-only width).
        names.setdefault(name, function)
    names["KERNLENS_QUALIFIED"] = qualified_functions()
    names["KERNLENS_PREFIXED"] = prefixed_functions()
    for name, function in names["KERNLENS_PREFIXED"].items():
        names.setdefault(name, function)
    for name in FACADE_FUNCTIONS:
        value = getattr(kdbg, name, None)
        if callable(value):
            names.setdefault(name, value)
    return names


def install_public_api(
    namespace: MutableMapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Install the public API into *namespace* (default: ``__main__``).

    GDB executes sourced Python files in ``__main__``.  Passing an
    explicit namespace is useful for tests and for callers that want to
    keep the injected names local.  The returned mapping is also stored
    as ``KERNLENS_API`` in the target namespace.
    """
    if namespace is None:
        namespace = sys.modules["__main__"].__dict__
    names = public_api()
    namespace.update(names)
    namespace["KERNLENS_API"] = names
    return names


__all__ = [
    "CORE_FUNCTION_CLASSES",
    "FACADE_FUNCTIONS",
    "INSTANCE_NAMES",
    "KernelDebugger",
    "core_functions",
    "install_public_api",
    "kdbg",
    "prefixed_functions",
    "public_api",
    "qualified_functions",
]