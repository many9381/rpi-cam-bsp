# Optional Raspberry Pi build tools

Raspberry Pi images omit target compilers and development headers by default.
`packagegroup-rpi5-buildtools` selects GCC/G++, binutils, make, pkgconfig,
standard C/C++ development files, CMake and Ninja only when
`RPI5_LOCAL_BUILDTOOLS=1`. This applies to `rpi5-minimal`, `rpi5-camera` and
`rpi5-camera-hailo`. QEMU does not select this package group.

Build a default image with the one-command launcher:

```sh
./scripts/build-image.sh
```

The launcher generates a fresh ID and defaults `RPI5_LOCAL_BUILDTOOLS` to `0`.
An explicit environment value is preserved; set it to `0` if the shell has
previously exported `1`.

For a separate development build with Pi-side compilation:

```sh
RPI5_LOCAL_BUILDTOOLS=1 ./scripts/build-image.sh
```

Use a fresh build ID when changing the option. To retry an interrupted build,
call `scripts/build.sh --build-id ID rpi5-camera-hailo build` with the ID printed
by the launcher. Keep the same option for the retry and for manual artifact
collection/provenance verification. The input
record stores this selection in `choices.local_buildtools`; the final rootfs
package manifest establishes what was actually installed.

This option does not remove required runtime libraries such as `libgcc` and
`libstdc++`. Applications retain their runtime dependency resolution. The host
cross-compiler used by Yocto also remains available for image construction.
Codex CLI and the optional firmware source checkout have separate image
selections; this flag only controls the target build-tools group.

## Migration from the earlier local overrides

The previously accepted image `20261016T111625Z-e664cb9647e7` contains GCC/G++ 15.3.0,
binutils 2.46.1, make 4.4.1, CMake 4.3.1, Ninja 1.13.2 and development headers.
They were added by two ignored image `.bbappend` files and the ignored
`packagegroup-rpi5-local-buildtools.bb`, even though the Git checkout alone
did not describe that selection.

Those three files were moved outside active layers into the private
`.state/buildtools-separation-2026-10-16/legacy-inputs/` directory. Do not copy
them back into the layers; provenance now rejects ignored recipe inputs.
The replacement package group and default-off selection are normal source
files. Historical images, package manifests and source archives are unchanged.
Devices using that earlier image retain their tools until a new image is installed.

Before accepting a newly built default image, inspect its actual package
manifest for absence of target `gcc`, `g++`, `cpp`, compiler symlink packages,
`packagegroup-core-buildessential` and the optional build-tools group. Check
build tools and development headers for any additional dependency paths;
required runtime libraries must remain. For an opted-in development build,
verify the compiler/header packages are present and perform a small native
C/C++ compile-and-run check on that device if that validation is requested.

On 2026-10-17 the user declined the separate development-image build and
on-device compile validation. Keep it out of active remaining-work lists
unless requested again. The opt-in configuration remains available; this
decision does not establish hardware acceptance of that variant.

On 2026-10-17, default build `20261017T051814Z-63b1d2587b1b` completed all
BitBake tasks and artifact collection. Its 368-package manifest contains no
target compiler, build-tools group, CMake, make, Ninja or development packages.
The camera application, web assets, HailoRT, Codex and required `libgcc` and
`libstdc++` runtime libraries are present. Artifact checksums passed.

Subsequent SSD deployment validation passed on 2026-10-17: 391 readable
installed-file hashes matched, development tools were absent, and three Wi-Fi
reboots retained normal camera operation. The user confirmed video, Hailo
readiness, increasing inference frames and detected object names/confidence
after the final reboot. See the separate
[deployment record](../../rpi-cam-hailo/docs/security/buildtools-deployment-validation-2026-10-17.md).
This acceptance covers the default image; it does not validate a separate
opted-in development build.
