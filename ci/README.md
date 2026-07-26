# Provider-Neutral CI Contract

The CI service must load `ci/container.env`, configure the job image as the
exact `KAS_CONTAINER_IMAGE` digest, override the image entry point to run a
shell, and run as a non-root UID. Do not substitute a tag. Persist
`build/kas-work/build/downloads`, `build/kas-work/build/sstate-cache`, and the
profile build directories as protected caches.

Jobs invoke exactly one provider-neutral stage:

```bash
./ci/pipeline.sh unit
./ci/pipeline.sh qemu
./ci/pipeline.sh rpi5-image
```

Publish ignored `artifacts/BUILD_ID/` only to access-controlled CI artifact
storage. Never publish `keys/`. Each build job requires empty CI key paths,
creates one ephemeral SSH key pair, and removes exactly that pair on exit.
`rpi5-image` intentionally reruns QEMU in the same job so the QEMU gate and
generated image use the same key, build ID, and Git revision.

Each job allows the pinned Astral uv 0.11.31 installer download, keeps the
installer under ignored `.state/uv-bin`, runs `uv lock --check` and
`uv sync --locked`, and then invokes the selected pipeline stage. The uv
binary is a job-local host prerequisite and is never committed or copied into
the target image.

The vendored `ci/kas-container` is the byte-exact official kas 5.4 launcher for
local container parity and provenance. CI itself executes inside the pinned
image. The container supplies the Yocto host toolchain; the uv project supplies
the exact Python and kas command environment.

Hardware flashing, Raspberry Pi tests, camera tests, and release approval
remain manual protected stages outside CI. CI never receives a block device or
privileged device access.
