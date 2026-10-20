import io
import contextlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from host import (
    Deployment, digest, extract_frontend, is_core_only, is_core_runtime, overlay,
    verify_approval, verify_bundle,
)
from manage import stage


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = {
            'schema': 1, 'sha': 'a' * 40, 'image': 'langear-release:' + 'a' * 40,
            'image_id': 'sha256:' + 'b' * 64,
            'checks': ['backend-pytest', 'frontend-vitest', 'frontend-typecheck-build', 'release-tool-tests'],
            'files': {},
        }
        for name in ('frontend.tar.gz', 'backend-image.tar.gz'):
            (self.root / name).write_bytes(b'artifact')
            self.manifest['files'][name] = digest(self.root / name)
        self.save()

    def save(self):
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))

    def test_accepts_matching_artifacts(self):
        self.assertEqual(verify_bundle(self.root), self.manifest)

    def test_rejects_changed_artifact(self):
        (self.root / 'frontend.tar.gz').write_bytes(b'different build')
        with self.assertRaisesRegex(ValueError, 'Checksum'):
            verify_bundle(self.root)

    def test_rejects_frontend_backend_revision_mismatch(self):
        self.manifest['image'] = 'langear-release:' + 'c' * 40
        self.save()
        with self.assertRaisesRegex(ValueError, 'Git SHA'):
            verify_bundle(self.root)

    def test_approval_is_bound_to_exact_manifest(self):
        approval = {'manifest_sha256': digest(self.root / 'manifest.json'),
                    'sha': self.manifest['sha'], 'image_id': self.manifest['image_id'], 'checks': 'login and recording'}
        (self.root / 'staging-approval.json').write_text(json.dumps(approval))
        verify_approval(self.root, self.manifest)
        self.manifest['image_id'] = 'sha256:' + 'd' * 64
        self.save()
        with self.assertRaisesRegex(ValueError, 'approval'):
            verify_approval(self.root, self.manifest)

    def test_rejects_archive_traversal_and_symlinks(self):
        for name, link in [('../outside', False), ('/absolute', False), ('index.html', True)]:
            archive = self.root / 'unsafe.tar.gz'
            with tarfile.open(archive, 'w:gz') as handle:
                entry = tarfile.TarInfo(name)
                if link:
                    entry.type = tarfile.SYMTYPE
                    entry.linkname = '../outside'
                    handle.addfile(entry)
                else:
                    entry.size = 1
                    handle.addfile(entry, io.BytesIO(b'x'))
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                extract_frontend(archive, self.root / 'web')

    def test_prepared_frontend_is_readable_by_nginx_workers(self):
        archive = self.root / 'valid.tar.gz'
        with tarfile.open(archive, 'w:gz') as handle:
            entry = tarfile.TarInfo('index.html')
            entry.size = 2
            entry.mode = 0o644
            handle.addfile(entry, io.BytesIO(b'ok'))
        destination = self.root / 'prepared'
        destination.mkdir(mode=0o700)
        extract_frontend(archive, destination)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o755)
        self.assertEqual((destination / 'index.html').read_text(), 'ok')

    def test_fixed_release_removes_only_the_isolated_development_proxy(self):
        deployment = object.__new__(Deployment)
        deployment.environment = 'staging'
        deployment.root = self.root
        (self.root / 'compose').mkdir()
        path = self.root / 'compose/nginx.preview.conf'
        path.write_text('server {\n    # BEGIN REVIEW DEVELOPMENT PROXY\n    location /api/content/ { proxy_pass http://task:8000/api/; }\n    # END REVIEW DEVELOPMENT PROXY\n    location /api/ { proxy_pass http://backend:8000; }\n}\n')
        deployment.release_proxy()
        self.assertNotIn('task:8000', path.read_text())
        self.assertIn('http://backend:8000', path.read_text())

    def test_release_overlay_removes_source_mount(self):
        config = overlay(self.manifest['image_id'], self.root, True)
        self.assertIn('volumes: !override', config)
        self.assertIn('working_dir: /app', config)
        self.assertNotIn('--reload', config)

    def test_review_overlay_runs_both_apis_and_worker_from_one_image(self):
        for immutable in (True, False):
            config = overlay(self.manifest['image_id'], self.root, immutable, runtime='review')
            self.assertIn('app.release:app', config)
            self.assertIn('review-worker:', config)
            self.assertEqual(config.count(self.manifest['image_id']), 2)
            self.assertIn('core.processing, --healthcheck', config)
            self.assertIn('env/review.env', config)
            self.assertEqual('--reload' in config, not immutable)

    def test_core_only_overlays_drop_legacy_entry_point_and_keep_worker(self):
        for runtime in ('core', 'core-v1'):
            for immutable in (True, False):
                with self.subTest(runtime=runtime, immutable=immutable):
                    config = overlay(self.manifest['image_id'], self.root, immutable, runtime=runtime)
                    self.assertIn('core.core_only:app', config)
                    self.assertNotIn('app.release:app', config)
                    self.assertIn('review-worker:', config)
                    self.assertIn('core.processing, --healthcheck', config)
                    self.assertIn('env/review.env', config)

    def test_core_runtime_manifests_require_postgres_core_tests(self):
        for runtime in ('review', 'core', 'core-v1'):
            with self.subTest(runtime=runtime):
                self.manifest.update(schema=2, runtime=runtime,
                                     checks=['backend-pytest', 'frontend-vitest',
                                             'frontend-typecheck-build', 'release-tool-tests'])
                self.save()
                with self.assertRaisesRegex(ValueError, 'Missing CI'):
                    verify_bundle(self.root)
                self.manifest['checks'].append('collection-core-pytest')
                self.save()
                self.assertEqual(verify_bundle(self.root)['runtime'], runtime)

    def test_legacy_runtime_keeps_the_legacy_entry_point(self):
        config = overlay(self.manifest['image_id'], self.root, True, runtime='legacy')
        self.assertIn('app.main:app', config)
        self.assertNotIn('core.core_only:app', config)
        self.assertNotIn('review-worker:', config)

    def test_review_is_not_core_only_and_keeps_legacy_schema_gates(self):
        self.assertFalse(is_core_only('review'))
        self.assertTrue(is_core_only('core'))
        self.assertTrue(is_core_only('core-v1'))
        self.assertTrue(is_core_runtime('review'))

    def test_frontend_smoke_check_covers_official_and_alias_prefixes(self):
        def urls_for(runtime):
            deployment = object.__new__(Deployment)
            deployment.environment = 'staging'
            urls = []

            def fake(*args, capture=False):
                url = args[-1]
                urls.append(url)
                return json.dumps({'sha': 'a' * 40}) if url.endswith('/release.json') else '401'

            with patch('host.run', side_effect=fake):
                deployment.check_frontend('a' * 40, runtime)
            return urls

        for runtime in ('core', 'core-v1'):
            urls = urls_for(runtime)
            self.assertTrue(any(url.endswith('/api/v1/auth/me') for url in urls))
            self.assertTrue(any(url.endswith('/api/content/v1/auth/me') for url in urls))
        legacy_urls = urls_for('legacy')
        self.assertTrue(any(url.endswith('/api/v1/auth/me') for url in legacy_urls))
        self.assertFalse(any('/api/content/v1/auth/me' in url for url in legacy_urls))

    def test_core_v1_rollback_skips_the_legacy_schema_gate(self):
        deployment = object.__new__(Deployment)
        deployment.environment = 'staging'
        deployment.root = self.root
        deployment.state_path = self.root / 'current.json'
        previous = {
            'image_id': 'sha256:' + 'b' * 64,
            'web': str(self.root / 'web'),
            'override': 'services:\n  backend:\n    image: "candidate"\n',
            'db_revision': ['legacy'],
            'state': {'runtime': 'core-v1'},
        }
        with patch.object(deployment, 'db_revision') as db_revision, \
                patch.object(deployment, 'start'), \
                patch.object(deployment, 'healthy'), \
                patch.object(deployment, 'switch_web'), \
                patch('host.write_json'):
            deployment.restore(previous)
        db_revision.assert_not_called()

    def test_review_release_requires_explicit_database_configuration(self):
        deployment = object.__new__(Deployment)
        deployment.root = self.root
        with patch('host.run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Provision'):
                deployment.core_revision('candidate')
            run.assert_not_called()

    def test_rollback_refuses_review_schema_drift_before_mutation(self):
        deployment = object.__new__(Deployment)
        with patch.object(deployment, 'db_revision', return_value=['legacy']), patch.object(deployment, 'core_revision', return_value=['new']), patch.object(deployment, 'compose') as compose:
            with self.assertRaisesRegex(RuntimeError, 'Review database revision changed'):
                deployment.restore({'db_revision': ['legacy'], 'core_db_revision': ['old'], 'core_probe_image': 'candidate'})
            compose.assert_not_called()

    def test_rollback_refuses_schema_change_before_mutation(self):
        deployment = object.__new__(Deployment)
        with patch.object(deployment, 'db_revision', return_value=['new']), patch.object(deployment, 'compose') as compose:
            with self.assertRaisesRegex(RuntimeError, 'revision changed'):
                deployment.restore({'db_revision': ['old']})
            compose.assert_not_called()

    def test_stage_uses_workflow_path_despite_old_github_display_name(self):
        metadata = {'conclusion': 'success', 'event': 'workflow_dispatch',
                    'path': '.github/workflows/frontend-dev-deploy.yml',
                    'name': 'Frontend Dev Deploy', 'head_sha': self.manifest['sha']}
        with patch('manage.run', return_value=json.dumps(metadata)), \
                patch('manage.tempfile.TemporaryDirectory', return_value=contextlib.nullcontext(str(self.root))), \
                patch('manage.upload', return_value='/remote/bundle') as upload, \
                patch('manage.invoke') as invoke:
            stage('123')
            upload.assert_called_once_with('staging', self.root, self.manifest['sha'])
            invoke.assert_called_once_with('staging', 'deploy', '--bundle', '/remote/bundle')

    def test_stage_refuses_pr_merge_artifacts(self):
        metadata = {'conclusion': 'success', 'event': 'pull_request',
                    'path': '.github/workflows/frontend-dev-deploy.yml'}
        with patch('manage.run', return_value=json.dumps(metadata)), patch('manage.upload') as upload:
            with self.assertRaises(SystemExit):
                stage('123')
            upload.assert_not_called()


if __name__ == '__main__':
    unittest.main()
