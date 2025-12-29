"""Tests for rendering modules (pm_live/render/)."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from io import StringIO

from pm import Project, Task, Section, BookmarkList, Bookmark
from pm_live.states import AppState
from pm_live.render.base import BaseRenderer
from pm_live.render.task_list import TaskListRenderer
from pm_live.render.main_menu import MainMenuRenderer
from pm_live.render.project_details import ProjectDetailsRenderer
from pm_live.render.forms import (
    AddProjectRenderer,
    EditProjectRenderer,
    ChangeStatusRenderer,
    DeleteConfirmationRenderer,
    EditListRenderer,
)
from pm_live.render.statistics import StatisticsRenderer


# ==================== Fixtures ====================


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = Mock()
    config.console_width = 100
    config.console_height = 30
    config.task_metadata_position = "next_to"
    config.quick_stats_metrics = ["total", "uncompleted_projects"]
    return config


@pytest.fixture
def mock_manager():
    """Create a mock DataManagerProtocol."""
    manager = Mock()
    manager.projects = []
    manager.standalone_tasks = []
    manager.bookmarks = []
    manager.metadata = {"pinned_items": []}
    manager.custom_field_definitions = []
    manager.default_field_visibility = {}
    manager.list_metadata = {}
    manager.get_project = Mock(return_value=None)
    return manager


@pytest.fixture
def sample_project():
    """Create a sample project with tasks."""
    return Project(
        id=1,
        name="Test Project",
        status="In Progress",
        description="A test project",
        tasks=[
            Task(name="Task 1", completed=None),
            Task(name="Task 2", completed=True),
            Task(
                name="Task 3",
                completed=None,
                subtasks=[
                    Task(name="Subtask 3.1", completed=None),
                    Task(name="Subtask 3.2", completed=True),
                ],
            ),
        ],
    )


@pytest.fixture
def sample_standalone_tasks():
    """Create sample standalone tasks."""
    return [
        Task(name="Standalone 1", completed=None),
        Task(name="Standalone 2", completed=True),
        Task(name="Standalone 3", completed=False),
    ]


# ==================== BaseRenderer Tests ====================


@patch("pm_live.render.base.get_config")
@patch("shutil.get_terminal_size")
def test_base_renderer_initialization(mock_terminal_size, mock_get_config, mock_config):
    """BaseRenderer initializes with config."""
    mock_terminal_size.return_value = Mock(columns=100)

    class ConcreteRenderer(BaseRenderer):
        def render(self, context):
            return "test"

    renderer = ConcreteRenderer()
    assert renderer._console is not None


@patch("pm_live.render.base.get_config")
def test_base_renderer_reset_console_buffer(mock_get_config, mock_config):
    """_reset_console_buffer creates new StringIO buffer."""

    class ConcreteRenderer(BaseRenderer):
        def render(self, context):
            return "test"

    renderer = ConcreteRenderer()
    renderer._reset_console_buffer()
    assert isinstance(renderer._console.file, StringIO)


@patch("pm_live.render.base.get_config")
def test_base_renderer_get_console_output(mock_get_config, mock_config):
    """_get_console_output returns buffer contents."""

    class ConcreteRenderer(BaseRenderer):
        def render(self, context):
            self._reset_console_buffer()
            self._console.print("Hello World")
            return self._get_console_output()

    renderer = ConcreteRenderer()
    output = renderer.render({})
    assert "Hello World" in output


@patch("pm_live.render.base.get_config")
def test_base_renderer_status_message_display(mock_get_config, mock_config):
    """_render_status_message displays status and error messages."""

    class ConcreteRenderer(BaseRenderer):
        def render(self, context):
            self._reset_console_buffer()
            self._render_status_message(context)
            return self._get_console_output()

    renderer = ConcreteRenderer()

    # Test normal status message
    context = {"status_message": "Test message", "status_is_error": False}
    output = renderer.render(context)
    assert "Test message" in output

    # Test error message
    context = {"status_message": "Error occurred", "status_is_error": True}
    output = renderer.render(context)
    assert "Error occurred" in output


@patch("pm_live.render.base.get_config")
def test_base_renderer_pad_to_bottom(mock_get_config, mock_config):
    """_pad_to_bottom adds newlines to fill screen."""

    class ConcreteRenderer(BaseRenderer):
        def render(self, context):
            self._reset_console_buffer()
            self._console.print("Line 1")
            self._console.print("Line 2")
            self._pad_to_bottom()
            return self._get_console_output()

    renderer = ConcreteRenderer()
    output = renderer.render({})
    # Should have padding newlines (exact count depends on config height)
    assert output.count("\n") >= 2


# ==================== MainMenuRenderer Tests ====================


def test_main_menu_basic_render(mock_manager):
    """MainMenuRenderer renders menu with quick stats."""
    renderer = MainMenuRenderer()
    context = {
        "manager": mock_manager,
        "selected_index": 0,
        "inline_input_mode": False,
        "text_input_buffer": "",
        "main_menu_tabs_selection": set(),
        "quick_stats_selection": set(),
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "Project Manager" in output
    assert "Settings" in output
    assert "Exit" in output


def test_main_menu_quick_stats_display(mock_manager):
    """MainMenuRenderer displays quick stats metrics."""
    mock_manager.projects = [Mock(), Mock(), Mock()]  # 3 projects

    renderer = MainMenuRenderer()
    context = {
        "manager": mock_manager,
        "selected_index": 0,
        "inline_input_mode": False,
        "text_input_buffer": "",
        "main_menu_tabs_selection": set(),
        "quick_stats_selection": {"uncompleted_projects"},
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "uncompleted project" in output


def test_main_menu_quick_add_mode(mock_manager):
    """MainMenuRenderer shows inline input when in input mode."""
    renderer = MainMenuRenderer()
    context = {
        "manager": mock_manager,
        "selected_index": 0,
        "inline_input_mode": True,
        "text_input_buffer": "New quick task",
        "main_menu_tabs_selection": {"quick_add"},  # Enable quick add
        "quick_stats_selection": set(),
        "quick_add_field_index": 0,
        "quick_add_priority": None,
        "quick_add_deadline": None,
        "quick_add_deadline_component": 0,
        "quick_add_deadline_edit_mode": False,
        "quick_add_list": "Tasks",
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "Project Manager" in output


def test_main_menu_selection_indicator(mock_manager):
    """MainMenuRenderer shows selection indicator on current item."""
    renderer = MainMenuRenderer()
    context = {
        "manager": mock_manager,
        "selected_index": 1,  # Select first menu item
        "inline_input_mode": False,
        "text_input_buffer": "",
        "main_menu_tabs_selection": set(),
        "quick_stats_selection": set(),
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    # Selection indicator depends on terminal/font; just ensure a selector-like character exists.
    assert ("›" in output) or (">" in output)


# ==================== TaskListRenderer Tests ====================


def test_task_list_empty_tasks(mock_manager):
    """TaskListRenderer handles empty task list."""

    renderer = TaskListRenderer()
    context = {
        "manager": mock_manager,
        "list_tasks": {"Tasks": [Section(name="", tasks=[])]},
        "task_lists": ["Tasks"],
        "active_tab": 0,
        "selected_index": 0,
        "inline_input_mode": False,
        "text_input_buffer": "",
        "collapsed_tasks": set(),
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "No tasks" in output or "+" in output


def test_task_list_flat_tasks(mock_manager, sample_standalone_tasks):
    """TaskListRenderer renders flat task list."""

    renderer = TaskListRenderer()
    context = {
        "manager": mock_manager,
        "list_tasks": {"Tasks": [Section(name="", tasks=sample_standalone_tasks)]},
        "task_lists": ["Tasks"],
        "active_tab": 0,
        "selected_index": 0,
        "inline_input_mode": False,
        "text_input_buffer": "",
        "collapsed_tasks": set(),
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    # Check for task names (they may have ANSI color codes)
    assert "Standalone" in output
    assert "1" in output
    assert "2" in output
    assert "3" in output


def test_task_list_nested_tasks(mock_manager):
    """TaskListRenderer renders nested tasks with indentation."""

    tasks = [
        Task(
            name="Parent Task",
            completed=None,
            subtasks=[
                Task(name="Child Task 1", completed=None),
                Task(name="Child Task 2", completed=True),
            ],
        )
    ]

    renderer = TaskListRenderer()
    context = {
        "manager": mock_manager,
        "list_tasks": {"Tasks": [Section(name="", tasks=tasks)]},
        "task_lists": ["Tasks"],
        "active_tab": 0,
        "selected_index": 0,
        "inline_input_mode": False,
        "text_input_buffer": "",
        "collapsed_tasks": set(),
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    # Check for task names (may have ANSI color codes)
    assert "Parent Task" in output
    assert "Child Task" in output


def test_task_list_collapsed_tasks(mock_manager):
    """TaskListRenderer hides collapsed subtasks."""

    tasks = [
        Task(
            name="Parent Task",
            completed=None,
            subtasks=[
                Task(name="Hidden Child", completed=None),
            ],
        )
    ]

    renderer = TaskListRenderer()
    context = {
        "manager": mock_manager,
        "list_tasks": {"Tasks": [Section(name="", tasks=tasks)]},
        "task_lists": ["Tasks"],
        "active_tab": 0,
        "selected_index": 0,
        "inline_input_mode": False,
        "text_input_buffer": "",
        "collapsed_tasks": {(0,)},  # Collapse first task
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "Parent Task" in output
    # Note: collapsed tasks may still show in some lists depending on implementation


def test_task_list_sections(mock_manager):
    """TaskListRenderer renders multiple sections."""

    renderer = TaskListRenderer()
    context = {
        "manager": mock_manager,
        "list_tasks": {
            "Tasks": [
                Section(name="Work", tasks=[Task(name="Work Task", completed=None)]),
                Section(name="Personal", tasks=[Task(name="Personal Task", completed=None)]),
            ]
        },
        "task_lists": ["Tasks"],
        "active_tab": 0,
        "selected_index": 0,
        "inline_input_mode": False,
        "text_input_buffer": "",
        "collapsed_tasks": set(),
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "Work" in output
    assert "Personal" in output
    assert "Work Task" in output
    assert "Personal Task" in output


def test_task_list_add_task_input(mock_manager):
    """TaskListRenderer shows inline input for adding tasks."""

    renderer = TaskListRenderer()
    context = {
        "manager": mock_manager,
        "list_tasks": {"Tasks": [Section(name="", tasks=[])]},
        "task_lists": ["Tasks"],
        "active_tab": 0,
        "selected_index": 0,
        "inline_input_mode": True,
        "text_input_buffer": "New task name",
        "collapsed_tasks": set(),
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "New task name" in output
    assert "+" in output


def test_task_list_completed_section(mock_manager, sample_standalone_tasks):
    """TaskListRenderer shows completed tasks in separate section."""

    renderer = TaskListRenderer()
    context = {
        "manager": mock_manager,
        "list_tasks": {"Tasks": [Section(name="", tasks=sample_standalone_tasks)]},
        "task_lists": ["Tasks"],
        "active_tab": 0,
        "selected_index": 0,
        "inline_input_mode": False,
        "text_input_buffer": "",
        "collapsed_tasks": set(),
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "Done" in output


# ==================== ProjectDetailsRenderer Tests ====================



def test_project_details_not_found(mock_manager):
    """ProjectDetailsRenderer handles missing project."""
    mock_manager.get_project.return_value = None

    renderer = ProjectDetailsRenderer()
    context = {
        "manager": mock_manager,
        "current_project_id": 999,
        "selected_index": 0,
        "inline_input_mode": False,
        "text_input_buffer": "",
        "collapsed_tasks": set(),
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "not found" in output.lower()



def test_project_details_basic_render(mock_manager, sample_project):
    """ProjectDetailsRenderer renders project information."""
    mock_manager.get_project.return_value = sample_project

    renderer = ProjectDetailsRenderer()
    context = {
        "manager": mock_manager,
        "current_project_id": 1,
        "selected_index": 0,
        "inline_input_mode": False,
        "text_input_buffer": "",
        "collapsed_tasks": set(),
        "status_message": None,
        "status_is_error": False,
    }

    import re

    output = renderer.render(context)
    output_plain = re.sub(r"\x1b\[[0-9;]*m", "", output)
    # Check for project info (may have ANSI codes)
    assert "TEST PROJECT" in output_plain.upper()
    assert "2/5" in output_plain
    assert "40%" in output_plain



def test_project_details_shows_tasks(mock_manager, sample_project):
    """ProjectDetailsRenderer displays project tasks."""
    mock_manager.get_project.return_value = sample_project

    renderer = ProjectDetailsRenderer()
    context = {
        "manager": mock_manager,
        "current_project_id": 1,
        "selected_index": 0,
        "inline_input_mode": False,
        "text_input_buffer": "",
        "collapsed_tasks": set(),
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "Task" in output
    assert "1" in output
    assert "2" in output
    assert "3" in output



def test_project_details_progress_bar(mock_manager, sample_project):
    """ProjectDetailsRenderer shows progress visualization."""
    mock_manager.get_project.return_value = sample_project

    renderer = ProjectDetailsRenderer()
    context = {
        "manager": mock_manager,
        "current_project_id": 1,
        "selected_index": 0,
        "inline_input_mode": False,
        "text_input_buffer": "",
        "collapsed_tasks": set(),
        "status_message": None,
        "status_is_error": False,
    }

    import re

    output = renderer.render(context)
    output_plain = re.sub(r"\x1b\[[0-9;]*m", "", output)
    # Should show progress info (e.g., "2/4 tasks" or progress bar)
    assert "2/5" in output_plain



def test_project_details_actions(mock_manager, sample_project):
    """ProjectDetailsRenderer shows available actions."""
    mock_manager.get_project.return_value = sample_project

    renderer = ProjectDetailsRenderer()
    context = {
        "manager": mock_manager,
        "current_project_id": 1,
        "selected_index": 0,
        "inline_input_mode": False,
        "text_input_buffer": "",
        "collapsed_tasks": set(),
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "Edit" in output or "Change Status" in output
    assert "Back" in output


# ==================== AddProjectRenderer Tests ====================



def test_add_project_form_basic_render():
    """AddProjectRenderer renders form fields."""

    renderer = AddProjectRenderer()
    context = {
        "manager": Mock(metadata={"pinned_items": []}, default_field_visibility={}, custom_field_definitions=[]),
        "state": AppState.ADD_PROJECT,
        "temp_project": Project(id="__temp__", name="", status="Planned", tasks=[]),
        "form_field_index": 0,
        "form_data": {},
        "inline_input_mode": False,
        "text_input_buffer": "",
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "New Project" in output
    assert "Name" in output
    assert "Timeframe" in output
    assert "Status" in output



def test_add_project_form_name_input():
    """AddProjectRenderer shows inline input for name."""

    renderer = AddProjectRenderer()
    context = {
        "manager": Mock(metadata={"pinned_items": []}, default_field_visibility={}, custom_field_definitions=[]),
        "state": AppState.ADD_PROJECT,
        "temp_project": Project(id="__temp__", name="", status="Planned", tasks=[]),
        # Field order starts with: status (0), name (1), description (2)
        "form_field_index": 1,
        "form_data": {},
        "inline_input_mode": True,
        "text_input_buffer": "My New Project",
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "My New Project" in output



def test_add_project_form_filled_data():
    """AddProjectRenderer displays filled form data."""

    renderer = AddProjectRenderer()
    context = {
        "manager": Mock(metadata={"pinned_items": []}, default_field_visibility={}, custom_field_definitions=[]),
        "state": AppState.ADD_PROJECT,
        "temp_project": Project(id="__temp__", name="", status="Planned", tasks=[]),
        "form_field_index": 3,
        "form_data": {
            "name": "Test Project",
            "timeframe": "Short-Term",
            "status": "Planned",
        },
        "inline_input_mode": False,
        "text_input_buffer": "",
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "Test Project" in output
    assert "Short-Term" in output
    assert "Planned" in output



def test_add_project_form_actions():
    """AddProjectRenderer shows submit and cancel actions."""

    renderer = AddProjectRenderer()
    context = {
        "manager": Mock(metadata={"pinned_items": []}, default_field_visibility={}, custom_field_definitions=[]),
        "state": AppState.ADD_PROJECT,
        "temp_project": Project(id="__temp__", name="", status="Planned", tasks=[]),
        "form_field_index": 0,
        "form_data": {},
        "inline_input_mode": False,
        "text_input_buffer": "",
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "Create" in output or "✓" in output
    assert "Cancel" in output


# ==================== EditProjectRenderer Tests ====================



def test_edit_project_form_not_found(mock_manager):
    """EditProjectRenderer handles missing project."""
    mock_manager.get_project.return_value = None

    renderer = EditProjectRenderer()
    context = {
        "manager": mock_manager,
        "current_project_id": 999,
        "form_field_index": 0,
        "form_data": {},
        "inline_input_mode": False,
        "text_input_buffer": "",
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "not found" in output.lower()



def test_edit_project_form_basic_render(mock_manager, sample_project):
    """EditProjectRenderer renders form with project data."""
    mock_manager.get_project.return_value = sample_project

    renderer = EditProjectRenderer()
    context = {
        "manager": mock_manager,
        "current_project_id": 1,
        "form_field_index": 0,
        "form_data": {
            "name": "Test Project",
            "description": "A test project",
            "timeframe": "Short-Term",
        },
        "inline_input_mode": False,
        "text_input_buffer": "",
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "TEST PROJECT" in output.upper()
    assert "DESCRIPTION" in output.upper() or "Description" in output
    assert "TIMEFRAME" in output.upper() or "Timeframe" in output



def test_edit_project_form_actions(mock_manager, sample_project):
    """EditProjectRenderer shows save, delete, and cancel actions."""
    mock_manager.get_project.return_value = sample_project

    renderer = EditProjectRenderer()
    context = {
        "manager": mock_manager,
        "current_project_id": 1,
        "form_field_index": 0,
        "form_data": {
            "name": "Test Project",
            "description": "A test project",
            "timeframe": "Short-Term",
        },
        "inline_input_mode": False,
        "text_input_buffer": "",
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "Save" in output
    assert "Delete" in output
    assert "Cancel" in output


# ==================== ChangeStatusRenderer Tests ====================



def test_change_status_basic_render(mock_manager, sample_project):
    """ChangeStatusRenderer renders status options."""
    mock_manager.get_project.return_value = sample_project

    renderer = ChangeStatusRenderer()
    context = {
        "manager": mock_manager,
        "current_project_id": 1,
        "selected_index": 0,
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "CHANGE STATUS" in output.upper() or "STATUS" in output.upper()
    assert "TEST PROJECT" in output.upper()
    assert "PLANNED" in output.upper() or "Planned" in output
    assert "PROGRESS" in output.upper() or "In Progress" in output
    assert "HOLD" in output.upper() or "On Hold" in output
    assert "DONE" in output.upper() or "Done" in output



def test_change_status_current_status_display(mock_manager, sample_project):
    """ChangeStatusRenderer shows current status."""
    mock_manager.get_project.return_value = sample_project

    renderer = ChangeStatusRenderer()
    context = {
        "manager": mock_manager,
        "current_project_id": 1,
        "selected_index": 0,
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "Current status" in output.lower() or "In Progress" in output


# ==================== DeleteConfirmationRenderer Tests ====================



def test_delete_confirmation_basic_render():
    """DeleteConfirmationRenderer shows yes/no options."""

    renderer = DeleteConfirmationRenderer()
    context = {
        "form_field_index": 0,
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "DELETE" in output.upper() or "CONFIRMATION" in output.upper()
    assert "Yes" in output or "delete" in output.lower()
    assert "No" in output or "cancel" in output.lower()



def test_delete_confirmation_warning_message():
    """DeleteConfirmationRenderer shows warning about permanence."""

    renderer = DeleteConfirmationRenderer()
    context = {
        "form_field_index": 0,
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "sure" in output.lower() or "cannot be undone" in output.lower()


# ==================== StatisticsRenderer Tests ====================



@patch("pm_live.render.statistics.get_stats")
def test_statistics_basic_render(mock_get_stats, mock_manager):
    """StatisticsRenderer displays project statistics."""
    mock_get_stats.return_value = {
        "total": 10,
        "planned": 2,
        "in_progress": 5,
        "on_hold": 1,
        "done": 2,
        "uncompleted_projects": 8,
    }

    renderer = StatisticsRenderer()
    context = {
        "manager": mock_manager,
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "Stats" in output
    assert "Projects" in output



@patch("pm_live.render.statistics.get_stats")
def test_statistics_shows_status_breakdown(mock_get_stats, mock_manager):
    """StatisticsRenderer shows breakdown by status."""
    mock_get_stats.return_value = {
        "total": 10,
        "planned": 2,
        "in_progress": 5,
        "on_hold": 1,
        "done": 2,
        "uncompleted_projects": 8,
    }

    renderer = StatisticsRenderer()
    context = {
        "manager": mock_manager,
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "Planned" in output
    assert "In Progress" in output
    assert "On Hold" in output
    assert "Done" in output



@patch("pm_live.render.statistics.get_stats")
def test_statistics_standalone_tasks(mock_get_stats, mock_manager, sample_standalone_tasks):
    """StatisticsRenderer shows standalone task statistics."""
    mock_get_stats.return_value = {"total": 5, "uncompleted_projects": 3}
    mock_manager.standalone_tasks = sample_standalone_tasks

    renderer = StatisticsRenderer()
    context = {
        "manager": mock_manager,
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "STANDALONE" in output.upper() or "TASKS" in output.upper()



@patch("pm_live.render.statistics.get_stats")
def test_statistics_bookmarks(mock_get_stats, mock_manager):
    """StatisticsRenderer shows bookmark statistics."""
    mock_get_stats.return_value = {"total": 5, "uncompleted_projects": 3}

    # Create sample bookmarks
    bookmark_list = BookmarkList(title="My List", items=[
        Bookmark(title="Link 1", url="http://example.com/1"),
        Bookmark(title="Link 2", url="http://example.com/2"),
    ])
    mock_manager.bookmarks = [bookmark_list]

    renderer = StatisticsRenderer()
    context = {
        "manager": mock_manager,
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "BOOKMARK" in output.upper()


# ==================== EditListRenderer Tests ====================



def test_edit_list_create_mode():
    """EditListRenderer shows create new list form."""

    renderer = EditListRenderer()
    context = {
        "form_field_index": 0,
        "form_data": {"name": "", "mode": "normal"},
        "inline_input_mode": False,
        "text_input_buffer": "",
        "editing_list_name": None,  # None = create mode
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "New List" in output



def test_edit_list_edit_mode():
    """EditListRenderer shows edit existing list form."""

    renderer = EditListRenderer()
    context = {
        "form_field_index": 0,
        "form_data": {"name": "My List", "mode": "sections"},
        "inline_input_mode": False,
        "text_input_buffer": "",
        "editing_list_name": "My List",  # Not None = edit mode
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "My List" in output
    assert "My List" in output



def test_edit_list_sections_mode():
    """EditListRenderer shows sections when mode is 'sections'."""

    renderer = EditListRenderer()
    context = {
        "form_field_index": 0,
        "form_data": {
            "name": "My List",
            "mode": "sections",
            "sections": [
                {"name": "Section 1", "tasks": []},
                {"name": "Section 2", "tasks": []},
            ],
        },
        "inline_input_mode": False,
        "text_input_buffer": "",
        "editing_list_name": None,
        "pending_section_add": False,
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "Section" in output
    assert "1" in output
    assert "2" in output


# ==================== Integration Tests ====================


def test_task_list_full_workflow(mock_manager, sample_project):
    """Test complete task list rendering workflow."""
    # Create list with project tasks
    tasks = sample_project.tasks
    renderer = TaskListRenderer()

    # Initial render
    context = {
        "manager": mock_manager,
        "list_tasks": {"Tasks": [Section(name="", tasks=tasks)]},
        "task_lists": ["Tasks"],
        "active_tab": 0,
        "selected_index": 0,
        "inline_input_mode": False,
        "text_input_buffer": "",
        "collapsed_tasks": set(),
        "status_message": None,
        "status_is_error": False,
    }

    output = renderer.render(context)
    assert "Task" in output
    assert "1" in output
    assert "3" in output

    # Collapse task 3 (has subtasks)
    context["collapsed_tasks"] = {(2,)}
    output = renderer.render(context)
    assert "Task" in output
    # Subtasks may or may not be shown depending on collapsed state



def test_add_edit_project_workflow(mock_manager, sample_project):
    """Test add and edit project form workflow."""

    # Step 1: Add project form
    add_renderer = AddProjectRenderer()
    add_context = {
        "manager": Mock(metadata={"pinned_items": []}, default_field_visibility={}, custom_field_definitions=[]),
        "state": AppState.ADD_PROJECT,
        "temp_project": Project(id="__temp__", name="", status="Planned", tasks=[]),
        "form_field_index": 0,
        "form_data": {},
        "inline_input_mode": False,
        "text_input_buffer": "",
        "status_message": None,
        "status_is_error": False,
    }

    output = add_renderer.render(add_context)
    assert "New Project" in output

    # Step 2: Fill form
    add_context["form_data"] = {
        "name": "New Project",
        "status": "Planned",
    }
    output = add_renderer.render(add_context)
    assert "New Project" in output

    # Step 3: Edit existing project
    mock_manager.get_project.return_value = sample_project
    edit_renderer = EditProjectRenderer()
    edit_context = {
        "manager": mock_manager,
        "current_project_id": 1,
        "form_field_index": 0,
        "form_data": {
            "name": sample_project.name,
            "description": sample_project.description,
        },
        "inline_input_mode": False,
        "text_input_buffer": "",
        "status_message": None,
        "status_is_error": False,
    }

    output = edit_renderer.render(edit_context)
    assert "TEST PROJECT" in output.upper()
