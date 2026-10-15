"""Package the tested frontend and saved backend image under one Git SHA."""
import hashlib
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    sha, dist, output = sys.argv[1:]
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise SystemExit('Expected a full Git SHA')
    dist, output = Path(dist), Path(output)
    image = f'langear-release:{sha}'
    info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image]))[0]
    if info['Config']['Labels'].get('org.opencontainers.image.revision') != sha:
        raise SystemExit('Backend image revision does not match frontend revision')
    (dist / 'release.json').write_text(json.dumps({'sha': sha}) + '\n')
    with tarfile.open(output / 'frontend.tar.gz', 'w:gz') as archive:
        for path in sorted(dist.iterdir()):
            archive.add(path, arcname=path.name)
    manifest = {
        'schema': 1, 'sha': sha, 'image': image, 'image_id': info['Id'],
        'checks': ['backend-pytest', 'frontend-vitest', 'frontend-typecheck-build', 'release-tool-tests'],
        'files': {name: digest(output / name) for name in ('frontend.tar.gz', 'backend-image.tar.gz')},
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
