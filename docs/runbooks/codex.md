# Codex CLI on the camera image

Both `rpi5-camera` and `rpi5-camera-hailo` select `codex-cli` explicitly through
`IMAGE_INSTALL` in `kas/rpi5-camera.yml` for development and review. It is not
an `RDEPENDS` entry of the camera firmware package group. Minimal Raspberry Pi
and QEMU images remain unchanged. Build the selected camera profile with a
valid build ID. Image generation does not require runtime PASS records;
flashing and hardware acceptance are separate stages with their own prerequisites.

## Package boundary

`recipes-devtools/codex-cli/codex-cli.bb` installs the latest stable official
`aarch64-unknown-linux-musl` release of Codex at build time. Both camera
profiles inherit `codex-latest`, which queries the
[GitHub latest-release API](https://docs.github.com/en/rest/releases/releases#get-the-latest-release)
before BitBake parses recipes. Drafts and prereleases are rejected. The
selected release becomes the actual package `PV`; its versioned download URL
and GitHub-provided SHA-256 distinguish it from older downloads and sstate.
License/notice files come from the commit resolved from that same release tag,
with SHA-256 checksums computed when resolving the release. Existing
`LIC_FILES_CHKSUM` checks remain active: upstream license/notice changes still
require review. This is a prebuilt-binary recipe for little-endian AArch64 Linux.

Resolution uses BitBake's revision cache to share one selection between the
cooker and task workers. A new BitBake invocation clears that selection and
checks latest again; `BB_SRCREV_POLICY` must be `clear` (the default). Use the
default non-persistent BitBake server so each invocation refreshes configuration.
The build host needs HTTPS access to `api.github.com`, `github.com` and
`raw.githubusercontent.com`. Network/API failures, rate limits, missing assets
or missing checksums stop configuration instead of silently shipping an older
version. Offline camera configuration is therefore unsupported. QEMU and
minimal profiles do not inherit this class or query Codex releases. For a
standalone `bitbake codex-cli` build, also add `INHERIT += "codex-latest"` to
the build configuration.

The CLI is installed as an isolated package under `/usr/lib/codex/`:

- `bin/codex` and `bin/codex-code-mode-host`
- `codex-package.json`, the upstream package manifest
- `codex-path/rg` and `codex-resources/bwrap`, required by daemon preparation

`/usr/bin/codex` and `/usr/bin/codex-code-mode-host` link to these executables.
Codex resolves its real executable path to find the package. The daemon copies
this tree into the user's home on first use; putting the manifest directly in
`/usr/` would incorrectly make the entire `/usr/` tree its source package.
Resource links pointing outside the package are rejected by upstream.

They do not need Node.js, npm, a target Rust compiler or a musl dynamic loader.
Binary sizes vary by release; runtime dependencies add further space.
Upstream LICENSE/NOTICE and the vendored MIT
notices are installed under `/usr/share/licenses/codex-cli/`.

The release's `bwrap` bytes are preserved because Codex verifies their embedded
digest when using the bundled sandbox. Its LGPL notice and the bundled
ripgrep MIT notice are included with the other licenses. Optional bundled zsh
and voice resources are omitted. Yocto also supplies system `bubblewrap`,
`ripgrep`, Bash, Git, CA certificates and basic terminal definitions.
No boot service, user configuration, pretrusted directory, API key or login
cache is installed by the recipe. Normal interactive startup can create a
user-owned background server and its updater under `~/.codex/`; those are
upstream runtime behavior, separate from the image-managed CLI.
Rebuild and deploy the camera image to update Codex; no recipe version edit is
needed. Already flashed devices keep their installed version until updated.
The image package manifest and `codex --version` identify the version installed
in that image; an unchanged project Git revision can now select a newer Codex
release on a later build.

## First use over SSH

Use the existing unprivileged `rpiadmin` account. An OpenAI connection and
account access are required for OpenAI-backed work; installing the CLI does
not install a local model or provide an account subscription. Follow the
[official CLI guide](https://learn.chatgpt.com/docs/codex/cli).

Camera SSDs installed with this project's default flash command already have
the host's login cache. Connect as `rpiadmin` and run `codex`. The login flow
below is for installations made with `--skip-codex-auth` or another flashing
tool, or when the cached login has been revoked.

To sign in manually after connecting over SSH with a terminal, run:

```bash
codex --version
umask 077
codex login --device-auth
mkdir -p "$HOME/work"
cd "$HOME/work"
codex --sandbox workspace-write --ask-for-approval on-request
```

Complete device-code login in a browser on another machine. It must be enabled
for your account/workspace. If it is unavailable, the official authentication
guide also describes forwarding the login callback over SSH. For API-key
authentication, provision `OPENAI_API_KEY` securely at runtime and use
`printenv OPENAI_API_KEY | codex login --with-api-key`; do not put its value in
a recipe, kas file, command argument, shell history or Git. See
[headless authentication](https://learn.chatgpt.com/docs/auth#login-on-headless-devices).

The user's home directory is writable persistent state. Treat the resulting
`~/.codex/auth.json` and Codex session logs as sensitive. They are per-user
runtime files, not deployment artifacts or acceptance evidence. Do not copy
the build host's Codex account/configuration onto the image.

## Reuse the build host's current ChatGPT login

The [official headless authentication guide](https://learn.chatgpt.com/docs/auth#fallback-authenticate-locally-and-copy-your-auth-cache)
supports copying a cached ChatGPT login to a trusted headless machine. This
project restores that cache onto the SSD **after image writing**, separately
from the Yocto package and image. No authentication file is added to `SRC_URI`,
the build rootfs, WIC download, package output or sstate.

### Automatic restoration during SSD installation

For `rpi5-camera` and `rpi5-camera-hailo`, `scripts/flash-ssd.sh` automatically:

1. Reads the current login from the sudo caller's `~/.codex/auth.json`, using
   the account identified by `SUDO_UID` rather than root's `HOME`. The file must
   belong to that caller, have mode `0600`, and contain a refreshable ChatGPT
   login. Missing or invalid credentials stop the operation before SSD erasure.
2. Holds a snapshot in the flasher's private temporary directory, which is
   removed by the existing exit cleanup. Each flash reads the current source;
   it does not reuse the older `keys/codex-auth.json` SSH snapshot.
3. Writes and verifies the selected image, then checks the device identity
   again and restores the snapshot onto the mounted SSD at
   `/home/rpiadmin/.codex/auth.json`. The image's account UID/GID are used;
   the directory is `0700` and the file is `0600`. Symlinked credential paths,
   incorrect build IDs and unexpected target accounts are rejected.
4. Unmounts the SSD, mounts it read-only, and verifies the restored bytes,
   owner and permissions before recording flash PASS. The non-secret flash
   JSON records `codex_auth_restored: true`; it contains no credentials.

The compressed image and its checksums remain unchanged. Only the installed
SSD receives personal credentials, and Codex can use them on its first boot.
Rebuilding requires no login-file copy; reinstalling through the same flash
script repeats restoration automatically. Minimal and QEMU images do not
receive Codex credentials.

Use `--codex-auth-file /absolute/path/auth.json` when the host uses a custom
`CODEX_HOME` or an explicit source file. Under sudo the file must still belong
to the invoking user. A direct root invocation reads root's cache unless an
explicit root-owned source is selected. Use `--skip-codex-auth` to deliberately
install a camera SSD without personal credentials; it is mutually exclusive
with `--codex-auth-file`. Other imaging tools do not run this restoration step.

The installation check verifies the cache file, not an online account request.
As with normal Codex use, revoked sessions or refresh conflicts can require
authentication again. Keep the host login current before installing a device.

### Restore an already running Pi over SSH

Connect once using the project's admin key and confirm the Pi's SSH host key.
For example, with `RPI_IP` set to the verified device address:

```bash
mkdir -p .state
ssh -i keys/rpi5_admin -o UserKnownHostsFile=.state/codex-known-hosts \
    "rpiadmin@$RPI_IP" true
./scripts/provision-codex-auth.sh --host "$RPI_IP"
```

The provisioner reads `${CODEX_HOME:-$HOME/.codex}/auth.json` on the build
host, validates a refreshable ChatGPT login and saves a private snapshot at
`keys/codex-auth.json`. It requires mode `0600`, checks that the snapshot is
Git-ignored and untracked, and never places tokens in command arguments or
logs. `--auth-file`, `--key`, `--port` and `--known-hosts` allow explicit paths
and SSH settings. It rejects unknown or changed SSH host keys.

On the Pi it atomically replaces `/home/rpiadmin/.codex/auth.json` only after
checking the transferred bytes. The directory is `rpiadmin`-owned with mode
`0700`, and the file is mode `0600`. It leaves the user's Codex configuration,
project trust, conversation history and sandbox settings unchanged. The
current setup uses the default file credential store; an explicit `keyring`
or `ephemeral` store, or a different target `CODEX_HOME`, must be resolved
before using this method.

After provisioning, run `codex` as `rpiadmin`; do not run `codex login` on
every invocation. Use `codex login status` to check whether the local cache
is recognized. This check does not make an authenticated model request.
Codex updates its persistent credentials during normal use. Expired/revoked
sessions or refresh conflicts can still require fresh authentication; this
is not a permanent-login guarantee. Rerun the SSH provisioner to replace the
Pi's login, or after installing with a tool that did not restore it. The local
SSH snapshot is not kept synchronized in the background.

Only work in directories you intend Codex to inspect and modify. Keep device
credentials and the camera application's provisioned security material outside
the coding workspace. The existing restricted `rpiadmin` sudo policy remains
unchanged; this package does not grant Codex root access.

## Sandbox and device checks

Linux command sandboxing uses Bubblewrap and kernel namespaces/seccomp. The
inspected Raspberry Pi kernel configuration already enables namespaces,
`CONFIG_USER_NS`, `CONFIG_SECCOMP` and `CONFIG_SECCOMP_FILTER`. No kernel,
sysctl, AppArmor, sudo or sandbox policy is weakened by this recipe. See the
[official sandbox documentation](https://learn.chatgpt.com/docs/sandboxing).

After booting the rebuilt camera image, check as `rpiadmin`:

```bash
codex --version
command -v bwrap rg git bash
codex sandbox -- /bin/true
codex app-server daemon start
codex app-server daemon version
codex
```

Then log in and run a small read-only request in a disposable working directory.
This checks the actual device sandbox, TLS connectivity, authentication and
model access. A host or device policy can still reject user namespace creation;
diagnose the specific policy instead of adding an unsandboxed/default-root
workaround to the image. Installing Codex on the target does not fix the build
host's existing BitBake user-namespace restriction.

Check that ordinary `codex` reaches its interactive screen without requesting
login when the cache was restored. `--version`, `doctor`, and `exec` alone do
not exercise daemon package preparation. On an older image that reports
`this CLI has no complete local package`, use `codex --no-daemon` temporarily
(or `codex --no-daemon resume ...` / `codex --no-daemon fork ...`), then rebuild
and install an image with the complete package layout.

The packaging tests execute the recipe's install function and check the
manifest, daemon resources, public links, helper, licenses, permissions and
exclusions. Metadata/fetch/unpack and ARM64
startup checks are separate from full BitBake package QA/image assembly and
authenticated device acceptance; they must not be recorded as hardware PASS.

After checking out the pinned BitBake sources, run
`python3 tests/integration/test_codex_bitbake.py` to verify release refresh,
worker cache consistency and offline policy against its actual fetcher cache.
This integration test uses synthetic releases and does not access the network.
