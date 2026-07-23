# uv 기반 Python 환경 전환 설계

## 목적

이 저장소의 Python 가상환경과 호스트 빌드 도구 의존성을 `uv` 프로젝트
모드로 통일한다. `pyproject.toml`이 직접 의존성의 단일 기준이 되고,
`uv.lock`이 전이 의존성의 정확한 버전을 고정한다. 각 Git worktree는
자신의 프로젝트 루트에 있는 `.venv`를 사용한다.

## 현재 상태

- Python 3.12.3 시스템 인터프리터를 사용한다.
- `requirements-build.txt`가 `kas==5.4`만 고정한다.
- 기존 활성 구현 worktree의 `.venv`는 `python3 -m venv --without-pip`으로
  만들어졌고, 별도 pip zipapp으로 패키지가 설치됐다.
- 설계서와 구현 계획의 호스트 명령은 `.venv/bin/activate`와 직접
  `python`/`kas` 실행을 전제로 한다.
- `uv` 실행 파일은 현재 호스트에 설치돼 있지 않다.

## 설계 결정

### 프로젝트 형식

저장소는 배포 가능한 Python 패키지가 아니라 Yocto 빌드·검증 도구
모음이므로 uv의 비패키지 프로젝트로 선언한다.

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

`kas`는 제품 런타임 의존성이 아니므로 `project.dependencies`가 아닌
`dependency-groups.build`에 둔다. `build`를 기본 그룹으로 지정해
`uv sync --locked`와 `uv run --locked`가 별도 그룹 옵션 없이 동일한
도구 집합을 사용하게 한다.

### 잠금 파일과 Python 버전

- `uv.lock`은 uv가 생성·갱신하며 수동으로 편집하지 않는다.
- `uv.lock`을 Git에 커밋해 kas와 모든 전이 의존성의 해석 결과를
  재현한다.
- `.python-version`에는 `3.12`를 기록한다.
- `python-preference = "only-system"`으로 설정해 uv가 예고 없이 별도
  Python 배포판을 내려받지 않게 한다.
- `required-version = "==0.11.31"`로 lockfile 생성기와 동기화 동작을
  고정한다.

### 가상환경 위치

uv의 기본 프로젝트 환경 위치를 사용한다. 따라서 `.venv`는 항상
`pyproject.toml`과 같은 프로젝트 루트에 생성된다.

- 기본 checkout:
  `/home/many/yocto-rpi5-cam-firmware/.venv`
- linked worktree:
  `WORKTREE_ROOT/.venv`

여러 worktree가 하나의 `.venv`를 공유하지 않는다. `.venv/`는 계속
Git에서 제외한다. 이 위치 계약은 논리 경로가 아니라 physical checkout
경로를 기준으로 검증한다.

- `UV_PROJECT_ENVIRONMENT`가 비어 있지 않으면 즉시 실패한다.
- `<physical repository root>/.venv`가 실제 디렉터리여야 하며 symlink를
  허용하지 않는다.
- `realpath .venv`는 `$(pwd -P)/.venv`와 정확히 같아야 한다.
- 실행 중인 `sys.prefix`의 physical 경로도 같은 디렉터리여야 한다.

### uv 설치 정책

uv 실행 파일은 저장소에 vendor하지 않는다. 호스트에 uv가 없으면
Astral의 버전 지정 standalone installer로 uv 0.11.31을 사용자 실행
경로에 설치한다. 설치 시 `UV_NO_MODIFY_PATH=1`을 사용해 shell 시작
파일을 수정하지 않는다.

```bash
curl -LsSf https://astral.sh/uv/0.11.31/install.sh |
  env UV_NO_MODIFY_PATH=1 sh
command -v uv
uv --version
```

installer가 출력한 사용자 실행 경로가 현재 `PATH`에 없다면 해당 경로를
현재 shell의 `PATH`에만 추가한다. 로그인 shell 설정 파일은 자동으로
변경하지 않는다. 이후 host preflight는 `uv`가 `PATH`에 있고 정확히
0.11.31인지 검사한다.

프로젝트의 `required-version` 검사는 잘못된 uv 버전으로 lockfile이나
환경을 갱신하는 것을 차단한다. uv 자체 설치는 호스트 선행조건이며
`.venv`의 내용에는 포함하지 않는다.

### 권한 상승 flash의 uv 신뢰 경계

root로 실행되는 flash 스크립트는 사용자 선택 실행 파일이나 `UV_BIN`을
입력으로 받지 않는다. `--version`만 위조하는 spoofed executable은
인증된 입력이 아니며 절대로 root로 실행하지 않는다. 대신 다음 공식
GNU x86_64 release archive를 고정한다.

- URL:
  `https://releases.astral.sh/github/uv/releases/download/0.11.31/uv-x86_64-unknown-linux-gnu.tar.gz`
- SHA-256:
  `8cc1cd82d434ec565376f98bd938d4b715b5791a80ff2d3aa78821cf85091b4b`
- Official release:
  `https://github.com/astral-sh/uv/releases/tag/0.11.31`

일반 사용자 runbook은 archive를 저장소의 ignored `.state/` 아래로
다운로드하고 SHA-256을 먼저 확인한다. `sudo`에는 absolute archive
경로인 `UV_ARCHIVE`만 전달한다. root 스크립트는 누락, 일반 파일이 아닌
입력, symlink를 거부하고 다음 순서를 지킨다.

1. root-owned private 임시 디렉터리를 만들고 archive bytes를 그 안으로
   먼저 복사한다.
2. 복사본의 exact SHA-256을 실행 없이 확인한다.
3. ownership과 permission을 보존하지 않는 안전한 tar 옵션으로 인증된
   복사본을 풀어 expected `uv-x86_64-unknown-linux-gnu/uv`만 선택한다.
4. 선택한 파일이 symlink가 아닌 root-owned 일반 파일인지 확인하고
   mode `0700`으로 제한한다.
5. 그 뒤에만 `uv --version`을 보조 검사하고 모든 privileged
   `uv run --locked` 호출에 같은 private executable을 사용한다.
6. 정확히 생성한 private 임시 객체만 정리한다.

root network download, `sudo -E`, 사용자 경로의 실행 파일 실행은
허용하지 않는다.

## 파일 변경

### 추가

- `pyproject.toml`
- `uv.lock`
- `.python-version`
- `tests/host/test_uv_environment_contract.py`

### 제거

- `requirements-build.txt`

### 갱신

- `.gitignore`
- `tests/host/test_repository_contract.py`
- `docs/superpowers/specs/2026-07-22-rpi5-yocto-build-validation-design.md`
- `docs/superpowers/plans/2026-07-22-rpi5-yocto-firmware-implementation.md`
- 이후 추가되는 호스트 스크립트, runbook, CI 명령

`requirements-build.txt`는 호환성 파일로 남기지 않는다. 직접 의존성
기준을 두 개 유지하면 pyproject와 requirements 파일이 서로 달라질 수
있기 때문이다.

## 운영 흐름

### 최초 설정

```bash
uv lock --check
uv sync --locked
uv run --locked kas --version
```

커밋된 lockfile이 pyproject와 맞지 않으면 `uv lock --check` 또는
`uv sync --locked`가 실패한다. 정상인 경우 uv가 프로젝트 루트의
`.venv`를 만들고 잠긴 의존성을 정확히 동기화한다.

### 명령 실행

가상환경 활성화를 작업 절차에 포함하지 않는다.

```bash
uv run --locked python -m unittest discover -s tests/host -v
uv run --locked kas dump kas/qemuarm64-minimal.yml
uv run --locked kas shell kas/qemuarm64-minimal.yml -c 'bitbake -p'
```

`uv run --locked`는 명령 실행 전에 프로젝트 환경과 lockfile 계약을
확인한다. 직접 `.venv/bin/python`, `.venv/bin/kas`, `pip`, `uv pip
install`을 사용하는 절차는 추가하지 않는다.

### 의존성 갱신

직접 의존성 변경은 `uv add --group build PACKAGE` 또는
`uv remove --group build PACKAGE`로 수행한다. 승인된 변경 후
`pyproject.toml`과 `uv.lock`을 같은 커밋에 포함하고 전체 호스트
테스트를 다시 실행한다.

## 기존 환경 마이그레이션

1. 삭제 대상이 프로젝트/worktree 루트의 `.venv`이고 내부에
   `pyvenv.cfg`가 있는지 확인한다. fixed literal 경로, non-symlink,
   physical 경로, exact `pyvenv.cfg` provenance, 현재 사용자 ownership,
   대상 이하 mount 부재를 모두 기계적으로 검증한다.
2. 기존 `.venv`만 삭제한다. 외부 checkout, 다운로드 캐시,
   sstate-cache에는 손대지 않으며 one-filesystem 삭제만 사용한다.
3. 고정된 uv 0.11.31을 설치하거나 기존 실행 파일의 버전을 확인한다.
4. `pyproject.toml`, `.python-version`, `uv.lock`을 준비한다.
5. `uv sync --locked`로 해당 worktree의 새 `.venv`를 생성한다.
6. Task 4 구현 worktree에도 uv 변경을 통합한 뒤 같은 명령으로
   `.venv`를 별도로 재생성한다.

## 오류 처리

- uv 미설치: 설치 절차를 출력하고 즉시 실패한다.
- uv 버전 불일치: `required-version` 검사가 실패하며 lockfile을
  변경하지 않는다.
- 시스템 Python 3.12 부재: managed Python을 자동 다운로드하지 않고
  즉시 실패한다.
- pyproject/lock 불일치: `--locked` 또는 `uv lock --check`가 실패한다.
- dependency resolution 실패: 기존 `uv.lock`을 보존하고 변경을
  커밋하지 않는다.
- `.venv`가 프로젝트 루트 밖을 가리키는 경우: 환경을 사용하지 않고
  잘못된 경로를 보고한다.
- `.venv` symlink 또는 비어 있지 않은 `UV_PROJECT_ENVIRONMENT`: 환경을
  만들거나 사용하기 전에 즉시 실패한다.

## 검증

### 오프라인 저장소 계약

Python 표준 라이브러리 `tomllib` 기반 테스트가 다음을 검증한다.

- Python 범위가 `>=3.12,<3.13`이다.
- 프로젝트가 `package = false`이다.
- `build` 그룹이 정확히 `kas==5.4`를 포함한다.
- 기본 그룹이 `build`이다.
- uv 요구 버전이 `==0.11.31`이다.
- 시스템 Python만 사용한다.
- `uv.lock`이 추적되며 kas 5.4와 해석된 전이 의존성을 포함한다.
- lock의 top-level Python 요구가 `==3.12.*`이고 virtual root metadata,
  build group, unique package names가 정확하다.
- kas에서 재귀적으로 도달 가능한 registry closure가 lock의 모든
  registry package와 같고 각 sdist/wheel에 SHA-256이 있다.
- `requirements-build.txt`가 존재하지 않는다.
- `.venv/`가 Git에서 제외된다.

### uv 통합 검증

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
"$UV" run --locked python -m unittest discover -s tests/host -v
git diff --check
git status --short
```

합격 조건은 uv 0.11.31, kas 5.4, 프로젝트 루트 `.venv`, 전체 호스트
테스트 성공, lockfile 무변경, 깨끗한 Git 상태다.

## Git 통합

- 통합 기준: `develop`
- 기능 브랜치: `feature/uv-python-environment`
- 설계·계획·구현은 기능 경계별 영문 Conventional Commit으로 기록한다.
- uv 전환을 먼저 `develop`에 통합한 뒤 진행 중인
  `feature/image-recipes`에 `develop`을 병합한다.
- AppArmor 사용자 namespace 차단은 uv 전환 범위가 아니다. Task 4의
  live BitBake 검증은 관리자 정책이 허용된 후 재개한다.

## 비목표

- kas 5.4 또는 Yocto 레이어 pin 변경
- Python 패키지 빌드·배포
- uv binary vendor
- 전역 또는 worktree 간 `.venv` 공유
- AppArmor/sysctl 자동 변경
- BitBake 빌드 산출물·다운로드·sstate 삭제
