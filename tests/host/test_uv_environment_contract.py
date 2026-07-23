import copy
import os
from pathlib import Path
import re
import sys
import tempfile
import tomllib
import unittest

from support import REPO_ROOT, read, run


SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def validate_lock(lock: dict) -> None:
    if lock.get("requires-python") != "==3.12.*":
        raise AssertionError("top-level requires-python must be ==3.12.*")

    package_list = lock.get("package", [])
    names = [package["name"] for package in package_list]
    if len(names) != len(set(names)):
        raise AssertionError("duplicate package names")
    packages = {package["name"]: package for package in package_list}

    expected_root = {
        "name": "yocto-rpi5-cam-firmware",
        "version": "0.0.0",
        "source": {"virtual": "."},
        "dev-dependencies": {"build": [{"name": "kas"}]},
        "metadata": {
            "requires-dev": {
                "build": [{"name": "kas", "specifier": "==5.4"}],
            },
        },
    }
    root = packages.get("yocto-rpi5-cam-firmware")
    if root != expected_root:
        raise AssertionError("virtual root metadata must be exact")

    kas = packages.get("kas")
    if not kas or kas.get("version") != "5.4":
        raise AssertionError("kas must be locked at 5.4")
    if kas.get("source") != {"registry": "https://pypi.org/simple"}:
        raise AssertionError("kas registry source must be exact")

    reachable: set[str] = set()
    pending = ["kas"]
    while pending:
        name = pending.pop()
        if name in reachable:
            continue
        package = packages.get(name)
        if package is None:
            raise AssertionError(f"missing dependency: {name}")
        reachable.add(name)
        pending.extend(
            dependency["name"]
            for dependency in package.get("dependencies", [])
        )

    locked_registry = {
        name
        for name, package in packages.items()
        if "registry" in package["source"]
    }
    reachable_registry = {
        name
        for name in reachable
        if "registry" in packages[name]["source"]
    }
    if reachable_registry != locked_registry:
        raise AssertionError("registry closure mismatch")

    for name in sorted(locked_registry):
        package = packages[name]
        sdist_hash = package.get("sdist", {}).get("hash", "")
        if SHA256.fullmatch(sdist_hash) is None:
            raise AssertionError(f"invalid sdist hash: {name}")
        wheels = package.get("wheels", [])
        if not wheels:
            raise AssertionError(f"missing wheels: {name}")
        for wheel in wheels:
            if SHA256.fullmatch(wheel.get("hash", "")) is None:
                raise AssertionError(f"invalid wheel hash: {name}")


def assert_checkout_local_environment(
    repo_root: Path,
    prefix: Path,
    environ: dict[str, str],
) -> Path:
    override = environ.get("UV_PROJECT_ENVIRONMENT", "")
    if override:
        raise AssertionError("UV_PROJECT_ENVIRONMENT must be unset or empty")

    physical_root = Path(os.path.realpath(repo_root))
    environment = repo_root / ".venv"
    expected = physical_root / ".venv"
    if environment.is_symlink():
        raise AssertionError(".venv must not be a symlink")
    if not environment.is_dir():
        raise AssertionError(".venv must be a directory")
    if Path(os.path.realpath(environment)) != expected:
        raise AssertionError(".venv must be physically checkout-local")
    if Path(prefix).resolve() != expected:
        raise AssertionError("sys.prefix must be the checkout-local .venv")
    return expected


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

    def test_lock_has_exact_root_and_python_metadata(self) -> None:
        validate_lock(self.lock)
        self.assertEqual(self.lock["requires-python"], "==3.12.*")
        package_list = self.lock["package"]
        names = [package["name"] for package in package_list]
        self.assertEqual(len(names), len(set(names)), "duplicate package names")
        packages = {package["name"]: package for package in package_list}
        root = packages["yocto-rpi5-cam-firmware"]
        self.assertEqual(root["version"], "0.0.0")
        self.assertEqual(root["source"], {"virtual": "."})
        self.assertEqual(
            root["dev-dependencies"],
            {"build": [{"name": "kas"}]},
        )
        self.assertEqual(
            root["metadata"],
            {
                "requires-dev": {
                    "build": [{"name": "kas", "specifier": "==5.4"}],
                },
            },
        )

    def test_lock_contains_complete_hashed_kas_registry_closure(self) -> None:
        validate_lock(self.lock)
        packages = {
            package["name"]: package
            for package in self.lock["package"]
        }
        kas = packages["kas"]
        self.assertEqual(kas["version"], "5.4")
        self.assertEqual(kas["source"], {"registry": "https://pypi.org/simple"})

        reachable: set[str] = set()
        pending = ["kas"]
        while pending:
            name = pending.pop()
            if name in reachable:
                continue
            self.assertIn(name, packages)
            reachable.add(name)
            for dependency in packages[name].get("dependencies", []):
                dependency_name = dependency["name"]
                self.assertIn(dependency_name, packages)
                pending.append(dependency_name)

        locked_registry = {
            name
            for name, package in packages.items()
            if "registry" in package["source"]
        }
        reachable_registry = {
            name
            for name in reachable
            if "registry" in packages[name]["source"]
        }
        self.assertEqual(reachable_registry, locked_registry)

        for name in sorted(locked_registry):
            package = packages[name]
            self.assertRegex(package["sdist"]["hash"], SHA256, name)
            self.assertTrue(package["wheels"], name)
            for wheel in package["wheels"]:
                self.assertRegex(wheel["hash"], SHA256, name)

    def test_running_environment_is_physical_checkout_local_venv(self) -> None:
        expected = assert_checkout_local_environment(
            REPO_ROOT,
            Path(sys.prefix),
            dict(os.environ),
        )
        self.assertEqual(expected, Path(os.path.realpath(REPO_ROOT)) / ".venv")
        self.assertEqual(sys.version_info[:2], (3, 12))
        result = run("uv", "--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"^uv 0\.11\.31(?:\s|$)")

    def test_environment_contract_rejects_external_override(self) -> None:
        environ = dict(os.environ)
        environ["UV_PROJECT_ENVIRONMENT"] = "/tmp/external-uv-environment"
        with self.assertRaisesRegex(AssertionError, "UV_PROJECT_ENVIRONMENT"):
            assert_checkout_local_environment(
                REPO_ROOT,
                Path(sys.prefix),
                environ,
            )

    def test_environment_contract_rejects_symlinked_venv(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="uv-environment-contract-",
        ) as temporary:
            temporary_root = Path(temporary)
            checkout = temporary_root / "checkout"
            external = temporary_root / "external"
            checkout.mkdir()
            external.mkdir()
            (checkout / ".venv").symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(AssertionError, "symlink"):
                assert_checkout_local_environment(
                    checkout,
                    external,
                    {},
                )

    def test_lock_validator_rejects_structural_corruption(self) -> None:
        cases: list[tuple[str, dict, str]] = []

        duplicate = copy.deepcopy(self.lock)
        duplicate["package"].append(copy.deepcopy(duplicate["package"][0]))
        cases.append(("duplicate", duplicate, "duplicate package"))

        missing = copy.deepcopy(self.lock)
        kas = next(
            package for package in missing["package"]
            if package["name"] == "kas"
        )
        kas["dependencies"].append({"name": "missing-package"})
        cases.append(("missing", missing, "missing dependency"))

        orphan = copy.deepcopy(self.lock)
        orphan_package = copy.deepcopy(orphan["package"][0])
        orphan_package["name"] = "orphan-package"
        orphan["package"].append(orphan_package)
        cases.append(("orphan", orphan, "registry closure"))

        bad_sdist = copy.deepcopy(self.lock)
        bad_sdist["package"][0]["sdist"]["hash"] = "sha256:not-a-digest"
        cases.append(("sdist hash", bad_sdist, "sdist hash"))

        bad_wheel = copy.deepcopy(self.lock)
        bad_wheel["package"][0]["wheels"][0]["hash"] = "md5:bad"
        cases.append(("wheel hash", bad_wheel, "wheel hash"))

        for name, lock, message in cases:
            with self.subTest(name=name):
                with self.assertRaisesRegex(AssertionError, message):
                    validate_lock(lock)


if __name__ == "__main__":
    unittest.main()
