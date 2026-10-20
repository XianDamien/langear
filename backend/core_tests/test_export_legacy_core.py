import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_legacy_core.py"


def load_script():
    spec = importlib.util.spec_from_file_location("export_legacy_core", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_environment_defaults_select_the_matching_container():
    module = load_script()
    assert module.container_name("staging") == "langear-staging-dev-postgres"
    assert module.container_name("prod") == "langear-prod-postgres"


def test_explicit_container_must_match_the_environment():
    module = load_script()
    assert module.container_name("prod", "langear-prod-postgres-blue") == "langear-prod-postgres-blue"
    for environment, name in (
        ("prod", "langear-staging-dev-postgres"),
        ("prod", "x-prod-staging"),
        ("staging", "langear-prod-postgres"),
    ):
        with pytest.raises(ValueError, match=environment):
            module.container_name(environment, name)
