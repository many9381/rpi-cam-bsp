# Build Setup and Optional QEMU Validation

This runbook prepares the x86_64 host for image builds and optional QEMU
validation. Pi builds, SSD installation and hardware acceptance do not require
a QEMU image or PASS marker. QEMU commands below run only when explicitly invoked.

The Pi build may still use `qemu-native` as a host tool for target post-install
processing. That dependency does not build or boot a separate QEMU image.
Run it from the repository root. Do not change commits while a build ID is
active.

## Build command arguments

`build.sh` accepts `[--build-id ID] PROFILE ACTION`. The build ID identifies
one build run and has the form `YYYYMMDDTHHMMSSZ-<12-character Git SHA>`.
The profile selects `qemu`, `rpi5-minimal`, `rpi5-camera` or
`rpi5-camera-hailo`; the action is `checkout`, `layers`, `parse` or `build`.
For example, `--build-id rpi5-camera-hailo build` is invalid because an image
profile is not a build ID and the separate profile argument is missing.

Start a new build directly with an explicit ID; QEMU and hardware PASS records
are not required for image generation:

```bash
BUILD_ID="$(./scripts/new-build-id.sh)"
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera-hailo build
```

If `.state/active-build-id` already identifies the run to continue, the ID can
be omitted from `build.sh`:

```bash
./scripts/build.sh --help
./scripts/build.sh rpi5-camera-hailo build
# Equivalent explicit form:
BUILD_ID="$(cat .state/active-build-id)"
./scripts/build.sh --build-id "$BUILD_ID" rpi5-camera-hailo build
```

The short form only reads the active ID; it does not create or replace it.
An explicit `--build-id` takes precedence. Missing/invalid active IDs and IDs
from another Git revision are rejected. Both forms build the selected profile
after host preflight without checking runtime acceptance records. Image
generation does not create QEMU or hardware PASS records. Flashing, device
validation and release acceptance use their own prerequisite checks.

## One-time host setup

The supported host is Ubuntu 24.04 with at least 4 logical CPUs, 32 GiB RAM,
4 GiB swap, and the free space enforced by the preflight script.

```bash
sudo apt-get update
sudo apt-get install -y build-essential chrpath cpio debianutils diffstat file \
  gawk gcc git iputils-ping libacl1 liblz4-tool locales make python3 \
  python3-git python3-jinja2 python3-pexpect python3-subunit socat tar texinfo \
  unzip wget xz-utils zstd bmap-tools openssh-client \
  avahi-utils curl ffmpeg iproute2 parted util-linux udev
sudo locale-gen en_US.UTF-8
if ! command -v uv >/dev/null 2>&1 ||
   [[ "$(uv --version | awk '{print $2}')" != "0.11.31" ]]; then
    curl -LsSf https://astral.sh/uv/0.11.31/install.sh |
        env UV_NO_MODIFY_PATH=1 UV_INSTALL_DIR="$HOME/.local/bin" sh
    export PATH="$HOME/.local/bin:$PATH"
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
if [[ ! -e keys/rpi5_admin && ! -e keys/rpi5_admin.pub ]]; then
    ssh-keygen -t ed25519 -f keys/rpi5_admin -C rpi5-admin
fi
chmod 600 keys/rpi5_admin
chmod 644 keys/rpi5_admin.pub
./scripts/host-preflight.sh --initial --key keys/rpi5_admin
```

The private key never enters an image or evidence directory. The public key is
injected at build time, and both local key files are ignored by Git.

## Optional final-commit QEMU validation

Start only from a clean `develop` worktree:

```bash
test "$(git branch --show-current)" = "develop"
test -z "$(git status --porcelain)"
BUILD_ID="$(./scripts/new-build-id.sh)"
./scripts/build.sh --build-id "$BUILD_ID" qemu checkout
./scripts/build.sh --build-id "$BUILD_ID" qemu layers
./scripts/build.sh --build-id "$BUILD_ID" qemu parse
./scripts/build.sh --build-id "$BUILD_ID" qemu build
./scripts/test-qemu.sh --build-id "$BUILD_ID"
test -f "artifacts/$BUILD_ID/qemu-test/PASS"
mkdir -p .state
printf '%s\n' "$BUILD_ID" > .state/active-build-id
```

Expected result: `PASS qemu`. This marker records the optional QEMU check;
flashing, Pi acceptance and release summaries do not require it. When omitted,
the release summary records QEMU as `NOT_RUN`.
The runner uses localhost port 2222 and must leave no QEMU process behind.

Continue with [USB SSD build and flash](usb-ssd-bringup.md).
