"""Configuration management for the Project Manager live CLI."""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback guard
    tomllib = None  # type: ignore


CONFIG_FILE_NAME = ".pm_config.toml"

from .quick_stats import DEFAULT_QUICK_STATS, normalize_quick_stats_selection
from .main_menu_tabs import DEFAULT_MAIN_MENU_TABS, normalize_main_menu_tabs


def _default_theme() -> Dict[str, str]:
    """Return default theme color values."""
    return {
        "primary": "white",
        "accent": "magenta",
        "success": "green",
        "warning": "yellow",
        "error": "red",
    }


@dataclass(slots=True)
class Config:
    """Runtime configuration values for the live CLI."""

    console_width: int = 120
    data_file_path: str = "projects.json"
    max_project_name_length: int = 200
    theme_colors: Dict[str, str] = field(default_factory=_default_theme)
    enable_file_logging: bool = True
    log_level_console: str = "INFO"
    log_level_file: str = "DEBUG"
    log_file_path: str = "pm_app.log"
    log_max_bytes: int = 5 * 1024 * 1024
    log_backup_count: int = 5
    quick_stats_metrics: list[str] = field(default_factory=lambda: list(DEFAULT_QUICK_STATS))
    main_menu_tabs: list[str] = field(default_factory=lambda: list(DEFAULT_MAIN_MENU_TABS))

    # Deadline display mode: "date" shows exact dates, "relative" shows days remaining
    deadline_display_mode: str = "relative"

    # Display "none" values for custom fields in project stats panels
    show_none_in_stats: bool = True

    # Bookmark action mode: "copy" copies URL to clipboard, "open" opens in browser
    bookmark_action_mode: str = "copy"

    # Status message display: "all" shows all status messages, "errors_only" shows errors only
    status_message_mode: str = "all"

    # Notes display mode: "dynamic" shows notes only when task selected, "always" shows notes always
    notes_display_mode: str = "dynamic"

    # Project browser default tab: "all" shows all projects first, "active" shows active projects first
    project_browser_default_tab: str = "all"

    def copy(self) -> "Config":
        """Return a deep copy suitable for mutation."""
        return copy.deepcopy(self)


_CONFIG: Config | None = None


def load_config(base_path: Optional[Path] = None) -> Config:
    """Load configuration from disk if available, falling back to defaults."""
    base = base_path or Path.cwd()
    file_path = base / CONFIG_FILE_NAME
    config = Config()

    if tomllib is None:
        return config  # TOML not available, keep defaults

    try:
        if file_path.exists():
            with file_path.open("rb") as fh:
                data = tomllib.load(fh)
            _apply_overrides(config, data or {})
    except (OSError, tomllib.TOMLDecodeError):
        # Ignore config errors but keep defaults to avoid crashing the CLI
        pass

    # Environment overrides
    data_override = os.getenv("PM_DATA_FILE")
    if data_override:
        config.data_file_path = data_override

    return config


def _apply_overrides(config: Config, overrides: Dict[str, Any]) -> None:
    """Apply raw dictionary overrides to the config object."""
    if "console_width" in overrides:
        config.console_width = int(overrides["console_width"])
    if "data_file_path" in overrides:
        config.data_file_path = str(overrides["data_file_path"])
    if "max_project_name_length" in overrides:
        config.max_project_name_length = int(overrides["max_project_name_length"])
    if "theme_colors" in overrides and isinstance(overrides["theme_colors"], dict):
        theme = {str(k): str(v) for k, v in overrides["theme_colors"].items()}
        config.theme_colors.update(theme)
    if "enable_file_logging" in overrides:
        config.enable_file_logging = bool(overrides["enable_file_logging"])
    if "log_level_console" in overrides:
        config.log_level_console = str(overrides["log_level_console"]).upper()
    if "log_level_file" in overrides:
        config.log_level_file = str(overrides["log_level_file"]).upper()
    if "log_file_path" in overrides:
        config.log_file_path = str(overrides["log_file_path"])
    if "log_max_bytes" in overrides:
        config.log_max_bytes = int(overrides["log_max_bytes"])
    if "log_backup_count" in overrides:
        config.log_backup_count = int(overrides["log_backup_count"])
    if "quick_stats_metrics" in overrides:
        raw_metrics = overrides["quick_stats_metrics"]
        if isinstance(raw_metrics, str):
            candidates = [raw_metrics]
        elif isinstance(raw_metrics, (list, tuple, set)):
            candidates = list(raw_metrics)
        else:
            candidates = []
        normalized = normalize_quick_stats_selection(str(item) for item in candidates)
        config.quick_stats_metrics = normalized
    if "main_menu_tabs" in overrides:
        raw_tabs = overrides["main_menu_tabs"]
        if isinstance(raw_tabs, str):
            candidates = [raw_tabs]
        elif isinstance(raw_tabs, (list, tuple, set)):
            candidates = list(raw_tabs)
        else:
            candidates = []
        normalized_tabs = normalize_main_menu_tabs(str(item) for item in candidates)
        config.main_menu_tabs = normalized_tabs
    # Deadline display mode
    if "deadline_display_mode" in overrides:
        value = str(overrides["deadline_display_mode"]).strip().lower()
        if value in {"date", "relative"}:
            config.deadline_display_mode = value
    if "show_none_in_stats" in overrides:
        config.show_none_in_stats = bool(overrides["show_none_in_stats"])
    if "bookmark_action_mode" in overrides:
        value = str(overrides["bookmark_action_mode"]).strip().lower()
        if value in {"copy", "open"}:
            config.bookmark_action_mode = value
    if "status_message_mode" in overrides:
        value = str(overrides["status_message_mode"]).strip().lower()
        if value in {"all", "errors_only"}:
            config.status_message_mode = value
    if "notes_display_mode" in overrides:
        value = str(overrides["notes_display_mode"]).strip().lower()
        if value in {"dynamic", "always"}:
            config.notes_display_mode = value
    if "project_browser_default_tab" in overrides:
        value = str(overrides["project_browser_default_tab"]).strip().lower()
        if value in {"all", "active"}:
            config.project_browser_default_tab = value

def get_config() -> Config:
    """Get cached configuration, loading it on first access."""
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load_config()
    return _CONFIG


def set_config(new_config: Config) -> None:
    """Replace the cached configuration (used for runtime updates/testing)."""
    global _CONFIG
    _CONFIG = new_config


def save_config(config: Config, base_path: Optional[Path] = None) -> None:
    """Save configuration to TOML file."""
    base = base_path or Path.cwd()
    file_path = base / CONFIG_FILE_NAME

    # Build TOML content from config
    toml_content = f"""# Project Manager CLI Configuration
#
console_width = {config.console_width}
data_file_path = "{config.data_file_path}"
max_project_name_length = {config.max_project_name_length}
enable_file_logging = {str(config.enable_file_logging).lower()}
log_level_console = "{config.log_level_console}"
log_level_file = "{config.log_level_file}"
log_file_path = "{config.log_file_path}"
log_max_bytes = {config.log_max_bytes}
log_backup_count = {config.log_backup_count}

# Deadline Display Mode
# Options: "date" (exact dates) | "relative" (days remaining)
deadline_display_mode = "{config.deadline_display_mode}"

# Project Stats Display
# Toggle whether to display fields set to "none" in project stats panels
show_none_in_stats = {str(config.show_none_in_stats).lower()}

# Bookmark Action Mode
# Options: "copy" (copy URL to clipboard) | "open" (open in default browser)
bookmark_action_mode = "{config.bookmark_action_mode}"

# Status Message Display
# Options: "all" (show all status messages) | "errors_only" (only errors)
status_message_mode = "{config.status_message_mode}"

# Notes Display Mode
# Options: "dynamic" (show only when task selected) | "always" (show always)
notes_display_mode = "{config.notes_display_mode}"

# Project Browser Default Tab
# Options: "all" (All tab first) | "active" (Active tab first)
project_browser_default_tab = "{config.project_browser_default_tab}"

[theme_colors]
"""
    # Add theme colors
    for key, value in config.theme_colors.items():
        toml_content += f'{key} = "{value}"\n'

    # Write to file
    try:
        with file_path.open("w", encoding="utf-8") as fh:
            fh.write(toml_content)
    except OSError as e:
        # Log error but don't crash
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to save config to %s: %s", file_path, e)
