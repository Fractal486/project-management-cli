"""Tests for configuration management (pm_live/config.py)."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pm_live.config import (
    CONFIG_FILE_NAME,
    Config,
    _apply_overrides,
    _default_theme,
    load_config,
    save_config,
    set_config,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def clean_env(monkeypatch):
    """Clean environment variables before each test."""
    monkeypatch.delenv("PM_DATA_FILE", raising=False)


# ==================== Default Config Tests ====================


def test_default_config_values():
    """Verify default configuration values are set correctly."""
    config = Config()
    assert config.console_width == 120
    assert config.data_file_path == "projects.json"
    assert config.max_project_name_length == 200
    assert config.enable_file_logging is True
    assert config.log_level_console == "INFO"
    assert config.log_level_file == "DEBUG"
    assert config.log_file_path == "pm_app.log"
    assert config.log_max_bytes == 5 * 1024 * 1024
    assert config.log_backup_count == 5
    assert config.deadline_display_mode == "relative"
    assert config.task_metadata_position == "below"


def test_default_theme_colors():
    """Verify default theme colors are set."""
    theme = _default_theme()
    assert theme["primary"] == "white"
    assert theme["accent"] == "magenta"
    assert theme["success"] == "green"
    assert theme["warning"] == "yellow"
    assert theme["error"] == "red"


def test_config_copy():
    """Test that config.copy() creates a deep copy."""
    config = Config()
    config.console_width = 100
    config.theme_colors["primary"] = "blue"

    copy = config.copy()
    assert copy.console_width == 100
    assert copy.theme_colors["primary"] == "blue"

    # Modify copy shouldn't affect original
    copy.console_width = 200
    copy.theme_colors["primary"] = "red"
    assert config.console_width == 100
    assert config.theme_colors["primary"] == "blue"


# ==================== Config Loading Tests ====================


def test_load_config_missing_file(temp_dir, clean_env):
    """Loading config from directory with no config file should return defaults."""
    config = load_config(temp_dir)
    assert config.console_width == 120
    assert config.data_file_path == "projects.json"


def test_load_valid_config_file(temp_dir, clean_env):
    """Load a valid TOML config file."""
    config_path = temp_dir / CONFIG_FILE_NAME
    config_path.write_text("""
console_width = 140
data_file_path = "custom.json"
max_project_name_length = 300

[theme_colors]
primary = "blue"
accent = "yellow"
""")

    config = load_config(temp_dir)
    assert config.console_width == 140
    assert config.data_file_path == "custom.json"
    assert config.max_project_name_length == 300
    assert config.theme_colors["primary"] == "blue"
    assert config.theme_colors["accent"] == "yellow"
    # Defaults should still be present for unspecified colors
    assert config.theme_colors["success"] == "green"


def test_load_empty_config_file(temp_dir, clean_env):
    """Empty config file should use all defaults."""
    config_path = temp_dir / CONFIG_FILE_NAME
    config_path.write_text("")

    config = load_config(temp_dir)
    assert config.console_width == 120
    assert config.data_file_path == "projects.json"


def test_load_invalid_toml_syntax(temp_dir, clean_env):
    """Invalid TOML should fall back to defaults without crashing."""
    config_path = temp_dir / CONFIG_FILE_NAME
    config_path.write_text("""
console_width = 140
[theme_colors
primary = "blue"  # Missing closing bracket
""")

    config = load_config(temp_dir)
    # Should fall back to defaults
    assert config.console_width == 120
    assert config.theme_colors["primary"] == "white"


def test_load_partial_config(temp_dir, clean_env):
    """Config with only some fields should use defaults for missing fields."""
    config_path = temp_dir / CONFIG_FILE_NAME
    config_path.write_text("""
console_width = 100
""")

    config = load_config(temp_dir)
    assert config.console_width == 100
    assert config.data_file_path == "projects.json"  # default
    assert config.max_project_name_length == 200  # default


# ==================== Apply Overrides Tests ====================


def test_apply_overrides_basic_types():
    """Test applying basic type overrides."""
    config = Config()
    overrides = {
        "console_width": 150,
        "data_file_path": "test.json",
        "max_project_name_length": 250,
        "enable_file_logging": False,
    }

    _apply_overrides(config, overrides)
    assert config.console_width == 150
    assert config.data_file_path == "test.json"
    assert config.max_project_name_length == 250
    assert config.enable_file_logging is False


def test_apply_overrides_logging_config():
    """Test applying logging configuration overrides."""
    config = Config()
    overrides = {
        "log_level_console": "warning",
        "log_level_file": "error",
        "log_file_path": "custom.log",
        "log_max_bytes": 10000,
        "log_backup_count": 3,
    }

    _apply_overrides(config, overrides)
    assert config.log_level_console == "WARNING"  # Should be uppercase
    assert config.log_level_file == "ERROR"
    assert config.log_file_path == "custom.log"
    assert config.log_max_bytes == 10000
    assert config.log_backup_count == 3


def test_apply_overrides_theme_colors():
    """Test applying theme color overrides."""
    config = Config()
    overrides = {
        "theme_colors": {
            "primary": "blue",
            "custom": "purple",
        }
    }

    _apply_overrides(config, overrides)
    assert config.theme_colors["primary"] == "blue"
    assert config.theme_colors["custom"] == "purple"
    # Other defaults should remain
    assert config.theme_colors["success"] == "green"


def test_apply_overrides_invalid_theme_colors():
    """Test that non-dict theme_colors are ignored."""
    config = Config()
    original_theme = config.theme_colors.copy()
    overrides = {
        "theme_colors": "not a dict"
    }

    _apply_overrides(config, overrides)
    assert config.theme_colors == original_theme


def test_apply_overrides_deadline_display_mode():
    """Test deadline display mode validation."""
    config = Config()

    # Valid values
    _apply_overrides(config, {"deadline_display_mode": "date"})
    assert config.deadline_display_mode == "date"

    _apply_overrides(config, {"deadline_display_mode": "relative"})
    assert config.deadline_display_mode == "relative"

    # Invalid value should be ignored
    _apply_overrides(config, {"deadline_display_mode": "invalid"})
    assert config.deadline_display_mode == "relative"  # Unchanged


def test_apply_overrides_task_metadata_position():
    """Test task metadata position validation."""
    config = Config()

    # Valid values
    _apply_overrides(config, {"task_metadata_position": "below"})
    assert config.task_metadata_position == "below"

    _apply_overrides(config, {"task_metadata_position": "next_to"})
    assert config.task_metadata_position == "next_to"

    # Invalid value should be ignored
    _apply_overrides(config, {"task_metadata_position": "invalid"})
    assert config.task_metadata_position == "next_to"  # Unchanged


def test_apply_overrides_quick_stats_single_string():
    """Test quick_stats_metrics with single string value."""
    config = Config()
    overrides = {"quick_stats_metrics": "uncompleted_projects"}

    _apply_overrides(config, overrides)
    assert isinstance(config.quick_stats_metrics, list)
    assert "uncompleted_projects" in config.quick_stats_metrics


def test_apply_overrides_quick_stats_list():
    """Test quick_stats_metrics with list value."""
    config = Config()
    overrides = {"quick_stats_metrics": ["active_projects", "bookmarks"]}

    _apply_overrides(config, overrides)
    assert isinstance(config.quick_stats_metrics, list)


def test_apply_overrides_main_menu_tabs_single_string():
    """Test main_menu_tabs with single string value."""
    config = Config()
    overrides = {"main_menu_tabs": "projects"}

    _apply_overrides(config, overrides)
    assert isinstance(config.main_menu_tabs, list)
    assert len(config.main_menu_tabs) > 0


def test_apply_overrides_main_menu_tabs_list():
    """Test main_menu_tabs with list value."""
    config = Config()
    overrides = {"main_menu_tabs": ["projects", "tasks"]}

    _apply_overrides(config, overrides)
    assert isinstance(config.main_menu_tabs, list)


# ==================== Environment Variable Tests ====================


def test_env_override_data_file(temp_dir, monkeypatch):
    """Test PM_DATA_FILE environment variable override."""
    config_path = temp_dir / CONFIG_FILE_NAME
    config_path.write_text('data_file_path = "config.json"')

    monkeypatch.setenv("PM_DATA_FILE", "env_override.json")
    config = load_config(temp_dir)

    # Environment should override config file
    assert config.data_file_path == "env_override.json"


def test_env_override_without_config_file(temp_dir, monkeypatch):
    """Test environment variable without config file."""
    monkeypatch.setenv("PM_DATA_FILE", "env_only.json")
    config = load_config(temp_dir)

    assert config.data_file_path == "env_only.json"


# ==================== Save Config Tests ====================


def test_save_config_creates_file(temp_dir):
    """Test saving config creates TOML file."""
    config = Config()
    config.console_width = 150
    config.data_file_path = "custom.json"

    save_config(config, temp_dir)

    config_path = temp_dir / CONFIG_FILE_NAME
    assert config_path.exists()

    content = config_path.read_text()
    assert "console_width = 150" in content
    assert 'data_file_path = "custom.json"' in content


def test_save_config_includes_all_settings(temp_dir):
    """Test that saved config includes all settings."""
    config = Config()
    save_config(config, temp_dir)

    config_path = temp_dir / CONFIG_FILE_NAME
    content = config_path.read_text()

    # Check key settings are present
    assert "console_width" in content
    assert "data_file_path" in content
    assert "max_project_name_length" in content
    assert "enable_file_logging" in content
    assert "deadline_display_mode" in content
    assert "task_metadata_position" in content
    assert "[theme_colors]" in content


def test_save_config_theme_colors(temp_dir):
    """Test that theme colors are saved correctly."""
    config = Config()
    config.theme_colors["primary"] = "blue"
    config.theme_colors["custom"] = "purple"

    save_config(config, temp_dir)

    config_path = temp_dir / CONFIG_FILE_NAME
    content = config_path.read_text()

    assert 'primary = "blue"' in content
    assert 'custom = "purple"' in content


def test_save_and_reload_config(temp_dir, clean_env):
    """Test saving and then reloading config preserves values."""
    config = Config()
    config.console_width = 150
    config.data_file_path = "test.json"
    config.max_project_name_length = 250
    config.theme_colors["primary"] = "blue"
    config.deadline_display_mode = "date"

    save_config(config, temp_dir)

    # Reload
    loaded = load_config(temp_dir)
    assert loaded.console_width == 150
    assert loaded.data_file_path == "test.json"
    assert loaded.max_project_name_length == 250
    assert loaded.theme_colors["primary"] == "blue"
    assert loaded.deadline_display_mode == "date"


# ==================== Error Handling Tests ====================


def test_load_config_file_permission_error(temp_dir, clean_env):
    """Test loading config handles OSError gracefully (simulated via mock)."""
    config_path = temp_dir / CONFIG_FILE_NAME
    config_path.write_text("console_width = 150")

    # Mock the open call to raise OSError
    with patch("pathlib.Path.open", side_effect=OSError("Permission denied")):
        # Should not crash, should return defaults
        config = load_config(temp_dir)
        assert config.console_width == 120  # Default


def test_save_config_file_permission_error(temp_dir):
    """Test saving config handles permission errors gracefully (simulated via mock)."""
    config = Config()

    # Mock the open call to raise OSError
    with patch("pathlib.Path.open", side_effect=OSError("Permission denied")):
        # Should not crash, just fail silently with logging
        try:
            save_config(config, temp_dir)
        except OSError:
            pytest.fail("save_config should handle OSError gracefully")


# ==================== Global Config Cache Tests ====================


def test_set_config_updates_cache():
    """Test that set_config updates the global cache."""
    new_config = Config()
    new_config.console_width = 999

    set_config(new_config)

    from pm_live.config import get_config
    cached = get_config()
    assert cached.console_width == 999

    # Reset to avoid affecting other tests
    set_config(None)


# ==================== Edge Cases ====================


def test_config_with_invalid_data_types(temp_dir, clean_env):
    """Test that TOML parser correctly types values (strings stay strings, numbers stay numbers)."""
    config_path = temp_dir / CONFIG_FILE_NAME
    config_path.write_text("""
console_width = 150
data_file_path = "valid.json"
""")

    # TOML parser ensures type correctness - this should work
    config = load_config(temp_dir)
    assert config.console_width == 150
    assert config.data_file_path == "valid.json"


def test_config_no_tomllib_available():
    """Test config loading when tomllib is not available."""
    with patch("pm_live.config.tomllib", None):
        config = load_config()
        # Should return defaults
        assert config.console_width == 120

