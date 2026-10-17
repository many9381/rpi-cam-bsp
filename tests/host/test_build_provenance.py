from __future__ import annotations

import glob
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from support import REPO_ROOT

HELPER = REPO_ROOT / 'scripts/lib/build_provenance.py'
BUILD_TOOLS = 'meta-rpi5-cam/recipes-core/packagegroups/packagegroup-rpi5-buildtools.bb'


class BuildProvenanceTest(unittest.TestCase):
    """Real repositories expose dirty content, ignored secrets and input drift."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='provenance-')
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Provenance test')
        self.put('kas/base.yml', 'header: {version: 19}\n')
        self.put('meta-rpi5-cam/conf/layer.conf', 'initial layer\n')
        self.put('meta-rpi5-cam/recipes-core/removed.bb', 'removed recipe\n')
        self.put('meta-rpi-cam-hailo/recipes-camera/camera-firmware/camera-firmware-source.inc', 'SRCREV = "1234"\n')
        self.put('scripts/build.sh', '#!/bin/bash\n')
        self.put('pyproject.toml', '[project]\n')
        self.put('uv.lock', 'version = 1\n')
        self.put('.gitignore', 'keys/\n.state/\nbuild/\nartifacts/\nrpi-cam-hailo/\n*.deb\n*.hef\n*.private.conf\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        self.out = self.root / 'artifacts/test/qemu/provenance'
        self.environment = os.environ.copy()
        self.environment.pop('CAMERA_FIRMWARE_MODEL_DIR', None)
        self.environment.pop('RPI_CAM_HAILO_DEV_REPO', None)
        self.environment.pop('CAMERA_FIRMWARE_GIT_URI', None)
        self.environment.pop('RPI5_LOCAL_BUILDTOOLS', None)

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout

    def put(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def invoke(self, action='snapshot', profile='qemu'):
        return subprocess.run(['python3', str(HELPER), action, '--repo', str(self.root),
                               '--out', str(self.out), '--profile', profile],
                              env=self.environment, capture_output=True, text=True)

    def snapshot(self, profile='qemu'):
        result = self.invoke(profile=profile)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads((self.out / 'inputs.json').read_text())

    def test_archives_dirty_untracked_development_inputs_and_deletions_without_secrets(self):
        self.put('meta-rpi5-cam/conf/layer.conf', 'dirty layer\n')
        self.put('meta-rpi-cam-hailo/recipes-camera/camera-firmware/files/fix.patch', 'actual patch\n')
        self.put('meta-rpi5-cam/recipes-core/device-config/files/rpi5-admin-sudoers', 'sudo rule\n')
        self.put('meta-rpi-cam-hailo/LICENSE', 'license\n')
        policy_inputs = {
            'meta-rpi5-cam/recipes-core/rpi5-security-policy/files/rpi5-security-status': '#!/bin/sh\nexit 0\n',
            'meta-rpi5-cam/recipes-core/rpi5-security-policy/files/rpi5-security-sudoers': 'fixed read-only rule\n',
            'meta-rpi5-cam/recipes-core/rpi5-security-policy/files/rpi5-security.nft': 'table ip rpi5_security {}\n',
        }
        for name, content in policy_inputs.items():
            self.put(name, content)

        (self.root / 'meta-rpi5-cam/recipes-core/removed.bb').unlink()
        self.put(BUILD_TOOLS, 'optional compiler group\n')
        for secret in ('keys/private.py', '.state/local.conf', 'build/generated.conf',
                       'rpi-cam-hailo/private.py', 'meta-rpi5-cam/keys/local-credential.json',
                       'meta-rpi5-cam/vendor.deb', 'meta-rpi5-cam/vendor.hef',
                       'meta-rpi5-cam/keys/unknown-credential.json'):
            self.put(secret, 'SENTINEL_PRIVATE_TOKEN')
        metadata = self.snapshot()
        with tarfile.open(self.out / 'sources.tar') as archive:
            names = archive.getnames()
            self.assertEqual(names, sorted(names))
            self.assertEqual(archive.extractfile('meta-rpi5-cam/conf/layer.conf').read(), b'dirty layer\n')
            self.assertEqual(archive.extractfile(BUILD_TOOLS).read(), b'optional compiler group\n')
            self.assertIn('meta-rpi-cam-hailo/recipes-camera/camera-firmware/files/fix.patch', names)
            self.assertIn('meta-rpi5-cam/recipes-core/device-config/files/rpi5-admin-sudoers', names)
            self.assertIn('meta-rpi-cam-hailo/LICENSE', names)
            for name, content in policy_inputs.items():
                self.assertEqual(archive.extractfile(name).read(), content.encode())
            self.assertNotIn('meta-rpi5-cam/recipes-core/removed.bb', names)
        self.assertNotIn(b'SENTINEL_PRIVATE_TOKEN', (self.out / 'sources.tar').read_bytes())
        self.assertIn('meta-rpi5-cam/recipes-core/removed.bb', metadata['deleted_tracked'])
        entries = {item['path']: item for item in metadata['sources']}
        self.assertEqual(entries[BUILD_TOOLS]['status'], 'untracked')
        self.assertEqual(entries['meta-rpi5-cam/conf/layer.conf']['sha256'], hashlib.sha256(b'dirty layer\n').hexdigest())
        self.assertEqual(metadata['git_head'], self.git('rev-parse', 'HEAD').strip())
        self.assertIn('private', metadata['purpose'])
        self.assertIn('byte-for-byte', metadata['reproducibility_limit'])

    def test_eligible_source_addition_change_removal_and_mode_change_reject_verification(self):
        for mutation in ('add', 'change', 'remove', 'mode'):
            with self.subTest(mutation=mutation):
                self.out = self.root / f'artifacts/{mutation}/provenance'
                path = self.root / 'meta-rpi5-cam/conf/layer.conf'
                path.write_text('initial layer\n')
                path.chmod(0o644)
                added = self.root / 'meta-rpi5-cam/new.bb'
                added.unlink(missing_ok=True)
                self.snapshot()
                if mutation == 'add':
                    self.put('meta-rpi5-cam/new.bb', 'new source\n')
                elif mutation == 'change':
                    path.write_text('changed content\n')
                elif mutation == 'remove':
                    path.unlink()
                else:
                    path.chmod(0o755)
                result = self.invoke('verify')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('changed', result.stderr)

    def test_retry_preserves_original_evidence_and_rejects_changed_source(self):
        self.snapshot()
        original = (self.out / 'inputs.json').read_bytes()
        original_tar = (self.out / 'sources.tar').read_bytes()
        self.assertEqual(self.invoke().returncode, 0)
        self.put('kas/base.yml', 'changed kas\n')
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('fresh build ID', result.stderr)
        self.assertEqual((self.out / 'inputs.json').read_bytes(), original)
        self.assertEqual((self.out / 'sources.tar').read_bytes(), original_tar)

    def test_source_and_parent_symlinks_are_rejected(self):
        secret = self.put('keys/private.py', 'private token')
        link = self.root / 'meta-rpi5-cam/escape.py'
        link.symlink_to(secret)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink', result.stderr)
        link.unlink()
        directory = self.root / 'meta-rpi-cam-hailo/escape'
        directory.symlink_to(self.root / 'keys', target_is_directory=True)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink', result.stderr)

    def test_hailo_hashes_exact_vendor_inputs_and_model_override_without_payload_or_path(self):
        self.put('meta-rpi5-cam/recipes-hailo/hailort/files/hailort_4.24.0_arm64.deb', 'runtime payload')
        self.put('meta-rpi5-cam/recipes-kernel/hailo-pci/files/hailort-pcie-driver_4.24.0_all.deb', 'driver payload')
        model_dir = Path(self.temp.name) / 'credential-bearing-private-dir'
        model_dir.mkdir()
        model = model_dir / 'yolo_model.hef'
        model.write_bytes(b'model payload')
        self.environment['CAMERA_FIRMWARE_MODEL_DIR'] = str(model_dir)
        self.environment['RPI_CAM_HAILO_DEV_REPO'] = '0'
        metadata = self.snapshot('rpi5-camera-hailo')
        vendors = {item['name']: item for item in metadata['vendor_inputs']}
        self.assertEqual(set(vendors), {'hailort_4.24.0_arm64.deb', 'hailort-pcie-driver_4.24.0_all.deb', 'yolo_model.hef'})
        self.assertEqual(vendors['yolo_model.hef']['sha256'], hashlib.sha256(b'model payload').hexdigest())
        self.assertEqual(vendors['yolo_model.hef']['size'], 13)
        self.assertEqual(metadata['choices']['model_directory'], 'environment')
        self.assertEqual(metadata['choices']['dev_repo'], {'origin': 'environment', 'enabled': False})
        self.assertNotIn('credential-bearing-private-dir', (self.out / 'inputs.json').read_text())
        tar = (self.out / 'sources.tar').read_bytes()
        for payload in (b'runtime payload', b'driver payload', b'model payload'):
            self.assertNotIn(payload, tar)
        model.write_bytes(b'changed model')
        result = self.invoke('verify', 'rpi5-camera-hailo')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('changed', result.stderr)

    def test_head_choice_and_snapshot_tampering_reject_verification(self):
        self.snapshot()
        self.environment['RPI_CAM_HAILO_DEV_REPO'] = '0'
        self.assertNotEqual(self.invoke('verify').returncode, 0)
        self.environment.pop('RPI_CAM_HAILO_DEV_REPO')
        with (self.out / 'sources.tar').open('ab') as stream:
            stream.write(b'tamper')
        self.assertNotEqual(self.invoke('verify').returncode, 0)

    def test_bitbake_discovered_recipes_cannot_hide_under_excluded_layer_directories(self):
        # Match the real layer BBFILES pattern, independently of helper selection.
        # Anchor fixture ignores at repo root so both ignored and untracked cases
        # beneath keys/build have the intended distinct Git discovery behavior.
        self.put('.gitignore', '/keys/\n/.state/\n/build/\n/artifacts/\n/rpi-cam-hailo/\n*.deb\n*.hef\n*.private.conf\n')
        scenario = 0
        for layer in ('meta-rpi5-cam', 'meta-rpi-cam-hailo'):
            for directory in ('build', 'keys', 'artifacts'):
                for suffix in ('.bb', '.bbappend'):
                    for ignored in (False, True):
                        for timing in ('before-snapshot', 'after-snapshot'):
                            with self.subTest(layer=layer, directory=directory, suffix=suffix,
                                              ignored=ignored, timing=timing):
                                scenario += 1
                                self.out = self.root / f'artifacts/case-{scenario}/provenance'
                                name = f'{layer}/recipes-core/{directory}/private-input{suffix}'
                                self.put('.git/info/exclude', '/' + name + '\n' if ignored else '')
                                if timing == 'after-snapshot':
                                    self.snapshot()
                                path = self.put(name, 'SENTINEL_PRIVATE_TOKEN')
                                try:
                                    matches = glob.glob(str(self.root / layer / f'recipes-*/*/*{suffix}'))
                                    self.assertIn(str(path), matches, 'must be consumed by real BBFILES pattern')
                                    result = self.invoke('verify' if timing == 'after-snapshot' else 'snapshot')
                                    self.assertNotEqual(result.returncode, 0)
                                    self.assertIn('excluded', result.stderr)
                                    self.assertNotIn('private-input', result.stderr)
                                    self.assertNotIn('SENTINEL_PRIVATE_TOKEN', result.stderr)
                                    if (self.out / 'sources.tar').exists():
                                        self.assertNotIn(b'SENTINEL_PRIVATE_TOKEN', (self.out / 'sources.tar').read_bytes())
                                finally:
                                    path.unlink()

    def test_excluded_layer_config_and_class_inputs_fail_without_copying_private_content(self):
        self.put('.gitignore', '/keys/\n/build/\n*.deb\n*.hef\n')
        for index, name in enumerate((
                'meta-rpi5-cam/conf/keys/private.conf',
                'meta-rpi-cam-hailo/classes/build/private.bbclass',
                'meta-rpi5-cam/recipes-core/keys/private.inc')):
            with self.subTest(name=name):
                self.out = self.root / f'artifacts/excluded-config-{index}/provenance'
                self.put('.git/info/exclude', '/' + name + '\n')
                self.snapshot()
                path = self.put(name, 'SENTINEL_PRIVATE_TOKEN')
                try:
                    result = self.invoke('verify')
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('excluded', result.stderr)
                    self.assertNotIn('private.', result.stderr)
                    self.assertNotIn(b'SENTINEL_PRIVATE_TOKEN', (self.out / 'sources.tar').read_bytes())
                finally:
                    path.unlink()

    def test_excluded_layer_symlink_directory_cannot_conceal_discovered_recipes(self):
        target = self.root / 'keys'
        for suffix in ('.bb', '.bbappend'):
            self.put(f'keys/private-input{suffix}', 'SENTINEL_PRIVATE_TOKEN')
        link = self.root / 'meta-rpi5-cam/recipes-core/keys'
        link.parent.mkdir(parents=True, exist_ok=True)
        for ignored in (False, True):
            for timing in ('before-snapshot', 'after-snapshot'):
                with self.subTest(ignored=ignored, timing=timing):
                    self.out = self.root / f'artifacts/symlink-{ignored}-{timing}/provenance'
                    self.put('.git/info/exclude', '/meta-rpi5-cam/recipes-core/keys\n' if ignored else '')
                    if timing == 'after-snapshot':
                        self.snapshot()
                    link.symlink_to(target, target_is_directory=True)
                    try:
                        for suffix in ('.bb', '.bbappend'):
                            self.assertIn(str(link / f'private-input{suffix}'),
                                          glob.glob(str(self.root / f'meta-rpi5-cam/recipes-*/*/*{suffix}')))
                        result = self.invoke('verify' if timing == 'after-snapshot' else 'snapshot')
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn('symlink', result.stderr)
                        self.assertNotIn('private-input', result.stderr)
                        if timing == 'before-snapshot':
                            self.assertFalse((self.out / 'sources.tar').exists())
                        else:
                            self.assertNotIn(b'SENTINEL_PRIVATE_TOKEN', (self.out / 'sources.tar').read_bytes())
                    finally:
                        link.unlink()

    def test_root_private_and_generated_trees_keep_bitbake_metadata_out_of_snapshot(self):
        for name in ('keys/private.bb', 'keys/private.conf', 'build/local.conf',
                     'artifacts/output.bbappend', '.state/credential.inc'):
            self.put(name, 'SENTINEL_PRIVATE_TOKEN')
        self.snapshot()
        self.assertEqual(self.invoke('verify').returncode, 0)
        self.assertNotIn(b'SENTINEL_PRIVATE_TOKEN', (self.out / 'sources.tar').read_bytes())

    def test_legacy_ignored_compiler_overrides_are_rejected(self):
        for name in (
                'meta-rpi5-cam/recipes-core/images/rpi5-minimal-image.bbappend',
                'meta-rpi5-cam/recipes-core/images/rpi5-camera-image.bbappend',
                'meta-rpi5-cam/recipes-core/packagegroups/packagegroup-rpi5-local-buildtools.bb'):
            with self.subTest(name=name):
                self.out = self.root / 'artifacts/legacy' / Path(name).name / 'provenance'
                self.put('.git/info/exclude', '/' + name + '\n')
                path = self.put(name, 'SENTINEL_LEGACY_OVERRIDE')
                try:
                    result = self.invoke()
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('ignored source', result.stderr)
                    self.assertFalse((self.out / 'sources.tar').exists())
                finally:
                    path.unlink()

    def test_compiler_selection_is_recorded_and_cannot_change_within_a_build(self):
        metadata = self.snapshot(profile='rpi5-camera')
        self.assertEqual(metadata['choices'].get('local_buildtools'),
                         {'origin': 'default', 'enabled': False})
        self.environment['RPI5_LOCAL_BUILDTOOLS'] = '1'
        self.assertNotEqual(self.invoke('verify', profile='rpi5-camera').returncode, 0)
        self.out = self.root / 'artifacts/development/provenance'
        metadata = self.snapshot(profile='rpi5-camera')
        self.assertEqual(metadata['choices']['local_buildtools'],
                         {'origin': 'environment', 'enabled': True})
        self.environment['RPI5_LOCAL_BUILDTOOLS'] = '0'
        self.assertNotEqual(self.invoke('verify', profile='rpi5-camera').returncode, 0)
        self.environment['RPI5_LOCAL_BUILDTOOLS'] = '1'
        self.out = self.root / 'artifacts/qemu/provenance'
        self.assertFalse(self.snapshot()['choices']['local_buildtools']['enabled'])

    def test_unknown_ignored_recipe_inputs_fail_without_archiving_or_printing_private_path(self):
        for suffix in ('.bb', '.bbappend', '.inc', '.bbclass', '.conf', '.py', '.patch', '.cfg', ''):
            with self.subTest(suffix=suffix):
                name = 'meta-rpi5-cam/private-credential-name' + suffix
                self.put('.git/info/exclude', '/' + name + '\n')
                path = self.put(name, 'SENTINEL_PRIVATE_TOKEN')
                try:
                    result = self.invoke()
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('ignored source', result.stderr)
                    self.assertNotIn('private-credential-name', result.stderr)
                    self.assertNotIn('SENTINEL_PRIVATE_TOKEN', result.stderr)
                    self.assertFalse((self.out / 'inputs.json').exists())
                finally:
                    path.unlink()
                    if self.out.exists():
                        for output in self.out.iterdir():
                            output.unlink()
                        self.out.rmdir()

    def test_unknown_nonignored_layer_resources_fail_instead_of_omitting_inputs(self):
        for name in ('meta-rpi5-cam/recipes-core/files/extra.cfg',
                     'meta-rpi-cam-hailo/recipes-camera/files/extensionless-resource'):
            with self.subTest(name=name):
                path = self.put(name, 'actual new recipe resource')
                result = self.invoke()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('unsupported source', result.stderr)
                self.assertIn('allowlist', result.stderr)
                self.assertFalse((self.out / 'inputs.json').exists())
                path.unlink()

    def test_staged_deletion_and_head_change_are_recorded_and_detected(self):
        self.git('rm', 'meta-rpi5-cam/recipes-core/removed.bb')
        metadata = self.snapshot()
        self.assertIn('meta-rpi5-cam/recipes-core/removed.bb', metadata['deleted_tracked'])
        self.git('commit', '-qm', 'delete recipe')
        result = self.invoke('verify')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('changed', result.stderr)

    def test_vendor_directory_switch_is_detected_even_with_identical_model(self):
        self.put('meta-rpi5-cam/recipes-hailo/hailort/files/hailort_4.24.0_arm64.deb', 'runtime')
        self.put('meta-rpi5-cam/recipes-kernel/hailo-pci/files/hailort-pcie-driver_4.24.0_all.deb', 'driver')
        self.put('rpi-cam-hailo/vendor/models/yolo_model.hef', 'model')
        self.snapshot('rpi5-camera-hailo')
        self.put('alternate-models/yolo_model.hef', 'model')
        self.environment['CAMERA_FIRMWARE_MODEL_DIR'] = str(self.root / 'alternate-models')
        self.assertNotEqual(self.invoke('verify', 'rpi5-camera-hailo').returncode, 0)

    def test_public_key_mutation_is_detected_but_never_archived(self):
        self.put('keys/rpi5_admin.pub', 'public identity')
        self.snapshot()
        with tarfile.open(self.out / 'sources.tar') as archive:
            self.assertFalse(any(name.startswith('keys/') for name in archive.getnames()))
        self.put('keys/rpi5_admin.pub', 'different public identity')
        self.assertNotEqual(self.invoke('verify').returncode, 0)

    def test_git_transport_override_is_fingerprinted_without_credentials(self):
        self.environment['CAMERA_FIRMWARE_GIT_URI'] = 'https://private-user:secret-token@example.invalid/source.git'
        metadata = self.snapshot()
        serialized = (self.out / 'inputs.json').read_text()
        self.assertNotIn('secret-token', serialized)
        self.assertEqual(metadata['choices']['firmware_transport']['origin'], 'environment')
        self.environment['CAMERA_FIRMWARE_GIT_URI'] = 'git://different/source.git'
        self.assertNotEqual(self.invoke('verify').returncode, 0)

    def test_missing_vendor_input_fails_without_recording_external_path(self):
        self.environment['CAMERA_FIRMWARE_MODEL_DIR'] = '/private/credential-location'
        result = self.invoke(profile='rpi5-camera-hailo')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('/private/credential-location', result.stderr)
        self.assertFalse((self.out / 'inputs.json').exists())


if __name__ == '__main__':
    unittest.main()
