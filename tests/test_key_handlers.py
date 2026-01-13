"""Tests for keyboard event handlers (pm_live/handlers/key_handlers.py)."""

import pytest
from unittest.mock import Mock, patch

from pm import Project, Task, BookmarkList, Bookmark
from pm_live.handlers.key_handlers import KeyHandlers
from pm_live.interfaces import HandlerContext
from pm_live.ui_state import UIState
from pm_live.states import AppState


# ==================== Fixtures ====================


@pytest.fixture
def mock_manager():
    """Create a mock DataManagerProtocol."""
    manager = Mock()
    manager.projects = []
    manager.bookmarks = []
    manager.custom_field_definitions = []
    manager.default_field_visibility = {}
    manager.force_save = Mock(return_value=True)
    manager.get_project = Mock()
    return manager


@pytest.fixture
def mock_ui_state():
    """Create a mock UIState."""
    ui_state = UIState()
    ui_state.state = AppState.MAIN_MENU
    ui_state.selected_index = 0
    ui_state.active_tab = 0
    ui_state.form_field_index = 0
    ui_state.inline_input_mode = False
    ui_state.text_input_buffer = ""
    ui_state.collapsed_tasks = set()
    ui_state.main_menu_tabs_selection = ["projects", "tasks", "bookmarks"]
    return ui_state


@pytest.fixture
def mock_context(mock_manager, mock_ui_state):
    """Create a mock HandlerContext."""
    context = Mock(spec=HandlerContext)
    context.manager = mock_manager
    context.ui_state = mock_ui_state
    context.get_flat_tasks = Mock(return_value=[])
    context.invalidate_task_cache = Mock()
    context.exit_application = Mock()
    return context


@pytest.fixture
def mock_task_handlers():
    """Create mock TaskHandlers."""
    task_handlers = Mock()
    task_handlers.handle_indent = Mock()
    task_handlers.handle_outdent = Mock()
    task_handlers.handle_collapse_toggle = Mock()
    return task_handlers


@pytest.fixture
def mock_enter_handlers():
    """Create mock EnterHandlers."""
    return Mock()


@pytest.fixture
def key_handlers(mock_context, mock_task_handlers, mock_enter_handlers):
    """Create a KeyHandlers instance."""
    return KeyHandlers(mock_context, mock_task_handlers, mock_enter_handlers)


# ==================== Navigation Tests (Up/Down) ====================


def test_on_up_decrements_selected_index(key_handlers, mock_ui_state):
    """Up arrow decrements selected_index."""
    mock_ui_state.state = AppState.MAIN_MENU
    mock_ui_state.selected_index = 5

    key_handlers.on_up()

    assert mock_ui_state.selected_index == 4


def test_on_up_clamps_at_zero(key_handlers, mock_ui_state):
    """Up arrow at index 0 stays at 0."""
    mock_ui_state.state = AppState.MAIN_MENU
    mock_ui_state.selected_index = 0

    key_handlers.on_up()

    assert mock_ui_state.selected_index == 0


def test_on_down_increments_selected_index(key_handlers, mock_ui_state):
    """Down arrow increments selected_index."""
    mock_ui_state.state = AppState.MAIN_MENU
    mock_ui_state.selected_index = 2

    key_handlers.on_down()

    assert mock_ui_state.selected_index == 3


def test_on_down_clamps_at_max(key_handlers, mock_ui_state):
    """Down arrow at max index stays at max."""
    mock_ui_state.state = AppState.MAIN_MENU
    max_index = key_handlers._get_max_index()
    mock_ui_state.selected_index = max_index

    key_handlers.on_down()

    assert mock_ui_state.selected_index == max_index


def test_on_up_in_form_state(key_handlers, mock_ui_state):
    """Up arrow in form state decrements form_field_index."""
    mock_ui_state.state = AppState.ADD_PROJECT
    mock_ui_state.form_field_index = 3

    key_handlers.on_up()

    assert mock_ui_state.form_field_index == 2


def test_on_down_in_form_state(key_handlers, mock_ui_state):
    """Down arrow in form state increments form_field_index."""
    mock_ui_state.state = AppState.ADD_PROJECT
    mock_ui_state.form_field_index = 2

    key_handlers.on_down()

    assert mock_ui_state.form_field_index == 3


# ==================== Navigation Tests (Left/Right) ====================


def test_on_left_calls_outdent(key_handlers, mock_ui_state, mock_task_handlers):
    """Left arrow in task list calls handle_outdent."""
    mock_ui_state.state = AppState.TASK_LIST
    mock_ui_state.inline_input_mode = False

    key_handlers.on_left()

    mock_task_handlers.handle_outdent.assert_called_once()


def test_on_right_calls_indent(key_handlers, mock_ui_state, mock_task_handlers):
    """Right arrow in task list calls handle_indent."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.inline_input_mode = False

    key_handlers.on_right()

    mock_task_handlers.handle_indent.assert_called_once()


def test_on_left_in_inline_mode_does_not_outdent(key_handlers, mock_ui_state, mock_task_handlers):
    """Left arrow in inline input mode doesn't outdent."""
    mock_ui_state.state = AppState.TASK_LIST
    mock_ui_state.inline_input_mode = True

    key_handlers.on_left()

    mock_task_handlers.handle_outdent.assert_not_called()


# ==================== Tab Navigation Tests ====================


def test_on_tab_cycles_project_browser_tabs(key_handlers, mock_ui_state):
    """Tab key cycles through project browser tabs."""
    mock_ui_state.state = AppState.PROJECT_BROWSER
    mock_ui_state.active_tab = 0

    key_handlers.on_tab()
    assert mock_ui_state.active_tab == 1
    assert mock_ui_state.selected_index == 0

    key_handlers.on_tab()
    assert mock_ui_state.active_tab == 2

    key_handlers.on_tab()
    assert mock_ui_state.active_tab == 0  # Wraps around


def test_on_tab_cycles_task_lists(key_handlers, mock_ui_state):
    """Tab key cycles through task lists."""
    mock_ui_state.state = AppState.TASK_LIST
    mock_ui_state.task_lists = ["Tasks", "Work", "Personal"]
    mock_ui_state.active_tab = 0

    key_handlers.on_tab()
    assert mock_ui_state.active_tab == 1
    assert mock_ui_state.selected_index == 0

    key_handlers.on_tab()
    assert mock_ui_state.active_tab == 2

    key_handlers.on_tab()
    assert mock_ui_state.active_tab == 0  # Wraps around


def test_on_tab_invalidates_cache(key_handlers, mock_ui_state, mock_context):
    """Tab key in task list invalidates cache."""
    mock_ui_state.state = AppState.TASK_LIST
    mock_ui_state.task_lists = ["Tasks", "Work"]

    key_handlers.on_tab()

    mock_context.invalidate_task_cache.assert_called_once()


# ==================== Collapse Toggle Tests ====================


def test_on_collapse_calls_handler(key_handlers, mock_ui_state, mock_task_handlers):
    """'c' key in task list calls collapse toggle."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.inline_input_mode = False

    key_handlers.on_collapse()

    mock_task_handlers.handle_collapse_toggle.assert_called_once()


def test_on_collapse_in_inline_mode_types_char(key_handlers, mock_ui_state, mock_task_handlers):
    """'c' key in inline input mode types the character."""
    mock_ui_state.state = AppState.MAIN_MENU
    mock_ui_state.inline_input_mode = True
    mock_ui_state.quick_add_field_index = 0
    mock_ui_state.text_input_buffer = "test"

    key_handlers.on_collapse()

    assert mock_ui_state.text_input_buffer == "testc"
    mock_task_handlers.handle_collapse_toggle.assert_not_called()


# ==================== Character Input Tests ====================


def test_on_char_appends_to_buffer(key_handlers, mock_ui_state):
    """Character input appends to text buffer."""
    mock_ui_state.inline_input_mode = True
    mock_ui_state.state = AppState.MAIN_MENU
    mock_ui_state.quick_add_field_index = 0
    mock_ui_state.text_input_buffer = "hello"
    mock_ui_state.text_input_cursor = len(mock_ui_state.text_input_buffer)

    key_handlers.on_char("x")

    assert mock_ui_state.text_input_buffer == "hellox"


def test_get_max_index_task_list_legacy_list_format_does_not_crash(mock_task_handlers, mock_enter_handlers):
    # Build a KeyHandlers instance with a real get_flat_tasks implementation.
    manager = Mock()
    manager.projects = []
    manager.bookmarks = []
    manager.custom_field_definitions = []
    manager.default_field_visibility = {}
    manager.force_save = Mock(return_value=True)
    manager.get_project = Mock()
    manager.standalone_tasks = []
    manager.list_metadata = {"Tasks": {"show_done_section": "section"}}

    ui_state = UIState()
    ui_state.state = AppState.TASK_LIST
    ui_state.task_lists = ["Tasks"]
    ui_state.active_tab = 0
    ui_state.collapsed_tasks = set()
    ui_state.list_tasks = {
        # Legacy format: list directly contains Task objects
        "Tasks": [Task(name="T1", completed=None)],
    }

    def _get_flat_tasks(tasks, _is_project: bool):
        from pm_live.tasks import flatten_tasks

        result = []
        flatten_tasks(list(tasks), result, 0, set())
        return result

    ctx = Mock(spec=HandlerContext)
    ctx.manager = manager
    ctx.ui_state = ui_state
    ctx.get_flat_tasks = _get_flat_tasks
    ctx.invalidate_task_cache = Mock()
    ctx.exit_application = Mock()

    handlers = KeyHandlers(ctx, mock_task_handlers, mock_enter_handlers)

    assert handlers._get_max_index() == 4


def test_on_insert_newline_in_inline_notes(key_handlers, mock_ui_state):
    """Ctrl+Shift+J inserts a newline into inline task notes."""
    mock_ui_state.inline_task_edit_mode = True
    mock_ui_state.inline_edit_field_index = 3
    mock_ui_state.inline_edit_notes = "ab"
    mock_ui_state.inline_edit_notes_cursor = 1

    key_handlers.on_insert_newline()

    assert mock_ui_state.inline_edit_notes == "a\nb"
    assert mock_ui_state.inline_edit_notes_cursor == 2


def test_on_insert_newline_in_project_description_buffer(key_handlers, mock_ui_state):
    """Ctrl+Shift+J inserts a newline into project description inline buffer."""
    mock_ui_state.state = AppState.EDIT_PROJECT
    mock_ui_state.inline_input_mode = True
    mock_ui_state.form_field_index = 2  # status, name, description
    mock_ui_state.text_input_buffer = "abc"
    mock_ui_state.text_input_cursor = 1

    key_handlers.on_insert_newline()

    assert mock_ui_state.text_input_buffer == "a\nbc"
    assert mock_ui_state.text_input_cursor == 2


def test_on_char_only_works_in_inline_mode(key_handlers, mock_ui_state):
    """Character input only works when inline_input_mode is active."""
    mock_ui_state.inline_input_mode = False
    mock_ui_state.text_input_buffer = "test"

    key_handlers.on_char("x")

    assert mock_ui_state.text_input_buffer == "test"  # Unchanged


def test_on_backspace_removes_last_char(key_handlers, mock_ui_state):
    """Backspace removes last character."""
    mock_ui_state.inline_input_mode = True
    mock_ui_state.state = AppState.MAIN_MENU
    mock_ui_state.quick_add_field_index = 0
    mock_ui_state.text_input_buffer = "hello"
    mock_ui_state.text_input_cursor = len(mock_ui_state.text_input_buffer)

    key_handlers.on_backspace()

    assert mock_ui_state.text_input_buffer == "hell"


def test_on_backspace_on_empty_buffer(key_handlers, mock_ui_state):
    """Backspace on empty buffer does nothing."""
    mock_ui_state.inline_input_mode = True
    mock_ui_state.state = AppState.MAIN_MENU
    mock_ui_state.quick_add_field_index = 0
    mock_ui_state.text_input_buffer = ""

    key_handlers.on_backspace()

    assert mock_ui_state.text_input_buffer == ""


def test_on_backspace_only_works_in_inline_mode(key_handlers, mock_ui_state):
    """Backspace only works when inline_input_mode is active."""
    mock_ui_state.inline_input_mode = False
    mock_ui_state.text_input_buffer = "test"

    key_handlers.on_backspace()

    assert mock_ui_state.text_input_buffer == "test"  # Unchanged


# ==================== Escape Key Tests ====================


def test_on_escape_exits_inline_input_mode(key_handlers, mock_ui_state):
    """Escape exits inline input mode and clears buffer."""
    mock_ui_state.inline_input_mode = True
    mock_ui_state.text_input_buffer = "some text"

    key_handlers.on_escape()

    assert mock_ui_state.inline_input_mode is False
    assert mock_ui_state.text_input_buffer == ""


def test_on_escape_project_browser_to_main_menu(key_handlers, mock_ui_state):
    """Escape from project browser returns to main menu."""
    mock_ui_state.state = AppState.PROJECT_BROWSER
    mock_ui_state.selected_index = 5

    key_handlers.on_escape()

    assert mock_ui_state.state == AppState.MAIN_MENU
    assert mock_ui_state.selected_index == 0


def test_on_escape_project_details_to_browser(key_handlers, mock_ui_state):
    """Escape from project details returns to browser."""
    mock_ui_state.state = AppState.PROJECT_DETAILS

    key_handlers.on_escape()

    assert mock_ui_state.state == AppState.PROJECT_BROWSER


def test_on_escape_task_list_to_main_menu(key_handlers, mock_ui_state):
    """Escape from task list returns to main menu."""
    mock_ui_state.state = AppState.TASK_LIST
    mock_ui_state.collapsed_tasks.discard("section_completed")  # Simulate Done section expanded
    mock_ui_state.expanded_pinned_lists = {"Work"}
    mock_ui_state.expanded_pinned_sections = {"Work:0"}
    mock_ui_state.expanded_pinned_list_sections = {"Work:1"}

    key_handlers.on_escape()

    assert mock_ui_state.state == AppState.MAIN_MENU
    assert "section_completed" in mock_ui_state.collapsed_tasks
    assert mock_ui_state.expanded_pinned_lists == set()
    assert mock_ui_state.expanded_pinned_sections == set()
    assert mock_ui_state.expanded_pinned_list_sections == set()


def test_on_escape_bookmarks_to_main_menu(key_handlers, mock_ui_state):
    """Escape from bookmarks returns to main menu."""
    mock_ui_state.state = AppState.BOOKMARKS

    key_handlers.on_escape()

    assert mock_ui_state.state == AppState.MAIN_MENU


def test_on_escape_settings_to_main_menu(key_handlers, mock_ui_state):
    """Escape from settings returns to main menu."""
    mock_ui_state.state = AppState.SETTINGS

    key_handlers.on_escape()

    assert mock_ui_state.state == AppState.MAIN_MENU


def test_on_escape_add_project_to_browser(key_handlers, mock_ui_state):
    """Escape from add project form returns to browser."""
    mock_ui_state.state = AppState.ADD_PROJECT
    mock_ui_state.form_data = {"name": "Test"}

    key_handlers.on_escape()

    assert mock_ui_state.state == AppState.PROJECT_BROWSER
    assert mock_ui_state.form_data == {}


def test_on_escape_edit_project_to_details(key_handlers, mock_ui_state):
    """Escape from edit project form returns to details."""
    mock_ui_state.state = AppState.EDIT_PROJECT
    mock_ui_state.form_data = {"name": "Test"}

    key_handlers.on_escape()

    assert mock_ui_state.state == AppState.PROJECT_DETAILS
    assert mock_ui_state.form_data == {}


def test_on_escape_delete_confirmation_cancels(key_handlers, mock_ui_state):
    """Escape from delete confirmation cancels delete."""
    mock_ui_state.state = AppState.DELETE_CONFIRMATION
    mock_ui_state.delete_context = {
        'delete_type': 'project',
        'previous_state': AppState.PROJECT_BROWSER,
        'previous_selected_index': 3
    }

    key_handlers.on_escape()

    assert mock_ui_state.state == AppState.PROJECT_BROWSER
    assert mock_ui_state.selected_index == 3
    assert mock_ui_state.delete_context is None


# ==================== Exit Tests ====================


def test_on_exit_saves_and_exits(key_handlers, mock_manager, mock_context):
    """Exit key saves data and calls exit_application."""
    key_handlers.on_exit()

    mock_manager.force_save.assert_called_once()
    mock_context.exit_application.assert_called_once()


# ==================== Get Max Index Tests ====================


def test_get_max_index_main_menu(key_handlers, mock_ui_state):
    """Get max index for main menu."""
    mock_ui_state.state = AppState.MAIN_MENU
    max_index = key_handlers._get_max_index()

    # Should have menu items + settings + exit (+ quick add if enabled)
    assert max_index >= 2


def test_get_max_index_project_browser(key_handlers, mock_ui_state, mock_manager):
    """Get max index for project browser."""
    mock_manager.projects = [
        Project(id=1, name="P1", status="Planned"),
        Project(id=2, name="P2", status="Planned"),
    ]
    mock_ui_state.state = AppState.PROJECT_BROWSER
    mock_ui_state.active_tab = 0

    max_index = key_handlers._get_max_index()

    # 2 projects + Add + Customize + Back = 5 items (max index 4)
    assert max_index == 4


def test_get_max_index_bookmarks(key_handlers, mock_ui_state, mock_manager):
    """Get max index for bookmarks."""
    mock_manager.bookmarks = [
        Bookmark(title="B1", url="https://example.com"),
        Bookmark(title="B2", url="https://example.com"),
    ]
    mock_ui_state.state = AppState.BOOKMARKS

    max_index = key_handlers._get_max_index()

    # 2 bookmarks + Add Bookmark + Add List + Back = 4 items (max index 4)
    assert max_index == 4


def test_get_max_index_settings(key_handlers, mock_ui_state):
    """Get max index for settings."""
    mock_ui_state.state = AppState.SETTINGS

    max_index = key_handlers._get_max_index()

    # Settings menu currently exposes 11 visible entries (0-10) plus Back (11).
    assert max_index == 11


# ==================== Get Max Form Index Tests ====================


def test_get_max_form_index_add_project(key_handlers, mock_ui_state):
    """Get max form index for add project."""
    mock_ui_state.state = AppState.ADD_PROJECT

    max_index = key_handlers._get_max_form_index()

    # ADD_PROJECT: editable fields + Create + Cancel
    from pm_live.custom_fields import get_all_fields
    from pm_live.utils import get_edit_project_field_keys

    all_fields = get_all_fields(key_handlers.manager.default_field_visibility, key_handlers.manager.custom_field_definitions)
    field_keys = get_edit_project_field_keys(all_fields)
    assert max_index == len(field_keys) + 1


def test_get_max_form_index_edit_project(key_handlers, mock_ui_state):
    """Get max form index for edit project."""
    mock_ui_state.state = AppState.EDIT_PROJECT

    max_index = key_handlers._get_max_form_index()

    # EDIT_PROJECT: editable fields + Save + Delete + Cancel
    from pm_live.custom_fields import get_all_fields
    from pm_live.utils import get_edit_project_field_keys

    all_fields = get_all_fields(key_handlers.manager.default_field_visibility, key_handlers.manager.custom_field_definitions)
    field_keys = get_edit_project_field_keys(all_fields)
    assert max_index == len(field_keys) + 2


def test_get_max_form_index_add_bookmark(key_handlers, mock_ui_state):
    """Get max form index for add bookmark."""
    mock_ui_state.state = AppState.ADD_BOOKMARK

    max_index = key_handlers._get_max_form_index()

    # 2 fields + Submit + Cancel = 3 (max index 3)
    assert max_index == 3


def test_get_max_form_index_delete_confirmation(key_handlers, mock_ui_state):
    """Get max form index for delete confirmation."""
    mock_ui_state.state = AppState.DELETE_CONFIRMATION

    max_index = key_handlers._get_max_form_index()

    # 2 options: Yes (0) and No (1)
    assert max_index == 1


# ==================== Integration Tests ====================


def test_navigation_sequence(key_handlers, mock_ui_state):
    """Test a sequence of navigation actions."""
    mock_ui_state.state = AppState.MAIN_MENU
    mock_ui_state.selected_index = 0

    # Move down 3 times
    key_handlers.on_down()
    key_handlers.on_down()
    key_handlers.on_down()
    assert mock_ui_state.selected_index == 3

    # Move up twice
    key_handlers.on_up()
    key_handlers.on_up()
    assert mock_ui_state.selected_index == 1


def test_inline_mode_full_workflow(key_handlers, mock_ui_state):
    """Test inline input mode workflow."""
    mock_ui_state.inline_input_mode = True
    mock_ui_state.state = AppState.MAIN_MENU
    mock_ui_state.quick_add_field_index = 0
    mock_ui_state.text_input_buffer = ""

    # Type some characters
    key_handlers.on_char("h")
    key_handlers.on_char("e")
    key_handlers.on_char("l")
    key_handlers.on_char("l")
    key_handlers.on_char("o")
    assert mock_ui_state.text_input_buffer == "hello"

    # Backspace once
    key_handlers.on_backspace()
    assert mock_ui_state.text_input_buffer == "hell"

    # Escape to exit
    key_handlers.on_escape()
    assert mock_ui_state.inline_input_mode is False
    assert mock_ui_state.text_input_buffer == ""


def test_form_navigation(key_handlers, mock_ui_state):
    """Test form field navigation."""
    mock_ui_state.state = AppState.ADD_PROJECT
    mock_ui_state.form_field_index = 0

    # Navigate down through form fields
    key_handlers.on_down()
    assert mock_ui_state.form_field_index == 1

    key_handlers.on_down()
    assert mock_ui_state.form_field_index == 2

    # Navigate back up
    key_handlers.on_up()
    assert mock_ui_state.form_field_index == 1


# ==================== Edge Cases ====================


def test_navigation_with_no_items(key_handlers, mock_ui_state, mock_manager):
    """Navigation with empty lists should not crash."""
    mock_manager.projects = []
    mock_manager.bookmarks = []
    mock_ui_state.state = AppState.PROJECT_BROWSER

    # Should not crash
    key_handlers.on_up()
    key_handlers.on_down()
    max_index = key_handlers._get_max_index()
    assert max_index >= 0


def test_escape_handles_missing_delete_context(key_handlers, mock_ui_state):
    """Escape handles missing delete_context gracefully."""
    mock_ui_state.state = AppState.DELETE_CONFIRMATION
    mock_ui_state.delete_context = None

    # Should not crash
    key_handlers.on_escape()


# ==================== Calendar Navigation Tests ====================


def test_calendar_move_day_crosses_month(key_handlers, mock_ui_state):
    """Calendar move handles month transitions."""
    mock_ui_state.state = AppState.CALENDAR
    mock_ui_state.calendar_year = 2025
    mock_ui_state.calendar_month = 1
    mock_ui_state.calendar_selected_day = 1

    key_handlers._calendar_move_day(-1)

    assert mock_ui_state.calendar_year == 2024
    assert mock_ui_state.calendar_month == 12
    assert mock_ui_state.calendar_selected_day == 31


def test_calendar_change_month_clamps_day(key_handlers, mock_ui_state):
    """Calendar month change clamps invalid days."""
    mock_ui_state.state = AppState.CALENDAR
    mock_ui_state.calendar_year = 2025
    mock_ui_state.calendar_month = 1
    mock_ui_state.calendar_selected_day = 31

    key_handlers._calendar_change_month(1)

    assert mock_ui_state.calendar_year == 2025
    assert mock_ui_state.calendar_month == 2
    assert mock_ui_state.calendar_selected_day == 28
