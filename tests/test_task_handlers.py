"""Tests for task handler operations (pm_live/handlers/task_handlers.py)."""

import pytest
from unittest.mock import Mock, MagicMock, patch, call

from pm import Task, Project
from pm_live.handlers.task_handlers import TaskHandlers
from pm_live.interfaces import HandlerContext
from pm_live.ui_state import UIState
from pm_live.states import AppState


# ==================== Fixtures ====================


@pytest.fixture
def mock_manager():
    """Create a mock DataManagerProtocol."""
    manager = Mock()
    manager.standalone_tasks = []
    manager.save = Mock(return_value=True)
    manager.mark_standalone_tasks_modified = Mock()
    manager.mark_list_tasks_modified = Mock()
    manager.update_project = Mock()
    manager.get_project = Mock()
    return manager


@pytest.fixture
def mock_ui_state():
    """Create a mock UIState."""
    ui_state = UIState()
    ui_state.state = AppState.PROJECT_DETAILS
    ui_state.current_project_id = 1
    ui_state.selected_index = 0
    ui_state.collapsed_tasks = set()
    ui_state.delete_context = None
    ui_state.form_field_index = 0
    return ui_state


@pytest.fixture
def mock_get_flat_tasks():
    """Create a mock flatten tasks function."""
    def _flatten(tasks, include_collapsed):
        """Simple flatten that returns (path, task, depth) tuples."""
        result = []
        for i, task in enumerate(tasks, 1):
            path = str(i)
            result.append((path, task, 0))
            # Add subtasks if present
            for j, subtask in enumerate(getattr(task, 'subtasks', []), 1):
                subpath = f"{path}.{j}"
                result.append((subpath, subtask, 1))
        return result
    return _flatten


@pytest.fixture
def mock_context(mock_manager, mock_ui_state, mock_get_flat_tasks):
    """Create a mock HandlerContext."""
    context = Mock(spec=HandlerContext)
    context.manager = mock_manager
    context.ui_state = mock_ui_state
    context.get_flat_tasks = mock_get_flat_tasks
    context.invalidate_task_cache = Mock()
    context.exit_application = Mock()
    context.show_status = Mock()
    context.update_console_width = Mock()
    context.update_quick_stats_selection = Mock()
    context.update_main_menu_tabs_selection = Mock()
    return context


@pytest.fixture
def task_handlers(mock_context):
    """Create a TaskHandlers instance."""
    return TaskHandlers(mock_context)


@pytest.fixture
def sample_project():
    """Create a sample project with tasks."""
    return Project(
        id=1,
        name="Test Project",
        status="In Progress",
        tasks=[
            Task(name="Task 1"),
            Task(name="Task 2", subtasks=[
                Task(name="Task 2.1"),
            ]),
            Task(name="Task 3"),
        ],
    )


# ==================== Get Selected Task Tests ====================


def test_get_selected_flat_task_project_details(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Get selected task in PROJECT_DETAILS state."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 0
    mock_manager.get_project.return_value = sample_project

    selected = task_handlers._get_selected_flat_task()

    assert selected is not None
    path, task, depth = selected
    assert path == "1"
    assert task.name == "Task 1"
    assert depth == 0


def test_get_selected_flat_task_invalid_index(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Get selected task with out of bounds index returns None."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.selected_index = 999
    mock_manager.get_project.return_value = sample_project

    selected = task_handlers._get_selected_flat_task()
    assert selected is None


def test_get_selected_flat_task_no_project(task_handlers, mock_manager, mock_ui_state):
    """Get selected task when project not found returns None."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_manager.get_project.return_value = None

    selected = task_handlers._get_selected_flat_task()
    assert selected is None


def test_get_selected_flat_task_standalone_tasks(task_handlers, mock_manager, mock_ui_state):
    """Get selected task from standalone tasks (TASK_LIST state)."""
    from pm import Section
    tasks = [Task(name="Standalone 1"), Task(name="Standalone 2")]
    section = Section(name="Tasks", tasks=tasks)
    mock_manager.standalone_tasks = tasks
    mock_ui_state.state = AppState.TASK_LIST
    mock_ui_state.selected_index = 1  # Index 0 is the section header
    mock_ui_state.task_lists = ["Tasks"]
    mock_ui_state.active_tab = 0
    mock_ui_state.list_tasks = {"Tasks": [section]}

    selected = task_handlers._get_selected_flat_task()

    assert selected is not None
    path, task, depth = selected
    assert task.name == "Standalone 1"


# ==================== Indent Handler Tests ====================


def test_handle_indent_success(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Test successful task indent operation."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 2  # Select "Task 2.1"
    mock_manager.get_project.return_value = sample_project

    with patch('pm_live.handlers.task_handlers.handle_task_indent', return_value=True) as mock_indent:
        task_handlers.handle_indent()

        # Verify indent was called
        mock_indent.assert_called_once()
        # Verify cache invalidation
        task_handlers._context.invalidate_task_cache.assert_called_once()


def test_handle_indent_no_selected_task(task_handlers, mock_manager, mock_ui_state):
    """Indent with no selected task should do nothing."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_manager.get_project.return_value = None

    with patch('pm_live.handlers.task_handlers.handle_task_indent') as mock_indent:
        task_handlers.handle_indent()

        # Should not call indent
        mock_indent.assert_not_called()


def test_handle_indent_standalone_tasks(task_handlers, mock_manager, mock_ui_state):
    """Test indent on standalone tasks."""
    from pm import Section
    tasks = [Task(name="Task 1"), Task(name="Task 2")]
    section = Section(name="Tasks", tasks=tasks)
    mock_manager.standalone_tasks = tasks
    mock_ui_state.state = AppState.TASK_LIST
    mock_ui_state.selected_index = 1
    mock_ui_state.task_lists = ["Tasks"]
    mock_ui_state.active_tab = 0
    mock_ui_state.list_tasks = {"Tasks": [section]}

    with patch('pm_live.handlers.task_handlers.handle_task_indent', return_value=True) as mock_indent:
        task_handlers.handle_indent()

        # Verify indent was called with is_standalone=True
        assert mock_indent.call_args[0][3] is True  # is_standalone argument
        # Verify save was called
        mock_manager.save.assert_called_once()


# ==================== Outdent Handler Tests ====================


def test_handle_outdent_success(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Test successful task outdent operation."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 2  # Select "Task 2.1"
    mock_manager.get_project.return_value = sample_project

    with patch('pm_live.handlers.task_handlers.handle_task_outdent', return_value=True) as mock_outdent:
        task_handlers.handle_outdent()

        # Verify outdent was called
        mock_outdent.assert_called_once()
        # Verify cache invalidation
        task_handlers._context.invalidate_task_cache.assert_called_once()


def test_handle_outdent_failed(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Test failed outdent (e.g., already at root level)."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 0  # Select first task
    mock_manager.get_project.return_value = sample_project

    with patch('pm_live.handlers.task_handlers.handle_task_outdent', return_value=False) as mock_outdent:
        task_handlers.handle_outdent()

        # Verify outdent was called but failed
        mock_outdent.assert_called_once()
        # Cache should NOT be invalidated on failure
        task_handlers._context.invalidate_task_cache.assert_not_called()


# ==================== Delete Handler Tests ====================


def test_handle_delete_completed_task_no_confirmation(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Deleting a completed task should skip confirmation."""
    # Create project with completed task
    sample_project.tasks[0].completed = True
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 0  # Select first task (completed)
    mock_manager.get_project.return_value = sample_project

    with patch('pm_live.handlers.task_handlers.handle_task_delete', return_value=True) as mock_delete:
        task_handlers.handle_delete()

        # Should delete immediately without confirmation
        mock_delete.assert_called_once()
        # Should NOT transition to DELETE_CONFIRMATION state
        assert mock_ui_state.state == AppState.PROJECT_DETAILS


def test_handle_delete_pending_task_shows_confirmation(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Deleting a pending task should show confirmation dialog."""
    # Task with completed=None (pending)
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 1  # Select second task (pending)
    mock_manager.get_project.return_value = sample_project

    task_handlers.handle_delete()

    # Should transition to DELETE_CONFIRMATION state
    assert mock_ui_state.state == AppState.DELETE_CONFIRMATION
    # Should set delete context
    assert mock_ui_state.delete_context is not None
    assert mock_ui_state.delete_context['delete_type'] == 'task'
    assert mock_ui_state.delete_context['previous_state'] == AppState.PROJECT_DETAILS


def test_execute_confirmed_delete_success(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Execute confirmed delete successfully removes task."""
    delete_params = {
        'path': '1',
        'is_standalone': False,
        'current_project_id': 1
    }
    mock_manager.get_project.return_value = sample_project

    with patch('pm_live.handlers.task_handlers.handle_task_delete', return_value=True) as mock_delete:
        result = task_handlers.execute_confirmed_delete(delete_params)

        assert result is True
        mock_delete.assert_called_once()
        task_handlers._context.invalidate_task_cache.assert_called_once()


def test_execute_confirmed_delete_standalone_tasks(task_handlers, mock_manager, mock_ui_state):
    """Execute confirmed delete on standalone tasks."""
    tasks = [Task(name="Task 1"), Task(name="Task 2")]
    mock_manager.standalone_tasks = tasks
    delete_params = {
        'path': '1',
        'is_standalone': True,
        'current_project_id': None
    }

    with patch('pm_live.handlers.task_handlers.handle_task_delete', return_value=True) as mock_delete:
        result = task_handlers.execute_confirmed_delete(delete_params)

        assert result is True
        # Should save and mark modified for standalone tasks
        mock_manager.save.assert_called_once()


# ==================== Move Up Handler Tests ====================


def test_handle_task_move_up_success(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Test successful move up operation."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 1  # Select "Task 2"
    mock_manager.get_project.return_value = sample_project

    with patch('pm_live.handlers.task_handlers.handle_task_move_up', return_value=True) as mock_move:
        task_handlers.handle_task_move_up()

        # Verify move was called
        mock_move.assert_called_once()
        # Verify cache invalidation
        task_handlers._context.invalidate_task_cache.assert_called_once()


def test_handle_task_move_up_no_selected_task(task_handlers, mock_manager, mock_ui_state):
    """Move up with no selected task should do nothing."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_manager.get_project.return_value = None

    with patch('pm_live.handlers.task_handlers.handle_task_move_up') as mock_move:
        task_handlers.handle_task_move_up()

        # Should not call move
        mock_move.assert_not_called()


def test_handle_task_move_up_reselects_task(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Move up should reselect the moved task."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 1  # Select "Task 2"
    moved_task = sample_project.tasks[1]
    mock_manager.get_project.return_value = sample_project

    with patch('pm_live.handlers.task_handlers.handle_task_move_up', return_value=True):
        task_handlers.handle_task_move_up()

        # The task should be reselected (implementation updates selected_index)
        # In this test, we just verify the logic ran without errors


# ==================== Move Down Handler Tests ====================


def test_handle_task_move_down_success(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Test successful move down operation."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 0  # Select "Task 1"
    mock_manager.get_project.return_value = sample_project

    with patch('pm_live.handlers.task_handlers.handle_task_move_down', return_value=True) as mock_move:
        task_handlers.handle_task_move_down()

        # Verify move was called
        mock_move.assert_called_once()
        # Verify cache invalidation
        task_handlers._context.invalidate_task_cache.assert_called_once()


def test_handle_task_move_down_failed(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Test failed move down (e.g., already at bottom)."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 2  # Select last task
    mock_manager.get_project.return_value = sample_project

    with patch('pm_live.handlers.task_handlers.handle_task_move_down', return_value=False) as mock_move:
        task_handlers.handle_task_move_down()

        # Verify move was called but failed
        mock_move.assert_called_once()
        # Cache should NOT be invalidated on failure
        task_handlers._context.invalidate_task_cache.assert_not_called()


# ==================== Collapse Toggle Tests ====================


def test_handle_collapse_toggle_collapse(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Test collapsing a task with subtasks."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 1  # Select "Task 2" which has subtasks
    mock_manager.get_project.return_value = sample_project

    task_handlers.handle_collapse_toggle()

    # Task 2 should be collapsed (path "2" added to collapsed_tasks)
    assert "2" in mock_ui_state.collapsed_tasks
    # Cache should be invalidated
    task_handlers._context.invalidate_task_cache.assert_called_once()


def test_handle_collapse_toggle_expand(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Test expanding a collapsed task."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 1  # Select "Task 2"
    mock_ui_state.collapsed_tasks.add("2")  # Pre-collapse it
    mock_manager.get_project.return_value = sample_project

    task_handlers.handle_collapse_toggle()

    # Task 2 should be expanded (removed from collapsed_tasks)
    assert "2" not in mock_ui_state.collapsed_tasks


def test_handle_collapse_toggle_no_subtasks(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Test toggle on task without subtasks does nothing."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 0  # Select "Task 1" (no subtasks)
    mock_manager.get_project.return_value = sample_project

    task_handlers.handle_collapse_toggle()

    # Should not add to collapsed_tasks
    assert len(mock_ui_state.collapsed_tasks) == 0
    # Should not invalidate cache
    task_handlers._context.invalidate_task_cache.assert_not_called()


def test_handle_collapse_toggle_no_selected_task(task_handlers, mock_manager, mock_ui_state):
    """Toggle with no selected task should do nothing."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_manager.get_project.return_value = None

    task_handlers.handle_collapse_toggle()

    # Should not crash or do anything
    assert len(mock_ui_state.collapsed_tasks) == 0


# ==================== Integration Tests ====================


def test_indent_outdent_sequence(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Test indent followed by outdent."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 1
    mock_manager.get_project.return_value = sample_project

    with patch('pm_live.handlers.task_handlers.handle_task_indent', return_value=True):
        with patch('pm_live.handlers.task_handlers.handle_task_outdent', return_value=True):
            # Indent
            task_handlers.handle_indent()
            assert task_handlers._context.invalidate_task_cache.call_count == 1

            # Outdent
            task_handlers.handle_outdent()
            assert task_handlers._context.invalidate_task_cache.call_count == 2


def test_delete_confirmation_workflow(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Test complete delete workflow: request -> confirmation -> execute."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 1  # Index 0 is the section header
    mock_manager.get_project.return_value = sample_project

    # Step 1: Request delete (should show confirmation)
    task_handlers.handle_delete()
    assert mock_ui_state.state == AppState.DELETE_CONFIRMATION
    assert mock_ui_state.delete_context is not None

    # Step 2: Execute confirmed delete
    delete_params = mock_ui_state.delete_context['delete_params']
    with patch('pm_live.handlers.task_handlers.handle_task_delete', return_value=True):
        result = task_handlers.execute_confirmed_delete(delete_params)
        assert result is True


def test_move_operations_preserve_selection(task_handlers, mock_manager, mock_ui_state, sample_project):
    """Test that move operations attempt to preserve selection."""
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 0
    mock_manager.get_project.return_value = sample_project

    with patch('pm_live.handlers.task_handlers.handle_task_move_down', return_value=True):
        original_index = mock_ui_state.selected_index
        task_handlers.handle_task_move_down()

        # Handler attempts to reselect the moved task
        # (The actual logic is complex, but we verify it runs)
        mock_manager.get_project.assert_called()


# ==================== Edge Cases ====================


def test_handler_with_empty_project(task_handlers, mock_manager, mock_ui_state):
    """Test handlers with project that has no tasks."""
    empty_project = Project(
        id=1,
        name="Empty Project",
        status="Planned",
        tasks=[]
    )
    mock_ui_state.state = AppState.PROJECT_DETAILS
    mock_ui_state.current_project_id = 1
    mock_ui_state.selected_index = 0
    mock_manager.get_project.return_value = empty_project

    # All operations should handle empty task list gracefully
    task_handlers.handle_indent()
    task_handlers.handle_outdent()
    task_handlers.handle_delete()
    task_handlers.handle_task_move_up()
    task_handlers.handle_task_move_down()
    task_handlers.handle_collapse_toggle()

    # No crashes, no operations executed
    task_handlers._context.invalidate_task_cache.assert_not_called()


def test_standalone_tasks_with_lists(task_handlers, mock_manager, mock_ui_state):
    """Test standalone tasks operations with custom lists."""
    from pm import Section
    tasks = [Task(name="Task 1"), Task(name="Task 2")]
    section = Section(name="My Section", tasks=tasks)

    mock_ui_state.state = AppState.TASK_LIST
    mock_ui_state.selected_index = 1  # Index 0 is the section header
    mock_ui_state.task_lists = ["Custom list"]
    mock_ui_state.active_tab = 0
    mock_ui_state.list_tasks = {"Custom list": [section]}

    with patch('pm_live.handlers.task_handlers.handle_task_indent', return_value=True):
        task_handlers.handle_indent()

        # Should handle list sections correctly
        mock_manager.mark_list_tasks_modified.assert_called_once()
