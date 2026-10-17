#!/usr/bin/env python3
"""Private, bounded local build-input evidence. Never archive vendor or key data."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

LAYERS = ('meta-rpi5-cam', 'meta-rpi-cam-hailo')
SCOPES = (*LAYERS, 'kas', 'scripts', 'pyproject.toml', 'uv.lock')
SOURCE_SUFFIXES = {
    '.bb', '.bbappend', '.bbclass', '.inc', '.conf', '.patch', '.py',
    '.service', '.rules', '.network', '.wks', '.example', '.txt', '.nft',
}
RESOURCE_NAMES = {'rpi5-admin-sudoers', 'rpi5-camera-sudoers', 'rpi5-security-status', 'rpi5-security-sudoers', 'LICENSE', 'License', 'COPYING'}
BITBAKE_METADATA_SUFFIXES = {'.bb', '.bbappend', '.bbclass', '.inc', '.conf'}
EXCLUDED_PARTS = {'keys', '.state', 'artifacts', 'build', '.git', '.venv',
                  '__pycache__', 'node_modules', 'rpi-cam-hailo'}
# Human documentation is explicitly outside build-source capture.
DOCUMENTATION = {'meta-rpi5-cam/README.md', 'meta-rpi-cam-hailo/README.md'}
# The reviewed archives selected by the current Hailo recipes. They never enter tar.
HAILO_INPUTS = (
    'meta-rpi5-cam/recipes-hailo/hailort/files/hailort_4.24.0_arm64.deb',
    'meta-rpi5-cam/recipes-kernel/hailo-pci/files/hailort-pcie-driver_4.24.0_all.deb',
)
PUBLIC_INPUTS = ('keys/rpi5_admin.pub', 'keys/camera-firmware/integrity-public.pem')
LIMIT = ('This private source snapshot is not a public release or a byte-for-byte '
         'reproducibility guarantee. Codex resolves latest stable on each invocation; '
         'the image package manifest records the installed version. Remote downloads, '
         'build host state and private provisioning inputs are not archived.')


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def eligible(name: str) -> bool:
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    if name in ('pyproject.toml', 'uv.lock'):
        return True
    if path.parts[0] == 'kas':
        return path.suffix == '.yml'
    if path.parts[0] == 'scripts':
        return path.suffix in {'.sh', '.py'}
    return path.parts[0] in LAYERS and (path.suffix in SOURCE_SUFFIXES or path.name in RESOURCE_NAMES)


def reject_symlinks(path: Path, boundary: Path) -> None:
    current = path
    while current != boundary:
        if current.is_symlink():
            raise ValueError('symlinked build input is not permitted')
        if current == current.parent:
            break
        current = current.parent


def digest_file(path: Path) -> dict:
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
            size += len(chunk)
    return {'sha256': digest.hexdigest(), 'size': size}


def capture(repo: Path, profile: str) -> dict:
    tracked = set(git(repo, 'ls-files', '-z', '--cached', '--', *SCOPES).decode().split('\0')) - {''}
    head_files = set(git(repo, 'ls-tree', '-rz', '--name-only', 'HEAD', '--', *SCOPES).decode().split('\0')) - {''}
    untracked = set(git(repo, 'ls-files', '-z', '--others', '--exclude-standard', '--', *SCOPES).decode().split('\0')) - {''}
    ignored = set(git(repo, 'ls-files', '-z', '--others', '--ignored', '--exclude-standard', '--', *SCOPES).decode().split('\0')) - {''}
    # Archive exclusions do not stop BitBake discovering recipes or including
    # configuration inside a layer. Reject those inputs without reading them.
    for name in tracked | head_files | untracked | ignored:
        path = Path(name)
        if (path.parts[0] in LAYERS and path.suffix in BITBAKE_METADATA_SUFFIXES
                and any(part in EXCLUDED_PARTS for part in path.parts[1:])
                and ((repo / name).exists() or (repo / name).is_symlink())):
            raise ValueError('BitBake metadata in an excluded layer source directory; move reviewed non-secret sources before using a fresh build ID')
    if any(name not in DOCUMENTATION
           and Path(name).suffix not in {'.deb', '.hef'}
           and not any(part in EXCLUDED_PARTS for part in Path(name).parts)
           for name in ignored):
        # Ignore rules can hide inputs that BitBake still discovers. Do not copy
        # those files or disclose their private path/content in an error.
        raise ValueError('unapproved ignored source detected; review source ignore rules before using a fresh build ID')
    # Reject symlinked directories even when Git reports only the directory itself.
    for name in tracked | head_files | untracked | ignored:
        path = repo / name
        if eligible(name) or (path.is_symlink() and path.is_dir()):
            reject_symlinks(path, repo)
    for name in sorted(tracked | untracked):
        path = Path(name)
        if (not eligible(name) and name not in DOCUMENTATION
                and not any(part in EXCLUDED_PARTS for part in path.parts)
                and (repo / name).exists()):
            raise ValueError(f'unsupported source file: {name}; review and extend the source allowlist before building')
    sources = []
    for name in sorted(tracked | untracked):
        if not eligible(name):
            continue
        path = repo / name
        if not path.exists():
            continue
        if not path.is_file():
            raise ValueError('build source must be a regular file')
        status = 'tracked' if name in tracked else 'untracked'
        sources.append({'path': name, 'status': status,
                        'executable': bool(path.stat().st_mode & 0o111), **digest_file(path)})
    vendor_inputs = []
    model_override = bool(os.environ.get('CAMERA_FIRMWARE_MODEL_DIR'))
    model_dir = Path(os.environ.get('CAMERA_FIRMWARE_MODEL_DIR') or
                     str(repo / 'rpi-cam-hailo/vendor/models'))
    if not model_dir.is_absolute():
        model_dir = repo / model_dir
    if profile == 'rpi5-camera-hailo':
        vendors = [(Path(name).name, repo / name) for name in HAILO_INPUTS]
        vendors.append(('yolo_model.hef', model_dir / 'yolo_model.hef'))
        for name, path in vendors:
            reject_symlinks(path, Path('/'))
            if not path.is_file():
                raise ValueError(f'required vendor input missing: {name}')
            vendor_inputs.append({'name': name, **digest_file(path)})
    public_inputs = []
    for name in PUBLIC_INPUTS:
        path = repo / name
        reject_symlinks(path, repo)
        if path.exists():
            public_inputs.append({'name': name, **digest_file(path)})
    choices = {'dev_repo': {'origin': 'environment' if os.environ.get('RPI_CAM_HAILO_DEV_REPO') else 'default',
                            'enabled': os.environ.get('RPI_CAM_HAILO_DEV_REPO', '1') != '0'}}
    buildtools = os.environ.get('RPI5_LOCAL_BUILDTOOLS') or '0'
    if buildtools not in {'0', '1'}:
        raise ValueError('RPI5_LOCAL_BUILDTOOLS must be 0 or 1')
    choices['local_buildtools'] = {
        'origin': 'environment' if os.environ.get('RPI5_LOCAL_BUILDTOOLS') else 'default',
        'enabled': profile != 'qemu' and buildtools == '1',
    }
    transport = os.environ.get('CAMERA_FIRMWARE_GIT_URI')
    choices['firmware_transport'] = {
        'origin': 'environment' if transport else 'recipe-default',
        'sha256': hashlib.sha256((transport or '').encode()).hexdigest(),
    }
    if profile == 'rpi5-camera-hailo':
        choices.update(model_directory='environment' if model_override else 'default',
                       model_directory_sha256=hashlib.sha256(os.fsencode(model_dir.absolute())).hexdigest())
    return {'schema_version': 1, 'profile': profile,
            'purpose': 'A private non-secret local source snapshot; not a public release.',
            'reproducibility_limit': LIMIT,
            'git_head': git(repo, 'rev-parse', 'HEAD').decode().strip(),
            'sources': sources,
            'deleted_tracked': sorted(name for name in tracked | head_files
                                      if eligible(name) and not (repo / name).exists()),
            'vendor_inputs': vendor_inputs, 'public_input_digests': public_inputs,
            'choices': choices}


def verify(repo: Path, out: Path, profile: str) -> None:
    reject_symlinks(out, Path('/'))
    manifest = out / 'inputs.json'
    archive = out / 'sources.tar'
    for path in (manifest, archive):
        if path.is_symlink() or not path.is_file():
            raise ValueError('source provenance missing or not a regular file; use a fresh build ID')
    recorded = json.loads(manifest.read_text())
    archived_hash = recorded.pop('source_archive_sha256', None)
    recorded.pop('captured_at', None)
    if digest_file(archive)['sha256'] != archived_hash or capture(repo, profile) != recorded:
        raise ValueError('build inputs or source evidence changed; use a fresh build ID')


def snapshot(repo: Path, out: Path, profile: str) -> None:
    reject_symlinks(out, Path('/'))
    if out.exists():
        verify(repo, out, profile)
        return
    inputs = capture(repo, profile)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Keep partial snapshots separate: a failed capture must never replace evidence.
    temporary = out.with_name(out.name + '.pending')
    temporary.mkdir(mode=0o700)
    try:
        archive = temporary / 'sources.tar'
        with tarfile.open(archive, 'w', format=tarfile.PAX_FORMAT) as stream:
            for item in inputs['sources']:
                path = repo / item['path']
                reject_symlinks(path, repo)
                content = path.read_bytes()
                if hashlib.sha256(content).hexdigest() != item['sha256']:
                    raise ValueError('build source changed during snapshot; use a fresh build ID')
                info = tarfile.TarInfo(item['path'])
                info.size = len(content)
                info.mode = 0o755 if item['executable'] else 0o644
                stream.addfile(info, io.BytesIO(content))
        if capture(repo, profile) != inputs:
            raise ValueError('build inputs changed during snapshot; use a fresh build ID')
        inputs['source_archive_sha256'] = digest_file(archive)['sha256']
        inputs['captured_at'] = datetime.now(timezone.utc).isoformat()
        (temporary / 'inputs.json').write_text(json.dumps(inputs, indent=2, sort_keys=True) + '\n')
        temporary.rename(out)
    finally:
        if temporary.exists():
            for path in temporary.iterdir():
                path.unlink()
            temporary.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('snapshot', 'verify'))
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--profile', choices=('qemu', 'rpi5-minimal', 'rpi5-camera', 'rpi5-camera-hailo'), required=True)
    args = parser.parse_args()
    try:
        (snapshot if args.action == 'snapshot' else verify)(args.repo.absolute(), args.out.absolute(), args.profile)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        # OSError may carry private external paths; never print them.
        message = str(error) if isinstance(error, ValueError) else 'unable to read build inputs or provenance; use a fresh build ID'
        parser.exit(1, f'ERROR: {message}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
