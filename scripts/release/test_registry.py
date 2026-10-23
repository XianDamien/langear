import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import actions
from host import Deployment, digest, verify_bundle
from manage import stage
from registry import image


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = {
            'schema': 3, 'sha': 'a' * 40, 'runtime': 'core-v1',
            'image': 'ghcr.io/xiandamien/langear/backend@sha256:' + 'b' * 64,
            'image_id': 'sha256:' + 'c' * 64,
            'frontend_image': 'ghcr.io/xiandamien/langear/frontend@sha256:' + 'd' * 64,
            'frontend_image_id': 'sha256:' + 'e' * 64,
            'files': {},
            'checks': ['frontend-vitest', 'frontend-typecheck-build',
                       'release-tool-tests', 'collection-core-pytest'],
        }
        self.save()

    def save(self):
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))

    def test_registry_manifest_requires_no_application_archives(self):
        self.assertEqual(verify_bundle(self.root), self.manifest)
        self.assertEqual([p.name for p in self.root.iterdir()], ['manifest.json'])

    def test_mutable_or_malformed_image_references_are_rejected(self):
        for key in ('image', 'frontend_image'):
            original = self.manifest[key]
            for ref in ('ghcr.io/xiandamien/langear/backend:latest',
                        'other.io/a@sha256:' + 'b' * 64, '--help'):
                with self.subTest(key=key, ref=ref):
                    self.manifest[key] = ref
                    self.save()
                    with self.assertRaisesRegex(ValueError, 'immutable'):
                        verify_bundle(self.root)
            self.manifest[key] = original

    def test_image_digest_is_selected_from_the_pushed_repository(self):
        tag = 'ghcr.io/xiandamien/langear/backend:a'
        info = [{'Id': self.manifest['image_id'], 'RepoDigests': [
            'unrelated/repo@sha256:' + 'f' * 64, self.manifest['image']]}]
        with patch('registry.subprocess.check_output', return_value=json.dumps(info)):
            self.assertEqual(image(tag), (self.manifest['image'], self.manifest['image_id']))

    def test_host_rejects_image_with_different_revision(self):
        info = [{'Id': self.manifest['image_id'], 'Config': {
            'Labels': {'org.opencontainers.image.revision': 'f' * 40}}}]
        with patch('host.run', return_value=json.dumps(info)):
            with self.assertRaisesRegex(RuntimeError, 'identity or Git revision'):
                Deployment('staging').verify_image(self.manifest['image'], self.manifest['image_id'], self.manifest['sha'])

    def test_failed_frontend_copy_still_removes_temporary_container(self):
        def fake(*args, **kwargs):
            if args[1] == 'create':
                return 'temporary-container'
            if args[1] == 'cp':
                raise subprocess.CalledProcessError(1, args)
        with patch('host.run', side_effect=fake) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                Deployment('staging').extract_frontend_image(self.manifest['frontend_image'], self.root)
            self.assertEqual(run.call_args.args, ('docker', 'rm', 'temporary-container'))

    def test_ssh_transports_metadata_only_with_strict_host_verification(self):
        env = {'DEPLOY_SSH_KEY': 'test-key', 'DEPLOY_KNOWN_HOSTS': 'test-host-key',
               'DEPLOY_HOST': 'example.test', 'DEPLOY_PORT': '20224', 'DEPLOY_USER': 'deploy',
               'REGISTRY_USER': 'ci', 'REGISTRY_TOKEN': 'short-lived-test-token'}
        def fake(command, **kwargs):
            self.assertIn('StrictHostKeyChecking=yes', command)
            self.assertNotIn(env['REGISTRY_TOKEN'], ' '.join(command))
            envelope = json.loads(kwargs['input'])
            self.assertEqual(set(envelope['files']), {'host.py', 'manifest.json'})
            self.assertNotIn('backend-image.tar.gz', envelope['files'])
            self.assertEqual(envelope['registry_token'], env['REGISTRY_TOKEN'])
            return subprocess.CompletedProcess(command, 0, '')
        with patch.dict(os.environ, env), patch('actions.subprocess.run', side_effect=fake):
            actions.execute('staging', 'deploy', self.root)

    def test_production_requires_acceptance_before_any_ssh(self):
        with patch('actions.subprocess.run') as run:
            with self.assertRaises(FileNotFoundError):
                actions.execute('prod', 'deploy', self.root)
            run.assert_not_called()

    def test_cli_retries_actions_job_without_uploading_registry_release(self):
        metadata = {'conclusion': 'success', 'event': 'push',
                    'path': '.github/workflows/frontend-dev-deploy.yml',
                    'head_sha': self.manifest['sha']}
        def fake(*args, **kwargs):
            if args[:2] == ('gh', 'api'):
                return json.dumps({'jobs': [{'name': 'deploy-staging', 'id': 456}]}) if args[2].endswith('/jobs') else json.dumps(metadata)
        with patch('manage.run', side_effect=fake) as run, \
                patch('manage.tempfile.TemporaryDirectory', return_value=contextlib.nullcontext(str(self.root))), \
                patch('manage.upload') as upload, patch('manage.invoke') as invoke:
            stage('123')
            run.assert_called_with('gh', 'run', 'rerun', '123', '--job', '456')
            upload.assert_not_called()
            invoke.assert_not_called()

    def test_failure_can_restore_development_snapshot_with_source_mounts(self):
        deployment = Deployment('staging')
        deployment.state_path = self.root / 'current.json'
        deployment.override = self.root / 'release.override.yml'
        previous = {'state': {'mode': 'dev'}, 'image_id': self.manifest['image_id'],
                    'override': 'services:\n  backend:\n    image: old\n', 'web': '/previous/web'}
        with patch.object(deployment, 'start') as start, \
                patch.object(deployment, 'healthy'), patch.object(deployment, 'switch_web'):
            deployment.restore(previous)
            start.assert_called_once()
            self.assertEqual(json.loads(deployment.state_path.read_text()), {'mode': 'dev'})

    def test_same_release_retry_verifies_runtime_without_recreating_containers(self):
        deployment = Deployment('staging')
        deployment.state_path = self.root / 'current.json'
        state = {'mode': 'release', 'sha': self.manifest['sha'],
                 'manifest_sha256': digest(self.root / 'manifest.json'),
                 'core_db_revision': ['test_revision']}
        deployment.state_path.write_text(json.dumps(state))
        snapshot = {'image_id': self.manifest['image_id'],
                    'worker_image_id': self.manifest['image_id'],
                    'core_db_revision': ['test_revision']}
        with patch.object(deployment, 'snapshot', return_value=snapshot), \
                patch.object(deployment, 'healthy') as healthy, \
                patch.object(deployment, 'check_frontend') as frontend, \
                patch('host.run') as run, contextlib.redirect_stdout(io.StringIO()):
            deployment.deploy(self.root)
            healthy.assert_called_once()
            frontend.assert_called_once_with(self.manifest['sha'])
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
