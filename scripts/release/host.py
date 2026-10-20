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

# Both contracts run the same core API and worker. They differ only in the
# frontend API base: core uses /api/content/v1 (Release A), core-v1 uses /api/v1
# (Release B). Both still serve the /api/content alias.
RUNTIMES = ('core', 'core-v1')


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
    if manifest.get('schema') != 2 or not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Invalid manifest schema or Git SHA')
    if manifest['image'] != f'langear-release:{sha}':
        raise ValueError('Image tag must match Git SHA')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', manifest['image_id']):
        raise ValueError('Invalid image ID')
    if set(manifest['files']) != {'frontend.tar.gz', 'backend-image.tar.gz'}:
        raise ValueError('Unexpected bundle files')
    required = {
        'frontend-vitest', 'frontend-typecheck-build', 'release-tool-tests',
        'collection-core-pytest',
    }
    runtime = manifest.get('runtime')
    if runtime not in RUNTIMES:
        raise ValueError('Unknown runtime contract')
    if set(manifest.get('checks', [])) != required:
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
    # Both runtime contracts use the same core-only entry point while the
    # /api/content alias is still required. Only the frontend base differs.
    app = 'core.core_only:app'
    directory = '/app' if immutable else '/workspace/backend'
    result = 'services:\n  backend:\n    image: ' + json.dumps(image) + '\n'
    result += (f'    working_dir: {directory}\n    environment:\n      PYTHONPATH: {directory}\n'
               f'    command: [uvicorn, {app}, --host, 0.0.0.0, --port, "8000"' +
               (']\n' if immutable else ', --reload]\n'))
    if immutable:
        result += '    volumes: !override\n      - ' + json.dumps(str(root / 'data/backend') + ':/app/data') + '\n'
    env = '    env_file: !override\n      - ' + json.dumps(str(root / 'env/backend.env')) + '\n      - ' + json.dumps(str(root / 'env/review.env')) + '\n'
    result += env + '    networks:\n      default: {}\n      review-storage: {}\n'
    result += ('  review-worker:\n    image: ' + json.dumps(image) + '\n'
               f'    working_dir: {directory}\n    environment:\n      PYTHONPATH: {directory}\n'
               '    command: [python, -m, core.processing]\n' + env +
               '    networks:\n      default: {}\n      review-storage: {}\n'
               '    restart: unless-stopped\n    mem_limit: 1g\n'
               '    depends_on:\n      backend:\n        condition: service_healthy\n'
               '    healthcheck:\n      test: [CMD, python, -m, core.processing, --healthcheck]\n'
               '      interval: 10s\n      timeout: 5s\n      start_period: 20s\n      retries: 3\n')
    if not immutable:
        result += '    volumes: !override\n      - ' + json.dumps(str(root / 'repo/backend') + ':/workspace/backend') + '\n'
    result += ('networks:\n  review-storage:\n    external: true\n    name: ' +
               json.dumps('langear-prod-review' if root.name == 'prod' else 'langear-staging-review') + '\n')
    return result


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

    def services(self):
        names = self.compose('config', '--services', capture=True).splitlines()
        return ['backend'] + (['review-worker'] if 'review-worker' in names else [])

    def core_revision(self, image):
        env_file = self.root / 'env/review.env'
        if not env_file.is_file():
            raise RuntimeError('Provision env/review.env and migrate the independent Review database before release')
        network = 'langear-prod-review' if self.environment == 'prod' else 'langear-staging-review'
        run('docker', 'network', 'inspect', network, capture=True)
        code = ('import json; from sqlalchemy import text; from core.db import get_engine; '
                'c=get_engine().connect(); print(json.dumps(list(c.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num")).scalars())))')
        return json.loads(run('docker', 'run', '--rm', '--network', network, '--env-file', env_file,
                              '--entrypoint', 'python', image, '-c', code, capture=True))

    def start(self, content):
        old = self.services()
        # Stop the worker before replacing its API or environment.
        if 'review-worker' in old:
            self.compose('stop', '-t', '30', 'review-worker')
        self.override.write_text(content)
        self.compose('up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '90', *self.services())

    def snapshot(self):
        value = {
            'image_id': run('docker', 'inspect', '--format', '{{.Image}}', self.container, capture=True),
            'web': str((self.root / 'web/current').resolve(strict=True)),
            'override': self.override.read_text() if self.override.exists() else None,
            'state': json.loads(self.state_path.read_text()) if self.state_path.exists() else None,
        }
        if self.environment == 'staging':
            proxy = self.root / 'compose/nginx.preview.conf'
            value['preview_proxy'] = proxy.read_text() if proxy.exists() else None
        if 'review-worker' in self.services():
            worker = self.compose('ps', '-q', 'review-worker', capture=True)
            value['worker_image_id'] = run('docker', 'inspect', '--format', '{{.Image}}', worker, capture=True)
            value['core_db_revision'] = self.core_revision(value['image_id'])
            value['core_probe_image'] = value['image_id']
        return value

    def release_proxy(self):
        if self.environment == 'staging':
            path = self.root / 'compose/nginx.preview.conf'
            # Source development may route Core to an isolated task container.
            # A fixed release must serve Core from its own paired backend image.
            content = path.read_text()
            content = re.sub(r'(?ms)^    # BEGIN REVIEW DEVELOPMENT PROXY\n.*?^    # END REVIEW DEVELOPMENT PROXY\n', '', content)
            path.write_text(content)

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
                        if 'review-worker' in self.services():
                            worker = self.compose('ps', '-q', 'review-worker', capture=True)
                            status = run('docker', 'inspect', '--format', '{{.State.Health.Status}}', worker, capture=True)
                            if status != 'healthy':
                                time.sleep(2)
                                continue
                            with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/api/content/ready', timeout=3) as ready:
                                if json.load(ready).get('status') != 'ready':
                                    continue
                        return
            except (OSError, ValueError):
                pass
            time.sleep(2)
        raise RuntimeError('Backend health check failed')

    def restore(self, previous):
        state = previous.get('state') or {}
        # A managed release must name its core runtime; only a dev snapshot may
        # omit it. This refuses pre-core release records instead of defaulting them.
        runtime = state.get('runtime') if previous.get('override') else 'core'
        if runtime not in RUNTIMES:
            raise RuntimeError('Rollback target predates the core-only release contract')
        if previous.get('core_db_revision') is not None and self.core_revision(previous['core_probe_image']) != previous['core_db_revision']:
            raise RuntimeError('Core database revision changed; automatic rollback refused')
        content = previous['override'] or overlay(previous['image_id'], self.root, False)
        # Always restore the exact image, even if a mutable historical tag changed.
        content = re.sub(r'(?m)^    image: .+$', '    image: ' + json.dumps(previous['image_id']), content)
        self.start(content)
        self.healthy()
        if self.environment == 'staging' and previous.get('preview_proxy') is not None:
            (self.root / 'compose/nginx.preview.conf').write_text(previous['preview_proxy'])
        self.switch_web(previous['web'])
        write_json(self.state_path, previous['state'] or {'mode': 'dev' if self.environment == 'staging' else 'core'})

    def deploy(self, bundle):
        manifest = verify_bundle(bundle)
        runtime = manifest['runtime']
        approval = verify_approval(bundle, manifest) if self.environment == 'prod' else None
        previous = self.snapshot()
        run('docker', 'load', '-i', bundle / 'backend-image.tar.gz')
        info = json.loads(run('docker', 'image', 'inspect', manifest['image'], capture=True))[0]
        if info['Id'] != manifest['image_id'] or info['Config']['Labels'].get('org.opencontainers.image.revision') != manifest['sha']:
            raise RuntimeError('Loaded backend does not match manifest')
        core_heads_code = ('import json; from alembic.config import Config; from alembic.script import ScriptDirectory; '
                           'print(json.dumps(sorted(ScriptDirectory.from_config(Config("alembic-core.ini")).get_heads())))')
        core_heads = json.loads(run('docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'python',
                                    manifest['image_id'], '-c', core_heads_code, capture=True))
        core_revision = self.core_revision(manifest['image_id'])
        if core_heads != core_revision:
            raise RuntimeError('Core migrations differ from database; back up and migrate explicitly before release')
        if approval and approval.get('core_db_revision') != core_revision:
            raise RuntimeError('Core production schema differs from validated staging schema')
        previous['core_db_revision'] = core_revision
        previous['core_probe_image'] = manifest['image_id']
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
            self.start(overlay(manifest['image_id'], self.root, True))
            self.healthy()
            self.release_proxy()
            self.switch_web(web)
            self.check_frontend(manifest['sha'])
            write_json(self.state_path, {'mode': 'release', 'sha': manifest['sha'],
                       'image_id': manifest['image_id'], 'bundle': str(bundle),
                       'manifest_sha256': digest(bundle / 'manifest.json'),
                       'core_db_revision': core_heads, 'runtime': runtime})
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
        for prefix in ('/api/v1', '/api/content/v1'):
            code = run('curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}', *flags,
                       url + prefix + '/auth/me', capture=True)
            if code != '401':
                raise RuntimeError(f'API authentication smoke check failed for {prefix}')

    def approve(self, checks):
        state = json.loads(self.state_path.read_text())
        if self.environment != 'staging' or state['mode'] != 'release':
            raise RuntimeError('Only a deployed immutable staging release can be approved')
        bundle = Path(state['bundle'])
        manifest = verify_bundle(bundle)
        runtime = manifest['runtime']
        snapshot = self.snapshot()
        if (digest(bundle / 'manifest.json') != state['manifest_sha256']
                or snapshot['image_id'] != manifest['image_id']
                or snapshot.get('worker_image_id') != manifest['image_id']):
            raise RuntimeError('Running release or stored bundle changed')
        self.healthy()
        self.check_frontend(manifest['sha'])
        if snapshot.get('core_db_revision') != state.get('core_db_revision'):
            raise RuntimeError('Core database changed since release deployment')
        write_json(bundle / 'staging-approval.json', {
            'sha': manifest['sha'], 'image_id': manifest['image_id'],
            'manifest_sha256': state['manifest_sha256'],
            'core_db_revision': state.get('core_db_revision'),
            'runtime': runtime,
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
            if previous.get('worker_image_id'):
                self.start(overlay(previous['image_id'], self.root, False))
            else:
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
