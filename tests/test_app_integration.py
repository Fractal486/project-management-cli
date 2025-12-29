"""Tests for pm_live.app - Application integration and initialization."""

import logging
from io import StringIO
from unittest.mock import Mock, MagicMock, patch, PropertyMock

import pytest

from pm import ProjectManager, Project, Task
from pm_live.app import LiveCLI
from pm_live.states import AppState
from pm_live.ui_state import UIState


logger = logging.getLogger(__name__)


@pytest.fixture
def mock_manager():
    """Create a mock ProjectManager."""
    manager = Mock(spec=ProjectManager)
    manager.projects = []
    manager.standalone_tasks = []
    manager.bookmarks = []
    manager.list_tasks = {"Tasks": []}
    return manager


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = Mock()
    config.console_width = 120
    config.quick_stats_metrics = ["uncompleted_projects", "uncompleted_tasks"]
    config.main_menu_tabs = ["projects", "tasks"]
    config.copy = Mock(return_value=config)
    return config


@pytest.fixture
def live_cli(mock_manager, mock_config):
    """Create a LiveCLI instance with mocked dependencies."""
    with patch("pm_live.app.get_config", return_value=mock_config):
        with patch("pm_live.app.create_key_bindings", return_value=Mock()):
            cli = LiveCLI(mock_manager)
    return cli


# ============================================================================
# Initialization Tests
# ============================================================================


def test_live_cli_initialization(mock_manager, mock_config):
    """LiveCLI initializes with correct components."""
    with patch("pm_live.app.get_config", return_value=mock_config):
        with patch("pm_live.app.create_key_bindings", return_value=Mock()):
            cli = LiveCLI(mock_manager)

    # Check basic attributes
    assert cli.manager is mock_manager
    assert isinstance(cli.ui_state, UIState)
    assert cli.ui_state.state == AppState.MAIN_MENU

    # Check handlers created
    assert cli.task_handlers is not None
    assert cli.bookmark_handlers is not None
    assert cli.enter_handlers is not None
    assert cli.key_handlers is not None

    # Check console initialized
    assert cli._console is not None
    assert cli._console_buffer is not None

    # Check renderers created
    assert len(cli.renderers) > 0
    assert AppState.MAIN_MENU in cli.renderers
    assert AppState.TASK_LIST in cli.renderers


def test_live_cli_initialization_with_list_tasks(mock_manager, mock_config):
    """LiveCLI initializes list_tasks from manager."""
    mock_manager.list_tasks = {"Tasks": [], "Project A": [], "Project B": []}

    with patch("pm_live.app.get_config", return_value=mock_config):
        with patch("pm_live.app.create_key_bindings", return_value=Mock()):
            cli = LiveCLI(mock_manager)

    assert cli.ui_state.list_tasks == {"Tasks": [], "Project A": [], "Project B": []}
    assert set(cli.ui_state.task_lists) == {"Tasks", "Project A", "Project B"}


def test_live_cli_initialization_without_list_tasks(mock_manager, mock_config):
    """LiveCLI handles missing list_tasks attribute gracefully."""
    # Remove list_tasks attribute
    del mock_manager.list_tasks

    with patch("pm_live.app.get_config", return_value=mock_config):
        with patch("pm_live.app.create_key_bindings", return_value=Mock()):
            cli = LiveCLI(mock_manager)

    # Should fall back to standalone_tasks
    assert "Tasks" in cli.ui_state.list_tasks
    assert cli.ui_state.list_tasks["Tasks"] == mock_manager.standalone_tasks


def test_live_cli_initialization_with_config_quick_stats(mock_manager, mock_config):
    """LiveCLI initializes quick stats from config."""
    mock_config.quick_stats_metrics = ["uncompleted_projects", "bookmarks"]

    with patch("pm_live.app.get_config", return_value=mock_config):
        with patch("pm_live.app.create_key_bindings", return_value=Mock()):
            cli = LiveCLI(mock_manager)

    assert "uncompleted_projects" in cli.ui_state.quick_stats_selection
    assert "bookmarks" in cli.ui_state.quick_stats_selection


# ============================================================================
# Console and Renderer Tests
# ============================================================================


def test_initialize_console_creates_renderers(live_cli):
    """_initialize_console creates all required renderers."""
    # Check all state-based renderers exist
    required_states = [
        AppState.MAIN_MENU,
        AppState.PROJECT_BROWSER,
        AppState.PROJECT_DETAILS,
        AppState.TASK_LIST,
        AppState.STATISTICS,
        AppState.CALENDAR,
        AppState.SETTINGS,
        AppState.QUICK_STATS_SETTINGS,
        AppState.BOOKMARKS,
        AppState.ADD_PROJECT,
        AppState.EDIT_PROJECT,
    ]

    for state in required_states:
        assert state in live_cli.renderers

    # Check special renderers
    assert live_cli.help_renderer is not None


def test_initialize_console_with_custom_width(mock_manager, mock_config):
    """_initialize_console uses custom console width."""
    mock_config.console_width = 80

    with patch("pm_live.app.get_config", return_value=mock_config):
        with patch("pm_live.app.create_key_bindings", return_value=Mock()):
            cli = LiveCLI(mock_manager)

    assert cli._console.width == 80


# ============================================================================
# Context Building Tests
# ============================================================================


def test_build_render_context(live_cli):
    """_build_render_context creates correct context dictionary."""
    live_cli.ui_state.selected_index = 5
    live_cli.ui_state.active_tab = 2
    live_cli.ui_state.current_project_id = 10
    live_cli.ui_state.text_input_buffer = "test input"
    live_cli.ui_state.status_message = "Test status"

    context = live_cli._build_render_context()

    assert context['manager'] is live_cli.manager
    assert context['selected_index'] == 5
    assert context['active_tab'] == 2
    assert context['current_project_id'] == 10
    assert context['text_input_buffer'] == "test input"
    assert context['status_message'] == "Test status"


def test_build_render_context_with_form_data(live_cli):
    """_build_render_context includes form data."""
    live_cli.ui_state.form_data = {"name": "Project A", "status": "In Progress"}
    live_cli.ui_state.form_field_index = 1

    context = live_cli._build_render_context()

    assert context['form_data'] == {"name": "Project A", "status": "In Progress"}
    assert context['form_field_index'] == 1


# ============================================================================
# Helper Method Tests
# ============================================================================


def test_show_status(live_cli):
    """_show_status updates UI state."""
    live_cli._show_status("Test message", is_error=False)

    assert live_cli.ui_state.status_message == "Test message"
    assert live_cli.ui_state.status_is_error is False


def test_show_status_error(live_cli):
    """_show_status marks errors correctly."""
    live_cli._show_status("Error message", is_error=True)

    assert live_cli.ui_state.status_message == "Error message"
    assert live_cli.ui_state.status_is_error is True


def test_invalidate_task_cache(live_cli):
    """_invalidate_task_cache clears the cache."""
    # Add some entries to cache
    live_cli.ui_state._flat_tasks_cache = {
        "key1": ["task1", "task2"],
        "key2": ["task3"]
    }

    live_cli._invalidate_task_cache()

    assert len(live_cli.ui_state._flat_tasks_cache) == 0


def test_get_flat_tasks_caching(live_cli):
    """_get_flat_tasks caches results."""
    tasks = [Mock(name="Task 1", subtasks=[])]

    with patch("pm_live.app.flatten_tasks") as mock_flatten:
        mock_flatten.return_value = None  # flatten_tasks modifies in place

        # First call
        result1 = live_cli._get_flat_tasks(tasks, is_project=False)

        # Second call with same parameters
        result2 = live_cli._get_flat_tasks(tasks, is_project=False)

        # flatten_tasks should only be called once due to caching
        assert mock_flatten.call_count == 1
        assert result1 is result2


def test_get_flat_tasks_cache_key_varies_by_collapse(live_cli):
    """_get_flat_tasks cache key includes collapsed state."""
    tasks = [Mock(name="Task 1", subtasks=[])]

    with patch("pm_live.app.flatten_tasks") as mock_flatten:
        mock_flatten.return_value = None

        # First call with default collapsed state
        live_cli._get_flat_tasks(tasks, is_project=False)

        # Change collapsed state
        live_cli.ui_state.collapsed_tasks.add("new_section")

        # Second call should miss cache
        live_cli._get_flat_tasks(tasks, is_project=False)

        # flatten_tasks should be called twice
        assert mock_flatten.call_count == 2


def test_restore_collapsed_tasks_always_includes_done_section(mock_manager, mock_config):
    """Restoring collapsed tasks should always keep the Done section collapsed by default."""
    mock_manager.metadata = {"collapsed_tasks": []}
    with patch("pm_live.app.get_config", return_value=mock_config):
        with patch("pm_live.app.create_key_bindings", return_value=Mock()):
            cli = LiveCLI(mock_manager)

    assert "section_completed" in cli.ui_state.collapsed_tasks


def test_persist_collapsed_tasks_excludes_done_section(live_cli):
    """Persisted collapsed tasks should not include the Done section key."""
    live_cli.manager.metadata = {}
    live_cli.manager.save = Mock()
    live_cli.manager.mark_metadata_modified = Mock()

    live_cli.ui_state.collapsed_tasks = {"section_completed", "Tasks:0", "1"}
    live_cli._persist_collapsed_tasks()

    assert live_cli.manager.metadata["collapsed_tasks"] == ["1", "Tasks:0"]


# ============================================================================
# Text Processing Tests
# ============================================================================


def test_strip_formatting_removes_ansi(live_cli):
    """_strip_formatting removes ANSI escape codes."""
    text_with_ansi = "\x1b[36mColored text\x1b[0m"
    result = live_cli._strip_formatting(text_with_ansi)
    assert result == "Colored text"


def test_strip_formatting_removes_rich_tags(live_cli):
    """_strip_formatting removes Rich markup tags."""
    text_with_tags = "[bold]Bold text[/bold]"
    result = live_cli._strip_formatting(text_with_tags)
    assert result == "Bold text"


def test_strip_formatting_empty_string(live_cli):
    """_strip_formatting handles empty strings."""
    assert live_cli._strip_formatting("") == ""
    assert live_cli._strip_formatting(None) == ""


def test_has_visible_content(live_cli):
    """_has_visible_content detects visible text."""
    assert live_cli._has_visible_content("Some text") is True
    assert live_cli._has_visible_content("\x1b[36mColored\x1b[0m") is True
    assert live_cli._has_visible_content("   ") is False
    assert live_cli._has_visible_content("\x1b[0m") is False


def test_is_divider_line(live_cli):
    """_is_divider_line detects divider lines."""
    assert live_cli._is_divider_line("─" * 40) is True
    assert live_cli._is_divider_line("━" * 40) is True
    assert live_cli._is_divider_line("=" * 40) is True
    assert live_cli._is_divider_line("-" * 40) is True
    assert live_cli._is_divider_line("Some text") is False
    assert live_cli._is_divider_line("") is False


def test_find_divider_index(live_cli):
    """_find_divider_index locates the footer divider."""
    lines = [
        "Main content line 1",
        "Main content line 2",
        "─" * 40,
        "Actions: [n] New  [e] Edit",
        ""
    ]

    index = live_cli._find_divider_index(lines)
    assert index == 2


def test_remove_footer_from_content(live_cli):
    """_remove_footer_from_content strips footer section."""
    content = "Main content\nMore content\n" + "─" * 40 + "\nActions: [n] New\n"
    result = live_cli._remove_footer_from_content(content)

    assert "Main content" in result
    assert "More content" in result
    assert "Actions:" not in result


def test_extract_footer_from_content(live_cli):
    """_extract_footer_from_content extracts footer section."""
    content = "Main content\n" + "─" * 40 + "\nActions: [n] New\n"
    result = live_cli._extract_footer_from_content(content)

    assert "Actions:" in result
    assert "Main content" not in result


# ============================================================================
# Configuration Update Tests
# ============================================================================


@patch("pm_live.app.set_config")
@patch("pm_live.app.get_config")
def test_update_console_width(mock_get_config, mock_set_config, live_cli, mock_config):
    """update_console_width persists new width."""
    mock_get_config.return_value = mock_config

    live_cli.update_console_width(100)

    # Should update config
    assert mock_config.console_width == 100
    mock_set_config.assert_called_once_with(mock_config)

    # Should reinitialize console
    assert live_cli._console.width == 100


@patch("pm_live.app.set_config")
@patch("pm_live.app.get_config")
def test_update_quick_stats_selection(mock_get_config, mock_set_config, live_cli, mock_config):
    """update_quick_stats_selection persists selection."""
    mock_get_config.return_value = mock_config

    live_cli.update_quick_stats_selection(["uncompleted_projects", "bookmarks"])

    # Should update UI state
    assert "uncompleted_projects" in live_cli.ui_state.quick_stats_selection
    assert "bookmarks" in live_cli.ui_state.quick_stats_selection

    # Should persist to config
    mock_set_config.assert_called_once()


@patch("pm_live.app.set_config")
@patch("pm_live.app.get_config")
def test_update_main_menu_tabs_selection(mock_get_config, mock_set_config, live_cli, mock_config):
    """update_main_menu_tabs_selection persists selection."""
    mock_get_config.return_value = mock_config

    live_cli.update_main_menu_tabs_selection(["projects", "bookmarks"])

    # Should update UI state
    assert "projects" in live_cli.ui_state.main_menu_tabs_selection
    assert "bookmarks" in live_cli.ui_state.main_menu_tabs_selection

    # Should persist to config
    mock_set_config.assert_called_once()


@patch("pm_live.app.set_config")
@patch("pm_live.app.get_config")
def test_update_main_menu_tabs_exits_quick_add_when_tasks_hidden(mock_get_config, mock_set_config, live_cli, mock_config):
    """update_main_menu_tabs_selection exits quick add when tasks tab is hidden."""
    mock_get_config.return_value = mock_config

    # Set up quick add mode
    live_cli.ui_state.inline_input_mode = True
    live_cli.ui_state.text_input_buffer = "New task"
    live_cli.ui_state.quick_add_priority = "High"

    # Hide tasks tab
    live_cli.update_main_menu_tabs_selection(["projects", "bookmarks"])

    # Should exit quick add mode
    assert live_cli.ui_state.inline_input_mode is False
    assert live_cli.ui_state.text_input_buffer == ""
    assert live_cli.ui_state.quick_add_priority is None


# ============================================================================
# Exit Handling Tests
# ============================================================================


def test_exit_application(live_cli):
    """_exit_application exits immediately."""
    live_cli.app = Mock()

    live_cli._exit_application()

    live_cli.app.exit.assert_called_once()


# ============================================================================
# Key Binding Delegation Tests
# ============================================================================


def test_on_up_delegates_to_handler(live_cli):
    """on_up delegates to key_handlers."""
    live_cli.key_handlers.on_up = Mock()

    live_cli.on_up()

    live_cli.key_handlers.on_up.assert_called_once()


def test_on_down_delegates_to_handler(live_cli):
    """on_down delegates to key_handlers."""
    live_cli.key_handlers.on_down = Mock()

    live_cli.on_down()

    live_cli.key_handlers.on_down.assert_called_once()


def test_on_enter_delegates_to_handler(live_cli):
    """on_enter delegates to enter_handlers."""
    live_cli.enter_handlers.handle_enter = Mock()

    live_cli.on_enter()

    live_cli.enter_handlers.handle_enter.assert_called_once()


def test_on_escape_delegates_to_handler(live_cli):
    """on_escape delegates to key_handlers."""
    live_cli.key_handlers.on_escape = Mock()

    live_cli.on_escape()

    live_cli.key_handlers.on_escape.assert_called_once()


def test_on_help_toggles_help_overlay(live_cli):
    """on_help toggles help overlay."""
    assert live_cli.ui_state.show_help is False

    live_cli.on_help()
    assert live_cli.ui_state.show_help is True

    live_cli.on_help()
    assert live_cli.ui_state.show_help is False


def test_on_help_in_inline_mode_types_h(live_cli):
    """on_help types 'h' when in inline input mode."""
    live_cli.ui_state.inline_input_mode = True
    live_cli.ui_state.text_input_buffer = ""

    live_cli.on_help()

    assert live_cli.ui_state.text_input_buffer == "h"
    assert live_cli.ui_state.show_help is False


def test_on_delete_delegates_to_task_handler(live_cli):
    """on_delete delegates to task_handlers in task states."""
    live_cli.ui_state.state = AppState.TASK_LIST
    live_cli.task_handlers.handle_delete = Mock()

    live_cli.on_delete()

    live_cli.task_handlers.handle_delete.assert_called_once()


def test_on_delete_delegates_to_bookmark_handler(live_cli):
    """on_delete delegates to bookmark_handlers in bookmark states."""
    live_cli.ui_state.state = AppState.BOOKMARKS
    live_cli.bookmark_handlers.handle_bookmarks_delete = Mock()

    live_cli.on_delete()

    live_cli.bookmark_handlers.handle_bookmarks_delete.assert_called_once()


def test_on_left_delegates_to_outdent(live_cli):
    """on_left delegates to outdent in task states."""
    live_cli.ui_state.state = AppState.TASK_LIST
    live_cli.task_handlers.handle_outdent = Mock()

    live_cli.on_left()

    live_cli.task_handlers.handle_outdent.assert_called_once()


def test_on_right_delegates_to_indent(live_cli):
    """on_right delegates to indent in task states."""
    live_cli.ui_state.state = AppState.TASK_LIST
    live_cli.task_handlers.handle_indent = Mock()

    live_cli.on_right()

    live_cli.task_handlers.handle_indent.assert_called_once()


# ============================================================================
# Integration Workflow Tests
# ============================================================================


def test_complete_workflow_initialization_to_render(mock_manager, mock_config):
    """Test complete workflow from initialization to render."""
    with patch("pm_live.app.get_config", return_value=mock_config):
        with patch("pm_live.app.create_key_bindings", return_value=Mock()):
            cli = LiveCLI(mock_manager)

    # Check initialized state
    assert cli.ui_state.state == AppState.MAIN_MENU

    # Build render context
    context = cli._build_render_context()
    assert context['manager'] is mock_manager
    assert context['selected_index'] == 0

    # Verify all components ready
    assert cli.renderers[AppState.MAIN_MENU] is not None
    assert cli._console is not None


def test_complete_workflow_state_transition(live_cli):
    """Test state transition workflow."""
    # Start at main menu
    assert live_cli.ui_state.state == AppState.MAIN_MENU

    # Transition to project browser
    live_cli.ui_state.state = AppState.PROJECT_BROWSER
    live_cli.ui_state.selected_index = 2

    context = live_cli._build_render_context()
    assert context['selected_index'] == 2

    # Transition to task list
    live_cli.ui_state.state = AppState.TASK_LIST

    assert AppState.TASK_LIST in live_cli.renderers


def test_complete_workflow_error_handling(live_cli):
    """Test error handling workflow."""
    # Show error status
    live_cli._show_status("Something went wrong", is_error=True)

    assert live_cli.ui_state.status_message == "Something went wrong"
    assert live_cli.ui_state.status_is_error is True

    # Context should include error
    context = live_cli._build_render_context()
    assert context['status_message'] == "Something went wrong"
    assert context['status_is_error'] is True


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


def test_build_render_context_with_missing_attributes(live_cli):
    """_build_render_context handles missing UI state attributes gracefully."""
    # Remove some optional attributes
    if hasattr(live_cli.ui_state, 'editing_list_name'):
        delattr(live_cli.ui_state, 'editing_list_name')

    # Should not raise
    context = live_cli._build_render_context()

    # Should have default values
    assert 'manager' in context
    assert 'selected_index' in context


def test_get_flat_tasks_with_different_task_lists(live_cli):
    """_get_flat_tasks handles different task lists separately."""
    tasks1 = [Mock(name="Task 1", subtasks=[])]
    tasks2 = [Mock(name="Task 2", subtasks=[])]

    with patch("pm_live.app.flatten_tasks") as mock_flatten:
        mock_flatten.return_value = None

        # Get flat tasks for different lists
        live_cli._get_flat_tasks(tasks1, is_project=False)
        live_cli._get_flat_tasks(tasks2, is_project=False)

        # Should call flatten_tasks twice (different task list identities)
        assert mock_flatten.call_count == 2


def test_strip_formatting_with_only_rich_tags(live_cli):
    """_strip_formatting handles Rich tags."""
    text = "Normal text with [bold]rich tags[/bold]"
    result = live_cli._strip_formatting(text)
    assert result == "Normal text with rich tags"


def test_strip_formatting_with_multiple_ansi_codes(live_cli):
    """_strip_formatting handles multiple ANSI codes."""
    text = "\x1b[1m\x1b[36mBold and colored\x1b[0m"
    result = live_cli._strip_formatting(text)
    assert result == "Bold and colored"
