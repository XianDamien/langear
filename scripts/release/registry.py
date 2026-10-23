"""Create the small release manifest; application bytes stay in GHCR."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from host import verify_bundle


def image(tag):
    info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', tag]))[0]
    repository = tag.rsplit(':', 1)[0]
    references = [ref for ref in info['RepoDigests'] if ref.startswith(repository + '@')]
    if len(references) != 1:
        raise ValueError('Expected exactly one pushed repository digest for ' + tag)
    return references[0], info['Id']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sha')
    parser.add_argument('backend')
    parser.add_argument('frontend')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    backend, backend_id = image(args.backend)
    frontend, frontend_id = image(args.frontend)
    manifest = {
        'schema': 3, 'sha': args.sha, 'runtime': os.environ.get('RELEASE_RUNTIME', 'core-v1'),
        'image': backend, 'image_id': backend_id,
        'frontend_image': frontend, 'frontend_image_id': frontend_id,
        'files': {},
        'checks': ['frontend-vitest', 'frontend-typecheck-build',
                   'release-tool-tests', 'collection-core-pytest'],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    verify_bundle(args.output)


if __name__ == '__main__':
    main()
