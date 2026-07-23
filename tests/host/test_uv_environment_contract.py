import tomllib
import unittest

from support import REPO_ROOT, read


class UvEnvironmentContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pyproject = tomllib.loads(read("pyproject.toml"))
        cls.lock = tomllib.loads(read("uv.lock"))

    def test_python_version_contract(self) -> None:
        self.assertEqual(read(".python-version"), "3.12\n")
        self.assertEqual(
            self.pyproject["project"]["requires-python"],
            ">=3.12,<3.13",
        )

    def test_build_group_pins_only_kas(self) -> None:
        self.assertEqual(self.pyproject["project"]["dependencies"], [])
        self.assertEqual(
            self.pyproject["dependency-groups"]["build"],
            ["kas==5.4"],
        )

    def test_uv_policy_is_exact(self) -> None:
        policy = self.pyproject["tool"]["uv"]
        self.assertFalse(policy["package"])
        self.assertEqual(policy["default-groups"], ["build"])
        self.assertEqual(policy["required-version"], "==0.11.31")
        self.assertEqual(policy["python-preference"], "only-system")

    def test_legacy_requirements_file_is_absent(self) -> None:
        self.assertFalse((REPO_ROOT / "requirements-build.txt").exists())
        self.assertIn(".venv/", set(read(".gitignore").splitlines()))

    def test_lock_contains_kas_and_its_resolved_dependencies(self) -> None:
        packages = {
            package["name"]: package
            for package in self.lock["package"]
        }
        self.assertEqual(packages["kas"]["version"], "5.4")
        dependencies = {
            dependency["name"]
            for dependency in packages["kas"].get("dependencies", [])
        }
        self.assertTrue(dependencies)
        self.assertTrue(dependencies.issubset(packages))


if __name__ == "__main__":
    unittest.main()
