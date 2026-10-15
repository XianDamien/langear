"""Server-side paired deployment. No migrations, DB resets, or Git checkout switches."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile
import time
import urllib.request

ROOTS = {'staging': Path('/home/kemove/langear/dev'), 'prod': Path('/srv/langear/prod')}


def run(*args, capture=False):
    result = subprocess.run([str(a) for a in args], check=True,
                            stdout=subprocess.PIPE if capture else None, text=True)
    return result.stdout.strip() if capture else None


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)


def verify_bundle(bundle):
    manifest = json.loads((bundle / 'manifest.json').read_text())
    sha = manifest['sha']
    if manifest.get('schema') != 1 or not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Invalid manifest schema or Git SHA')
    if manifest['image'] != f'langear-release:{sha}':
        raise ValueError('Image tag must match Git SHA')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', manifest['image_id']):
        raise ValueError('Invalid image ID')
    if set(manifest['files']) != {'frontend.tar.gz', 'backend-image.tar.gz'}:
        raise ValueError('Unexpected bundle files')
    if set(manifest.get('checks', [])) != {'backend-pytest', 'frontend-vitest', 'frontend-typecheck-build', 'release-tool-tests'}:
        raise ValueError('Missing CI checks')
    for name, expected in manifest['files'].items():
        if digest(bundle / name) != expected:
            raise ValueError(f'Checksum mismatch: {name}')
    return manifest


def extract_frontend(archive_path, destination):
    # Reject links, devices, and traversal before writing anything.
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                raise ValueError('Unsafe frontend archive member')
        archive.extractall(destination)
    if not (destination / 'index.html').is_file():
        raise ValueError('Missing frontend index.html')
    # TemporaryDirectory starts at 0700; Nginx workers need directory traversal.
    destination.chmod(0o755)


def verify_approval(bundle, manifest):
    approval = json.loads((bundle / 'staging-approval.json').read_text())
    if (approval['manifest_sha256'] != digest(bundle / 'manifest.json')
            or approval['sha'] != manifest['sha'] or approval['image_id'] != manifest['image_id']
            or not approval.get('checks', '').strip()):
        raise ValueError('Staging approval does not match these artifacts')
    return approval


def overlay(image, root, immutable):
    text = 'services:\n  backend:\n    image: ' + json.dumps(image) + '\n'
    if immutable:
        text += ('    working_dir: /app\n    environment:\n      PYTHONPATH: /app\n'
                 '    command: [uvicorn, app.main:app, --host, 0.0.0.0, --port, "8000"]\n'
                 '    volumes: !override\n      - ' + json.dumps(str(root / 'data/backend') + ':/app/data') + '\n')
    return text


class Deployment:
    def __init__(self, environment):
        self.environment = environment
        self.root = ROOTS[environment]
        self.base = self.root / 'compose/docker-compose.yml'
        self.override = self.root / 'compose/release.override.yml'
        self.state_dir = self.root / 'releases'
        self.state_path = self.state_dir / 'current.json'
        self.container = 'langear-staging-dev-backend' if environment == 'staging' else 'langear-prod-backend'
        self.port = 8004 if environment == 'staging' else 8000

    def compose(self, *args, capture=False):
        command = ['docker', 'compose', '-f', self.base]
        if self.override.exists():
            command += ['-f', self.override]
        return run(*command, *args, capture=capture)

    def db_revision(self):
        # Report only schema revisions, never connection strings or data.
        postgres = self.container.replace('-backend', '-postgres')
        output = run('docker', 'exec', postgres, 'sh', '-c',
                     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1 '
                     '-c "SELECT version_num FROM alembic_version ORDER BY version_num"', capture=True)
        return output.splitlines()

    def snapshot(self):
        return {
            'image_id': run('docker', 'inspect', '--format', '{{.Image}}', self.container, capture=True),
            'web': str((self.root / 'web/current').resolve(strict=True)),
            'override': self.override.read_text() if self.override.exists() else None,
            'db_revision': self.db_revision(),
            'state': json.loads(self.state_path.read_text()) if self.state_path.exists() else None,
        }

    def switch_web(self, path):
        link = self.root / 'web/.release-next'
        link.unlink(missing_ok=True)
        link.symlink_to(path)
        link.replace(self.root / 'web/current')
        if self.environment == 'staging':
            # Docker resolves bind-mount symlinks at container creation, not reload.
            self.compose('up', '-d', '--no-deps', '--force-recreate', 'web')

    def healthy(self):
        for _ in range(30):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/health', timeout=3) as response:
                    if json.load(response).get('status') == 'healthy':
                        return
            except (OSError, ValueError):
                pass
            time.sleep(2)
        raise RuntimeError('Backend health check failed')

    def restore(self, previous):
        if self.db_revision() != previous['db_revision']:
            raise RuntimeError('Database revision changed; automatic rollback refused')
        content = previous['override'] or overlay(previous['image_id'], self.root, False)
        # Always restore the exact image, even if a mutable historical tag changed.
        content = re.sub(r'(?m)^    image: .+$', '    image: ' + json.dumps(previous['image_id']), content)
        self.override.write_text(content)
        self.compose('up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '90', 'backend')
        self.healthy()
        self.switch_web(previous['web'])
        write_json(self.state_path, previous['state'] or {'mode': 'dev' if self.environment == 'staging' else 'legacy'})

    def deploy(self, bundle):
        manifest = verify_bundle(bundle)
        approval = verify_approval(bundle, manifest) if self.environment == 'prod' else None
        previous = self.snapshot()
        if approval and approval['db_revision'] != previous['db_revision']:
            raise RuntimeError('Production schema differs from validated staging schema; prepare migration separately')
        run('docker', 'load', '-i', bundle / 'backend-image.tar.gz')
        info = json.loads(run('docker', 'image', 'inspect', manifest['image'], capture=True))[0]
        if info['Id'] != manifest['image_id'] or info['Config']['Labels'].get('org.opencontainers.image.revision') != manifest['sha']:
            raise RuntimeError('Loaded backend does not match manifest')
        heads_code = ('import json; from alembic.config import Config; from alembic.script import ScriptDirectory; '
                      'print(json.dumps(sorted(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())))')
        heads = json.loads(run('docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'python',
                               manifest['image_id'], '-c', heads_code, capture=True))
        if heads != previous['db_revision']:
            raise RuntimeError('Candidate migrations differ from database; prepare and apply migration explicitly first')
        web = self.root / 'web/releases' / manifest['sha']
        if web.exists():
            raise RuntimeError('Release already installed; use rollback or a new commit, never overwrite artifacts')
        with tempfile.TemporaryDirectory(dir=web.parent, prefix='.prepare-') as tmp:
            extract_frontend(bundle / 'frontend.tar.gz', Path(tmp))
            if json.loads((Path(tmp) / 'release.json').read_text()) != {'sha': manifest['sha']}:
                raise RuntimeError('Frontend revision does not match backend')
            Path(tmp).rename(web)
        write_json(bundle / 'previous.json', previous)
        try:
            self.override.write_text(overlay(manifest['image_id'], self.root, True))
            self.compose('up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '90', 'backend')
            self.healthy()
            self.switch_web(web)
            self.check_frontend(manifest['sha'])
            write_json(self.state_path, {'mode': 'release', 'sha': manifest['sha'],
                       'image_id': manifest['image_id'], 'bundle': str(bundle),
                       'manifest_sha256': digest(bundle / 'manifest.json'), 'db_revision': heads})
        except Exception:
            self.restore(previous)
            raise
        print(json.dumps({'environment': self.environment, 'sha': manifest['sha'], 'status': 'deployed'}))

    def check_frontend(self, sha):
        # curl -k is limited to the known local staging self-signed endpoint.
        url = 'https://127.0.0.1:8445' if self.environment == 'staging' else 'http://127.0.0.1:8082'
        flags = ['-k'] if self.environment == 'staging' else []
        value = run('curl', '-fsS', '--retry', '5', '--retry-connrefused', '--retry-delay', '1', *flags, url + '/release.json', capture=True)
        if json.loads(value) != {'sha': sha}:
            raise RuntimeError('Served frontend revision is wrong')
        code = run('curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}', *flags, url + '/api/v1/auth/me', capture=True)
        if code != '401':
            raise RuntimeError('API authentication smoke check failed')

    def approve(self, checks):
        state = json.loads(self.state_path.read_text())
        if self.environment != 'staging' or state['mode'] != 'release':
            raise RuntimeError('Only a deployed immutable staging release can be approved')
        bundle = Path(state['bundle'])
        manifest = verify_bundle(bundle)
        if digest(bundle / 'manifest.json') != state['manifest_sha256'] or self.snapshot()['image_id'] != manifest['image_id']:
            raise RuntimeError('Running release or stored bundle changed')
        self.healthy()
        self.check_frontend(manifest['sha'])
        if self.db_revision() != state['db_revision']:
            raise RuntimeError('Database changed since release deployment')
        write_json(bundle / 'staging-approval.json', {
            'sha': manifest['sha'], 'image_id': manifest['image_id'],
            'manifest_sha256': state['manifest_sha256'], 'db_revision': state['db_revision'],
            'checks': checks, 'approved_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        })
        print('Staging approval recorded for ' + manifest['sha'])

    def rollback(self):
        state = json.loads(self.state_path.read_text())
        if state.get('mode') != 'release':
            raise RuntimeError('No managed release to roll back')
        self.restore(json.loads((Path(state['bundle']) / 'previous.json').read_text()))
        print('Restored previous frontend and backend; database unchanged')

    def dev(self):
        if self.environment != 'staging':
            raise RuntimeError('Hot reload is only available in staging')
        previous = self.snapshot()
        try:
            self.override.unlink(missing_ok=True)
            self.compose('up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '90', 'backend')
            self.healthy()
            # Refresh Nginx's backend DNS binding after container recreation.
            self.compose('up', '-d', '--no-deps', '--force-recreate', 'web')
            write_json(self.state_path, {'mode': 'dev', 'frontend': previous['web']})
        except Exception:
            self.restore(previous)
            raise
        print('Backend source reload enabled; frontend remains the last static preview build')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('environment', choices=ROOTS)
    parser.add_argument('action', choices=['deploy', 'approve', 'rollback', 'dev', 'status'])
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--checks')
    args = parser.parse_args()
    deployment = Deployment(args.environment)
    if args.action == 'status':
        print(json.dumps(deployment.snapshot(), indent=2))
        return
    deployment.state_dir.mkdir(exist_ok=True)
    with (deployment.state_dir / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'deploy':
            if not args.bundle or args.bundle.resolve().parent != deployment.state_dir.resolve():
                parser.error('Bundle must be a direct child of the environment releases directory')
            deployment.deploy(args.bundle.resolve())
        elif args.action == 'approve':
            if not args.checks or not args.checks.strip():
                parser.error('--checks must describe completed acceptance checks')
            deployment.approve(args.checks)
        else:
            getattr(deployment, args.action)()


if __name__ == '__main__':
    main()
