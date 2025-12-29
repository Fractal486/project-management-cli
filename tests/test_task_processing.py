"""Tests for task processing and tree manipulation (pm_live/tasks.py)."""

import pytest
from unittest.mock import Mock, MagicMock
from typing import List

from pm import Task, Project
from pm_live.tasks import (
    flatten_tasks,
    find_task_by_path,
    get_task_parent_and_index,
    get_prev_task_at_same_or_higher_level,
    handle_task_indent,
    handle_task_outdent,
    handle_task_delete,
    toggle_task_completion,
    handle_task_move_up,
    handle_task_move_down,
)


# ==================== Fixtures ====================


@pytest.fixture
def simple_tasks():
    """Create a simple flat list of tasks."""
    return [
        Task(name="Task 1"),
        Task(name="Task 2"),
        Task(name="Task 3"),
    ]


@pytest.fixture
def nested_tasks():
    """Create a nested task structure.

    Structure:
    1. Design
       1.1. Wireframes
       1.2. Mockups
    2. Build
       2.1. Backend
           2.1.1. API
           2.1.2. Database
       2.2. Frontend
    3. Test
    """
    return [
        Task(name="Design", subtasks=[
            Task(name="Wireframes"),
            Task(name="Mockups"),
        ]),
        Task(name="Build", subtasks=[
            Task(name="Backend", subtasks=[
                Task(name="API"),
                Task(name="Database"),
            ]),
            Task(name="Frontend"),
        ]),
        Task(name="Test"),
    ]


@pytest.fixture
def tasks_with_completion():
    """Create tasks with various completion states."""
    return [
        Task(name="Not started", completed=None),
        Task(name="Completed", completed=True),
        Task(name="Failed", completed=False),
        Task(name="Parent", completed=None, subtasks=[
            Task(name="Child completed", completed=True),
            Task(name="Child not started", completed=None),
        ]),
    ]


@pytest.fixture
def tasks_with_priority():
    """Create tasks with various priorities."""
    return [
        Task(name="High priority", priority="High"),
        Task(name="Medium priority", priority="Medium"),
        Task(name="Low priority", priority="Low"),
        Task(name="No priority", priority=None),
    ]


@pytest.fixture
def mock_manager():
    """Create a mock DataManagerProtocol."""
    manager = Mock()
    manager.standalone_tasks = []
    manager.save = Mock()
    manager.mark_standalone_tasks_modified = Mock()
    manager.update_project = Mock()
    manager.get_project = Mock()
    return manager


@pytest.fixture
def mock_project():
    """Create a mock project with tasks."""
    project = Project(
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
    return project


# ==================== Task Flattening Tests ====================


def test_flatten_tasks_empty_list():
    """Flatten empty task list should return empty result."""
    result = []
    flatten_tasks([], result)
    assert result == []


def test_flatten_tasks_flat_list(simple_tasks):
    """Flatten a flat list of tasks."""
    result = []
    flatten_tasks(simple_tasks, result)

    assert len(result) == 3
    assert result[0] == ("1", simple_tasks[0], 0)
    assert result[1] == ("2", simple_tasks[1], 0)
    assert result[2] == ("3", simple_tasks[2], 0)


def test_flatten_tasks_single_level_nesting():
    """Flatten tasks with one level of nesting."""
    tasks = [
        Task(name="Parent", subtasks=[
            Task(name="Child 1"),
            Task(name="Child 2"),
        ]),
    ]

    result = []
    flatten_tasks(tasks, result)

    assert len(result) == 3
    assert result[0] == ("1", tasks[0], 0)
    assert result[1] == ("1.1", tasks[0].subtasks[0], 1)
    assert result[2] == ("1.2", tasks[0].subtasks[1], 1)


def test_flatten_tasks_deep_nesting(nested_tasks):
    """Flatten tasks with multiple levels of nesting."""
    result = []
    flatten_tasks(nested_tasks, result)

    # Should have 9 tasks total (3 top + 2 design + 3 build (1 backend parent + 2 backend children + 1 frontend))
    assert len(result) == 9

    # Check top-level paths
    assert result[0][0] == "1"  # Design
    assert result[0][2] == 0    # depth 0

    # Check nested paths
    assert result[1][0] == "1.1"  # Wireframes
    assert result[1][2] == 1      # depth 1
    assert result[2][0] == "1.2"  # Mockups

    # Check deeply nested
    assert result[4][0] == "2.1"    # Backend
    assert result[5][0] == "2.1.1"  # API
    assert result[5][2] == 2        # depth 2
    assert result[6][0] == "2.1.2"  # Database


def test_flatten_tasks_preserve_order(nested_tasks):
    """Flattening should preserve task order."""
    result = []
    flatten_tasks(nested_tasks, result)

    # Verify names appear in depth-first order
    names = [task.name for _, task, _ in result]
    assert names == [
        "Design", "Wireframes", "Mockups",
        "Build", "Backend", "API", "Database", "Frontend",
        "Test"
    ]


def test_flatten_tasks_with_collapsed():
    """Flattening with collapsed tasks should skip their subtasks."""
    tasks = [
        Task(name="Task 1", subtasks=[
            Task(name="Task 1.1"),
            Task(name="Task 1.2"),
        ]),
        Task(name="Task 2", subtasks=[
            Task(name="Task 2.1"),
        ]),
    ]

    # Collapse "1" - should hide 1.1 and 1.2
    collapsed = {"1"}
    result = []
    flatten_tasks(tasks, result, collapsed_tasks=collapsed)

    # Should only have Task 1, Task 2, and Task 2.1 (Task 1's children are hidden)
    assert len(result) == 3
    assert result[0][0] == "1"    # Task 1
    assert result[1][0] == "2"    # Task 2
    assert result[2][0] == "2.1"  # Task 2.1


def test_flatten_tasks_with_indentation():
    """Flattening should track correct indentation depth."""
    tasks = [
        Task(name="Level 0", subtasks=[
            Task(name="Level 1", subtasks=[
                Task(name="Level 2", subtasks=[
                    Task(name="Level 3"),
                ]),
            ]),
        ]),
    ]

    result = []
    flatten_tasks(tasks, result)

    assert result[0][2] == 0  # Level 0
    assert result[1][2] == 1  # Level 1
    assert result[2][2] == 2  # Level 2
    assert result[3][2] == 3  # Level 3


# ==================== Find Task by Path Tests ====================


def test_find_task_by_path_empty_path(simple_tasks):
    """Empty path should return None."""
    task = find_task_by_path(simple_tasks, "")
    assert task is None


def test_find_task_by_path_root_level(simple_tasks):
    """Find task at root level."""
    task = find_task_by_path(simple_tasks, "1")
    assert task == simple_tasks[0]

    task = find_task_by_path(simple_tasks, "2")
    assert task == simple_tasks[1]

    task = find_task_by_path(simple_tasks, "3")
    assert task == simple_tasks[2]


def test_find_task_by_path_nested(nested_tasks):
    """Find task in nested structure."""
    # Find top-level task
    task = find_task_by_path(nested_tasks, "1")
    assert task.name == "Design"

    # Find first-level nested task
    task = find_task_by_path(nested_tasks, "1.1")
    assert task.name == "Wireframes"

    # Find deeply nested task
    task = find_task_by_path(nested_tasks, "2.1.1")
    assert task.name == "API"

    task = find_task_by_path(nested_tasks, "2.1.2")
    assert task.name == "Database"


def test_find_task_by_path_invalid_path(simple_tasks):
    """Invalid paths should return None."""
    # Out of bounds
    assert find_task_by_path(simple_tasks, "10") is None

    # Negative index (0-based would be -1, but path uses 1-based)
    assert find_task_by_path(simple_tasks, "0") is None

    # Invalid format
    assert find_task_by_path(simple_tasks, "abc") is None

    # Path to non-existent subtask
    assert find_task_by_path(simple_tasks, "1.1") is None


def test_find_task_by_path_partial_invalid(nested_tasks):
    """Path that's valid partway but then invalid should return None."""
    # "1" exists but "1.10" doesn't
    assert find_task_by_path(nested_tasks, "1.10") is None

    # "2.1" exists but "2.1.10" doesn't
    assert find_task_by_path(nested_tasks, "2.1.10") is None


# ==================== Get Task Parent and Index Tests ====================


def test_get_task_parent_and_index_empty_path(simple_tasks):
    """Empty path should return None."""
    parent, idx, siblings = get_task_parent_and_index(simple_tasks, "")
    assert parent is None
    assert idx is None
    assert siblings is None


def test_get_task_parent_and_index_root_level(simple_tasks):
    """Get parent and index for root-level task."""
    parent, idx, siblings = get_task_parent_and_index(simple_tasks, "1")
    assert parent is None  # Root tasks have no parent
    assert idx == 0
    assert siblings == simple_tasks

    parent, idx, siblings = get_task_parent_and_index(simple_tasks, "2")
    assert parent is None
    assert idx == 1
    assert siblings == simple_tasks


def test_get_task_parent_and_index_nested(nested_tasks):
    """Get parent and index for nested task."""
    # First-level subtask
    parent, idx, siblings = get_task_parent_and_index(nested_tasks, "1.1")
    assert parent == nested_tasks[0]  # Design
    assert idx == 0
    assert siblings == nested_tasks[0].subtasks

    # Deeply nested task
    parent, idx, siblings = get_task_parent_and_index(nested_tasks, "2.1.1")
    assert parent.name == "Backend"
    assert idx == 0
    assert len(siblings) == 2  # API and Database


def test_get_task_parent_and_index_invalid_path(simple_tasks):
    """Invalid path should return None values."""
    parent, idx, siblings = get_task_parent_and_index(simple_tasks, "10")
    assert parent is None
    assert idx is None
    assert siblings is None


# ==================== Get Previous Task at Same or Higher Level Tests ====================


def test_get_prev_task_at_same_or_higher_level_first_task():
    """First task has no previous task."""
    flat_tasks = [
        ("1", Task(name="Task 1"), 0),
        ("2", Task(name="Task 2"), 0),
    ]

    result = get_prev_task_at_same_or_higher_level(flat_tasks, 0)
    assert result is None


def test_get_prev_task_at_same_or_higher_level_same_level():
    """Find previous task at same level."""
    flat_tasks = [
        ("1", Task(name="Task 1"), 0),
        ("2", Task(name="Task 2"), 0),
        ("3", Task(name="Task 3"), 0),
    ]

    result = get_prev_task_at_same_or_higher_level(flat_tasks, 1)
    assert result == flat_tasks[0]

    result = get_prev_task_at_same_or_higher_level(flat_tasks, 2)
    assert result == flat_tasks[1]


def test_get_prev_task_at_same_or_higher_level_from_nested():
    """Find previous task when coming from nested level."""
    flat_tasks = [
        ("1", Task(name="Task 1"), 0),
        ("1.1", Task(name="Task 1.1"), 1),
        ("1.2", Task(name="Task 1.2"), 1),
        ("2", Task(name="Task 2"), 0),
    ]

    # From 1.1, previous at same/higher is 1
    result = get_prev_task_at_same_or_higher_level(flat_tasks, 1)
    assert result == flat_tasks[0]

    # From 1.2, previous at same level is 1.1
    result = get_prev_task_at_same_or_higher_level(flat_tasks, 2)
    assert result == flat_tasks[1]

    # From 2, previous at same level is 1
    result = get_prev_task_at_same_or_higher_level(flat_tasks, 3)
    assert result == flat_tasks[0]


def test_get_prev_task_at_same_or_higher_level_skip_deeper():
    """Should skip over tasks at deeper levels."""
    flat_tasks = [
        ("1", Task(name="Task 1"), 0),
        ("1.1", Task(name="Task 1.1"), 1),
        ("1.1.1", Task(name="Task 1.1.1"), 2),
        ("1.2", Task(name="Task 1.2"), 1),
    ]

    # From 1.2 (depth 1), should find 1.1 (depth 1), skipping 1.1.1 (depth 2)
    result = get_prev_task_at_same_or_higher_level(flat_tasks, 3)
    assert result == flat_tasks[1]  # 1.1


# ==================== Task Handler Tests ====================
# These tests use mocks for DataManagerProtocol


def test_toggle_task_completion_cycle(mock_manager):
    """Test that toggle_task_completion cycles through None -> True -> False -> None."""
    tasks = [Task(name="Task 1", completed=None)]
    mock_manager.standalone_tasks = tasks

    # None -> True
    result = toggle_task_completion(mock_manager, None, "1", is_standalone=True)
    assert result is True
    assert tasks[0].completed is True

    # True -> False
    result = toggle_task_completion(mock_manager, None, "1", is_standalone=True)
    assert result is True
    assert tasks[0].completed is False

    # False -> None
    result = toggle_task_completion(mock_manager, None, "1", is_standalone=True)
    assert result is True
    assert tasks[0].completed is None


def test_toggle_task_completion_invalid_path(mock_manager):
    """Toggle with invalid path should return False."""
    mock_manager.standalone_tasks = [Task(name="Task 1")]

    result = toggle_task_completion(mock_manager, None, "10", is_standalone=True)
    assert result is False


def test_handle_task_delete_root_level(mock_manager):
    """Delete a root-level task."""
    tasks = [
        Task(name="Task 1"),
        Task(name="Task 2"),
        Task(name="Task 3"),
    ]
    mock_manager.standalone_tasks = tasks

    result = handle_task_delete(mock_manager, None, "2", is_standalone=True)
    assert result is True
    assert len(tasks) == 2
    assert tasks[0].name == "Task 1"
    assert tasks[1].name == "Task 3"


def test_handle_task_delete_with_subtasks(mock_manager):
    """Deleting a task should also delete its subtasks."""
    tasks = [
        Task(name="Parent", subtasks=[
            Task(name="Child 1"),
            Task(name="Child 2"),
        ]),
    ]
    mock_manager.standalone_tasks = tasks

    # Delete the parent
    result = handle_task_delete(mock_manager, None, "1", is_standalone=True)
    assert result is True
    assert len(tasks) == 0


def test_handle_task_delete_nested(mock_manager):
    """Delete a nested task."""
    tasks = [
        Task(name="Parent", subtasks=[
            Task(name="Child 1"),
            Task(name="Child 2"),
        ]),
    ]
    mock_manager.standalone_tasks = tasks

    # Delete Child 1
    result = handle_task_delete(mock_manager, None, "1.1", is_standalone=True)
    assert result is True
    assert len(tasks[0].subtasks) == 1
    assert tasks[0].subtasks[0].name == "Child 2"


def test_handle_task_delete_invalid_path(mock_manager):
    """Delete with invalid path should return False."""
    mock_manager.standalone_tasks = [Task(name="Task 1")]

    result = handle_task_delete(mock_manager, None, "10", is_standalone=True)
    assert result is False


def test_handle_task_move_up_success(mock_manager):
    """Move a task up in the list."""
    tasks = [
        Task(name="Task 1"),
        Task(name="Task 2"),
        Task(name="Task 3"),
    ]
    mock_manager.standalone_tasks = tasks

    # Move Task 2 up
    result = handle_task_move_up(mock_manager, None, "2", is_standalone=True)
    assert result is True
    assert tasks[0].name == "Task 2"
    assert tasks[1].name == "Task 1"
    assert tasks[2].name == "Task 3"


def test_handle_task_move_up_first_task(mock_manager):
    """Cannot move first task up."""
    tasks = [
        Task(name="Task 1"),
        Task(name="Task 2"),
    ]
    mock_manager.standalone_tasks = tasks

    result = handle_task_move_up(mock_manager, None, "1", is_standalone=True)
    assert result is False
    assert tasks[0].name == "Task 1"  # Unchanged


def test_handle_task_move_down_success(mock_manager):
    """Move a task down in the list."""
    tasks = [
        Task(name="Task 1"),
        Task(name="Task 2"),
        Task(name="Task 3"),
    ]
    mock_manager.standalone_tasks = tasks

    # Move Task 2 down
    result = handle_task_move_down(mock_manager, None, "2", is_standalone=True)
    assert result is True
    assert tasks[0].name == "Task 1"
    assert tasks[1].name == "Task 3"
    assert tasks[2].name == "Task 2"


def test_handle_task_move_down_last_task(mock_manager):
    """Cannot move last task down."""
    tasks = [
        Task(name="Task 1"),
        Task(name="Task 2"),
    ]
    mock_manager.standalone_tasks = tasks

    result = handle_task_move_down(mock_manager, None, "2", is_standalone=True)
    assert result is False
    assert tasks[1].name == "Task 2"  # Unchanged


def test_handle_task_indent_success(mock_manager):
    """Indent a task to make it a subtask of the previous task."""
    tasks = [
        Task(name="Task 1"),
        Task(name="Task 2"),
    ]
    mock_manager.standalone_tasks = tasks

    # Indent Task 2 under Task 1
    result = handle_task_indent(mock_manager, None, "2", is_standalone=True)
    assert result is True
    assert len(tasks) == 1
    assert tasks[0].name == "Task 1"
    assert len(tasks[0].subtasks) == 1
    assert tasks[0].subtasks[0].name == "Task 2"


def test_handle_task_indent_first_task(mock_manager):
    """Cannot indent the first task."""
    tasks = [
        Task(name="Task 1"),
        Task(name="Task 2"),
    ]
    mock_manager.standalone_tasks = tasks

    result = handle_task_indent(mock_manager, None, "1", is_standalone=True)
    assert result is False
    assert len(tasks) == 2  # Unchanged


def test_handle_task_outdent_success(mock_manager):
    """Outdent a subtask to make it a sibling of its parent."""
    tasks = [
        Task(name="Task 1", subtasks=[
            Task(name="Task 1.1"),
        ]),
        Task(name="Task 2"),
    ]
    mock_manager.standalone_tasks = tasks

    # Outdent Task 1.1
    result = handle_task_outdent(mock_manager, None, "1.1", is_standalone=True)
    assert result is True
    assert len(tasks) == 3
    assert tasks[0].name == "Task 1"
    assert len(tasks[0].subtasks) == 0
    assert tasks[1].name == "Task 1.1"  # Now a root-level task after Task 1
    assert tasks[2].name == "Task 2"


def test_handle_task_outdent_root_level(mock_manager):
    """Cannot outdent a root-level task."""
    tasks = [
        Task(name="Task 1"),
        Task(name="Task 2"),
    ]
    mock_manager.standalone_tasks = tasks

    result = handle_task_outdent(mock_manager, None, "1", is_standalone=True)
    assert result is False
    assert len(tasks) == 2  # Unchanged


def test_handle_task_outdent_preserves_position(mock_manager):
    """Outdenting should place task after its parent."""
    tasks = [
        Task(name="Task 1", subtasks=[
            Task(name="Task 1.1"),
            Task(name="Task 1.2"),
        ]),
        Task(name="Task 2"),
    ]
    mock_manager.standalone_tasks = tasks

    # Outdent Task 1.2
    result = handle_task_outdent(mock_manager, None, "1.2", is_standalone=True)
    assert result is True
    assert len(tasks) == 3
    assert tasks[0].name == "Task 1"
    assert tasks[1].name == "Task 1.2"  # Placed after its former parent
    assert tasks[2].name == "Task 2"
    assert len(tasks[0].subtasks) == 1
    assert tasks[0].subtasks[0].name == "Task 1.1"


# ==================== Integration Tests with Projects ====================


def test_task_operations_with_project(mock_manager, mock_project):
    """Test task operations work with projects."""
    mock_manager.get_project = Mock(return_value=mock_project)

    # Toggle completion on a project task
    result = toggle_task_completion(mock_manager, 1, "1", is_standalone=False)
    assert result is True
    assert mock_project.tasks[0].completed is True

    # Verify update_project was called
    mock_manager.update_project.assert_called_with(mock_project)


def test_task_operations_project_not_found(mock_manager):
    """Task operations should fail if project not found."""
    mock_manager.get_project = Mock(return_value=None)

    result = toggle_task_completion(mock_manager, 999, "1", is_standalone=False)
    assert result is False


def test_task_list_override(mock_manager):
    """Test that task_list_override parameter works."""
    # Create custom task list
    custom_tasks = [
        Task(name="Custom 1"),
        Task(name="Custom 2"),
    ]

    # Toggle on custom list (not manager.standalone_tasks)
    result = toggle_task_completion(
        mock_manager, None, "1", is_standalone=True, task_list_override=custom_tasks
    )
    assert result is True
    assert custom_tasks[0].completed is True

    # save() should not be called since we're using override
    mock_manager.save.assert_not_called()
