"""The promise behind ``py.typed``: annotations have to be *resolvable*.

``py.typed`` tells a type checker to read the inline annotations, and a
static checker is happy to read them even when a human -- or a library --
could not.  Two things break that promise at runtime instead of at
type-check time:

* a class-level annotation that names one of the class's own members
  (``__slots__: tuple[str, ...]`` next to a method called ``tuple``) --
  ``typing.get_type_hints`` resolves names in the class namespace, hits
  the method, and raises ``TypeError: 'function' object is not
  subscriptable``; and
* an annotation that only exists under ``TYPE_CHECKING``, which resolves
  for the checker and not for ``dataclasses`` / ``pydantic`` / ``sphinx``.

The first case is checked statically for every module (including the ones
that need GDB, since those are most of the package); the second
dynamically for the modules that import without a debugger.
"""

from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys
import typing
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "kernlens"


def _member_names(node: ast.ClassDef) -> set[str]:
    """Names bound directly in *node*'s class body."""
    names: set[str] = set()
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(item.name)
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            names.add(item.target.id)
        elif isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _class_annotations(node: ast.ClassDef) -> typing.Iterator[tuple[int, ast.expr]]:
    """Yield ``(line, annotation)`` for class-level and method annotations."""
    for item in node.body:
        if isinstance(item, ast.AnnAssign):
            yield item.lineno, item.annotation
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = (
                item.args.args + item.args.kwonlyargs + item.args.posonlyargs
            )
            arguments += [
                a for a in (item.args.vararg, item.args.kwarg) if a is not None
            ]
            for argument in arguments:
                if argument.annotation is not None:
                    yield argument.lineno, argument.annotation
            if item.returns is not None:
                yield item.lineno, item.returns


def _shadowed_annotations() -> list[str]:
    """Return ``path:line Class.member`` for annotations shadowed by a member."""
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            members = _member_names(node)
            if not members:
                continue
            for line, annotation in _class_annotations(node):
                for child in ast.walk(annotation):
                    if isinstance(child, ast.Name) and child.id in members:
                        found.append(
                            f"{path.relative_to(ROOT)}:{line} "
                            f"{node.name}.{child.id}"
                        )
    return found


_HOST_PROBE = r"""
import importlib
import inspect
import json
import pkgutil
import typing

import kernlens

checked = 0
failures = []
for info in pkgutil.walk_packages(kernlens.__path__, "kernlens."):
    try:
        module = importlib.import_module(info.name)
    except ImportError:
        # ``kernlens.commands`` / most of ``kernlens.gdb`` import ``gdb``,
        # which only exists inside a debugger.
        continue
    for name, obj in vars(module).items():
        if name.startswith("_"):
            continue
        if getattr(obj, "__module__", None) != module.__name__:
            continue
        if not (inspect.isclass(obj) or inspect.isfunction(obj)):
            continue
        checked += 1
        try:
            typing.get_type_hints(obj)
        except Exception as exc:
            failures.append(
                f"{module.__name__}.{name}: {type(exc).__name__}: {exc}"
            )
print(json.dumps({"checked": checked, "failures": failures}))
"""


def _host_resolution_report() -> dict[str, typing.Any]:
    """Run the resolvability probe in a *fresh* interpreter.

    In-process importing makes the result depend on test order: the
    integration tests install a fake ``gdb`` into ``sys.modules``, and
    once they have, ``kernlens.commands`` imports but fails at
    class-definition time with ``AttributeError: module 'gdb' has no
    attribute 'Command'``.  A subprocess starts without the fake, so
    "does this module import without a debugger?" has one answer.
    """
    result = subprocess.run(
        [sys.executable, "-c", _HOST_PROBE],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"probe failed:\n{result.stderr[-2000:]}")
    return json.loads(result.stdout)


class AnnotationResolutionTests(unittest.TestCase):
    def test_no_class_annotation_is_shadowed_by_a_member(self) -> None:
        """``tuple[str, ...]`` must mean the builtin, not ``self.tuple``.

        This is the static half: it reads every module, including the
        GDB-only ones, and needs no imports.  ``Styler`` was the case that
        escaped -- pyright and mypy both accepted the annotation while
        ``get_type_hints(Styler)`` raised.
        """
        self.assertEqual(_shadowed_annotations(), [])

    def test_host_annotations_resolve(self) -> None:
        """``get_type_hints`` must work for every public host symbol."""
        report = _host_resolution_report()
        # A floor, so a broken walker that imports nothing cannot pass.
        self.assertGreater(report["checked"], 40)
        self.assertEqual(report["failures"], [])


if __name__ == "__main__":
    unittest.main()
