# uv-Managed Python Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the repository's hand-built Python virtual environment and `requirements-build.txt` with a reproducible uv project whose Python 3.12 environment is created as `.venv` in each checkout or worktree.

**Architecture:** `pyproject.toml` owns the direct build-tool contract, while the committed uv-generated `uv.lock` owns the complete resolved dependency graph. Repository tests validate the static contract with Python's standard library, and all documented Python and kas execution goes through `uv run --locked` without shell activation. Every environment gate rejects `UV_PROJECT_ENVIRONMENT` and requires a physical checkout-local non-symlink `.venv`. Privileged flashing authenticates a pinned official uv release archive inside a root-owned private directory before executing it. The uv feature is reviewed on `feature/uv-python-environment`, merged into `develop`, and then incorporated into the in-progress `feature/image-recipes` worktree before that work resumes.

**Tech Stack:** uv 0.11.31, system CPython 3.12, PEP 621 `pyproject.toml`, uv dependency groups and lockfile, kas 5.4, Python `tomllib` and `unittest`, Git feature branches and linked worktrees.

## Global Constraints

- Use `develop` as the integration branch and `feature/uv-python-environment` as the implementation branch.
- Write English Conventional Commit subjects and commit only independently testable functional units.
- Set `requires-python = ">=3.12,<3.13"` and `.python-version` to exactly `3.12`.
- Set `[tool.uv].required-version = "==0.11.31"` and verify `uv --version` prints `uv 0.11.31`.
- Set `[tool.uv].package = false`, `default-groups = ["build"]`, and `python-preference = "only-system"`.
- Keep `project.dependencies = []`; put exactly `kas==5.4` in `dependency-groups.build`.
- Commit `uv.lock`, generate or update it only with uv, and never edit it manually.
- Remove `requirements-build.txt`; do not keep a compatibility requirements file.
- Keep `.venv/` ignored; reject non-empty `UV_PROJECT_ENVIRONMENT`; require a physical, non-symlink `.venv` beside `pyproject.toml` whose realpath and running `sys.prefix` both equal `<physical checkout root>/.venv`.
- Do not activate `.venv`, call `.venv/bin/*`, use pip, use `uv pip install`, or run documented Python/kas commands outside `uv run --locked`.
- Before the uv project exists, only the migration plan's baseline and red-state checks may use the already-installed system `python3`; all steady-state repository workflows use uv.
- Install uv itself as a host prerequisite; do not vendor the uv binary or add it to `.venv`.
- For root flashing, pass only an absolute non-symlink `UV_ARCHIVE` authenticated as the official uv 0.11.31 GNU x86_64 archive with SHA-256 `8cc1cd82d434ec565376f98bd938d4b715b5791a80ff2d3aa78821cf85091b4b`; never pass or execute a user-selected executable path.
- Do not let uv download Python; fail if a compatible system Python 3.12 is unavailable.
- Change build dependencies only with `uv add --group build PACKAGE` or `uv remove --group build PACKAGE`, and commit `pyproject.toml` with the regenerated `uv.lock`.
- Delete only the verified legacy environment at `/home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation/.venv`; do not delete external checkouts, downloads, sstate, build outputs, or any other worktree.
- Do not change kas 5.4, Yocto layer pins, image behavior, AppArmor, sysctl settings, or the pending Task 4 BitBake acceptance decision.

---

## File Map

| Path | Change | Responsibility |
|---|---|---|
| `pyproject.toml` | Create | Declare the non-package project, Python range, build dependency group, and exact uv policy. |
| `uv.lock` | Create with `uv lock` | Lock kas and every resolved transitive dependency; never hand-edit this file. |
| `.python-version` | Create | Select the system Python 3.12 line for uv project discovery. |
| `.gitignore` | Modify | Document and retain the worktree-local `.venv/` exclusion. |
| `requirements-build.txt` | Delete | Remove the superseded second dependency source. |
| `tests/host/test_repository_contract.py` | Modify | Require the three uv project files and forbid the legacy requirements file. |
| `tests/host/test_uv_environment_contract.py` | Create | Parse and validate `pyproject.toml`, `uv.lock`, `.python-version`, and the local-environment policy offline. |
| `tests/host/test_uv_docs_contract.py` | Create | Reject legacy/direct and wrapped commands; enforce authenticated archive ordering and fail-closed negative coverage, physical-environment gate ordering, finalized helper/QEMU/deletion flow, and exact embedded environment-contract fidelity. |
| `docs/superpowers/specs/2026-07-22-rpi5-yocto-build-validation-design.md` | Modify | Express host setup, checkout, parse, build, and QEMU commands using locked uv execution. |
| `docs/superpowers/specs/2026-07-23-uv-python-environment-design.md` | Modify | Define physical environment locality and the authenticated privileged archive trust boundary. |
| `docs/superpowers/plans/2026-07-22-rpi5-yocto-firmware-implementation.md` | Modify | Make every planned host script, runbook, CI flow, test command, and kas invocation conform to the uv contract. |
| `docs/superpowers/plans/2026-07-23-uv-python-environment-implementation.md` | Modify | Keep this execution plan aligned with the finalized helper set, archive handoff, locality gates, QEMU process-group command, and safe legacy deletion. |

### Task 1: Establish the uv Project and Offline Environment Contract

**Files:**

- Create: `pyproject.toml`
- Create: `uv.lock` using uv
- Create: `.python-version`
- Create: `tests/host/test_uv_environment_contract.py`
- Modify: `.gitignore`
- Modify: `tests/host/test_repository_contract.py`
- Delete: `requirements-build.txt`

**Interfaces:**

- Consumes: system CPython `>=3.12,<3.13`, uv `0.11.31`, and the existing `tests/host/support.py` helpers `REPO_ROOT` and `read(relative: str) -> str`.
- Produces: `uv sync --locked`, `uv run --locked python ...`, and `uv run --locked kas ...` from any checkout root, with the environment at `REPO_ROOT / ".venv"`.

- [ ] **Step 1: Confirm the feature worktree and record the pre-change test baseline**

Run:

```bash
git branch --show-current
git status --short
python3 --version
python3 -m unittest discover -s tests/host -p 'test_*.py' -v
```

Expected:

- branch output is `feature/uv-python-environment`;
- `git status --short` is empty;
- Python reports `3.12.x`;
- every existing host test passes before the dependency contract changes.

- [ ] **Step 2: Replace the repository dependency assertion and add the failing uv contract**

Replace `tests/host/test_repository_contract.py` with:

```python
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
```

Create `tests/host/test_uv_environment_contract.py` with:

```python
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
```

- [ ] **Step 3: Run the new contracts and verify the red state**

Run:

```bash
python3 -m unittest discover -s tests/host -p 'test_repository_contract.py' -v
python3 -m unittest discover -s tests/host -p 'test_uv_environment_contract.py' -v
```

Expected:

- the repository test fails because `pyproject.toml`, `uv.lock`, and `.python-version` do not exist and `requirements-build.txt` still exists;
- the uv test errors with `FileNotFoundError` for `pyproject.toml`;
- failures are contract failures, not syntax or import failures.

- [ ] **Step 4: Install or select exactly uv 0.11.31 without changing shell startup files**

Run:

```bash
if [[ ! -x /home/many/.local/bin/uv ]] ||
   [[ "$(/home/many/.local/bin/uv --version | awk '{print $2}')" != "0.11.31" ]]; then
    curl -LsSf https://astral.sh/uv/0.11.31/install.sh |
        env UV_NO_MODIFY_PATH=1 UV_INSTALL_DIR=/home/many/.local/bin sh
    export PATH="/home/many/.local/bin:$PATH"
fi
test -x /home/many/.local/bin/uv
/home/many/.local/bin/uv --version
```

Expected:

- network access is explicitly approved if the installer must be downloaded;
- `command -v uv` resolves a user-owned executable;
- the version is exactly `uv 0.11.31`;
- no `.zshrc`, `.bashrc`, profile, or other shell startup file changes;
- an already-installed incompatible uv is not used for this repository.

- [ ] **Step 5: Add the exact project inputs and remove the legacy dependency file**

Create `pyproject.toml` with:

```toml
[project]
name = "yocto-rpi5-cam-firmware"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = []

[dependency-groups]
build = [
    "kas==5.4",
]

[tool.uv]
package = false
default-groups = ["build"]
required-version = "==0.11.31"
python-preference = "only-system"
```

Create `.python-version` with:

```text
3.12
```

Replace `.gitignore` with:

```gitignore
.worktrees/

# Worktree-local uv project environment.
.venv/
__pycache__/
*.py[cod]

build/
downloads/
sstate-cache/
.state/

keys/*
!keys/README.md

artifacts/*
!artifacts/README.md
!artifacts/releases/
artifacts/releases/*
!artifacts/releases/*.json

*.log
```

Delete `requirements-build.txt` with an explicit file deletion patch. Do not create an exported requirements file.

- [ ] **Step 6: Verify the tests remain red only because the generated lockfile is absent**

Run:

```bash
python3 -m unittest discover -s tests/host -p 'test_repository_contract.py' -v
python3 -m unittest discover -s tests/host -p 'test_uv_environment_contract.py' -v
```

Expected: both commands report `uv.lock` as the only missing project-contract file; no assertion references `requirements-build.txt` as a required file.

- [ ] **Step 7: Generate the lockfile and synchronize the worktree-local environment**

Run:

```bash
test -z "${UV_PROJECT_ENVIRONMENT:-}"
/home/many/.local/bin/uv lock
/home/many/.local/bin/uv lock --check
/home/many/.local/bin/uv sync --locked
test -d .venv
test ! -L .venv
test "$(realpath .venv)" = "$(pwd -P)/.venv"
/home/many/.local/bin/uv run --locked python -c \
  'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; assert pathlib.Path(sys.prefix).resolve() == expected; assert sys.version_info[:2] == (3, 12)'
```

Expected:

- uv resolves `kas==5.4` and writes `uv.lock`;
- `uv lock --check` exits `0` without modifying the lockfile;
- `uv sync --locked` creates `.venv` in the current feature worktree;
- uv uses a system CPython 3.12 interpreter and does not download managed Python;
- a dependency-resolution or download failure leaves the generated inputs uncommitted and preserves any previously valid `uv.lock`.

- [ ] **Step 8: Verify the interpreter prefix, kas version, and complete host suite**

Run:

```bash
test -z "${UV_PROJECT_ENVIRONMENT:-}"
test -d .venv
test ! -L .venv
test "$(realpath .venv)" = "$(pwd -P)/.venv"
/home/many/.local/bin/uv run --locked python -c \
  'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; assert pathlib.Path(sys.prefix).resolve() == expected; assert sys.version_info[:2] == (3, 12)'
/home/many/.local/bin/uv run --locked python -c 'import importlib.metadata as metadata; assert metadata.version("kas") == "5.4"'
/home/many/.local/bin/uv run --locked kas --version
/home/many/.local/bin/uv run --locked python -m unittest discover -s tests/host -p 'test_*.py' -v
```

Expected:

- the prefix assertion exits `0`;
- package metadata is exactly `5.4`;
- kas output contains `5.4`;
- every host test passes.

- [ ] **Step 9: Verify repository hygiene and lock reproducibility**

Run:

```bash
test ! -e requirements-build.txt
git check-ignore -v .venv
/home/many/.local/bin/uv lock --check
git diff --check
git status --short
```

Expected:

- the legacy requirements file is absent;
- `.venv` is ignored by the repository rule;
- the lock is current;
- no whitespace errors are reported;
- status lists only the intended project/test changes and the deleted requirements file, never `.venv`.

- [ ] **Step 10: Commit the tested uv project contract**

Run:

```bash
git add .gitignore .python-version pyproject.toml uv.lock tests/host/test_repository_contract.py tests/host/test_uv_environment_contract.py
git add -u requirements-build.txt
git diff --cached --check
git commit -m "build: migrate Python environment to uv"
```

Expected: the commit contains the exact metadata, generated lockfile, offline tests, ignore policy, and legacy file deletion; the worktree is clean afterward.

### Task 2: Migrate the Build-Validation Design to Locked uv Commands

**Files:**

- Create: `tests/host/test_uv_docs_contract.py`
- Modify: `docs/superpowers/specs/2026-07-22-rpi5-yocto-build-validation-design.md`

**Interfaces:**

- Consumes: the Task 1 commands `uv lock --check`, `uv sync --locked`, and `uv run --locked TOOL ...`.
- Produces: a canonical design whose setup, kas checkout, parse, build, and QEMU examples never require environment activation or pip.

- [ ] **Step 1: Write the failing build-design documentation contract**

Create `tests/host/test_uv_docs_contract.py` with:

```python
import re
import unittest

from support import read


DESIGN_DOCUMENT = (
    "docs/superpowers/specs/"
    "2026-07-22-rpi5-yocto-build-validation-design.md"
)
LEGACY_FRAGMENTS = (
    "requirements-build.txt",
    "python3 -m venv",
    ".venv/bin/activate",
    "pip install",
    "uv pip install",
)
DIRECT_TOOL = re.compile(
    r"(^\s*|(?:&&|\|\||;|\||\$\(|`)\s*)"
    r"(?:(?:[A-Za-z_][A-Za-z0-9_]*="
    r"(?:[^\s;&|]+|'[^']*'|\"[^\"]*\"))\s+|"
    r"(?:(?:sudo|env|exec|time|setsid)\s+))*"
    r"(?:python3?|kas)(?=\s|$)"
)
DIRECT_TOOL_NEGATIVE_FIXTURES = (
    "sudo python scripts/check.py",
    "env kas dump kas/rpi5-minimal.yml",
    "exec python -m unittest",
    "time kas --version",
    "FOO=bar python scripts/check.py",
    "setsid kas shell kas/qemuarm64-minimal.yml",
)


def shell_lines(markdown: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    in_shell_fence = False
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        stripped = line.strip()
        if stripped in ("```bash", "```sh", "```shell"):
            in_shell_fence = True
            continue
        if stripped.startswith("```"):
            in_shell_fence = False
            continue
        if in_shell_fence:
            lines.append((line_number, line))
        elif stripped.startswith("Run: `") and stripped.endswith("`"):
            lines.append((line_number, stripped.removeprefix("Run: `")[:-1]))
    return lines


class UvDocsContractTest(unittest.TestCase):
    def test_direct_tool_detector_rejects_wrappers_and_assignments(self) -> None:
        for command in DIRECT_TOOL_NEGATIVE_FIXTURES:
            with self.subTest(command=command):
                self.assertIsNotNone(DIRECT_TOOL.search(command))

    def test_direct_tool_detector_allows_locked_uv_under_setsid(self) -> None:
        self.assertIsNone(
            DIRECT_TOOL.search(
                "setsid uv run --locked kas shell "
                "kas/qemuarm64-minimal.yml -c runqemu"
            )
        )

    def test_build_design_uses_locked_uv_commands(self) -> None:
        text = read(DESIGN_DOCUMENT)
        for fragment in LEGACY_FRAGMENTS:
            self.assertNotIn(fragment, text)
        self.assertIn("uv lock --check", text)
        self.assertIn("uv sync --locked", text)
        self.assertGreaterEqual(text.count("uv run --locked kas"), 8)
        offenders = [
            f"{line_number}: {line}"
            for line_number, line in shell_lines(text)
            if DIRECT_TOOL.search(line)
        ]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the documentation contract and verify the red state**

Run:

```bash
/home/many/.local/bin/uv run --locked python -m unittest discover -s tests/host -p 'test_uv_docs_contract.py' -v
```

Expected: the test fails and identifies the legacy venv creation, activation, pip installation, and direct kas command examples in the design.

- [ ] **Step 3: Replace the design's host and build command flow**

In `docs/superpowers/specs/2026-07-22-rpi5-yocto-build-validation-design.md`, replace Sections 8.1 through 8.4 with the following complete text:

````markdown
### 8.1 호스트 준비

호스트 준비 스크립트는 다음을 검사하고 결과를 종료 코드로 반환한다.

- x86_64와 지원 Ubuntu 버전
- CPU, RAM, Swap, 디스크 공간
- `en_US.UTF-8` locale
- Git, 시스템 Python 3.12, uv 0.11.31, tar, make, gcc 최소 버전
- 필수 패키지와 `bmaptool`, QEMU, SSH 클라이언트
- 현재 사용자의 빌드 디렉터리 쓰기 권한
- BitBake를 root로 실행하지 않는지 여부
- SSH 공개키 파일 존재와 올바른 공개키 형식

Python 빌드 도구의 직접 의존성은 `pyproject.toml`, 전체 해석 결과는
`uv.lock`이 관리한다. uv는 시스템 Python만 사용하며 각 checkout 또는
worktree 루트에 독립적인 `.venv`를 만든다.

기본 명령 흐름은 다음과 같다.

```bash
test -z "${UV_PROJECT_ENVIRONMENT:-}"
uv --version
uv lock --check
uv sync --locked
test -d .venv
test ! -L .venv
test "$(realpath .venv)" = "$(pwd -P)/.venv"
uv run --locked python -c \
  'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; assert pathlib.Path(sys.prefix).resolve() == expected; assert sys.version_info[:2] == (3, 12)'
./scripts/host-preflight.sh
```

### 8.2 소스와 메타데이터 검증

```bash
uv run --locked kas checkout kas/qemuarm64-minimal.yml
uv run --locked kas shell kas/qemuarm64-minimal.yml -c 'bitbake-layers show-layers'
uv run --locked kas shell kas/qemuarm64-minimal.yml -c 'bitbake -p'
uv run --locked kas shell kas/rpi5-minimal.yml -c 'bitbake-layers show-layers'
uv run --locked kas shell kas/rpi5-minimal.yml -c 'bitbake -p'
```

이 단계의 합격 조건은 다음과 같다.

- 모든 저장소가 잠금 파일의 SHA와 일치한다.
- 모든 레이어가 `wrynose` 또는 BitBake 2.18과 호환된다.
- 중복 레시피와 치명적인 BitBake 경고가 없다.
- 두 구성 모두 전체 메타데이터를 파싱한다.

### 8.3 이미지 빌드

```bash
uv run --locked kas build kas/qemuarm64-minimal.yml
uv run --locked kas build kas/rpi5-minimal.yml
```

QEMU 이미지를 먼저 빌드한다. 이 빌드가 실패하면 Raspberry Pi 이미지
빌드와 SSD 기록을 진행하지 않는다.

각 성공 빌드는 다음 정보를 남긴다.

- 프로젝트 Git SHA
- 모든 외부 레이어 SHA
- BitBake, kas, uv 버전
- 이미지 패키지 목록
- 라이선스 매니페스트
- 빌드 로그
- 산출물 SHA-256

### 8.4 QEMU 시험

QEMU는 root 권한이 필요하지 않은 user-mode 네트워크를 기본으로 한다.

```bash
uv run --locked kas shell kas/qemuarm64-minimal.yml -c 'runqemu qemuarm64 nographic slirp'
```

`test-qemu.sh`는 별도 프로세스로 QEMU를 시작하고 제한 시간 안에 다음을
자동 확인한다.

1. 커널이 부팅되고 systemd multi-user target에 도달한다.
2. `uname -m` 결과가 `aarch64`이다.
3. systemd 상태가 `running`이다.
4. 유선 네트워크 구성 서비스와 SSH 서비스가 active이다.
5. SSH 비밀번호 인증과 root 로그인이 거부된다.
6. `rpiadmin` 공개키 인증이 성공한다.
7. 루트 파일시스템에 임시 파일을 쓰고 읽고 삭제할 수 있다.
8. 정상 종료 후 QEMU 프로세스와 임시 네트워크 자원이 남지 않는다.

QEMU 시작 제한 시간은 180초로 한다. 실패 시 콘솔 로그, systemd 실패
유닛, QEMU 실행 명령을 증적으로 보관한다.
````

- [ ] **Step 4: Run the focused and complete host suites**

Run:

```bash
/home/many/.local/bin/uv run --locked python -m unittest discover -s tests/host -p 'test_uv_docs_contract.py' -v
/home/many/.local/bin/uv run --locked python -m unittest discover -s tests/host -p 'test_*.py' -v
git diff --check
```

Expected: the focused test and complete host suite pass, and no whitespace errors are reported.

- [ ] **Step 5: Commit the build-design migration**

Run:

```bash
git add tests/host/test_uv_docs_contract.py docs/superpowers/specs/2026-07-22-rpi5-yocto-build-validation-design.md
git diff --cached --check
git commit -m "docs: adopt uv in build validation workflow"
```

Expected: one documentation contract and the corresponding canonical design change are committed together.

### Task 3: Align the Firmware Implementation Plan, Future Scripts, Runbooks, and CI

**Files:**

- Modify: `tests/host/test_uv_docs_contract.py`
- Modify: `docs/superpowers/plans/2026-07-22-rpi5-yocto-firmware-implementation.md`

**Interfaces:**

- Consumes: the Task 1 uv project contract and the shell-example parser from Task 2.
- Produces: one executable firmware implementation plan in which host tests, Python helpers, native kas, future host scripts, runbooks, and CI use the same locked project environment.

- [ ] **Step 1: Extend the documentation test to cover the complete firmware plan**

Replace `tests/host/test_uv_docs_contract.py` with:

```python
import re
import unittest

from support import read


DESIGN_DOCUMENT = (
    "docs/superpowers/specs/"
    "2026-07-22-rpi5-yocto-build-validation-design.md"
)
IMPLEMENTATION_PLAN = (
    "docs/superpowers/plans/"
    "2026-07-22-rpi5-yocto-firmware-implementation.md"
)
LEGACY_FRAGMENTS = (
    "python3 -m venv",
    ".venv/bin/activate",
    "pip install",
    "uv pip install",
)
DIRECT_TOOL = re.compile(
    r"(^\s*|(?:&&|\|\||;|\||\$\(|`)\s*)"
    r"(?:(?:[A-Za-z_][A-Za-z0-9_]*="
    r"(?:[^\s;&|]+|'[^']*'|\"[^\"]*\"))\s+|"
    r"(?:(?:sudo|env|exec|time|setsid)\s+))*"
    r"(?:python3?|kas)(?=\s|$)"
)
DIRECT_TOOL_NEGATIVE_FIXTURES = (
    "sudo python scripts/check.py",
    "env kas dump kas/rpi5-minimal.yml",
    "exec python -m unittest",
    "time kas --version",
    "FOO=bar python scripts/check.py",
    "setsid kas shell kas/qemuarm64-minimal.yml",
)
INDIRECT_KAS_FRAGMENTS = (
    "run_logged kas ",
    "rpi5_require_cmd kas",
    'rpi5_require_cmd "kas"',
    "command -v kas",
)


def shell_lines(markdown: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    in_shell_fence = False
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        stripped = line.strip()
        if stripped in ("```bash", "```sh", "```shell"):
            in_shell_fence = True
            continue
        if stripped.startswith("```"):
            in_shell_fence = False
            continue
        if in_shell_fence:
            lines.append((line_number, line))
        elif stripped.startswith("Run: `") and stripped.endswith("`"):
            lines.append((line_number, stripped.removeprefix("Run: `")[:-1]))
    return lines


class UvDocsContractTest(unittest.TestCase):
    def test_direct_tool_detector_rejects_wrappers_and_assignments(self) -> None:
        for command in DIRECT_TOOL_NEGATIVE_FIXTURES:
            with self.subTest(command=command):
                self.assertIsNotNone(DIRECT_TOOL.search(command))

    def test_direct_tool_detector_allows_locked_uv_under_setsid(self) -> None:
        self.assertIsNone(
            DIRECT_TOOL.search(
                "setsid uv run --locked kas shell "
                "kas/qemuarm64-minimal.yml -c runqemu"
            )
        )

    def assert_locked_uv_document(self, relative: str) -> str:
        text = read(relative)
        for fragment in LEGACY_FRAGMENTS:
            self.assertNotIn(fragment, text, f"{relative}: {fragment}")
        offenders = [
            f"{line_number}: {line}"
            for line_number, line in shell_lines(text)
            if DIRECT_TOOL.search(line)
        ]
        self.assertEqual(offenders, [], relative)
        return text

    def test_build_design_uses_locked_uv_commands(self) -> None:
        text = self.assert_locked_uv_document(DESIGN_DOCUMENT)
        self.assertNotIn("requirements-build.txt", text)
        self.assertIn("uv lock --check", text)
        self.assertIn("uv sync --locked", text)
        self.assertGreaterEqual(text.count("uv run --locked kas"), 8)

    def test_firmware_plan_uses_locked_uv_commands(self) -> None:
        text = self.assert_locked_uv_document(IMPLEMENTATION_PLAN)
        for fragment in INDIRECT_KAS_FRAGMENTS:
            self.assertNotIn(fragment, text)
        self.assertNotIn("- Create: `requirements-build.txt`", text)
        self.assertNotIn("# requirements-build.txt", text)
        self.assertNotRegex(text, r"git add [^\n]*requirements-build\.txt")
        self.assertIn(
            'self.assertFalse((REPO_ROOT / "requirements-build.txt").exists())',
            text,
        )
        self.assertIn("| `pyproject.toml` |", text)
        self.assertIn("| `uv.lock` |", text)
        self.assertIn("| `.python-version` |", text)
        self.assertIn("required-version = \"==0.11.31\"", text)
        self.assertIn("python-preference = \"only-system\"", text)
        self.assertGreaterEqual(text.count("uv run --locked python"), 25)
        self.assertGreaterEqual(text.count("uv run --locked kas"), 15)
        self.assertIn("run_logged uv run --locked kas", text)
        self.assertIn("uv run --locked kas for-all-repos", text)
        self.assertIn("uv run --locked python \"$helper\" validate", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the extended test and capture the legacy-command failures**

Run:

```bash
/home/many/.local/bin/uv run --locked python -m unittest discover -s tests/host -p 'test_uv_docs_contract.py' -v
```

Expected: the design test remains green; the firmware-plan test fails on the legacy requirements file, activation commands, direct test commands, direct kas calls, and planned shell-script invocations.

- [ ] **Step 3: Update the implementation plan's global project contract**

Apply these exact semantic changes to
`docs/superpowers/plans/2026-07-22-rpi5-yocto-firmware-implementation.md`:

1. Replace the architecture sentence beginning `Native kas==5.4` with:

```markdown
The native developer path is a non-package uv project pinned to uv 0.11.31,
system Python 3.12, and `kas==5.4`; the provider-neutral CI entry point
bootstraps that same uv version inside an OCI image pinned by digest.
```

2. Add these lines to `## Global Constraints` immediately after the kas pin:

```markdown
- Manage native Python tools only through `pyproject.toml` and committed `uv.lock`; do not create a requirements compatibility file.
- Require system Python `>=3.12,<3.13`, uv `0.11.31`, and a worktree-local ignored `.venv`.
- Use `uv lock --check`, `uv sync --locked`, and `uv run --locked`; never activate `.venv`, call pip, or invoke native Python/kas outside uv.
- Change native build dependencies only with `uv add --group build PACKAGE` or `uv remove --group build PACKAGE`, and commit `pyproject.toml` and `uv.lock` together.
```

3. In the Git workflow example, replace the first task's add command with:

```bash
git add .gitignore .python-version pyproject.toml uv.lock keys/README.md artifacts/README.md tests
```

4. Replace the dependency row in `## File Map` with these three rows:

```markdown
| `pyproject.toml` | Pin the non-package uv project, system Python range, uv version, and native `kas==5.4` build group. |
| `uv.lock` | Lock the complete native Python dependency graph generated by uv. |
| `.python-version` | Select the system Python 3.12 line for every checkout and worktree. |
```

- [ ] **Step 4: Rewrite Task 1 of the firmware plan around the uv project**

Replace the entire existing Task 1 section, from its `### Task 1` heading
through the line immediately before `### Task 2`, with:

~~~~markdown
### Task 1: Repository Guardrails and uv Test Harness

**Feature branch:** `feature/repository-guardrails`

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `uv.lock` using uv
- Create: `.python-version`
- Create: `keys/README.md`
- Create: `artifacts/README.md`
- Create: `tests/oeqa/README.md`
- Create: `tests/host/support.py`
- Create: `tests/host/test_repository_contract.py`
- Create: `tests/host/test_uv_environment_contract.py`

**Interfaces:**
- Consumes: system Python 3.12, uv 0.11.31, and the repository root.
- Produces: `support.REPO_ROOT: pathlib.Path`, `support.read(relative: str) -> str`, and `support.run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]` for later host tests; `uv run --locked` supplies Python and kas from a root-level `.venv`.

- [ ] **Step 1: Create the feature branch**

```bash
git switch develop
git switch -c feature/repository-guardrails
```

- [ ] **Step 2: Install or select the pinned uv prerequisite**

```bash
if [[ ! -x /home/many/.local/bin/uv ]] ||
   [[ "$(/home/many/.local/bin/uv --version | awk '{print $2}')" != "0.11.31" ]]; then
    curl -LsSf https://astral.sh/uv/0.11.31/install.sh |
        env UV_NO_MODIFY_PATH=1 UV_INSTALL_DIR=/home/many/.local/bin sh
    export PATH="/home/many/.local/bin:$PATH"
fi
test "$(/home/many/.local/bin/uv --version | awk '{print $2}')" = "0.11.31"
```

Expected: uv is exactly 0.11.31 and no shell startup file is modified.

- [ ] **Step 3: Add the uv project inputs and generate the lock**

```toml
# pyproject.toml
[project]
name = "yocto-rpi5-cam-firmware"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = []

[dependency-groups]
build = [
    "kas==5.4",
]

[tool.uv]
package = false
default-groups = ["build"]
required-version = "==0.11.31"
python-preference = "only-system"
```

```text
# .python-version
3.12
```

```gitignore
# .gitignore
.worktrees/

# Worktree-local uv project environment.
.venv/
__pycache__/
*.py[cod]

build/
downloads/
sstate-cache/
.state/

keys/*
!keys/README.md

artifacts/*
!artifacts/README.md
!artifacts/releases/
artifacts/releases/*
!artifacts/releases/*.json

*.log
```

Run:

```bash
test -z "${UV_PROJECT_ENVIRONMENT:-}"
uv lock
uv lock --check
uv sync --locked
test -d .venv
test ! -L .venv
test "$(realpath .venv)" = "$(pwd -P)/.venv"
uv run --locked python -c \
  'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; assert pathlib.Path(sys.prefix).resolve() == expected; assert sys.version_info[:2] == (3, 12)'
```

Expected: uv resolves `kas==5.4`, writes `uv.lock`, and creates `.venv`
beside `pyproject.toml` with system Python 3.12. Commit the generated
lockfile without editing it manually.

- [ ] **Step 4: Write the failing repository and uv contract tests**

```python
# tests/host/support.py
from __future__ import annotations

import os
from pathlib import Path
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
```

```python
# tests/host/test_repository_contract.py
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
```

```python
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
```

- [ ] **Step 5: Run the tests and confirm the missing-policy red state**

Run:

```bash
uv run --locked python -m unittest discover -s tests/host -p 'test_repository_contract.py' -v
uv run --locked python -m unittest discover -s tests/host -p 'test_uv_environment_contract.py' -v
```

Expected: the uv environment contract passes; the repository contract
errors on the absent `keys/README.md`, `artifacts/README.md`, or
`tests/oeqa/README.md`.

- [ ] **Step 6: Add the remaining exact repository policy files**

````markdown
# keys/README.md

배포용 로그인 키는 로컬에서 다음 명령으로 생성한다.

```bash
ssh-keygen -t ed25519 -f keys/rpi5_admin -C rpi5-admin
chmod 600 keys/rpi5_admin
chmod 644 keys/rpi5_admin.pub
```

빌드는 `keys/rpi5_admin.pub`를 이미지에 주입하고, QEMU·실기기 시험은
`keys/rpi5_admin`을 사용한다. 두 파일 모두 Git에 추가하지 않는다.
공개키가 없거나 `ssh-keygen -l -f keys/rpi5_admin.pub` 검증에 실패하면
빌드 전 점검을 실패시킨다.
````

```markdown
# artifacts/README.md

각 실행은 `artifacts/BUILD_ID/` 아래에 `images`, `checksums`, `manifests`,
`qemu-test`, `rpi5-test`, `camera-test`를 만든다. BUILD_ID 형식은
`UTC-git-sha`이며 이미지와 원시 로그는 Git에 추가하지 않는다. 외부
보관소에는 최근 정상 Raspberry Pi 이미지 세 개와 직전 정상 이미지를
유지한다.

Git에는 `artifacts/releases/BUILD_ID.json` 형식의 작은 승인 요약만
추가할 수 있다. 요약은 build ID, 프로젝트 SHA, 외부 레이어 SHA,
이미지 SHA-256, 시험 결과, 승인 시각만 포함하고 개인 키·IP·장치
일련번호·원시 journal은 포함하지 않는다.
```

```markdown
# tests/oeqa/README.md

Yocto 6.0 `testimage`의 QEMU 대상은 `allow-empty-password`,
`empty-root-password`, `allow-root-login`을 요구한다. 이 프로젝트의
공개키 전용 `rpiadmin` 및 root 로그인 금지 정책과 양립하지 않으므로
해당 기능을 이미지에 추가하지 않는다.

QEMU 런타임 합격 판정은 localhost SLIRP SSH를 사용하는
`scripts/test-qemu.sh`가 담당한다. 이 디렉터리는 보안상 의도된 선택을
기록하며 OEQA 런타임 모듈을 활성화하지 않는다.
```

- [ ] **Step 7: Run the contracts and inspect ignored paths**

Run:

```bash
test -z "${UV_PROJECT_ENVIRONMENT:-}"
uv lock --check
uv sync --locked
test -d .venv
test ! -L .venv
test "$(realpath .venv)" = "$(pwd -P)/.venv"
uv run --locked python -c \
  'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; assert pathlib.Path(sys.prefix).resolve() == expected; assert sys.version_info[:2] == (3, 12)'
uv run --locked python -m unittest discover -s tests/host -p 'test_repository_contract.py' -v
uv run --locked python -m unittest discover -s tests/host -p 'test_uv_environment_contract.py' -v
uv run --locked kas --version
git check-ignore -v .venv keys/rpi5_admin keys/rpi5_admin.pub build/example artifacts/example/images/image.wic
```

Expected: all nine contracts pass, kas reports 5.4, and all five generated
or sensitive paths are reported as ignored.

- [ ] **Step 8: Commit the repository foundation**

```bash
git add .gitignore .python-version pyproject.toml uv.lock keys/README.md artifacts/README.md tests
git commit -m "chore: add uv-managed Yocto workspace guardrails"
```

Expected: merge `feature/repository-guardrails` to `develop` only after the
repository and uv environment contracts pass.
~~~~

- [ ] **Step 5: Apply the exact repetitive command migration throughout Tasks 2-15**

Use one reviewable bulk patch to make every literal mapping below everywhere
in the firmware plan. Preserve each command's arguments, quoting,
redirections, and expected output.

| Legacy command fragment | Required replacement |
|---|---|
| `. .venv/bin/activate && python ` | `uv run --locked python ` |
| `. .venv/bin/activate && kas ` | `uv run --locked kas ` |
| `python -m unittest ` at the start of a Bash example line | `uv run --locked python -m unittest ` |
| `python scripts/` at the start of a Bash example line | `uv run --locked python scripts/` |
| `python -m json.tool ` at the start of a Bash example line | `uv run --locked python -m json.tool ` |
| `python - ` at the start of a Bash example line | `uv run --locked python - ` |
| `kas checkout ` at the start of a Bash example line | `uv run --locked kas checkout ` |
| `kas dump ` at the start of a Bash example line | `uv run --locked kas dump ` |
| `kas shell ` at the start of a Bash example line | `uv run --locked kas shell ` |
| `kas build ` at the start of a Bash example line | `uv run --locked kas build ` |

For multi-command `Run:` lines, remove only the activation fragment. For
example, the gated-build failure check becomes exactly:

```markdown
Run: `BUILD_ID="$(./scripts/new-build-id.sh)"; ./scripts/build.sh --build-id "$BUILD_ID" rpi5-minimal build`
```

Shell orchestration scripts remain directly executable. Their internal
Python/kas calls are changed in the next step so callers do not need an
activated environment.

- [ ] **Step 6: Make planned host scripts self-contained uv callers**

In the Task 5 `scripts/host-preflight.sh` block:

1. Change the command list from global kas to uv:

```bash
required_commands=(
    git tar make gcc python3 uv
    bmaptool qemu-system-aarch64
    ssh scp ssh-keygen ssh-keyscan ss
    avahi-resolve-host-name ping
    lsblk findmnt blockdev partprobe udevadm
    mount umount sha256sum file ffprobe
)
```

2. Immediately after `repo_root="$(rpi5_repo_root)"`, add:

```bash
cd "$repo_root"
```

3. Replace Python, uv, and kas version checks with:

```bash
uv_version="$(uv --version | awk '{print $2}')"
[[ "$uv_version" == "0.11.31" ]] || rpi5_die "uv must be version 0.11.31"
uv lock --check || rpi5_die "uv.lock is stale"
test -z "${UV_PROJECT_ENVIRONMENT:-}" ||
    rpi5_die "UV_PROJECT_ENVIRONMENT must be unset or empty"
test -d .venv || rpi5_die ".venv must be a directory"
test ! -L .venv || rpi5_die ".venv must not be a symlink"
test "$(realpath .venv)" = "$(pwd -P)/.venv" ||
    rpi5_die ".venv must be physically checkout-local"
uv run --locked python -c \
    'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; assert pathlib.Path(sys.prefix).resolve() == expected; assert sys.version_info[:2] == (3, 12)' ||
    rpi5_die "uv must run physical checkout-local Python 3.12"
python_version="$(uv run --locked python -c 'import platform; print(platform.python_version())')"
version_ge "$python_version" "3.12" || rpi5_die "Python must be at least 3.12"
version_ge "3.12.999" "$python_version" || rpi5_die "Python must be below 3.13"
uv run --locked kas --version |
    grep -Eq '(^|[[:space:]])5\.4([[:space:]]|$)' ||
    rpi5_die "kas must be version 5.4"
```

In Task 6's `scripts/build.sh`, replace the entire action case with:

```bash
repo_root="$(rpi5_repo_root)"
cd "$repo_root"
case "$action" in
    checkout) run_logged uv run --locked kas checkout "$config" ;;
    layers) run_logged uv run --locked kas shell "$config" -c 'bitbake-layers show-layers' ;;
    parse) run_logged uv run --locked kas shell "$config" -c 'bitbake -p' ;;
    build)
        run_logged uv run --locked kas build "$config"
        "$repo_root/scripts/collect-artifacts.sh" \
            --build-id "$build_id" --profile "$profile" \
            --config "$config" --machine "$machine" --image "$image"
        ;;
esac
```

In Task 6's `scripts/collect-artifacts.sh`, add `cd "$repo_root"` after
`repo_root="$(rpi5_repo_root)"`, then replace its kas calls with:

```bash
uv run --locked kas for-all-repos "$config" \
    'printf "%s %s\n" "$KAS_REPO_NAME" "$(git rev-parse HEAD)"' \
    | LC_ALL=C sort > "$out/manifests/layer-revisions.txt"

project_revision="$(git -C "$repo_root" rev-parse HEAD)"
kas_version="$(uv run --locked kas --version | tr '\n' ' ')"
```

In Task 7's QEMU launcher, preserve process-group cleanup by using and
contract-testing this exact invocation:

```bash
repo_root="$(rpi5_repo_root)"
cd "$repo_root"
setsid uv run --locked kas shell kas/qemuarm64-minimal.yml \
    -c 'runqemu qemuarm64 rpi5-minimal-image nographic slirp'
```

Add the corresponding embedded contract:

```python
self.assertIn("setsid uv run --locked kas shell", script)
```

In Task 8, replace every privileged executable handoff with an authenticated
archive flow. Pin:

- archive:
  `https://releases.astral.sh/github/uv/releases/download/0.11.31/uv-x86_64-unknown-linux-gnu.tar.gz`
- SHA-256:
  `8cc1cd82d434ec565376f98bd938d4b715b5791a80ff2d3aa78821cf85091b4b`
- release:
  `https://github.com/astral-sh/uv/releases/tag/0.11.31`

The future root script must contain this complete trust-boundary core before
any block-device query or operation:

```bash
readonly UV_RELEASE_SHA256="8cc1cd82d434ec565376f98bd938d4b715b5791a80ff2d3aa78821cf85091b4b"
authenticated_uv_bin=""

authenticate_uv_archive() {
    local uv_archive="$1"
    local uv_private_dir="$2"
    local uv_archive_copy="$uv_private_dir/uv-release.tar.gz"
    local uv_extract_dir="$uv_private_dir/extract"
    local candidate_uv_bin="$uv_extract_dir/uv-x86_64-unknown-linux-gnu/uv"

    authenticated_uv_bin=""
    if [[ "$uv_archive" != /* || ! -f "$uv_archive" || -L "$uv_archive" ]]; then
        rpi5_die "UV_ARCHIVE must be an absolute regular non-symlink archive path" || true
        return 1
    fi
    if ! install -m 0600 -- "$uv_archive" "$uv_archive_copy"; then
        rpi5_die "failed to copy uv archive into private storage" || true
        return 1
    fi
    if [[ ! -f "$uv_archive_copy" || -L "$uv_archive_copy" ]]; then
        rpi5_die "private uv archive copy is not a regular file" || true
        return 1
    fi
    if [[ "$(stat -c %u "$uv_archive_copy")" != "$EUID" ]]; then
        rpi5_die "private uv archive copy ownership is invalid" || true
        return 1
    fi
    if ! printf '%s  %s\n' "$UV_RELEASE_SHA256" "$uv_archive_copy" |
        sha256sum --check --strict --status; then
        rpi5_die "authenticated uv archive checksum mismatch" || true
        return 1
    fi

    if ! install -d -m 0700 "$uv_extract_dir"; then
        rpi5_die "failed to create private uv extraction directory" || true
        return 1
    fi
    if ! tar --extract --file "$uv_archive_copy" --directory "$uv_extract_dir" \
        --gzip --no-same-owner --no-same-permissions; then
        rpi5_die "failed to extract authenticated uv archive" || true
        return 1
    fi
    if [[ ! -f "$candidate_uv_bin" || -L "$candidate_uv_bin" ]]; then
        rpi5_die "authenticated archive is missing the expected uv executable" || true
        return 1
    fi
    if ! chmod 0700 "$candidate_uv_bin"; then
        rpi5_die "failed to restrict authenticated uv executable mode" || true
        return 1
    fi
    if [[ "$(stat -c %u "$candidate_uv_bin")" != "$EUID" ||
          "$(stat -c %a "$candidate_uv_bin")" != "700" ]]; then
        rpi5_die "authenticated uv executable ownership or mode is invalid" || true
        return 1
    fi
    authenticated_uv_bin="$candidate_uv_bin"
}

[[ "$EUID" -eq 0 ]] || rpi5_die "flash requires root for the selected device only"
[[ -z "${UV_PROJECT_ENVIRONMENT:-}" ]] ||
    rpi5_die "UV_PROJECT_ENVIRONMENT must be unset for privileged flashing"
repo_root="$(rpi5_repo_root)"
cd "$repo_root"
[[ -d .venv && ! -L .venv ]] ||
    rpi5_die "privileged uv requires a physical checkout-local .venv"
[[ "$(realpath .venv)" == "$repo_root/.venv" ]] ||
    rpi5_die "privileged uv environment resolves outside the checkout"
uv_archive="${UV_ARCHIVE:-}"
[[ "$uv_archive" = /* && -f "$uv_archive" && ! -L "$uv_archive" ]] ||
    rpi5_die "UV_ARCHIVE must be an absolute regular non-symlink archive path"
umask 077
uv_private_dir=""
cleanup_uv() {
    if [[ "${uv_private_dir:-}" =~ ^/var/tmp/rpi5-flash-uv\.[A-Za-z0-9]{8}$ ]] &&
       [[ -d "$uv_private_dir" && ! -L "$uv_private_dir" ]] &&
       [[ "$(stat -c %u "$uv_private_dir")" == "0" ]]; then
        find "$uv_private_dir" -xdev -depth -delete
    fi
    uv_private_dir=""
}
uv_private_dir="$(mktemp -d /var/tmp/rpi5-flash-uv.XXXXXXXX)"
trap cleanup_uv EXIT
chown root:root "$uv_private_dir"
chmod 0700 "$uv_private_dir"
[[ -d "$uv_private_dir" && ! -L "$uv_private_dir" ]]
[[ "$(stat -c %u "$uv_private_dir")" == "0" ]]
authenticate_uv_archive "$uv_archive" "$uv_private_dir" || exit 1
uv_bin="$authenticated_uv_bin"
[[ "$("$uv_bin" --version | awk '{print $2}')" == "0.11.31" ]] ||
    rpi5_die "authenticated uv executable must be version 0.11.31"
"$uv_bin" run --locked python -c \
    'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; assert pathlib.Path(sys.prefix).resolve() == expected; assert sys.version_info[:2] == (3, 12)'
```

Use that single authenticated private executable for the finalized complete
helper set:

```bash
image_bytes="$("$uv_bin" run --locked python "$helper" bmap-size --bmap "$bmap")"
metadata="$("$uv_bin" run --locked python "$helper" validate \
    --topology "$topology" --target "$device" --image-bytes "$image_bytes" \
    "${protected[@]}" --allow-mounted)"
mapfile -t mounted < <("$uv_bin" run --locked python "$helper" mounts \
    --topology "$topology" --target "$device")
"$uv_bin" run --locked python "$helper" validate \
    --topology "$topology" --target "$device" --image-bytes "$image_bytes" \
    "${protected[@]}" >/dev/null
boot_partition="$("$uv_bin" run --locked python "$helper" partition \
    --device "$device" --number 1)"
root_partition="$("$uv_bin" run --locked python "$helper" partition \
    --device "$device" --number 2)"
```

The flash cleanup function must invoke `cleanup_uv`; the root script must
contain no download command, `sudo -E`, or network access.

Add the future executable negative test `test_spoofed_uv_executable_is_rejected`.
It must put a real executable that prints `uv 0.11.31` and writes a marker
inside a wrong-hash archive at the expected release path, then exercise the
exact fail-closed production authentication sequence:

```python
archive_root = root / "archive-root"
payload = archive_root / "uv-x86_64-unknown-linux-gnu"
payload.mkdir(parents=True)
spoof = payload / "uv"
archive = root / "spoof.tar.gz"
marker = root / "SPOOF_EXECUTED"
private = root / "private"
private.mkdir(mode=0o700)
spoof.write_text(
    "#!/usr/bin/env bash\n"
    ': > "${SPOOF_MARKER:?}"\n'
    "printf 'uv 0.11.31\\n'\n",
    encoding="utf-8",
)
spoof.chmod(0o755)
tar_result = run(
    "tar", "--create", "--gzip",
    "--file", os.fspath(archive),
    "--directory", os.fspath(archive_root),
    "uv-x86_64-unknown-linux-gnu",
)
self.assertEqual(tar_result.returncode, 0, tar_result.stderr)
result = run(
    "bash", "-c",
    'source "$1"\n'
    'authenticate_uv_archive "$2" "$3" || exit 1\n'
    'uv_bin="$authenticated_uv_bin"\n'
    '"$uv_bin" --version\n',
    "bash", str(REPO_ROOT / "scripts/flash-ssd.sh"),
    str(archive), str(private),
    env={"SPOOF_MARKER": os.fspath(marker)},
)
self.assertNotEqual(result.returncode, 0)
self.assertIn("authenticated uv archive checksum mismatch", result.stderr)
self.assertFalse(marker.exists(), "spoofed executable was run")
```

In Task 9's `scripts/discover-rpi5.sh`, replace its inline Python call with:

```bash
repo_root="$(rpi5_repo_root)"
cd "$repo_root"
    uv run --locked python - "$1" <<'PY'
```

These scripts resolve the uv project from the repository root and reject a
stale lock through `--locked`.

In Task 5's embedded `HostToolsTest`, make the required-tool assertion
include uv:

```python
        for command in (
            "uv",
            "bmaptool",
            "qemu-system-aarch64",
            "avahi-resolve-host-name",
            "partprobe",
            "ffprobe",
        ):
            self.assertIn(command, script)
```

In Task 5's Ubuntu package command, replace:

```bash
  python3-jinja2 python3-pexpect python3-pip python3-subunit python3-venv socat \
```

with:

```bash
  python3-jinja2 python3-pexpect python3-subunit socat \
```

The system Python interpreter remains required, but pip and the standard
library venv provisioning package are no longer repository setup tools.

- [ ] **Step 7: Migrate the planned operator runbooks**

Replace the Task 12 one-time Python setup block with:

```bash
if ! command -v uv >/dev/null 2>&1 ||
   [[ "$(uv --version | awk '{print $2}')" != "0.11.31" ]]; then
    curl -LsSf https://astral.sh/uv/0.11.31/install.sh |
        env UV_NO_MODIFY_PATH=1 UV_INSTALL_DIR=/home/many/.local/bin sh
    export PATH="/home/many/.local/bin:$PATH"
fi
test -z "${UV_PROJECT_ENVIRONMENT:-}"
uv lock --check
uv sync --locked
test -d .venv
test ! -L .venv
test "$(realpath .venv)" = "$(pwd -P)/.venv"
uv run --locked python -c \
  'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; assert pathlib.Path(sys.prefix).resolve() == expected; assert sys.version_info[:2] == (3, 12)'
uv run --locked kas --version
```

In the same Task 12 Ubuntu package block, replace:

```bash
  python3-jinja2 python3-pexpect python3-pip python3-subunit python3-venv socat \
```

with:

```bash
  python3-jinja2 python3-pexpect python3-subunit socat \
```

Remove each standalone `. .venv/bin/activate` line from the QEMU, USB SSD,
remote Raspberry Pi, and camera runbook blocks. Keep their repository shell
scripts directly executable because Task 6 makes Python/kas calls inside
those scripts use uv.

Before every minimal or camera flash, download and verify the pinned archive
as the normal user into ignored repository state, then pass only its
absolute path:

```bash
UV_RELEASE_URL="https://releases.astral.sh/github/uv/releases/download/0.11.31/uv-x86_64-unknown-linux-gnu.tar.gz"
UV_RELEASE_SHA256="8cc1cd82d434ec565376f98bd938d4b715b5791a80ff2d3aa78821cf85091b4b"
UV_ARCHIVE="$(pwd -P)/.state/uv-release/uv-x86_64-unknown-linux-gnu.tar.gz"
mkdir -p "$(dirname "$UV_ARCHIVE")"
curl --fail --location --proto '=https' --tlsv1.2 \
  "$UV_RELEASE_URL" --output "$UV_ARCHIVE.download"
printf '%s  %s\n' "$UV_RELEASE_SHA256" "$UV_ARCHIVE.download" |
  sha256sum --check --strict
mv -- "$UV_ARCHIVE.download" "$UV_ARCHIVE"
test -f "$UV_ARCHIVE"
test ! -L "$UV_ARCHIVE"
printf '%s  %s\n' "$UV_RELEASE_SHA256" "$UV_ARCHIVE" |
  sha256sum --check --strict
sudo UV_ARCHIVE="$UV_ARCHIVE" ./scripts/flash-ssd.sh \
  --build-id "$BUILD_ID" --profile "$PROFILE" \
  --device "$TARGET_DEVICE" --confirm "$CONFIRMATION"
```

Do not use `sudo -E`, a root download, or any user-selected executable
handoff.

Replace every remaining runbook Python command with its locked form:

```bash
uv run --locked python -m json.tool "artifacts/$BUILD_ID/rpi5-test/result.json"
uv run --locked python -m json.tool "artifacts/$BUILD_ID/camera-test/result.json"
uv run --locked python scripts/release_summary.py --build-id "$BUILD_ID"
uv run --locked python -m json.tool "$RELEASE_JSON"
uv run --locked python - "$RELEASE_JSON" <<'PY'
uv run --locked python -m json.tool "artifacts/releases/$BUILD_ID.json"
```

- [ ] **Step 8: Make the future CI flow bootstrap and use the same uv contract**

In Task 13, change `ci/pipeline.sh` so `repo_root` is followed by this exact
bootstrap function and invocation:

```bash
ensure_uv() {
    if ! command -v uv >/dev/null 2>&1 ||
       [[ "$(uv --version | awk '{print $2}')" != "0.11.31" ]]; then
        mkdir -p "$repo_root/.state/uv-bin"
        curl -LsSf https://astral.sh/uv/0.11.31/install.sh |
            env UV_NO_MODIFY_PATH=1 UV_INSTALL_DIR="$repo_root/.state/uv-bin" sh
        export PATH="$repo_root/.state/uv-bin:$PATH"
    fi
    [[ "$(uv --version | awk '{print $2}')" == "0.11.31" ]] ||
        rpi5_die "uv must be version 0.11.31"
    cd "$repo_root"
    test -z "${UV_PROJECT_ENVIRONMENT:-}"
    uv lock --check
    uv sync --locked
    test -d .venv
    test ! -L .venv
    test "$(realpath .venv)" = "$(pwd -P)/.venv"
    uv run --locked python -c \
        'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; assert pathlib.Path(sys.prefix).resolve() == expected; assert sys.version_info[:2] == (3, 12)'
}

ensure_uv
```

Replace Task 13's container-aware required-command block with:

```bash
required_commands=(
    git tar make gcc python3 uv
    qemu-system-aarch64 ssh scp ssh-keygen ssh-keyscan ss
    sha256sum setsid sort awk grep stat df nproc tr tee
)
if [[ "$container_mode" == "0" ]]; then
    required_commands+=(
        bmaptool avahi-resolve-host-name ping
        lsblk findmnt blockdev partprobe udevadm
        mount umount file ffprobe
    )
fi
```

Replace `run_unit()` with:

```bash
run_unit() {
    uv run --locked python -m unittest discover -s tests/host -p 'test_*.py' -v
    while IFS= read -r script; do
        bash -n "$script"
    done < <(find scripts ci -type f -name '*.sh' -print | LC_ALL=C sort)
}
```

Add this method to the embedded `CiContractTest`:

```python
    def test_pipeline_bootstraps_pinned_uv_project(self) -> None:
        script = read("ci/pipeline.sh")
        self.assertIn("https://astral.sh/uv/0.11.31/install.sh", script)
        self.assertIn("UV_NO_MODIFY_PATH=1", script)
        self.assertIn('[[ "$(uv --version | awk \'{print $2}\')" == "0.11.31" ]]', script)
        self.assertIn("uv lock --check", script)
        self.assertIn("uv sync --locked", script)
        self.assertIn("uv run --locked python", script)
```

Change Task 13's focused CI-test expectation from `Ran 4 tests` to
`Ran 5 tests`.

Update the CI service-boundary text to state exactly:

```markdown
Each job allows the pinned Astral uv 0.11.31 installer download, keeps the
installer under ignored `.state/uv-bin`, runs `uv lock --check` and
`uv sync --locked`, and then invokes the selected pipeline stage. The uv
binary is a job-local host prerequisite and is never committed or copied
into the target image.
```

Keep the OCI digest, official kas-container wrapper checksum, and kas source
commit unchanged. The container still supplies the Yocto host toolchain;
the uv project supplies the exact Python/kas command environment.

**Final consolidated documentation contract**

Before the final verification step, extend the staged
`tests/host/test_uv_docs_contract.py` into the six-test final contract. Keep
the earlier build-design and firmware-plan coverage, and add these named
helpers and final-plan test:

- `assert_authenticated_privileged_uv_flow` must require the exact archive
  URL/SHA/release, a private copied archive, explicit failure returns for
  copy/hash/extract/mode errors, no authenticator command substitution, early
  cleanup arming, the wrong-hash tar fixture containing the spoof executable,
  and no marker execution.
- `assert_secure_flash_script_order` must prove archive copy, copied-byte
  checksum, safe extraction, validated-path publication, version/locality
  gate, and locked execution all precede the first block-device operation.
- `assert_override_rejected_before_sync` must inspect every embedded bash
  block containing `sync --locked` and prove
  `UV_PROJECT_ENVIRONMENT` is rejected before its first lock/sync/run.
- `assert_physical_venv_gates` must enforce the non-symlink directory,
  physical realpath, `sys.prefix`, and Python 3.12 checks at every future
  feature/integration/image/CI gate and in privileged flashing.
- `assert_exact_embedded_environment_contracts` must compare the firmware
  plan's one and this plan's two environment-test blocks byte-for-byte with
  the live final environment contract.
- `test_uv_migration_plan_matches_final_secure_flow` must enforce the complete
  helper set, `validate --target`, repository anchors, QEMU `setsid` contract,
  exact safe-deletion guards, wrapper fixtures, and the final contract
  requirements above.

The two earlier embedded documentation-test blocks remain intentionally
stage-specific TDD snapshots; this final upgrade supersedes them rather than
rewriting their historical RED expectations.

- [ ] **Step 9: Run the documentation contract and inspect every remaining direct command**

Run:

```bash
/home/many/.local/bin/uv run --locked python -m unittest discover -s tests/host -p 'test_uv_docs_contract.py' -v
/home/many/.local/bin/uv run --locked python -m unittest discover -s tests/host -p 'test_*.py' -v
rg -n 'python3 -m venv|\.[v]env/bin/activate|pip install|uv pip install' docs/superpowers/specs/2026-07-22-rpi5-yocto-build-validation-design.md docs/superpowers/plans/2026-07-22-rpi5-yocto-firmware-implementation.md
rg -n 'Create: `requirements-build\.txt`|# requirements-build\.txt|git add .*requirements-build\.txt' docs/superpowers/plans/2026-07-22-rpi5-yocto-firmware-implementation.md
rg -n 'U[V]_BIN' docs/superpowers/plans/2026-07-22-rpi5-yocto-firmware-implementation.md docs/superpowers/plans/2026-07-23-uv-python-environment-implementation.md
rg -n -U 'validate --topology "\$topology" \\\n[[:space:]]+--device' docs/superpowers/plans/2026-07-22-rpi5-yocto-firmware-implementation.md docs/superpowers/plans/2026-07-23-uv-python-environment-implementation.md
git diff --check
```

Expected:

- all six focused documentation-contract tests pass;
- the complete host suite passes;
- all four `rg` commands exit `1` with no matches;
- the documentation contract allows direct system `python3` only in the six
  explicitly enumerated pre-project baseline/red-state commands and rejects
  every direct steady-state Python/kas command, including wrapper forms;
- `git diff --check` reports no errors.

- [ ] **Step 10: Review the large plan diff by semantic area**

Run:

```bash
git diff --stat
git diff -- docs/superpowers/plans/2026-07-22-rpi5-yocto-firmware-implementation.md
git status --short
```

Expected:

- only the live uv environment/documentation contracts, canonical firmware
  plan, active uv plan, and uv design specification are changed in this
  review-fix wave;
- no Yocto pin, image recipe, device policy, evidence gate, hardware flow,
  OCI digest, or wrapper checksum changes;
- every deleted activation/direct invocation has an equivalent locked uv
  command or a self-contained wrapper call.

- [ ] **Step 11: Commit the firmware-plan migration**

Run:

```bash
git add tests/host/test_uv_docs_contract.py docs/superpowers/plans/2026-07-22-rpi5-yocto-firmware-implementation.md
git diff --cached --check
git commit -m "docs: align firmware implementation plan with uv"
```

Expected: the command-policy test and complete future-workflow rewrite form
one independently reviewable documentation commit.

### Task 4: Integrate to `develop`, Replace the Legacy Worktree Environment, and Revalidate

**Files:**

- Delete generated directory after exact-path validation: `/home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation/.venv`
- Recreate generated directory with uv: `/home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation/.venv`
- No new tracked source file is created in this task.

**Interfaces:**

- Consumes: a reviewed, clean `feature/uv-python-environment`; clean main and image-recipe worktrees; the exact commits from Tasks 1-3.
- Produces: a tested merge on `develop`, an image-recipe branch containing that merge, and a newly uv-managed `.venv` local to the image-recipe worktree.

- [ ] **Step 1: Run the feature-branch release gate before integration**

Run from `/home/many/yocto-rpi5-cam-firmware/.worktrees/uv-python-environment`:

```bash
test "$(git branch --show-current)" = "feature/uv-python-environment"
test -z "$(git status --porcelain)"
UV=/home/many/.local/bin/uv
test "$("$UV" --version | awk '{print $2}')" = "0.11.31"
test -z "${UV_PROJECT_ENVIRONMENT:-}"
"$UV" lock --check
"$UV" sync --locked
test -d .venv
test ! -L .venv
test "$(realpath .venv)" = "$(pwd -P)/.venv"
"$UV" run --locked python -c \
  'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; assert pathlib.Path(sys.prefix).resolve() == expected; assert sys.version_info[:2] == (3, 12)'
"$UV" run --locked kas --version
"$UV" run --locked python -m unittest discover -s tests/host -p 'test_*.py' -v
git diff --exit-code
git log --oneline --decorate -5
```

Expected: exact uv and kas versions, the feature-worktree `.venv` prefix,
all tests passing, no diff, and the design, plan, environment, design-doc,
and firmware-plan commits visible in history.

- [ ] **Step 2: Verify both receiving worktrees are clean**

Run:

```bash
git -C /home/many/yocto-rpi5-cam-firmware status --short --branch
git -C /home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation status --short --branch
git -C /home/many/yocto-rpi5-cam-firmware worktree list
```

Expected:

- the main checkout has no uncommitted paths;
- the implementation worktree is on `feature/image-recipes` with no
  uncommitted tracked or untracked paths;
- no worktree currently has `develop` checked out.

If either status contains a path, stop before switching or merging and
preserve that work as user-owned state.

- [ ] **Step 3: Merge the reviewed uv branch into `develop` in a dedicated integration worktree**

Run:

```bash
git -C /home/many/yocto-rpi5-cam-firmware worktree add /home/many/yocto-rpi5-cam-firmware/.worktrees/uv-develop-integration develop
git -C /home/many/yocto-rpi5-cam-firmware/.worktrees/uv-develop-integration merge --no-ff feature/uv-python-environment -m "build: merge uv Python environment"
```

Expected: a non-fast-forward English Conventional Commit-style merge is
created on `develop` without conflicts.

- [ ] **Step 4: Validate the merged `develop` state with its own `.venv`**

Run from
`/home/many/yocto-rpi5-cam-firmware/.worktrees/uv-develop-integration`:

```bash
UV=/home/many/.local/bin/uv
test "$("$UV" --version | awk '{print $2}')" = "0.11.31"
test -z "${UV_PROJECT_ENVIRONMENT:-}"
"$UV" lock --check
"$UV" sync --locked
test -d .venv
test ! -L .venv
test "$(realpath .venv)" = "$(pwd -P)/.venv"
"$UV" run --locked python -c \
  'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; assert pathlib.Path(sys.prefix).resolve() == expected; assert sys.version_info[:2] == (3, 12)'
"$UV" run --locked kas --version
"$UV" run --locked python -m unittest discover -s tests/host -p 'test_*.py' -v
test -z "$(git status --porcelain)"
```

Expected: the merge is clean, its environment is local to the integration
worktree, kas is 5.4, and every host test passes.

- [ ] **Step 5: Incorporate `develop` into the pending image-recipe feature**

Run:

```bash
git -C /home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation merge --no-ff develop -m "build: integrate uv Python environment"
```

Expected: `feature/image-recipes` receives the uv project and tests without
changing its reviewed image recipes or Yocto pins.

- [ ] **Step 6: Resolve and validate the exact legacy environment target before deletion**

Run:

```bash
readonly legacy_venv="/home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation/.venv"
readonly legacy_cfg="$legacy_venv/pyvenv.cfg"
[[ -d "$legacy_venv" && ! -L "$legacy_venv" ]]
test "$(realpath -- "$legacy_venv")" = "$legacy_venv"
test -f "$legacy_cfg"
test ! -L "$legacy_cfg"
grep -Fqx 'home = /usr/bin' "$legacy_cfg"
grep -Fqx 'include-system-site-packages = false' "$legacy_cfg"
grep -Fqx 'version = 3.12.3' "$legacy_cfg"
grep -Fqx 'executable = /usr/bin/python3.12' "$legacy_cfg"
grep -Fqx 'command = /usr/bin/python3 -m venv --without-pip /home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation/.venv' "$legacy_cfg"
if find "$legacy_venv" -xdev ! -user "$(id -un)" -print -quit | grep -q .; then
    printf 'legacy environment contains an entry not owned by %s\n' "$(id -un)" >&2
    exit 1
fi
while IFS= read -r mount_target; do
    if [[ "$mount_target" == "$legacy_venv" || "$mount_target" == "$legacy_venv/"* ]]; then
        printf 'mount exists at or below legacy environment: %s\n' "$mount_target" >&2
        exit 1
    fi
done < <(findmnt -rn -o TARGET)
```

Expected:

- `realpath` is exactly the fixed `.venv` path above;
- every `pyvenv.cfg` provenance line exactly matches the approved legacy
  `/usr/bin/python3 -m venv --without-pip` flow;
- the target and all entries are owned by the current intended user;
- the target is neither a symlink nor a mount point, and no descendant is a
  mount point.

- [ ] **Step 7: Delete only the verified legacy environment and recreate it with uv**

Run exactly:

```bash
readonly legacy_venv="/home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation/.venv"
readonly legacy_cfg="$legacy_venv/pyvenv.cfg"
[[ -d "$legacy_venv" && ! -L "$legacy_venv" ]]
test "$(realpath -- "$legacy_venv")" = "$legacy_venv"
test -f "$legacy_cfg"
test ! -L "$legacy_cfg"
grep -Fqx 'home = /usr/bin' "$legacy_cfg"
grep -Fqx 'include-system-site-packages = false' "$legacy_cfg"
grep -Fqx 'version = 3.12.3' "$legacy_cfg"
grep -Fqx 'executable = /usr/bin/python3.12' "$legacy_cfg"
grep -Fqx 'command = /usr/bin/python3 -m venv --without-pip /home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation/.venv' "$legacy_cfg"
if find "$legacy_venv" -xdev ! -user "$(id -un)" -print -quit | grep -q .; then
    exit 1
fi
while IFS= read -r mount_target; do
    if [[ "$mount_target" == "$legacy_venv" || "$mount_target" == "$legacy_venv/"* ]]; then
        exit 1
    fi
done < <(findmnt -rn -o TARGET)
rm -r --one-file-system -- "$legacy_venv"
test ! -e "$legacy_venv"
cd /home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation
UV=/home/many/.local/bin/uv
test "$("$UV" --version | awk '{print $2}')" = "0.11.31"
test -z "${UV_PROJECT_ENVIRONMENT:-}"
"$UV" lock --check
"$UV" sync --locked
test -d .venv
test ! -L .venv
test "$(realpath .venv)" = "$(pwd -P)/.venv"
"$UV" run --locked python -c \
  'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; assert pathlib.Path(sys.prefix).resolve() == expected; assert sys.version_info[:2] == (3, 12)'
```

Expected:

- the old generated environment is permanently removed, but it contains no
  source and is reproducible from the committed project files;
- no `build/`, `downloads/`, `sstate-cache/`, checkout, or artifact path is
  removed;
- uv creates a new `.venv` at the same worktree-local path using the locked
  dependency graph.

- [ ] **Step 8: Validate the new image-worktree environment and Task 4 source**

Run from
`/home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation`:

```bash
UV=/home/many/.local/bin/uv
test "$("$UV" --version | awk '{print $2}')" = "0.11.31"
test -z "${UV_PROJECT_ENVIRONMENT:-}"
"$UV" lock --check
test -d .venv
test ! -L .venv
test "$(realpath .venv)" = "$(pwd -P)/.venv"
"$UV" run --locked python -c \
  'import pathlib, sys; expected = pathlib.Path.cwd().resolve() / ".venv"; assert pathlib.Path(sys.prefix).resolve() == expected; assert sys.version_info[:2] == (3, 12)'
"$UV" run --locked python -c 'import importlib.metadata as metadata; assert metadata.version("kas") == "5.4"'
"$UV" run --locked kas dump kas/qemuarm64-minimal.yml
"$UV" run --locked kas dump kas/rpi5-minimal.yml
"$UV" run --locked kas dump kas/rpi5-camera.yml
"$UV" run --locked python -m unittest discover -s tests/host -p 'test_*.py' -v
git diff --check
git status --short --branch
```

Expected:

- all three kas configurations dump successfully with their existing pins;
- every offline host test, including the Task 4 image contract, passes;
- `.venv` is absent from status and the branch is clean;
- no live BitBake parse is claimed here because the separately recorded
  Ubuntu AppArmor user-namespace restriction remains outside this change.

- [ ] **Step 9: Record the integrated revisions and stop at the existing AppArmor gate**

Run:

```bash
git -C /home/many/yocto-rpi5-cam-firmware/.worktrees/uv-develop-integration log -1 --oneline
git -C /home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation log -2 --oneline
git -C /home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation merge-base --is-ancestor develop HEAD
```

Expected: the `develop` uv merge and image-branch integration merge are
visible, and `develop` is an ancestor of `feature/image-recipes`. Resume the
pending live BitBake parse only after the approved administrator-side
AppArmor change; do not modify AppArmor or sysctl as part of this plan.

## Plan Completion Criteria

- `pyproject.toml`, `.python-version`, and uv-generated `uv.lock` are tracked
  together; `requirements-build.txt` is absent.
- uv is exactly 0.11.31, only system Python 3.12 is used, and kas is exactly
  5.4.
- Each active checkout/worktree uses its own ignored root-level `.venv`.
- The verified legacy implementation-worktree environment has been deleted
  and recreated by `uv sync --locked`.
- Static repository, lockfile, and documentation contracts pass.
- Every active environment gate rejects `UV_PROJECT_ENVIRONMENT`, symlinked
  `.venv`, and a physical path or `sys.prefix` outside the checkout.
- Privileged flashing accepts only the pinned official uv archive, verifies
  a root-private copy before safe extraction, and never executes a
  user-selected path; the spoofed-executable negative test remains enforced.
- Legacy-environment deletion is limited to the fixed literal target after
  exact provenance, ownership, realpath, symlink, and mount checks, and uses
  one-filesystem removal.
- Canonical design, implementation plan, future scripts, runbooks, and CI
  contain no activation, pip setup, use of the legacy requirements file, or
  direct documented Python/kas execution; contract tests may name the file
  only to assert its absence.
- The uv feature is merged to `develop`, then merged into
  `feature/image-recipes`, with both receiving states clean and tested.
- Yocto pins, image behavior, hardware gates, caches, and AppArmor policy are
  unchanged.
