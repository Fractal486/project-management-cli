"""Enumeration and documentation of the live CLI state machine.

The application is modelled as a single active state (screen) at any time.
Handlers transition between these states. Centralising the enum helps keep
navigation, rendering, and tests aligned.
"""

from enum import Enum


class AppState(Enum):
    """All possible UI screens."""

    MAIN_MENU = "main_menu"
    PROJECT_BROWSER = "project_browser"
    PROJECT_DETAILS = "project_details"
    TASK_LIST = "task_list"
    STATISTICS = "statistics"
    CALENDAR = "calendar"
    SETTINGS = "settings"
    QUICK_STATS_SETTINGS = "quick_stats_settings"
    MAIN_MENU_TABS_SETTINGS = "main_menu_tabs_settings"
    DEADLINE_SETTINGS = "deadline_settings"
    TASK_METADATA_SETTINGS = "task_metadata_settings"
    PROJECT_BROWSER_TAB_SETTINGS = "project_browser_tab_settings"
    STATS_NONE_SETTINGS = "stats_none_settings"
    BOOKMARK_ACTION_SETTINGS = "bookmark_action_settings"
    MESSAGE_DISPLAY_SETTINGS = "message_display_settings"
    NOTES_DISPLAY_SETTINGS = "notes_display_settings"
    CUSTOMIZE_FIELDS = "customize_fields"
    ADD_CUSTOM_FIELD = "add_custom_field"
    EDIT_CUSTOM_FIELD = "edit_custom_field"
    BOOKMARKS = "bookmarks"
    BOOKMARK_LIST = "bookmark_list"
    SEARCH = "search"
    ADD_PROJECT = "add_project"
    EDIT_PROJECT = "edit_project"
    CHANGE_STATUS = "change_status"
    ADD_BOOKMARK = "add_bookmark"
    EDIT_BOOKMARK = "edit_bookmark"
    EDIT_TAB = "edit_tab"
    DELETE_CONFIRMATION = "delete_confirmation"
