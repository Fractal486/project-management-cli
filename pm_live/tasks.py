"""Task tree helpers used by the interactive CLI.

This module supports two task identifier styles:

1) Stable task ids (``Task.id``) used by the live UI.
2) Positional path ids (e.g. ``"2.1.3"``) used by tests and some helper flows.
"""

import logging
from typing import List, Optional, Tuple, Set
from pm import Task, Project
from .interfaces import DataManagerProtocol

logger = logging.getLogger(__name__)


def flatten_tasks(
    tasks: List[Task],
    result: list,
    depth: int = 0,
    collapsed_tasks: Set[str] = None,
) -> None:
    """Flatten a tree of tasks into a linear list with id metadata.

    ``flatten_tasks`` walks the task tree depth-first and records each
    encountered task together with its id and current indentation depth so
    that selectors and progress calculations can work with a consistent
    representation.

    Parameters
    ----------
    tasks:
        The list of tasks to flatten at the current level.
    result:
        Mutable list that will receive tuples of ``(task_id, task, depth)``.
    depth:
        Integer depth in the tree (root level is ``0``).
    collapsed_tasks:
        Set of task ids representing collapsed nodes. When an id is present,
        its descendants are skipped so they stay hidden in the UI.

    """
    if collapsed_tasks is None:
        collapsed_tasks = set()
    
    def _walk(items: List[Task], current_depth: int, parent_path: str) -> None:
        for i, task in enumerate(items, start=1):
            path_id = f"{parent_path}.{i}" if parent_path else str(i)
            result.append((path_id, task, current_depth))

            stable_id = getattr(task, "id", None)
            is_collapsed = (
                path_id in collapsed_tasks
                or (stable_id is not None and stable_id in collapsed_tasks)
            )

            subtasks_attr = getattr(task, "subtasks", None)
            if subtasks_attr and not is_collapsed:
                _walk(list(subtasks_attr), current_depth + 1, path_id)

    _walk(list(tasks), depth, "")


def collect_all_tasks(tasks: List[Task]) -> List[Task]:
    """Collect all tasks and subtasks into a flat list.

    Unlike ``flatten_tasks``, this returns just the task objects without
    id or depth metadata. Useful for aggregate statistics.

    Parameters
    ----------
    tasks:
        The list of root tasks to flatten.

    Returns
    -------
    List of all tasks including nested subtasks.
    """
    result = []
    for task in tasks:
        result.append(task)
        if hasattr(task, 'subtasks') and task.subtasks:
            result.extend(collect_all_tasks(task.subtasks))
    return result


def find_task_by_path(tasks: List[Task], path: str) -> Optional[Task]:
    """Locate a task by its positional path id (e.g. "1.2.3")."""
    if not path or not path.strip():
        return None

    parts = path.split(".")
    current = tasks
    task: Optional[Task] = None

    for part in parts:
        if not part.isdigit():
            return None
        idx = int(part) - 1
        if idx < 0 or idx >= len(current):
            return None
        task = current[idx]
        current = getattr(task, "subtasks", []) or []

    return task




def find_task_by_id(tasks: List[Task], task_id: str) -> Optional[Task]:
    """Locate a task by its stable identifier."""
    if not task_id:
        return None
    for task in tasks:
        if getattr(task, "id", None) == task_id:
            return task
        subtasks = getattr(task, "subtasks", None)
        if subtasks:
            found = find_task_by_id(subtasks, task_id)
            if found:
                return found
    return None


def get_task_parent_and_index(
    tasks: List[Task],
    path: str,
    parent: Optional[Task] = None,
) -> Tuple[Optional[Task], Optional[int], Optional[List[Task]]]:
    """Return (parent_task, index, siblings) for a positional path id."""
    if not path or not path.strip():
        return None, None, None

    parts = path.split(".")
    current = tasks
    current_parent: Optional[Task] = parent

    for depth_idx, part in enumerate(parts):
        if not part.isdigit():
            return None, None, None
        idx = int(part) - 1
        if idx < 0 or idx >= len(current):
            return None, None, None

        if depth_idx == len(parts) - 1:
            return current_parent, idx, current

        current_parent = current[idx]
        current = getattr(current_parent, "subtasks", []) or []

    return None, None, None


def get_task_parent_and_index_by_id(
    tasks: List[Task],
    task_id: str,
    parent: Optional[Task] = None,
) -> Tuple[Optional[Task], Optional[int], Optional[List[Task]]]:
    """Return the parent task, index, and sibling list for a task id."""
    if not task_id:
        return None, None, None
    for idx, task in enumerate(tasks):
        if getattr(task, "id", None) == task_id:
            return parent, idx, tasks
        subtasks = getattr(task, "subtasks", None)
        if subtasks:
            found_parent, found_idx, found_list = get_task_parent_and_index_by_id(
                subtasks,
                task_id,
                task,
            )
            if found_list is not None:
                return found_parent, found_idx, found_list
    return None, None, None


def _get_task_parent_and_index_any(
    tasks: List[Task],
    identifier: str,
) -> Tuple[Optional[Task], Optional[int], Optional[List[Task]]]:
    """Resolve either a stable task id (Task.id) or a positional path id."""
    parent, idx, siblings = get_task_parent_and_index_by_id(tasks, identifier)
    if siblings is not None:
        return parent, idx, siblings
    return get_task_parent_and_index(tasks, identifier)




def get_prev_task_at_same_or_higher_level(
    flat_tasks: List[Tuple[str, Task, int]],
    current_index: int,
) -> Optional[Tuple[str, Task, int]]:
    """Return the closest previous entry that can adopt the current task.

    Parameters
    ----------
    flat_tasks:
        Flattened task list containing ``(task_id, task, depth)`` tuples.
    current_index:
        Index of the task being inspected.

    Returns
    -------
    Optional[Tuple[str, Task, int]]
        The candidate tuple that precedes the current task and whose depth
        is less than or equal to the current depth, or ``None`` if no such
        task exists.
    """
    if current_index <= 0:
        return None
        
    current_depth = flat_tasks[current_index][2]
    
    # Look backwards to find a task at the same or higher level
    for i in range(current_index - 1, -1, -1):
        _, _, depth = flat_tasks[i]
        if depth <= current_depth:
            return flat_tasks[i]
    
    return None


def handle_task_indent(
    manager: DataManagerProtocol,
    project_id: Optional[int],
    task_id: str,
    is_standalone: bool = False,
    task_list_override: Optional[List[Task]] = None,
) -> bool:
    """Indent the task at ``task_id`` beneath the previous visible task.

    Parameters
    ----------
    manager:
        Data access object that keeps track of projects and tasks.
    project_id:
        ID of the project that owns the task.  ``None`` when operating on
        standalone tasks.
    task_id:
        Stable task identifier referencing the task to indent.
    is_standalone:
        ``True`` if we are editing standalone tasks rather than a project.
    task_list_override:
        Optional explicit task list to operate on (used for per-list task sets).

    Returns
    -------
    bool
        ``True`` when the indent succeeded, ``False`` when the operation is
        invalid (e.g., the task is already the first entry).
    """
    if is_standalone:
        task_list = manager.standalone_tasks if task_list_override is None else task_list_override
        project = None
    else:
        project = manager.get_project(project_id)
        if not project:
            return False
        task_list = project.tasks

    # Flatten the tasks to find the current task and previous task
    flat_tasks = []
    flatten_tasks(task_list, flat_tasks)
    
    # Find current task's index in the flat list
    current_index = -1
    task = None
    for i, (path_id, t, depth) in enumerate(flat_tasks):
        if path_id == task_id or getattr(t, "id", None) == task_id:
            current_index = i
            task = t
            break
    
    if current_index <= 0:  # Can't indent the first task
        return False

    # Find the previous task at the same or higher level
    prev_task_info = get_prev_task_at_same_or_higher_level(flat_tasks, current_index)
    if not prev_task_info:
        return False  # No suitable parent task found
    
    prev_task_id, prev_task, prev_depth = prev_task_info
    
    # Remove the task from its current position
    parent_task, task_idx, parent_list = _get_task_parent_and_index_any(task_list, task_id)
    if parent_list is None:
        return False
    
    # Remove the task from parent's list so it can be appended to the new parent
    removed_task = parent_list.pop(task_idx)
    
    # Add to prev_task's subtasks
    if not hasattr(prev_task, 'subtasks') or prev_task.subtasks is None:
        prev_task.subtasks = []
    prev_task.subtasks.append(removed_task)

    # Update cache and save
    if is_standalone:
        # Persist only if operating on canonical list
        if task_list is manager.standalone_tasks:
            manager.mark_standalone_tasks_modified()
            manager.save()
    else:
        manager.update_project(project)

    logger.info(
        "Indented task %s (project_id=%s, standalone=%s)",
        getattr(task, "name", task_id),
        project_id,
        is_standalone,
    )
    return True


def handle_task_outdent(
    manager: DataManagerProtocol,
    project_id: Optional[int],
    task_id: str,
    is_standalone: bool = False,
    task_list_override: Optional[List[Task]] = None,
) -> bool:
    """Move the task at ``task_id`` one level up in the hierarchy.

    Parameters
    ----------
    manager, project_id, task_id, is_standalone:
        See :func:`handle_task_indent`.
    task_list_override:
        Optional explicit task list to operate on (used for per-list task sets).

    Returns
    -------
    bool
        ``True`` when the outdent is applied, ``False`` when the task is
        already at the root level or the referenced id is invalid.
    """
    if is_standalone:
        task_list = manager.standalone_tasks if task_list_override is None else task_list_override
        project = None
    else:
        project = manager.get_project(project_id)
        if not project:
            return False
        task_list = project.tasks

    # Find the parent task and the index of this task within the parent
    parent_task, task_idx, parent_list = _get_task_parent_and_index_any(task_list, task_id)
    if parent_task is None or parent_list is None:
        return False  # Can't outdent if already at top level

    # Remove the task from its parent's subtasks
    removed_task = parent_list.pop(task_idx)
    
    # Need to find where to insert the task (after its parent in the parent's parent list)
    grandparent_task, _, grandparent_list = get_task_parent_and_index_by_id(
        task_list,
        getattr(parent_task, "id", ""),
    )
    if grandparent_list is None:
        # Fall back to positional lookup when parent ids are unavailable or task_id is positional.
        parent_positional = None
        # Recompute the positional id for the parent from the current path, if possible.
        if task_id and task_id.strip() and all(p.isdigit() for p in task_id.split(".")):
            parent_positional = ".".join(task_id.split(".")[:-1])
        if parent_positional:
            grandparent_task, _, grandparent_list = get_task_parent_and_index(task_list, parent_positional)
    
    if grandparent_list:
        # Find the position of the parent in the grandparent list
        parent_pos = -1
        for i, t in enumerate(grandparent_list):
            if t is parent_task:
                parent_pos = i
                break
        if parent_pos != -1:
            # Insert the task right after its parent so relative order is preserved
            grandparent_list.insert(parent_pos + 1, removed_task)
    else:
        # This is for the case where parent_task is a top-level task
        # Find the position of the parent in the main task list
        parent_pos = -1
        for i, t in enumerate(task_list):
            if t is parent_task:
                parent_pos = i
                break
        if parent_pos != -1:
            # Insert the task right after its parent
            task_list.insert(parent_pos + 1, removed_task)
    
    # Update cache and save
    if is_standalone:
        if task_list is manager.standalone_tasks:
            manager.mark_standalone_tasks_modified()
            manager.save()
    else:
        manager.update_project(project)

    logger.info(
        "Outdented task %s (project_id=%s, standalone=%s)",
        getattr(removed_task, "name", task_id),
        project_id,
        is_standalone,
    )
    return True


def handle_task_delete(
    manager: DataManagerProtocol,
    project_id: Optional[int],
    task_id: str,
    is_standalone: bool = False,
    task_list_override: Optional[List[Task]] = None,
) -> bool:
    """Remove the task referenced by ``task_id`` from the tree.

    Parameters
    ----------
    manager, project_id, task_id, is_standalone:
        See :func:`handle_task_indent`.
    task_list_override:
        Optional explicit task list to operate on (used for per-list task sets).

    Returns
    -------
    bool
        ``True`` when the task existed and was removed.
    """
    if is_standalone:
        task_list = manager.standalone_tasks if task_list_override is None else task_list_override
        project = None
    else:
        project = manager.get_project(project_id)
        if not project:
            return False
        task_list = project.tasks

    # Find the parent task and the index of this task within the parent
    parent_task, task_idx, parent_list = _get_task_parent_and_index_any(task_list, task_id)
    if parent_list is None:
        return False

    # Remove the task from its parent's list
    removed_task = parent_list.pop(task_idx)

    # Update cache and save
    if is_standalone:
        if task_list is manager.standalone_tasks:
            manager.mark_standalone_tasks_modified()
            manager.save()
    else:
        manager.update_project(project)

    task_name = getattr(removed_task, "name", task_id)
    logger.info(
        "Deleted task %s (task_id=%s, project_id=%s, standalone=%s)",
        task_name,
        task_id,
        project_id,
        is_standalone,
    )
    return True


def toggle_task_completion(
    manager: DataManagerProtocol,
    project_id: Optional[int],
    task_id: str,
    is_standalone: bool = False,
    task_list_override: Optional[List[Task]] = None,
    pinned_task_id: Optional[str] = None,
) -> bool:
    """Cycle the tri-state completion flag for the referenced task.

    Parameters
    ----------
    manager, project_id, task_id, is_standalone:
        See :func:`handle_task_indent`.
    task_list_override:
        Optional explicit task list to operate on (used for per-list task sets).

    Returns
    -------
    bool
        ``True`` when the task exists and the state was toggled.
    """
    if is_standalone:
        task_list = manager.standalone_tasks if task_list_override is None else task_list_override
        project = None
    else:
        project = manager.get_project(project_id)
        if not project:
            return False
        task_list = project.tasks

    task = find_task_by_id(task_list, task_id)
    if not task:
        task = find_task_by_path(task_list, task_id)
    if not task:
        return False

    # Cycle through all three states for both project and standalone tasks:
    # None -> True -> False -> None
    if task.completed is None:
        task.completed = True
    elif task.completed is True:
        task.completed = False
    else:
        task.completed = None

    # Keep pinned metadata in sync with the new status
    if pinned_task_id:
        try:
            manager.update_pinned_task_status(pinned_task_id, task.completed)
        except Exception:
            pass

    # Update cache and save
    if is_standalone:
        if task_list is manager.standalone_tasks:
            manager.mark_standalone_tasks_modified()
            manager.save()
    else:
        manager.update_project(project)

    state_label = {None: "pending", True: "complete", False: "failed"}[task.completed]
    logger.info(
        "Toggled task %s (project_id=%s, standalone=%s) -> %s",
        getattr(task, "name", task_id),
        project_id,
        is_standalone,
        state_label,
    )

    return True


def handle_task_move_up(
    manager: DataManagerProtocol,
    project_id: Optional[int],
    task_id: str,
    is_standalone: bool = False,
    task_list_override: Optional[List[Task]] = None,
) -> bool:
    """Swap the task with its previous sibling inside the same parent list.

    Parameters
    ----------
    manager, project_id, task_id, is_standalone:
        See :func:`handle_task_indent`.
    task_list_override:
        Optional explicit task list to operate on (used for per-list task sets).

    Returns
    -------
    bool
        ``True`` if the task moved, ``False`` if it was already first.
    """
    if is_standalone:
        task_list = manager.standalone_tasks if task_list_override is None else task_list_override
        project = None
    else:
        project = manager.get_project(project_id)
        if not project:
            return False
        task_list = project.tasks

    # Find the parent task and the index of this task within the parent
    parent_task, task_idx, parent_list = _get_task_parent_and_index_any(task_list, task_id)
    if parent_list is None or task_idx is None:
        return False

    # Can't move up if already at the top
    if task_idx == 0:
        return False

    # Get the task object before swapping
    task = parent_list[task_idx]

    # Swap with the previous task
    parent_list[task_idx], parent_list[task_idx - 1] = parent_list[task_idx - 1], parent_list[task_idx]

    # Update cache and save
    if is_standalone:
        if task_list is manager.standalone_tasks:
            manager.mark_standalone_tasks_modified()
            manager.save()
    else:
        manager.update_project(project)

    logger.info(
        "Moved task up %s (task_id=%s, project_id=%s, standalone=%s)",
        getattr(task, "name", task_id),
        task_id,
        project_id,
        is_standalone,
    )
    return True


def handle_task_move_down(
    manager: DataManagerProtocol,
    project_id: Optional[int],
    task_id: str,
    is_standalone: bool = False,
    task_list_override: Optional[List[Task]] = None,
) -> bool:
    """Swap the task with its next sibling inside the same parent list.

    Parameters
    ----------
    manager, project_id, task_id, is_standalone:
        See :func:`handle_task_indent`.
    task_list_override:
        Optional explicit task list to operate on (used for per-list task sets).

    Returns
    -------
    bool
        ``True`` if the task moved, ``False`` if it was already last.
    """
    if is_standalone:
        task_list = manager.standalone_tasks if task_list_override is None else task_list_override
        project = None
    else:
        project = manager.get_project(project_id)
        if not project:
            return False
        task_list = project.tasks

    # Find the parent task and the index of this task within the parent
    parent_task, task_idx, parent_list = _get_task_parent_and_index_any(task_list, task_id)
    if parent_list is None or task_idx is None:
        return False

    # Can't move down if already at the bottom
    if task_idx >= len(parent_list) - 1:
        return False

    # Get the task object before swapping
    task = parent_list[task_idx]

    # Swap with the next task
    parent_list[task_idx], parent_list[task_idx + 1] = parent_list[task_idx + 1], parent_list[task_idx]

    # Update cache and save
    if is_standalone:
        if task_list is manager.standalone_tasks:
            manager.mark_standalone_tasks_modified()
            manager.save()
    else:
        manager.update_project(project)

    logger.info(
        "Moved task down %s (task_id=%s, project_id=%s, standalone=%s)",
        getattr(task, "name", task_id),
        task_id,
        project_id,
        is_standalone,
    )
    return True

