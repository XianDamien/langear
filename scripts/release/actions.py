"""GitHub Actions SSH client. Only release metadata and tooling cross SSH."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from host import ROOTS, verify_approval, verify_bundle


# Sent over SSH as code, with the data envelope on stdin. The application images
# are pulled by the host. The registry token never reaches a file or command line.
BOOTSTRAP = '''
import json, os, pathlib, subprocess, sys
data = json.load(sys.stdin)
root = pathlib.Path(data['root'])
bundle = root / 'releases' / data['sha']
bundle.mkdir(parents=True, exist_ok=True)
for name, content in data['files'].items():
    target = bundle / name
    if target.exists() and target.read_text() != content:
        raise RuntimeError('Refusing to overwrite release file: ' + name)
    target.write_text(content)
command = ['python3', str(bundle / 'host.py'), data['environment'], data['action']]
if data['action'] == 'deploy':
    (root / 'releases/nginx.preview.conf').write_text(data['proxy'])
    command += ['--bundle', str(bundle), '--registry-user', data['registry_user']]
elif data['action'] == 'approve':
    state = json.loads((root / 'releases/current.json').read_text())
    if state.get('sha') != data['sha'] or state.get('mode') != 'release':
        raise RuntimeError('Requested release is no longer running on staging')
    command += ['--checks', data['checks']]
result = subprocess.run(command, input=data.get('registry_token', ''), text=True,
                        stdout=sys.stderr)
if result.returncode:
    sys.exit(result.returncode)
if data['action'] == 'approve':
    print((bundle / 'staging-approval.json').read_text())
'''


def execute(environment, action, directory, checks=''):
    manifest = verify_bundle(directory)
    if manifest['schema'] != 3:
        raise ValueError('Actions deployment requires registry artifacts')
    if environment == 'prod':
        verify_approval(directory, manifest)
    source = Path(__file__).resolve().parents[2]
    files = {'manifest.json': (directory / 'manifest.json').read_text(),
             'host.py': Path(__file__).with_name('host.py').read_text()}
    if environment == 'prod':
        files['staging-approval.json'] = (directory / 'staging-approval.json').read_text()
    data = {
        'environment': environment, 'action': action, 'sha': manifest['sha'],
        'root': str(ROOTS[environment]), 'files': files,
        'proxy': (source / 'compose/nginx.preview.conf').read_text(),
        'registry_user': os.environ.get('REGISTRY_USER', ''),
        'registry_token': os.environ.get('REGISTRY_TOKEN', ''), 'checks': checks,
    }
    with tempfile.TemporaryDirectory(prefix='langear-ssh-') as tmp:
        key, known_hosts = Path(tmp) / 'key', Path(tmp) / 'known_hosts'
        key.write_text(os.environ['DEPLOY_SSH_KEY'] + '\n')
        key.chmod(0o600)
        known_hosts.write_text(os.environ['DEPLOY_KNOWN_HOSTS'] + '\n')
        command = ['ssh', '-i', str(key), '-p', str(int(os.environ['DEPLOY_PORT'])),
                   '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
                   '-o', 'ConnectTimeout=20', '-o', 'StrictHostKeyChecking=yes',
                   '-o', 'UserKnownHostsFile=' + str(known_hosts),
                   '-l', os.environ['DEPLOY_USER'], '--', os.environ['DEPLOY_HOST'],
                   shlex.join(['python3', '-c', BOOTSTRAP])]
        result = subprocess.run(command, input=json.dumps(data), text=True, check=True,
                                stdout=subprocess.PIPE)
    if action == 'approve':
        approval = json.loads(result.stdout)
        (directory / 'staging-approval.json').write_text(json.dumps(approval, indent=2) + '\n')
        verify_approval(directory, manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('environment', choices=ROOTS)
    parser.add_argument('action', choices=('deploy', 'approve'))
    parser.add_argument('--directory', type=Path, default=Path('release'))
    parser.add_argument('--checks', default='')
    args = parser.parse_args()
    if args.action == 'approve' and (args.environment != 'staging' or not args.checks.strip()):
        parser.error('Approval requires staging and completed acceptance checks')
    execute(args.environment, args.action, args.directory, args.checks)


if __name__ == '__main__':
    main()
