"""
Unit tests for SettingsRepository.

Tests settings repository operations including:
- Getting settings by key
- Setting/updating settings
- Getting all settings
- JSON value handling
- Handling non-existent settings
"""

import pytest
from sqlalchemy.orm import Session
from app.repositories.settings_repo import SettingsRepository
from app.models.setting import Setting


@pytest.mark.unit
class TestSettingsRepository:
    """Test SettingsRepository operations."""

    def test_get_nonexistent_setting(self, test_db: Session):
        """Test getting a setting that doesn't exist."""
        repo = SettingsRepository(test_db)

        value = repo.get("nonexistent_key")

        assert value is None

    def test_get_existing_setting(self, test_db: Session):
        """Test getting a setting that exists."""
        repo = SettingsRepository(test_db)

        # Create a setting
        setting = Setting(key="test_key", value={"data": "test_value"})
        test_db.add(setting)
        test_db.commit()

        # Get the setting
        value = repo.get("test_key")

        assert value == {"data": "test_value"}

    def test_get_setting_with_string_value(self, test_db: Session):
        """Test getting a setting with a simple string value."""
        repo = SettingsRepository(test_db)

        # Create setting with string value
        setting = Setting(key="app_name", value="LanGear")
        test_db.add(setting)
        test_db.commit()

        value = repo.get("app_name")

        assert value == "LanGear"

    def test_get_setting_with_number_value(self, test_db: Session):
        """Test getting a setting with a number value."""
        repo = SettingsRepository(test_db)

        # Create setting with number value
        setting = Setting(key="max_cards", value=100)
        test_db.add(setting)
        test_db.commit()

        value = repo.get("max_cards")

        assert value == 100

    def test_get_setting_with_boolean_value(self, test_db: Session):
        """Test getting a setting with a boolean value."""
        repo = SettingsRepository(test_db)

        # Create setting with boolean value
        setting = Setting(key="enable_audio", value=True)
        test_db.add(setting)
        test_db.commit()

        value = repo.get("enable_audio")

        assert value is True

    def test_get_setting_with_dict_value(self, test_db: Session):
        """Test getting a setting with a dictionary value."""
        repo = SettingsRepository(test_db)

        # Create setting with dict value
        config = {
            "daily_new_cards": 20,
            "daily_review_cards": 50,
            "max_interval": 365
        }
        setting = Setting(key="srs_config", value=config)
        test_db.add(setting)
        test_db.commit()

        value = repo.get("srs_config")

        assert value == config
        assert value["daily_new_cards"] == 20

    def test_get_setting_with_list_value(self, test_db: Session):
        """Test getting a setting with a list value."""
        repo = SettingsRepository(test_db)

        # Create setting with list value
        themes = ["light", "dark", "auto"]
        setting = Setting(key="available_themes", value=themes)
        test_db.add(setting)
        test_db.commit()

        value = repo.get("available_themes")

        assert value == themes
        assert len(value) == 3

    def test_set_new_setting(self, test_db: Session):
        """Test setting a new setting that doesn't exist."""
        repo = SettingsRepository(test_db)

        # Set new setting
        setting = repo.set("new_key", {"value": "new_data"})

        assert setting.key == "new_key"
        assert setting.value == {"value": "new_data"}

        # Verify it was persisted
        test_db.commit()
        retrieved = repo.get("new_key")
        assert retrieved == {"value": "new_data"}

    def test_set_update_existing_setting(self, test_db: Session):
        """Test updating an existing setting."""
        repo = SettingsRepository(test_db)

        # Create initial setting
        initial_setting = Setting(key="update_test", value={"version": 1})
        test_db.add(initial_setting)
        test_db.commit()

        # Update the setting
        updated_setting = repo.set("update_test", {"version": 2, "updated": True})

        assert updated_setting.key == "update_test"
        assert updated_setting.value == {"version": 2, "updated": True}

        # Verify update was persisted
        test_db.commit()
        retrieved = repo.get("update_test")
        assert retrieved == {"version": 2, "updated": True}

    def test_set_multiple_updates(self, test_db: Session):
        """Test updating the same setting multiple times."""
        repo = SettingsRepository(test_db)

        # First set
        repo.set("counter", 0)
        test_db.commit()
        assert repo.get("counter") == 0

        # Second update
        repo.set("counter", 1)
        test_db.commit()
        assert repo.get("counter") == 1

        # Third update
        repo.set("counter", 2)
        test_db.commit()
        assert repo.get("counter") == 2

    def test_set_different_value_types(self, test_db: Session):
        """Test setting values of different types."""
        repo = SettingsRepository(test_db)

        # String
        repo.set("str_setting", "hello")
        assert repo.get("str_setting") == "hello"

        # Number
        repo.set("num_setting", 42)
        assert repo.get("num_setting") == 42

        # Boolean
        repo.set("bool_setting", False)
        assert repo.get("bool_setting") is False

        # Dict
        repo.set("dict_setting", {"key": "value"})
        assert repo.get("dict_setting") == {"key": "value"}

        # List
        repo.set("list_setting", [1, 2, 3])
        assert repo.get("list_setting") == [1, 2, 3]

    def test_set_nested_json(self, test_db: Session):
        """Test setting a nested JSON structure."""
        repo = SettingsRepository(test_db)

        nested_config = {
            "srs": {
                "new_cards": {
                    "daily_limit": 20,
                    "order": "random"
                },
                "review_cards": {
                    "daily_limit": 50,
                    "order": "due_date"
                }
            },
            "ui": {
                "theme": "dark",
                "language": "en",
                "features": ["audio", "hints", "auto_advance"]
            }
        }

        setting = repo.set("app_config", nested_config)
        test_db.commit()

        retrieved = repo.get("app_config")

        assert retrieved == nested_config
        assert retrieved["srs"]["new_cards"]["daily_limit"] == 20
        assert "audio" in retrieved["ui"]["features"]

    def test_get_all_empty(self, test_db: Session):
        """Test getting all settings when database is empty."""
        repo = SettingsRepository(test_db)

        all_settings = repo.get_all()

        assert all_settings == {}

    def test_get_all_single_setting(self, test_db: Session):
        """Test getting all settings when one setting exists."""
        repo = SettingsRepository(test_db)

        # Create a setting
        setting = Setting(key="only_key", value={"only": "value"})
        test_db.add(setting)
        test_db.commit()

        all_settings = repo.get_all()

        assert len(all_settings) == 1
        assert all_settings["only_key"] == {"only": "value"}

    def test_get_all_multiple_settings(self, test_db: Session):
        """Test getting all settings when multiple settings exist."""
        repo = SettingsRepository(test_db)

        # Create multiple settings
        settings_data = {
            "setting1": "value1",
            "setting2": 42,
            "setting3": {"nested": "data"},
            "setting4": [1, 2, 3],
            "setting5": True
        }

        for key, value in settings_data.items():
            repo.set(key, value)

        test_db.commit()

        all_settings = repo.get_all()

        assert len(all_settings) == 5
        for key, value in settings_data.items():
            assert all_settings[key] == value

    def test_get_all_returns_dict(self, test_db: Session):
        """Test that get_all returns a dictionary."""
        repo = SettingsRepository(test_db)

        # Create some settings
        repo.set("key1", "value1")
        repo.set("key2", "value2")
        test_db.commit()

        all_settings = repo.get_all()

        assert isinstance(all_settings, dict)
        assert "key1" in all_settings
        assert "key2" in all_settings

    def test_set_overwrites_completely(self, test_db: Session):
        """Test that set completely overwrites the previous value."""
        repo = SettingsRepository(test_db)

        # Set initial complex value
        initial = {
            "field1": "value1",
            "field2": "value2",
            "field3": "value3"
        }
        repo.set("config", initial)
        test_db.commit()

        # Update with completely different value
        new = {
            "different_field": "different_value"
        }
        repo.set("config", new)
        test_db.commit()

        # Should be completely replaced, not merged
        retrieved = repo.get("config")
        assert retrieved == new
        assert "field1" not in retrieved

    def test_set_with_null_value(self, test_db: Session):
        """Test setting a null value."""
        repo = SettingsRepository(test_db)

        setting = repo.set("nullable_key", None)

        assert setting.value is None
        assert repo.get("nullable_key") is None

    def test_set_with_empty_dict(self, test_db: Session):
        """Test setting an empty dictionary."""
        repo = SettingsRepository(test_db)

        setting = repo.set("empty_dict", {})

        assert setting.value == {}
        assert repo.get("empty_dict") == {}

    def test_set_with_empty_list(self, test_db: Session):
        """Test setting an empty list."""
        repo = SettingsRepository(test_db)

        setting = repo.set("empty_list", [])

        assert setting.value == []
        assert repo.get("empty_list") == []

    def test_multiple_repositories_share_data(self, test_db: Session):
        """Test that multiple repository instances share the same database."""
        repo1 = SettingsRepository(test_db)
        repo2 = SettingsRepository(test_db)

        # Set with repo1
        repo1.set("shared_key", "shared_value")
        test_db.commit()

        # Get with repo2
        value = repo2.get("shared_key")

        assert value == "shared_value"

    def test_realistic_config_scenario(self, test_db: Session):
        """Test a realistic configuration management scenario."""
        repo = SettingsRepository(test_db)

        # Initial setup
        repo.set("daily_new_cards", 20)
        repo.set("daily_review_cards", 50)
        repo.set("enable_audio", True)
        repo.set("theme", "dark")
        test_db.commit()

        # User changes settings
        repo.set("daily_new_cards", 30)
        repo.set("theme", "light")
        test_db.commit()

        # Verify changes
        all_settings = repo.get_all()
        assert all_settings["daily_new_cards"] == 30
        assert all_settings["daily_review_cards"] == 50  # Unchanged
        assert all_settings["theme"] == "light"
        assert all_settings["enable_audio"] is True  # Unchanged

    def test_unicode_in_settings(self, test_db: Session):
        """Test that settings can handle Unicode characters."""
        repo = SettingsRepository(test_db)

        unicode_data = {
            "greeting": "你好",
            "emoji": "🎉",
            "mixed": "Hello 世界 👋"
        }

        repo.set("unicode_test", unicode_data)
        test_db.commit()

        retrieved = repo.get("unicode_test")

        assert retrieved == unicode_data
        assert retrieved["greeting"] == "你好"
        assert retrieved["emoji"] == "🎉"
