"""Tests for move task to project feature."""

import pytest
from unittest.mock import Mock, MagicMock

from pm import Project, Task, Section
from pm_live.handlers.enter_handlers import EnterHandlers
from pm_live.handlers.key_handlers import KeyHandlers
from pm_live.interfaces import HandlerContext
from pm_live.states import AppState
from pm_live.ui_state import UIState


# ==================== Fixtures ====================


@pytest.fixture
def mock_manager():
    """Create a mock DataManagerProtocol."""
    manager = Mock()
    manager.projects = []
    manager.list_tasks = {}
    manager.get_project = Mock(return_value=None)
    manager.update_project = Mock()
    manager.mark_list_tasks_modified = Mock()
    manager.save = Mock()
    return manager


@pytest.fixture
def ui_state():
    """Create a UIState instance."""
    state = UIState()
    state.state = AppState.MAIN_MENU
    state.selected_index = 0
    state.active_tab = 0
    state.task_lists = ["Tasks", "Work", "Personal"]
    return state


@pytest.fixture
def mock_context(mock_manager, ui_state):
    """Create a mock HandlerContext."""
    context = Mock(spec=HandlerContext)
    context.manager = mock_manager
    context.ui_state = ui_state
    context.get_flat_tasks = Mock(return_value=[])
    context.invalidate_task_cache = Mock()
    context.exit_application = Mock()
    context.show_status = Mock()
    context.update_console_width = Mock()
    context.update_quick_stats_selection = Mock()
    context.update_main_menu_tabs_selection = Mock()
    context.persist_collapsed_tasks = Mock()
    return context


@pytest.fixture
def enter_handlers(mock_context):
    """Create an EnterHandlers instance."""
    return EnterHandlers(mock_context, Mock())


@pytest.fixture
def mock_task_handlers():
    """Create mock TaskHandlers."""
    return Mock()


@pytest.fixture
def mock_enter_handlers():
    """Create mock EnterHandlers."""
    return Mock()


@pytest.fixture
def key_handlers(mock_context, mock_task_handlers, mock_enter_handlers):
    """Create a KeyHandlers instance."""
    return KeyHandlers(mock_context, mock_task_handlers, mock_enter_handlers)


# ==================== Enter Handler Tests ====================


def test_move_task_from_project_to_another_project(mock_context, enter_handlers):
    """Move task from one project to another project."""
    ui_state = mock_context.ui_state
    manager = mock_context.manager

    # Setup source and target projects
    source_project = Project(id=1, name="Source Project", status="active")
    target_project = Project(id=2, name="Target Project", status="active")
    task = Task(name="Test Task")
    source_project.tasks = [task]
    target_project.tasks = []

    manager.projects = [source_project, target_project]
    manager.get_project = Mock(return_value=source_project)

    # Setup UI state for project selection
    ui_state.state = AppState.PROJECT_SELECTION_MENU
    ui_state.selected_index = 1  # Select target project
    ui_state.previous_state = AppState.PROJECT_DETAILS
    ui_state.move_task_source = {
        "task": task,
        "task_id": "task_1",
        "list_name": None,
        "section_idx": None,
        "project_id": 1,
    }

    enter_handlers.handle_project_selection_enter()

    # Verify task was removed from source and added to target
    assert task not in source_project.tasks
    assert task in target_project.tasks
    assert ui_state.state == AppState.PROJECT_DETAILS
    assert ui_state.current_project_id == 2
    assert ui_state.move_task_source is None


def test_move_task_from_task_list_to_project(mock_context, enter_handlers):
    """Move task from standalone task list to a project."""
    ui_state = mock_context.ui_state
    manager = mock_context.manager

    # Setup project and task in list
    target_project = Project(id=1, name="Target Project", status="active")
    target_project.tasks = []
    task = Task(name="Test Task")

    section = Section(name="", tasks=[task])
    manager.projects = [target_project]
    manager.list_tasks = {"Tasks": [section]}
    ui_state.list_tasks = manager.list_tasks

    # Setup UI state
    ui_state.state = AppState.PROJECT_SELECTION_MENU
    ui_state.selected_index = 0  # Select target project
    ui_state.previous_state = AppState.TASK_LIST
    ui_state.move_task_source = {
        "task": task,
        "task_id": "task_1",
        "list_name": "Tasks",
        "section_idx": 0,
        "project_id": None,
    }

    enter_handlers.handle_project_selection_enter()

    # Verify task was removed from list and added to project
    assert task not in section.tasks
    assert task in target_project.tasks
    assert ui_state.state == AppState.TASK_LIST
    assert ui_state.move_task_source is None
    manager.mark_list_tasks_modified.assert_called()


def test_move_task_from_project_to_tasks_list(mock_context, enter_handlers):
    """Move task from project to standalone Tasks list."""
    ui_state = mock_context.ui_state
    manager = mock_context.manager

    # Setup source project with task
    source_project = Project(id=1, name="Source Project", status="active")
    task = Task(name="Test Task")
    source_project.tasks = [task]

    section = Section(name="", tasks=[])
    manager.projects = [source_project]
    manager.list_tasks = {"Tasks": [section]}
    manager.get_project = Mock(return_value=source_project)
    ui_state.list_tasks = manager.list_tasks

    # Setup UI state - select "Move to Tasks" option (index = len(projects))
    ui_state.state = AppState.PROJECT_SELECTION_MENU
    ui_state.selected_index = 1  # Index after all projects = Move to Tasks
    ui_state.previous_state = AppState.PROJECT_DETAILS
    ui_state.move_task_source = {
        "task": task,
        "task_id": "task_1",
        "list_name": None,
        "section_idx": None,
        "project_id": 1,
    }

    enter_handlers.handle_project_selection_enter()

    # Verify task was moved to Tasks list
    assert task not in source_project.tasks
    assert task in section.tasks
    assert ui_state.state == AppState.TASK_LIST
    assert ui_state.move_task_source is None
    manager.mark_list_tasks_modified.assert_called()


def test_move_task_to_same_project_shows_error(mock_context, enter_handlers):
    """Attempting to move task to the same project shows an error."""
    ui_state = mock_context.ui_state
    manager = mock_context.manager

    # Setup project with task
    project = Project(id=1, name="Same Project", status="active")
    task = Task(name="Test Task")
    project.tasks = [task]

    manager.projects = [project]

    # Setup UI state - select the same project
    ui_state.state = AppState.PROJECT_SELECTION_MENU
    ui_state.selected_index = 0  # Select the same project
    ui_state.previous_state = AppState.PROJECT_DETAILS
    ui_state.move_task_source = {
        "task": task,
        "task_id": "task_1",
        "list_name": None,
        "section_idx": None,
        "project_id": 1,
    }

    enter_handlers.handle_project_selection_enter()

    # Verify error was shown and task was not moved
    assert task in project.tasks  # Task still in original project
    assert ui_state.move_task_source is None  # State was cleaned up
    # Verify we returned to previous state
    assert ui_state.state == AppState.PROJECT_DETAILS


def test_move_task_no_task_source_returns_to_previous(mock_context, enter_handlers):
    """When no task source is set, return to previous state."""
    ui_state = mock_context.ui_state

    ui_state.state = AppState.PROJECT_SELECTION_MENU
    ui_state.previous_state = AppState.PROJECT_DETAILS
    ui_state.move_task_source = None

    enter_handlers.handle_project_selection_enter()

    assert ui_state.state == AppState.PROJECT_DETAILS


def test_move_task_invalid_selection_returns_with_error(mock_context, enter_handlers):
    """Invalid selection index shows error and returns."""
    ui_state = mock_context.ui_state
    manager = mock_context.manager

    project = Project(id=1, name="Project", status="active")
    task = Task(name="Test Task")
    manager.projects = [project]

    # Setup UI state with invalid index
    ui_state.state = AppState.PROJECT_SELECTION_MENU
    ui_state.selected_index = 99  # Invalid index
    ui_state.previous_state = AppState.TASK_LIST
    ui_state.move_task_source = {
        "task": task,
        "task_id": "task_1",
        "list_name": "Tasks",
        "section_idx": 0,
        "project_id": None,
    }

    enter_handlers.handle_project_selection_enter()

    assert ui_state.state == AppState.TASK_LIST
    assert ui_state.move_task_source is None


def test_move_task_creates_tasks_section_if_missing(mock_context, enter_handlers):
    """When moving to Tasks list, create section if it doesn't exist."""
    ui_state = mock_context.ui_state
    manager = mock_context.manager

    # Setup source project with task
    source_project = Project(id=1, name="Source Project", status="active")
    task = Task(name="Test Task")
    source_project.tasks = [task]

    # No Tasks section exists
    manager.projects = [source_project]
    manager.list_tasks = {}
    manager.get_project = Mock(return_value=source_project)
    ui_state.list_tasks = manager.list_tasks

    # Setup UI state - select "Move to Tasks" option
    ui_state.state = AppState.PROJECT_SELECTION_MENU
    ui_state.selected_index = 1  # Move to Tasks
    ui_state.previous_state = AppState.PROJECT_DETAILS
    ui_state.move_task_source = {
        "task": task,
        "task_id": "task_1",
        "list_name": None,
        "section_idx": None,
        "project_id": 1,
    }

    enter_handlers.handle_project_selection_enter()

    # Verify Tasks section was created and task was added
    assert "Tasks" in manager.list_tasks
    assert len(manager.list_tasks["Tasks"]) == 1
    assert task in manager.list_tasks["Tasks"][0].tasks


# ==================== Key Handler Tests (Navigation) ====================


def test_navigate_up_in_project_selection(mock_context, key_handlers):
    """Navigate up in project selection menu."""
    ui_state = mock_context.ui_state

    ui_state.state = AppState.PROJECT_SELECTION_MENU
    ui_state.selected_index = 2

    key_handlers.on_up()

    assert ui_state.selected_index == 1


def test_navigate_up_at_top_stays_at_zero(mock_context, key_handlers):
    """Navigate up at top of list stays at index 0."""
    ui_state = mock_context.ui_state

    ui_state.state = AppState.PROJECT_SELECTION_MENU
    ui_state.selected_index = 0

    key_handlers.on_up()

    assert ui_state.selected_index == 0


def test_navigate_down_in_project_selection(mock_context, key_handlers):
    """Navigate down in project selection menu."""
    ui_state = mock_context.ui_state
    manager = mock_context.manager

    project1 = Project(id=1, name="Project 1", status="active")
    project2 = Project(id=2, name="Project 2", status="active")
    manager.projects = [project1, project2]

    ui_state.state = AppState.PROJECT_SELECTION_MENU
    ui_state.selected_index = 0
    ui_state.move_task_source = {"project_id": None}  # From task list, no Tasks option

    key_handlers.on_down()

    assert ui_state.selected_index == 1


def test_navigate_down_includes_tasks_option_when_from_project(mock_context, key_handlers):
    """Navigate down includes 'Move to Tasks' option when moving from a project."""
    ui_state = mock_context.ui_state
    manager = mock_context.manager

    project1 = Project(id=1, name="Project 1", status="active")
    manager.projects = [project1]

    ui_state.state = AppState.PROJECT_SELECTION_MENU
    ui_state.selected_index = 0
    ui_state.move_task_source = {"project_id": 1}  # From a project

    key_handlers.on_down()

    # Should be able to navigate to index 1 (Move to Tasks option)
    assert ui_state.selected_index == 1


def test_navigate_down_stops_at_last_project_when_from_list(mock_context, key_handlers):
    """Navigation stops at last project when moving from task list."""
    ui_state = mock_context.ui_state
    manager = mock_context.manager

    project1 = Project(id=1, name="Project 1", status="active")
    manager.projects = [project1]

    ui_state.state = AppState.PROJECT_SELECTION_MENU
    ui_state.selected_index = 0
    ui_state.move_task_source = {"project_id": None}  # From task list

    key_handlers.on_down()

    # Should stay at 0 since there's only one project and no Tasks option
    assert ui_state.selected_index == 0


# ==================== Key Handler Tests (Escape) ====================


def test_escape_cancels_project_selection(mock_context, key_handlers):
    """Escape cancels project selection and returns to previous state."""
    ui_state = mock_context.ui_state

    ui_state.state = AppState.PROJECT_SELECTION_MENU
    ui_state.previous_state = AppState.PROJECT_DETAILS
    ui_state.move_task_original_index = 5
    ui_state.move_task_source = {"task": Task(name="Test")}

    key_handlers.on_escape()

    assert ui_state.state == AppState.PROJECT_DETAILS
    assert ui_state.selected_index == 5  # Restored original index
    assert ui_state.move_task_source is None


def test_escape_clears_move_task_state(mock_context, key_handlers):
    """Escape clears all move task state variables."""
    ui_state = mock_context.ui_state

    ui_state.state = AppState.PROJECT_SELECTION_MENU
    ui_state.previous_state = AppState.TASK_LIST
    ui_state.move_task_source = {"task": Task(name="Test")}
    ui_state.move_task_target_project_idx = 3
    ui_state.move_task_original_index = 2

    key_handlers.on_escape()

    assert ui_state.move_task_source is None
    assert ui_state.move_task_target_project_idx == 0
    assert ui_state.move_task_original_index == 0


def test_escape_returns_to_main_menu_if_no_previous_state(mock_context, key_handlers):
    """Escape returns to main menu if previous state is not set."""
    ui_state = mock_context.ui_state

    ui_state.state = AppState.PROJECT_SELECTION_MENU
    ui_state.previous_state = None
    ui_state.move_task_source = {"task": Task(name="Test")}

    key_handlers.on_escape()

    assert ui_state.state == AppState.MAIN_MENU
    assert ui_state.selected_index == 0
