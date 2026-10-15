"""Mac entry point: stage a successful CI bundle, approve, then promote exact artifacts."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

HOSTS = {'staging': 'zhaohui-staging-server', 'prod': 'langear-prod'}
ROOTS = {'staging': '/home/kemove/langear/dev', 'prod': '/srv/langear/prod'}
SCRIPT = Path(__file__).with_name('host.py')


def run(*args, capture=False):
    result = subprocess.run([str(a) for a in args], check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else None


def ssh(environment, *args, capture=False):
    return run('ssh', HOSTS[environment], shlex.join([str(a) for a in args]), capture=capture)


def install_tool(environment):
    directory = ROOTS[environment] + '/releases'
    ssh(environment, 'mkdir', '-p', directory)
    run('scp', SCRIPT, HOSTS[environment] + ':' + directory + '/host.py')


def invoke(environment, action, *args):
    install_tool(environment)
    ssh(environment, 'python3', ROOTS[environment] + '/releases/host.py', environment, action, *args)


def upload(environment, directory, sha):
    target = ROOTS[environment] + '/releases/' + sha
    # Do not overwrite an existing bundle or its acceptance/rollback record.
    ssh(environment, 'mkdir', '-p', ROOTS[environment] + '/releases')
    ssh(environment, 'mkdir', target)
    for name in ('manifest.json', 'frontend.tar.gz', 'backend-image.tar.gz', 'staging-approval.json'):
        path = directory / name
        if path.exists():
            run('scp', path, HOSTS[environment] + ':' + target + '/' + name)
    return target


def stage(run_id):
    metadata = json.loads(run('gh', 'api', 'repos/{owner}/{repo}/actions/runs/' + run_id, capture=True))
    if (metadata['conclusion'] != 'success' or metadata['event'] not in ('push', 'workflow_dispatch')
            or metadata['path'] != '.github/workflows/frontend-dev-deploy.yml'):
        raise SystemExit('Use a successful push/workflow_dispatch run of Verify and Package Release')
    # GitHub retains the old workflow display name until the default branch is updated.
    sha = metadata['head_sha']
    with tempfile.TemporaryDirectory(prefix='langear-release-') as tmp:
        directory = Path(tmp)
        run('gh', 'run', 'download', run_id, '--name', 'langear-release-' + sha, '--dir', directory)
        manifest = json.loads((directory / 'manifest.json').read_text())
        if manifest['sha'] != sha:
            raise SystemExit('CI run and bundle revisions differ')
        from host import verify_bundle
        verify_bundle(directory)
        target = upload('staging', directory, sha)
        invoke('staging', 'deploy', '--bundle', target)


def promote(sha, execute):
    with tempfile.TemporaryDirectory(prefix='langear-promote-') as tmp:
        directory = Path(tmp)
        source = HOSTS['staging'] + ':' + ROOTS['staging'] + '/releases/' + sha + '/'
        for name in ('manifest.json', 'staging-approval.json'):
            run('scp', source + name, directory / name)
        from host import verify_approval, verify_bundle
        manifest = json.loads((directory / 'manifest.json').read_text())
        approval = verify_approval(directory, manifest)
        if manifest['sha'] != sha:
            raise SystemExit('Requested SHA does not match staging manifest')
        print(json.dumps({'target': HOSTS['prod'], 'sha': sha, 'image_id': manifest['image_id'],
                          'staging_checks': approval['checks'], 'execute': execute}, indent=2), flush=True)
        if not execute:
            print('Plan only. After production release authorization, repeat with --execute.')
            return
        for name in ('frontend.tar.gz', 'backend-image.tar.gz'):
            run('scp', source + name, directory / name)
        verify_bundle(directory)
        target = upload('prod', directory, sha)
        invoke('prod', 'deploy', '--bundle', target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    stage_parser = sub.add_parser('stage', help='Deploy a successful CI run to the staging preview')
    stage_parser.add_argument('--run', required=True)
    approve = sub.add_parser('approve', help='Record completed staging acceptance checks')
    approve.add_argument('--checks', required=True)
    promotion = sub.add_parser('promote', help='Plan production promotion; --execute performs it')
    promotion.add_argument('--sha', required=True)
    promotion.add_argument('--execute', action='store_true')
    rollback = sub.add_parser('rollback')
    rollback.add_argument('environment', choices=HOSTS)
    rollback.add_argument('--execute', action='store_true')
    sub.add_parser('dev', help='Restore staging source mount and hot reload')
    status = sub.add_parser('status')
    status.add_argument('environment', choices=HOSTS)
    args = parser.parse_args()
    if args.action == 'stage':
        stage(args.run)
    elif args.action == 'approve':
        invoke('staging', 'approve', '--checks', args.checks)
    elif args.action == 'promote':
        if not re.fullmatch(r'[0-9a-f]{40}', args.sha):
            parser.error('--sha requires a full Git SHA')
        promote(args.sha, args.execute)
    elif args.action == 'rollback':
        if args.environment == 'prod' and not args.execute:
            print('Plan: restore previous production frontend/backend; add --execute after authorization.')
            return
        invoke(args.environment, 'rollback')
    elif args.action == 'dev':
        invoke('staging', 'dev')
    else:
        # Read-only status does not install files on the target.
        source = SCRIPT.read_text()
        result = subprocess.run(['ssh', HOSTS[args.environment], 'python3 - ' + args.environment + ' status'],
                                input=source, text=True, check=True)


if __name__ == '__main__':
    main()
