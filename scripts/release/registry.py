"""Create the small release manifest; application bytes stay in GHCR."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from host import verify_bundle

CONFIG_DIGEST = re.compile(r'sha256:[0-9a-f]{64}')


def image(tag):
    info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', tag]))[0]
    repository = tag.rsplit(':', 1)[0]
    references = [ref for ref in info['RepoDigests'] if ref.startswith(repository + '@')]
    if len(references) != 1:
        raise ValueError('Expected exactly one pushed repository digest for ' + tag)
    reference = references[0]
    # The local image Id is not stable across Docker image stores; the registry
    # manifest's config digest is the image ID that classic-store hosts verify.
    manifest = json.loads(subprocess.check_output(['docker', 'manifest', 'inspect', reference]))
    config = manifest.get('config', {}).get('digest') if isinstance(manifest, dict) else None
    if not isinstance(config, str) or not CONFIG_DIGEST.fullmatch(config):
        raise ValueError('Expected a single-platform registry manifest for ' + reference)
    return reference, config


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
