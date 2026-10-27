"""Structural guarantees for the core / output / gdb package split."""

from __future__ import annotations

import ast
import pathlib
import unittest

from kernlens import BitOps, IntCodec, IntFmt, KAddr, KPageTable, Logger, Palette
from kernlens.core.addr import KAddr as CoreAddr
from kernlens.core.bitops import BitOps as CoreBitOps
from kernlens.core.codec import IntCodec as CoreCodec
from kernlens.core.fmt import IntFmt as CoreFmt
from kernlens.core.paging import KPageTable as CorePaging
from kernlens.gdb import DebugConfig as LazyConfig
from kernlens.gdb.config import DebugConfig as DirectConfig
from kernlens.output import Logger as OutputLogger
from kernlens.output import Palette as OutputPalette


ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "kernlens"

LEGACY_MODULES = (
    "BitOps.py",
    "IntCodec.py",
    "IntFmt.py",
    "KAddr.py",
    "KPageTable.py",
    "Logger.py",
    "_Internal.py",
)

#: One module per closed kernel subsystem, plus the shared base.
INSPECTOR_MODULES = (
    "_base.py",
    "bpf.py",
    "buddy.py",
    "dmabuf.py",
    "dmesg.py",
    "kallsyms.py",
    "metadata.py",
    "modules.py",
    "slabcache.py",
    "structpage.py",
)

#: One module per command domain, plus the framework/help/formatting plumbing.
COMMAND_MODULES = (
    "__init__.py",
    "formatting.py",
    "framework.py",
    "help.py",
    "kernel_base.py",
    "memory.py",
    "metadata.py",
    "misc.py",
    "overview.py",
    "paging.py",
    "primitives.py",
)


class LayerBoundaryTests(unittest.TestCase):
    def test_layers_do_not_import_upward(self) -> None:
        forbidden = {
            "core": ("gdb", "output"),
            "output": ("gdb", "core"),
        }
        for package, blocked in forbidden.items():
            for path in sorted((SRC / package).glob("*.py")):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        names = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        names = [node.module or ""]
                    else:
                        continue
                    for name in names:
                        for prefix in blocked:
                            self.assertFalse(
                                name == prefix or name.startswith(prefix + "."),
                                f"{path} must not import {prefix}",
                            )

    def test_legacy_module_paths_are_gone(self) -> None:
        for name in LEGACY_MODULES:
            self.assertFalse(
                (SRC / name).exists(),
                f"{name} should have moved into a subpackage",
            )
        self.assertFalse(
            (SRC / "gdb" / "toolkit.py").exists(),
            "gdb.toolkit should be replaced by gdb.facade",
        )


class InspectorBoundaryTests(unittest.TestCase):
    def test_inspector_package_has_one_module_per_subsystem(self) -> None:
        package = SRC / "gdb" / "inspectors"
        present = {path.name for path in package.glob("*.py")}
        self.assertTrue(
            set(INSPECTOR_MODULES) <= present,
            f"missing inspector modules: {set(INSPECTOR_MODULES) - present}",
        )

    def test_inspectors_do_not_import_the_god_module(self) -> None:
        package = SRC / "gdb" / "inspectors"
        for path in sorted(package.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    self.assertNotIn(
                        module,
                        ("kernel", "facade", "api"),
                        f"{path} must not import gdb.{module}",
                    )

    def test_no_subsystem_stays_in_a_monolith(self) -> None:
        text = (SRC / "gdb" / "kernel.py").read_text(encoding="utf-8")
        # The facade is a thin composition shim; domain logic lives in
        # the inspector modules, so the classic section banners are gone.
        self.assertNotIn("# --- kallsyms ---", text)
        self.assertNotIn("# --- buddy allocator ---", text)
        self.assertLess(
            len(text.splitlines()), 150,
            "gdb/kernel.py should stay a thin facade",
        )


class CommandBoundaryTests(unittest.TestCase):
    def test_command_package_has_one_module_per_domain(self) -> None:
        package = SRC / "commands"
        present = {path.name for path in package.glob("*.py")}
        self.assertTrue(
            set(COMMAND_MODULES) <= present,
            f"missing command modules: {set(COMMAND_MODULES) - present}",
        )

    def test_gdbinit_is_only_a_bootstrap(self) -> None:
        text = (ROOT / "gdbinit.py").read_text(encoding="utf-8")
        self.assertLess(
            len(text.splitlines()), 220,
            "gdbinit.py should stay a thin bootstrap",
        )
        self.assertNotIn("class KernLens", text)
        self.assertNotIn("_HELP: dict", text)

    def test_command_modules_do_not_import_the_bootstrap(self) -> None:
        package = SRC / "commands"
        for path in sorted(package.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(
                        node.module,
                        "gdbinit",
                        f"{path} must not import the bootstrap",
                    )


class SingleRegistryTests(unittest.TestCase):
    def test_api_derives_its_tables_from_the_facade(self) -> None:
        text = (SRC / "gdb" / "api.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        # FACADE_FUNCTIONS and INSTANCE_NAMES must alias the facade's
        # derived tuples, not carry their own literal list.
        for node in tree.body:
            if not isinstance(node, ast.AnnAssign):
                continue
            name = getattr(node.target, "id", "")
            if name in ("FACADE_FUNCTIONS", "INSTANCE_NAMES"):
                self.assertNotIsInstance(
                    node.value, ast.Tuple,
                    f"{name} must not be a hand-maintained literal",
                )
        self.assertIn("FREE_FUNCTION_NAMES", text)
        self.assertIn("COMPONENT_NAMES", text)

    def test_facade_has_the_single_binding_table(self) -> None:
        text = (SRC / "gdb" / "facade.py").read_text(encoding="utf-8")
        self.assertIn("_BINDINGS", text)
        self.assertNotIn("self.debug = self.logger.debug", text)


class ColorRoleTests(unittest.TestCase):
    def test_color_roles_are_ansi_sequences(self) -> None:
        from kernlens.output import colors

        for name in colors.__all__:
            with self.subTest(role=name):
                value = getattr(colors, name)
                self.assertIsInstance(value, str)
                self.assertTrue(value.startswith("\033["), value)

    def test_command_layer_never_uses_raw_palette(self) -> None:
        """Commands paint through the semantic roles, not raw ANSI palettes.

        Every command module either wraps text in ``output.message``
        (pwndbg's role helpers) or reads named roles from
        ``output.colors``; none may reach for ``Palette`` members, so a
        restyle touches one file instead of every command.
        """
        package = SRC / "commands"
        for path in sorted(package.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(module=path.name):
                self.assertNotIn("Palette.", text)
                self.assertNotIn("import Palette", text)
                self.assertNotIn("\x1b[", text)

    def test_command_painting_uses_the_role_modules(self) -> None:
        package = SRC / "commands"
        users = {
            path.name
            for path in package.glob("*.py")
            if "from ..output import colors" in path.read_text(encoding="utf-8")
            or "from ..output import message" in path.read_text(encoding="utf-8")
        }
        self.assertIn("help.py", users)
        self.assertIn("overview.py", users)
        self.assertIn("paging.py", users)


class PublicSurfaceTests(unittest.TestCase):
    def test_root_exports_are_the_new_classes(self) -> None:
        self.assertIs(BitOps, CoreBitOps)
        self.assertIs(IntCodec, CoreCodec)
        self.assertIs(IntFmt, CoreFmt)
        self.assertIs(KAddr, CoreAddr)
        self.assertIs(KPageTable, CorePaging)
        self.assertIs(Logger, OutputLogger)
        self.assertIs(Palette, OutputPalette)

    def test_gdb_lazy_export_resolves_without_gdb(self) -> None:
        self.assertIs(LazyConfig, DirectConfig)


class LayoutRegistryTests(unittest.TestCase):
    """The fallback registry is gdb-free and the inspectors use it.

    Struct offsets must come from the debug info, then from the single
    registry, never from a literal baked into an inspector.
    """

    def test_layouts_module_imports_no_gdb(self) -> None:
        tree = ast.parse(
            (SRC / "gdb" / "layouts.py").read_text(encoding="utf-8")
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                self.assertNotIn(
                    name.split(".")[0], ("gdb",),
                    "gdb/layouts.py must not import the gdb module",
                )

    def test_inspectors_do_not_call_raw_offset_of_with_a_literal(self) -> None:
        # ``_offset_of``/``_sizeof`` take a hardcoded default; the
        # inspectors must go through ``_layout_offset``/``_layout_sizeof``
        # (which consult the registry) instead.
        package = SRC / "gdb" / "inspectors"
        for path in sorted(package.glob("*.py")):
            if path.name == "_base.py":
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(module=path.name):
                self.assertNotIn("self._offset_of(", text)
                self.assertNotIn("self._sizeof(", text)

    def test_registry_is_the_only_place_offsets_are_written(self) -> None:
        # The verified numeric offsets live in exactly one module.
        text = (SRC / "gdb" / "layouts.py").read_text(encoding="utf-8")
        self.assertIn("_LAYOUTS", text)
        self.assertIn("StructVariant", text)

    def test_btf_parser_imports_are_defensive(self) -> None:
        # ``btf`` is pure Python and unit-tested outside GDB, so its
        # ``import gdb`` must be guarded.
        text = (SRC / "gdb" / "btf.py").read_text(encoding="utf-8")
        self.assertIn("try:", text)
        self.assertIn("except ImportError:", text)

    def test_resolver_consults_btf_between_dwarf_and_the_registry(self) -> None:
        text = (SRC / "gdb" / "inspectors" / "_base.py").read_text(
            encoding="utf-8"
        )
        # The chain is spelled out in ``_resolve_offset`` / ``_resolve_sizeof``.
        self.assertIn("_dwarf_offset", text)
        self.assertIn("_btf_database", text)
        self.assertLess(
            text.index("def _dwarf_offset"),
            text.index("def _btf_database"),
            "DWARF must be tried before BTF",
        )


class ToolsLayoutTests(unittest.TestCase):
    """``tools/`` holds developer scripts, not part of the package."""

    def test_generator_lives_under_tools(self) -> None:
        self.assertTrue((ROOT / "tools" / "gen_layouts.py").is_file())
        package = SRC / "kernlens"
        self.assertFalse((package / "gen_layouts.py").exists())

    def test_generator_reuses_the_registry(self) -> None:
        text = (ROOT / "tools" / "gen_layouts.py").read_text(encoding="utf-8")
        self.assertIn("from kernlens.gdb import btf, layouts", text)
        # It must not carry its own copy of the offsets, nor invoke a tool
        # the user may not have (the probe reads BTF itself).
        self.assertNotIn("0x90", text)
        self.assertNotIn("0x60", text)
        self.assertNotIn('"bpftool"', text)


if __name__ == "__main__":
    unittest.main()
