# Raspberry Pi 5 Yocto Firmware Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build reproducible Yocto 6.0 LTS images for `qemuarm64` and Raspberry Pi 5, validate the common ARM64 userspace in QEMU, boot Raspberry Pi 5 from USB SSD without UART, and validate Camera Module 3 Wide (`IMX708`) remotely.

**Architecture:** A pinned `kas` configuration composes split Yocto 6.0 repositories with a focused `meta-rpi5-cam` layer. Host-side scripts enforce build gates, evidence capture, safe SSD flashing, remote discovery, three-reboot hardware acceptance, and camera capture acceptance; QEMU and real-hardware results remain separate. The native developer path is a non-package uv project pinned to uv 0.11.31,
system Python 3.12, and `kas==5.4`; the provider-neutral CI entry point
bootstraps that same uv version inside an OCI image pinned by digest.

**Tech Stack:** Yocto Project 6.0 LTS (`wrynose`), BitBake 2.18, OpenEmbedded-Core, `meta-yocto`, `meta-raspberrypi`, `meta-openembedded`, kas 5.4, Bash 5, Python 3.12 standard-library `unittest`, systemd, OpenSSH, QEMU AArch64, bmaptool, libcamera/rpicam-apps, libav/libx264.

## Global Constraints

- The build host is x86_64 Ubuntu 24.04.4 LTS with 16 logical CPUs, 35 GiB RAM, 8 GiB swap, and 227 GiB free workspace capacity at the approved baseline.
- Use Yocto Project 6.0 LTS `wrynose`; do not use the legacy combined `poky` repository.
- Pin `kas==5.4` and keep both the compatible branch name and exact 40-character commit for every external repository.
- Manage native Python tools only through `pyproject.toml` and committed `uv.lock`; do not create a requirements compatibility file.
- Require system Python `>=3.12,<3.13`, uv `0.11.31`, and a worktree-local ignored `.venv`.
- Use `uv lock --check`, `uv sync --locked`, and `uv run --locked`; never activate `.venv`, call pip, or invoke native Python/kas outside uv.
- Change native build dependencies only with `uv add --group build PACKAGE` or `uv remove --group build PACKAGE`, and commit `pyproject.toml` and `uv.lock` together.
- Pin BitBake `2.18` to `fae9db3168dbff1b8c76fe9c6726a9687ff97514`.
- Pin OpenEmbedded-Core `wrynose` to `b5a6cada82d7ffb362bda9081c354dcc0b6ee264`.
- Pin `meta-yocto` `wrynose` to `824795b885b25e074a2880fbcd54e1a6c875d47d`.
- Pin `meta-openembedded` `wrynose` to `d97b5602d7f64422c94b7311466cda7f6b1962d5`.
- Pin `meta-raspberrypi` `wrynose` to `f62c67921474370829d24a4fa01ef88543f3906b`.
- Use `qemuarm64` only for common AArch64 userspace validation; Raspberry Pi 5 boot firmware, RP1, USB SSD, Ethernet, and IMX708 are real-hardware gates.
- Use `raspberrypi5`, `BOOT_MEDIA = "usb"`, and `CMDLINE_ROOT_PARTITION = "/dev/sda2"`; phase 1 assumes one USB SSD is attached.
- Use wired Ethernet DHCP, mDNS-first discovery, the `rpiadmin` account, SSH public-key authentication only, locked passwords, and disabled root SSH login.
- Do not enable `debug-tweaks`, `allow-empty-password`, `empty-root-password`, `allow-root-login`, or serial root autologin.
- UART is excluded. HDMI and a USB keyboard are used only after five minutes without any network signal.
- The normal hardware acceptance path must require no local input after power-on and must pass three consecutive remote reboot cycles.
- Camera Module 3 Wide uses IMX708, `RASPBERRYPI_CAMERA_V3 = "1"`, headless `rpicam-*` commands, and software H.264 via libav/libx264.
- `commercial` license flags are accepted only in the camera development image; external distribution requires a recorded GPL and product-license review.
- Store build outputs and logs outside Git. Commit configuration, scripts, tests, lock data, checksums, and compact result summaries only.
- Stop scheduling new BitBake tasks below 10 GiB free and halt immediately below 5 GiB free; do not start a fresh build below 20 GiB free.
- Flash only an explicitly named whole USB block device through bmaptool. Never implement an automatic `dd` fallback.
- A Raspberry Pi image may be flashed only when its build ID has a passing QEMU result and matching checksums, manifests, and layer revisions.
- Do not add Wi-Fi provisioning, a GUI, OTA/A-B updates, secure boot, disk encryption, streaming, or automatic root-partition expansion in this implementation.
- Use `develop` as the integration branch and create one `feature/SCOPE` branch from `develop` for each independently reviewable task.
- Make commits at functional boundaries, keep each commit independently testable, and write every commit subject in English using Conventional Commit prefixes.

---

## Implementation Notes and Deliberate Deviations

Yocto 6.0 `testimage.bbclass` requires `allow-empty-password`, `empty-root-password`, and `allow-root-login` for its built-in QEMU target. Those features directly violate the approved key-only and no-root-login policy. Therefore runtime acceptance is implemented by `scripts/test-qemu.sh`, which launches `runqemu ... slirp` and tests port `127.0.0.1:2222` using the same private key used for real hardware. `tests/oeqa/README.md` records this decision so the security policy is not silently weakened.

The approved design named `kas/lock.yml`. This plan keeps that name and includes it explicitly after `kas/base.yml`; its `overrides.repos` section is the single canonical commit-pin set. A lock update changes all five repositories together and reruns every gate.

No Git remote is configured at plan time. CI is therefore provider-neutral: `ci/pipeline.sh` is the pipeline contract, and the CI service must run it inside the exact OCI image declared in `ci/container.env`. Provider-specific YAML is intentionally absent because adding one would invent an unselected hosting platform.

## Git Branch and Commit Workflow

For each numbered task, start from an up-to-date `develop` branch, create the exact feature branch named in that task, complete its red-green verification cycle, and commit the tested functional unit with the English subject shown in the task. Merge only a passing feature branch back into `develop`; do not develop directly on `master` or `develop`.

```bash
git switch develop
git switch -c feature/repository-guardrails
# Task 1: implement and verify the repository guardrail unit
git add .gitignore .python-version pyproject.toml uv.lock keys/README.md artifacts/README.md tests
git commit -m "chore: add uv-managed Yocto workspace guardrails"
git switch develop
git merge --no-ff feature/repository-guardrails
```

Delete a feature branch only after its merge commit and verification are both present on `develop`. Reserve `master` for reviewed release baselines; promoting `develop` to `master` is outside the individual feature tasks and happens only after the complete phase acceptance gate.

## File Map

| Path | Responsibility |
|---|---|
| `.gitignore` | Exclude build trees, caches, private/public deployment keys, and large evidence while allowing compact release summaries. |
| `pyproject.toml` | Pin the non-package uv project, system Python range, uv version, and native `kas==5.4` build group. |
| `uv.lock` | Lock the complete native Python dependency graph generated by uv. |
| `.python-version` | Select the system Python 3.12 line for every checkout and worktree. |
| `kas/base.yml` | Declare split Yocto repositories, common layer/config policy, shared cache locations, and build metadata settings. |
| `kas/lock.yml` | Override all external repositories with the approved exact commits. |
| `kas/qemuarm64-minimal.yml` | Select `qemuarm64`, the minimal image, ext4 output, and localhost-only SLIRP SSH forwarding. |
| `kas/rpi5-minimal.yml` | Select `raspberrypi5`, USB boot, `/dev/sda2`, Wic+bmap output, and the minimal hostname. |
| `kas/rpi5-camera.yml` | Add multimedia layers, IMX708, libav/libx264, camera image, and the camera hostname. |
| `meta-rpi5-cam/conf/layer.conf` | Register the custom layer for `wrynose`. |
| `meta-rpi5-cam/recipes-core/device-config/device-config.bb` | Create `rpiadmin`, inject its public key and build ID, and install network, SSH, sudo, and journal policy. |
| `meta-rpi5-cam/recipes-core/device-config/files/*` | Hold target configuration files with no host-specific secrets. |
| `meta-rpi5-cam/recipes-core/images/rpi5-minimal-image.bb` | Define the common headless userspace and lock root authentication. |
| `meta-rpi5-cam/recipes-core/images/rpi5-camera-image.bb` | Extend the minimal image only with IMX708 capture and file-inspection packages. |
| `scripts/lib/common.sh` | Supply shared build-ID, key, path, and error helpers. |
| `scripts/lib/remote.sh` | Supply consistent SSH/SCP options and bounded wait operations. |
| `scripts/lib/block_device.py` | Pure, unit-tested USB block-device topology and safety validation. |
| `scripts/new-build-id.sh` | Generate one immutable evidence/build identifier for a complete gate run. |
| `scripts/host-preflight.sh` | Check host architecture, OS, resources, packages, locale, permissions, and key validity. |
| `scripts/build.sh` | Map profiles to kas files/build dirs and enforce QEMU/phase-1 gates. |
| `scripts/collect-artifacts.sh` | Copy immutable deploy outputs and metadata into `artifacts/BUILD_ID/`. |
| `scripts/test-qemu-guest.sh` | Run key-only SSH assertions against an already running QEMU guest. |
| `scripts/test-qemu.sh` | Launch/stop QEMU, capture console output, and write the QEMU PASS marker. |
| `scripts/flash-ssd.sh` | Validate, confirm, write, and read-only verify a USB SSD. |
| `scripts/discover-rpi5.sh` | Resolve mDNS, previous IP, or an optional dnsmasq lease file and return one SSH-ready IP. |
| `scripts/test-rpi5.sh` | Execute initial hardware checks and three reboot/recovery cycles. |
| `scripts/test-camera.sh` | Validate IMX708, JPEG, software-H.264, retrieval, and post-reboot capture. |
| `tests/host/*.py` | Exercise repository contracts and pure host-side safety logic without hardware. |
| `tests/oeqa/README.md` | Explain why built-in testimage is not enabled under the approved security policy. |
| `keys/README.md` | Document local key generation and permissions; key material remains untracked. |
| `artifacts/README.md` | Define evidence layout, retention, and what may be committed. |
| `docs/runbooks/*.md` | Give exact operator sequences for build/QEMU, SSD, remote Pi, camera, and EEPROM recovery. |
| `docs/licensing/camera-h264.md` | Record development-only commercial flag scope and the release review gate. |
| `ci/container.env` | Pin kas version, kas-container checksum, and OCI image digest. |
| `ci/kas-container` | Vendor the official kas 5.4 wrapper exactly. |
| `ci/pipeline.sh` | Expose provider-neutral `unit`, `qemu`, and `rpi5-image` CI stages. |

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

### Task 2: Pinned kas Configuration Matrix

**Feature branch:** `feature/kas-configuration`

**Files:**
- Create: `kas/base.yml`
- Create: `kas/lock.yml`
- Create: `kas/qemuarm64-minimal.yml`
- Create: `kas/rpi5-minimal.yml`
- Create: `kas/rpi5-camera.yml`
- Create: `tests/host/test_kas_contract.py`

**Interfaces:**
- Consumes: the exact branch/SHA set in Global Constraints and a local layer named `meta-rpi5-cam`.
- Produces: three kas entry points with targets `rpi5-minimal-image`, `rpi5-minimal-image`, and `rpi5-camera-image`; all receive `RPI5_ADMIN_SSH_PUBKEY` and `RPI5_BUILD_ID` through the kas `env` allowlist.

- [ ] **Step 1: Create the feature branch**

```bash
git switch develop
git switch -c feature/kas-configuration
```

- [ ] **Step 2: Write the failing kas matrix tests**

```python
# tests/host/test_kas_contract.py
import unittest

import yaml

from support import REPO_ROOT


PINS = {
    "bitbake": ("2.18", "fae9db3168dbff1b8c76fe9c6726a9687ff97514"),
    "openembedded-core": ("wrynose", "b5a6cada82d7ffb362bda9081c354dcc0b6ee264"),
    "meta-yocto": ("wrynose", "824795b885b25e074a2880fbcd54e1a6c875d47d"),
    "meta-openembedded": ("wrynose", "d97b5602d7f64422c94b7311466cda7f6b1962d5"),
    "meta-raspberrypi": ("wrynose", "f62c67921474370829d24a4fa01ef88543f3906b"),
}


def load(name: str) -> dict:
    with (REPO_ROOT / "kas" / name).open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


class KasContractTest(unittest.TestCase):
    def test_branches_and_lock_commits_match(self) -> None:
        base = load("base.yml")
        lock = load("lock.yml")
        for repo, (branch, commit) in PINS.items():
            self.assertEqual(base["repos"][repo]["branch"], branch)
            self.assertEqual(lock["overrides"]["repos"][repo]["commit"], commit)

    def test_base_uses_split_repositories_and_shared_cache(self) -> None:
        base = load("base.yml")
        self.assertNotIn("poky", base["repos"])
        self.assertEqual(base["repos"]["bitbake"]["layers"], {})
        self.assertIn("meta", base["repos"]["openembedded-core"]["layers"])
        self.assertIn("meta-poky", base["repos"]["meta-yocto"]["layers"])
        conf = base["local_conf_header"]["base"]
        self.assertIn('DL_DIR = "${TOPDIR}/../downloads"', conf)
        self.assertIn('SSTATE_DIR = "${TOPDIR}/../sstate-cache"', conf)
        self.assertNotIn("debug-tweaks", conf)

    def test_qemu_profile_is_hardware_independent(self) -> None:
        data = load("qemuarm64-minimal.yml")
        self.assertEqual(data["machine"], "qemuarm64")
        self.assertEqual(data["target"], "rpi5-minimal-image")
        self.assertNotIn("repos", data)
        conf = data["local_conf_header"]["qemu"]
        self.assertIn("127.0.0.1:2222-:22", conf)

    def test_pi_profile_boots_from_usb_ssd(self) -> None:
        data = load("rpi5-minimal.yml")
        self.assertEqual(data["machine"], "raspberrypi5")
        self.assertIn(".", data["repos"]["meta-raspberrypi"]["layers"])
        conf = data["local_conf_header"]["rpi5-minimal"]
        self.assertIn('BOOT_MEDIA = "usb"', conf)
        self.assertIn('CMDLINE_ROOT_PARTITION = "/dev/sda2"', conf)
        self.assertIn('IMAGE_FSTYPES = "wic.bz2 wic.bmap"', conf)

    def test_camera_profile_enables_exact_dependencies(self) -> None:
        data = load("rpi5-camera.yml")
        self.assertEqual(
            set(data["repos"]["meta-openembedded"]["layers"]),
            {"meta-oe", "meta-python", "meta-multimedia"},
        )
        conf = data["local_conf_header"]["rpi5-camera"]
        for required in (
            'RASPBERRYPI_CAMERA_V3 = "1"',
            'PACKAGECONFIG:append:pn-libcamera-apps = " libav"',
            'PACKAGECONFIG:append:pn-rpidistro-ffmpeg = " x264"',
            'LICENSE_FLAGS_ACCEPTED += " commercial"',
        ):
            self.assertIn(required, conf)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the kas test and confirm it fails before manifests exist**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_kas_contract.py' -v`

Expected: `ERROR` with `FileNotFoundError: .../kas/base.yml`.

- [ ] **Step 4: Create the common manifest and explicit lock file**

```yaml
# kas/base.yml
header:
  version: 19

build_system: openembedded
distro: poky
target: rpi5-minimal-image

repos:
  bitbake:
    url: https://git.openembedded.org/bitbake
    branch: "2.18"
    layers: {}
  openembedded-core:
    url: https://git.openembedded.org/openembedded-core
    branch: wrynose
    layers:
      meta:
  meta-yocto:
    url: https://git.yoctoproject.org/meta-yocto
    branch: wrynose
    layers:
      meta-poky:
  meta-openembedded:
    url: https://github.com/openembedded/meta-openembedded.git
    branch: wrynose
    layers: {}
  meta-raspberrypi:
    url: https://github.com/agherzan/meta-raspberrypi.git
    branch: wrynose
    layers: {}
  meta-rpi5-cam:
    layers:
      meta-rpi5-cam:

env:
  RPI5_ADMIN_SSH_PUBKEY: null
  RPI5_BUILD_ID: null

local_conf_header:
  base: |
    CONF_VERSION = "2"
    INIT_MANAGER = "systemd"
    PACKAGE_CLASSES = "package_rpm"
    DL_DIR = "${TOPDIR}/../downloads"
    SSTATE_DIR = "${TOPDIR}/../sstate-cache"
    BB_DISKMON_DIRS = "\
        STOPTASKS,${TMPDIR},10G,100K \
        STOPTASKS,${DL_DIR},10G,100K \
        STOPTASKS,${SSTATE_DIR},10G,100K \
        HALT,${TMPDIR},5G,10K \
        HALT,${DL_DIR},5G,10K \
        HALT,${SSTATE_DIR},5G,10K"
    INHERIT += "buildhistory"
    BUILDHISTORY_COMMIT = "0"
    COPY_LIC_MANIFEST = "1"
    COPY_LIC_DIRS = "1"
    RM_OLD_IMAGE = "1"
    RPI5_ADMIN_SSH_PUBKEY ??= ""
    RPI5_BUILD_ID ??= "unversioned"
```

```yaml
# kas/lock.yml
header:
  version: 19

overrides:
  repos:
    bitbake:
      commit: fae9db3168dbff1b8c76fe9c6726a9687ff97514
    openembedded-core:
      commit: b5a6cada82d7ffb362bda9081c354dcc0b6ee264
    meta-yocto:
      commit: 824795b885b25e074a2880fbcd54e1a6c875d47d
    meta-openembedded:
      commit: d97b5602d7f64422c94b7311466cda7f6b1962d5
    meta-raspberrypi:
      commit: f62c67921474370829d24a4fa01ef88543f3906b
```

- [ ] **Step 5: Create the QEMU and Raspberry Pi profile manifests**

```yaml
# kas/qemuarm64-minimal.yml
header:
  version: 19
  includes:
    - kas/base.yml
    - kas/lock.yml

machine: qemuarm64
target: rpi5-minimal-image

local_conf_header:
  qemu: |
    IMAGE_FSTYPES = "ext4"
    QB_SLIRP_OPT = "-netdev user,id=net0,hostfwd=tcp:127.0.0.1:2222-:22"
```

```yaml
# kas/rpi5-minimal.yml
header:
  version: 19
  includes:
    - kas/base.yml
    - kas/lock.yml

machine: raspberrypi5
target: rpi5-minimal-image

repos:
  meta-raspberrypi:
    layers:
      .:

local_conf_header:
  rpi5-minimal: |
    IMAGE_FSTYPES = "wic.bz2 wic.bmap"
    WKS_FILE = "sdimage-raspberrypi.wks"
    BOOT_MEDIA = "usb"
    CMDLINE_ROOT_PARTITION = "/dev/sda2"
    hostname:pn-base-files = "rpi5-minimal"
```

```yaml
# kas/rpi5-camera.yml
header:
  version: 19
  includes:
    - kas/rpi5-minimal.yml

target: rpi5-camera-image

repos:
  meta-openembedded:
    layers:
      meta-oe:
      meta-python:
      meta-multimedia:

local_conf_header:
  rpi5-camera: |
    hostname:pn-base-files = "rpi5-camera"
    RASPBERRYPI_CAMERA_V3 = "1"
    PACKAGECONFIG:append:pn-libcamera-apps = " libav"
    PACKAGECONFIG:append:pn-rpidistro-ffmpeg = " x264"
    LICENSE_FLAGS_ACCEPTED += " commercial"
```

- [ ] **Step 6: Run offline schema/contract checks**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_kas_contract.py' -v`

Expected: `Ran 5 tests` followed by `OK`.

Run: `uv run --locked kas dump kas/qemuarm64-minimal.yml >/tmp/rpi5-qemu-kas-dump.yml`

Expected: exit code `0`; the dump has `machine: qemuarm64` and all five lock commits.

Run: `uv run --locked kas dump kas/rpi5-camera.yml >/tmp/rpi5-camera-kas-dump.yml`

Expected: exit code `0`; the dump has `machine: raspberrypi5`, target `rpi5-camera-image`, and exactly the three `meta-openembedded` layers.

- [ ] **Step 7: Commit the kas matrix**

```bash
git add kas tests/host/test_kas_contract.py
git commit -m "build: pin Yocto kas configuration matrix"
```

### Task 3: Secure Device Configuration Layer

**Feature branch:** `feature/secure-device-config`

**Files:**
- Create: `meta-rpi5-cam/conf/layer.conf`
- Create: `meta-rpi5-cam/recipes-core/device-config/device-config.bb`
- Create: `meta-rpi5-cam/recipes-core/device-config/files/20-wired.network`
- Create: `meta-rpi5-cam/recipes-core/device-config/files/sshd_config.d-rpi5.conf`
- Create: `meta-rpi5-cam/recipes-core/device-config/files/journald.conf.d-rpi5.conf`
- Create: `meta-rpi5-cam/recipes-core/device-config/files/rpi5-admin-sudoers`
- Create: `tests/host/test_layer_contract.py`

**Interfaces:**
- Consumes: BitBake variables `RPI5_ADMIN_SSH_PUBKEY: str` and `RPI5_BUILD_ID: str` forwarded by kas.
- Produces: package `device-config`, user `rpiadmin`, `/home/rpiadmin/.ssh/authorized_keys`, `/etc/rpi5-build-id`, wired DHCP, persistent journal, SSH key-only policy, and a limited sudo command set.

- [ ] **Step 1: Create the feature branch**

```bash
git switch develop
git switch -c feature/secure-device-config
```

Expected: `git branch --show-current` prints `feature/secure-device-config`.

- [ ] **Step 2: Write the failing layer and security-policy tests**

```python
# tests/host/test_layer_contract.py
import unittest

from support import read


class LayerContractTest(unittest.TestCase):
    def test_layer_targets_only_wrynose(self) -> None:
        layer = read("meta-rpi5-cam/conf/layer.conf")
        self.assertIn('LAYERSERIES_COMPAT_rpi5cam = "wrynose"', layer)
        self.assertIn('LAYERDEPENDS_rpi5cam = "core"', layer)

    def test_device_recipe_creates_locked_admin_and_injects_key(self) -> None:
        recipe = read(
            "meta-rpi5-cam/recipes-core/device-config/device-config.bb"
        )
        self.assertIn("inherit useradd", recipe)
        self.assertIn("--password '!' rpiadmin", recipe)
        self.assertIn("RPI5_ADMIN_SSH_PUBKEY", recipe)
        self.assertIn("authorized_keys", recipe)
        self.assertIn("RPI5_BUILD_ID", recipe)
        self.assertNotIn("keys/rpi5_admin.pub", recipe)

    def test_sshd_policy_is_key_only_and_non_root(self) -> None:
        policy = read(
            "meta-rpi5-cam/recipes-core/device-config/files/"
            "sshd_config.d-rpi5.conf"
        )
        self.assertIn("PasswordAuthentication no", policy)
        self.assertIn("KbdInteractiveAuthentication no", policy)
        self.assertIn("PermitRootLogin no", policy)
        self.assertIn("AllowUsers rpiadmin", policy)

    def test_wired_network_uses_dhcp_and_mdns(self) -> None:
        network = read(
            "meta-rpi5-cam/recipes-core/device-config/files/20-wired.network"
        )
        self.assertIn("Name=eth* en*", network)
        self.assertIn("DHCP=yes", network)
        self.assertIn("MulticastDNS=yes", network)

    def test_sudo_does_not_grant_an_unbounded_shell(self) -> None:
        sudoers = read(
            "meta-rpi5-cam/recipes-core/device-config/files/rpi5-admin-sudoers"
        )
        self.assertNotIn("ALL=(ALL) NOPASSWD: ALL", sudoers)
        self.assertIn("/usr/bin/systemctl reboot", sudoers)
        self.assertIn("/usr/bin/systemctl poweroff", sudoers)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the layer test and confirm the missing-file failure**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_layer_contract.py' -v`

Expected: `ERROR` with `FileNotFoundError` under `meta-rpi5-cam/`.

- [ ] **Step 4: Register the custom layer**

```bitbake
# meta-rpi5-cam/conf/layer.conf
BBPATH .= ":${LAYERDIR}"
BBFILES += "${LAYERDIR}/recipes-*/*/*.bb ${LAYERDIR}/recipes-*/*/*.bbappend"

BBFILE_COLLECTIONS += "rpi5cam"
BBFILE_PATTERN_rpi5cam = "^${LAYERDIR}/"
BBFILE_PRIORITY_rpi5cam = "8"

LAYERDEPENDS_rpi5cam = "core"
LAYERSERIES_COMPAT_rpi5cam = "wrynose"
```

- [ ] **Step 5: Add the exact target configuration files**

```ini
# meta-rpi5-cam/recipes-core/device-config/files/20-wired.network
[Match]
Name=eth* en*

[Network]
DHCP=yes
IPv6AcceptRA=yes
MulticastDNS=yes
LLMNR=no

[DHCPv4]
RouteMetric=100
```

```text
# meta-rpi5-cam/recipes-core/device-config/files/sshd_config.d-rpi5.conf
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AuthenticationMethods publickey
AllowUsers rpiadmin
```

```ini
# meta-rpi5-cam/recipes-core/device-config/files/journald.conf.d-rpi5.conf
[Journal]
Storage=persistent
Compress=yes
SystemMaxUse=256M
RuntimeMaxUse=64M
```

```sudoers
# meta-rpi5-cam/recipes-core/device-config/files/rpi5-admin-sudoers
Cmnd_Alias RPI5_POWER = /usr/bin/systemctl reboot, /usr/bin/systemctl poweroff
Cmnd_Alias RPI5_DIAGNOSTICS = /usr/bin/journalctl -b --no-pager, /usr/bin/journalctl -b -1 --no-pager, /usr/bin/dmesg
rpiadmin ALL=(root) NOPASSWD: RPI5_POWER, RPI5_DIAGNOSTICS
```

- [ ] **Step 6: Add the device configuration recipe with build-time validation**

```bitbake
# meta-rpi5-cam/recipes-core/device-config/device-config.bb
SUMMARY = "Raspberry Pi 5 headless device policy"
DESCRIPTION = "Installs the rpiadmin account, SSH policy, wired network, persistent journal, sudo policy, and build identity."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = " \
    file://20-wired.network \
    file://sshd_config.d-rpi5.conf \
    file://journald.conf.d-rpi5.conf \
    file://rpi5-admin-sudoers \
"

S = "${UNPACKDIR}"

inherit useradd

USERADD_PACKAGES = "${PN}"
USERADD_PARAM:${PN} = "--uid 1000 --home-dir /home/rpiadmin \
    --create-home --shell /bin/sh --user-group --password '!' rpiadmin"

RPI5_ADMIN_SSH_PUBKEY ??= ""
RPI5_BUILD_ID ??= "unversioned"

do_install() {
    key_lines="$(printf '%s\n' "${RPI5_ADMIN_SSH_PUBKEY}" | wc -l)"
    if [ "$key_lines" -ne 1 ] || \
       ! printf '%s\n' "${RPI5_ADMIN_SSH_PUBKEY}" | \
         grep -Eq '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)) [A-Za-z0-9+/=]+( .*)?$'; then
        bbfatal "RPI5_ADMIN_SSH_PUBKEY must contain one valid OpenSSH public key"
    fi

    if ! printf '%s\n' "${RPI5_BUILD_ID}" | \
         grep -Eq '^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{7,40}$'; then
        bbfatal "RPI5_BUILD_ID must be UTC timestamp plus Git SHA"
    fi

    install -d -m 0700 ${D}/home/rpiadmin/.ssh
    printf '%s\n' "${RPI5_ADMIN_SSH_PUBKEY}" \
        > ${D}/home/rpiadmin/.ssh/authorized_keys
    chmod 0600 ${D}/home/rpiadmin/.ssh/authorized_keys
    chown -R rpiadmin:rpiadmin ${D}/home/rpiadmin

    install -d -m 0755 ${D}${sysconfdir}/systemd/network
    install -m 0644 ${UNPACKDIR}/20-wired.network \
        ${D}${sysconfdir}/systemd/network/20-wired.network

    install -d -m 0755 ${D}${sysconfdir}/ssh/sshd_config.d
    install -m 0600 ${UNPACKDIR}/sshd_config.d-rpi5.conf \
        ${D}${sysconfdir}/ssh/sshd_config.d/20-rpi5.conf

    install -d -m 0755 ${D}${sysconfdir}/systemd/journald.conf.d
    install -m 0644 ${UNPACKDIR}/journald.conf.d-rpi5.conf \
        ${D}${sysconfdir}/systemd/journald.conf.d/20-rpi5.conf
    install -d -m 2755 ${D}${localstatedir}/log/journal

    install -d -m 0750 ${D}${sysconfdir}/sudoers.d
    install -m 0440 ${UNPACKDIR}/rpi5-admin-sudoers \
        ${D}${sysconfdir}/sudoers.d/rpi5-admin

    printf '%s\n' "${RPI5_BUILD_ID}" > ${D}${sysconfdir}/rpi5-build-id
    chmod 0644 ${D}${sysconfdir}/rpi5-build-id
}

FILES:${PN} += " \
    /home/rpiadmin \
    ${sysconfdir}/rpi5-build-id \
    ${sysconfdir}/ssh/sshd_config.d/20-rpi5.conf \
    ${sysconfdir}/sudoers.d/rpi5-admin \
    ${sysconfdir}/systemd/journald.conf.d/20-rpi5.conf \
    ${sysconfdir}/systemd/network/20-wired.network \
    ${localstatedir}/log/journal \
"

CONFFILES:${PN} = " \
    ${sysconfdir}/ssh/sshd_config.d/20-rpi5.conf \
    ${sysconfdir}/sudoers.d/rpi5-admin \
    ${sysconfdir}/systemd/journald.conf.d/20-rpi5.conf \
    ${sysconfdir}/systemd/network/20-wired.network \
"

RDEPENDS:${PN} = "openssh-sshd sudo systemd-networkd"
```

- [ ] **Step 7: Run the layer tests and BitBake syntax checks**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_layer_contract.py' -v`

Expected: `Ran 5 tests` followed by `OK`.

Run: `uv run --locked kas shell kas/qemuarm64-minimal.yml -c 'bitbake-layers show-layers'`

Expected: exit code `0`; output contains `meta`, `meta-poky`, and `meta-rpi5-cam`, and does not list `meta-raspberrypi` or `meta-multimedia` as active layers.

- [ ] **Step 8: Commit the secure target configuration in English**

```bash
git add meta-rpi5-cam tests/host/test_layer_contract.py
git commit -m "feat: add secure headless device configuration"
```

Expected: one independently testable commit on `feature/secure-device-config`; merge it to `develop` with `git merge --no-ff feature/secure-device-config` after review.

### Task 4: Minimal and Camera Image Recipes

**Feature branch:** `feature/image-recipes`

**Files:**
- Create: `meta-rpi5-cam/recipes-core/images/rpi5-minimal-image.bb`
- Create: `meta-rpi5-cam/recipes-core/images/rpi5-camera-image.bb`
- Create: `tests/host/test_image_contract.py`

**Interfaces:**
- Consumes: package `device-config`, kas-selected machine/config variables, and camera recipes exposed by the multimedia dynamic layer.
- Produces: BitBake targets `rpi5-minimal-image` and `rpi5-camera-image`; the camera target is a strict extension of the minimal target.

- [ ] **Step 1: Create the feature branch from integrated device configuration**

```bash
git switch develop
git switch -c feature/image-recipes
```

Expected: `feature/image-recipes` contains the merged Task 3 commit.

- [ ] **Step 2: Write the failing image composition tests**

```python
# tests/host/test_image_contract.py
import unittest

from support import read


class ImageContractTest(unittest.TestCase):
    def test_minimal_image_has_remote_admin_and_no_debug_features(self) -> None:
        recipe = read(
            "meta-rpi5-cam/recipes-core/images/rpi5-minimal-image.bb"
        )
        for package in (
            "device-config",
            "systemd-networkd",
            "openssh-sftp-server",
            "avahi-daemon",
            "sudo",
            "iproute2",
            "util-linux",
            "procps",
            "ethtool",
        ):
            self.assertIn(package, recipe)
        self.assertIn("ssh-server-openssh", recipe)
        self.assertIn("usermod -p '!' root", recipe)
        self.assertIn('IMAGE_FEATURES:remove = "debug-tweaks', recipe)

    def test_camera_image_is_a_narrow_extension(self) -> None:
        recipe = read(
            "meta-rpi5-cam/recipes-core/images/rpi5-camera-image.bb"
        )
        self.assertIn("require rpi5-minimal-image.bb", recipe)
        for package in (
            "libcamera-apps",
            "libcamera",
            "v4l-utils",
            "media-ctl",
            "rpidistro-ffmpeg",
            "file",
        ):
            self.assertIn(package, recipe)
        for excluded in ("opencv", "tensorflow", "gstreamer", "weston", "qtbase"):
            self.assertNotIn(excluded, recipe.lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the image test and confirm the missing-file failure**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_image_contract.py' -v`

Expected: `ERROR` with `FileNotFoundError` for `rpi5-minimal-image.bb`.

- [ ] **Step 4: Add the common minimal image**

```bitbake
# meta-rpi5-cam/recipes-core/images/rpi5-minimal-image.bb
SUMMARY = "Headless Raspberry Pi 5 and QEMU validation image"
DESCRIPTION = "Minimal systemd image with wired DHCP, mDNS, key-only SSH, diagnostics, and persistent evidence."
LICENSE = "MIT"

IMAGE_INSTALL = " \
    packagegroup-core-boot \
    ${CORE_IMAGE_EXTRA_INSTALL} \
    device-config \
    systemd-networkd \
    openssh-sftp-server \
    avahi-daemon \
    sudo \
    iproute2 \
    util-linux \
    procps \
    ethtool \
"

IMAGE_FEATURES += "ssh-server-openssh"
IMAGE_FEATURES:remove = "debug-tweaks allow-empty-password empty-root-password allow-root-login serial-autologin-root"
IMAGE_LINGUAS = " "

IMAGE_ROOTFS_SIZE = "1048576"
IMAGE_ROOTFS_EXTRA_SPACE = "524288"

inherit core-image extrausers

EXTRA_USERS_PARAMS = "usermod -p '!' root;"
```

- [ ] **Step 5: Add the Camera Module 3 Wide image**

```bitbake
# meta-rpi5-cam/recipes-core/images/rpi5-camera-image.bb
SUMMARY = "Headless Raspberry Pi 5 Camera Module 3 Wide image"
DESCRIPTION = "Extends rpi5-minimal-image with IMX708 still capture and software H.264 recording."

require rpi5-minimal-image.bb

IMAGE_INSTALL:append = " \
    libcamera-apps \
    libcamera \
    v4l-utils \
    media-ctl \
    rpidistro-ffmpeg \
    file \
"

IMAGE_ROOTFS_SIZE = "4194304"
```

- [ ] **Step 6: Run offline image tests**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_image_contract.py' -v`

Expected: `Ran 2 tests` followed by `OK`.

- [ ] **Step 7: Parse all three configurations against the pinned upstream layers**

Run: `uv run --locked kas checkout kas/qemuarm64-minimal.yml`

Expected: all five external repositories resolve to the commits in `kas/lock.yml`.

Run: `uv run --locked kas shell kas/qemuarm64-minimal.yml -c 'bitbake -p'`

Expected: `Parsing of ... recipes complete` and exit code `0`.

Run: `uv run --locked kas shell kas/rpi5-minimal.yml -c 'bitbake -p'`

Expected: parse succeeds and `bitbake-layers show-layers` includes the root `meta-raspberrypi` layer.

Run: `uv run --locked kas shell kas/rpi5-camera.yml -c 'bitbake -p'`

Expected: parse succeeds with `meta-oe`, `meta-python`, `meta-multimedia`, and the Raspberry Pi multimedia dynamic layer active.

Run: `uv run --locked kas shell kas/rpi5-camera.yml -c 'bitbake -e libcamera-apps | grep "^PACKAGECONFIG="'`

Expected: the effective `PACKAGECONFIG` contains both `drm` and `libav`.

Run: `uv run --locked kas shell kas/rpi5-camera.yml -c 'bitbake -e rpidistro-ffmpeg | grep "^PACKAGECONFIG="'`

Expected: the effective `PACKAGECONFIG` contains `x264` and `gpl`.

- [ ] **Step 8: Commit the image definitions in English**

```bash
git add meta-rpi5-cam/recipes-core/images tests/host/test_image_contract.py
git commit -m "feat: define minimal and IMX708 camera images"
```

Expected: merge `feature/image-recipes` to `develop` only after all parse checks pass.

### Task 5: Host Preflight and Build Identity

**Feature branch:** `feature/host-preflight`

**Files:**
- Create: `scripts/lib/common.sh`
- Create: `scripts/new-build-id.sh`
- Create: `scripts/host-preflight.sh`
- Create: `tests/host/test_host_tools.py`

**Interfaces:**
- Consumes: repository state, `keys/rpi5_admin.pub`, Ubuntu host facts, and `--initial` or `--incremental` mode.
- Produces: build IDs matching `^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$`; preflight exits `0` only when every mandatory condition passes.

- [ ] **Step 1: Create the feature branch**

```bash
git switch develop
git switch -c feature/host-preflight
```

- [ ] **Step 2: Write failing unit and syntax tests**

```python
# tests/host/test_host_tools.py
import re
import unittest

from support import REPO_ROOT, read, run


class HostToolsTest(unittest.TestCase):
    def test_new_build_id_uses_utc_and_current_commit(self) -> None:
        result = run("bash", "scripts/new-build-id.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        build_id = result.stdout.strip()
        self.assertRegex(build_id, r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")
        sha = run("git", "rev-parse", "--short=12", "HEAD").stdout.strip()
        self.assertTrue(build_id.endswith(f"-{sha}"))

    def test_common_library_accepts_only_canonical_build_ids(self) -> None:
        good = run(
            "bash",
            "-c",
            "source scripts/lib/common.sh; "
            "rpi5_validate_build_id 20260722T120000Z-0123456789ab",
        )
        bad = run(
            "bash",
            "-c",
            "source scripts/lib/common.sh; rpi5_validate_build_id latest",
        )
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertNotEqual(bad.returncode, 0)

    def test_preflight_has_both_disk_modes_and_required_tools(self) -> None:
        script = read("scripts/host-preflight.sh")
        self.assertIn("--initial", script)
        self.assertIn("146800640", script)
        self.assertIn("--incremental", script)
        self.assertIn("20971520", script)
        for command in (
            "uv",
            "bmaptool",
            "qemu-system-aarch64",
            "avahi-resolve-host-name",
            "partprobe",
            "ffprobe",
        ):
            self.assertIn(command, script)

    def test_scripts_are_valid_bash(self) -> None:
        for path in (
            "scripts/lib/common.sh",
            "scripts/new-build-id.sh",
            "scripts/host-preflight.sh",
        ):
            result = run("bash", "-n", path)
            self.assertEqual(result.returncode, 0, f"{path}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm they fail on missing scripts**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_host_tools.py' -v`

Expected: failures mention `scripts/new-build-id.sh` and `scripts/host-preflight.sh`.

- [ ] **Step 4: Add shared validation helpers**

```bash
#!/usr/bin/env bash
# scripts/lib/common.sh

rpi5_repo_root() {
    cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P
}

rpi5_die() {
    printf 'ERROR: %s\n' "$*" >&2
    return 1
}

rpi5_require_cmd() {
    command -v "$1" >/dev/null 2>&1 || rpi5_die "required command not found: $1"
}

rpi5_validate_build_id() {
    [[ "${1:-}" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ ]]
}

rpi5_validate_key_pair() {
    local private_key="$1"
    local public_key="${private_key}.pub"
    [[ -f "$private_key" ]] || rpi5_die "private key missing: $private_key"
    [[ -f "$public_key" ]] || rpi5_die "public key missing: $public_key"
    [[ "$(wc -l < "$public_key")" -eq 1 ]] || \
        rpi5_die "public key must contain exactly one line"
    grep -Eq '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)) [A-Za-z0-9+/=]+( .*)?$' \
        "$public_key" || rpi5_die "unsupported public key format"
    ssh-keygen -l -f "$public_key" >/dev/null || rpi5_die "ssh-keygen rejected public key"
    [[ "$(stat -c '%a' "$private_key")" == "600" ]] || \
        rpi5_die "private key mode must be 600"
}

rpi5_require_pass() {
    local marker="$1"
    local label="$2"
    [[ -f "$marker" ]] || rpi5_die "$label PASS marker missing: $marker"
}
```

- [ ] **Step 5: Add immutable build-ID generation**

```bash
#!/usr/bin/env bash
# scripts/new-build-id.sh
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

repo_root="$(rpi5_repo_root)"
revision="$(git -C "$repo_root" rev-parse --short=12 HEAD)"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
printf '%s-%s\n' "$timestamp" "$revision"
```

- [ ] **Step 6: Add the host preflight implementation**

```bash
#!/usr/bin/env bash
# scripts/host-preflight.sh
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

usage() {
    printf 'Usage: %s [--initial|--incremental] [--key PATH]\n' "$0"
}

mode="--incremental"
key_path="$(rpi5_repo_root)/keys/rpi5_admin"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --initial|--incremental) mode="$1"; shift ;;
        --key) key_path="$2"; shift 2 ;;
        --help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

repo_root="$(rpi5_repo_root)"
cd "$repo_root"
minimum_disk_kib=20971520
[[ "$mode" == "--initial" ]] && minimum_disk_kib=146800640

[[ "$EUID" -ne 0 ]] || rpi5_die "BitBake must not run as root"
[[ "$(uname -m)" == "x86_64" ]] || rpi5_die "host architecture must be x86_64"

source /etc/os-release
[[ "$ID" == "ubuntu" && "$VERSION_ID" == "24.04" ]] || \
    rpi5_die "supported host is Ubuntu 24.04"
[[ "$(nproc)" -ge 4 ]] || rpi5_die "at least 4 logical CPUs are required"

memory_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
swap_kib="$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)"
[[ "$memory_kib" -ge 33554432 ]] || rpi5_die "at least 32 GiB RAM is required"
[[ "$swap_kib" -ge 4194304 ]] || rpi5_die "at least 4 GiB swap is required"

free_kib="$(df -Pk "$repo_root" | awk 'NR == 2 {print $4}')"
[[ "$free_kib" -ge "$minimum_disk_kib" ]] || \
    rpi5_die "insufficient free space: ${free_kib} KiB"
[[ -w "$repo_root" ]] || rpi5_die "repository is not writable"

locale -a | grep -Eiq '^en_US\.(utf-?8|UTF-?8)$' || \
    rpi5_die "en_US.UTF-8 locale is required"

required_commands=(
    git tar make gcc python3 uv
    bmaptool qemu-system-aarch64
    ssh scp ssh-keygen ssh-keyscan ss
    avahi-resolve-host-name ping
    lsblk findmnt blockdev partprobe udevadm
    mount umount sha256sum file ffprobe
)
for required in "${required_commands[@]}"; do
    rpi5_require_cmd "$required"
done

version_ge() {
    printf '%s\n%s\n' "$2" "$1" | sort -V -C
}

git_version="$(git --version | awk '{print $3}')"
tar_version="$(tar --version | awk 'NR == 1 {print $NF}')"
make_version="$(make --version | awk 'NR == 1 {print $3}')"
gcc_version="$(gcc -dumpfullversion -dumpversion)"
version_ge "$git_version" "1.8.3.1" || rpi5_die "Git is too old"
version_ge "$tar_version" "1.28" || rpi5_die "tar is too old"
version_ge "$make_version" "4.0" || rpi5_die "make is too old"
version_ge "$gcc_version" "8.0" || rpi5_die "GCC is too old"
uv_version="$(uv --version | awk '{print $2}')"
[[ "$uv_version" == "0.11.31" ]] || rpi5_die "uv must be version 0.11.31"
uv lock --check || rpi5_die "uv.lock is stale"
python_version="$(uv run --locked python -c 'import platform; print(platform.python_version())')"
version_ge "$python_version" "3.12" || rpi5_die "Python must be at least 3.12"
version_ge "3.12.999" "$python_version" || rpi5_die "Python must be below 3.13"
uv run --locked kas --version |
    grep -Eq '(^|[[:space:]])5\.4([[:space:]]|$)' ||
    rpi5_die "kas must be version 5.4"

rpi5_validate_key_pair "$key_path"

printf 'PASS host-preflight mode=%s cpus=%s memory_kib=%s swap_kib=%s free_kib=%s\n' \
    "$mode" "$(nproc)" "$memory_kib" "$swap_kib" "$free_kib"
```

- [ ] **Step 7: Make scripts executable and run offline tests**

Run: `chmod 0755 scripts/new-build-id.sh scripts/host-preflight.sh`

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_host_tools.py' -v`

Expected: `Ran 4 tests` followed by `OK`.

- [ ] **Step 8: Install Ubuntu host dependencies once and run preflight**

Run on the supported Ubuntu 24.04 host:

```bash
sudo apt-get update
sudo apt-get install -y build-essential chrpath cpio debianutils diffstat file gawk \
  gcc git iputils-ping libacl1 liblz4-tool locales make python3 python3-git \
  python3-jinja2 python3-pexpect python3-subunit socat \
  tar texinfo unzip wget xz-utils zstd bmap-tools qemu-system-arm openssh-client \
  avahi-utils curl ffmpeg iproute2 parted util-linux udev
sudo locale-gen en_US.UTF-8
swapon --show
```

Expected: the host has at least 4 GiB configured swap; if `swapon --show` is empty or undersized, use the organization's approved host provisioning procedure before continuing.

Run: `./scripts/host-preflight.sh --initial --key keys/rpi5_admin`

Expected: one line beginning `PASS host-preflight`. Only one-time package/locale provisioning uses administrator privileges; kas, BitBake, preflight, builds, and tests run as the normal user.

- [ ] **Step 9: Commit the host tooling in English**

```bash
git add scripts/lib/common.sh scripts/new-build-id.sh scripts/host-preflight.sh tests/host/test_host_tools.py
git commit -m "feat: add Yocto host preflight checks"
```

Expected: merge `feature/host-preflight` to `develop` after the real-host check passes.

### Task 6: Build Orchestration and Immutable Evidence

**Feature branch:** `feature/build-evidence`

**Files:**
- Create: `scripts/build.sh`
- Create: `scripts/collect-artifacts.sh`
- Create: `tests/host/test_build_contract.py`

**Interfaces:**
- Consumes: `scripts/build.sh --build-id BUILD_ID PROFILE ACTION`, where `PROFILE` is `qemu`, `rpi5-minimal`, or `rpi5-camera`, and `ACTION` is `checkout`, `layers`, `parse`, or `build`.
- Produces: profile-specific `KAS_BUILD_DIR`, shared downloads/sstate below `build/kas-work/build/`, logs, deploy artifacts, layer revisions, license/package manifests, checksums, and `artifacts/BUILD_ID/PROFILE/COMPLETE`.
- Gate: `rpi5-minimal build` requires `artifacts/BUILD_ID/qemu-test/PASS`; `rpi5-camera build` additionally requires `artifacts/BUILD_ID/rpi5-test/PASS`.

- [ ] **Step 1: Create the feature branch**

```bash
git switch develop
git switch -c feature/build-evidence
```

- [ ] **Step 2: Write the failing build-orchestration contract tests**

```python
# tests/host/test_build_contract.py
import unittest

from support import read, run


class BuildContractTest(unittest.TestCase):
    def test_profiles_map_to_exact_kas_files(self) -> None:
        script = read("scripts/build.sh")
        expected = {
            "qemu": "kas/qemuarm64-minimal.yml",
            "rpi5-minimal": "kas/rpi5-minimal.yml",
            "rpi5-camera": "kas/rpi5-camera.yml",
        }
        for profile, kas_file in expected.items():
            self.assertIn(profile, script)
            self.assertIn(kas_file, script)

    def test_hardware_builds_are_gated(self) -> None:
        script = read("scripts/build.sh")
        self.assertIn("qemu-test/PASS", script)
        self.assertIn("rpi5-test/PASS", script)
        self.assertNotIn("kas build --update", script)

    def test_collector_requires_core_outputs(self) -> None:
        script = read("scripts/collect-artifacts.sh")
        for suffix in (".ext4", ".wic.bz2", ".wic.bmap", ".manifest"):
            self.assertIn(suffix, script)
        self.assertIn("layer-revisions.txt", script)
        self.assertIn("SHA256SUMS", script)

    def test_scripts_are_valid_bash(self) -> None:
        for path in ("scripts/build.sh", "scripts/collect-artifacts.sh"):
            result = run("bash", "-n", path)
            self.assertEqual(result.returncode, 0, f"{path}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm the missing-script failure**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_build_contract.py' -v`

Expected: failures mention `scripts/build.sh` and `scripts/collect-artifacts.sh`.

- [ ] **Step 4: Add the gated profile build wrapper**

```bash
#!/usr/bin/env bash
# scripts/build.sh
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

usage() {
    printf 'Usage: %s --build-id ID {qemu|rpi5-minimal|rpi5-camera} {checkout|layers|parse|build}\n' "$0"
}

[[ "${1:-}" == "--build-id" && $# -eq 4 ]] || { usage >&2; exit 2; }
build_id="$2"
profile="$3"
action="$4"
rpi5_validate_build_id "$build_id" || rpi5_die "invalid build ID: $build_id"

case "$profile" in
    qemu)
        config="kas/qemuarm64-minimal.yml"
        machine="qemuarm64"
        image="rpi5-minimal-image"
        ;;
    rpi5-minimal)
        config="kas/rpi5-minimal.yml"
        machine="raspberrypi5"
        image="rpi5-minimal-image"
        ;;
    rpi5-camera)
        config="kas/rpi5-camera.yml"
        machine="raspberrypi5"
        image="rpi5-camera-image"
        ;;
    *) usage >&2; exit 2 ;;
esac

case "$action" in checkout|layers|parse|build) ;; *) usage >&2; exit 2 ;; esac

repo_root="$(rpi5_repo_root)"
key_path="$repo_root/keys/rpi5_admin"
current_revision="$(git -C "$repo_root" rev-parse --short=12 HEAD)"
[[ "$build_id" == *"-$current_revision" ]] || \
    rpi5_die "build ID revision does not match HEAD $current_revision"

if [[ "$action" == "build" && "$profile" != "qemu" ]]; then
    rpi5_require_pass "$repo_root/artifacts/$build_id/qemu-test/PASS" "QEMU"
fi
if [[ "$action" == "build" && "$profile" == "rpi5-camera" ]]; then
    rpi5_require_pass "$repo_root/artifacts/$build_id/rpi5-test/PASS" "phase-1 hardware"
fi

"$repo_root/scripts/host-preflight.sh" --incremental --key "$key_path"

export RPI5_ADMIN_SSH_PUBKEY
RPI5_ADMIN_SSH_PUBKEY="$(tr -d '\n' < "${key_path}.pub")"
export RPI5_BUILD_ID="$build_id"
export KAS_WORK_DIR="$repo_root/build/kas-work"
export KAS_BUILD_DIR="$KAS_WORK_DIR/build/$profile"
mkdir -p "$KAS_WORK_DIR" "$KAS_BUILD_DIR" "$repo_root/artifacts/$build_id/$profile"

log="$repo_root/artifacts/$build_id/$profile/${action}.log"
run_logged() {
    set +e
    "$@" 2>&1 | tee "$log"
    status="${PIPESTATUS[0]}"
    set -e
    return "$status"
}

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

- [ ] **Step 5: Add deterministic artifact collection**

```bash
#!/usr/bin/env bash
# scripts/collect-artifacts.sh
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

[[ $# -eq 10 ]] || rpi5_die "collector requires build-id, profile, config, machine, and image"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --build-id) build_id="$2"; shift 2 ;;
        --profile) profile="$2"; shift 2 ;;
        --config) config="$2"; shift 2 ;;
        --machine) machine="$2"; shift 2 ;;
        --image) image="$2"; shift 2 ;;
        *) rpi5_die "unknown argument: $1" ;;
    esac
done

rpi5_validate_build_id "$build_id" || rpi5_die "invalid build ID"
repo_root="$(rpi5_repo_root)"
cd "$repo_root"
build_dir="$repo_root/build/kas-work/build/$profile"
deploy="$build_dir/tmp/deploy/images/$machine"
out="$repo_root/artifacts/$build_id/$profile"
mkdir -p "$out/images" "$out/checksums" "$out/manifests" "$out/licenses"

copy_required() {
    local source_path="$1"
    [[ -e "$source_path" ]] || rpi5_die "required artifact missing: $source_path"
    cp -L "$source_path" "$out/images/"
}

case "$profile" in
    qemu)
        copy_required "$deploy/$image-$machine.rootfs.ext4"
        copy_required "$deploy/Image"
        ;;
    rpi5-minimal|rpi5-camera)
        copy_required "$deploy/$image-$machine.rootfs.wic.bz2"
        copy_required "$deploy/$image-$machine.rootfs.wic.bmap"
        ;;
    *) rpi5_die "unknown profile: $profile" ;;
esac

manifest="$deploy/$image-$machine.rootfs.manifest"
[[ -e "$manifest" ]] || rpi5_die "package manifest missing: $manifest"
cp -L "$manifest" "$out/manifests/"

shopt -s nullglob
license_dirs=("$build_dir/tmp/deploy/licenses/$image-$machine"*)
[[ "${#license_dirs[@]}" -gt 0 ]] || rpi5_die "license manifest directory missing"
cp -a "${license_dirs[@]}" "$out/licenses/"

export KAS_WORK_DIR="$repo_root/build/kas-work"
export KAS_BUILD_DIR="$build_dir"
uv run --locked kas for-all-repos "$config" \
    'printf "%s %s\n" "$KAS_REPO_NAME" "$(git rev-parse HEAD)"' \
    | LC_ALL=C sort > "$out/manifests/layer-revisions.txt"

project_revision="$(git -C "$repo_root" rev-parse HEAD)"
kas_version="$(uv run --locked kas --version | tr '\n' ' ')"
printf '{"build_id":"%s","profile":"%s","machine":"%s","image":"%s","project_revision":"%s","kas_version":"%s"}\n' \
    "$build_id" "$profile" "$machine" "$image" "$project_revision" "$kas_version" \
    > "$out/manifests/build-metadata.json"

(
    cd "$out"
    sha256sum images/* > checksums/SHA256SUMS
)
touch "$out/COMPLETE"
```

- [ ] **Step 6: Make scripts executable and run contract tests**

Run: `chmod 0755 scripts/build.sh scripts/collect-artifacts.sh`

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_build_contract.py' -v`

Expected: `Ran 4 tests` followed by `OK`.

- [ ] **Step 7: Verify build-ID and gate failures without starting BitBake**

Run: `./scripts/build.sh --build-id invalid qemu parse`

Expected: nonzero exit with `invalid build ID`.

Run: `BUILD_ID="$(./scripts/new-build-id.sh)"; ./scripts/build.sh --build-id "$BUILD_ID" rpi5-minimal build`

Expected: nonzero exit with `QEMU PASS marker missing`; no BitBake task starts.

- [ ] **Step 8: Commit build orchestration in English**

```bash
git add scripts/build.sh scripts/collect-artifacts.sh tests/host/test_build_contract.py
git commit -m "feat: add gated Yocto build evidence pipeline"
```

Expected: merge `feature/build-evidence` to `develop` after offline tests and gate-failure checks pass.

### Task 7: Key-Only QEMU Runtime Gate

**Feature branch:** `feature/qemu-smoke-test`

**Files:**
- Create: `scripts/lib/remote.sh`
- Create: `scripts/test-qemu-guest.sh`
- Create: `scripts/test-qemu.sh`
- Create: `tests/host/test_qemu_contract.py`

**Interfaces:**
- Consumes: a complete `qemu` build for one build ID, `keys/rpi5_admin`, localhost TCP port 2222, and `build/kas-work/build/qemu`.
- Produces: console and SSH logs under `artifacts/BUILD_ID/qemu-test/`; `PASS` appears only after all eight guest assertions pass and the QEMU process exits cleanly.
- `scripts/test-qemu-guest.sh` can test an already-running guest, which is also the CI integration boundary.

- [ ] **Step 1: Create the feature branch**

```bash
git switch develop
git switch -c feature/qemu-smoke-test
```

- [ ] **Step 2: Write the failing QEMU contract tests**

```python
# tests/host/test_qemu_contract.py
import unittest

from support import read, run


class QemuContractTest(unittest.TestCase):
    def test_guest_checks_all_acceptance_properties(self) -> None:
        script = read("scripts/test-qemu-guest.sh")
        for expected in (
            "uname -m",
            "systemctl is-system-running",
            "systemd-networkd.service",
            "sshd.service",
            "/etc/rpi5-build-id",
            "PasswordAuthentication no",
            "PermitRootLogin no",
            "/var/tmp/qemu-rw-test",
            "systemctl --failed",
        ):
            self.assertIn(expected, script)

    def test_launcher_uses_local_slirp_and_cleans_process_group(self) -> None:
        script = read("scripts/test-qemu.sh")
        self.assertIn("runqemu qemuarm64 rpi5-minimal-image nographic slirp", script)
        self.assertIn("127.0.0.1", script)
        self.assertIn("2222", script)
        self.assertIn("ss -H -ltn", script)
        self.assertIn('kill -- "-$qemu_pid"', script)
        self.assertIn("launch-command.txt", script)
        self.assertIn("guest-PASS", script)

    def test_qemu_scripts_are_valid_bash(self) -> None:
        for path in (
            "scripts/lib/remote.sh",
            "scripts/test-qemu-guest.sh",
            "scripts/test-qemu.sh",
        ):
            result = run("bash", "-n", path)
            self.assertEqual(result.returncode, 0, f"{path}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm the missing-script failure**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_qemu_contract.py' -v`

Expected: failures mention `scripts/test-qemu-guest.sh` and `scripts/test-qemu.sh`.

- [ ] **Step 4: Add the shared SSH transport with strict host-key handling**

```bash
#!/usr/bin/env bash
# scripts/lib/remote.sh

rpi5_remote_init() {
    local host="$1"
    local port="$2"
    local key="$3"
    local known_hosts="$4"
    local user="${5:-rpiadmin}"

    RPI5_REMOTE_HOST="$host"
    RPI5_REMOTE_PORT="$port"
    RPI5_REMOTE_KEY="$key"
    RPI5_KNOWN_HOSTS="$known_hosts"
    RPI5_REMOTE_USER="$user"
    RPI5_SSH=(
        ssh -p "$port" -i "$key"
        -o BatchMode=yes
        -o ConnectTimeout=5
        -o ServerAliveInterval=10
        -o ServerAliveCountMax=2
        -o StrictHostKeyChecking=yes
        -o UserKnownHostsFile="$known_hosts"
        "$user@$host"
    )
    RPI5_SCP=(
        scp -P "$port" -i "$key"
        -o BatchMode=yes
        -o ConnectTimeout=5
        -o StrictHostKeyChecking=yes
        -o UserKnownHostsFile="$known_hosts"
    )
}

rpi5_refresh_host_key() {
    local temporary="${RPI5_KNOWN_HOSTS}.new"
    if ssh-keyscan -T 3 -H -p "$RPI5_REMOTE_PORT" "$RPI5_REMOTE_HOST" \
        > "$temporary" 2>/dev/null && [[ -s "$temporary" ]]; then
        mv "$temporary" "$RPI5_KNOWN_HOSTS"
        return 0
    fi
    rm -f "$temporary"
    return 1
}

rpi5_wait_ssh() {
    local timeout_seconds="$1"
    local deadline=$((SECONDS + timeout_seconds))
    while (( SECONDS < deadline )); do
        if rpi5_refresh_host_key && "${RPI5_SSH[@]}" true >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

rpi5_remote() {
    "${RPI5_SSH[@]}" "$@"
}

rpi5_copy_from() {
    local remote_path="$1"
    local local_path="$2"
    "${RPI5_SCP[@]}" \
        "$RPI5_REMOTE_USER@$RPI5_REMOTE_HOST:$remote_path" "$local_path"
}
```

- [ ] **Step 5: Add the reusable QEMU guest assertions**

```bash
#!/usr/bin/env bash
# scripts/test-qemu-guest.sh
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"
source "$(dirname "$0")/lib/remote.sh"

host="127.0.0.1"
port="2222"
timeout_seconds="180"
key="$(rpi5_repo_root)/keys/rpi5_admin"
evidence_dir=""
build_id=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --build-id) build_id="$2"; shift 2 ;;
        --host) host="$2"; shift 2 ;;
        --port) port="$2"; shift 2 ;;
        --timeout) timeout_seconds="$2"; shift 2 ;;
        --key) key="$2"; shift 2 ;;
        --evidence-dir) evidence_dir="$2"; shift 2 ;;
        *) rpi5_die "unknown QEMU guest argument: $1" ;;
    esac
done

rpi5_validate_build_id "$build_id" || rpi5_die "invalid build ID"
rpi5_validate_key_pair "$key"
[[ -n "$evidence_dir" ]] || \
    evidence_dir="$(rpi5_repo_root)/artifacts/$build_id/qemu-test"
mkdir -p "$evidence_dir"
known_hosts="$evidence_dir/known_hosts"
rpi5_remote_init "$host" "$port" "$key" "$known_hosts"
rpi5_wait_ssh "$timeout_seconds" || rpi5_die "QEMU SSH did not become ready"
rpi5_remote 'systemctl --failed --no-pager' \
    > "$evidence_dir/systemd-failed.log" 2>&1 || true
rpi5_remote 'sudo -n /usr/bin/journalctl -b --no-pager' \
    > "$evidence_dir/journal.log" 2>&1 || true

ssh_log="$evidence_dir/ssh-checks.log"
: > "$ssh_log"
check_exact() {
    local label="$1"
    local expected="$2"
    local command="$3"
    local output
    output="$(rpi5_remote "$command")"
    printf '%s=%s\n' "$label" "$output" | tee -a "$ssh_log"
    [[ "$output" == "$expected" ]] || \
        rpi5_die "$label expected '$expected' but got '$output'"
}

check_exact architecture aarch64 'uname -m'
check_exact build_id "$build_id" 'cat /etc/rpi5-build-id'
check_exact systemd running 'systemctl is-system-running'
check_exact networkd active 'systemctl is-active systemd-networkd.service'
check_exact sshd active 'systemctl is-active sshd.service'

rpi5_remote "ip -4 -o address show scope global | grep -Eq 'inet 10\\.0\\.2\\.'"
rpi5_remote "printf '%s' '$build_id' > /var/tmp/qemu-rw-test && grep -Fx '$build_id' /var/tmp/qemu-rw-test && rm /var/tmp/qemu-rw-test" \
    >> "$ssh_log"
rpi5_remote "grep -Fx 'PasswordAuthentication no' /etc/ssh/sshd_config.d/20-rpi5.conf && grep -Fx 'PermitRootLogin no' /etc/ssh/sshd_config.d/20-rpi5.conf" \
    >> "$ssh_log"

root_ssh=(
    ssh -p "$port" -i "$key" -o BatchMode=yes -o ConnectTimeout=5
    -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known_hosts"
    "root@$host" true
)
if "${root_ssh[@]}" >> "$ssh_log" 2>&1; then
    rpi5_die "root SSH login unexpectedly succeeded"
fi

password_only=(
    ssh -p "$port" -o BatchMode=yes -o ConnectTimeout=5
    -o PubkeyAuthentication=no
    -o PreferredAuthentications=password,keyboard-interactive
    -o NumberOfPasswordPrompts=0
    -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known_hosts"
    "rpiadmin@$host" true
)
if "${password_only[@]}" >> "$ssh_log" 2>&1; then
    rpi5_die "non-key SSH login unexpectedly succeeded"
fi

printf '{"build_id":"%s","architecture":"aarch64","systemd":"running","network":"active","ssh":"key-only"}\n' \
    "$build_id" > "$evidence_dir/result.json"
touch "$evidence_dir/guest-PASS"
rpi5_remote 'sudo -n /usr/bin/systemctl poweroff'
```

- [ ] **Step 6: Add the QEMU lifecycle wrapper**

```bash
#!/usr/bin/env bash
# scripts/test-qemu.sh
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

[[ "${1:-}" == "--build-id" && $# -eq 2 ]] || \
    rpi5_die "Usage: $0 --build-id ID"
build_id="$2"
rpi5_validate_build_id "$build_id" || rpi5_die "invalid build ID"

repo_root="$(rpi5_repo_root)"
key="$repo_root/keys/rpi5_admin"
rpi5_validate_key_pair "$key"
rpi5_require_pass "$repo_root/artifacts/$build_id/qemu/COMPLETE" "QEMU build"

evidence="$repo_root/artifacts/$build_id/qemu-test"
mkdir -p "$evidence"
[[ ! -e "$evidence/PASS" ]] || rpi5_die "QEMU PASS already exists for $build_id"
if ss -H -ltn 'sport = :2222' | grep -q .; then
    rpi5_die "localhost port 2222 is already in use"
fi

export RPI5_ADMIN_SSH_PUBKEY
RPI5_ADMIN_SSH_PUBKEY="$(tr -d '\n' < "${key}.pub")"
export RPI5_BUILD_ID="$build_id"
export KAS_WORK_DIR="$repo_root/build/kas-work"
export KAS_BUILD_DIR="$KAS_WORK_DIR/build/qemu"

qemu_pid=""
cleanup() {
    if [[ -n "$qemu_pid" ]] && kill -0 "$qemu_pid" 2>/dev/null; then
        kill -- "-$qemu_pid" 2>/dev/null || true
        wait "$qemu_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

printf '%s\n' "uv run --locked kas shell kas/qemuarm64-minimal.yml -c runqemu qemuarm64 rpi5-minimal-image nographic slirp" \
    > "$evidence/launch-command.txt"
cd "$repo_root"
setsid uv run --locked kas shell kas/qemuarm64-minimal.yml \
    -c 'runqemu qemuarm64 rpi5-minimal-image nographic slirp' \
    > "$evidence/console.log" 2>&1 &
qemu_pid="$!"

"$repo_root/scripts/test-qemu-guest.sh" \
    --build-id "$build_id" --host 127.0.0.1 --port 2222 \
    --timeout 180 --key "$key" --evidence-dir "$evidence"

deadline=$((SECONDS + 30))
while kill -0 "$qemu_pid" 2>/dev/null && (( SECONDS < deadline )); do
    sleep 1
done
if kill -0 "$qemu_pid" 2>/dev/null; then
    rpi5_die "QEMU did not exit within 30 seconds after poweroff"
fi
wait "$qemu_pid"
qemu_pid=""

[[ -f "$evidence/guest-PASS" ]] || rpi5_die "guest assertions did not pass"
mv "$evidence/guest-PASS" "$evidence/PASS"
printf 'PASS qemu build_id=%s\n' "$build_id"
```

- [ ] **Step 7: Make scripts executable and run offline tests**

Run: `chmod 0755 scripts/test-qemu-guest.sh scripts/test-qemu.sh`

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_qemu_contract.py' -v`

Expected: `Ran 3 tests` followed by `OK`.

- [ ] **Step 8: Commit the QEMU gate in English before assigning a build ID**

```bash
git add scripts/lib/remote.sh scripts/test-qemu-guest.sh scripts/test-qemu.sh tests/host/test_qemu_contract.py
git commit -m "feat: add key-only QEMU smoke validation"
```

Expected: the implementation is now part of the SHA that will be embedded in the image.

- [ ] **Step 9: Merge, then execute the real QEMU gate on the integration SHA**

```bash
git switch develop
git merge --no-ff feature/qemu-smoke-test
BUILD_ID="$(./scripts/new-build-id.sh)"
./scripts/build.sh --build-id "$BUILD_ID" qemu build
./scripts/test-qemu.sh --build-id "$BUILD_ID"
```

Expected: `artifacts/$BUILD_ID/qemu-test/PASS` exists, `result.json` reports `aarch64`, `running`, and `key-only`, `systemd-failed.log` and `launch-command.txt` are retained, and no QEMU process or port-2222 listener remains. Later feature merges invalidate this provisional ID, so Task 15 reruns QEMU once on the final integration SHA.

### Task 8: USB SSD Topology Validation and Safe Flashing

**Feature branch:** `feature/usb-ssd-flashing`

**Files:**
- Create: `scripts/lib/block_device.py`
- Create: `scripts/flash-ssd.sh`
- Create: `tests/host/test_block_device.py`
- Create: `tests/host/test_flash_contract.py`

**Interfaces:**
- Consumes: `lsblk --json --bytes --paths` topology, one exact whole-device path, protected mount sources, Wic image size from its bmap, matching checksums, profile COMPLETE, and prerequisite PASS markers.
- Produces: either a non-mutating rejection or a bmaptool-written USB SSD whose boot and root partitions pass read-only inspection; evidence is written under `artifacts/BUILD_ID/flash/`.
- Safety invariant: no code path invokes `dd`; a write requires root, a USB transport, an unmounted non-system whole disk, adequate capacity, and exact confirmation `ERASE:DEVICE:BUILD_ID`.

- [ ] **Step 1: Create the feature branch**

```bash
git switch develop
git switch -c feature/usb-ssd-flashing
```

- [ ] **Step 2: Write failing pure topology tests**

```python
# tests/host/test_block_device.py
import json
from pathlib import Path
import tempfile
import unittest

from support import REPO_ROOT


import sys
sys.path.insert(0, str(REPO_ROOT / "scripts/lib"))
import block_device  # noqa: E402

TOPOLOGY = {
    "blockdevices": [
        {
            "name": "/dev/nvme0n1",
            "kname": "nvme0n1",
            "path": "/dev/nvme0n1",
            "type": "disk",
            "tran": "nvme",
            "size": 1000000000000,
            "model": "SYSTEM",
            "serial": "SYS1",
            "mountpoints": [None],
            "children": [
                {
                    "name": "/dev/nvme0n1p2",
                    "kname": "nvme0n1p2",
                    "path": "/dev/nvme0n1p2",
                    "type": "part",
                    "tran": None,
                    "size": 900000000000,
                    "model": None,
                    "serial": None,
                    "mountpoints": ["/"],
                }
            ],
        },
        {
            "name": "/dev/sdb",
            "kname": "sdb",
            "path": "/dev/sdb",
            "type": "disk",
            "tran": "usb",
            "size": 500000000000,
            "model": "USB SSD",
            "serial": "USB1",
            "mountpoints": [None],
            "children": [
                {
                    "name": "/dev/sdb1",
                    "kname": "sdb1",
                    "path": "/dev/sdb1",
                    "type": "part",
                    "tran": None,
                    "size": 268435456,
                    "model": None,
                    "serial": None,
                    "mountpoints": [None],
                },
                {
                    "name": "/dev/sdb2",
                    "kname": "sdb2",
                    "path": "/dev/sdb2",
                    "type": "part",
                    "tran": None,
                    "size": 499000000000,
                    "model": None,
                    "serial": None,
                    "mountpoints": [None],
                },
            ],
        },
    ]
}


class BlockDeviceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.nodes = block_device.parse_topology(TOPOLOGY)

    def test_accepts_unmounted_usb_whole_disk(self) -> None:
        result = block_device.validate_target(
            self.nodes, "/dev/sdb", 4000000000, ["/dev/nvme0n1p2"], False
        )
        self.assertEqual(result["serial"], "USB1")

    def test_rejects_partition_non_usb_small_and_system_disk(self) -> None:
        cases = (
            ("/dev/sdb1", 1, []),
            ("/dev/nvme0n1", 1, []),
            ("/dev/sdb", 600000000000, []),
            ("/dev/nvme0n1", 1, ["/dev/nvme0n1p2"]),
        )
        for target, size, protected in cases:
            with self.subTest(target=target, size=size, protected=protected):
                with self.assertRaises(ValueError):
                    block_device.validate_target(
                        self.nodes, target, size, protected, False
                    )

    def test_rejects_mounted_target_child(self) -> None:
        topology = json.loads(json.dumps(TOPOLOGY))
        topology["blockdevices"][1]["children"][0]["mountpoints"] = ["/media/ssd"]
        nodes = block_device.parse_topology(topology)
        with self.assertRaisesRegex(ValueError, "mounted"):
            block_device.validate_target(nodes, "/dev/sdb", 1, [], False)

    def test_partition_paths_cover_sd_and_nvme_names(self) -> None:
        self.assertEqual(block_device.partition_path("/dev/sdb", 2), "/dev/sdb2")
        self.assertEqual(
            block_device.partition_path("/dev/nvme1n1", 2), "/dev/nvme1n1p2"
        )

    def test_reads_image_size_from_bmap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.wic.bmap"
            path.write_text(
                '<?xml version="1.0"?><bmap version="2.0"><ImageSize>4294967296</ImageSize></bmap>',
                encoding="utf-8",
            )
            self.assertEqual(block_device.bmap_image_size(path), 4294967296)


if __name__ == "__main__":
    unittest.main()
```

```python
# tests/host/test_flash_contract.py
import unittest

from support import read, run


class FlashContractTest(unittest.TestCase):
    def test_flash_requires_all_safety_inputs(self) -> None:
        script = read("scripts/flash-ssd.sh")
        for required in (
            "--build-id",
            "--profile",
            "--device",
            "--confirm",
            "qemu-test/PASS",
            "bmaptool copy",
            "lsblk --json --bytes --paths",
            "VENDOR",
            "fingerprint_before",
            "mount -o ro",
            "root=/dev/sda2",
            "blockdev --flushbufs",
            "transport",
            "size_bytes",
            "written_at",
        ):
            self.assertIn(required, script)

    def test_flash_has_no_dd_fallback(self) -> None:
        script = read("scripts/flash-ssd.sh")
        self.assertNotIn("dd if=", script)
        self.assertNotIn(" of=", script)

    def test_flash_script_is_valid_bash(self) -> None:
        result = run("bash", "-n", "scripts/flash-ssd.sh")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm the helper and wrapper are absent**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_block_device.py' -v`

Expected: import fails because `scripts/lib/block_device.py` does not exist.

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_flash_contract.py' -v`

Expected: failures mention `scripts/flash-ssd.sh`.

- [ ] **Step 4: Implement pure block-device validation**

```python
#!/usr/bin/env python3
# scripts/lib/block_device.py
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class Device:
    path: str
    kname: str
    type: str
    tran: str | None
    size: int
    model: str
    serial: str
    mountpoints: tuple[str, ...]
    parent: str | None


def parse_topology(payload: dict) -> dict[str, Device]:
    nodes: dict[str, Device] = {}

    def visit(raw: dict, parent: str | None) -> None:
        path = str(raw.get("path") or raw.get("name"))
        mountpoints = tuple(value for value in (raw.get("mountpoints") or []) if value)
        node = Device(
            path=path,
            kname=str(raw.get("kname") or Path(path).name),
            type=str(raw.get("type") or ""),
            tran=raw.get("tran"),
            size=int(raw.get("size") or 0),
            model=str(raw.get("model") or "").strip(),
            serial=str(raw.get("serial") or "").strip(),
            mountpoints=mountpoints,
            parent=parent,
        )
        if path in nodes:
            raise ValueError(f"duplicate block-device path: {path}")
        nodes[path] = node
        for child in raw.get("children") or []:
            visit(child, path)

    for root in payload.get("blockdevices") or []:
        visit(root, None)
    return nodes


def lookup(nodes: dict[str, Device], name: str) -> Device:
    candidates = [
        node for node in nodes.values()
        if name in {node.path, f"/dev/{node.kname}"}
    ]
    if len(candidates) != 1:
        raise ValueError(f"block device does not resolve uniquely: {name}")
    return candidates[0]


def root_disk(nodes: dict[str, Device], name: str) -> Device:
    node = lookup(nodes, name)
    while node.parent is not None:
        node = nodes[node.parent]
    return node


def descendants(nodes: dict[str, Device], root_path: str) -> list[Device]:
    result: list[Device] = []
    pending = [root_path]
    while pending:
        parent = pending.pop()
        children = [node for node in nodes.values() if node.parent == parent]
        result.extend(children)
        pending.extend(node.path for node in children)
    return result


def mounted_paths(nodes: dict[str, Device], target: str) -> list[str]:
    root = lookup(nodes, target)
    mounted: list[str] = []
    for node in [root, *descendants(nodes, root.path)]:
        if node.mountpoints:
            mounted.append(node.path)
    return mounted


def validate_target(
    nodes: dict[str, Device],
    target: str,
    image_bytes: int,
    protected_sources: list[str],
    allow_mounted: bool,
) -> dict:
    node = lookup(nodes, target)
    if node.type != "disk":
        raise ValueError(f"target is not a whole disk: {target}")
    if node.tran != "usb":
        raise ValueError(f"target transport is not USB: {node.tran}")
    if node.size < image_bytes:
        raise ValueError(f"target is smaller than image: {node.size} < {image_bytes}")

    target_root = root_disk(nodes, node.path)
    for source in protected_sources:
        if not source.startswith("/dev/"):
            continue
        protected_root = root_disk(nodes, source)
        if protected_root.path == target_root.path:
            raise ValueError(f"target backs a protected filesystem: {source}")

    mounted = mounted_paths(nodes, node.path)
    if mounted and not allow_mounted:
        raise ValueError(f"target or child is mounted: {', '.join(mounted)}")

    result = asdict(node)
    result["mounted"] = mounted
    return result


def partition_path(device: str, number: int) -> str:
    if number < 1:
        raise ValueError("partition number must be positive")
    separator = "p" if re.search(r"[0-9]$", device) else ""
    return f"{device}{separator}{number}"


def bmap_image_size(path: Path) -> int:
    root = ET.parse(path).getroot()
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "ImageSize" and element.text:
            return int(element.text.strip())
    raise ValueError("ImageSize missing from bmap")


def load_nodes(path: Path) -> dict[str, Device]:
    return parse_topology(json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("--topology", type=Path, required=True)
    validate.add_argument("--target", required=True)
    validate.add_argument("--image-bytes", type=int, required=True)
    validate.add_argument("--protected", action="append", default=[])
    validate.add_argument("--allow-mounted", action="store_true")

    mounts = commands.add_parser("mounts")
    mounts.add_argument("--topology", type=Path, required=True)
    mounts.add_argument("--target", required=True)

    partition = commands.add_parser("partition")
    partition.add_argument("--device", required=True)
    partition.add_argument("--number", type=int, required=True)

    bmap_size = commands.add_parser("bmap-size")
    bmap_size.add_argument("--bmap", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "validate":
        result = validate_target(
            load_nodes(args.topology),
            args.target,
            args.image_bytes,
            args.protected,
            args.allow_mounted,
        )
        print(json.dumps(result, sort_keys=True))
    elif args.command == "mounts":
        for path in mounted_paths(load_nodes(args.topology), args.target):
            print(path)
    elif args.command == "partition":
        print(partition_path(args.device, args.number))
    elif args.command == "bmap-size":
        print(bmap_image_size(args.bmap))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
```

- [ ] **Step 5: Run pure validation tests**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_block_device.py' -v`

Expected: `Ran 5 tests` followed by `OK`; no block device is opened or modified.

- [ ] **Step 6: Implement the guarded bmaptool writer and read-only verifier**

```bash
#!/usr/bin/env bash
# scripts/flash-ssd.sh
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

usage() {
    printf 'Usage: sudo UV_BIN=/absolute/path/to/uv %s --build-id ID --profile {rpi5-minimal|rpi5-camera} --device /dev/DEVICE --confirm ERASE:/dev/DEVICE:ID\n' "$0"
}

build_id=""
profile=""
device=""
confirmation=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --build-id) build_id="$2"; shift 2 ;;
        --profile) profile="$2"; shift 2 ;;
        --device) device="$2"; shift 2 ;;
        --confirm) confirmation="$2"; shift 2 ;;
        --help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

[[ "$EUID" -eq 0 ]] || rpi5_die "flash requires root for the selected device only"
rpi5_validate_build_id "$build_id" || rpi5_die "invalid build ID"
[[ "$profile" == "rpi5-minimal" || "$profile" == "rpi5-camera" ]] || \
    rpi5_die "invalid profile"
[[ "$device" == /dev/* ]] || rpi5_die "device must be an explicit /dev path"
[[ "$confirmation" == "ERASE:$device:$build_id" ]] || \
    rpi5_die "confirmation must exactly match ERASE:$device:$build_id"

repo_root="$(rpi5_repo_root)"
cd "$repo_root"
uv_bin="${UV_BIN:-}"
[[ "$uv_bin" == /* && -x "$uv_bin" ]] || \
    rpi5_die "UV_BIN must be an absolute executable path"
[[ "$("$uv_bin" --version)" == "uv 0.11.31" ]] || \
    rpi5_die "UV_BIN must be uv 0.11.31"
profile_root="$repo_root/artifacts/$build_id/$profile"
flash_root="$repo_root/artifacts/$build_id/flash"
flash_marker="$flash_root/${profile}-PASS"
[[ ! -e "$flash_marker" ]] || rpi5_die "flash PASS already exists for $profile"
mkdir -p "$flash_root"
rpi5_require_pass "$repo_root/artifacts/$build_id/qemu-test/PASS" "QEMU"
rpi5_require_pass "$profile_root/COMPLETE" "$profile build"
if [[ "$profile" == "rpi5-camera" ]]; then
    rpi5_require_pass "$repo_root/artifacts/$build_id/rpi5-test/PASS" "phase-1 hardware"
fi

image_name="rpi5-minimal-image-raspberrypi5.rootfs.wic.bz2"
[[ "$profile" == "rpi5-camera" ]] && \
    image_name="rpi5-camera-image-raspberrypi5.rootfs.wic.bz2"
image="$profile_root/images/$image_name"
bmap="${image%.bz2}.bmap"
[[ -f "$image" && -f "$bmap" ]] || rpi5_die "Wic image or bmap is missing"
(
    cd "$profile_root"
    sha256sum -c checksums/SHA256SUMS
)

helper="$repo_root/scripts/lib/block_device.py"
image_bytes="$("$uv_bin" run --locked python "$helper" bmap-size --bmap "$bmap")"
temporary="$(mktemp -d /tmp/rpi5-flash.XXXXXX)"
topology="$temporary/lsblk.json"
boot_mount="$temporary/boot"
root_mount="$temporary/root"
mkdir "$boot_mount" "$root_mount"

cleanup() {
    mountpoint -q "$root_mount" && umount "$root_mount" || true
    mountpoint -q "$boot_mount" && umount "$boot_mount" || true
    rm -f "$topology"
    rmdir "$root_mount" "$boot_mount" "$temporary" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

protected=()
for protected_path in / /boot /home "$repo_root"; do
    source_device="$(findmnt -n -o SOURCE --target "$protected_path" 2>/dev/null || true)"
    if [[ "$source_device" == /dev/* ]]; then
        protected+=(--protected "$(readlink -f "$source_device")")
    fi
done

lsblk --json --bytes --paths \
    -o NAME,KNAME,PATH,PKNAME,TYPE,TRAN,SIZE,VENDOR,MODEL,SERIAL,MOUNTPOINTS \
    > "$topology"
metadata="$("$uv_bin" run --locked python "$helper" validate --topology "$topology" \
    --target "$device" --image-bytes "$image_bytes" \
    "${protected[@]}" --allow-mounted)"
fingerprint_before="$(LC_ALL=C lsblk -dn -b -P -o PATH,TYPE,TRAN,SIZE,VENDOR,MODEL,SERIAL "$device")"
{
    printf 'metadata=%s\n' "$metadata"
    printf 'fingerprint=%s\n' "$fingerprint_before"
    lsblk --bytes --paths -o NAME,TYPE,TRAN,SIZE,VENDOR,MODEL,SERIAL,MOUNTPOINTS "$device"
} | tee "$flash_root/${profile}-selected-device.log"

mapfile -t mounted < <("$uv_bin" run --locked python "$helper" mounts --topology "$topology" --target "$device")
for mounted_device in "${mounted[@]}"; do
    umount "$mounted_device"
done

lsblk --json --bytes --paths \
    -o NAME,KNAME,PATH,PKNAME,TYPE,TRAN,SIZE,VENDOR,MODEL,SERIAL,MOUNTPOINTS \
    > "$topology"
fingerprint_after="$(LC_ALL=C lsblk -dn -b -P -o PATH,TYPE,TRAN,SIZE,VENDOR,MODEL,SERIAL "$device")"
[[ "$fingerprint_after" == "$fingerprint_before" ]] || rpi5_die "target identity changed before write"
"$uv_bin" run --locked python "$helper" validate --topology "$topology" \
    --target "$device" --image-bytes "$image_bytes" "${protected[@]}" >/dev/null

bmaptool copy --bmap "$bmap" "$image" "$device"
sync
blockdev --rereadpt "$device"
udevadm settle --timeout=30

boot_partition="$("$uv_bin" run --locked python "$helper" partition --device "$device" --number 1)"
root_partition="$("$uv_bin" run --locked python "$helper" partition --device "$device" --number 2)"
[[ -b "$boot_partition" && -b "$root_partition" ]] || \
    rpi5_die "expected two partitions after flashing"
[[ "$(lsblk -n -o FSTYPE "$root_partition")" == "ext4" ]] || \
    rpi5_die "root partition is not ext4"

mount -o ro "$boot_partition" "$boot_mount"
[[ -f "$boot_mount/config.txt" ]] || rpi5_die "config.txt missing"
[[ -f "$boot_mount/cmdline.txt" ]] || rpi5_die "cmdline.txt missing"
grep -Eq '(^|[[:space:]])root=/dev/sda2([[:space:]]|$)' "$boot_mount/cmdline.txt" || \
    rpi5_die "boot command line does not select /dev/sda2"
[[ -f "$boot_mount/kernel_2712.img" ]] || rpi5_die "Pi 5 kernel missing"
find "$boot_mount" -name bcm2712-rpi-5-b.dtb -print -quit | grep -q . || \
    rpi5_die "Pi 5 device tree missing"
umount "$boot_mount"

mount -o ro "$root_partition" "$root_mount"
[[ "$(cat "$root_mount/etc/rpi5-build-id")" == "$build_id" ]] || \
    rpi5_die "root filesystem build ID mismatch"
umount "$root_mount"

sync
blockdev --flushbufs "$device"
serial="$(lsblk -dn -o SERIAL "$device" | tr -cd 'A-Za-z0-9._-')"
[[ -n "$serial" ]] || serial="unknown-serial"
vendor="$(lsblk -dn -o VENDOR "$device" | tr -cd 'A-Za-z0-9._ -')"
model="$(lsblk -dn -o MODEL "$device" | tr -cd 'A-Za-z0-9._ -')"
transport="$(lsblk -dn -o TRAN "$device" | tr -cd 'A-Za-z0-9._-')"
size_bytes="$(lsblk -dn -b -o SIZE "$device" | tr -cd '0-9')"
[[ "$transport" == "usb" && "$size_bytes" =~ ^[1-9][0-9]*$ ]] || \
    rpi5_die "target identity became invalid after write"
written_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '{"build_id":"%s","profile":"%s","device":"%s","transport":"%s","size_bytes":%s,"vendor":"%s","model":"%s","serial":"%s","image_sha256":"%s","written_at":"%s"}\n' \
    "$build_id" "$profile" "$device" "$transport" "$size_bytes" "$vendor" "$model" "$serial" \
    "$(sha256sum "$image" | awk '{print $1}')" "$written_at" \
    > "$flash_root/${profile}-${serial}.json"
touch "$flash_marker"
printf 'PASS flash build_id=%s profile=%s device=%s serial=%s; buffers flushed, safe to disconnect\n' \
    "$build_id" "$profile" "$device" "$serial"
```

- [ ] **Step 7: Run safety tests and a no-device help check**

Run: `chmod 0755 scripts/lib/block_device.py scripts/flash-ssd.sh`

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_block_device.py' -v`

Expected: `Ran 5 tests` followed by `OK`.

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_flash_contract.py' -v`

Expected: `Ran 3 tests` followed by `OK`.

Run: `./scripts/flash-ssd.sh --help`

Expected: usage is printed without reading or writing any block device.

- [ ] **Step 8: Commit SSD safety tooling in English**

```bash
git add scripts/lib/block_device.py scripts/flash-ssd.sh tests/host/test_block_device.py tests/host/test_flash_contract.py
git commit -m "feat: add guarded USB SSD image flashing"
```

Expected: merge `feature/usb-ssd-flashing` to `develop` after all pure safety tests pass. Actual device writing occurs at the consolidated hardware checkpoint in Task 15, where the operator resolves and confirms one concrete device.

### Task 9: Bounded Network Discovery Without UART

**Feature branch:** `feature/network-discovery`

**Files:**
- Create: `scripts/discover-rpi5.sh`
- Create: `tests/host/test_discovery.py`

**Interfaces:**
- Consumes: `--hostname NAME`, `--timeout SECONDS`, and optional `--previous-ip`, `--lease-file`, `--mac`, `--port`, and `--state-file` arguments.
- Produces: exactly one validated IPv4 address on stdout; progress and failures go to stderr. The successful address is cached in the ignored `.state/last-rpi5-ip` file by default.
- Discovery order per poll is mDNS, the caller-provided previous IP, the cached IP, and matching dnsmasq lease entries. A candidate is accepted only when `ssh-keyscan` proves that the expected SSH port is listening.

- [ ] **Step 1: Create the feature branch**

```bash
git switch develop
git switch -c feature/network-discovery
```

- [ ] **Step 2: Write failing discovery tests with fake network commands**

```python
# tests/host/test_discovery.py
from pathlib import Path
import os
import tempfile
import unittest

from support import REPO_ROOT, read, run


class DiscoveryTest(unittest.TestCase):
    def make_command(self, directory: Path, name: str, body: str) -> None:
        path = directory / name
        path.write_text("#!/usr/bin/env bash\nset -eu\n" + body, encoding="utf-8")
        path.chmod(0o755)

    def test_contract_is_bounded_and_has_all_discovery_sources(self) -> None:
        script = read("scripts/discover-rpi5.sh")
        for text in (
            "--timeout",
            'timeout_seconds="300"',
            "avahi-resolve-host-name",
            "--previous-ip",
            "--lease-file",
            "--mac",
            "ssh-keyscan",
            ".state/last-rpi5-ip",
        ):
            self.assertIn(text, script)

    def test_resolves_mdns_and_prints_only_the_ip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            self.make_command(
                fake_bin,
                "avahi-resolve-host-name",
                "printf 'rpi5-minimal.local\\t192.0.2.10\\n'\n",
            )
            self.make_command(
                fake_bin,
                "ssh-keyscan",
                '[[ "${@: -1}" == "192.0.2.10" ]]\nprintf "host-key\\n"\n',
            )
            env = {
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "RPI5_DISCOVERY_POLL_SECONDS": "0.01",
            }
            result = run(
                "bash",
                "scripts/discover-rpi5.sh",
                "--hostname",
                "rpi5-minimal",
                "--timeout",
                "1",
                "--state-file",
                str(root / "state"),
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "192.0.2.10\n")

    def test_falls_back_to_matching_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            self.make_command(fake_bin, "avahi-resolve-host-name", "exit 1\n")
            self.make_command(
                fake_bin,
                "ssh-keyscan",
                '[[ "${@: -1}" == "198.51.100.23" ]]\nprintf "host-key\\n"\n',
            )
            leases = root / "dnsmasq.leases"
            leases.write_text(
                "2147483647 dc:a6:32:00:00:01 198.51.100.23 rpi5-minimal *\n",
                encoding="utf-8",
            )
            env = {
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "RPI5_DISCOVERY_POLL_SECONDS": "0.01",
            }
            result = run(
                "bash",
                "scripts/discover-rpi5.sh",
                "--hostname",
                "rpi5-minimal",
                "--lease-file",
                str(leases),
                "--mac",
                "dc:a6:32:00:00:01",
                "--timeout",
                "1",
                "--state-file",
                str(root / "state"),
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "198.51.100.23\n")

    def test_script_is_valid_bash(self) -> None:
        result = run("bash", "-n", "scripts/discover-rpi5.sh")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test and confirm the script is missing**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_discovery.py' -v`

Expected: failures mention `scripts/discover-rpi5.sh`.

- [ ] **Step 4: Implement bounded discovery**

```bash
#!/usr/bin/env bash
# scripts/discover-rpi5.sh
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

usage() {
    printf 'Usage: %s [--hostname NAME] [--timeout SEC] [--previous-ip IP] [--lease-file PATH] [--mac MAC] [--port PORT] [--state-file PATH]\n' "$0"
}

repo_root="$(rpi5_repo_root)"
cd "$repo_root"
hostname="rpi5-minimal"
timeout_seconds="300"
previous_ip=""
lease_file=""
mac=""
port="22"
state_file="$repo_root/.state/last-rpi5-ip"
poll_seconds="${RPI5_DISCOVERY_POLL_SECONDS:-5}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hostname) hostname="$2"; shift 2 ;;
        --timeout) timeout_seconds="$2"; shift 2 ;;
        --previous-ip) previous_ip="$2"; shift 2 ;;
        --lease-file) lease_file="$2"; shift 2 ;;
        --mac) mac="$2"; shift 2 ;;
        --port) port="$2"; shift 2 ;;
        --state-file) state_file="$2"; shift 2 ;;
        --help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

[[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]] || rpi5_die "timeout must be a positive integer"
[[ "$port" =~ ^[1-9][0-9]*$ && "$port" -le 65535 ]] || rpi5_die "invalid SSH port"
[[ "$hostname" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || rpi5_die "invalid hostname"
if [[ -n "$lease_file" && ! -r "$lease_file" ]]; then
    rpi5_die "lease file is not readable: $lease_file"
fi

valid_ipv4() {
    uv run --locked python - "$1" <<'PY'
import ipaddress
import sys
try:
    ipaddress.IPv4Address(sys.argv[1])
except ipaddress.AddressValueError:
    raise SystemExit(1)
PY
}

declare -A attempted=()
try_candidate() {
    local candidate="${1:-}"
    [[ -n "$candidate" ]] || return 0
    valid_ipv4 "$candidate" || return 0
    [[ -z "${attempted[$candidate]+present}" ]] || return 0
    attempted["$candidate"]=1
    printf 'Probing %s:%s\n' "$candidate" "$port" >&2
    if ssh-keyscan -T 3 -p "$port" "$candidate" >/dev/null 2>&1; then
        mkdir -p "$(dirname "$state_file")"
        printf '%s\n' "$candidate" > "$state_file"
        printf '%s\n' "$candidate"
        exit 0
    fi
}

deadline=$((SECONDS + timeout_seconds))
while (( SECONDS < deadline )); do
    attempted=()
    mdns_name="${hostname%.local}.local"
    mdns_ip="$(avahi-resolve-host-name -4 "$mdns_name" 2>/dev/null | awk 'NR == 1 {print $2}' || true)"
    try_candidate "$mdns_ip"
    try_candidate "$previous_ip"
    if [[ -r "$state_file" ]]; then
        try_candidate "$(head -n 1 "$state_file")"
    fi
    if [[ -n "$lease_file" ]]; then
        while IFS= read -r lease_ip; do
            try_candidate "$lease_ip"
        done < <(
            awk -v host="$hostname" -v wanted_mac="$mac" '
                ($4 == host || (wanted_mac != "" && tolower($2) == tolower(wanted_mac))) {print $3}
            ' "$lease_file"
        )
    fi
    printf 'No reachable SSH endpoint for %s yet\n' "$hostname" >&2
    sleep "$poll_seconds"
done

rpi5_die "no reachable $hostname SSH endpoint within ${timeout_seconds}s"
```

- [ ] **Step 5: Make the script executable and run all discovery tests**

Run: `chmod 0755 scripts/discover-rpi5.sh`

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_discovery.py' -v`

Expected: `Ran 4 tests` followed by `OK`; test stdout contains no diagnostics.

- [ ] **Step 6: Commit the discovery unit in English**

```bash
git add scripts/discover-rpi5.sh tests/host/test_discovery.py
git commit -m "feat: add bounded Raspberry Pi network discovery"
```

Expected: merge `feature/network-discovery` to `develop` after fake-network and syntax tests pass. Do not connect hardware yet; the final integration task performs one consolidated bring-up.

### Task 10: Raspberry Pi 5 USB-Boot Acceptance and Reboot Recovery

**Feature branch:** `feature/rpi5-hardware-validation`

**Files:**
- Create: `scripts/test-rpi5.sh`
- Create: `tests/host/test_rpi5_contract.py`

**Interfaces:**
- Consumes: a phase-1 minimal-image flash PASS marker, the build ID, an initial IP address, the SSH key, and optional DHCP lease/MAC hints.
- Produces: per-boot check logs and `artifacts/BUILD_ID/rpi5-test/PASS` after the initial check plus exactly three successful reboot/recovery cycles.
- Each reboot must disappear from the network, return within 120 seconds, present a new boot ID, and still boot `/dev/sda2` from USB with systemd, Ethernet, writable root, and key-only SSH intact.

- [ ] **Step 1: Create the feature branch**

```bash
git switch develop
git switch -c feature/rpi5-hardware-validation
```

- [ ] **Step 2: Write the failing hardware-acceptance contract tests**

```python
# tests/host/test_rpi5_contract.py
import unittest

from support import read, run


class RaspberryPiAcceptanceContractTest(unittest.TestCase):
    def test_all_phase_one_acceptance_checks_are_present(self) -> None:
        script = read("scripts/test-rpi5.sh")
        for expected in (
            "Raspberry Pi 5",
            "uname -m",
            "systemctl is-system-running",
            "ip -4 -o address show scope global",
            "ip -4 route show default",
            "/carrier",
            "/dev/sda2",
            'transport" == "usb',
            "root_uuid",
            "mmcblk",
            "findmnt -n -o OPTIONS /",
            "/etc/rpi5-build-id",
            "PasswordAuthentication no",
            "PermitRootLogin no",
            "/proc/sys/kernel/random/boot_id",
            "journalctl -b -1",
        ):
            self.assertIn(expected, script)

    def test_exactly_three_reboots_have_a_120_second_budget(self) -> None:
        script = read("scripts/test-rpi5.sh")
        self.assertIn('for reboot_number in 1 2 3', script)
        self.assertIn('--timeout 120', script)
        self.assertIn('elapsed" -le 120', script)
        self.assertIn("sudo -n /usr/bin/systemctl reboot", script)

    def test_help_is_non_mutating_and_script_is_valid_bash(self) -> None:
        help_result = run("bash", "scripts/test-rpi5.sh", "--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("Usage:", help_result.stdout)
        syntax = run("bash", "-n", "scripts/test-rpi5.sh")
        self.assertEqual(syntax.returncode, 0, syntax.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm the script is missing**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_rpi5_contract.py' -v`

Expected: failures mention `scripts/test-rpi5.sh`.

- [ ] **Step 4: Implement phase-1 acceptance and reboot recovery**

```bash
#!/usr/bin/env bash
# scripts/test-rpi5.sh
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"
source "$(dirname "$0")/lib/remote.sh"

usage() {
    printf 'Usage: %s --build-id ID --host IP [--hostname NAME] [--port PORT] [--key PATH] [--lease-file PATH] [--mac MAC]\n' "$0"
}

build_id=""
host=""
hostname="rpi5-minimal"
port="22"
key="$(rpi5_repo_root)/keys/rpi5_admin"
lease_file=""
mac=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --build-id) build_id="$2"; shift 2 ;;
        --host) host="$2"; shift 2 ;;
        --hostname) hostname="$2"; shift 2 ;;
        --port) port="$2"; shift 2 ;;
        --key) key="$2"; shift 2 ;;
        --lease-file) lease_file="$2"; shift 2 ;;
        --mac) mac="$2"; shift 2 ;;
        --help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

rpi5_validate_build_id "$build_id" || rpi5_die "invalid build ID"
[[ -n "$host" ]] || rpi5_die "initial host is required"
rpi5_validate_key_pair "$key"
repo_root="$(rpi5_repo_root)"
rpi5_require_pass "$repo_root/artifacts/$build_id/qemu-test/PASS" "QEMU"
rpi5_require_pass "$repo_root/artifacts/$build_id/rpi5-minimal/COMPLETE" "minimal image"
rpi5_require_pass "$repo_root/artifacts/$build_id/flash/rpi5-minimal-PASS" "minimal flash"

evidence="$repo_root/artifacts/$build_id/rpi5-test"
[[ ! -e "$evidence/PASS" ]] || rpi5_die "phase-1 PASS already exists"
mkdir -p "$evidence"
known_hosts="$evidence/known_hosts"
connected="0"

collect_diagnostics() {
    [[ "$connected" == "1" ]] || return 0
    rpi5_remote 'sudo -n /usr/bin/journalctl -b --no-pager' > "$evidence/journal-current.log" 2>&1 || true
    rpi5_remote 'sudo -n /usr/bin/journalctl -b -1 --no-pager' > "$evidence/journal-previous.log" 2>&1 || true
    rpi5_remote 'sudo -n /usr/bin/dmesg' > "$evidence/dmesg.log" 2>&1 || true
    rpi5_remote 'lsblk -o NAME,TYPE,TRAN,SIZE,MODEL,SERIAL,FSTYPE,UUID,MOUNTPOINTS' \
        > "$evidence/lsblk.log" 2>&1 || true
    rpi5_remote 'findmnt --real' > "$evidence/findmnt.log" 2>&1 || true
    rpi5_remote 'networkctl status --no-pager' > "$evidence/networkctl.log" 2>&1 || true
}

on_exit() {
    local status="$?"
    trap - EXIT
    collect_diagnostics
    exit "$status"
}
trap on_exit EXIT

connect_current_host() {
    rpi5_remote_init "$host" "$port" "$key" "$known_hosts"
    rpi5_wait_ssh 20 || rpi5_die "key-only SSH did not become ready on $host"
    connected="1"
}

remote_exact() {
    local label="$1"
    local expected="$2"
    local command="$3"
    local log="$4"
    local output
    output="$(rpi5_remote "$command")"
    printf '%s=%s\n' "$label" "$output" | tee -a "$log"
    [[ "$output" == "$expected" ]] || \
        rpi5_die "$label expected '$expected' but got '$output'"
}

assert_denied_logins() {
    local log="$1"
    local root_ssh=(
        ssh -p "$port" -i "$key" -o BatchMode=yes -o ConnectTimeout=5
        -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known_hosts"
        "root@$host" true
    )
    if "${root_ssh[@]}" >> "$log" 2>&1; then
        rpi5_die "root SSH login unexpectedly succeeded"
    fi
    local password_only=(
        ssh -p "$port" -o BatchMode=yes -o ConnectTimeout=5
        -o PubkeyAuthentication=no
        -o PreferredAuthentications=password,keyboard-interactive
        -o NumberOfPasswordPrompts=0
        -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$known_hosts"
        "rpiadmin@$host" true
    )
    if "${password_only[@]}" >> "$log" 2>&1; then
        rpi5_die "non-key SSH login unexpectedly succeeded"
    fi
}

declare -A observed_boot_ids=()
checked_boot_id=""
expected_root_uuid=""

check_boot() {
    local cycle="$1"
    local log="$evidence/boot-${cycle}.log"
    : > "$log"

    remote_exact architecture aarch64 'uname -m' "$log"
    model="$(rpi5_remote "tr -d '\\000' </proc/device-tree/model")"
    printf 'model=%s\n' "$model" | tee -a "$log"
    [[ "$model" == *"Raspberry Pi 5"* ]] || rpi5_die "unexpected board model"
    remote_exact build_id "$build_id" 'cat /etc/rpi5-build-id' "$log"
    remote_exact systemd running 'systemctl is-system-running' "$log"
    remote_exact networkd active 'systemctl is-active systemd-networkd.service' "$log"
    remote_exact sshd active 'systemctl is-active sshd.service' "$log"

    rpi5_remote "ip -4 -o address show scope global | grep -Eq 'inet [0-9]'" \
        >> "$log"
    wired_interface="$(rpi5_remote "ip -4 route show default | awk 'NR == 1 {print \$5}'")"
    [[ "$wired_interface" == eth* || "$wired_interface" == en* ]] || \
        rpi5_die "default route is not on a wired interface"
    remote_exact ethernet_carrier 1 "cat /sys/class/net/$wired_interface/carrier" "$log"
    printf 'default_interface=%s\n' "$wired_interface" | tee -a "$log"

    root_info="$(rpi5_remote 'root_source=$(findmnt -n -o SOURCE /); parent=$(lsblk -no PKNAME "$root_source" | head -n 1); transport=$(lsblk -dn -o TRAN "/dev/$parent" | tr -d "[:space:]"); root_uuid=$(lsblk -no UUID "$root_source" | tr -d "[:space:]"); printf "%s|%s|%s|%s" "$root_source" "/dev/$parent" "$transport" "$root_uuid"')"
    IFS='|' read -r root_source root_disk transport root_uuid <<< "$root_info"
    printf 'root_source=%s root_disk=%s transport=%s root_uuid=%s\n' \
        "$root_source" "$root_disk" "$transport" "$root_uuid" | tee -a "$log"
    [[ "$root_source" == "/dev/sda2" ]] || rpi5_die "root is not /dev/sda2"
    [[ "$root_source" != /dev/mmcblk* ]] || rpi5_die "root unexpectedly uses microSD"
    [[ "$transport" == "usb" ]] || rpi5_die "root disk transport is not usb"
    [[ -n "$root_uuid" ]] || rpi5_die "root filesystem UUID is empty"
    if [[ "$cycle" == "initial" ]]; then
        expected_root_uuid="$root_uuid"
    elif [[ "$root_uuid" != "$expected_root_uuid" ]]; then
        rpi5_die "root filesystem changed across reboot"
    fi
    if rpi5_remote "lsblk -ndo NAME | grep -Eq '^mmcblk'"; then
        rpi5_die "microSD must be removed during normal acceptance"
    fi
    rpi5_remote "findmnt -n -o OPTIONS / | tr ',' '\\n' | grep -Fx rw" >> "$log"
    rpi5_remote "printf '%s' '$build_id' > /var/tmp/rpi5-rw-test && grep -Fx '$build_id' /var/tmp/rpi5-rw-test && rm /var/tmp/rpi5-rw-test" \
        >> "$log"
    rpi5_remote "grep -Fx 'PasswordAuthentication no' /etc/ssh/sshd_config.d/20-rpi5.conf && grep -Fx 'PermitRootLogin no' /etc/ssh/sshd_config.d/20-rpi5.conf" \
        >> "$log"
    assert_denied_logins "$log"

    boot_id="$(rpi5_remote 'cat /proc/sys/kernel/random/boot_id')"
    [[ "$boot_id" =~ ^[0-9a-f-]{36}$ ]] || rpi5_die "invalid boot ID"
    [[ -z "${observed_boot_ids[$boot_id]+present}" ]] || rpi5_die "boot ID did not change"
    observed_boot_ids["$boot_id"]=1
    printf 'boot_id=%s\n' "$boot_id" | tee -a "$log"
    checked_boot_id="$boot_id"
}

connect_current_host
check_boot initial
initial_boot_id="$checked_boot_id"

reboot_1=""
reboot_2=""
reboot_3=""
for reboot_number in 1 2 3; do
    started="$SECONDS"
    rpi5_remote 'sudo -n /usr/bin/systemctl reboot' >/dev/null 2>&1 || true
    down_deadline=$((SECONDS + 60))
    while (( SECONDS < down_deadline )); do
        if ! ssh-keyscan -T 2 -p "$port" "$host" >/dev/null 2>&1; then
            break
        fi
        sleep 2
    done
    (( SECONDS < down_deadline )) || rpi5_die "Pi never left the network"

    discovery=(
        "$repo_root/scripts/discover-rpi5.sh"
        --hostname "$hostname" --timeout 120 --previous-ip "$host" --port "$port"
    )
    [[ -z "$lease_file" ]] || discovery+=(--lease-file "$lease_file")
    [[ -z "$mac" ]] || discovery+=(--mac "$mac")
    host="$("${discovery[@]}")"
    connect_current_host
    check_boot "reboot-$reboot_number"
    current_boot_id="$checked_boot_id"
    printf -v "reboot_$reboot_number" '%s' "$current_boot_id"
    elapsed=$((SECONDS - started))
    [[ "$elapsed" -le 120 ]] || rpi5_die "reboot $reboot_number exceeded 120 seconds"
    printf 'reboot=%s elapsed_seconds=%s host=%s\n' \
        "$reboot_number" "$elapsed" "$host" | tee -a "$evidence/reboots.log"
done

printf '{"build_id":"%s","reboots":3,"initial_boot_id":"%s","reboot_boot_ids":["%s","%s","%s"],"result":"PASS"}\n' \
    "$build_id" "$initial_boot_id" "$reboot_1" "$reboot_2" "$reboot_3" \
    > "$evidence/result.json"
touch "$evidence/PASS"
printf 'PASS rpi5 build_id=%s host=%s reboots=3\n' "$build_id" "$host"
```

- [ ] **Step 5: Make the script executable and run offline contract tests**

Run: `chmod 0755 scripts/test-rpi5.sh`

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_rpi5_contract.py' -v`

Expected: `Ran 3 tests` followed by `OK`; `--help` does not access keys, the network, or block devices.

- [ ] **Step 6: Commit hardware validation in English**

```bash
git add scripts/test-rpi5.sh tests/host/test_rpi5_contract.py
git commit -m "feat: add Raspberry Pi 5 USB boot acceptance"
```

Expected: merge `feature/rpi5-hardware-validation` to `develop` after offline tests. Do not run it against the Pi in this task; Task 15 runs it once against the final integrated commit to avoid repeated local SSD connections.

### Task 11: Camera Module 3 Wide Remote Acceptance

**Feature branch:** `feature/imx708-validation`

**Files:**
- Modify: `meta-rpi5-cam/recipes-core/images/rpi5-camera-image.bb`
- Modify: `tests/host/test_image_contract.py`
- Create: `scripts/test-camera.sh`
- Create: `tests/host/test_camera_contract.py`

**Interfaces:**
- Consumes: the camera-image and flash COMPLETE/PASS markers, phase-1 hardware PASS, an initial reachable host, the SSH key, and explicit operator attestation through `--wide-label-confirmed`.
- Produces: sensor/media logs, retrieved JPEG and raw H.264 samples with matching remote/local SHA-256 values, thermal/load observations, a post-reboot JPEG, and `artifacts/BUILD_ID/camera-test/PASS`.
- Software can prove the IMX708 sensor and autofocus path but cannot distinguish the standard and Wide lens electronically. The script refuses to run without the operator's `--wide-label-confirmed` attestation after the physical label/cable check in Task 15.

- [ ] **Step 1: Create the feature branch**

```bash
git switch develop
git switch -c feature/imx708-validation
```

- [ ] **Step 2: Extend the failing image test for unprivileged camera access**

Add to `ImageContractTest` in `tests/host/test_image_contract.py`:

```python
    def test_camera_user_has_device_groups(self) -> None:
        camera = read("meta-rpi5-cam/recipes-core/images/rpi5-camera-image.bb")
        self.assertIn("video,render", camera)
        self.assertIn("rpiadmin", camera)
```

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_image_contract.py' -v`

Expected: one failure because the camera image does not yet add `rpiadmin` to the device groups.

- [ ] **Step 3: Grant only the camera device groups in the camera image**

Append to `meta-rpi5-cam/recipes-core/images/rpi5-camera-image.bb`:

```bitbake
EXTRA_USERS_PARAMS:append = " usermod -a -G video,render rpiadmin;"
```

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_image_contract.py' -v`

Expected: all image contract tests pass; no unrestricted sudo command is added.

- [ ] **Step 4: Write the failing camera acceptance tests**

```python
# tests/host/test_camera_contract.py
import unittest

from support import read, run


class CameraAcceptanceContractTest(unittest.TestCase):
    def test_sensor_still_and_software_h264_commands_are_exact(self) -> None:
        script = read("scripts/test-camera.sh")
        for expected in (
            "--wide-label-confirmed",
            "operator-wide-label.txt",
            "rpicam-hello --list-cameras",
            "rpicam-hello --version",
            "imx708",
            "[0-9]+x[0-9]+",
            "rpicam-still --nopreview --autofocus-mode auto --timeout 2s",
            "rpicam-vid --nopreview --timeout 10s",
            "--width 1920 --height 1080 --framerate 30",
            "--codec libav --libav-format h264 --libav-video-codec libx264",
            "ffprobe",
            "sha256sum",
            "/sys/class/thermal/thermal_zone0/temp",
            "diagnostic-journal.log",
        ):
            self.assertIn(expected, script)

    def test_capture_is_repeated_after_one_reboot(self) -> None:
        script = read("scripts/test-camera.sh")
        self.assertIn("sudo -n /usr/bin/systemctl reboot", script)
        self.assertIn("post-reboot", script)
        self.assertIn("--timeout 120", script)
        self.assertIn("camera-test/PASS", script)

    def test_help_is_non_mutating_and_script_is_valid_bash(self) -> None:
        help_result = run("bash", "scripts/test-camera.sh", "--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("Usage:", help_result.stdout)
        syntax = run("bash", "-n", "scripts/test-camera.sh")
        self.assertEqual(syntax.returncode, 0, syntax.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5: Run the camera tests and confirm the script is missing**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_camera_contract.py' -v`

Expected: failures mention `scripts/test-camera.sh`.

- [ ] **Step 6: Implement IMX708 still, H.264, retrieval, and reboot checks**

```bash
#!/usr/bin/env bash
# scripts/test-camera.sh
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"
source "$(dirname "$0")/lib/remote.sh"

usage() {
    printf 'Usage: %s --build-id ID --host IP --wide-label-confirmed [--hostname NAME] [--port PORT] [--key PATH] [--lease-file PATH] [--mac MAC]\n' "$0"
}

build_id=""
host=""
hostname="rpi5-camera"
port="22"
key="$(rpi5_repo_root)/keys/rpi5_admin"
lease_file=""
mac=""
wide_label_confirmed="0"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --build-id) build_id="$2"; shift 2 ;;
        --host) host="$2"; shift 2 ;;
        --wide-label-confirmed) wide_label_confirmed="1"; shift ;;
        --hostname) hostname="$2"; shift 2 ;;
        --port) port="$2"; shift 2 ;;
        --key) key="$2"; shift 2 ;;
        --lease-file) lease_file="$2"; shift 2 ;;
        --mac) mac="$2"; shift 2 ;;
        --help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

rpi5_validate_build_id "$build_id" || rpi5_die "invalid build ID"
[[ "$wide_label_confirmed" == "1" ]] || \
    rpi5_die "operator must confirm the physical Camera Module 3 Wide label"
[[ -n "$host" ]] || rpi5_die "initial host is required"
rpi5_validate_key_pair "$key"
repo_root="$(rpi5_repo_root)"
rpi5_require_pass "$repo_root/artifacts/$build_id/qemu-test/PASS" "QEMU"
rpi5_require_pass "$repo_root/artifacts/$build_id/rpi5-test/PASS" "phase-1 hardware"
rpi5_require_pass "$repo_root/artifacts/$build_id/rpi5-camera/COMPLETE" "camera image"
rpi5_require_pass "$repo_root/artifacts/$build_id/flash/rpi5-camera-PASS" "camera flash"

evidence="$repo_root/artifacts/$build_id/camera-test"
[[ ! -e "$evidence/PASS" ]] || rpi5_die "camera PASS already exists"
mkdir -p "$evidence/samples"
printf 'camera_module=Camera Module 3 Wide\nlabel_confirmed_by_operator=yes\nconfirmed_at=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$evidence/operator-wide-label.txt"
known_hosts="$evidence/known_hosts"
connected="0"

collect_camera_diagnostics() {
    [[ "$connected" == "1" ]] || return 0
    rpi5_remote 'sudo -n /usr/bin/journalctl -b --no-pager' \
        > "$evidence/diagnostic-journal.log" 2>&1 || true
    rpi5_remote 'sudo -n /usr/bin/dmesg' \
        > "$evidence/diagnostic-dmesg.log" 2>&1 || true
    rpi5_remote 'rpicam-hello --version' \
        > "$evidence/diagnostic-rpicam-version.log" 2>&1 || true
    rpi5_remote 'rpicam-hello --list-cameras' \
        > "$evidence/diagnostic-camera-list.log" 2>&1 || true
    rpi5_remote 'media-ctl -p' \
        > "$evidence/diagnostic-media-topology.log" 2>&1 || true
}

on_camera_exit() {
    local status="$?"
    trap - EXIT
    collect_camera_diagnostics
    exit "$status"
}
trap on_camera_exit EXIT

connect_current_host() {
    rpi5_remote_init "$host" "$port" "$key" "$known_hosts"
    rpi5_wait_ssh 20 || rpi5_die "camera image SSH did not become ready"
    connected="1"
    [[ "$(rpi5_remote 'cat /etc/rpi5-build-id')" == "$build_id" ]] || \
        rpi5_die "camera image build ID mismatch"
    [[ "$(rpi5_remote 'systemctl is-system-running')" == "running" ]] || \
        rpi5_die "camera image systemd is not running"
    [[ "$(rpi5_remote 'findmnt -n -o SOURCE /')" == "/dev/sda2" ]] || \
        rpi5_die "camera image is not rooted on USB /dev/sda2"
}

check_thermal() {
    local label="$1"
    local temperature
    temperature="$(rpi5_remote 'cat /sys/class/thermal/thermal_zone0/temp')"
    [[ "$temperature" =~ ^[0-9]+$ ]] || rpi5_die "invalid thermal reading"
    [[ "$temperature" -lt 85000 ]] || rpi5_die "SoC temperature reached 85 C"
    printf '%s temperature_millic=%s load=%s\n' \
        "$label" "$temperature" "$(rpi5_remote 'cat /proc/loadavg')" \
        | tee -a "$evidence/health.log"
}

copy_and_verify() {
    local remote_path="$1"
    local local_path="$2"
    local remote_sha
    remote_sha="$(rpi5_remote "sha256sum '$remote_path' | awk '{print \$1}'")"
    rpi5_copy_from "$remote_path" "$local_path"
    local_sha="$(sha256sum "$local_path" | awk '{print $1}')"
    [[ "$remote_sha" == "$local_sha" ]] || rpi5_die "copy checksum mismatch for $remote_path"
    printf '%s  %s\n' "$local_sha" "$(basename "$local_path")" \
        >> "$evidence/samples/SHA256SUMS"
}

capture_still() {
    local label="$1"
    local remote_jpeg="/var/tmp/imx708-${label}.jpg"
    rpi5_remote "rm -f '$remote_jpeg'; rpicam-still --nopreview --autofocus-mode auto --timeout 2s --output '$remote_jpeg'" \
        > "$evidence/still-${label}.log" 2>&1
    rpi5_remote "test -s '$remote_jpeg' && file '$remote_jpeg' | grep -F 'JPEG image data'" \
        >> "$evidence/still-${label}.log"
    copy_and_verify "$remote_jpeg" "$evidence/samples/imx708-${label}.jpg"
    rpi5_remote "rm -f '$remote_jpeg'"
}

connect_current_host
rpi5_remote 'sudo -n /usr/bin/dmesg' > "$evidence/kernel.log"
grep -Eiq 'imx708|unicam|cfe' "$evidence/kernel.log" || \
    rpi5_die "kernel log has no camera pipeline evidence"
rpi5_remote 'media-ctl -p' > "$evidence/media-topology.log"
rpi5_remote 'v4l2-ctl --list-devices' > "$evidence/video-devices.log"
rpi5_remote 'rpicam-hello --version' > "$evidence/rpicam-version.log" 2>&1
rpi5_remote 'rpicam-hello --list-cameras' > "$evidence/cameras.log" 2>&1
grep -Eiq 'imx708' "$evidence/cameras.log" || rpi5_die "IMX708 was not enumerated"
grep -Eq '[0-9]+x[0-9]+' "$evidence/cameras.log" || rpi5_die "IMX708 sensor modes were not listed"

initial_boot_id="$(rpi5_remote 'cat /proc/sys/kernel/random/boot_id')"
check_thermal before-capture
capture_still initial

remote_video="/var/tmp/imx708-wide-1080p30.h264"
rpi5_remote "rm -f '$remote_video'; rpicam-vid --nopreview --timeout 10s --width 1920 --height 1080 --framerate 30 --codec libav --libav-format h264 --libav-video-codec libx264 --output '$remote_video'" \
    > "$evidence/video.log" 2>&1
rpi5_remote "test -s '$remote_video' && ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate -of csv=p=0 '$remote_video'" \
    > "$evidence/ffprobe.log"
grep -Eq '^h264,1920,1080,(30/1|30)$' "$evidence/ffprobe.log" || \
    rpi5_die "H.264 stream is not 1920x1080 at 30 fps"
copy_and_verify "$remote_video" "$evidence/samples/imx708-wide-1080p30.h264"
rpi5_remote "rm -f '$remote_video'"
check_thermal after-video

rpi5_remote 'sudo -n /usr/bin/systemctl reboot' >/dev/null 2>&1 || true
discovery=(
    "$repo_root/scripts/discover-rpi5.sh"
    --hostname "$hostname" --timeout 120 --previous-ip "$host" --port "$port"
)
[[ -z "$lease_file" ]] || discovery+=(--lease-file "$lease_file")
[[ -z "$mac" ]] || discovery+=(--mac "$mac")
host="$("${discovery[@]}")"
connect_current_host
post_boot_id="$(rpi5_remote 'cat /proc/sys/kernel/random/boot_id')"
[[ "$post_boot_id" != "$initial_boot_id" ]] || rpi5_die "camera reboot did not occur"
rpi5_remote 'rpicam-hello --list-cameras' > "$evidence/cameras-post-reboot.log" 2>&1
grep -Eiq 'imx708' "$evidence/cameras-post-reboot.log" || \
    rpi5_die "IMX708 missing after reboot"
grep -Eq '[0-9]+x[0-9]+' "$evidence/cameras-post-reboot.log" || \
    rpi5_die "IMX708 modes missing after reboot"
capture_still post-reboot
check_thermal post-reboot

printf '{"build_id":"%s","sensor":"imx708","lens_variant":"wide-operator-verified","jpeg":"PASS","h264":"libx264-1920x1080-30fps","reboot_capture":"PASS","result":"PASS"}\n' \
    "$build_id" > "$evidence/result.json"
touch "$evidence/PASS"
printf 'PASS camera build_id=%s sensor=imx708 host=%s\n' "$build_id" "$host"
```

- [ ] **Step 7: Make the script executable and run offline camera tests**

Run: `chmod 0755 scripts/test-camera.sh`

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_camera_contract.py' -v`

Expected: `Ran 3 tests` followed by `OK`.

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_image_contract.py' -v`

Expected: all image recipe tests pass with the new device-group assertion.

- [ ] **Step 8: Commit Camera Module 3 Wide validation in English**

```bash
git add meta-rpi5-cam/recipes-core/images/rpi5-camera-image.bb tests/host/test_image_contract.py scripts/test-camera.sh tests/host/test_camera_contract.py
git commit -m "feat: add IMX708 Wide camera acceptance tests"
```

Expected: merge `feature/imx708-validation` to `develop` after offline tests. Physical capture remains deferred to the consolidated Task 15 sequence.

### Task 12: Operator Runbooks, Evidence Policy, and H.264 Review Gate

**Feature branch:** `feature/operator-runbooks`

**Files:**
- Create: `README.md`
- Create: `docs/runbooks/build-qemu.md`
- Create: `docs/runbooks/usb-ssd-bringup.md`
- Create: `docs/runbooks/remote-validation.md`
- Create: `docs/runbooks/camera-validation.md`
- Create: `docs/runbooks/eeprom-recovery.md`
- Create: `docs/licensing/camera-h264.md`
- Create: `docs/evidence-schema.md`
- Create: `tests/host/test_docs_contract.py`

**Interfaces:**
- Consumes: all commands, gates, evidence paths, and recovery boundaries defined in Tasks 1-11.
- Produces: one canonical operator route that requires only two planned hands-on SSD sessions, plus a separately labeled emergency EEPROM path.

- [ ] **Step 1: Create the feature branch**

```bash
git switch develop
git switch -c feature/operator-runbooks
```

- [ ] **Step 2: Write the failing documentation contract**

```python
# tests/host/test_docs_contract.py
import unittest

from support import read


class DocumentationContractTest(unittest.TestCase):
    def test_readme_declares_supported_path_and_git_policy(self) -> None:
        text = read("README.md")
        for expected in (
            "Yocto 6.0",
            "Raspberry Pi 5",
            "Camera Module 3 Wide",
            "USB SSD",
            "develop",
            "feature/SCOPE",
            "English",
        ):
            self.assertIn(expected, text)

    def test_runbooks_cover_every_gate_and_no_uart_boundary(self) -> None:
        combined = "\n".join(
            read(path)
            for path in (
                "docs/runbooks/build-qemu.md",
                "docs/runbooks/usb-ssd-bringup.md",
                "docs/runbooks/remote-validation.md",
                "docs/runbooks/camera-validation.md",
                "docs/runbooks/eeprom-recovery.md",
            )
        )
        for expected in (
            "QEMU PASS",
            "ERASE:$TARGET_DEVICE:$BUILD_ID",
            "USB-to-UART",
            "five minutes",
            "180 seconds",
            "three reboots",
            "IMX708",
            "microSD",
            "BOOT_ORDER",
            "UAS",
        ):
            self.assertIn(expected, combined)
        self.assertNotIn("sudo dd ", combined)

    def test_license_and_evidence_boundaries_are_explicit(self) -> None:
        license_text = read("docs/licensing/camera-h264.md")
        self.assertIn("libx264", license_text)
        self.assertIn("GPL", license_text)
        self.assertIn("development", license_text)
        self.assertIn("blocks external distribution", license_text)
        evidence = read("docs/evidence-schema.md")
        for forbidden in ("private key", "IP address", "device serial", "raw journal"):
            self.assertIn(forbidden, evidence)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm the documents are missing**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_docs_contract.py' -v`

Expected: failures list the missing README and runbook files.

- [ ] **Step 4: Add the repository entry point**

````markdown
# Raspberry Pi 5 Camera Firmware

This repository builds a pinned Yocto 6.0 (`wrynose`) image for Raspberry Pi 5 on an x86_64 Ubuntu 24.04 host. The final target boots from a USB SSD and supports Camera Module 3 Wide (IMX708), headless still capture, and software H.264.

## Supported route

1. Run host preflight and build the `qemuarm64` minimal image.
2. Pass key-only QEMU runtime checks.
3. Build and flash the Raspberry Pi minimal image to one explicitly selected USB SSD.
4. Pass remote USB-boot acceptance and three reboots.
5. Build, flash, and remotely validate the camera image.

Start with [build and QEMU](docs/runbooks/build-qemu.md), then follow [USB SSD bring-up](docs/runbooks/usb-ssd-bringup.md), [remote validation](docs/runbooks/remote-validation.md), and [camera validation](docs/runbooks/camera-validation.md). EEPROM recovery is an exception path only.

## Git policy

`develop` is the integration branch. Start each independently testable unit from current `develop` as `feature/SCOPE`, commit at functional boundaries, and write every commit message in English using a Conventional Commit subject. `master` receives only a fully accepted release baseline.

Generated builds, keys, images, raw evidence, IP addresses, and device identifiers are never committed. Only the compact JSON record described in [the evidence schema](docs/evidence-schema.md) is eligible for Git.
````

- [ ] **Step 5: Add the exact build and QEMU runbook**

````markdown
# Build and QEMU Gate

## One-time setup

```bash
sudo apt-get update
sudo apt-get install -y build-essential chrpath cpio debianutils diffstat file gawk \
  gcc git iputils-ping libacl1 liblz4-tool locales make python3 python3-git \
  python3-jinja2 python3-pexpect python3-subunit socat \
  tar texinfo unzip wget xz-utils zstd bmap-tools qemu-system-arm openssh-client \
  avahi-utils curl ffmpeg iproute2 parted util-linux udev
sudo locale-gen en_US.UTF-8
if ! command -v uv >/dev/null 2>&1 || [[ "$(uv --version)" != "uv 0.11.31" ]]; then
    curl -LsSf https://astral.sh/uv/0.11.31/install.sh |
        env UV_NO_MODIFY_PATH=1 UV_INSTALL_DIR=/home/many/.local/bin sh
    export PATH="/home/many/.local/bin:$PATH"
fi
uv lock --check
uv sync --locked
uv run --locked kas --version
ssh-keygen -t ed25519 -f keys/rpi5_admin -C rpi5-admin
chmod 600 keys/rpi5_admin
chmod 644 keys/rpi5_admin.pub
./scripts/host-preflight.sh --initial --key keys/rpi5_admin
```

## Final-commit QEMU gate

Run only from a clean `develop` worktree. Do not change commits while a build ID is active.

```bash
BUILD_ID="$(./scripts/new-build-id.sh)"
./scripts/build.sh --build-id "$BUILD_ID" qemu checkout
./scripts/build.sh --build-id "$BUILD_ID" qemu layers
./scripts/build.sh --build-id "$BUILD_ID" qemu parse
./scripts/build.sh --build-id "$BUILD_ID" qemu build
./scripts/test-qemu.sh --build-id "$BUILD_ID"
test -f "artifacts/$BUILD_ID/qemu-test/PASS"
printf '%s\n' "$BUILD_ID" > .state/active-build-id
```

Expected: `PASS qemu`; the QEMU PASS marker is mandatory before either Raspberry Pi image build. The runner uses localhost port 2222 and leaves no QEMU process behind.
````

- [ ] **Step 6: Add the guarded USB SSD runbook**

````markdown
# USB SSD Build and Flash

Never infer a target from `/dev/sdX` ordering and never use `dd`. Disconnect unrelated removable drives first. The flashing tool independently rejects the host root/swap disks, partitions, mounted targets, non-USB transport, undersized media, mismatched checksums, missing gates, and an inexact confirmation string.

```bash
BUILD_ID="$(cat .state/active-build-id)"
./scripts/build.sh --build-id "$BUILD_ID" rpi5-minimal build
lsblk --bytes --paths -o NAME,TYPE,TRAN,SIZE,MODEL,SERIAL,MOUNTPOINTS
read -r -p 'Exact whole USB SSD device (for example /dev/sdb or /dev/nvme1n1): ' TARGET_DEVICE
lsblk --bytes --paths -o NAME,TYPE,TRAN,SIZE,MODEL,SERIAL,MOUNTPOINTS "$TARGET_DEVICE"
read -r -p "Type ERASE:$TARGET_DEVICE:$BUILD_ID: " CONFIRMATION
UV_BIN="$(command -v uv)"
test "$("$UV_BIN" --version)" = "uv 0.11.31"
sudo UV_BIN="$UV_BIN" ./scripts/flash-ssd.sh --build-id "$BUILD_ID" --profile rpi5-minimal \
  --device "$TARGET_DEVICE" --confirm "$CONFIRMATION"
test -f "artifacts/$BUILD_ID/flash/rpi5-minimal-PASS"
```

Stop on any device mismatch. A PASS means bmaptool completed, both partitions appeared, boot files were inspected read-only, and `/etc/rpi5-build-id` matched on the root partition.
````

- [ ] **Step 7: Add the no-UART remote bring-up runbook**

````markdown
# Remote Raspberry Pi 5 Validation

USB-to-UART is not part of this project. Before the first power-on, do the only planned assembly session: power off the Pi, fit the physically labeled Camera Module 3 Wide and CSI cable, connect the flashed USB SSD and wired Ethernet, then connect a stable 5 V/5 A supply. HDMI is optional and stays disconnected unless the five minutes network deadline expires.

```bash
BUILD_ID="$(cat .state/active-build-id)"
read -r -p 'Press Enter, then immediately apply power to start the first-boot clock: '
BOOT_WAIT_START="$SECONDS"
RPI_IP="$(./scripts/discover-rpi5.sh --hostname rpi5-minimal --timeout 300)"
ssh-keyscan -T 3 -H "$RPI_IP" > .state/rpi5-initial-known-hosts
ssh -i keys/rpi5_admin -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=.state/rpi5-initial-known-hosts "rpiadmin@$RPI_IP" true
BOOT_WAIT_ELAPSED=$((SECONDS - BOOT_WAIT_START))
test "$BOOT_WAIT_ELAPSED" -le 180
./scripts/test-rpi5.sh --build-id "$BUILD_ID" --host "$RPI_IP"
test -f "artifacts/$BUILD_ID/rpi5-test/PASS"
```

Expected: first-boot key-only SSH is ready within 180 seconds; then aarch64, Raspberry Pi 5 model, matching build ID, systemd running, wired DHCP/default route, `/dev/sda2` on USB transport, writable root, root/password login denied, and three reboots recovered in at most 120 seconds each.

If there is no network signal after five minutes, do one local HDMI/power inspection. Record the screen and power indication before changing anything. Follow the EEPROM exception runbook only for an explicit bootloader/USB-boot diagnosis.
````

- [ ] **Step 8: Add the camera runbook**

````markdown
# Camera Module 3 Wide Validation

Phase-1 hardware PASS must exist first. Build the camera image while the validated minimal system remains powered, then request remote poweroff. This creates only one planned SSD swap/reflash session.

```bash
BUILD_ID="$(cat .state/active-build-id)"
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera build
CAMERA_MANIFEST=("artifacts/$BUILD_ID/rpi5-camera/manifests/"*.manifest)
test "${#CAMERA_MANIFEST[@]}" -eq 1
grep -Eq '^libcamera-apps ' "${CAMERA_MANIFEST[0]}"
grep -Eq '^rpidistro-ffmpeg ' "${CAMERA_MANIFEST[0]}"
grep -Eq '^x264 ' "${CAMERA_MANIFEST[0]}"
```

Power off remotely, move only the SSD to the x86 host, and flash it with the guarded procedure using `--profile rpi5-camera` and exact confirmation `ERASE:$TARGET_DEVICE:$BUILD_ID`. Reconnect the SSD to the already assembled Pi and power on.

```bash
RPI_IP="$(./scripts/discover-rpi5.sh --hostname rpi5-camera --timeout 300)"
./scripts/test-camera.sh --build-id "$BUILD_ID" --host "$RPI_IP" \
  --wide-label-confirmed
test -f "artifacts/$BUILD_ID/camera-test/PASS"
```

Expected: IMX708 enumeration, autofocus JPEG, a retrieved 1920x1080 30 fps H.264 stream encoded through libav/libx264, matching transfer hashes, temperature below 85 C, and another JPEG after reboot. The Wide lens variant is confirmed from the physical module label; software identifies only IMX708.
````

- [ ] **Step 9: Add the exceptional EEPROM recovery runbook**

````markdown
# EEPROM Recovery Exception

This is not a normal boot medium. Use a microSD card only after the remote five minutes timeout and one HDMI inspection indicate a bootloader/USB-boot problem. Preserve the SSD and its evidence unchanged.

1. On a separate workstation, use Raspberry Pi Imager's bootloader utility image for Raspberry Pi 5 with USB boot selected, writing to a clearly identified temporary microSD card.
2. With Pi power removed, disconnect the USB SSD, insert only that recovery microSD, attach HDMI, and power on.
3. Wait for the documented success screen/LED pattern, then remove power and the microSD.
4. If a Raspberry Pi OS diagnostic microSD is used, run `sudo rpi-eeprom-config`, record `BOOT_ORDER`, and require that its hexadecimal sequence contains digit `4` (USB-MSD). Power off and remove microSD before normal testing.
5. On the x86 host, confirm the bridge remains stable as USB mass storage. If failure occurs only with UAS, replace the bridge/enclosure first; add a kernel quirk only in a separately reviewed hardware-compatibility feature.
6. Reconnect the unchanged validated USB SSD and retry the five-minute discovery once.
7. Record the recovery date, displayed result, power supply, EEPROM version, `BOOT_ORDER`, bridge model, and whether USB boot resumed. Do not add a UART step.

If recovery does not produce the success indication or USB-MSD digit `4` cannot be confirmed, stop. Do not repeatedly rewrite the SSD or EEPROM; investigate power, cable, enclosure compatibility, and board condition separately.
````

- [ ] **Step 10: Add licensing and evidence policies**

````markdown
# Camera H.264 Licensing Gate

The camera development profile enables the Yocto `commercial` flag and rpidistro-ffmpeg's GPL/libx264 configuration to prove software H.264 on the selected hardware. This approval is scoped to internal development and validation images.

Any external distribution, product shipment, customer image, or published binary requires a recorded review of GPL source/notice obligations, all linked FFmpeg components, libx264 patent/commercial considerations, and the destination jurisdictions. A missing review blocks external distribution. Hardware encoding or a differently licensed encoder is a separate design change and must receive its own feature branch and acceptance run.
````

````markdown
# Evidence Schema

Raw evidence lives under ignored `artifacts/BUILD_ID/` directories. It may contain console logs, an IP address, a device serial, SSH host keys, retrieved media, and a raw journal, so it is never committed. A private key is never copied into evidence at all.

Only `artifacts/releases/BUILD_ID.json` may be committed. Schema version 1 contains: build ID, full project revision, exact external source revisions, minimal and camera image SHA-256 values, QEMU/Raspberry Pi/camera PASS states, reboot count, H.264 mode, and UTC validation completion time. It must not contain a private key, public key, IP address, MAC address, device serial, SSH host key, user name, sample media, console log, or raw journal.

The release record is derived only after all markers for the same build ID exist. The image checksum files and raw evidence remain in controlled external storage according to the retention policy in `artifacts/README.md`.
````

- [ ] **Step 11: Run document tests and commit the operator unit in English**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_docs_contract.py' -v`

Expected: `Ran 3 tests` followed by `OK`.

```bash
git add README.md docs/runbooks docs/licensing docs/evidence-schema.md tests/host/test_docs_contract.py
git commit -m "docs: add Raspberry Pi build and validation runbooks"
```

Expected: merge `feature/operator-runbooks` to `develop` after the documentation contract passes.

### Task 13: Pinned, Provider-Neutral kas Container CI

**Feature branch:** `feature/kas-container-ci`

**Files:**
- Modify: `scripts/host-preflight.sh`
- Modify: `scripts/build.sh`
- Modify: `tests/host/test_host_tools.py`
- Create: `ci/container.env`
- Create: `ci/kas-container`
- Create: `ci/pipeline.sh`
- Create: `ci/README.md`
- Create: `tests/host/test_ci_contract.py`

**Interfaces:**
- Consumes: a CI job already running as a non-root user inside the pinned OCI digest, with the repository writable and build/download/sstate directories persisted as caches.
- Produces: `unit`, `qemu`, and `rpi5-image` stages. The image stage repeats the QEMU gate with the same ephemeral key and build ID before building the minimal Raspberry Pi image.
- CI never accesses a block device, flashes media, performs real-hardware or camera acceptance, or creates a release record.

- [ ] **Step 1: Create the feature branch**

```bash
git switch develop
git switch -c feature/kas-container-ci
```

- [ ] **Step 2: Write failing CI and container-preflight tests**

Add to `HostToolsTest` in `tests/host/test_host_tools.py`:

```python
    def test_preflight_requires_proof_for_container_mode(self) -> None:
        script = read("scripts/host-preflight.sh")
        self.assertIn("--container", script)
        self.assertIn("/.dockerenv", script)
        self.assertIn("/run/.containerenv", script)
        self.assertIn("RPI5_CI_CONTAINER", read("scripts/build.sh"))
```

```python
# tests/host/test_ci_contract.py
from pathlib import Path
import hashlib
import unittest

from support import REPO_ROOT, read, run


EXPECTED_IMAGE = "ghcr.io/siemens/kas/kas@sha256:11f076b79b84f57cb7d933941ff619f09a7c17e562e1643d13836d5f8d0a92f3"
EXPECTED_WRAPPER_SHA = "9707355d1eba19e334e663ab9fcf6881ac323aed16ff7f4fd7e217f879a3894c"


class CiContractTest(unittest.TestCase):
    def test_container_inputs_are_immutable(self) -> None:
        values = dict(
            line.split("=", 1)
            for line in read("ci/container.env").splitlines()
            if line and not line.startswith("#")
        )
        self.assertEqual(values["KAS_VERSION"], "5.4")
        self.assertEqual(values["KAS_CONTAINER_IMAGE"], EXPECTED_IMAGE)
        self.assertEqual(values["KAS_CONTAINER_SCRIPT_SHA256"], EXPECTED_WRAPPER_SHA)
        self.assertEqual(
            values["KAS_SOURCE_COMMIT"],
            "81bab5294be29de4b64adedce962d36184bfc66f",
        )

    def test_vendored_wrapper_matches_official_5_4_bytes(self) -> None:
        digest = hashlib.sha256((REPO_ROOT / "ci/kas-container").read_bytes()).hexdigest()
        self.assertEqual(digest, EXPECTED_WRAPPER_SHA)

    def test_pipeline_has_only_non_hardware_stages(self) -> None:
        script = read("ci/pipeline.sh")
        for stage in ("unit", "qemu", "rpi5-image"):
            self.assertIn(stage, script)
        for forbidden in ("flash-ssd.sh", "bmaptool", "lsblk", "sudo ", "test-rpi5.sh", "test-camera.sh"):
            self.assertNotIn(forbidden, script)
        self.assertIn("RPI5_CI_CONTAINER=1", script)
        self.assertGreaterEqual(script.count("test-qemu.sh"), 1)

    def test_pipeline_bootstraps_pinned_uv_project(self) -> None:
        script = read("ci/pipeline.sh")
        self.assertIn("https://astral.sh/uv/0.11.31/install.sh", script)
        self.assertIn("UV_NO_MODIFY_PATH=1", script)
        self.assertIn('[[ "$(uv --version)" == "uv 0.11.31" ]]', script)
        self.assertIn("uv lock --check", script)
        self.assertIn("uv sync --locked", script)
        self.assertIn("uv run --locked python", script)

    def test_pipeline_is_valid_bash(self) -> None:
        result = run("bash", "-n", "ci/pipeline.sh")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests and confirm CI files and mode are missing**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_ci_contract.py' -v`

Expected: failures mention `ci/container.env`, `ci/kas-container`, and `ci/pipeline.sh`.

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_host_tools.py' -v`

Expected: the new container-mode test fails.

- [ ] **Step 4: Add an explicit verified-container preflight mode**

Change the usage and argument parser in `scripts/host-preflight.sh`:

```bash
usage() {
    printf 'Usage: %s [--initial|--incremental] [--container] [--key PATH]\n' "$0"
}

mode="--incremental"
container_mode="0"
key_path="$(rpi5_repo_root)/keys/rpi5_admin"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --initial|--incremental) mode="$1"; shift ;;
        --container) container_mode="1"; shift ;;
        --key) key_path="$2"; shift 2 ;;
        --help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done
```

Replace the unconditional Ubuntu check with:

```bash
source /etc/os-release
if [[ "$container_mode" == "1" ]]; then
    [[ -f /.dockerenv || -f /run/.containerenv ]] || \
        rpi5_die "--container requires a real container environment"
else
    [[ "$ID" == "ubuntu" && "$VERSION_ID" == "24.04" ]] || \
        rpi5_die "supported native host is Ubuntu 24.04"
fi
```

Define role-specific command sets before the existing command loop:

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

Replace the direct preflight invocation in `scripts/build.sh` with:

```bash
preflight_args=(--incremental --key "$key_path")
if [[ "${RPI5_CI_CONTAINER:-0}" == "1" ]]; then
    preflight_args+=(--container)
fi
"$repo_root/scripts/host-preflight.sh" "${preflight_args[@]}"
```

The container flag does not waive CPU, memory, swap, free-space, key, tool-version, or kas-version checks. It only replaces the native Ubuntu identity check and omits host-only flash/discovery tools.

- [ ] **Step 5: Pin kas and vendor the byte-exact official wrapper**

```dotenv
# ci/container.env
KAS_VERSION=5.4
KAS_CONTAINER_IMAGE=ghcr.io/siemens/kas/kas@sha256:11f076b79b84f57cb7d933941ff619f09a7c17e562e1643d13836d5f8d0a92f3
KAS_CONTAINER_SCRIPT_SHA256=9707355d1eba19e334e663ab9fcf6881ac323aed16ff7f4fd7e217f879a3894c
KAS_SOURCE_COMMIT=81bab5294be29de4b64adedce962d36184bfc66f
```

Run:

```bash
mkdir -p ci
curl -fsSL https://raw.githubusercontent.com/siemens/kas/5.4/kas-container -o ci/kas-container
printf '%s  %s\n' \
  '9707355d1eba19e334e663ab9fcf6881ac323aed16ff7f4fd7e217f879a3894c' \
  'ci/kas-container' | sha256sum --check --strict
chmod 0755 ci/kas-container
```

Expected: `ci/kas-container: OK`. Any checksum mismatch stops implementation; never update the expected hash without a separately reviewed dependency-update feature.

- [ ] **Step 6: Add the provider-neutral pipeline entry point**

```bash
#!/usr/bin/env bash
# ci/pipeline.sh
set -euo pipefail

source "$(dirname "$0")/../scripts/lib/common.sh"
source "$(dirname "$0")/container.env"

usage() {
    printf 'Usage: %s {unit|qemu|rpi5-image}\n' "$0"
}

[[ $# -eq 1 ]] || { usage >&2; exit 2; }
stage="$1"
repo_root="$(rpi5_repo_root)"
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
export RPI5_CI_CONTAINER=1
created_key="0"

cleanup() {
    if [[ "$created_key" == "1" ]]; then
        rm -f "$repo_root/keys/rpi5_admin" "$repo_root/keys/rpi5_admin.pub"
    fi
}
trap cleanup EXIT INT TERM

ensure_test_key() {
    mkdir -p "$repo_root/keys"
    if [[ -e "$repo_root/keys/rpi5_admin" || -e "$repo_root/keys/rpi5_admin.pub" ]]; then
        rpi5_validate_key_pair "$repo_root/keys/rpi5_admin"
        return
    fi
    ssh-keygen -q -t ed25519 -N '' -f "$repo_root/keys/rpi5_admin" -C ci-rpi5
    chmod 600 "$repo_root/keys/rpi5_admin"
    chmod 644 "$repo_root/keys/rpi5_admin.pub"
    created_key="1"
}

run_unit() {
    uv run --locked python -m unittest discover -s tests/host -p 'test_*.py' -v
    while IFS= read -r script; do
        bash -n "$script"
    done < <(find scripts ci -type f -name '*.sh' -print | LC_ALL=C sort)
}

run_qemu_for_build_id() {
    local build_id="$1"
    "$repo_root/scripts/build.sh" --build-id "$build_id" qemu checkout
    "$repo_root/scripts/build.sh" --build-id "$build_id" qemu parse
    "$repo_root/scripts/build.sh" --build-id "$build_id" qemu build
    "$repo_root/scripts/test-qemu.sh" --build-id "$build_id"
}

case "$stage" in
    unit)
        run_unit
        ;;
    qemu)
        ensure_test_key
        build_id="$($repo_root/scripts/new-build-id.sh)"
        run_qemu_for_build_id "$build_id"
        printf 'BUILD_ID=%s\n' "$build_id"
        ;;
    rpi5-image)
        ensure_test_key
        build_id="$($repo_root/scripts/new-build-id.sh)"
        run_qemu_for_build_id "$build_id"
        "$repo_root/scripts/build.sh" --build-id "$build_id" rpi5-minimal build
        printf 'BUILD_ID=%s\n' "$build_id"
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
```

- [ ] **Step 7: Document the CI service boundary**

````markdown
# Provider-Neutral CI Contract

The CI service must load `ci/container.env`, configure the job image as the exact `KAS_CONTAINER_IMAGE` digest, override the image entry point to run a shell, and run as a non-root UID. Do not substitute a tag. Persist `build/kas-work/build/downloads`, `build/kas-work/build/sstate-cache`, and the profile build directories as protected caches.

Jobs invoke one of:

```bash
./ci/pipeline.sh unit
./ci/pipeline.sh qemu
./ci/pipeline.sh rpi5-image
```

Publish ignored `artifacts/BUILD_ID/` only to access-controlled CI artifact storage. Never publish `keys/`. Each build job creates and removes an ephemeral SSH key. `rpi5-image` intentionally reruns QEMU in the same job so the QEMU and generated image use the same key, build ID, and Git revision.

Each job allows the pinned Astral uv 0.11.31 installer download, keeps the
installer under ignored `.state/uv-bin`, runs `uv lock --check` and
`uv sync --locked`, and then invokes the selected pipeline stage. The uv
binary is a job-local host prerequisite and is never committed or copied
into the target image.

The vendored `ci/kas-container` is the byte-exact official kas 5.4 launcher for local container parity and provenance. CI itself executes inside the pinned image. The container still supplies the Yocto host toolchain; the uv project supplies the exact Python/kas command environment. Hardware flashing, Raspberry Pi tests, camera tests, and release approval remain manual protected stages outside CI.
````

- [ ] **Step 8: Make the pipeline executable and run all offline tests**

Run: `chmod 0755 ci/pipeline.sh`

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_ci_contract.py' -v`

Expected: `Ran 5 tests` followed by `OK`, including the exact wrapper SHA-256.

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_host_tools.py' -v`

Expected: all host tool tests pass.

Run: `./ci/pipeline.sh unit`

Expected: every offline host test and Bash syntax check passes inside the pinned container. The QEMU and image stages are enabled only after this result.

- [ ] **Step 9: Commit the CI unit in English**

```bash
git add scripts/host-preflight.sh scripts/build.sh tests/host/test_host_tools.py ci tests/host/test_ci_contract.py
git commit -m "ci: add pinned kas container pipeline"
```

Expected: merge `feature/kas-container-ci` to `develop`; wire the three generic commands into the selected CI service in a follow-up repository-administration change because this repository currently has no configured remote/provider.

### Task 14: Sanitized Release Evidence Generation

**Feature branch:** `feature/release-evidence`

**Files:**
- Create: `scripts/release_summary.py`
- Create: `tests/host/test_release_summary.py`

**Interfaces:**
- Consumes: the final build ID, current full Git revision, exact layer revisions, both Wic checksums, and all QEMU/minimal-flash/three-reboot/camera-flash/camera-capture PASS markers for that same ID.
- Produces: one deterministic-schema `artifacts/releases/BUILD_ID.json` with no host, network, person, key, device, sample, or raw-log identifiers.

- [ ] **Step 1: Create the feature branch**

```bash
git switch develop
git switch -c feature/release-evidence
```

- [ ] **Step 2: Write failing pure release-summary tests**

```python
# tests/host/test_release_summary.py
import json
from pathlib import Path
import sys
import tempfile
import unittest

from support import REPO_ROOT


sys.path.insert(0, str(REPO_ROOT / "scripts"))
import release_summary  # noqa: E402


PINS = {
    "bitbake": "fae9db3168dbff1b8c76fe9c6726a9687ff97514",
    "openembedded-core": "b5a6cada82d7ffb362bda9081c354dcc0b6ee264",
    "meta-yocto": "824795b885b25e074a2880fbcd54e1a6c875d47d",
    "meta-openembedded": "d97b5602d7f64422c94b7311466cda7f6b1962d5",
    "meta-raspberrypi": "f62c67921474370829d24a4fa01ef88543f3906b",
}
REVISION = "0123456789abcdef0123456789abcdef01234567"
BUILD_ID = "20260722T120000Z-0123456789ab"


class ReleaseSummaryTest(unittest.TestCase):
    def fixture(self, root: Path) -> None:
        lock = root / "kas/lock.yml"
        lock.parent.mkdir(parents=True)
        lock.write_text(
            "header:\n  version: 19\noverrides:\n  repos:\n"
            + "".join(
                f"    {name}:\n      commit: {commit}\n"
                for name, commit in PINS.items()
            ),
            encoding="utf-8",
        )
        base = root / "artifacts" / BUILD_ID
        for marker in release_summary.REQUIRED_MARKERS:
            path = base / marker
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        for profile, image in (
            ("rpi5-minimal", "rpi5-minimal-image-raspberrypi5.rootfs.wic.bz2"),
            ("rpi5-camera", "rpi5-camera-image-raspberrypi5.rootfs.wic.bz2"),
        ):
            metadata = base / profile / "manifests/build-metadata.json"
            metadata.parent.mkdir(parents=True, exist_ok=True)
            metadata.write_text(
                json.dumps({"build_id": BUILD_ID, "project_revision": REVISION}),
                encoding="utf-8",
            )
            sums = base / profile / "checksums/SHA256SUMS"
            sums.parent.mkdir(parents=True, exist_ok=True)
            sums.write_text(f"{'a' * 64}  images/{image}\n", encoding="utf-8")
        revisions = base / "rpi5-camera/manifests/layer-revisions.txt"
        revisions.write_text(
            "".join(f"{name} {commit}\n" for name, commit in PINS.items()),
            encoding="utf-8",
        )
        (base / "rpi5-test/result.json").write_text(
            json.dumps({"build_id": BUILD_ID, "reboots": 3, "result": "PASS"}),
            encoding="utf-8",
        )
        (base / "camera-test/result.json").write_text(
            json.dumps(
                {
                    "build_id": BUILD_ID,
                    "sensor": "imx708",
                    "lens_variant": "wide-operator-verified",
                    "h264": "libx264-1920x1080-30fps",
                    "result": "PASS",
                }
            ),
            encoding="utf-8",
        )

    def test_builds_sanitized_record_from_complete_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            record = release_summary.build_record(
                root, BUILD_ID, REVISION, "2026-07-22T12:00:00Z"
            )
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["build_id"], BUILD_ID)
            self.assertEqual(record["source_revisions"], PINS)
            self.assertEqual(record["validation"]["reboots"], 3)
            self.assertEqual(record["validation"]["camera"], "PASS")
            self.assertEqual(
                record["validation"]["lens_variant"], "wide-operator-verified"
            )
            serialized = json.dumps(record).lower()
            for forbidden in (
                "ip_address",
                "mac_address",
                "serial",
                "private_key",
                "known_hosts",
                "rpiadmin",
            ):
                self.assertNotIn(forbidden, serialized)

    def test_rejects_a_missing_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            (root / "artifacts" / BUILD_ID / "camera-test/PASS").unlink()
            with self.assertRaisesRegex(ValueError, "required marker"):
                release_summary.build_record(
                    root, BUILD_ID, REVISION, "2026-07-22T12:00:00Z"
                )

    def test_rejects_a_layer_revision_different_from_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            revisions = root / "artifacts" / BUILD_ID / "rpi5-camera/manifests/layer-revisions.txt"
            revisions.write_text("bitbake " + "f" * 40 + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source revisions"):
                release_summary.build_record(
                    root, BUILD_ID, REVISION, "2026-07-22T12:00:00Z"
                )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests and confirm the module is missing**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_release_summary.py' -v`

Expected: import failure for `release_summary`.

- [ ] **Step 4: Implement strict aggregation and sanitization**

```python
#!/usr/bin/env python3
# scripts/release_summary.py
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from typing import Any

import yaml


BUILD_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")
REQUIRED_MARKERS = (
    "qemu/COMPLETE",
    "qemu-test/PASS",
    "rpi5-minimal/COMPLETE",
    "flash/rpi5-minimal-PASS",
    "rpi5-test/PASS",
    "rpi5-camera/COMPLETE",
    "flash/rpi5-camera-PASS",
    "camera-test/PASS",
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_pins(root: Path) -> dict[str, str]:
    with (root / "kas/lock.yml").open(encoding="utf-8") as stream:
        lock = yaml.safe_load(stream)
    return {
        name: data["commit"]
        for name, data in lock["overrides"]["repos"].items()
    }


def load_revisions(path: Path) -> dict[str, str]:
    revisions: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        name, commit = line.split()
        revisions[name] = commit
    return revisions


def image_checksum(path: Path) -> dict[str, str]:
    matches: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, filename = line.split(maxsplit=1)
        filename = filename.lstrip("*")
        if filename.endswith(".wic.bz2"):
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(f"invalid SHA-256 in {path}")
            matches.append({"filename": Path(filename).name, "sha256": digest})
    if len(matches) != 1:
        raise ValueError(f"expected one Wic checksum in {path}")
    return matches[0]


def build_record(
    root: Path, build_id: str, project_revision: str, completed_at: str
) -> dict[str, Any]:
    if not BUILD_ID_RE.fullmatch(build_id):
        raise ValueError("invalid build ID")
    if not re.fullmatch(r"[0-9a-f]{40}", project_revision):
        raise ValueError("project revision must be a full Git SHA")
    if not build_id.endswith(project_revision[:12]):
        raise ValueError("build ID does not match project revision")

    base = root / "artifacts" / build_id
    for marker in REQUIRED_MARKERS:
        if not (base / marker).is_file():
            raise ValueError(f"required marker missing: {marker}")

    for profile in ("rpi5-minimal", "rpi5-camera"):
        metadata = load_json(base / profile / "manifests/build-metadata.json")
        if metadata.get("build_id") != build_id:
            raise ValueError(f"{profile} build ID mismatch")
        if metadata.get("project_revision") != project_revision:
            raise ValueError(f"{profile} project revision mismatch")

    pins = load_pins(root)
    revisions = load_revisions(
        base / "rpi5-camera/manifests/layer-revisions.txt"
    )
    if any(revisions.get(name) != commit for name, commit in pins.items()):
        raise ValueError("source revisions do not match kas lock")

    rpi_result = load_json(base / "rpi5-test/result.json")
    camera_result = load_json(base / "camera-test/result.json")
    if rpi_result.get("build_id") != build_id or rpi_result.get("result") != "PASS":
        raise ValueError("Raspberry Pi result mismatch")
    if rpi_result.get("reboots") != 3:
        raise ValueError("exactly three reboots are required")
    if camera_result.get("build_id") != build_id or camera_result.get("result") != "PASS":
        raise ValueError("camera result mismatch")
    if camera_result.get("sensor") != "imx708":
        raise ValueError("camera sensor is not IMX708")
    if camera_result.get("lens_variant") != "wide-operator-verified":
        raise ValueError("Camera Module 3 Wide label was not operator-confirmed")
    if not str(camera_result.get("h264", "")).startswith("libx264-"):
        raise ValueError("camera H.264 mode is not libx264")

    return {
        "schema_version": 1,
        "build_id": build_id,
        "project_revision": project_revision,
        "source_revisions": {name: pins[name] for name in sorted(pins)},
        "images": {
            "rpi5_minimal": image_checksum(
                base / "rpi5-minimal/checksums/SHA256SUMS"
            ),
            "rpi5_camera": image_checksum(
                base / "rpi5-camera/checksums/SHA256SUMS"
            ),
        },
        "validation": {
            "qemu": "PASS",
            "rpi5": "PASS",
            "reboots": 3,
            "camera": "PASS",
            "sensor": "imx708",
            "lens_variant": camera_result["lens_variant"],
            "h264": camera_result["h264"],
        },
        "validation_completed_at": completed_at,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-id", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    if status:
        raise SystemExit("tracked worktree must be clean before release summary")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    completed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    record = build_record(root, args.build_id, revision, completed_at)
    output = root / "artifacts/releases" / f"{args.build_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit(f"release record already exists: {output}")
    output.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(output.relative_to(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run pure tests and a non-mutating help check**

Run: `uv run --locked python -m unittest discover -s tests/host -p 'test_release_summary.py' -v`

Expected: `Ran 3 tests` followed by `OK`.

Run: `uv run --locked python scripts/release_summary.py --help`

Expected: usage is printed; no artifact is created.

- [ ] **Step 6: Commit release evidence tooling in English**

```bash
git add scripts/release_summary.py tests/host/test_release_summary.py
git commit -m "feat: add sanitized release evidence summary"
```

Expected: merge `feature/release-evidence` to `develop` after pure fixture tests pass. Generate the first real JSON only after Task 15 acceptance.

### Task 15: Final Integrated Build, Two-Session Hardware Acceptance, and Promotion

**Feature branch:** `feature/release-acceptance`

**Files:**
- Create after successful validation: `artifacts/releases/BUILD_ID.json`
- Verify only: every source, test, runbook, CI, build, flash, and evidence file from Tasks 1-14.

**Interfaces:**
- Consumes: a clean `develop` containing all merged feature tasks, one USB SSD, Raspberry Pi 5, Camera Module 3 Wide already available for assembly, wired Ethernet, stable 5 V/5 A power, and the local SSH key.
- Produces: QEMU PASS, minimal USB-boot PASS with three reboots, IMX708/JPEG/software-H.264 PASS, a sanitized release JSON, and an explicitly reviewable promotion point.
- Hands-on budget: one initial powered-off assembly/connection session and one later SSD removal/reflash/reconnection session. HDMI is used only after the five-minute remote deadline; microSD is used only for diagnosed EEPROM recovery; USB-to-UART is never required.

- [ ] **Step 1: Confirm all feature work is integrated before assigning a build ID**

```bash
git switch develop
git status --short --branch
git log --first-parent --oneline master..develop
git branch --no-merged develop
```

Expected: the worktree is clean, Tasks 1-14 are present as reviewed merge commits, and no required feature branch appears in the unmerged list. Do not start a release build if any implementation commit is still pending.

Create the acceptance branch without changing the commit:

```bash
git switch -c feature/release-acceptance
test -z "$(git status --porcelain)"
```

- [ ] **Step 2: Run the complete offline and parse gates**

```bash
uv run --locked python -m unittest discover -s tests/host -p 'test_*.py' -v
while IFS= read -r script; do bash -n "$script"; done \
  < <(find scripts ci -type f -name '*.sh' -print | LC_ALL=C sort)
uv run --locked kas dump kas/qemuarm64-minimal.yml >/tmp/rpi5-qemu-final.yml
uv run --locked kas dump kas/rpi5-minimal.yml >/tmp/rpi5-minimal-final.yml
uv run --locked kas dump kas/rpi5-camera.yml >/tmp/rpi5-camera-final.yml
./scripts/host-preflight.sh --initial --key keys/rpi5_admin
```

Expected: every unit/syntax test passes, all three kas configurations dump without mutation, and native host preflight prints PASS. Any failure stops the sequence before a build or device connection.

- [ ] **Step 3: Freeze one clean-commit identity and pass QEMU**

```bash
test -z "$(git status --porcelain)"
BUILD_ID="$(./scripts/new-build-id.sh)"
mkdir -p .state
printf '%s\n' "$BUILD_ID" > .state/active-build-id
./scripts/build.sh --build-id "$BUILD_ID" qemu checkout
./scripts/build.sh --build-id "$BUILD_ID" qemu layers
./scripts/build.sh --build-id "$BUILD_ID" qemu parse
./scripts/build.sh --build-id "$BUILD_ID" rpi5-minimal layers
./scripts/build.sh --build-id "$BUILD_ID" rpi5-minimal parse
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera layers
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera parse
./scripts/build.sh --build-id "$BUILD_ID" qemu build
./scripts/test-qemu.sh --build-id "$BUILD_ID"
test -f "artifacts/$BUILD_ID/qemu-test/PASS"
```

Expected: QEMU reports `PASS qemu`, its guest build ID equals `$BUILD_ID`, key-only login succeeds, root/password login fails, systemd/network/SSH are active, and QEMU exits. Keep the tracked worktree and HEAD unchanged for the rest of this task.

- [ ] **Step 4: Build the minimal Pi image and perform the destructive operator checkpoint**

```bash
./scripts/build.sh --build-id "$BUILD_ID" rpi5-minimal build
(cd "artifacts/$BUILD_ID/rpi5-minimal" && sha256sum --check checksums/SHA256SUMS)
lsblk --bytes --paths -o NAME,TYPE,TRAN,SIZE,MODEL,SERIAL,MOUNTPOINTS
read -r -p 'Exact whole USB SSD device: ' TARGET_DEVICE
test -b "$TARGET_DEVICE"
lsblk --bytes --paths -o NAME,TYPE,TRAN,SIZE,MODEL,SERIAL,MOUNTPOINTS "$TARGET_DEVICE"
read -r -p "Type ERASE:$TARGET_DEVICE:$BUILD_ID: " CONFIRMATION
test "$CONFIRMATION" = "ERASE:$TARGET_DEVICE:$BUILD_ID"
UV_BIN="$(command -v uv)"
test "$("$UV_BIN" --version)" = "uv 0.11.31"
sudo UV_BIN="$UV_BIN" ./scripts/flash-ssd.sh --build-id "$BUILD_ID" --profile rpi5-minimal \
  --device "$TARGET_DEVICE" --confirm "$CONFIRMATION"
test -f "artifacts/$BUILD_ID/flash/rpi5-minimal-PASS"
```

Expected: the operator confirms the model/serial/size and exact whole device twice before the sole write command. The script uses bmaptool, not `dd`, then verifies both partitions and embedded build ID read-only.

- [ ] **Step 5: Perform hands-on session 1 and discover remotely**

With all power removed:

1. Verify the module's physical label/packaging says **Camera Module 3 Wide** and inspect the CSI cable contacts/orientation.
2. Attach the camera to the correct Raspberry Pi 5 camera connector; do not repeatedly reseat it after power-on.
3. Attach the just-verified USB SSD and wired Ethernet.
4. Use an official-equivalent 5 V/5 A (27 W) supply; leave HDMI disconnected initially.
5. Start the command below, press Enter, and immediately apply power once:

```bash
read -r -p 'Press Enter, then immediately apply power to start the first-boot clock: '
BOOT_WAIT_START="$SECONDS"
RPI_IP="$(./scripts/discover-rpi5.sh --hostname rpi5-minimal --timeout 300)"
ssh-keyscan -T 3 -H "$RPI_IP" > .state/rpi5-initial-known-hosts
ssh -i keys/rpi5_admin -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=.state/rpi5-initial-known-hosts "rpiadmin@$RPI_IP" true
BOOT_WAIT_ELAPSED=$((SECONDS - BOOT_WAIT_START))
test "$BOOT_WAIT_ELAPSED" -le 180
printf 'Discovered minimal image at %s\n' "$RPI_IP"
```

Expected: one IP is returned within five minutes and key-only SSH succeeds within 180 seconds. A later SSH response fails phase-1 timing even if discovery eventually succeeds. With no signal by five minutes, stop automated acceptance and perform one HDMI/power inspection. Use `docs/runbooks/eeprom-recovery.md` only when that inspection specifically indicates a bootloader/USB-boot failure; do not add UART or routinely substitute microSD.

- [ ] **Step 6: Pass phase-1 real-hardware acceptance and three reboots**

If a dnsmasq lease file or known MAC is available, append `--lease-file PATH` and/or `--mac ADDRESS`; otherwise mDNS/previous-IP discovery remains sufficient.

```bash
./scripts/test-rpi5.sh --build-id "$BUILD_ID" --host "$RPI_IP"
test -f "artifacts/$BUILD_ID/rpi5-test/PASS"
uv run --locked python -m json.tool "artifacts/$BUILD_ID/rpi5-test/result.json"
RPI_IP="$(cat .state/last-rpi5-ip)"
```

Expected: initial acceptance plus exactly three different boot IDs, each reboot recovered within 120 seconds. Every cycle remains aarch64 Raspberry Pi 5, build-ID matched, systemd running, Ethernet routed, `/dev/sda2` on USB transport, writable, and root/password SSH denied.

- [ ] **Step 7: Build the gated camera image before the only SSD swap**

Keep the validated Pi connected while the x86 host builds; this avoids an extra physical cycle.

```bash
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera build
(cd "artifacts/$BUILD_ID/rpi5-camera" && sha256sum --check checksums/SHA256SUMS)
CAMERA_MANIFEST=("artifacts/$BUILD_ID/rpi5-camera/manifests/"*.manifest)
test "${#CAMERA_MANIFEST[@]}" -eq 1
grep -Eq '^libcamera-apps ' "${CAMERA_MANIFEST[0]}"
grep -Eq '^rpidistro-ffmpeg ' "${CAMERA_MANIFEST[0]}"
grep -Eq '^x264 ' "${CAMERA_MANIFEST[0]}"
ssh -i keys/rpi5_admin -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile="artifacts/$BUILD_ID/rpi5-test/known_hosts" \
  "rpiadmin@$RPI_IP" sudo -n /usr/bin/systemctl poweroff
```

Expected: the camera build gate sees phase-1 PASS, the manifest contains the intended libcamera/FFmpeg/x264 packages, and the Pi powers off. Wait until activity stops and remove power before touching the SSD.

- [ ] **Step 8: Perform hands-on session 2, guarded camera reflash, and reconnection**

Disconnect only the SSD from the powered-off Pi and connect it to the x86 host. Device names may change, so resolve it from scratch:

```bash
lsblk --bytes --paths -o NAME,TYPE,TRAN,SIZE,MODEL,SERIAL,MOUNTPOINTS
read -r -p 'Exact whole USB SSD device after reconnection: ' TARGET_DEVICE
test -b "$TARGET_DEVICE"
lsblk --bytes --paths -o NAME,TYPE,TRAN,SIZE,MODEL,SERIAL,MOUNTPOINTS "$TARGET_DEVICE"
read -r -p "Type ERASE:$TARGET_DEVICE:$BUILD_ID: " CONFIRMATION
test "$CONFIRMATION" = "ERASE:$TARGET_DEVICE:$BUILD_ID"
UV_BIN="$(command -v uv)"
test "$("$UV_BIN" --version)" = "uv 0.11.31"
sudo UV_BIN="$UV_BIN" ./scripts/flash-ssd.sh --build-id "$BUILD_ID" --profile rpi5-camera \
  --device "$TARGET_DEVICE" --confirm "$CONFIRMATION"
test -f "artifacts/$BUILD_ID/flash/rpi5-camera-PASS"
```

Remove the SSD safely, reconnect it to the unchanged Pi/camera/Ethernet assembly, reapply power once, and do not move the live CSI cable.

- [ ] **Step 9: Pass Camera Module 3 Wide acceptance remotely**

```bash
RPI_IP="$(./scripts/discover-rpi5.sh --hostname rpi5-camera --timeout 300)"
./scripts/test-camera.sh --build-id "$BUILD_ID" --host "$RPI_IP" \
  --wide-label-confirmed
test -f "artifacts/$BUILD_ID/camera-test/PASS"
uv run --locked python -m json.tool "artifacts/$BUILD_ID/camera-test/result.json"
(cd "artifacts/$BUILD_ID/camera-test/samples" && sha256sum --check SHA256SUMS)
```

Expected: IMX708/media topology is present, autofocus JPEG and 10-second 1920x1080 30 fps software-libx264 H.264 are retrieved with matching hashes, temperature stays below 85 C, and IMX708/JPEG still work after one reboot. A failure leaves camera PASS absent and blocks release evidence.

- [ ] **Step 10: Generate, inspect, and commit only the sanitized release record**

```bash
test -z "$(git status --porcelain --untracked-files=no)"
uv run --locked python scripts/release_summary.py --build-id "$BUILD_ID"
RELEASE_JSON="artifacts/releases/$BUILD_ID.json"
uv run --locked python -m json.tool "$RELEASE_JSON"
uv run --locked python - "$RELEASE_JSON" <<'PY'
import json
import sys

record = json.load(open(sys.argv[1], encoding="utf-8"))
forbidden = {
    "ip", "ip_address", "mac", "mac_address", "serial", "device",
    "private_key", "public_key", "known_hosts", "user", "username",
    "sample", "journal", "console_log",
}

def keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key.lower()
            yield from keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from keys(child)

found = forbidden.intersection(keys(record))
if found:
    raise SystemExit(f"forbidden release keys: {sorted(found)}")
PY
git add "$RELEASE_JSON"
git diff --cached --check
git diff --cached -- "$RELEASE_JSON"
git commit -m "release: record validated Raspberry Pi 5 image"
```

Expected: exactly one small JSON file is staged and committed; raw logs, media, keys, device identity, and IP data remain ignored. The JSON's `project_revision` is the pre-evidence commit whose first 12 characters appear in `$BUILD_ID`.

- [ ] **Step 11: Merge acceptance evidence and define the controlled promotion point**

```bash
git switch develop
git merge --no-ff feature/release-acceptance
uv run --locked python -m json.tool "artifacts/releases/$BUILD_ID.json"
git status --short --branch
```

Expected: `develop` is clean and retains the complete English functional/merge history. Do not delete `feature/release-acceptance` until external artifact retention and review are confirmed.

Promotion to `master` requires explicit human approval of the release JSON, raw evidence location/retention, and the H.264 licensing review. After that approval only:

```bash
VALIDATED_REVISION="$(uv run --locked python -c 'import json,sys; print(json.load(open(sys.argv[1]))["project_revision"])' "artifacts/releases/$BUILD_ID.json")"
git tag -a "rpi5-$BUILD_ID" "$VALIDATED_REVISION" \
  -m "Validated Raspberry Pi 5 camera image $BUILD_ID"
git switch master
git merge --no-ff develop
git status --short --branch
```

Expected: the annotated tag points to the exact validated source revision, while `master` also contains the following sanitized evidence commit. No push is attempted because no remote/provider is configured.

## Stop/Go Matrix

| Gate | GO evidence | On failure |
|---|---|---|
| Offline contracts | all `unittest` and Bash syntax checks pass | Fix on the responsible feature branch; do not create a build ID. |
| Configuration | all kas dumps/parses pass with exact lock SHAs | Do not build or update pins implicitly. |
| QEMU | `qemu-test/PASS` for the active build ID | Do not build any Pi image. |
| Minimal image/flash | checksum, COMPLETE, guarded flash PASS | Do not power the Pi with that SSD. |
| Remote phase 1 | USB root, security, network, and three-reboot PASS | Do not build/flash the camera profile; collect bounded diagnostics. |
| Camera image/flash | phase-1 gate, checksum, package manifest, guarded flash PASS | Do not run or record camera acceptance. |
| Camera runtime | IMX708, JPEG, libx264 H.264, thermal, retrieval, reboot PASS | Do not generate release JSON. |
| Release | sanitized JSON, license review, retained raw evidence | Keep `develop`; do not tag, promote, distribute, or push. |

## Plan Completion Criteria

The implementation is complete only when all Tasks 1-14 have English functional commits on feature branches merged to `develop`, Task 15 has produced every PASS marker for one unchanged source revision/build ID, the two planned hands-on sessions are recorded, the sanitized release JSON is reviewed, and the approved promotion command succeeds. QEMU success alone never represents Raspberry Pi or camera success, and EEPROM/microSD recovery never becomes the normal boot path.
