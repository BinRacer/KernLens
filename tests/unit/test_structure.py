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

#: Anything that looks like a filename: word characters, dots, hyphens,
#: underscores and slashes, a dot, then an extension-ish tail.
#:
#: Three separate narrowings were tried here and all three were wrong in
#: the same direction -- they matched less than they claimed:
#:
#: * ``[\w.]+`` cannot match a hyphenated name such as
#:   ``some-long-name.md``, because a hyphen is not a word character;
#: * adding the hyphen but keeping an extension *whitelist* still cannot
#:   match ``py.typed`` or ``gdbinit.example``, whose tails are not in it;
#: * leaving the slash out means the rooted-path guard matches nothing at
#:   all, since every path it looks for starts with ``src/`` or ``docs/``.
#:
#: Measured: with the whitelist, deleting ``src/kernlens/py.typed`` -- a
#: file ``docs/architecture.md`` lists as current -- failed no test.  Each
#: version was verified by deleting the file it was supposed to guard, and
#: every version except this one reported success.
#:
#: A false positive is caught immediately, because every token here is
#: checked against the real tree in a test that runs on every commit; a
#: false negative is not.  So the pattern errs wide.
DOC_FILENAME = re.compile(r"[\w./-]+\.\w[\w-]*")

#: Tokens that look like filenames but belong outside this repository.
#: ``~/.gdbinit`` appears in the architecture tree as the path a reader
#: sources KernLens *from*, so it is not a claim about our own tree.
NOT_IN_REPO = frozenset({"/.gdbinit"})

#: Directories that are not the repository's own content.  Excluded from
#: the bare-name search because they contain copies of common filenames:
#: ``.venv`` ships ``py.typed`` for six of its own packages, so every
#: lookup for that name succeeded no matter what ``src/`` held, and
#: deleting the real marker failed no test.  That is the third way this
#: guard was silently blind (see ``DOC_FILENAME``), and the same shape as
#: the first two: a search over more than the thing being guarded.
VENDORED = frozenset({
    ".git", ".tmp", ".venv", "build", "dist", "__pycache__", "node_modules",
    # ``mkdocs build`` output; it mirrors ``docs/`` and is gitignored.
    "site",
})


def doc_filenames(text: str) -> list[str]:
    """Return every filename *text* mentions, minus the known outsiders.

    Both guards call this, so a path absent from the tree is spotted in
    the architecture block and in the prose by the same rule.  They were
    written separately once and drifted apart, which is how the two plan
    documents went unnoticed.
    """
    return [name for name in DOC_FILENAME.findall(text) if name not in NOT_IN_REPO]


def path_exists(token: str) -> bool:
    """True when *token* names something in this checkout.

    A token containing a slash is used as a path relative to the root.  A
    bare name is searched for across the tree, because the architecture
    block lists files without their directory -- but only outside
    :data:`VENDORED`, else a name that any installed package also ships
    (``py.typed``, ``__init__.py``) resolves to the copy in ``.venv``.
    """
    if "/" in token:
        return (ROOT / token).exists()
    return any(
        not any(part in VENDORED for part in path.relative_to(ROOT).parts)
        for path in ROOT.rglob(token)
    )


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
        # The checkout shim is deliberately tiny: it locates ``src/`` and
        # hands the real bootstrap the namespace it was sourced in.
        shim = (ROOT / "gdbinit.py").read_text(encoding="utf-8")
        self.assertLess(
            len(shim.splitlines()), 40,
            "gdbinit.py should stay a checkout shim",
        )
        self.assertIn("from kernlens.gdbinit import bootstrap", shim)

        # The implementation moved into the package so the wheel can ship
        # it; it is still a bootstrap, not a home for command logic.
        text = (SRC / "gdbinit.py").read_text(encoding="utf-8")
        self.assertLess(
            len(text.splitlines()), 220,
            "the packaged gdbinit.py should stay a thin bootstrap",
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
        """``_BINDINGS`` stays the source of truth for the flat surface.

        The facade binds each name with an explicit
        ``self.<name>: Final = self.<component>.<member>`` assignment so a
        type checker can see the method signature; a ``setattr`` loop left
        the whole surface invisible.  Those assignments are a second spelling
        of the table, so this compares the two and fails on any drift in
        either direction.  (See ``CHANGELOG.md``: a facade that calls
        ``kdbg.info`` must not report an attribute error.)
        """
        text = (SRC / "gdb" / "facade.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        bindings: tuple[tuple[str, str, str, bool], ...] = ()
        init: ast.FunctionDef | None = None
        for node in tree.body:
            if (
                isinstance(node, ast.AnnAssign)
                and getattr(node.target, "id", "") == "_BINDINGS"
            ):
                bindings = ast.literal_eval(node.value)
            elif isinstance(node, ast.ClassDef) and node.name == "KernelDebugger":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        init = item
        self.assertTrue(bindings)
        self.assertIsNotNone(init)
        self.assertNotIn(
            "_free in _BINDINGS", text,
            "the facade must bind explicitly; a setattr loop is invisible "
            "to type checkers",
        )
        bound: list[tuple[str, str, str]] = []
        for node in ast.walk(init):
            # ``self.<name>: Final = self.<component>.<member>``.  ``Final``
            # is what makes ``pyright --verifytypes`` count the binding as a
            # declared type instead of an inference; the annotation is part
            # of the contract this test guards.
            if not isinstance(node, ast.AnnAssign) or node.value is None:
                continue
            target, value = node.target, node.value
            if not (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Attribute)
                and isinstance(value.value.value, ast.Name)
                and value.value.value.id == "self"
            ):
                continue
            if not (
                isinstance(node.annotation, ast.Name)
                and node.annotation.id == "Final"
            ):
                self.fail(
                    "facade binding is not declared Final: "
                    + ast.unparse(node)
                )
            bound.append((target.attr, value.value.attr, value.attr))
        self.assertEqual(
            bound, [(name, component, member) for name, component, member, _ in bindings]
        )


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

    def test_the_short_host_cli_delegates_to_the_long_one(self) -> None:
        """``bin/kl`` is the short spelling of ``bin/kernlens``.

        GDB commands have two spellings -- ``kernlens-<verb>`` and its
        ``kl-<verb>`` alias -- and the host-side CLI is the same tool for
        the other interpreter.  Having only the long name meant a reader
        who had just typed ``kl-status`` had to remember
        ``kernlens doctor`` one prompt later.

        The wrapper execs the long script instead of repeating its
        ``PYTHONPATH`` setup: two copies of "where is ``src/``" is two
        places to get it wrong, and the package path is the one thing
        that has to be right for either to work at all.
        """
        short = ROOT / "bin" / "kl"
        self.assertTrue(short.is_file())
        # It has to be executable, or `./bin/kl doctor` is a permission
        # error rather than a command.
        self.assertTrue(short.stat().st_mode & 0o111)
        text = short.read_text(encoding="utf-8")
        self.assertIn('exec "$here/kernlens" "$@"', text)
        # Only the code counts: the comment explains that the long script
        # is where `PYTHONPATH` is set, which is the point of delegating.
        code = "\n".join(
            line for line in text.splitlines()
            if not line.lstrip().startswith("#")
        )
        self.assertNotIn("PYTHONPATH", code)
        self.assertIn("exec", code)

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

    def test_any_command_count_it_states_matches_the_registry(self) -> None:
        """If the banner names a count, the count has to be right.

        It used to say "30 kl-* commands" and a test required it to.  That
        made the banner one more place the number had to be edited on
        every release, which is the burden the package description was
        freed from.  The tagline now says what the project *is* instead,
        and the feature line lists capabilities with no number at all.

        So a number is no longer required; a wrong one is still a
        failure, because a banner is the least likely place anyone would
        think to check.  Both copies are read -- the `<desc>` a screen
        reader announces and the visible strip -- because each is
        hand-written and they drift apart.
        """
        import re

        from contract_spec import CANONICAL_COMMANDS

        expected = len(CANONICAL_COMMANDS)
        for element in self._root().iter():
            if not (element.tag.endswith("desc")
                    or element.get("class") == "surface"):
                continue
            surface = "".join(element.itertext())
            with self.subTest(surface=surface[:40]):
                for number in re.findall(
                    r"(\d+)\s+(?:kl-\*\s+)?commands", surface,
                ):
                    self.assertEqual(
                        int(number), expected,
                        f"the banner says {number} commands; the registry "
                        f"has {expected}",
                    )

    def test_both_copies_name_the_same_capabilities(self) -> None:
        """The `<desc>` and the visible strip must describe one tool.

        They are separate prose, so they drift, and the rendered image
        still looks right while they do.  That is how the banner ended up
        promising "SLUB" without the freelist and omitting `struct page`
        entirely, both of which the canonical description names and the
        commands actually implement.

        The feature list is the one from `pyproject.toml`, so this also
        fails if the project decides to stop advertising something.
        """
        root = self._root()
        copies = {
            element.get("id") or "surface": "".join(element.itertext()).lower()
            for element in root.iter()
            if element.tag.endswith("desc") or element.get("class") == "surface"
        }
        self.assertEqual(len(copies), 2, "expected a desc and a surface line")
        for feature in ("page tables", "slub", "freelist", "struct page",
                        "symbols", "kaslr"):
            for name, text in copies.items():
                with self.subTest(feature=feature, copy=name):
                    self.assertIn(feature, text)

    def test_has_no_external_assets(self) -> None:
        """One file, no network, no rasters.

        A hosted font or a linked bitmap would make the banner depend on
        something the repository does not control, and GitHub's image
        proxy does not always fetch them.
        """
        raw = self.PATH.read_text(encoding="utf-8")
        for banned in ("<image", "xlink:href", ".png", ".jpg", ".woff"):
            self.assertNotIn(banned, raw)

    def test_the_text_is_large_enough_to_clear_contrast(self) -> None:
        """The fill colours cannot reach 4.5:1, so the sizes have to.

        A banner is one file, so it cannot change colour between GitHub's
        light and dark themes.  Sweeping every grey shows the best a
        single fill can do across #ffffff and #0d1117 is 4.35:1, which is
        below the 4.5 AA requires for small text.  That ceiling is a
        property of the two backgrounds, not of this banner.

        WCAG therefore has to be satisfied through size: bold text counts
        as "large" from 18.66px, and large text needs only 3.0.  Both
        small lines are held above that threshold here, so a later edit
        that shrinks one of them fails instead of quietly regressing.
        """
        import re

        css = self.PATH.read_text(encoding="utf-8")
        sizes = {
            name: float(re.search(
                rf"\.{name} \{{[^}}]*font-size:\s*([\d.]+)px", css, re.S,
            ).group(1))
            for name in ("wordmark", "tagline", "surface")
        }
        # 18.66 is the WCAG threshold for bold text; round up to 19px.
        for name in ("tagline", "surface"):
            with self.subTest(element=name):
                self.assertGreaterEqual(
                    sizes[name], 19.0,
                    f".{name} is {sizes[name]}px; below 18.66px bold it "
                    f"would need 4.5:1, which no single fill can reach",
                )
        # And the weights those thresholds assume.
        for name in ("tagline", "surface"):
            with self.subTest(element=name):
                weight = re.search(
                    rf"\.{name} \{{[^}}]*font-weight:\s*(\d+)", css, re.S,
                ).group(1)
                self.assertGreaterEqual(int(weight), 600)

    def test_every_fill_is_readable_on_both_github_themes(self) -> None:
        """The colours are measured, not eyeballed.

        The wordmark used to end at #7209b7, which is 2.20:1 against
        GitHub's dark background: the "Lens" half was almost invisible
        there, and on the light theme it looked fine, so nothing caught
        it.  Both backgrounds are checked here, because a banner is one
        file and cannot pick a colour per theme.

        The thresholds are WCAG AA.  3.0 applies to the wordmark (58px is
        "large") and to the two small lines, which are set at 19px bold
        or larger for exactly this reason; the ceiling for any single
        fill across both backgrounds is 4.35:1, so 4.5 is not reachable
        and is not asserted.
        """
        import re

        raw = self.PATH.read_text(encoding="utf-8")

        def channel(value: float) -> float:
            value /= 255
            return value / 12.92 if value <= 0.04045 else (
                ((value + 0.055) / 1.055) ** 2.4
            )

        def luminance(colour: str) -> float:
            colour = colour.lstrip("#")
            red, green, blue = (
                channel(int(colour[index:index + 2], 16))
                for index in (0, 2, 4)
            )
            return 0.2126 * red + 0.7152 * green + 0.0722 * blue

        def ratio(one: str, other: str) -> float:
            first, second = luminance(one), luminance(other)
            high, low = max(first, second), min(first, second)
            return (high + 0.05) / (low + 0.05)

        backgrounds = {"light": "#ffffff", "dark": "#0d1117"}
        # Two syntaxes, because a gradient stop is an attribute
        # (`stop-color="#..."`) and a CSS rule is a declaration
        # (`fill: #...`).  A regex that only matched the colon form
        # silently skipped the gradient, which is the half that was
        # wrong, so the guard passed on the broken file.
        fills = re.findall(r"(?:stop-color|fill)\s*[:=]\s*[\"']?(#[0-9a-fA-F]{6})", raw)
        self.assertTrue(fills, "no colours found in the banner")
        # The gradient end that made "Lens" vanish has to be one of them,
        # or this test is not looking where the defect was.
        self.assertGreaterEqual(len(set(fills)), 4, f"only found {sorted(set(fills))}")
        for fill in sorted(set(fills)):
            for theme, background in backgrounds.items():
                with self.subTest(colour=fill, theme=theme):
                    self.assertGreaterEqual(
                        ratio(fill, background), 3.0,
                        f"{fill} is {ratio(fill, background):.2f}:1 on "
                        f"{background}; the dark end must stay readable",
                    )

    def test_no_comment_contains_a_double_hyphen(self) -> None:
        """``--`` is illegal inside an XML comment, and fails silently.

        This is the second time it has happened: the file stops parsing
        at that point, GitHub renders nothing, and the only symptom is a
        blank space at the top of both READMEs.  ``test_parses_as_xml``
        catches it, but the message ("invalid token, line 11") does not
        say what to fix, so this names the real problem.

        Typing a dash as ``--`` is an English habit, and the comments in
        this file are prose.
        """
        import re

        raw = self.PATH.read_text(encoding="utf-8")
        for body in re.findall(r"<!--(.*?)-->", raw, re.S):
            with self.subTest(comment=body.strip()[:50]):
                self.assertNotIn("--", body)


class DocumentationTrackingTests(unittest.TestCase):
    """The repository tree in the docs must describe the real tree.

    ``docs/en/architecture.md`` carries a hand-drawn tree, and it drifted
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
        text = (ROOT / "docs" / "en" / "architecture.md").read_text(
            encoding="utf-8",
        )
        start = text.index("```\n")
        end = text.index("```", start + 4)
        return text[start:end]

    def test_every_name_in_the_tree_exists(self) -> None:
        block = self._tree_block()
        missing = [
            name for name in doc_filenames(block)
            if name not in self.ILLUSTRATIVE and not path_exists(name)
        ]
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

    def test_every_top_level_directory_appears_in_the_tree(self) -> None:
        """A directory nobody documented is a directory nobody finds.

        The tree guard above is one-directional: everything it names
        exists.  That direction passes just as well when a whole new
        directory is added and never mentioned, which is how ``overrides/``
        and ``hooks/`` would have arrived -- infrastructure the site
        cannot build without, and invisible to a reader of the layout.
        """
        block = self._tree_block()
        absent = sorted(
            path.name for path in ROOT.iterdir()
            if path.is_dir()
            and path.name not in VENDORED
            and not path.name.startswith(".")
            and f"{path.name}/" not in block
        )
        self.assertEqual(absent, [])

    def test_every_bin_script_appears_in_the_tree(self) -> None:
        """``bin/`` is small enough that every entry has to be named.

        The top-level test only asks for the directory, so a second
        launcher can be added and stay undocumented -- which is what
        happened with ``bin/kl``.  Two spellings of one command is exactly
        the kind of thing a reader has to be told, because the whole point
        is that they are interchangeable.

        The match is on ``bin/<name>``, not the bare name: ``kl`` is a
        substring of ``kl-help`` and of half the tree, so a plain
        containment test passes whether the launcher is documented or not.
        """
        import re

        block = self._tree_block()
        absent = sorted(
            path.name for path in (ROOT / "bin").iterdir()
            if path.is_file()
            and not re.search(rf"bin/{re.escape(path.name)}\b", block)
        )
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
            for token in doc_filenames(text):
                if not token.startswith(roots):
                    continue
                if not path_exists(token):
                    stale.append(f"{doc.relative_to(ROOT)}: {token}")
        self.assertEqual(sorted(set(stale)), [])


class ReadmeStructureTests(unittest.TestCase):
    """The front page must stay a front page.

    The README was 927 lines because reference material accumulated in it:
    317 lines of API documentation and 110 of contributor notes, both of
    which belong in their own files.  Moving them once is easy; keeping
    them out is the part that needs a test, because appending "just one
    more table" is always locally reasonable.

    These pin the three properties that made the rewrite worth doing.
    """

    #: A ceiling, not a target.  The file is ~270 lines; this leaves room
    #: for a new section without inviting one to grow indefinitely.
    MAX_LINES = 340

    def _readme(self, name: str = "README.md") -> str:
        return (ROOT / name).read_text(encoding="utf-8")

    def test_stays_short(self) -> None:
        for name in ("README.md", "README.zh-CN.md"):
            with self.subTest(readme=name):
                lines = len(self._readme(name).splitlines())
                self.assertLessEqual(
                    lines, self.MAX_LINES,
                    f"{name} is {lines} lines; reference material belongs "
                    "in docs/en/api.md or CONTRIBUTING.md",
                )

    def test_shows_real_command_output(self) -> None:
        """A front page with no output has to be taken on faith.

        The old README contained 34 fenced blocks -- 19 python, 7 gdb, 8
        console -- and not one line of captured command output.  The
        strongest thing the project owns was invisible.
        """
        for name in ("README.md", "README.zh-CN.md"):
            with self.subTest(readme=name):
                text = self._readme(name)
                self.assertIn("Paging: 4-level", text)
                self.assertIn("huge leaf", text)
                self.assertIn("freeptr:", text)
                self.assertIn("decoded=", text)

    def test_the_reference_and_contributor_docs_exist(self) -> None:
        """The material moved out of the README must still be reachable.

        A split that leaves the front page clean and the content
        unreachable is worse than the long README was.
        """
        for name in (
            "docs/en/api.md", "docs/zh-CN/api.md",
            "CONTRIBUTING.md", "CONTRIBUTING.zh-CN.md",
        ):
            with self.subTest(path=name):
                self.assertTrue((ROOT / name).is_file(), name)
        for target in ("docs/en/api.md", "CONTRIBUTING.md"):
            with self.subTest(linked=target):
                self.assertIn(f"({target})", self._readme("README.md"))


class PackagedDistributionTests(unittest.TestCase):
    """The startup file ships in the package, and the docs say how.

    The project used to be checkout-only, and a test here forbade install
    commands because the wheel could not work: ``gdbinit.py`` lived beside
    ``src/``, not inside it, so ``pip install`` produced a package that
    installed cleanly and then could not be loaded.  The file is package
    data now and a console script prints its path, so the tripwire is
    inverted: the wheel must contain the startup file and the entry
    point, and the prose must describe the install that exists.

    ``pip install kernlens`` stays forbidden until the first release is
    actually on PyPI; adding the command before that would point readers
    at a 404.  That is a release step, not a packaging step.
    """

    #: Write-ups that would 404 until the first PyPI release is published.
    FORBIDDEN = ("pip install kernlens", "uvx kernlens", "pipx install",
                 "uv tool install kernlens")

    def _docs(self) -> dict[str, str]:
        return {
            name: (ROOT / name).read_text(encoding="utf-8")
            for name in (
                "README.md", "README.zh-CN.md",
                "CONTRIBUTING.md", "CONTRIBUTING.zh-CN.md",
            )
        }

    def test_the_startup_file_lives_in_the_package(self) -> None:
        self.assertTrue((SRC / "gdbinit.py").is_file())
        self.assertIn(
            "def bootstrap", (SRC / "gdbinit.py").read_text(
                encoding="utf-8",
            ),
        )

    def test_pyproject_ships_the_startup_file_and_the_script(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(
            'kernlens = ["py.typed", "gdbinit.py"]', pyproject,
        )
        self.assertIn("[project.scripts]", pyproject)
        self.assertIn('kernlens = "kernlens.cli:main"', pyproject)

    def test_the_console_script_prints_a_loadable_startup_file(self) -> None:
        from kernlens import install

        path = install.startup_path()
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, "gdbinit.py")
        self.assertIn("def bootstrap", path.read_text(encoding="utf-8"))

    def test_the_console_script_module_is_importable(self) -> None:
        from kernlens import cli

        self.assertTrue(callable(cli.main))

    def test_the_docs_describe_the_install_that_exists(self) -> None:
        for name, text in self._docs().items():
            with self.subTest(document=name):
                self.assertIn("kernlens doctor", text)
        for name in ("README.md", "README.zh-CN.md"):
            with self.subTest(readme=name):
                self.assertIn("install.sh", self._docs()[name])

    def test_no_document_offers_a_command_that_would_404(self) -> None:
        for name, text in self._docs().items():
            for phrase in self.FORBIDDEN:
                with self.subTest(document=name, phrase=phrase):
                    self.assertNotIn(phrase, text)

    def test_the_readme_says_where_installation_comes_from(self) -> None:
        # Silence is not enough: a reader who has been told nothing will
        # try the package manager, because that is what always works.
        for name in ("README.md", "README.zh-CN.md"):
            with self.subTest(readme=name):
                text = self._docs()[name]
                self.assertIn("git clone", text)

    def test_the_policy_is_stated_with_its_reason(self) -> None:
        # The reason is the part that survives a rewrite.  The startup
        # file is in the wheel now, but it is still sourced, not imported,
        # and that distinction is what the contributor notes must keep.
        for name in ("CONTRIBUTING.md", "CONTRIBUTING.zh-CN.md"):
            with self.subTest(document=name):
                text = self._docs()[name]
                self.assertIn("gdbinit.py", text)


class WriteAccessClaimTests(unittest.TestCase):
    """A "read-only" claim is a promise; the code has one exception.

    SECURITY.md said KernLens "is read-only by design".  It is not:
    ``kl-msr --write`` runs ``gdb.execute("set $reg = ...")``, which
    changes the target.  The claim was load-bearing -- it was the sentence
    that defined what counts as unsafe behaviour against the target -- so
    a reader deciding whether to trust the tool with a live kernel was
    reading something false.

    These tests do not forbid writing.  They require that the presence of
    a write path and the documentation describing it cannot disagree,
    which is the failure that actually happened.
    """

    ROOT = pathlib.Path(__file__).resolve().parents[2]

    #: Every command module, so a new write path is found wherever it lives.
    def _writers(self) -> list[str]:
        import ast

        found: list[str] = []
        for path in (self.ROOT / "src" / "kernlens").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = getattr(func, "attr", None)
                if name != "execute" or not node.args:
                    continue
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(
                    first.value, str,
                ):
                    command = first.value.strip()
                elif isinstance(first, ast.JoinedStr):
                    head = first.values[0] if first.values else None
                    command = (
                        head.value.strip()
                        if isinstance(head, ast.Constant) else ""
                    )
                else:
                    continue
                # Only a `set` mutates the target; `info`, `p`, etc. read.
                if command.split()[:1] == ["set"]:
                    found.append(
                        f"{path.relative_to(self.ROOT)}: {command[:40]}"
                    )
        return sorted(set(found))

    def test_the_write_path_still_exists(self) -> None:
        # If this fails, the exception is gone and the documents below
        # should stop mentioning it -- change both together.
        self.assertTrue(
            self._writers(),
            "no `gdb.execute('set ...')` found; if writing was removed, "
            "drop the kl-msr --write exception from SECURITY.md and both "
            "READMEs",
        )

    def test_security_policy_names_the_exception(self) -> None:
        text = (self.ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertNotIn("KernLens is read-only", text)
        self.assertIn("kl-msr --write", text)

    def test_both_readmes_name_the_exception(self) -> None:
        for name in ("README.md", "README.zh-CN.md"):
            with self.subTest(readme=name):
                text = (self.ROOT / name).read_text(encoding="utf-8")
                self.assertIn("kl-msr --write", text)


class StdlibRunnerTests(unittest.TestCase):
    """``unittest`` outside pytest needs the paths pytest injects.

    The suite advertises itself as unittest-compatible and both
    CONTRIBUTING files show how to run it that way, but ``pythonpath`` in
    ``pyproject.toml`` is a pytest setting: run under ``unittest`` and the
    helper modules ``tests/conftest.py`` puts on ``sys.path`` are simply
    absent.  That was not theoretical -- the documented command reported
    10 unit modules and 4 integration tests as import errors, and every
    one of them was a missing ``PYTHONPATH`` entry rather than a defect.

    So the fix has three parts that must agree: ``conftest.py`` decides
    the paths, the documented ``PYTHONPATH`` passes them on, and CI runs
    the documented command.  A test that only read one of them would let
    the other two drift -- which is exactly how the broken pair survived.
    """

    ROOT = pathlib.Path(__file__).resolve().parents[2]
    CONFTEST = ROOT / "tests" / "conftest.py"
    #: Every file that tells a reader (or a runner) how to invoke it.
    DOCS = ("CONTRIBUTING.md", "CONTRIBUTING.zh-CN.md")
    CI = ROOT / ".github" / "workflows" / "ci.yml"

    def _injected(self) -> list[str]:
        """The directory names ``conftest.py`` puts on ``sys.path``.

        Read from :data:`conftest.EXTRA_PATHS` rather than by parsing the
        file.  A first version did parse it and returned the wrong answer:
        the loop variable is ``_TESTS``, so the AST gave the *identifier*
        where the directory is ``tests``, and the guard failed against the
        documents it was supposed to agree with.  The list is public for
        exactly this reason -- one definition, read by everyone who needs
        to spell it.
        """
        import conftest

        return [path.name for path in conftest.EXTRA_PATHS]

    def test_the_paths_are_what_the_documents_say(self) -> None:
        expected = ":".join(self._injected())
        for name in self.DOCS:
            with self.subTest(document=name):
                text = (self.ROOT / name).read_text(encoding="utf-8")
                self.assertIn(f"PYTHONPATH={expected}", text)

    def test_ci_runs_the_documented_command(self) -> None:
        expected = ":".join(self._injected())
        text = self.CI.read_text(encoding="utf-8")
        self.assertIn(f"PYTHONPATH={expected}", text)
        # Both suites, because ``discover`` restarting per directory is
        # what caught the split between unit and integration helpers.
        for suite in ("tests/unit", "tests/integration"):
            with self.subTest(suite=suite):
                self.assertIn(
                    f"python -m unittest discover -s {suite}", text,
                )

    def test_the_guard_would_notice_a_missing_path(self) -> None:
        # A guard whose expected value is derived from the thing it guards
        # cannot fail; prove the comparison is real by removing one entry.
        injected = self._injected()
        self.assertGreaterEqual(len(injected), 2)
        self.assertNotEqual(
            ":".join(injected[1:]), ":".join(injected),
        )

    def test_the_directories_exist(self) -> None:
        # ``PYTHONPATH`` silently ignores a path that does not exist, so a
        # renamed directory would turn the documented command into the
        # import-error run this guard exists to prevent.
        import conftest

        for path in conftest.EXTRA_PATHS:
            with self.subTest(path=path.name):
                self.assertTrue(path.is_dir(), f"{path} is not a directory")


class CiSkipListTests(unittest.TestCase):
    """``paths-ignore`` may only name files no test opens.

    The list exists to avoid a four-version matrix for a licence typo, and
    it went wrong in the obvious way: it held ``docs/**``, ``images/**``,
    ``examples/api/gdbinit.example`` and ``CHANGELOG.md``, and every one of
    those is read by the suite.  A docs-only push was therefore green
    *without* running the test that would have caught it, and the stale
    file it produced was found by a different workflow one run later -- by
    which time the failure pointed at a commit that was fine.

    The justification is a map, not a static analysis.  Deciding "does a
    test read this?" from text alone cannot work: ``release.check()``
    reads ``CHANGELOG.md`` through the module's own ``ROOT``, so no test
    file mentions the filename, and a search would call it unasserted.
    What a map can do is force the judgement to be written down, so that
    adding an entry without thinking about the suite is a failing test.
    """

    WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

    #: Every file CI is allowed to skip, and why that is safe.  A new
    #: entry has to be justified here, which is the point.
    JUSTIFIED = {
        "CREDITS.md": (
            "attribution prose; no test and no tool opens it"
        ),
        "LICENSE": (
            "the licence text; `pyproject.toml` names it as a licence "
            "file, so a build notices a missing one, and nothing reads "
            "its contents"
        ),
    }

    def _ignored(self) -> list[str]:
        """The literal entries under ``paths-ignore``, in file order."""
        lines = self.WORKFLOW.read_text(encoding="utf-8").splitlines()
        start = next(
            index for index, line in enumerate(lines)
            if line.strip() == "paths-ignore:"
        )
        entries: list[str] = []
        for line in lines[start + 1:]:
            stripped = line.strip()
            if not stripped.startswith("- "):
                break
            entries.append(stripped[2:].strip().strip('"').strip("'"))
        return entries

    def test_every_entry_is_justified(self) -> None:
        self.assertEqual(sorted(self._ignored()), sorted(self.JUSTIFIED))

    def test_the_release_inputs_are_never_skipped(self) -> None:
        # `tools/release.py check` reads three hand-written files, and one
        # of them is the changelog.  A skip that covered it would let a
        # malformed release section land unread -- the exact failure this
        # class exists for.
        import release

        guarded = {
            path.name for path in (
                release.CHANGELOG, release.CITATION,
            )
        }
        for entry in self._ignored():
            with self.subTest(entry=entry):
                self.assertNotIn(entry.rstrip("/*"), guarded)

    def test_no_directory_is_skipped(self) -> None:
        # Every directory in this repository holds at least one file a
        # test reads, and a glob hides which ones.
        for entry in self._ignored():
            with self.subTest(entry=entry):
                self.assertNotIn("*", entry)
                self.assertFalse((ROOT / entry).is_dir(), entry)

    def test_pull_requests_are_not_filtered(self) -> None:
        # Filtering ``pull_request`` would leave a required check pending
        # forever on a docs-only PR, because no run would be created.
        text = self.WORKFLOW.read_text(encoding="utf-8")
        pull = text.index("pull_request:")
        self.assertNotIn(
            "paths-ignore",
            text[pull:text.index("workflow_dispatch:")],
        )


if __name__ == "__main__":
    unittest.main()
