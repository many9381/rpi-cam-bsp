import unittest

from support import read


class RepositoryContractTest(unittest.TestCase):
    def test_build_dependency_is_pinned(self) -> None:
        self.assertEqual(read("requirements-build.txt"), "kas==5.4\n")

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
