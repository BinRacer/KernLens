"""Structural guarantees for the core / output / gdb package split."""

from __future__ import annotations

import ast
import io
import pathlib
import re
import tokenize
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
    "buddy.py",
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

    def test_range_deriver_lives_under_tools(self) -> None:
        self.assertTrue((ROOT / "tools" / "abi_ranges.py").is_file())
        package = SRC / "kernlens"
        self.assertFalse((package / "abi_ranges.py").exists())

    def test_range_deriver_reuses_the_registry(self) -> None:
        text = (ROOT / "tools" / "abi_ranges.py").read_text(encoding="utf-8")
        # It reads the registry to report which rows are missing, and it
        # must not hard-code an offset: the whole point is that the values
        # come from a probed kernel, never from the source text.  Only the
        # *code* is checked -- the docstring legitimately quotes the
        # measured 0x18 to explain what the tool is for.
        self.assertIn("from kernlens.gdb import layouts", text)
        self.assertIn("layouts.lookup", text)
        code = self._code_without_strings(text)
        self.assertNotRegex(code, r"0x[0-9a-fA-F]{2,}")

    @staticmethod
    def _code_without_strings(text: str) -> str:
        """Return *text* with comments and string literals removed."""
        pieces: list[str] = []
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            pieces.append(token.string)
        return " ".join(pieces)


class BannerTests(unittest.TestCase):
    """``images/banner.svg`` must stay a valid, self-contained SVG.

    It is the only image in the repository, so a broken one breaks the
    front page of both READMEs at once -- and it fails silently, because
    GitHub renders a malformed SVG as nothing rather than as an error.

    The failure that prompted these tests was a raw ``<`` inside a CSS
    comment in ``<style>``.  ``<style>`` content is XML *text*, so the
    character started a tag and the file stopped parsing at that line.
    """

    PATH = ROOT / "images" / "banner.svg"

    def _root(self):
        """The parsed root element.

        Un-annotated on purpose: importing ``xml.etree`` at module scope
        for a type name would make the module depend on it for one
        signature, and the test is about the file rather than the tree.
        """
        import xml.etree.ElementTree as ET

        return ET.parse(self.PATH).getroot()

    def test_parses_as_xml(self) -> None:
        """A malformed SVG renders as nothing, with no error anywhere.

        This is the exact failure that shipped once: a raw ``<`` inside a
        CSS comment made the file stop parsing at that line, and both
        READMEs silently lost their only image.
        """
        import xml.etree.ElementTree as ET

        ET.parse(self.PATH)  # raises ParseError on a malformed file

    def test_is_accessible_and_scalable(self) -> None:
        root = self._root()
        self.assertEqual(root.get("role"), "img")
        # Both ids referenced by `aria-labelledby` must exist, or screen
        # readers get an image with no name.
        ids = root.get("aria-labelledby", "").split()
        self.assertEqual(len(ids), 2, root.get("aria-labelledby"))
        present = {element.get("id") for element in root.iter()}
        for name in ids:
            self.assertIn(name, present)
        # A viewBox is what lets the same file render at README width and
        # in a 200px preview without a second asset.
        self.assertIsNotNone(root.get("viewBox"))

    def test_carries_the_surface_count(self) -> None:
        """The banner states the command count; a test keeps it true.

        The count is auto-checked against the command registry rather than
        the string, so a wrong number in the banner is a failure here.
        """
        from contract_spec import CANONICAL_COMMANDS

        text = "".join(
            (element.text or "") for element in self._root().iter()
        )
        self.assertIn(f"{len(CANONICAL_COMMANDS)} kl-* commands", text)

    def test_has_no_external_assets(self) -> None:
        """One file, no network, no rasters.

        A hosted font or a linked bitmap would make the banner depend on
        something the repository does not control, and GitHub's image
        proxy does not always fetch them.
        """
        raw = self.PATH.read_text(encoding="utf-8")
        for banned in ("<image", "xlink:href", ".png", ".jpg", ".woff"):
            self.assertNotIn(banned, raw)


class DocumentationTrackingTests(unittest.TestCase):
    """The repository tree in the docs must describe the real tree.

    ``docs/architecture.md`` carries a hand-drawn tree, and it drifted
    twice: once when the examples were regrouped and again when they were
    renamed.  Both times the failure was silent -- a stale name in
    passive-voice documentation looks exactly like a current one -- and
    both times a reader following it got a file-not-found.

    These tests are cheap because the check is narrow: every filename the
    tree block lists must exist somewhere in the repository, and every
    example must appear in it.  They do not attempt to verify the prose.
    """

    #: Files listed inside a code fence in architecture.md that are not
    #: repository paths: illustrative names in examples and the like.
    ILLUSTRATIVE = frozenset({"anything.py"})

    def _tree_block(self) -> str:
        text = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
        start = text.index("```\n")
        end = text.index("```", start + 4)
        return text[start:end]

    def test_every_name_in_the_tree_exists(self) -> None:
        block = self._tree_block()
        missing = []
        # Anchored at a word boundary start so a hyphenated long name
        # (`example-coverage-plan.md`) is matched whole rather than from
        # its last segment.
        for match in re.finditer(
            r"(?<![\w.-])[\w.]+\.(?:py|md|svg|example|toml|lock)", block,
        ):
            name = match.group(0)
            if name in self.ILLUSTRATIVE:
                continue
            if not list(ROOT.rglob(name)):
                missing.append(name)
        self.assertEqual(sorted(set(missing)), [])

    def test_every_example_appears_in_the_tree(self) -> None:
        """A new example must be listed, or the tree is already wrong.

        The reverse direction -- nothing listed that is not real -- is the
        test above; this one stops the tree from quietly omitting a whole
        directory's worth of files.
        """
        block = self._tree_block()
        absent = []
        for path in sorted((ROOT / "examples").rglob("*.py")):
            if path.name not in block:
                absent.append(str(path.relative_to(ROOT)))
        self.assertEqual(absent, [])

    def test_doc_paths_name_real_files(self) -> None:
        """No document may cite a path that the tree does not have.

        Scoped to paths that look rooted (``examples/``, ``tools/``,
        ``src/``, ...) because a bare ``foo.py`` is usually an
        illustrative name, while a rooted one is a claim about this
        repository.  CHANGELOG is exempt: it is a record of what was once
        true, so its historical paths must be allowed to dangle.
        """
        roots = ("src/", "tests/", "tools/", "examples/", "docs/", ".github/")
        stale = []
        for doc in ROOT.rglob("*.md"):
            if doc.name in {"CHANGELOG.md", "CREDITS.md"}:
                continue
            if any(part in {".git", ".tmp", ".venv"} for part in doc.parts):
                continue
            text = doc.read_text(encoding="utf-8", errors="replace")
            for token in re.findall(r"[\w./-]+\.(?:py|md|json|yml|toml)", text):
                if not token.startswith(roots):
                    continue
                if not (ROOT / token).exists():
                    stale.append(f"{doc.relative_to(ROOT)}: {token}")
        self.assertEqual(sorted(set(stale)), [])


if __name__ == "__main__":
    unittest.main()
