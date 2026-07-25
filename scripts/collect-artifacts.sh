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
