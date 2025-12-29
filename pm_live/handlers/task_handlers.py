"""Task operation handlers for the live CLI."""

import logging

from ..interfaces import HandlerContext
from ..tasks import (
    flatten_tasks,
    handle_task_indent, handle_task_outdent, handle_task_delete,
    handle_task_move_up, handle_task_move_down,
    get_task_parent_and_index_by_id
)
from ..states import AppState
from ..utils import validate_task_name

PRIORITY_CYCLE = ["none", "!", "!!", "!!!"]

logger = logging.getLogger(__name__)


class TaskHandlers:
    """Handles task-related operations."""

    def __init__(self, context: HandlerContext):
        """Initialize with shared handler context."""
        self._context = context
        self.manager = context.manager
        self.ui_state = context.ui_state
        self._get_flat_tasks = context.get_flat_tasks
        self._invalidate_task_cache = context.invalidate_task_cache
        self._persist_collapsed_tasks = context.persist_collapsed_tasks
        self._operation_section_list = None

    def _clear_inline_edit_state(self):
        """Reset inline edit tracking state."""
        self.ui_state.inline_task_edit_mode = False
        self.ui_state.inline_edit_task_id = None
        self.ui_state.inline_edit_task = None
        self.ui_state.inline_edit_origin = None
        self.ui_state.inline_edit_list_name = None
        self.ui_state.inline_edit_project_id = None
        self.ui_state.inline_edit_field_index = 0
        self.ui_state.inline_edit_deadline_component = 0
        self.ui_state.inline_edit_name = ""
        self.ui_state.inline_edit_name_cursor = 0
        self.ui_state.inline_edit_deadline = None
        self.ui_state.inline_edit_priority = "none"
        self.ui_state.inline_edit_notes = None
        self.ui_state.inline_edit_notes_cursor = 0
        self.ui_state.inline_edit_original = {}

    def begin_inline_edit(self):
        """Enter inline edit mode for the currently selected task."""
        # Don't start if already editing something else
        if self.ui_state.inline_task_edit_mode:
            return

        selected_flat = self._get_selected_flat_task()
        if not selected_flat:
            return

        task_id, task, depth = selected_flat

        # Determine origin
        origin = "project" if self.ui_state.state == AppState.PROJECT_DETAILS else "task_list"
        list_name = None
        if origin == "task_list":
            task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
            active_tab = getattr(self.ui_state, "active_tab", 0)
            list_name = task_lists[active_tab] if 0 <= active_tab < len(task_lists) else "Tasks"

        priority_value = getattr(task, "priority", None)
        if priority_value not in PRIORITY_CYCLE or priority_value is None:
            priority_value = "none"

        self.ui_state.inline_task_edit_mode = True
        self.ui_state.inline_edit_task_id = getattr(task, "id", None)
        self.ui_state.inline_edit_task = task
        self.ui_state.inline_edit_origin = origin
        self.ui_state.inline_edit_list_name = list_name
        self.ui_state.inline_edit_project_id = self.ui_state.current_project_id
        self.ui_state.inline_edit_field_index = 0  # Start on name
        self.ui_state.inline_edit_deadline_component = 0
        self.ui_state.inline_edit_name = task.name or ""
        self.ui_state.inline_edit_name_cursor = len(self.ui_state.inline_edit_name)
        self.ui_state.inline_edit_deadline = getattr(task, "deadline", None) or None
        self.ui_state.inline_edit_priority = priority_value
        self.ui_state.inline_edit_notes = getattr(task, "notes", None) or None
        self.ui_state.inline_edit_notes_cursor = len(self.ui_state.inline_edit_notes or "")
        self.ui_state.inline_edit_original = {
            "name": task.name,
            "deadline": getattr(task, "deadline", None),
            "priority": getattr(task, "priority", None),
            "notes": getattr(task, "notes", None),
        }
        # Ensure inline text buffer is not in use simultaneously
        self.ui_state.inline_input_mode = False
        self.ui_state.text_input_buffer = ""

    def cancel_inline_edit(self):
        """Exit inline edit mode without persisting edits."""
        task = getattr(self.ui_state, "inline_edit_task", None)
        origin = getattr(self.ui_state, "inline_edit_origin", None)
        task_id = getattr(self.ui_state, "inline_edit_task_id", None)

        # For calendar tasks, check if it's new by looking at the original task name
        # New tasks are created with empty names
        if origin == "calendar" and task is not None:
            is_new_task = not getattr(task, "name", "")
        else:
            is_new_task = task_id is None and task is not None

        if is_new_task:
            # Remove the in-flight unsaved task from its container so cancel truly discards it.
            try:
                if origin == "project":
                    project = self.manager.get_project(self.ui_state.inline_edit_project_id)
                    if project and task in getattr(project, "tasks", []):
                        project.tasks.remove(task)
                elif origin == "calendar" or origin == "task_list":
                    list_name = getattr(self.ui_state, "inline_edit_list_name", None) or "Tasks"
                    # Prefer ui_state.list_tasks (live structure), fall back to manager.list_tasks/standalone_tasks.
                    list_tasks_map = getattr(self.ui_state, "list_tasks", None) or getattr(self.manager, "list_tasks", {})
                    sections = list_tasks_map.get(list_name)
                    
                    # If not in list_tasks_map, maybe it's in standalone_tasks (legacy)
                    if sections is None and list_name == "Tasks":
                        sections = getattr(self.manager, "standalone_tasks", [])

                    if sections:
                        # Legacy flat list (no sections)
                        if isinstance(sections, list) and sections and not isinstance(sections[0], dict) and not hasattr(sections[0], "name"):
                            try:
                                sections.remove(task)
                            except ValueError:
                                pass
                        else:
                            # Sections structure (list of Section objects or dicts)
                            for section in sections:
                                section_tasks = section.tasks if hasattr(section, "tasks") else section.get("tasks", [])
                                if task in section_tasks:
                                    section_tasks.remove(task)
                                    break
                else:
                    # Generic fallback for other origins
                    list_tasks_map = getattr(self.ui_state, "list_tasks", None) or getattr(self.manager, "list_tasks", {})
                    found = False
                    for sections in list_tasks_map.values():
                        for section in sections:
                            section_tasks = section.tasks if hasattr(section, "tasks") else section.get("tasks", [])
                            if task in section_tasks:
                                section_tasks.remove(task)
                                found = True
                                break
                        if found:
                            break
            except Exception:
                # Best-effort removal; still proceed to clear state/cache.
                pass

        self._clear_inline_edit_state()
        self._invalidate_task_cache()

    def commit_inline_edit(self):
        """Persist inline edits to the target task."""
        if not self.ui_state.inline_task_edit_mode or not self.ui_state.inline_edit_task:
            self._clear_inline_edit_state()
            return True

        task = self.ui_state.inline_edit_task
        name_valid, cleaned_name = validate_task_name(self.ui_state.inline_edit_name)
        if not name_valid:
            # Keep the user in edit mode but surface the validation error
            try:
                self._context.show_status(cleaned_name, True)
            except Exception:
                pass
            return True

        # Apply edits to the task object
        task.name = cleaned_name
        task.deadline = self.ui_state.inline_edit_deadline
        task.priority = None if self.ui_state.inline_edit_priority == "none" else self.ui_state.inline_edit_priority
        task.notes = self.ui_state.inline_edit_notes

        origin = self.ui_state.inline_edit_origin
        if origin == "project":
            project = self.manager.get_project(self.ui_state.inline_edit_project_id)
            if project:
                self.manager.update_project(project)
        else:
            # Standalone tasks (per-list task sets)
            try:
                self.manager.mark_list_tasks_modified()
                self.manager.save()
            except Exception:
                # Fallback to standalone dirty flag if list tracking is unavailable
                try:
                    self.manager.mark_standalone_tasks_modified()
                    self.manager.save()
                except Exception:
                    pass

        # Sync pinned metadata to reflect the changes
        try:
            self.manager.refresh_pinned_metadata()
            self.manager.save()
        except Exception:
            pass

        self._invalidate_task_cache()
        self._clear_inline_edit_state()
        return True

    def _get_task_list_override_for_list(self, selected_task=None, selected_task_id: str = None):
        """Get a flattened list of all tasks in the current list, preserving section isolation.

        After task operations, we update the sections with the modified task list.
        """
        # Allow lookup while in the delete confirmation dialog so task deletes still
        # operate on the correct list/section after the state switch.
        if self.ui_state.state not in (AppState.TASK_LIST, AppState.DELETE_CONFIRMATION):
            return None

        # Store a reference to the sections so we can update them after operations
        task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
        active_tab = getattr(self.ui_state, "active_tab", 0)
        active_list_name = task_lists[active_tab] if 0 <= active_tab < len(task_lists) else "Tasks"
        list_tasks_map = getattr(self.ui_state, "list_tasks", {"Tasks": self.manager.standalone_tasks})
        sections_for_list = list_tasks_map.get(active_list_name, [])

        # Store sections for later update
        self._current_list_sections = sections_for_list
        self._current_list_name = active_list_name
        self._operation_section_list = None

        if not sections_for_list:
            return None

        # Old format: direct list of tasks
        if sections_for_list and not isinstance(sections_for_list[0], dict) and not hasattr(sections_for_list[0], 'name'):
            self._operation_section_list = sections_for_list
            return sections_for_list

        def task_in_tree(task_list, target, use_identity=True):
            for item in task_list:
                if use_identity:
                    if item is target:
                        return True
                elif item == target:
                    return True
                
                if getattr(item, "subtasks", None):
                    if task_in_tree(item.subtasks, target, use_identity):
                        return True
            return False

        # Try to locate the section containing the selected task by identity
        if selected_task is not None:
            # First pass: check by identity (strongest match)
            for section in sections_for_list:
                section_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])
                if task_in_tree(section_tasks, selected_task, use_identity=True):
                    self._operation_section_list = section_tasks
                    logger.debug("Found task list by identity in section: %s", getattr(section, 'name', 'unknown'))
                    return section_tasks

            # Second pass: check by equality (fallback if objects were recreated/copied)
            for section in sections_for_list:
                section_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])
                if task_in_tree(section_tasks, selected_task, use_identity=False):
                    self._operation_section_list = section_tasks
                    logger.debug("Found task list by equality in section: %s", getattr(section, 'name', 'unknown'))
                    return section_tasks

        # Fallback: try to resolve by matching the selected id within each section
        if selected_task_id:
            logger.warning(
                "Task lookup by identity/equality failed for id %s. Falling back to id match.",
                selected_task_id,
            )

            for section in sections_for_list:
                section_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])
                parent, _, parent_list = get_task_parent_and_index_by_id(section_tasks, selected_task_id)

                if parent_list is not None:
                    self._operation_section_list = section_tasks
                    return section_tasks

        # Final fallback: operate on the first section's task list (if present)
        first_section = sections_for_list[0]
        section_tasks = first_section.tasks if hasattr(first_section, 'tasks') else first_section.get('tasks', [])
        self._operation_section_list = section_tasks
        return section_tasks

    def _update_list_sections_after_operation(self):
        """After task operations, reconstruct sections with the modified task list."""
        if self._operation_section_list is not None:
            self._operation_section_list = None
            return

        if not hasattr(self, '_current_list_sections') or not hasattr(self, '_current_list_name'):
            return

        # Get the flattened list that was modified by the operation
        task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
        active_tab = getattr(self.ui_state, "active_tab", 0)
        active_list_name = task_lists[active_tab] if 0 <= active_tab < len(task_lists) else "Tasks"
        list_tasks_map = getattr(self.ui_state, "list_tasks", {"Tasks": self.manager.standalone_tasks})
        sections_for_list = list_tasks_map.get(active_list_name, [])

        # Collect all modified tasks from all sections
        modified_all_tasks = []
        for section in sections_for_list:
            section_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])
            modified_all_tasks.extend(section_tasks)

        # For now, keep all tasks in the first section (preserves structure but may consolidate across sections)
        # This ensures task operations don't lose tasks across section boundaries
        if sections_for_list and modified_all_tasks:
            if hasattr(sections_for_list[0], 'tasks'):
                sections_for_list[0].tasks = modified_all_tasks
            else:
                sections_for_list[0]['tasks'] = modified_all_tasks

    def handle_indent(self):
        """Handle task indentation."""
        selected_flat_task = self._get_selected_flat_task()
        if not selected_flat_task:
            return

        task_id, task, current_depth = selected_flat_task
        is_standalone = self.ui_state.state == AppState.TASK_LIST

        # Get flattened task list from current list (sections flattened into one list)
        task_list_override = self._get_task_list_override_for_list(
            selected_task=task,
            selected_task_id=getattr(task, "id", ""),
        )

        success = handle_task_indent(
            self.manager,
            self.ui_state.current_project_id,
            getattr(task, "id", ""),
            is_standalone,
            task_list_override=task_list_override
        )

        if success:
            # Update sections after operation
            self._update_list_sections_after_operation()
            # Mark per-list tasks modified when operating in standalone task lists
            if is_standalone:
                try:
                    self.manager.mark_list_tasks_modified()
                    self.manager.save()
                except Exception:
                    pass
            self._invalidate_task_cache()
            logger.info(
                "Task indented via handler (task_id=%s, standalone=%s)",
                getattr(task, "id", ""),
                is_standalone,
            )
        else:
            logger.debug(
                "Task indent failed via handler (task_id=%s, standalone=%s)",
                getattr(task, "id", ""),
                is_standalone,
            )

    def handle_outdent(self):
        """Handle task outdentation."""
        selected_flat_task = self._get_selected_flat_task()
        if not selected_flat_task:
            return

        task_id, task, current_depth = selected_flat_task
        is_standalone = self.ui_state.state == AppState.TASK_LIST

        # Get flattened task list from current list (sections flattened into one list)
        task_list_override = self._get_task_list_override_for_list(
            selected_task=task,
            selected_task_id=getattr(task, "id", ""),
        )

        success = handle_task_outdent(
            self.manager,
            self.ui_state.current_project_id,
            getattr(task, "id", ""),
            is_standalone,
            task_list_override=task_list_override
        )

        if success:
            # Update sections after operation
            self._update_list_sections_after_operation()
            # Mark per-list tasks modified when operating in standalone task lists
            if is_standalone:
                try:
                    self.manager.mark_list_tasks_modified()
                    self.manager.save()
                except Exception:
                    pass
            self._invalidate_task_cache()
            logger.info(
                "Task outdented via handler (task_id=%s, standalone=%s)",
                getattr(task, "id", ""),
                is_standalone,
            )
        else:
            logger.debug(
                "Task outdent failed via handler (task_id=%s, standalone=%s)",
                getattr(task, "id", ""),
                is_standalone,
            )

    def handle_delete(self):
        """Handle task deletion - skip confirmation for completed tasks."""
        selected_flat_task = self._get_selected_flat_task()
        if not selected_flat_task:
            return

        task_id, task, current_depth = selected_flat_task
        is_standalone = self.ui_state.state == AppState.TASK_LIST

        # Check if task is completed - if so, delete directly without confirmation
        if task.completed is not None:
            delete_params = {
                'task_id': getattr(task, "id", ""),
                'task': task,
                'is_standalone': is_standalone,
                'current_project_id': self.ui_state.current_project_id
            }
            self.execute_confirmed_delete(delete_params)
            return

        # For pending tasks, show confirmation dialog
        self.ui_state.delete_context = {
            'delete_type': 'task',
            'previous_state': self.ui_state.state,
            'previous_selected_index': self.ui_state.selected_index,
            'delete_params': {
                'task_id': getattr(task, "id", ""),
                'task': task,
                'is_standalone': is_standalone,
                'current_project_id': self.ui_state.current_project_id
            }
        }

        # Transition to confirmation dialog
        self.ui_state.state = AppState.DELETE_CONFIRMATION
        self.ui_state.form_field_index = 1  # Default to "No" for safety
        logger.info(
            "Showing delete confirmation for task (task_id=%s, standalone=%s)",
            getattr(task, "id", ""),
            is_standalone,
        )

    def _reselect_task_after_move(self, task_to_follow):
        """Reselect a task after it has been moved, handling both project and standalone lists.

        Args:
            task_to_follow: The task object that was moved
        """
        if self.ui_state.state == AppState.PROJECT_DETAILS:
            project = self.manager.get_project(self.ui_state.current_project_id)
            if not project:
                return
            flat_tasks = self._get_flat_tasks(project.tasks, True)
            # Find index of the moved task in the unified list
            for i, (_, t, _) in enumerate(flat_tasks):
                if t is task_to_follow:
                    self.ui_state.selected_index = i
                    break
        else:
            # Use the active list's tasks for standalone lists - need to calculate rendered index
            task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
            active_tab = getattr(self.ui_state, "active_tab", 0)
            active_list_name = task_lists[active_tab] if 0 <= active_tab < len(task_lists) else "Tasks"
            list_tasks_map = getattr(self.ui_state, "list_tasks", {"Tasks": self.manager.standalone_tasks})
            sections_for_list = list_tasks_map.get(active_list_name, [])

            # Build section data structure matching the renderer's logic
            list_metadata = self.manager.list_metadata
            done_mode = list_metadata.get(active_list_name, {}).get("show_done_section", "section")
            # Handle legacy boolean values
            if isinstance(done_mode, bool):
                done_mode = "section" if done_mode else "inline"
            all_section_data = []
            for section_idx, section in enumerate(sections_for_list):
                section_id = section.get("id") if isinstance(section, dict) else getattr(section, "id", None)
                section_name = section.name if hasattr(section, 'name') else section.get('name', '')
                section_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])
                flat_for_section = self._get_flat_tasks(section_tasks, False)
                if done_mode in ["section", "bottom"]:
                    pending = [t for t in flat_for_section if t[1].completed is None]
                    completed = [t for t in flat_for_section if t[1].completed is not None]
                else:  # "inline"
                    pending = flat_for_section
                    completed = []
                all_section_data.append((section_idx, section_id, section_name, pending, completed))

            show_section_headers = len(all_section_data) > 1 or (len(all_section_data) == 1 and all_section_data[0][2])

            # Calculate rendered indices matching the display logic
            current_index = 0
            all_completed_flat = []
            task_found = False

            for section_idx, section_id, section_name, pending, completed in all_section_data:
                if show_section_headers:
                    # Section header
                    current_index += 1
                    section_collapse_key = f"section:{section_id}"
                    is_collapsed = section_collapse_key in self.ui_state.collapsed_tasks
                    if not is_collapsed:
                        # Search in this section's pending tasks
                        for task_id, t, depth in pending:
                            if t is task_to_follow:
                                self.ui_state.selected_index = current_index
                                task_found = True
                                break
                            current_index += 1
                        if task_found:
                            break
                        # Add button
                        current_index += 1
                else:
                    # No section headers - search in pending tasks directly
                    for task_id, t, depth in pending:
                        if t is task_to_follow:
                            self.ui_state.selected_index = current_index
                            task_found = True
                            break
                        current_index += 1
                    if task_found:
                        break

                # Collect completed tasks when tasks are separated
                if done_mode in ["section", "bottom"]:
                    all_completed_flat.extend(completed)

            if not task_found and done_mode in ["section", "bottom"]:
                # Add the single + button if not showing section headers
                if not show_section_headers:
                    current_index += 1

                # Completed section header
                completed_header_index = current_index
                is_completed_collapsed = "section_completed" in self.ui_state.collapsed_tasks
                completed_items_start = completed_header_index + 1

                # Search in completed list
                if not is_completed_collapsed:
                    for j, (_, t, _) in enumerate(all_completed_flat):
                        if t is task_to_follow:
                            self.ui_state.selected_index = completed_items_start + j
                            break
                else:
                    # Completed section collapsed; select its header if task was there
                    for _, t, _ in all_completed_flat:
                        if t is task_to_follow:
                            self.ui_state.selected_index = completed_header_index
                            break

    def handle_task_move_up(self):
        """Handle moving task up in normal task lists, including cross-section movement."""
        selected_flat_task = self._get_selected_flat_task()
        if not selected_flat_task:
            return

        task_id, task, current_depth = selected_flat_task
        is_standalone = self.ui_state.state == AppState.TASK_LIST

        # Store task reference to find it after the move
        task_to_follow = task

        # Get flattened task list from current list (sections flattened into one list)
        task_list_override = self._get_task_list_override_for_list(
            selected_task=task,
            selected_task_id=getattr(task, "id", ""),
        )

        success = handle_task_move_up(
            self.manager,
            self.ui_state.current_project_id,
            getattr(task, "id", ""),
            is_standalone,
            task_list_override=task_list_override
        )

        # If normal move failed and we're in sectioned task list, try cross-section move
        if not success and is_standalone and self._is_sectioned_list():
            success = self._handle_cross_section_move_up(task_id, task)

        if success:
            # Update sections after operation
            self._update_list_sections_after_operation()
            # Mark per-list tasks modified when operating in standalone task lists
            if is_standalone:
                try:
                    self.manager.mark_list_tasks_modified()
                    self.manager.save()
                except Exception:
                    pass
            self._invalidate_task_cache()
            # Reselect the moved task respecting the current list layout
            self._reselect_task_after_move(task_to_follow)
            logger.info(
                "Task moved up via handler (task_id=%s, standalone=%s)",
                getattr(task, "id", ""),
                is_standalone,
            )
        else:
            logger.debug(
                "Task move up failed via handler (task_id=%s, standalone=%s)",
                getattr(task, "id", ""),
                is_standalone,
            )

    def handle_task_move_down(self):
        """Handle moving task down in normal task lists, including cross-section movement."""
        selected_flat_task = self._get_selected_flat_task()
        if not selected_flat_task:
            return

        task_id, task, current_depth = selected_flat_task
        is_standalone = self.ui_state.state == AppState.TASK_LIST

        # Store task reference to find it after the move
        task_to_follow = task

        # Get flattened task list from current list (sections flattened into one list)
        task_list_override = self._get_task_list_override_for_list(
            selected_task=task,
            selected_task_id=getattr(task, "id", ""),
        )

        success = handle_task_move_down(
            self.manager,
            self.ui_state.current_project_id,
            getattr(task, "id", ""),
            is_standalone,
            task_list_override=task_list_override
        )

        # If normal move failed and we're in sectioned task list, try cross-section move
        if not success and is_standalone and self._is_sectioned_list():
            success = self._handle_cross_section_move_down(task_id, task)

        if success:
            # Update sections after operation
            self._update_list_sections_after_operation()
            # Mark per-list tasks modified when operating in standalone task lists
            if is_standalone:
                try:
                    self.manager.mark_list_tasks_modified()
                    self.manager.save()
                except Exception:
                    pass
            self._invalidate_task_cache()
            # Reselect the moved task respecting the current list layout
            self._reselect_task_after_move(task_to_follow)
            logger.info(
                "Task moved down via handler (task_id=%s, standalone=%s)",
                getattr(task, "id", ""),
                is_standalone,
            )
        else:
            logger.debug(
                "Task move down failed via handler (task_id=%s, standalone=%s)",
                getattr(task, "id", ""),
                is_standalone,
            )

    def handle_task_move_left(self):
        """Move the selected standalone task to the list on the left."""
        self._move_task_to_adjacent_list(-1)

    def handle_task_move_right(self):
        """Move the selected standalone task to the list on the right."""
        self._move_task_to_adjacent_list(1)

    def _move_task_to_adjacent_list(self, direction: int) -> None:
        """Move the selected task to the adjacent list (left/right) in the task list screen."""
        if self.ui_state.state != AppState.TASK_LIST:
            return

        selected_flat_task = self._get_selected_flat_task()
        if not selected_flat_task:
            return

        task_id, task, _ = selected_flat_task
        task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
        active_tab = getattr(self.ui_state, "active_tab", 0)
        target_tab = active_tab + direction
        if target_tab < 0 or target_tab >= len(task_lists):
            return

        source_list_name = task_lists[active_tab]
        target_list_name = task_lists[target_tab]
        list_tasks_map = getattr(self.ui_state, "list_tasks", None) or getattr(self.manager, "list_tasks", {})

        source_sections = list_tasks_map.get(source_list_name, [])
        removed_task = self._remove_task_from_sections(source_sections, task, getattr(task, "id", ""))
        if removed_task is None:
            return

        target_sections = list_tasks_map.get(target_list_name)
        if not target_sections:
            try:
                from pm import Section
                target_sections = [Section(name="", tasks=[])]
            except Exception:
                target_sections = []
            list_tasks_map[target_list_name] = target_sections

        if target_sections and not isinstance(target_sections[0], dict) and not hasattr(target_sections[0], "name"):
            target_sections.append(removed_task)
        else:
            if not target_sections:
                try:
                    from pm import Section
                    target_sections.append(Section(name="", tasks=[]))
                except Exception:
                    return
            target_section = target_sections[0]
            target_tasks = target_section.tasks if hasattr(target_section, "tasks") else target_section.get("tasks", [])
            target_tasks.append(removed_task)

        try:
            self.manager.mark_list_tasks_modified()
            self.manager.save()
        except Exception:
            pass

        self.ui_state.active_tab = target_tab
        new_index = self._find_task_index_in_list(removed_task, target_list_name)
        if new_index is not None:
            self.ui_state.selected_index = new_index

        self._invalidate_task_cache()

    def _remove_task_from_sections(self, sections, task, task_id: str):
        """Remove a task from a section list by identity or task id, returning the task."""
        if not sections:
            return None

        def pop_by_identity(task_list, target):
            for i, item in enumerate(task_list):
                if item is target:
                    return task_list.pop(i)
                subtasks = getattr(item, "subtasks", None)
                if subtasks:
                    removed = pop_by_identity(subtasks, target)
                    if removed is not None:
                        return removed
            return None

        if sections and not isinstance(sections[0], dict) and not hasattr(sections[0], "name"):
            parent_task, task_idx, parent_list = get_task_parent_and_index_by_id(sections, task_id)
            if parent_list and 0 <= task_idx < len(parent_list) and parent_list[task_idx] is task:
                return parent_list.pop(task_idx)
            return pop_by_identity(sections, task)

        for section in sections:
            section_tasks = section.tasks if hasattr(section, "tasks") else section.get("tasks", [])
            parent_task, task_idx, parent_list = get_task_parent_and_index_by_id(section_tasks, task_id)
            if parent_list and 0 <= task_idx < len(parent_list) and parent_list[task_idx] is task:
                return parent_list.pop(task_idx)
            removed = pop_by_identity(section_tasks, task)
            if removed is not None:
                return removed
        return None

    def _find_task_index_in_list(self, task, list_name: str):
        """Return the rendered index of task in the specified list, if found."""
        list_tasks_map = getattr(self.ui_state, "list_tasks", {"Tasks": self.manager.standalone_tasks})
        sections_for_list = list_tasks_map.get(list_name, [])
        list_metadata = self.manager.list_metadata
        done_mode = list_metadata.get(list_name, {}).get("show_done_section", "section")
        # Handle legacy boolean values
        if isinstance(done_mode, bool):
            done_mode = "section" if done_mode else "inline"
        collapsed_tasks = self.ui_state.collapsed_tasks

        # Old format: direct list of tasks
        if sections_for_list and not isinstance(sections_for_list[0], dict) and not hasattr(sections_for_list[0], "name"):
            all_flat_tasks = self._get_flat_tasks(sections_for_list, False)
            if done_mode in ["section", "bottom"]:
                pending_flat = [t for t in all_flat_tasks if t[1].completed is None]
                completed_flat = [t for t in all_flat_tasks if t[1].completed is not None]
                for i, (_, t, _) in enumerate(pending_flat):
                    if t is task:
                        return i
                add_index = len(pending_flat)
                completed_header_index = add_index + 1
                is_completed_collapsed = "section_completed" in collapsed_tasks
                completed_items_start = completed_header_index + 1
                for j, (_, t, _) in enumerate(completed_flat):
                    if t is task:
                        return completed_header_index if is_completed_collapsed else completed_items_start + j
            else:
                for i, (_, t, _) in enumerate(all_flat_tasks):
                    if t is task:
                        return i
            return None

        all_section_data = []
        for section_idx, section in enumerate(sections_for_list):
            section_id = section.get("id") if isinstance(section, dict) else getattr(section, "id", None)
            section_name = section.name if hasattr(section, "name") else section.get("name", "")
            section_tasks = section.tasks if hasattr(section, "tasks") else section.get("tasks", [])
            flat_for_section = self._get_flat_tasks(section_tasks, False)
            if done_mode in ["section", "bottom"]:
                pending = [t for t in flat_for_section if t[1].completed is None]
                completed = [t for t in flat_for_section if t[1].completed is not None]
            else:  # "inline"
                pending = flat_for_section
                completed = []
            all_section_data.append((section_idx, section_id, section_name, pending, completed))

        show_section_headers = len(all_section_data) > 1 or (len(all_section_data) == 1 and all_section_data[0][2])
        current_index = 0
        all_completed_flat = []

        for section_idx, section_id, section_name, pending, completed in all_section_data:
            if show_section_headers:
                section_collapse_key = f"section:{section_id}"
                is_collapsed = section_collapse_key in collapsed_tasks
                current_index += 1
                if not is_collapsed:
                    for task_id, t, depth in pending:
                        if t is task:
                            return current_index
                        current_index += 1
                    current_index += 1  # Add button
            else:
                for task_id, t, depth in pending:
                    if t is task:
                        return current_index
                    current_index += 1

            if done_mode in ["section", "bottom"]:
                all_completed_flat.extend(completed)

        if done_mode in ["section", "bottom"]:
            if not show_section_headers:
                current_index += 1  # Single add button
            completed_header_index = current_index
            is_completed_collapsed = "section_completed" in collapsed_tasks
            completed_items_start = completed_header_index + 1
            for j, (_, t, _) in enumerate(all_completed_flat):
                if t is task:
                    return completed_header_index if is_completed_collapsed else completed_items_start + j

        return None

    def handle_collapse_toggle(self):
        """Toggle collapse/expand state of the selected task."""
        selected_flat_task = self._get_selected_flat_task()
        if not selected_flat_task:
            return

        task_path, task, current_depth = selected_flat_task

        # Only allow collapsing if the task has subtasks
        if not task.subtasks:
            return

        # Toggle the collapsed state using the positional path id from the flattened view.
        if not task_path:
            return
        if task_path in self.ui_state.collapsed_tasks:
            self.ui_state.collapsed_tasks.remove(task_path)  # Expand
            logger.debug("Expanded task node %s", task_path)
        else:
            self.ui_state.collapsed_tasks.add(task_path)  # Collapse
            logger.debug("Collapsed task node %s", task_path)

        # Invalidate cache
        self._invalidate_task_cache()
        self._persist_collapsed_tasks()

    def _get_selected_flat_task(self):
        """Get the currently selected task from the flattened list."""
        if self.ui_state.state == AppState.PROJECT_DETAILS:
            project = self.manager.get_project(self.ui_state.current_project_id)
            if project:
                flat_tasks = self._get_flat_tasks(project.tasks, True)
                if 0 <= self.ui_state.selected_index < len(flat_tasks):
                    return flat_tasks[self.ui_state.selected_index]
        elif self.ui_state.state == AppState.TASK_LIST:
            # Resolve current list tasks
            task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
            active_tab = getattr(self.ui_state, "active_tab", 0)
            active_list_name = task_lists[active_tab] if 0 <= active_tab < len(task_lists) else "Tasks"
            list_tasks_map = getattr(self.ui_state, "list_tasks", {"Tasks": self.manager.standalone_tasks})
            sections_for_list = list_tasks_map.get(active_list_name, [])

            # Handle both old format (list of tasks) and new format (list of sections)
            if sections_for_list and not isinstance(sections_for_list[0], dict) and not hasattr(sections_for_list[0], 'name'):
                # Old format: direct list of tasks
                # Check if completed tasks should be shown inline or in Done section
                list_metadata = self.manager.list_metadata
                done_mode = list_metadata.get(active_list_name, {}).get("show_done_section", "section")
                # Handle legacy boolean values
                if isinstance(done_mode, bool):
                    done_mode = "section" if done_mode else "inline"

                all_flat_tasks = self._get_flat_tasks(sections_for_list, False)

                if done_mode in ["section", "bottom"]:
                    pending_flat = [t for t in all_flat_tasks if t[1].completed is None]
                    completed_flat = [t for t in all_flat_tasks if t[1].completed is not None]

                    add_index = len(pending_flat)
                    if 0 <= self.ui_state.selected_index < len(pending_flat):
                        return pending_flat[self.ui_state.selected_index]
                    if done_mode == "section":
                        completed_header_index = add_index + 1
                        is_completed_collapsed = "section_completed" in self.ui_state.collapsed_tasks
                        completed_items_start = completed_header_index + 1
                        if not is_completed_collapsed and completed_items_start <= self.ui_state.selected_index < completed_items_start + len(completed_flat):
                            idx = self.ui_state.selected_index - completed_items_start
                            return completed_flat[idx]
                    else:  # bottom
                        completed_items_start = add_index + 1
                        if completed_items_start <= self.ui_state.selected_index < completed_items_start + len(completed_flat):
                            idx = self.ui_state.selected_index - completed_items_start
                            return completed_flat[idx]
                else:
                    # Keep all tasks in original order
                    add_index = len(all_flat_tasks)
                    if 0 <= self.ui_state.selected_index < len(all_flat_tasks):
                        return all_flat_tasks[self.ui_state.selected_index]
            else:
                # New format: list of sections with headers/add buttons and completed block
                # Check if completed tasks should be shown inline or in Done section
                list_metadata = self.manager.list_metadata
                done_mode = list_metadata.get(active_list_name, {}).get("show_done_section", "section")
                # Handle legacy boolean values
                if isinstance(done_mode, bool):
                    done_mode = "section" if done_mode else "inline"

                all_section_data = []
                for section_idx, section in enumerate(sections_for_list):
                    section_id = section.get("id") if isinstance(section, dict) else getattr(section, "id", None)
                    section_name = section.name if hasattr(section, 'name') else section.get('name', '')
                    section_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])
                    flat_for_section = self._get_flat_tasks(section_tasks, False)

                    # Split into pending and completed ONLY if showing Done section
                    # Otherwise, keep tasks in original order
                    if done_mode in ["section", "bottom"]:
                        pending = [t for t in flat_for_section if t[1].completed is None]
                        completed = [t for t in flat_for_section if t[1].completed is not None]
                    else:
                        # Keep all tasks in original order, don't separate completed ones
                        pending = flat_for_section
                        completed = []

                    all_section_data.append((section_idx, section_id, section_name, section_tasks, pending, completed))

                show_section_headers = len(all_section_data) > 1 or (len(all_section_data) == 1 and all_section_data[0][2])

                task_index_to_data = {}
                all_completed_flat = []
                current_index = 0

                for section_idx, section_id, section_name, section_tasks, pending, completed in all_section_data:
                    if show_section_headers:
                        # Header index (not selectable as task)
                        header_idx = current_index
                        current_index += 1
                        section_collapse_key = f"section:{section_id}"
                        is_collapsed = section_collapse_key in self.ui_state.collapsed_tasks
                        if not is_collapsed:
                            # Add pending tasks to index mapping
                            for task_id, task, depth in pending:
                                task_index_to_data[current_index] = (task_id, task, depth)
                                current_index += 1

                            # If Done section is disabled, add completed tasks inline here
                            if done_mode == "inline":
                                for task_id, task, depth in completed:
                                    task_index_to_data[current_index] = (task_id, task, depth)
                                    current_index += 1

                            # Add button index (skip)
                            current_index += 1
                    else:
                        # No section headers - add pending tasks
                        for task_id, task, depth in pending:
                            task_index_to_data[current_index] = (task_id, task, depth)
                            current_index += 1

                        # If Done section is disabled, add completed tasks inline here
                        if done_mode == "inline":
                            for task_id, task, depth in completed:
                                task_index_to_data[current_index] = (task_id, task, depth)
                                current_index += 1

                    # Collect completed tasks for Done section/bottom (only used if split mode)
                    if done_mode in ["section", "bottom"]:
                        for task_id, task, depth in completed:
                            all_completed_flat.append((task_id, task, depth))

                if not show_section_headers:
                    # Single + button
                    current_index += 1

                # Handle Done section/bottom (only if show_done_section is split)
                if done_mode == "section":
                    completed_header_index = current_index
                    is_completed_collapsed = "section_completed" in self.ui_state.collapsed_tasks
                    completed_items_start = completed_header_index + 1
                    current_index += 1  # completed header

                    # First check if selection is in pending/inline tasks
                    if self.ui_state.selected_index in task_index_to_data:
                        return task_index_to_data[self.ui_state.selected_index]

                    # Then check if selection is in Done section
                    if (not is_completed_collapsed) and (completed_items_start <= self.ui_state.selected_index < completed_items_start + len(all_completed_flat)):
                        idx = self.ui_state.selected_index - completed_items_start
                        return all_completed_flat[idx]
                elif done_mode == "bottom":
                    completed_items_start = current_index
                    if self.ui_state.selected_index in task_index_to_data:
                        return task_index_to_data[self.ui_state.selected_index]
                    if completed_items_start <= self.ui_state.selected_index < completed_items_start + len(all_completed_flat):
                        idx = self.ui_state.selected_index - completed_items_start
                        return all_completed_flat[idx]
                else:
                    # Done section is disabled - all tasks (including completed) are in task_index_to_data
                    if self.ui_state.selected_index in task_index_to_data:
                        return task_index_to_data[self.ui_state.selected_index]

        return None

    def _flatten_list_sections(self, sections_for_list):
        """Flatten all sections for the active list into a single list."""
        flattened = []
        if not sections_for_list:
            return flattened

        for section in sections_for_list:
            section_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])
            flatten_tasks(section_tasks, flattened, collapsed_tasks=self.ui_state.collapsed_tasks)
        return flattened

    def execute_confirmed_delete(self, delete_params: dict):
        """Execute the actual task deletion after confirmation."""
        task_id = delete_params.get('task_id') or delete_params.get('path')
        if not task_id:
            return False
        is_standalone = delete_params['is_standalone']
        current_project_id = delete_params.get('current_project_id')

        # Temporarily set current_project_id for the delete operation
        original_project_id = self.ui_state.current_project_id
        self.ui_state.current_project_id = current_project_id

        task = delete_params.get('task')
        # Get flattened task list from current list (sections flattened into one list)
        task_list_override = self._get_task_list_override_for_list(
            selected_task=task,
            selected_task_id=getattr(task, "id", ""),
        )

        success = handle_task_delete(
            self.manager,
            self.ui_state.current_project_id,
            task_id,
            is_standalone,
            task_list_override=task_list_override
        )

        # Restore original state
        self.ui_state.current_project_id = original_project_id

        if success:
            # Update sections after operation
            self._update_list_sections_after_operation()
            # Mark per-list tasks modified when operating in standalone task lists
            if is_standalone:
                try:
                    self.manager.mark_list_tasks_modified()
                    self.manager.save()
                except Exception:
                    pass
            self._invalidate_task_cache()
        else:
            logger.debug("Task delete failed after confirmation (task_id=%s, standalone=%s)", task_id, is_standalone)

        return success

    def _is_sectioned_list(self) -> bool:
        """Check if current list has multiple sections (enabling cross-section moves)."""
        task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
        active_tab = getattr(self.ui_state, "active_tab", 0)
        active_list_name = task_lists[active_tab] if 0 <= active_tab < len(task_lists) else "Tasks"
        list_tasks_map = getattr(self.ui_state, "list_tasks", {"Tasks": self.manager.standalone_tasks})
        sections_for_list = list_tasks_map.get(active_list_name, [])

        # Check if we have multiple sections with the section structure
        if not sections_for_list:
            return False

        # Check if it's the new section format (list of Section objects)
        if sections_for_list and (isinstance(sections_for_list[0], dict) or hasattr(sections_for_list[0], 'name')):
            return len(sections_for_list) > 1

        return False

    def _handle_cross_section_move_up(self, task_id: str, task) -> bool:
        """Move task from current section to end of previous section."""
        task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
        active_tab = getattr(self.ui_state, "active_tab", 0)
        active_list_name = task_lists[active_tab] if 0 <= active_tab < len(task_lists) else "Tasks"
        list_tasks_map = getattr(self.ui_state, "list_tasks", {"Tasks": self.manager.standalone_tasks})
        sections_for_list = list_tasks_map.get(active_list_name, [])

        # Find which section contains the task
        current_section_idx = None
        for section_idx, section in enumerate(sections_for_list):
            section_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])
            # Check if task is at root level of this section (not nested)
            for i, t in enumerate(section_tasks):
                if t is task:
                    current_section_idx = section_idx
                    break
            if current_section_idx is not None:
                break

        # Can't move to previous section if no previous section exists
        if current_section_idx is None or current_section_idx == 0:
            return False

        # Get current and previous sections
        current_section = sections_for_list[current_section_idx]
        previous_section = sections_for_list[current_section_idx - 1]
        current_tasks = current_section.tasks if hasattr(current_section, 'tasks') else current_section.get('tasks', [])
        previous_tasks = previous_section.tasks if hasattr(previous_section, 'tasks') else previous_section.get('tasks', [])

        # Find and remove task from current section
        task_obj = None
        for i, t in enumerate(current_tasks):
            if t is task:
                task_obj = current_tasks.pop(i)
                break

        if task_obj is None:
            return False

        # Add to end of previous section
        previous_tasks.append(task_obj)

        # Save changes
        self.manager.mark_list_tasks_modified()
        self.manager.save()

        logger.info("Moved task up across sections: %s from section %d to %d",
                   task.name, current_section_idx, current_section_idx - 1)
        return True

    def _handle_cross_section_move_down(self, task_id: str, task) -> bool:
        """Move task from current section to beginning of next section."""
        task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
        active_tab = getattr(self.ui_state, "active_tab", 0)
        active_list_name = task_lists[active_tab] if 0 <= active_tab < len(task_lists) else "Tasks"
        list_tasks_map = getattr(self.ui_state, "list_tasks", {"Tasks": self.manager.standalone_tasks})
        sections_for_list = list_tasks_map.get(active_list_name, [])

        # Find which section contains the task
        current_section_idx = None
        for section_idx, section in enumerate(sections_for_list):
            section_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])
            # Check if task is at root level of this section (not nested)
            for i, t in enumerate(section_tasks):
                if t is task:
                    current_section_idx = section_idx
                    break
            if current_section_idx is not None:
                break

        # Can't move to next section if no next section exists
        if current_section_idx is None or current_section_idx >= len(sections_for_list) - 1:
            return False

        # Get current and next sections
        current_section = sections_for_list[current_section_idx]
        next_section = sections_for_list[current_section_idx + 1]
        current_tasks = current_section.tasks if hasattr(current_section, 'tasks') else current_section.get('tasks', [])
        next_tasks = next_section.tasks if hasattr(next_section, 'tasks') else next_section.get('tasks', [])

        # Find and remove task from current section
        task_obj = None
        for i, t in enumerate(current_tasks):
            if t is task:
                task_obj = current_tasks.pop(i)
                break

        if task_obj is None:
            return False

        # Add to beginning of next section
        next_tasks.insert(0, task_obj)

        # Save changes
        self.manager.mark_list_tasks_modified()
        self.manager.save()

        logger.info("Moved task down across sections: %s from section %d to %d",
                   task.name, current_section_idx, current_section_idx + 1)
        return True

