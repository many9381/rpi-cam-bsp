#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

test -z "${UV_PROJECT_ENVIRONMENT:-}" || \
    rpi5_die "UV_PROJECT_ENVIRONMENT must be unset or empty"

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

case "$profile" in
    qemu)
        expected_config="kas/qemuarm64-minimal.yml"
        expected_machine="qemuarm64"
        expected_image="rpi5-minimal-image"
        ;;
    rpi5-minimal)
        expected_config="kas/rpi5-minimal.yml"
        expected_machine="raspberrypi5"
        expected_image="rpi5-minimal-image"
        ;;
    rpi5-camera)
        expected_config="kas/rpi5-camera.yml"
        expected_machine="raspberrypi5"
        expected_image="rpi5-camera-image"
        ;;
    rpi5-camera-hailo)
        expected_config="kas/rpi5-camera-hailo.yml"
        expected_machine="raspberrypi5"
        expected_image="rpi5-camera-image"
        ;;
    *) rpi5_die "unknown profile: $profile" ;;
esac
[[ "$config" == "$expected_config" && "$machine" == "$expected_machine" && \
    "$image" == "$expected_image" ]] || \
    rpi5_die "collector arguments do not match profile: $profile"

rpi5_validate_build_id "$build_id" || rpi5_die "invalid build ID: $build_id"
repo_root="$(rpi5_repo_root)"
current_revision="$(git -C "$repo_root" rev-parse --short=12 HEAD)"
[[ "$build_id" == *"-$current_revision" ]] || \
    rpi5_die "build ID revision does not match HEAD $current_revision"

out="$repo_root/artifacts/$build_id/$profile"
[[ ! -e "$out/COMPLETE" ]] || rpi5_die "evidence already complete: $out"

cd "$repo_root"
build_dir="$repo_root/build/kas-work/build/$profile"
deploy="$build_dir/tmp/deploy/images/$machine"
for subtree in images checksums manifests licenses; do
    rm -rf -- "$out/$subtree"
done
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
    rpi5-minimal|rpi5-camera|rpi5-camera-hailo)
        copy_required "$deploy/$image-$machine.rootfs.wic.bz2"
        copy_required "$deploy/$image-$machine.rootfs.wic.bmap"
        ;;
    *) rpi5_die "unknown profile: $profile" ;;
esac

manifest="$deploy/$image-$machine.rootfs.manifest"
[[ -e "$manifest" ]] || rpi5_die "package manifest missing: $manifest"
cp -L "$manifest" "$out/manifests/"

license_root="$build_dir/tmp/deploy/licenses/$machine"
license_link="$license_root/$image-$machine.rootfs"
[[ -L "$license_link" ]] || rpi5_die "license manifest link missing: $license_link"
license_dir="$(readlink -f -- "$license_link")"
[[ -d "$license_dir" ]] || rpi5_die "license manifest directory missing"
case "$license_dir" in
    "$license_root/$image-$machine.rootfs-"*) ;;
    *) rpi5_die "license manifest link escapes expected image scope" ;;
esac
cp -a "$license_dir" "$out/licenses/"

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
