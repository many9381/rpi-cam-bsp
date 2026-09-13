# Codex CLI on the camera image

Both `rpi5-camera` and `rpi5-camera-hailo` include `codex-cli` through their
common camera package group. Minimal Raspberry Pi and QEMU images remain
unchanged. Build and flash the selected camera profile using the existing
build-ID and hardware acceptance gates; this addition does not bypass them.

## Package boundary

`recipes-devtools/codex-cli/codex-cli_0.154.0.bb` installs the official
`aarch64-unknown-linux-musl` release of Codex 0.154.0. Its archive SHA-256 is
fixed in the recipe, and the license files are fetched from source commit
`6b9826e3aa83b1a5947db50f4332cb9c65f1b340`. This is a prebuilt-binary recipe,
not a Rust cross-build from source. The recipe only supports little-endian
AArch64 Linux targets.

The two static executables are installed together:

- `/usr/bin/codex`
- `/usr/bin/codex-code-mode-host`, which Codex discovers beside its executable

They do not need Node.js, npm, a target Rust compiler or a musl dynamic loader.
The two binaries occupy about 277 MiB before filesystem compression; runtime
dependencies add further space. Upstream LICENSE/NOTICE and the vendored MIT
notices are installed under `/usr/share/licenses/codex-cli/`.

The archive's bundled `bwrap`, `rg` and `zsh` are not copied into the image.
Yocto supplies `bubblewrap`, `ripgrep`, Bash, Git, CA certificates and basic
terminal definitions instead. Upstream resolves these tools on PATH when its
standalone resources are absent. No auto-start service, automatic updater,
user configuration, pretrusted directory, API key or login cache is installed.
Update the recipe version/checksums and rebuild the image to update Codex.

## First use over SSH

Use the existing unprivileged `rpiadmin` account. An OpenAI connection and
account access are required for OpenAI-backed work; installing the CLI does
not install a local model or provide an account subscription. Follow the
[official CLI guide](https://learn.chatgpt.com/docs/codex/cli).

After connecting over SSH with a terminal, run:

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
codex sandbox linux -- /bin/true
```

Then log in and run a small read-only request in a disposable working directory.
This checks the actual device sandbox, TLS connectivity, authentication and
model access. A host or device policy can still reject user namespace creation;
diagnose the specific policy instead of adding an unsandboxed/default-root
workaround to the image. Installing Codex on the target does not fix the build
host's existing BitBake user-namespace restriction.

The packaging tests execute the recipe's install function and check helper,
license, permission and exclusion behavior. Metadata/fetch/unpack and ARM64
startup checks are separate from full BitBake package QA/image assembly and
authenticated device acceptance; they must not be recorded as hardware PASS.
