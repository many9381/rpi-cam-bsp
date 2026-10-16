import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import REPO_ROOT


class CodexPackagingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "codex"
        self.unpack = self.root / "unpack"
        self.destination = self.root / "image"
        (self.source / "bin").mkdir(parents=True)
        (self.unpack / "licenses").mkdir(parents=True)
        for name in ("codex", "codex-code-mode-host"):
            (self.source / "bin" / name).write_bytes(b"executable fixture: " + name.encode())
        for name in ("LICENSE", "NOTICE", "wezterm-MIT.txt", "bubblewrap-COPYING"):
            (self.unpack / "licenses" / f"codex-1.2.3-{name}").write_text(f"notice: {name}\n")
        (self.unpack / "ratatui-MIT.txt").write_text("Ratatui MIT notice fixture\n")
        (self.unpack / "ripgrep-MIT.txt").write_text("ripgrep MIT notice fixture\n")
        (self.source / "codex-package.json").write_text(json.dumps({
            "layoutVersion": 1, "version": "1.2.3",
            "target": "aarch64-unknown-linux-musl", "variant": "codex",
            "entrypoint": "bin/codex", "resourcesDir": "codex-resources",
            "pathDir": "codex-path",
        }))
        # The daemon requires real files within the package, not links to /usr/bin.
        for path in ("codex-path/rg", "codex-resources/bwrap"):
            file = self.source / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b"required tool: " + path.encode())
        # Optional resources and credentials must not be copied indiscriminately.
        (self.source / "auth.json").write_text("must not ship")
        for path in ("codex-resources/zsh/bin/zsh", "codex-resources/voice/bin/codex-voice-host"):
            file = self.source / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("use the Yocto package instead")

    def install(self) -> subprocess.CompletedProcess:
        if self.destination.exists():
            shutil.rmtree(self.destination)
        recipe = REPO_ROOT / "meta-rpi5-cam/recipes-devtools/codex-cli/codex-cli.bb"
        self.assertTrue(recipe.is_file(), "Codex image recipe is missing")
        match = re.search(r"^do_install\(\) \{\n(.*?)^\}", recipe.read_text(), re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        for name, value in {
            "S": self.source,
            "UNPACKDIR": self.unpack,
            "D": self.destination,
            "bindir": "/usr/bin",
            "libdir": "/usr/lib",
            "datadir": "/usr/share",
            "PN": "codex-cli",
            "PV": "1.2.3",
        }.items():
            body = body.replace("${" + name + "}", str(value))
        return subprocess.run(["bash", "-eu", "-c", body], capture_output=True, text=True)

    def test_installs_cli_helper_and_notices_without_unrelated_archive_files(self) -> None:
        """Catch missing helpers, unsafe permissions and copying the whole archive."""
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        package = self.destination / "usr/lib/codex"
        self.assertTrue((package / "codex-package.json").is_file(), "daemon cannot discover its package")
        self.assertEqual(
            {str(p.relative_to(self.destination)) for p in self.destination.rglob("*") if p.is_file() or p.is_symlink()},
            {
                "usr/bin/codex", "usr/bin/codex-code-mode-host",
                "usr/lib/codex/bin/codex", "usr/lib/codex/bin/codex-code-mode-host",
                "usr/lib/codex/codex-package.json", "usr/lib/codex/codex-path/rg",
                "usr/lib/codex/codex-resources/bwrap",
                "usr/share/licenses/codex-cli/LICENSE", "usr/share/licenses/codex-cli/NOTICE",
                "usr/share/licenses/codex-cli/ratatui-MIT.txt", "usr/share/licenses/codex-cli/wezterm-MIT.txt",
                "usr/share/licenses/codex-cli/bubblewrap-COPYING", "usr/share/licenses/codex-cli/ripgrep-MIT.txt",
            },
        )
        metadata = json.loads((package / "codex-package.json").read_text())
        self.assertEqual(metadata["version"], "1.2.3")
        self.assertTrue((package / metadata["entrypoint"]).is_file())
        self.assertTrue((package / metadata["pathDir"] / "rg").is_file())
        self.assertTrue((package / metadata["resourcesDir"] / "bwrap").is_file())
        for path in ("bin/codex", "bin/codex-code-mode-host", "codex-path/rg", "codex-resources/bwrap"):
            installed = package / path
            self.assertFalse(installed.is_symlink(), "daemon rejects links outside its package")
            self.assertEqual(installed.read_bytes(), (self.source / path).read_bytes())
            self.assertEqual(stat.S_IMODE(installed.stat().st_mode), 0o755)
        for name in ("codex", "codex-code-mode-host"):
            link = self.destination / "usr/bin" / name
            target = Path(os.readlink(link))
            resolved = self.destination / str(target).lstrip("/") if target.is_absolute() else link.parent / target
            self.assertEqual(resolved.resolve(), package / "bin" / name)
        self.assertEqual(stat.S_IMODE((package / "codex-package.json").stat().st_mode), 0o644)
        for notice in (self.destination / "usr/share/licenses/codex-cli").iterdir():
            self.assertEqual(stat.S_IMODE(notice.stat().st_mode), 0o644)

    def test_missing_code_mode_helper_fails_installation(self) -> None:
        """Catch silently packaging a CLI whose execution helper cannot start."""
        (self.source / "bin/codex-code-mode-host").unlink()
        self.assertNotEqual(self.install().returncode, 0)

    def test_missing_daemon_package_component_fails_installation(self) -> None:
        """Catch shipping an image that versions correctly but cannot start a daemon."""
        for path in ("codex-package.json", "codex-path/rg", "codex-resources/bwrap"):
            with self.subTest(path=path):
                source = self.source / path
                contents = source.read_bytes()
                source.unlink()
                result = self.install()
                source.write_bytes(contents)
                self.assertNotEqual(result.returncode, 0)

    def test_missing_upstream_notice_fails_installation(self) -> None:
        """Catch producing a distributable package without upstream notices."""
        (self.unpack / "licenses/codex-1.2.3-NOTICE").unlink()
        self.assertNotEqual(self.install().returncode, 0)


if __name__ == "__main__":
    unittest.main()
