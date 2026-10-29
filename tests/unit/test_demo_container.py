"""The demo container has to stay reproducible and honest.

It is the one artifact in the repository that needs a network, a
compiler, and several minutes to produce, so nothing here builds it.  The
checks are the facts that would otherwise drift: the kernel version the
image compiles is the one the tutorial was captured from, the config
fragment still carries what the commands read, the entrypoint still waits
for userspace before attaching, and the published-image workflow still
targets the registry the docs name.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "demo"
DOCKERFILE = DEMO / "Dockerfile"
ENTRYPOINT = DEMO / "entrypoint.sh"
CONFIG = DEMO / "kernel" / "config.fragment"
IMAGE_WORKFLOW = ROOT / ".github" / "workflows" / "demo-image.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class FilesTests(unittest.TestCase):
    def test_every_demo_file_exists(self) -> None:
        for name in (
            "Dockerfile",
            "entrypoint.sh",
            "demo.gdb",
            "demo-commands.gdb",
            "README.md",
            "kernel/config.fragment",
            "kernel/init.c",
        ):
            with self.subTest(name=name):
                self.assertTrue((DEMO / name).is_file(), name)

    def test_the_build_context_is_ignored_where_it_matters(self) -> None:
        ignored = _text(ROOT / ".dockerignore")
        for entry in (".git", ".venv", "build", "site"):
            with self.subTest(entry=entry):
                self.assertRegex(ignored, rf"(?m)^{re.escape(entry)}/?$")


class DockerfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = _text(DOCKERFILE)

    def test_it_is_a_two_stage_build(self) -> None:
        self.assertIn("AS kernel", self.text)
        self.assertIn("AS runtime", self.text)
        self.assertIn("COPY --from=kernel", self.text)

    def test_the_base_image_can_be_overridden(self) -> None:
        # A restricted network has to be able to point at a mirror
        # without editing the file.
        self.assertIn("ARG BASE_IMAGE=ubuntu:24.04", self.text)

    def test_the_kernel_version_is_pinned(self) -> None:
        self.assertRegex(self.text, r"(?m)^ARG KERNEL_VERSION=\d+\.\d+\.\d+$")

    def test_the_kernel_version_is_the_capture_version(self) -> None:
        capture = json.loads(
            (ROOT / "tools" / "tutorial_capture.json").read_text(
                encoding="utf-8",
            )
        )
        self.assertIn(
            f"ARG KERNEL_VERSION={capture['context']['kernel']}", self.text,
        )

    def test_it_strips_dwarf_and_keeps_btf(self) -> None:
        # The image would be several hundred megabytes larger with DWARF,
        # and KernLens reads `.BTF` plus the symbol table.
        self.assertIn("objcopy --strip-debug", self.text)
        self.assertIn("CONFIG_DEBUG_INFO_BTF=y", _text(CONFIG))

    def test_it_installs_without_recommends(self) -> None:
        self.assertIn("--no-install-recommends", self.text)

    def test_it_carries_the_checkout_layout(self) -> None:
        self.assertIn("COPY gdbinit.py /opt/kernlens/gdbinit.py", self.text)
        self.assertIn("COPY src /opt/kernlens/src", self.text)

    def test_it_has_an_entrypoint(self) -> None:
        self.assertIn('ENTRYPOINT ["/opt/demo/entrypoint.sh"]', self.text)


class ConfigTests(unittest.TestCase):
    def test_the_fragment_keeps_what_the_commands_read(self) -> None:
        text = _text(CONFIG)
        for option in (
            "CONFIG_SERIAL_8250_CONSOLE=y",
            "CONFIG_BLK_DEV_INITRD=y",
            "CONFIG_RD_GZIP=y",
            "CONFIG_SLUB=y",
            "CONFIG_SLAB_FREELIST_RANDOM=y",
            "CONFIG_KALLSYMS_ALL=y",
            "CONFIG_RANDOMIZE_BASE=y",
            "CONFIG_IKCONFIG=y",
            "CONFIG_IKCONFIG_PROC=y",
            "CONFIG_BPF_SYSCALL=y",
            "CONFIG_DEBUG_INFO_BTF=y",
        ):
            with self.subTest(option=option):
                self.assertIn(option, text)

    def test_the_init_prints_the_marker_the_entrypoint_waits_for(self) -> None:
        marker = "kernlens-demo: init running"
        self.assertIn(marker, _text(DEMO / "kernel" / "init.c"))
        self.assertIn(marker, _text(ENTRYPOINT))


class GdbTests(unittest.TestCase):
    def test_the_setup_loads_the_image_and_the_startup_file(self) -> None:
        text = _text(DEMO / "demo.gdb")
        self.assertIn("file /opt/demo/vmlinux", text)
        self.assertIn("target remote :1234", text)
        self.assertIn("source /opt/kernlens/gdbinit.py", text)

    def test_the_tour_has_no_baked_in_address(self) -> None:
        # The kernel is built at a different time and KASLR moves it; an
        # address copied from the tutorial would be a bug report waiting
        # to happen.
        text = _text(DEMO / "demo-commands.gdb")
        self.assertNotRegex(text, r"0x[0-9a-fA-F]{8,}")
        self.assertIn("reader.kvar_addr", text)

    def test_the_tour_covers_more_than_one_subsystem(self) -> None:
        text = _text(DEMO / "demo-commands.gdb")
        for command in ("kl-status", "kl-kbase", "kl-kconfig", "kl-slab"):
            with self.subTest(command=command):
                self.assertIn(command, text)
        self.assertIn("kl-pagewalk", text)


class EntrypointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = _text(ENTRYPOINT)

    def test_it_boots_the_minimal_machine(self) -> None:
        self.assertIn("-M microvm", self.text)

    def test_it_opens_the_gdbstub(self) -> None:
        self.assertIn("-s >\"$CONSOLE\" 2>&1 &", self.text)

    def test_it_waits_for_userspace_before_attaching(self) -> None:
        # Attaching at reset reads uninitialised memory; the marker is
        # what says the kernel has finished booting.
        self.assertLess(
            self.text.index("kernlens-demo: init running"),
            self.text.index("gdb -q -batch"),
        )

    def test_it_cleans_up_qemu(self) -> None:
        self.assertIn("trap", self.text)
        self.assertIn('kill "$qemu"', self.text)
        # `exec gdb` would replace the shell and drop the trap, leaving
        # QEMU running when GDB exits.
        self.assertNotIn("exec gdb", self.text)

    def test_a_caller_command_replaces_the_tour(self) -> None:
        self.assertIn('-ex "$*"', self.text)
        self.assertIn("demo-commands.gdb", self.text)


class PublishedImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = _text(IMAGE_WORKFLOW)

    def test_it_runs_on_a_version_tag(self) -> None:
        self.assertIn('tags: ["v*"]', self.text)

    def test_it_can_push_to_the_registry(self) -> None:
        self.assertIn("packages: write", self.text)
        self.assertIn("ghcr.io", self.text)
        self.assertIn("docker/build-push-action", self.text)

    def test_it_builds_the_demo_dockerfile(self) -> None:
        self.assertIn("file: demo/Dockerfile", self.text)
        self.assertIn("context: .", self.text)


class DocumentationTests(unittest.TestCase):
    def test_the_page_exists_and_is_reachable(self) -> None:
        page = ROOT / "docs" / "demo-container.md"
        self.assertTrue(page.is_file())
        mkdocs = _text(ROOT / "mkdocs.yml")
        self.assertIn("demo-container.md", mkdocs)

    def test_the_readme_shows_the_local_build(self) -> None:
        # There is no published image until the first tagged release, so
        # the README must show the command that works from a checkout.
        readme = _text(ROOT / "README.md")
        self.assertIn("docker build -f demo/Dockerfile", readme)
        self.assertIn("docker run --rm -it kernlens-demo", readme)

    def test_the_chinese_readme_shows_it_too(self) -> None:
        readme = _text(ROOT / "README.zh-CN.md")
        self.assertIn("docker build -f demo/Dockerfile", readme)
        self.assertIn("docker run --rm -it kernlens-demo", readme)


if __name__ == "__main__":
    unittest.main()
