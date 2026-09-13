import re
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
        for name in ("LICENSE", "NOTICE", "wezterm-MIT.txt"):
            (self.unpack / "licenses" / f"codex-0.154.0-{name}").write_text(f"notice: {name}\n")
        (self.unpack / "ratatui-MIT.txt").write_text("Ratatui MIT notice fixture\n")
        # An indiscriminate archive copy would leak credentials or bundled tools.
        (self.source / "auth.json").write_text("must not ship")
        for path in ("codex-path/rg", "codex-resources/bwrap", "codex-resources/zsh/bin/zsh"):
            file = self.source / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("use the Yocto package instead")

    def install(self) -> subprocess.CompletedProcess:
        recipe = REPO_ROOT / "meta-rpi5-cam/recipes-devtools/codex-cli/codex-cli_0.154.0.bb"
        self.assertTrue(recipe.is_file(), "Codex image recipe is missing")
        match = re.search(r"^do_install\(\) \{\n(.*?)^\}", recipe.read_text(), re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        for name, value in {
            "S": self.source,
            "UNPACKDIR": self.unpack,
            "D": self.destination,
            "bindir": "/usr/bin",
            "datadir": "/usr/share",
            "PN": "codex-cli",
            "PV": "0.154.0",
        }.items():
            body = body.replace("${" + name + "}", str(value))
        return subprocess.run(["bash", "-eu", "-c", body], capture_output=True, text=True)

    def test_installs_cli_helper_and_notices_without_unrelated_archive_files(self) -> None:
        """Catch missing helpers, unsafe permissions and copying the whole archive."""
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            {str(p.relative_to(self.destination)) for p in self.destination.rglob("*") if p.is_file()},
            {
                "usr/bin/codex", "usr/bin/codex-code-mode-host",
                "usr/share/licenses/codex-cli/LICENSE", "usr/share/licenses/codex-cli/NOTICE",
                "usr/share/licenses/codex-cli/ratatui-MIT.txt", "usr/share/licenses/codex-cli/wezterm-MIT.txt",
            },
        )
        for name in ("codex", "codex-code-mode-host"):
            installed = self.destination / "usr/bin" / name
            self.assertEqual(installed.read_bytes(), (self.source / "bin" / name).read_bytes())
            self.assertEqual(stat.S_IMODE(installed.stat().st_mode), 0o755)
        for notice in (self.destination / "usr/share/licenses/codex-cli").iterdir():
            self.assertEqual(stat.S_IMODE(notice.stat().st_mode), 0o644)

    def test_missing_code_mode_helper_fails_installation(self) -> None:
        """Catch silently packaging a CLI whose execution helper cannot start."""
        (self.source / "bin/codex-code-mode-host").unlink()
        self.assertNotEqual(self.install().returncode, 0)

    def test_missing_upstream_notice_fails_installation(self) -> None:
        """Catch producing a distributable package without upstream notices."""
        (self.unpack / "licenses/codex-0.154.0-NOTICE").unlink()
        self.assertNotEqual(self.install().returncode, 0)


if __name__ == "__main__":
    unittest.main()
