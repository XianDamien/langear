"""Unit tests for SettingsService."""

import pytest
from sqlalchemy.orm import Session

from app.services.settings_service import SettingsService
from tests.test_data.seed_data import create_test_user_settings


@pytest.mark.unit
class TestSettingsService:
    """Test user-level settings service behavior."""

    def test_get_settings_creates_defaults(self, test_db: Session):
        service = SettingsService(test_db)

        result = service.get_settings(user_id=1)

        assert result == {
            "desired_retention": 0.9,
            "learning_steps": [15],
            "relearning_steps": [15],
            "maximum_interval": 36500,
            "default_source_scope": [],
        }

    def test_get_settings_with_existing_row(self, test_db: Session):
        create_test_user_settings(test_db)
        service = SettingsService(test_db)

        result = service.get_settings(user_id=1)

        assert result == {
            "desired_retention": 0.9,
            "learning_steps": [15],
            "relearning_steps": [15],
            "maximum_interval": 36500,
            "default_source_scope": [1, 2],
        }

    def test_update_settings_success(self, test_db: Session):
        create_test_user_settings(test_db)
        service = SettingsService(test_db)

        result = service.update_settings(
            user_id=1,
            updates={
                "desired_retention": 0.87,
                "learning_steps": [15, 1440],
                "relearning_steps": [15],
                "maximum_interval": 1000,
                "default_source_scope": [3],
            },
        )

        assert result["desired_retention"] == 0.87
        assert result["learning_steps"] == [15, 1440]
        assert result["relearning_steps"] == [15]
        assert result["maximum_interval"] == 1000
        assert result["default_source_scope"] == [3]

    def test_update_settings_preserves_unspecified_fields(self, test_db: Session):
        create_test_user_settings(test_db)
        service = SettingsService(test_db)

        result = service.update_settings(
            user_id=1,
            updates={"desired_retention": 0.88},
        )

        assert result["desired_retention"] == 0.88
        assert result["learning_steps"] == [15]
        assert result["relearning_steps"] == [15]
        assert result["maximum_interval"] == 36500
        assert result["default_source_scope"] == [1, 2]

    def test_update_settings_invalid_key(self, test_db: Session):
        service = SettingsService(test_db)

        with pytest.raises(ValueError, match="Invalid settings keys"):
            service.update_settings(user_id=1, updates={"invalid_key": 123})

    def test_update_settings_invalid_desired_retention(self, test_db: Session):
        service = SettingsService(test_db)

        with pytest.raises(ValueError, match="between 0 and 1"):
            service.update_settings(user_id=1, updates={"desired_retention": 0})

        with pytest.raises(ValueError, match="between 0 and 1"):
            service.update_settings(user_id=1, updates={"desired_retention": 1})

    def test_update_settings_invalid_step_lists(self, test_db: Session):
        service = SettingsService(test_db)

        with pytest.raises(ValueError, match="learning_steps must be a list"):
            service.update_settings(user_id=1, updates={"learning_steps": "15"})

        with pytest.raises(ValueError, match="positive integers only"):
            service.update_settings(user_id=1, updates={"relearning_steps": [15, 0]})

    def test_update_settings_invalid_maximum_interval(self, test_db: Session):
        service = SettingsService(test_db)

        with pytest.raises(ValueError, match="positive integer"):
            service.update_settings(user_id=1, updates={"maximum_interval": 0})

    def test_update_settings_invalid_default_source_scope(self, test_db: Session):
        service = SettingsService(test_db)

        with pytest.raises(ValueError, match="must be a list"):
            service.update_settings(user_id=1, updates={"default_source_scope": "1,2"})

        with pytest.raises(ValueError, match="positive integers only"):
            service.update_settings(user_id=1, updates={"default_source_scope": [1, -2]})
