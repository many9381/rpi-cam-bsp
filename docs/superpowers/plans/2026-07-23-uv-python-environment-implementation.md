# uv-Managed Python Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the repository's hand-built Python virtual environment and `requirements-build.txt` with a reproducible uv project whose Python 3.12 environment is created as `.venv` in each checkout or worktree.

**Architecture:** `pyproject.toml` owns the direct build-tool contract, while the committed uv-generated `uv.lock` owns the complete resolved dependency graph. Repository tests validate the static contract with Python's standard library, and all documented Python and kas execution goes through `uv run --locked` without shell activation. The uv feature is reviewed on `feature/uv-python-environment`, merged into `develop`, and then incorporated into the in-progress `feature/image-recipes` worktree before that work resumes.

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
- Keep `.venv/` ignored and use uv's default worktree-local `.venv` beside `pyproject.toml`.
- Do not activate `.venv`, call `.venv/bin/*`, use pip, use `uv pip install`, or run documented Python/kas commands outside `uv run --locked`.
- Before the uv project exists, only the migration plan's baseline and red-state checks may use the already-installed system `python3`; all steady-state repository workflows use uv.
- Install uv itself as a host prerequisite; do not vendor the uv binary or add it to `.venv`.
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
| `tests/host/test_uv_docs_contract.py` | Create | Reject legacy activation, pip setup, and direct Python/kas execution in canonical build documentation. |
| `docs/superpowers/specs/2026-07-22-rpi5-yocto-build-validation-design.md` | Modify | Express host setup, checkout, parse, build, and QEMU commands using locked uv execution. |
| `docs/superpowers/plans/2026-07-22-rpi5-yocto-firmware-implementation.md` | Modify | Make every planned host script, runbook, CI flow, test command, and kas invocation conform to the uv contract. |

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
if ! command -v uv >/dev/null 2>&1 || [[ "$(uv --version)" != "uv 0.11.31" ]]; then
    curl -LsSf https://astral.sh/uv/0.11.31/install.sh |
        env UV_NO_MODIFY_PATH=1 UV_INSTALL_DIR=/home/many/.local/bin sh
    export PATH="/home/many/.local/bin:$PATH"
fi
command -v uv
uv --version
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
uv lock
uv lock --check
uv sync --locked
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
uv run --locked python -c 'import pathlib, sys; assert pathlib.Path(sys.prefix).resolve() == pathlib.Path(".venv").resolve()'
uv run --locked python -c 'import importlib.metadata as metadata; assert metadata.version("kas") == "5.4"'
uv run --locked kas --version
uv run --locked python -m unittest discover -s tests/host -p 'test_*.py' -v
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
uv lock --check
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
    r"(^\s*|(?:&&|\|\||;|\||\$\()\s*)(?:python3?|kas)(?=\s)"
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
uv run --locked python -m unittest discover -s tests/host -p 'test_uv_docs_contract.py' -v
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
uv --version
uv lock --check
uv sync --locked
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
uv run --locked python -m unittest discover -s tests/host -p 'test_uv_docs_contract.py' -v
uv run --locked python -m unittest discover -s tests/host -p 'test_*.py' -v
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
    r"(^\s*|(?:&&|\|\||;|\||\$\()\s*)(?:python3?|kas)(?=\s)"
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
uv run --locked python -m unittest discover -s tests/host -p 'test_uv_docs_contract.py' -v
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
if ! command -v uv >/dev/null 2>&1 || [[ "$(uv --version)" != "uv 0.11.31" ]]; then
    curl -LsSf https://astral.sh/uv/0.11.31/install.sh |
        env UV_NO_MODIFY_PATH=1 UV_INSTALL_DIR=/home/many/.local/bin sh
    export PATH="/home/many/.local/bin:$PATH"
fi
test "$(uv --version)" = "uv 0.11.31"
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
uv lock
uv lock --check
uv sync --locked
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
# tests/host/test_uv_environment_contract.py
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
uv lock --check
uv sync --locked
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
python_version="$(uv run --locked python -c 'import platform; print(platform.python_version())')"
version_ge "$python_version" "3.12" || rpi5_die "Python must be at least 3.12"
version_ge "3.12.999" "$python_version" || rpi5_die "Python must be below 3.13"
uv run --locked kas --version |
    grep -Eq '(^|[[:space:]])5\.4([[:space:]]|$)' ||
    rpi5_die "kas must be version 5.4"
```

In Task 6's `scripts/build.sh`, replace the entire action case with:

```bash
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

In Task 8's `scripts/flash-ssd.sh`, replace the block-device helper call with:

```bash
uv run --locked python "$helper" validate --topology "$topology" \
    --device "$target_device" --image-bytes "$image_bytes"
```

In Task 9's `scripts/discover-rpi5.sh`, replace its inline Python call with:

```bash
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
if ! command -v uv >/dev/null 2>&1 || [[ "$(uv --version)" != "uv 0.11.31" ]]; then
    curl -LsSf https://astral.sh/uv/0.11.31/install.sh |
        env UV_NO_MODIFY_PATH=1 UV_INSTALL_DIR=/home/many/.local/bin sh
    export PATH="/home/many/.local/bin:$PATH"
fi
uv lock --check
uv sync --locked
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
    if ! command -v uv >/dev/null 2>&1 || [[ "$(uv --version)" != "uv 0.11.31" ]]; then
        mkdir -p "$repo_root/.state/uv-bin"
        curl -LsSf https://astral.sh/uv/0.11.31/install.sh |
            env UV_NO_MODIFY_PATH=1 UV_INSTALL_DIR="$repo_root/.state/uv-bin" sh
        export PATH="$repo_root/.state/uv-bin:$PATH"
    fi
    [[ "$(uv --version)" == "uv 0.11.31" ]] ||
        rpi5_die "uv must be version 0.11.31"
    cd "$repo_root"
    uv lock --check
    uv sync --locked
    uv run --locked python -c 'import sys; assert sys.version_info[:2] == (3, 12)'
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
        self.assertIn('[[ "$(uv --version)" == "uv 0.11.31" ]]', script)
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

- [ ] **Step 9: Run the documentation contract and inspect every remaining direct command**

Run:

```bash
uv run --locked python -m unittest discover -s tests/host -p 'test_uv_docs_contract.py' -v
uv run --locked python -m unittest discover -s tests/host -p 'test_*.py' -v
rg -n 'python3 -m venv|\.venv/bin/activate|pip install|uv pip install' docs/superpowers/specs/2026-07-22-rpi5-yocto-build-validation-design.md docs/superpowers/plans/2026-07-22-rpi5-yocto-firmware-implementation.md
rg -n 'Create: `requirements-build\.txt`|# requirements-build\.txt|git add .*requirements-build\.txt' docs/superpowers/plans/2026-07-22-rpi5-yocto-firmware-implementation.md
git diff --check
```

Expected:

- both documentation tests pass;
- the complete host suite passes;
- both `rg` commands exit `1` with no matches;
- `git diff --check` reports no errors.

- [ ] **Step 10: Review the large plan diff by semantic area**

Run:

```bash
git diff --stat
git diff -- docs/superpowers/plans/2026-07-22-rpi5-yocto-firmware-implementation.md
git status --short
```

Expected:

- only the uv documentation test and canonical firmware plan are changed in
  this task;
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
test "$(uv --version)" = "uv 0.11.31"
uv lock --check
uv sync --locked
uv run --locked python -c 'import pathlib, sys; assert pathlib.Path(sys.prefix).resolve() == pathlib.Path(".venv").resolve()'
uv run --locked kas --version
uv run --locked python -m unittest discover -s tests/host -p 'test_*.py' -v
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
uv lock --check
uv sync --locked
uv run --locked python -c 'import pathlib, sys; assert pathlib.Path(sys.prefix).resolve() == pathlib.Path(".venv").resolve()'
uv run --locked kas --version
uv run --locked python -m unittest discover -s tests/host -p 'test_*.py' -v
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
test -d /home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation/.venv
test -f /home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation/.venv/pyvenv.cfg
realpath /home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation/.venv
sed -n '1,120p' /home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation/.venv/pyvenv.cfg
test "$(realpath /home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation/.venv)" = "/home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation/.venv"
```

Expected:

- `realpath` is exactly the fixed `.venv` path above;
- `pyvenv.cfg` identifies a Python 3.12 environment created by the legacy
  `/usr/bin/python3 -m venv --without-pip` flow;
- the target is neither a symlink to another worktree nor a parent
  directory.

- [ ] **Step 7: Delete only the verified legacy environment and recreate it with uv**

Run exactly:

```bash
rm -r -- /home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation/.venv
test ! -e /home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation/.venv
cd /home/many/yocto-rpi5-cam-firmware/.worktrees/yocto-implementation
uv lock --check
uv sync --locked
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
test "$(uv --version)" = "uv 0.11.31"
uv lock --check
uv run --locked python -c 'import pathlib, sys; assert pathlib.Path(sys.prefix).resolve() == pathlib.Path(".venv").resolve()'
uv run --locked python -c 'import importlib.metadata as metadata; assert metadata.version("kas") == "5.4"'
uv run --locked kas dump kas/qemuarm64-minimal.yml
uv run --locked kas dump kas/rpi5-minimal.yml
uv run --locked kas dump kas/rpi5-camera.yml
uv run --locked python -m unittest discover -s tests/host -p 'test_*.py' -v
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
- Canonical design, implementation plan, future scripts, runbooks, and CI
  contain no activation, pip setup, use of the legacy requirements file, or
  direct documented Python/kas execution; contract tests may name the file
  only to assert its absence.
- The uv feature is merged to `develop`, then merged into
  `feature/image-recipes`, with both receiving states clean and tested.
- Yocto pins, image behavior, hardware gates, caches, and AppArmor policy are
  unchanged.
