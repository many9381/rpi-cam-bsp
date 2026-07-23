import unittest

from support import REPO_ROOT, read


class RepositoryContractTest(unittest.TestCase):
    def test_uv_project_files_replace_legacy_requirements(self) -> None:
        for relative in ("pyproject.toml", "uv.lock", ".python-version"):
            self.assertTrue((REPO_ROOT / relative).is_file(), relative)
        self.assertFalse((REPO_ROOT / "requirements-build.txt").exists())

    def test_generated_and_sensitive_paths_are_ignored(self) -> None:
        ignored = set(read(".gitignore").splitlines())
        required = {
            ".venv/",
            "build/",
            "downloads/",
            "sstate-cache/",
            "keys/*",
            "!keys/README.md",
            "artifacts/*",
            "!artifacts/README.md",
            "!artifacts/releases/",
            "artifacts/releases/*",
            "!artifacts/releases/*.json",
            ".state/",
        }
        self.assertTrue(required.issubset(ignored))

    def test_key_documentation_forbids_tracking_key_material(self) -> None:
        text = read("keys/README.md")
        self.assertIn("ssh-keygen -t ed25519 -f keys/rpi5_admin", text)
        self.assertIn("keys/rpi5_admin.pub", text)
        self.assertIn("Git에 추가하지 않는다", text)

    def test_oeqa_security_decision_is_explicit(self) -> None:
        text = read("tests/oeqa/README.md")
        self.assertIn("allow-empty-password", text)
        self.assertIn("scripts/test-qemu.sh", text)


if __name__ == "__main__":
    unittest.main()
