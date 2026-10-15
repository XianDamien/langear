import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from host import Deployment, digest, extract_frontend, overlay, verify_approval, verify_bundle


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

    def test_release_overlay_removes_source_mount(self):
        config = overlay(self.manifest['image_id'], self.root, True)
        self.assertIn('volumes: !override', config)
        self.assertIn('working_dir: /app', config)
        self.assertNotIn('--reload', config)

    def test_rollback_refuses_schema_change_before_mutation(self):
        deployment = object.__new__(Deployment)
        with patch.object(deployment, 'db_revision', return_value=['new']), patch.object(deployment, 'compose') as compose:
            with self.assertRaisesRegex(RuntimeError, 'revision changed'):
                deployment.restore({'db_revision': ['old']})
            compose.assert_not_called()


if __name__ == '__main__':
    unittest.main()
