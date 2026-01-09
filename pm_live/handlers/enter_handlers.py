"""Enter key handlers for different views in the live CLI."""

import logging
from pathlib import Path
from typing import Optional

from ..interfaces import HandlerContext
from ..states import AppState
from ..quick_stats import QUICK_STATS_ORDER, normalize_quick_stats_selection
from ..main_menu_tabs import MAIN_MENU_TABS_ORDER, normalize_main_menu_tabs, build_main_menu_items, is_quick_add_enabled
from ..keybindings import FORM_STATES
from ..utils import (
    filter_projects_by_tab,
    validate_project_name,
    validate_task_name,
    validate_section_name,
    sanitize_input,
    get_edit_project_field_keys,
    get_visible_fields_sorted,
    sort_projects_for_display,
)
from ..tasks import toggle_task_completion, flatten_tasks
from ..utils.calendar import CalendarEntry, collect_deadline_map
from pm import Task, Project, Section, STATUS_DISPLAY_ORDER
from .form_handlers import FormHandlers
from ..custom_fields import get_all_fields

logger = logging.getLogger(__name__)


class EnterHandlers:
    """Handles enter key presses in different application states."""

    def __init__(self, context: HandlerContext, bookmark_handlers, task_handlers=None):
        """Initialize with shared handler context."""
        self._context = context
        self.manager = context.manager
        self.ui_state = context.ui_state
        self._get_flat_tasks = context.get_flat_tasks
        self._invalidate_task_cache = context.invalidate_task_cache
        self._exit_application = context.exit_application
        self._status_callback = context.show_status
        self._key_handlers = None  # Set after construction to avoid circular init
        self.form_handlers = FormHandlers(context, advance_form_cursor=self._advance_form_cursor)
        self.bookmark_handlers = bookmark_handlers
        self.task_handlers = task_handlers

    def set_key_handlers(self, key_handlers) -> None:
        """Provide KeyHandlers instance for cursor clamping."""
        self._key_handlers = key_handlers

    def _set_status(self, message: str | None, is_error: bool = False):
        """Store a status message for renderers to display."""
        self._status_callback(message, is_error)

    def _advance_form_cursor(self) -> None:
        """Move form cursor to the next field, clamped to max."""
        max_index = None
        try:
            if self._key_handlers:
                max_index = self._key_handlers._get_max_form_index()
        except Exception:
            max_index = None

        if max_index is None:
            self.ui_state.form_field_index += 1
        else:
            self.ui_state.form_field_index = min(self.ui_state.form_field_index + 1, max_index)

    def _calendar_navigate_month(self, delta: int) -> None:
        """Navigate calendar by delta months, handling year transitions.

        Args:
            delta: Number of months to move (negative for backward)
        """
        from calendar import monthrange

        year = self.ui_state.calendar_year
        month = self.ui_state.calendar_month + delta
        selected_day = self.ui_state.calendar_selected_day or 1

        # Handle year wraparound
        while month > 12:
            month -= 12
            year += 1
        while month < 1:
            month += 12
            year -= 1

        # Clamp day to valid range for new month
        _, max_day = monthrange(year, month)
        selected_day = min(selected_day, max_day)

        self.ui_state.calendar_year = year
        self.ui_state.calendar_month = month
        self.ui_state.calendar_selected_day = selected_day

    def _get_calendar_tasks_for_selected_day(self) -> list[CalendarEntry]:
        """Return tasks with deadlines for the selected calendar day."""
        year = self.ui_state.calendar_year
        month = self.ui_state.calendar_month
        day = self.ui_state.calendar_selected_day
        if not (year and month and day):
            return []

        list_tasks_map = getattr(self.ui_state, "list_tasks", None) or getattr(
            self.manager,
            "list_tasks",
            {"Tasks": getattr(self.manager, "standalone_tasks", [])},
        )
        deadline_map = collect_deadline_map(self.manager, list_tasks_map)
        date_key = f"{year:04d}-{month:02d}-{day:02d}"
        return deadline_map.get(date_key, [])

    @staticmethod
    def _normalize_select_options(options):
        """Ensure select options are SelectOption objects (not raw dicts)."""
        from pm_live.custom_fields import SelectOption

        normalized = []
        for opt in options or []:
            if isinstance(opt, SelectOption):
                normalized.append(opt)
            elif isinstance(opt, dict):
                normalized.append(SelectOption(value=opt.get("value", ""), color=opt.get("color")))
            else:
                try:
                    value = getattr(opt, "value", "")
                    color = getattr(opt, "color", None)
                    normalized.append(SelectOption(value=value, color=color))
                except Exception:
                    continue
        return normalized

    def start_add_project_form(self):
        """Enter the add-project form using the same path as the footer action."""
        from pm import Project

        self._set_status(None)
        temp_project = Project(
            id="__temp_new_project__",
            name="",
            status="Planned",
            tasks=[],
        )
        self.ui_state.current_project_id = temp_project.id
        self.ui_state._temp_project = temp_project
        self.ui_state.form_data = {
            "name": "",
            "status": "Planned",
        }
        self.ui_state.state = AppState.ADD_PROJECT
        self.ui_state.selected_index = 0
        self.ui_state.form_field_index = 0

    def _prepare_inline_task_edit_state(self, new_task, origin: str, list_name: str | None, project_id: str | None, new_task_index: int | None):
        """Shared inline edit initialisation for new task rows."""
        from pm_live.handlers.task_handlers import PRIORITY_CYCLE

        if new_task_index is not None:
            self.ui_state.selected_index = new_task_index

        priority_value = getattr(new_task, "priority", None)
        if priority_value not in PRIORITY_CYCLE or priority_value is None:
            priority_value = "none"

        self.ui_state.inline_task_edit_mode = True
        self.ui_state.inline_edit_task_id = None
        self.ui_state.inline_edit_task = new_task
        self.ui_state.inline_edit_origin = origin
        self.ui_state.inline_edit_list_name = list_name
        self.ui_state.inline_edit_project_id = project_id
        self.ui_state.inline_edit_field_index = 0
        self.ui_state.inline_edit_deadline_component = 0
        self.ui_state.inline_edit_name = new_task.name or ""
        self.ui_state.inline_edit_name_cursor = len(self.ui_state.inline_edit_name)
        self.ui_state.inline_edit_deadline = getattr(new_task, "deadline", None) or None
        self.ui_state.inline_edit_priority = priority_value
        self.ui_state.inline_edit_notes = getattr(new_task, "notes", None) or None
        self.ui_state.inline_edit_notes_cursor = len(self.ui_state.inline_edit_notes or "")
        self.ui_state.inline_edit_original = {
            "name": new_task.name,
            "deadline": getattr(new_task, "deadline", None),
            "priority": getattr(new_task, "priority", None),
            "notes": getattr(new_task, "notes", None),
        }
        # Ensure inline text buffer is not in use simultaneously
        self.ui_state.inline_input_mode = False
        self.ui_state.text_input_buffer = ""

        self._invalidate_task_cache()
        self._set_status(None)

    def start_inline_task_add_for_project(self):
        """Add a new task inside the current project and begin inline edit."""
        project = self.manager.get_project(self.ui_state.current_project_id)
        if not project:
            return False

        flat_tasks = self._get_flat_tasks(project.tasks, True)
        new_task = Task(name="")
        project.tasks.append(new_task)

        self._prepare_inline_task_edit_state(
            new_task,
            origin="project",
            list_name=None,
            project_id=self.ui_state.current_project_id,
            new_task_index=len(flat_tasks),
        )
        logger.info("Created new task for inline editing in project %s", self.ui_state.current_project_id)
        return True

    def _build_task_list_layout(self):
        """Build layout metadata for the task list view (standalone lists)."""
        task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
        active_tab = getattr(self.ui_state, "active_tab", 0)
        active_list_name = task_lists[active_tab] if 0 <= active_tab < len(task_lists) else "Tasks"
        list_tasks_map = getattr(
            self.ui_state,
            "list_tasks",
            getattr(self.manager, "list_tasks", {"Tasks": self.manager.standalone_tasks}),
        )
        sections_for_list = list_tasks_map.get(active_list_name, [])

        # Handle legacy format (flat task list) by wrapping in a default section
        if sections_for_list:
            first = sections_for_list[0]
            looks_like_section = (
                (isinstance(first, dict) and 'tasks' in first)
                or hasattr(first, 'tasks')
            )
            if not looks_like_section:
                default_section = type('Section', (), {'name': '', 'tasks': sections_for_list})()
                sections_for_list = [default_section]

        # Check if completed tasks should be shown inline or in Done section
        list_metadata = self.manager.list_metadata
        show_done_section = list_metadata.get(active_list_name, {}).get("show_done_section", "section")

        all_section_data = []  # (section_idx, section_id, section_name, section_obj, pending, completed)
        section_idx_to_id = {}
        for section_idx, section in enumerate(sections_for_list):
            section_id = section.get("id") if isinstance(section, dict) else getattr(section, "id", None)
            section_name = section.name if hasattr(section, 'name') else section.get('name', '')
            section_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])
            flat_for_section = self._get_flat_tasks(section_tasks, False)

            # Split into pending and completed for "section" and "bottom" modes
            # Otherwise, keep tasks in original order
            if show_done_section in ["section", "bottom"]:
                pending = [t for t in flat_for_section if t[1].completed is None]
                completed = [t for t in flat_for_section if t[1].completed is not None]
            else:  # "inline"
                # Keep all tasks in original order, don't separate completed ones
                pending = flat_for_section
                completed = []

            all_section_data.append((section_idx, section_id, section_name, section, pending, completed))
            section_idx_to_id[section_idx] = section_id

        show_section_headers = len(all_section_data) > 1 or (len(all_section_data) == 1 and all_section_data[0][2])

        current_index = 0
        section_header_indices = {}
        section_add_indices = {}
        task_index_to_data = {}
        index_to_section_idx = {}
        all_completed_flat = []

        for section_idx, section_id, section_name, section_obj, pending, completed in all_section_data:
            section_tasks = section_obj.tasks if hasattr(section_obj, 'tasks') else section_obj.get('tasks', [])
            if show_section_headers:
                section_header_indices[section_idx] = current_index
                index_to_section_idx[current_index] = section_idx
                current_index += 1

                section_collapse_key = f"section:{section_id}"
                is_section_collapsed = section_collapse_key in self.ui_state.collapsed_tasks

                if not is_section_collapsed:
                    for task_id, task, depth in pending:
                        task_index_to_data[current_index] = (task_id, task, section_tasks)
                        index_to_section_idx[current_index] = section_idx
                        current_index += 1

                    section_add_indices[section_idx] = current_index
                    index_to_section_idx[current_index] = section_idx
                    current_index += 1
            else:
                for task_id, task, depth in pending:
                    task_index_to_data[current_index] = (task_id, task, section_tasks)
                    index_to_section_idx[current_index] = section_idx
                    current_index += 1

            for task_id, task, depth in completed:
                all_completed_flat.append((task_id, task, depth, section_tasks, section_idx))

        if not show_section_headers:
            add_index = current_index
            current_index += 1
        else:
            add_index = None

        # Count indices for completed tasks based on mode
        if show_done_section == "section":
            # Section mode: has header with collapse functionality
            completed_header_index = current_index
            is_completed_collapsed = "section_completed" in self.ui_state.collapsed_tasks
            current_index += 1  # Header
            completed_items_start = current_index
            if not is_completed_collapsed:
                current_index += len(all_completed_flat)
        elif show_done_section == "bottom":
            # Bottom mode: no header, tasks always visible
            completed_header_index = None
            is_completed_collapsed = False
            completed_items_start = current_index
            current_index += len(all_completed_flat)
        else:  # "inline"
            completed_header_index = None
            is_completed_collapsed = False
            completed_items_start = None

        new_list_index = current_index
        can_edit_tab = active_tab > 0 and active_tab < len(task_lists)
        if can_edit_tab:
            edit_tab_index = new_list_index + 1
            back_index = edit_tab_index + 1
        else:
            edit_tab_index = None
            back_index = new_list_index + 1

        return {
            "task_lists": task_lists,
            "active_tab": active_tab,
            "active_list_name": active_list_name,
            "list_tasks_map": list_tasks_map,
            "all_section_data": all_section_data,
            "show_section_headers": show_section_headers,
            "section_header_indices": section_header_indices,
            "section_add_indices": section_add_indices,
            "task_index_to_data": task_index_to_data,
            "index_to_section_idx": index_to_section_idx,
            "section_idx_to_id": section_idx_to_id,
            "all_completed_flat": all_completed_flat,
            "add_index": add_index,
            "completed_header_index": completed_header_index,
            "completed_items_start": completed_items_start,
            "is_completed_collapsed": is_completed_collapsed,
            "new_list_index": new_list_index,
            "can_edit_tab": can_edit_tab,
            "edit_tab_index": edit_tab_index,
            "back_index": back_index,
        }

    def build_task_list_layout(self):
        """Public wrapper for task list layout metadata."""
        return self._build_task_list_layout()

    def start_inline_task_add_for_list(self, target_section_idx: int | None = None, layout: dict | None = None):
        """Add a new task in the task list view (per-list sections) and enter inline edit."""
        layout = layout or self._build_task_list_layout()
        if not layout:
            return False

        all_section_data = layout["all_section_data"]
        if not all_section_data:
            return False

        if target_section_idx is None:
            target_section_idx = 0

        section_entry = next((entry for entry in all_section_data if entry[0] == target_section_idx), None)
        if not section_entry:
            return False

        _, _, _, section_obj, _, _ = section_entry
        if hasattr(section_obj, 'tasks'):
            section_tasks = section_obj.tasks
        elif isinstance(section_obj, dict):
            section_tasks = section_obj.setdefault('tasks', [])
        else:
            section_tasks = []

        if layout["show_section_headers"]:
            new_task_index = layout["section_add_indices"].get(target_section_idx)
            if new_task_index is None:
                return False
        else:
            new_task_index = layout["add_index"]

        new_task = Task(name="")
        section_tasks.append(new_task)

        self._prepare_inline_task_edit_state(
            new_task,
            origin="task_list",
            list_name=layout["active_list_name"],
            project_id=self.ui_state.current_project_id,
            new_task_index=new_task_index,
        )
        logger.info("Created new task for inline editing in list '%s' (section %s)", layout["active_list_name"], target_section_idx)
        return True

    def start_edit_custom_field(self, field_idx: int) -> None:
        """Begin editing a custom field from the Customize Fields screen."""
        custom_fields = getattr(self.manager, "custom_field_definitions", [])
        if field_idx < 0 or field_idx >= len(custom_fields):
            return

        field = custom_fields[field_idx]
        select_options = []
        try:
            existing_opts = getattr(field, "select_options", []) or []
            # Shallow copy to avoid mutating original until save
            select_options = list(existing_opts)
        except Exception:
            pass

        self.ui_state.state = AppState.EDIT_CUSTOM_FIELD
        self.ui_state.form_data = {
            "key": getattr(field, "key", ""),
            "label": getattr(field, "label", ""),
            "field_type": getattr(field, "field_type", "text"),
            "visible": getattr(field, "visible", True),
            "required": getattr(field, "required", False),
            "number_format": getattr(field, "number_format", "number"),
            "currency_symbol": getattr(field, "currency_symbol", "$"),
            "select_options": select_options,
        }
        self.ui_state.form_field_index = 0
        self.ui_state.selected_index = 0
        self.ui_state.inline_input_mode = False
        self.ui_state.text_input_buffer = ""
        self.ui_state.custom_field_date_edit_mode = False
        self.ui_state.custom_field_date_buffer = None
        logger.info("Opening edit custom field form for '%s'", getattr(field, "key", ""))

    def handle_enter(self):
        """Route to appropriate enter handler based on current state."""
        start_state = self.ui_state.state
        was_inline = bool(self.ui_state.inline_input_mode)

        # Inline task edit confirmation takes precedence
        if getattr(self.ui_state, "inline_task_edit_mode", False) and self.task_handlers:
            # For calendar, remember the edited task to adjust cursor after save
            saved_task = None
            if self.ui_state.state == AppState.CALENDAR:
                saved_task = getattr(self.ui_state, "inline_edit_task", None)

            handled = self.task_handlers.commit_inline_edit()
            if handled:
                # For calendar, move cursor to the saved task's position
                # But only if save was successful (edit mode exited)
                if self.ui_state.state == AppState.CALENDAR and saved_task and not self.ui_state.inline_task_edit_mode:
                    tasks = self._key_handlers._get_calendar_tasks_for_active_tab()
                    for i, item in enumerate(tasks):
                        # Extract actual entry (handle tuples for upcoming tab)
                        if isinstance(item, tuple):
                            if item[0] == "task":
                                entry = item[1]
                            else:
                                # Skip headers
                                continue
                        else:
                            entry = item
                        if entry.kind == "task" and entry.item is saved_task:
                            self.ui_state.calendar_task_selected_index = i
                            break
                return

        if self.ui_state.state == AppState.MAIN_MENU:
            self.handle_main_menu_enter()
        elif self.ui_state.state == AppState.PROJECT_BROWSER:
            self.handle_project_browser_enter()
        elif self.ui_state.state == AppState.PROJECT_DETAILS:
            self.handle_project_details_enter()
        elif self.ui_state.state == AppState.TASK_LIST:
            self.handle_task_list_enter()
        elif self.ui_state.state == AppState.STATISTICS:
            # Only interactive element is the back action
            self.ui_state.state = AppState.MAIN_MENU
            self.ui_state.selected_index = 0
        elif self.ui_state.state == AppState.SEARCH:
            self.handle_search_enter()
        elif self.ui_state.state == AppState.PROJECT_SELECTION_MENU:
            self.handle_project_selection_enter()
        elif self.ui_state.state == AppState.CALENDAR:
            # If in inline edit mode, save changes
            if self.ui_state.inline_task_edit_mode:
                tasks = self._key_handlers._get_calendar_tasks_for_active_tab()
                task_index = self.ui_state.calendar_task_selected_index
                if 0 <= task_index < len(tasks):
                    item = tasks[task_index]
                    # Extract actual entry (handle both raw entries and tuples for upcoming tab)
                    if isinstance(item, tuple) and item[0] == "task":
                        entry = item[1]
                    else:
                        entry = item
                    if entry.kind != "task":
                        self.ui_state.inline_task_edit_mode = False
                        self._set_status("Only tasks can be edited here")
                        return

                    task = entry.item
                    project_name = entry.project_name

                    # Update task with edited values
                    task.name = self.ui_state.inline_edit_name
                    task.deadline = self.ui_state.inline_edit_deadline
                    task.priority = self.ui_state.inline_edit_priority

                    # Save changes
                    if project_name:
                        self.manager.save()
                    else:
                        self.manager.mark_list_tasks_modified()
                        self.manager.save()

                    # Exit inline edit mode
                    self.ui_state.inline_task_edit_mode = False
                return

            # Check if we're on navigation arrows
            if self.ui_state.calendar_navigation_focus == "prev":
                # Navigate to previous month (or year if at January)
                self._calendar_navigate_month(-1)
                self.ui_state.calendar_task_selected_index = 0
                if not self.ui_state.calendar_selected_day:
                    self.ui_state.calendar_selected_day = 1
            elif self.ui_state.calendar_navigation_focus == "next":
                # Navigate to next month (or year if at December)
                self._calendar_navigate_month(1)
                self.ui_state.calendar_task_selected_index = 0
                if not self.ui_state.calendar_selected_day:
                    self.ui_state.calendar_selected_day = 1
            elif self.ui_state.calendar_navigation_focus == "back":
                # Only other interactive element is the back action
                self.ui_state.state = AppState.MAIN_MENU
                self.ui_state.selected_index = 0
            elif self.ui_state.calendar_navigation_focus == "tasks":
                # Cycle task completion status
                tasks = self._key_handlers._get_calendar_tasks_for_active_tab()
                task_index = self.ui_state.calendar_task_selected_index
                has_add = self._key_handlers._has_add_button_in_calendar()
                
                # Check if we're on the "+ Add task" button (index == len)
                if has_add and task_index == len(tasks):
                    self._key_handlers.start_inline_task_add_for_calendar()
                    return

                if 0 <= task_index < len(tasks):
                    item = tasks[task_index]
                    
                    # Handle section headers in upcoming tab
                    if self.ui_state.calendar_tasks_tab == 2 and isinstance(item, tuple) and item[0] == "header":
                        # Toggle collapse/expand for this section
                        _, section_key, _, _ = item
                        if section_key in self.ui_state.calendar_upcoming_collapsed:
                            self.ui_state.calendar_upcoming_collapsed.remove(section_key)
                        else:
                            self.ui_state.calendar_upcoming_collapsed.add(section_key)
                        return
                    
                    # Extract actual entry (handle both raw entries and tuples)
                    if isinstance(item, tuple) and item[0] == "task":
                        entry = item[1]
                    else:
                        entry = item
                    
                    if entry.kind != "task":
                        project = entry.item if entry.kind == "project_field" else None
                        project_id = getattr(project, "id", None)
                        if project_id is None:
                            self._set_status("Project not found", True)
                            return

                        self.ui_state.state = AppState.PROJECT_DETAILS
                        self.ui_state.current_project_id = project_id
                        self.ui_state.selected_index = 0
                        return

                    task = entry.item
                    project_name = entry.project_name

                    # Cycle: None -> True -> False -> None
                    current = getattr(task, "completed", None)
                    if current is None:
                        task.completed = True
                    elif current is True:
                        task.completed = False
                    else:
                        task.completed = None

                    # Save changes
                    if project_name:
                        # Task is from a project, save will update it
                        self.manager.save()
                    else:
                        # Task is standalone or from list, mark modified and save
                        self.manager.mark_list_tasks_modified()
                        self.manager.save()
                return
            else:
                self.ui_state.calendar_navigation_focus = "tasks"
                self.ui_state.calendar_task_selected_index = 0
        elif self.ui_state.state == AppState.SETTINGS:
            self.handle_settings_enter()
        elif self.ui_state.state == AppState.QUICK_STATS_SETTINGS:
            self.handle_quick_stats_settings_enter()
        elif self.ui_state.state == AppState.MAIN_MENU_TABS_SETTINGS:
            self.handle_main_menu_tabs_settings_enter()
        elif self.ui_state.state == AppState.DEADLINE_SETTINGS:
            self.handle_deadline_settings_enter()
        elif self.ui_state.state == AppState.PROJECT_BROWSER_TAB_SETTINGS:
            self.handle_project_browser_tab_settings_enter()
        elif self.ui_state.state == AppState.STATS_NONE_SETTINGS:
            self.handle_stats_none_settings_enter()
        elif self.ui_state.state == AppState.MESSAGE_DISPLAY_SETTINGS:
            self.handle_message_display_settings_enter()
        elif self.ui_state.state == AppState.NOTES_DISPLAY_SETTINGS:
            self.handle_notes_display_settings_enter()
        elif self.ui_state.state == AppState.BOOKMARK_ACTION_SETTINGS:
            self.handle_bookmark_action_settings_enter()
        elif self.ui_state.state == AppState.CUSTOMIZE_FIELDS:
            self.handle_customize_fields_enter()
        elif self.ui_state.state == AppState.ADD_CUSTOM_FIELD:
            self.handle_add_custom_field_enter()
        elif self.ui_state.state == AppState.EDIT_CUSTOM_FIELD:
            self.handle_edit_custom_field_enter()
        elif self.ui_state.state == AppState.BOOKMARKS:
            self.bookmark_handlers.handle_bookmarks_enter()
        elif self.ui_state.state == AppState.BOOKMARK_LIST:
            self.bookmark_handlers.handle_bookmark_list_enter()
        elif self.ui_state.state == AppState.CHANGE_STATUS:
            self.handle_change_status_enter()
        elif self.ui_state.state == AppState.ADD_PROJECT:
            self.handle_add_project_enter()
        elif self.ui_state.state == AppState.EDIT_PROJECT:
            self.handle_edit_project_enter()
        elif self.ui_state.state == AppState.ADD_BOOKMARK:
            self.bookmark_handlers.handle_add_bookmark_enter()
        elif self.ui_state.state == AppState.EDIT_BOOKMARK:
            self.bookmark_handlers.handle_edit_bookmark_enter()
        elif self.ui_state.state == AppState.EDIT_TAB:
            self.handle_edit_list_enter()
        elif self.ui_state.state == AppState.DELETE_CONFIRMATION:
            self.handle_delete_confirmation_enter()

        # If we just saved inline text in a form, move to the next field automatically
        if was_inline and not self.ui_state.inline_input_mode and start_state in FORM_STATES:
            self._advance_form_cursor()

    def _find_task_by_name_path(self, tasks: list, target_path: str) -> Optional[object]:
        """Find a task object by its name-based path (e.g. "Parent.Child.Grandchild").
        
        Args:
            tasks: Root task list
            target_path: Dot-separated task name path
            
        Returns:
            Task object if found, None otherwise
        """
        parts = target_path.split('.')
        if not parts:
            return None
            
        # Walk down the tree following the name path
        current_tasks = tasks
        for part in parts:
            found = False
            for task in current_tasks:
                if getattr(task, 'name', '') == part:
                    if part == parts[-1]:  # Last part - found target
                        return task
                    # Continue down the tree
                    current_tasks = getattr(task, 'subtasks', [])
                    found = True
                    break
            if not found:
                return None
        
        return None
    
    def _expand_task_ancestors(self, tasks: list, target: object) -> bool:
        """Expand all ancestor tasks for target by removing them from collapsed set.
        
        Returns True if any changes were made to collapsed_tasks.
        """
        def _find_task_path(tasks_list: list, target_task: object) -> Optional[list]:
            """Return ancestor path to target (excluding target), or None."""
            for task in tasks_list:
                if task is target_task:
                    return []
                subtasks = getattr(task, 'subtasks', None)
                if subtasks:
                    path = _find_task_path(list(subtasks), target_task)
                    if path is not None:
                        return [task] + path
            return None
        
        path = _find_task_path(tasks, target)
        if path is None:
            return False
            
        before = set(self.ui_state.collapsed_tasks)
        for ancestor in path:
            ancestor_id = getattr(ancestor, 'id', None)
            if ancestor_id and ancestor_id in self.ui_state.collapsed_tasks:
                self.ui_state.collapsed_tasks.discard(ancestor_id)
        
        return before != self.ui_state.collapsed_tasks

    def handle_search_enter(self):
        """Handle enter in search - jump to selected result."""
        if not self.ui_state.search_results:
            return

        selected_idx = self.ui_state.search_selected_index
        if selected_idx < 0 or selected_idx >= len(self.ui_state.search_results):
            return

        result = self.ui_state.search_results[selected_idx]
        result_type = result.get('type')

        # Save previous state to potentially return to
        previous_state = self.ui_state.previous_state or AppState.MAIN_MENU

        if result_type == 'project':
            # Jump to project details - find project in sorted list
            project_id = result.get('id')
            
            # Get sorted projects as they appear in the browser
            sorted_projects = self._get_filtered_projects_sorted()
            
            # Find the project index
            project_idx = 0
            for i, proj in enumerate(sorted_projects):
                if proj.id == project_id:
                    project_idx = i
                    break
            
            if 0 <= project_idx < len(sorted_projects):
                self.ui_state.project_browser_selected_index = project_idx
                self.ui_state.project_browser_selected_project_id = sorted_projects[project_idx].id
                self.ui_state.current_project_id = sorted_projects[project_idx].id

            self.ui_state.state = AppState.PROJECT_DETAILS
            self.ui_state.selected_index = 0
            # Clear search state
            self.ui_state.search_query = ""
            self.ui_state.search_results = []
            self.ui_state.search_selected_index = 0

        elif result_type == 'task':
            # Jump to task location (in project or list)
            project_id = result.get('project_id')
            list_name = result.get('list_name')
            task_path = result.get('id')  # This is the task path from search

            if project_id is not None:
                # Task in project - open project details and find task
                project = self.manager.get_project(project_id)
                if project:
                    # Find task object by name path
                    task_obj = self._find_task_by_name_path(project.tasks, task_path)
                    
                    # Expand ancestors if task is collapsed
                    if task_obj:
                        expanded = self._expand_task_ancestors(project.tasks, task_obj)
                        if expanded:
                            self._context.persist_collapsed_tasks()
                    
                    self.ui_state.state = AppState.PROJECT_DETAILS
                    self.ui_state.current_project_id = project_id
                    
                    # Find task index in flattened list
                    flat_tasks = self._get_flat_tasks(project.tasks, self.ui_state.collapsed_tasks)
                    match_index = None
                    for idx, (_, task, _) in enumerate(flat_tasks):
                        if task_obj is not None and task is task_obj:
                            match_index = idx
                            break
                    
                    self.ui_state.selected_index = match_index if match_index is not None else 0
            elif list_name:
                # Task in standalone list - open task list and find task
                task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
                if list_name not in task_lists:
                    task_lists.append(list_name)
                    self.ui_state.task_lists = task_lists
                self.ui_state.active_tab = task_lists.index(list_name)
                self.ui_state.state = AppState.TASK_LIST
                
                # Get all tasks from the list
                list_tasks = getattr(self.manager, 'list_tasks', {})
                sections = list_tasks.get(list_name, [])
                
                # Find task object by name path across all sections
                task_obj = None
                section_idx_found = 0
                for section_idx, section in enumerate(sections):
                    section_tasks = getattr(section, 'tasks', [])
                    task_obj = self._find_task_by_name_path(section_tasks, task_path)
                    if task_obj:
                        section_idx_found = section_idx
                        # Expand ancestors if collapsed
                        expanded = self._expand_task_ancestors(section_tasks, task_obj)
                        if expanded:
                            self._context.persist_collapsed_tasks()
                        break
                
                # Use the helper method from enter_handlers to select the task
                # This matches the go-to-source logic in app.py
                if task_obj:
                    layout = self._build_task_list_layout()
                    if layout:
                        # First try to find in active tasks
                        idx_map = layout.get("task_index_to_data", {})
                        section_map = layout.get("index_to_section_idx", {})
                        match_index = None
                        for idx, (_, task, _) in idx_map.items():
                            if section_map.get(idx) == section_idx_found and task is task_obj:
                                match_index = idx
                                break
                        
                        if match_index is not None:
                            self.ui_state.selected_index = match_index
                        else:
                            # Not found in active tasks - check completed section
                            completed_offset = None
                            for idx, (_, task, _, _, completed_section_idx) in enumerate(layout.get("all_completed_flat", [])):
                                if completed_section_idx == section_idx_found and task is task_obj:
                                    completed_offset = idx
                                    break
                            
                            if completed_offset is not None:
                                # If completed section is collapsed, expand it
                                if layout.get("is_completed_collapsed") and layout.get("completed_header_index") is not None:
                                    self.ui_state.collapsed_tasks.discard("section_completed")
                                    self._context.persist_collapsed_tasks()
                                    # Rebuild layout after expanding
                                    layout = self._build_task_list_layout()
                                    completed_offset = None
                                    for idx, (_, task, _, _, completed_section_idx) in enumerate(layout.get("all_completed_flat", [])):
                                        if completed_section_idx == section_idx_found and task is task_obj:
                                            completed_offset = idx
                                            break
                                
                                completed_start = layout.get("completed_items_start")
                                if completed_start is not None and completed_offset is not None:
                                    self.ui_state.selected_index = completed_start + completed_offset
                                else:
                                    self.ui_state.selected_index = 0
                            else:
                                self.ui_state.selected_index = 0
                    else:
                        self.ui_state.selected_index = 0
                else:
                    self.ui_state.selected_index = 0

            # Clear search state
            self.ui_state.search_query = ""
            self.ui_state.search_results = []
            self.ui_state.search_selected_index = 0

        elif result_type == 'bookmark':
            # Jump to bookmarks screen and find bookmark
            bookmark_id = result.get('id')
            list_id = result.get('list_id')
            
            bookmarks = getattr(self.manager, 'bookmarks', [])
            
            # Check if bookmark is inside a list
            if list_id is not None:
                # Find the bookmark list in manager.bookmarks
                list_idx = None
                bookmark_list = None
                for i, item in enumerate(bookmarks):
                    if hasattr(item, 'id') and item.id == list_id:
                        list_idx = i
                        bookmark_list = item
                        break
                
                if bookmark_list and hasattr(bookmark_list, 'items'):
                    # Find the bookmark within the list
                    bookmark_idx_in_list = None
                    for j, bookmark in enumerate(bookmark_list.items):
                        if hasattr(bookmark, 'id') and bookmark.id == bookmark_id:
                            bookmark_idx_in_list = j
                            break
                    
                    if bookmark_idx_in_list is not None and list_idx is not None:
                        # Navigate to the list view with the bookmark selected
                        self.ui_state.state = AppState.BOOKMARK_LIST
                        self.ui_state.current_list_index = list_idx
                        self.ui_state.selected_index = bookmark_idx_in_list
                    else:
                        self.ui_state.state = AppState.BOOKMARKS
                        self.ui_state.selected_index = list_idx if list_idx is not None else 0
                else:
                    # List not found, go to bookmarks screen
                    self.ui_state.state = AppState.BOOKMARKS
                    self.ui_state.selected_index = list_idx if list_idx is not None else 0
            else:
                # Standalone bookmark - find it in flat bookmarks
                bookmark_idx = 0
                for i, bookmark in enumerate(bookmarks):
                    if not hasattr(bookmark, 'items'):  # Only check non-list items
                        if getattr(bookmark, 'url', '') == bookmark_id:
                            bookmark_idx = i
                            break
                
                self.ui_state.state = AppState.BOOKMARKS
                self.ui_state.selected_index = bookmark_idx
            
            # Clear search state
            self.ui_state.search_query = ""
            self.ui_state.search_results = []
            self.ui_state.search_selected_index = 0
            
        elif result_type == 'bookmark_list':
            # Jump to bookmark list view
            list_id = result.get('id')

            bookmarks = getattr(self.manager, 'bookmarks', [])
            list_idx = None

            for i, item in enumerate(bookmarks):
                if hasattr(item, 'id') and item.id == list_id:
                    list_idx = i
                    break

            if list_idx is not None:
                self.ui_state.state = AppState.BOOKMARK_LIST
                self.ui_state.current_list_index = list_idx
                self.ui_state.selected_index = 0
            else:
                self.ui_state.state = AppState.BOOKMARKS
                self.ui_state.selected_index = 0
            # Clear search state
            self.ui_state.search_query = ""
            self.ui_state.search_results = []
            self.ui_state.search_selected_index = 0

    def handle_main_menu_enter(self):
        """Handle enter in main menu."""
        # If in inline edit mode, save changes
        if self.ui_state.inline_task_edit_mode and self.ui_state.inline_edit_task:
            task = self.ui_state.inline_edit_task
            old_name = getattr(task, "name", "")

            # Update task with edited values
            task.name = self.ui_state.inline_edit_name
            task.deadline = self.ui_state.inline_edit_deadline
            task.priority = self.ui_state.inline_edit_priority
            task.notes = self.ui_state.inline_edit_notes

            # Update pinned item metadata to reflect new name/deadline/priority/notes
            pinned_items = self.manager.metadata.get("pinned_items", [])
            task_id = getattr(task, "id", None)
            for item in pinned_items:
                if item.get("type") != "task":
                    continue
                if item.get("id") and item.get("id") != task_id:
                    continue
                if not item.get("id") and item.get("name") != old_name:
                    continue
                    # Update metadata to match new values
                    item["name"] = task.name
                    item["deadline"] = task.deadline
                    item["priority"] = task.priority
                    item["notes"] = task.notes
                    item["completed"] = getattr(task, "completed", None)
                    self.manager.mark_metadata_modified()
                    break

            # Save changes
            self.manager.save()

            # Exit inline edit mode
            self.ui_state.inline_task_edit_mode = False
            return

        def _reset_pinned_expanded_state() -> None:
            self.ui_state.expanded_pinned_lists = set()
            self.ui_state.expanded_pinned_sections = set()
            self.ui_state.expanded_pinned_list_sections = set()

        # Handle pinned section separately
        if self.ui_state.in_pinned_section:
            display_items = getattr(self.ui_state, "pinned_display_items", None)
            pinned_items = self.ui_state.reordered_pinned_items or self.manager.get_pinned_items()
            target_list = display_items or pinned_items
            if 0 <= self.ui_state.pinned_selected_index < len(target_list):
                if display_items:
                    entry = target_list[self.ui_state.pinned_selected_index]
                    kind = entry.get("kind")
                    if kind == "list_section":
                        list_name = entry.get("list_name", "")
                        section_idx = entry.get("section_idx", 0)
                        section_id = entry.get("section_id")
                        section_key = section_id or f"{list_name}:{section_idx}"
                        expanded = set(getattr(self.ui_state, "expanded_pinned_list_sections", set()))
                        if section_key in expanded:
                            expanded.remove(section_key)
                        else:
                            expanded.add(section_key)
                        self.ui_state.expanded_pinned_list_sections = expanded
                        return
                    if kind in ("list_task", "section_task"):
                        list_name = entry.get("list_name", "")
                        section_idx = entry.get("section_idx", 0)
                        section_id = entry.get("section_id")
                        if section_id:
                            resolved_list, resolved_idx, _ = self.manager.find_section_by_id(section_id)
                            if resolved_list:
                                list_name = resolved_list
                            if resolved_idx is not None:
                                section_idx = resolved_idx
                        task_name = entry.get("task_name", "")
                        list_sections = self.manager.list_tasks.get(list_name, [])
                        if 0 <= section_idx < len(list_sections):
                            section = list_sections[section_idx]
                            tasks = getattr(section, "tasks", [])

                            def _mark_first_unstarted(name: str) -> bool:
                                for t in tasks:
                                    if getattr(t, "name", None) == name and getattr(t, "completed", None) is None:
                                        t.completed = True
                                        return True
                                return False

                            if _mark_first_unstarted(task_name):
                                self.manager.mark_list_tasks_modified()
                                self.manager.save()
                        return
                    if kind != "pinned":
                        return  # Only top-level pinned entries have enter actions
                    item = entry.get("item", {})
                else:
                    item = target_list[self.ui_state.pinned_selected_index]
                item_type = item.get("type")

                if item_type == "task":
                    # Cycle task completion status: None -> True -> False -> None
                    current = item.get("completed")
                    if current is None:
                        new_status = True
                    elif current is True:
                        new_status = False
                    else:
                        new_status = None

                    # Update in pinned items
                    item["completed"] = new_status
                    self.manager.mark_metadata_modified()

                    # Also update the actual task if we can find it
                    task_id = item.get("id")
                    self.manager.update_pinned_task_status(task_id, new_status)
                    self.manager.save()

                elif item_type == "project":
                    # Navigate to project details
                    project_id = item.get("id")
                    project = self.manager.get_project(project_id)
                    if project:
                        _reset_pinned_expanded_state()
                        self.ui_state.state = AppState.PROJECT_DETAILS
                        self.ui_state.current_project_id = project_id
                        self.ui_state.selected_index = 0
                        self.ui_state.in_pinned_section = False
                        logger.info("Opening project %s from pinned items", project.name)
                    else:
                        self._set_status("Project not found", True)

                elif item_type == "bookmark":
                    # Handle bookmark action (copy or open)
                    from ..config import get_config
                    config = get_config()
                    url = item.get("url")
                    
                    if config.bookmark_action_mode == "open":
                        # Open in browser
                        try:
                            import webbrowser
                            webbrowser.open(url)
                            self._set_status(f"Opening: {item.get('title', 'Bookmark')}", False)
                        except Exception:
                            self._set_status(f"Failed to open bookmark", True)
                    else:
                        # Copy URL to clipboard (default)
                        import subprocess
                        import platform
                        try:
                            if platform.system() == "Windows":
                                subprocess.run(["clip"], input=url.encode("utf-16le"), check=True)
                            elif platform.system() == "Darwin":
                                subprocess.run(["pbcopy"], input=url.encode(), check=True)
                            else:
                                subprocess.run(["xclip", "-selection", "clipboard"], input=url.encode(), check=True)
                            # Mark this pinned bookmark as "copied" to render a green icon while selected
                            item["copied"] = True
                            self.manager.mark_metadata_modified()
                        except Exception:
                            self._set_status(f"URL: {url}")
                elif item_type == "bookmark_list":
                    from pm import BookmarkList
                    target_title = item.get("title")
                    target_index = None
                    for idx, bookmark_item in enumerate(self.manager.bookmarks):
                        if isinstance(bookmark_item, BookmarkList) and bookmark_item.title == target_title:
                            target_index = idx
                            break
                    if target_index is not None:
                        _reset_pinned_expanded_state()
                        self.ui_state.state = AppState.BOOKMARK_LIST
                        self.ui_state.current_list_index = target_index
                        self.ui_state.selected_index = 0
                        self.ui_state.in_pinned_section = False
                        logger.info("Opening bookmark list %s from pinned items", target_title)
                    else:
                        self._set_status("List not found", True)

                elif item_type == "list":
                    # Toggle expanded state for pinned list (transient UI state only)
                    list_name = item.get("name", "")
                    list_key = list_name
                    expanded_lists = set(getattr(self.ui_state, "expanded_pinned_lists", set()))
                    expanded_list_sections = set(getattr(self.ui_state, "expanded_pinned_list_sections", set()))
                    if list_key in expanded_lists:
                        expanded_lists.remove(list_key)
                    else:
                        expanded_lists.add(list_key)
                    # Reset section expansion for this list whenever the list is toggled
                    list_sections = self.manager.list_tasks.get(list_name, [])
                    section_keys = set()
                    for idx, section in enumerate(list_sections):
                        sid = section.get("id") if isinstance(section, dict) else getattr(section, "id", None)
                        section_keys.add(sid or f"{list_name}:{idx}")
                    expanded_list_sections = {
                        k
                        for k in expanded_list_sections
                        if (
                            k not in section_keys
                            and not (isinstance(k, str) and k.startswith(f"{list_name}:"))
                        )
                    }
                    self.ui_state.expanded_pinned_lists = expanded_lists
                    self.ui_state.expanded_pinned_list_sections = expanded_list_sections

                elif item_type == "section":
                    # Toggle expanded state for pinned section (transient UI state only)
                    key = item.get("id")
                    expanded_sections = set(getattr(self.ui_state, "expanded_pinned_sections", set()))
                    if key in expanded_sections:
                        expanded_sections.remove(key)
                    else:
                        expanded_sections.add(key)
                    self.ui_state.expanded_pinned_sections = expanded_sections
            return

        selected_idx = self.ui_state.selected_index
        menu_selection = self.ui_state.main_menu_tabs_selection
        quick_add_enabled = is_quick_add_enabled(menu_selection)
        menu_items = build_main_menu_items(menu_selection)

        actions = []
        if quick_add_enabled:
            actions.append("quick_add")
        actions.extend(action for _, action in menu_items)
        actions.append("settings")
        actions.append("exit")

        if selected_idx < 0 or selected_idx >= len(actions):
            logger.debug("Unhandled main menu index: %s", selected_idx)
            return

        action = actions[selected_idx]

        logger.debug("Main menu selection index %s -> %s", selected_idx, action)

        if action == "browse":
            _reset_pinned_expanded_state()
            self.ui_state.state = AppState.PROJECT_BROWSER
            self.ui_state.selected_index = 0
            self.ui_state.active_tab = 0
            logger.info("Navigating to project browser")
        elif action == "tasks":
            _reset_pinned_expanded_state()
            self.ui_state.state = AppState.TASK_LIST
            self.ui_state.selected_index = 0
            self.ui_state.active_tab = 0
            logger.info("Navigating to standalone tasks")
        elif action == "bookmarks":
            _reset_pinned_expanded_state()
            self.ui_state.state = AppState.BOOKMARKS
            self.ui_state.selected_index = 0
            logger.info("Navigating to bookmarks")
        elif action == "stats":
            _reset_pinned_expanded_state()
            self.ui_state.state = AppState.STATISTICS
            self.ui_state.selected_index = 0
            logger.info("Viewing statistics dashboard")
        elif action == "calendar":
            _reset_pinned_expanded_state()
            self.ui_state.state = AppState.CALENDAR
            self.ui_state.selected_index = 0
            from datetime import datetime
            now = datetime.now()
            self.ui_state.calendar_year = now.year
            self.ui_state.calendar_month = now.month
            self.ui_state.calendar_selected_day = now.day
            self.ui_state.calendar_navigation_focus = "day"  # Start on day selection
            self.ui_state.calendar_task_selected_index = 0
            logger.info("Viewing calendar")
        elif action == "settings":
            _reset_pinned_expanded_state()
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 0
            logger.info("Opening settings screen")
        elif action == "quick_add":
            if not self.ui_state.inline_input_mode:
                self._set_status(None)
                self.ui_state.inline_input_mode = True
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
                self.ui_state.quick_add_priority = None
                self.ui_state.quick_add_field_index = 0
                self.ui_state.selected_index = 0
                logger.debug("Quick add mode activated")
            else:
                # Handle name field - move to next field when Enter is pressed (index 0)
                if self.ui_state.quick_add_field_index == 0:
                    self.ui_state.quick_add_field_index = 1
                    return
                # Handle priority cycling when Enter is pressed on priority field (index 1)
                elif self.ui_state.quick_add_field_index == 1:
                    # Cycle through priorities: None -> !!! -> !! -> ! -> None
                    priorities = [None, "!!!", "!!", "!"]
                    current = self.ui_state.quick_add_priority
                    try:
                        current_idx = priorities.index(current)
                        next_idx = (current_idx + 1) % len(priorities)
                        self.ui_state.quick_add_priority = priorities[next_idx]
                        logger.debug("Cycled priority to: %s", self.ui_state.quick_add_priority)
                    except ValueError:
                        self.ui_state.quick_add_priority = "!!!"
                    return
                # Handle deadline field edit mode toggle when Enter is pressed on deadline field (index 2)
                elif self.ui_state.quick_add_field_index == 2:
                    if not self.ui_state.quick_add_deadline_edit_mode:
                        # Enter edit mode
                        self.ui_state.quick_add_deadline_edit_mode = True
                        self.ui_state.quick_add_deadline_component = 0
                        # Initialize with today's date if not set
                        if not self.ui_state.quick_add_deadline:
                            from datetime import datetime
                            today = datetime.now()
                            self.ui_state.quick_add_deadline = f"{today.year:04d}-{today.month:02d}-{today.day:02d}"
                        logger.debug("Entered deadline edit mode")
                    else:
                        # Exit edit mode
                        self.ui_state.quick_add_deadline_edit_mode = False
                        self.ui_state.quick_add_deadline_component = 0
                        logger.debug("Exited deadline edit mode, deadline set to: %s", self.ui_state.quick_add_deadline)
                    return
                # Handle list field cycling when Enter is pressed on list field (index 3)
                elif self.ui_state.quick_add_field_index == 3:
                    # Cycle through available task lists
                    available_lists = list(getattr(self.manager, "list_tasks", {}).keys()) if hasattr(self.manager, "list_tasks") else []
                    if not available_lists:
                        available_lists = ["Tasks"]
                    current = self.ui_state.quick_add_list
                    try:
                        current_idx = available_lists.index(current)
                        next_idx = (current_idx + 1) % len(available_lists)
                        self.ui_state.quick_add_list = available_lists[next_idx]
                        logger.debug("Cycled quick add list to: %s", self.ui_state.quick_add_list)
                    except (ValueError, IndexError):
                        self.ui_state.quick_add_list = available_lists[0] if available_lists else "Tasks"
                    return
                # Handle task addition when Enter is pressed on Add button (index 4)
                elif self.ui_state.quick_add_field_index != 4:
                    return

                is_valid, result = validate_task_name(self.ui_state.text_input_buffer)
                if not is_valid:
                    logger.warning("Quick add validation failed: %s", result)
                    self._set_status(result, True)
                    return

                task_name = result
                priority = self.ui_state.quick_add_priority
                deadline = self.ui_state.quick_add_deadline
                target_list = self.ui_state.quick_add_list

                # Add to selected task list
                try:
                    from pm import Section
                    if not hasattr(self.manager, "list_tasks") or target_list not in self.manager.list_tasks:
                        # Initialize mapping if missing with a default section
                        if not hasattr(self.manager, "list_tasks"):
                            self.manager.list_tasks = {}
                        self.manager.list_tasks[target_list] = [Section(name='', tasks=[])]

                    # Get the tasks list (list of sections)
                    tasks_list = self.manager.list_tasks.get(target_list, [])

                    # Add to first section, or create default section if empty
                    if tasks_list and hasattr(tasks_list[0], 'tasks'):
                        # Section object
                        tasks_list[0].tasks.append(Task(name=task_name, priority=priority, deadline=deadline))
                    elif tasks_list and isinstance(tasks_list[0], dict) and 'tasks' in tasks_list[0]:
                        # Section dict
                        tasks_list[0]['tasks'].append(Task(name=task_name, priority=priority, deadline=deadline))
                    else:
                        # Empty or old format - wrap in section
                        default_section = Section(name='', tasks=[Task(name=task_name, priority=priority, deadline=deadline)])
                        self.manager.list_tasks[target_list] = [default_section]

                    self.manager.mark_list_tasks_modified()
                except Exception as e:
                    # Fallback to legacy list
                    self.manager.standalone_tasks.append(Task(name=task_name, priority=priority, deadline=deadline))
                    self.manager.mark_standalone_tasks_modified()

                self.manager.save()
                self._set_status(None)

                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self.ui_state.quick_add_priority = None
                self.ui_state.quick_add_field_index = 0
                self.ui_state.quick_add_deadline = None
                self.ui_state.quick_add_deadline_component = 0
                self.ui_state.quick_add_deadline_edit_mode = False
                self.ui_state.quick_add_list = "Tasks"
        elif action == "exit":
            logger.info("Exit selected from main menu")
            self.manager.force_save()
            self._exit_application()

    def handle_project_browser_enter(self):
        """Handle enter in project browser."""
        # Header row: toggle sort by the selected column
        if self.ui_state.selected_index == -1:
            self._apply_project_sort()
            return

        # Handle cell editing mode
        if self.ui_state.cell_editing:
            self._save_cell_edit()
            return

        # Handle cell selection mode - enter edit mode for selected cell
        if self.ui_state.cell_selection_mode:
            self._enter_cell_edit_mode()
            return

        filtered = self._get_filtered_projects_sorted()

        if self.ui_state.selected_index < len(filtered):
            self._set_status(None)
            # View project details
            selected_project = filtered[self.ui_state.selected_index]
            self.ui_state.project_browser_selected_index = self.ui_state.selected_index
            self.ui_state.project_browser_selected_project_id = selected_project.id
            self.ui_state.current_project_id = selected_project.id
            self.ui_state.state = AppState.PROJECT_DETAILS
            self.ui_state.selected_index = 0
        elif self.ui_state.selected_index == len(filtered):
            self.start_add_project_form()
        elif self.ui_state.selected_index == len(filtered) + 1:
            self._set_status(None)
            # Customize fields
            self.ui_state.state = AppState.CUSTOMIZE_FIELDS
            self.ui_state.selected_index = 0
        else:
            self._set_status(None)
            # Back to main menu
            self.ui_state.state = AppState.MAIN_MENU
            self.ui_state.selected_index = 0
            self.ui_state.project_sort_key = None
            self.ui_state.project_sort_order = None

    def handle_project_details_enter(self):
        """Handle enter in project details."""
        project = self.manager.get_project(self.ui_state.current_project_id)
        if not project:
            return

        # Build flat list of all tasks (show pending, completed, and failed together)
        flat_tasks = self._get_flat_tasks(project.tasks, True)

        # Index mapping and layout
        add_index = len(flat_tasks)
        actions_start_index = add_index + 1

        selected = self.ui_state.selected_index

        # Toggle task (tri-state handled by toggle_task_completion)
        if selected < len(flat_tasks):
            task_id, task, _ = flat_tasks[selected]
            pinned_task_id = getattr(task, "id", None)
            toggle_task_completion(
                self.manager,
                self.ui_state.current_project_id,
                getattr(task, "id", ""),
                False,
                pinned_task_id=pinned_task_id,
            )
            self._invalidate_task_cache()
            self._set_status(None)
            return

        # Add new task - begin inline edit flow like the Tasks tab (name/deadline/priority inline)
        if selected == add_index:
            self._set_status(None)
            self.start_inline_task_add_for_project()
            return

        # Actions after tasks
        # 0: Change Project Status, 1: Edit Project, 2: Back to Projects
        action_idx = selected - actions_start_index
        if action_idx == 0:
            self._set_status(None)
            self.ui_state.state = AppState.CHANGE_STATUS
            self.ui_state.selected_index = 0
            logger.info("Opening change status dialog for project %s", self.ui_state.current_project_id)
        elif action_idx == 1:
            project = self.manager.get_project(self.ui_state.current_project_id)
            if project:
                self.ui_state.form_data = {
                    "name": project.name,
                    "description": project.description,
                    "status": project.status,
                }
                # Pre-fill custom fields (including built-ins like timeframe)
                self.ui_state.form_data.update(project.custom_field_values)
            else:
                self.ui_state.form_data = {}
            self._set_status(None)
            self.ui_state.previous_state = self.ui_state.state
            self.ui_state.state = AppState.EDIT_PROJECT
            self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            logger.info("Opening edit project form for project %s", self.ui_state.current_project_id)
        elif action_idx == 2:
            # Back to projects
            self._set_status(None)
            self.ui_state.state = AppState.PROJECT_BROWSER
            self._restore_project_browser_selection(self.ui_state.current_project_id)
            logger.info("Returning to project browser from project details")

    def handle_task_list_enter(self):
        """Handle enter in standalone task list view."""
        layout = self._build_task_list_layout()
        if not layout:
            return

        task_lists = layout["task_lists"]
        active_tab = layout["active_tab"]
        active_list_name = layout["active_list_name"]
        list_tasks_map = layout["list_tasks_map"]
        all_section_data = layout["all_section_data"]
        index_to_section_idx = layout["index_to_section_idx"]
        show_section_headers = layout["show_section_headers"]
        section_header_indices = layout["section_header_indices"]
        section_add_indices = layout["section_add_indices"]
        section_idx_to_id = layout.get("section_idx_to_id", {})
        task_index_to_data = layout["task_index_to_data"]
        all_completed_flat = layout["all_completed_flat"]
        add_index = layout["add_index"]
        completed_header_index = layout["completed_header_index"]
        is_completed_collapsed = layout["is_completed_collapsed"]
        completed_items_start = layout["completed_items_start"]
        new_list_index = layout["new_list_index"]
        can_edit_tab = layout["can_edit_tab"]
        edit_tab_index = layout["edit_tab_index"]
        back_index = layout["back_index"]

        selected = self.ui_state.selected_index

        # Toggle section collapse/expand
        if show_section_headers:
            for section_idx, header_idx in section_header_indices.items():
                if selected == header_idx:
                    section_id = section_idx_to_id.get(section_idx)
                    section_collapse_key = f"section:{section_id}"
                    if section_collapse_key in self.ui_state.collapsed_tasks:
                        self.ui_state.collapsed_tasks.discard(section_collapse_key)
                    else:
                        self.ui_state.collapsed_tasks.add(section_collapse_key)
                    self._invalidate_task_cache()
                    self._context.persist_collapsed_tasks()
                    return

        # Toggle pending task
        if selected in task_index_to_data:
            task_id, task, section_tasks = task_index_to_data[selected]
            section_idx = index_to_section_idx.get(selected, 0)
            pinned_task_id = getattr(task, "id", None)
            changed = toggle_task_completion(
                self.manager,
                self.ui_state.current_project_id,
                getattr(task, "id", ""),
                True,
                task_list_override=section_tasks,
                pinned_task_id=pinned_task_id,
            )
            if changed:
                try:
                    self.manager.mark_list_tasks_modified()
                    self.manager.save()
                except Exception:
                    pass
                self._invalidate_task_cache()
                self._set_status(None)
            return

        # Add new task to specific section or global
        target_section_idx = None
        new_task_index = None
        if show_section_headers:
            # Check if selected matches any section's + button
            for section_idx, add_idx in section_add_indices.items():
                if selected == add_idx:
                    target_section_idx = section_idx
                    new_task_index = add_idx  # New task will appear where + used to be
                    break
        elif add_index is not None and selected == add_index:
            # Single + button for normal list - add to first section
            target_section_idx = 0
            new_task_index = add_index

        if target_section_idx is not None:
            self.start_inline_task_add_for_list(target_section_idx, layout)
            return

        # Toggle completed section collapse (only when Done section is shown)
        if completed_header_index is not None and selected == completed_header_index:
            if is_completed_collapsed:
                self.ui_state.collapsed_tasks.discard("section_completed")
            else:
                self.ui_state.collapsed_tasks.add("section_completed")
            self._invalidate_task_cache()
            self._context.persist_collapsed_tasks()
            return

        # Toggle a completed task (only when Done section is shown)
        if (
            completed_items_start is not None
            and (not is_completed_collapsed)
            and (completed_items_start <= selected < completed_items_start + len(all_completed_flat))
        ):
            idx = selected - completed_items_start
            task_id, task, _, section_tasks, section_idx = all_completed_flat[idx]
            pinned_task_id = getattr(task, "id", None)
            changed = toggle_task_completion(
                self.manager,
                self.ui_state.current_project_id,
                getattr(task, "id", ""),
                True,
                task_list_override=section_tasks,
                pinned_task_id=pinned_task_id,
            )
            if changed:
                try:
                    self.manager.mark_list_tasks_modified()
                    self.manager.save()
                except Exception:
                    pass
                self._invalidate_task_cache()
                self._set_status(None)
            return

        # Handle New list creation
        if selected == new_list_index:
            from pm import Section
            self._set_status(None)
            # Done section should always reset to collapsed when leaving the task list.
            self.ui_state.collapsed_tasks.add("section_completed")
            self.ui_state.state = AppState.EDIT_TAB
            self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            self.ui_state.editing_list_name = None  # None = creating new list
            # Initialize with normal mode and no sections
            self.ui_state.form_data = {
                "name": "",
                "color": "white",  # Default color
                "mode": "normal",
                "show_done_section": "section",  # Default to showing done section
                "sections": []
            }
            logger.info("Opening create list dialog")
            return

        # Handle Edit List (only for non-default tabs)
        if can_edit_tab and selected == edit_tab_index:
            from pm import Section
            self._set_status(None)
            # Done section should always reset to collapsed when leaving the task list.
            self.ui_state.collapsed_tasks.add("section_completed")
            self.ui_state.state = AppState.EDIT_TAB
            self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            self.ui_state.editing_list_name = task_lists[active_tab]  # Name of list being edited

            # Load sections from current list
            current_sections = list_tasks_map.get(active_list_name, [])
            sections_data = []
            if current_sections:
                # Convert Section objects to dicts for form_data
                for section in current_sections:
                    section_name = section.name if hasattr(section, 'name') else section.get('name', '')
                    section_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])
                    sections_data.append({
                        'name': section_name,
                        'tasks': section_tasks
                    })
            else:
                # Fallback: create default section if none exist
                sections_data = [{"name": "", "tasks": []}]

            # Detect mode based on sections structure
            # Normal mode: single unnamed section
            # Sections mode: multiple sections OR single named section
            if len(sections_data) == 1 and sections_data[0]['name'] == '':
                list_mode = 'normal'
                # Keep the section data for saving, even though it won't be displayed
                # This preserves tasks when user edits but doesn't change mode
            else:
                list_mode = 'sections'

            # Get current color and show_done_section from list_metadata
            list_metadata = self.manager.list_metadata.get(active_list_name, {})
            list_color = list_metadata.get("color", "white")
            show_done_section = list_metadata.get("show_done_section", "section")

            self.ui_state.form_data = {
                "name": active_list_name,
                "color": list_color,
                "mode": list_mode,
                "show_done_section": show_done_section,
                "sections": sections_data
            }
            logger.info("Opening edit list dialog for list '%s'", active_list_name)
            return

        # Back to main menu
        if selected == back_index:
            self._set_status(None)
            # Done section should always reset to collapsed when leaving the task list.
            self.ui_state.collapsed_tasks.add("section_completed")
            self.ui_state.state = AppState.MAIN_MENU
            self.ui_state.selected_index = 0
            return

    def handle_change_status_enter(self):
        """Handle enter in change status."""
        status_options = STATUS_DISPLAY_ORDER + ["Cancel"]
        selected_status = status_options[self.ui_state.selected_index]

        if selected_status != "Cancel":
            project = self.manager.get_project(self.ui_state.current_project_id)
            if project:
                project.status = selected_status
                self.manager.update_project(project)
                logger.info("Project %s status changed to %s", project.id, selected_status)

        # Back to project details
        self.ui_state.state = AppState.PROJECT_DETAILS
        self.ui_state.selected_index = 0

    def handle_add_project_enter(self):
        """Handle enter in add project form (reuses edit project layout)."""
        form_handlers = self.form_handlers
        manager = self.manager
        
        # Get temp project
        project = getattr(self.ui_state, '_temp_project', None)
        if not project:
            return

        all_fields = get_all_fields(manager.default_field_visibility, manager.custom_field_definitions)
        editable_fields = get_edit_project_field_keys(all_fields)
        total_fields = len(editable_fields)

        if self.ui_state.form_field_index < total_fields:
            # Edit field
            field_name = editable_fields[self.ui_state.form_field_index]
            form_handlers.edit_form_field(field_name, is_add_form=False, project=project)
        elif self.ui_state.form_field_index == total_fields:
            # Create Project (first action button)
            if "name" in self.ui_state.form_data:
                is_valid, result = validate_project_name(self.ui_state.form_data["name"])
                if not is_valid:
                    self._set_status(result, True)
                    return
                project.name = result
            else:
                if not project.name:
                    self._set_status("Project name is required.", True)
                    return

            if "status" in self.ui_state.form_data:
                project.status = self.ui_state.form_data["status"]

            # Assign real ID and add to manager
            project.id = self.manager.next_id()
            
            # Persist custom field values (including built-in custom fields)
            for field in all_fields:
                if field.key in self.ui_state.form_data:
                    new_value = self.ui_state.form_data[field.key]
                    if new_value is None or new_value == "":
                        continue
                    project.custom_field_values[field.key] = new_value
                    # Keep legacy attributes in sync for built-in fields
                    if field.key == "timeframe":
                        setattr(project, field.key, new_value)
            
            self.manager.add_project(project)
            self.ui_state.form_data = {}
            self.ui_state._temp_project = None
            self.ui_state.state = AppState.PROJECT_BROWSER
            self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            self._set_status(None)
        else:
            # Cancel (second action button)
            self.ui_state.form_data = {}
            self.ui_state._temp_project = None
            self.ui_state.state = AppState.PROJECT_BROWSER
            self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            self._set_status(None)

    def handle_edit_project_enter(self):
        """Handle enter in edit project form."""
        form_handlers = self.form_handlers

        project = self.manager.get_project(self.ui_state.current_project_id)
        if not project:
            return

        all_fields = get_all_fields(self.manager.default_field_visibility, self.manager.custom_field_definitions)
        editable_fields = get_edit_project_field_keys(all_fields)
        total_fields = len(editable_fields)

        if self.ui_state.form_field_index < total_fields:
            # Edit field
            field_name = editable_fields[self.ui_state.form_field_index]
            form_handlers.edit_form_field(field_name, is_add_form=False, project=project)
        elif self.ui_state.form_field_index == total_fields:
            # Save changes
            if "name" in self.ui_state.form_data:
                is_valid, result = validate_project_name(self.ui_state.form_data["name"])
                if not is_valid:
                    self._set_status(result, True)
                    return
                project.name = result

            if "description" in self.ui_state.form_data:
                project.description = sanitize_input(self.ui_state.form_data["description"])

            if "status" in self.ui_state.form_data:
                project.status = self.ui_state.form_data["status"]

            # Persist custom field values (including built-in custom fields)
            for field in all_fields:
                if field.key in self.ui_state.form_data:
                    new_value = self.ui_state.form_data[field.key]
                else:
                    new_value = project.custom_field_values.get(field.key, getattr(project, field.key, None))

                if new_value is None or new_value == "":
                    project.custom_field_values.pop(field.key, None)
                    continue

                project.custom_field_values[field.key] = new_value

                # Keep legacy attributes in sync for built-in fields
                if field.key == "timeframe":
                    setattr(project, field.key, new_value)
            self.manager.update_project(project)
            self.ui_state.form_data = {}
            target_state = self.ui_state.previous_state or AppState.PROJECT_DETAILS
            self.ui_state.state = target_state
            self.ui_state.previous_state = None  # Clear it
            if target_state == AppState.PROJECT_BROWSER:
                self._restore_project_browser_selection(project.id)
            else:
                self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            self._set_status(None)
        elif self.ui_state.form_field_index == total_fields + 1:
            # Delete project - show confirmation
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""

            # Store delete context for confirmation
            self.ui_state.delete_context = {
                'delete_type': 'project',
                'previous_state': AppState.EDIT_PROJECT,
                'previous_selected_index': 0,
                'previous_form_field_index': self.ui_state.form_field_index,
                'delete_params': {
                    'project_id': self.ui_state.current_project_id,
                    'project_name': project.name
                }
            }

            # Transition to confirmation dialog
            self.ui_state.state = AppState.DELETE_CONFIRMATION
            self.ui_state.form_field_index = 1  # Default to "No" for safety
            logger.info("Showing delete confirmation for project '%s'", project.name)
            self._set_status(None)
        else:
            # Cancel (index after delete)
            self.ui_state.form_data = {}
            target_state = self.ui_state.previous_state or AppState.PROJECT_DETAILS
            self.ui_state.state = target_state
            self.ui_state.previous_state = None  # Clear it
            if target_state == AppState.PROJECT_BROWSER:
                self._restore_project_browser_selection(project.id)
            else:
                self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            self._set_status(None)

    def handle_settings_enter(self):
        """Handle enter in settings."""
        settings_items = ["clear_completed", "quick_stats", "main_menu_tabs", "deadline_display", "project_browser_tab", "message_display", "stats_none_toggle", "bookmark_action", "export_data", "clear_logs", "help_overlay"]
        selected_idx = self.ui_state.selected_index

        if selected_idx == 0:
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""

            # Store delete context for confirmation
            self.ui_state.delete_context = {
                'delete_type': 'clear_completed',
                'previous_state': AppState.SETTINGS,
                'previous_selected_index': self.ui_state.selected_index,
                'delete_params': {}
            }

            # Transition to confirmation dialog
            self.ui_state.state = AppState.DELETE_CONFIRMATION
            self.ui_state.form_field_index = 1  # Default to "No" for safety
            logger.info("Showing delete confirmation for clearing completed tasks")
        elif selected_idx == 1:
            # Configure quick stats selection
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
            self.ui_state.state = AppState.QUICK_STATS_SETTINGS
            self.ui_state.selected_index = 0
        elif selected_idx == 2:
            # Configure main menu tabs selection
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
            self.ui_state.state = AppState.MAIN_MENU_TABS_SETTINGS
            self.ui_state.selected_index = 0
        elif selected_idx == 3:
            # Configure deadline display mode
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
            self.ui_state.state = AppState.DEADLINE_SETTINGS
            self.ui_state.selected_index = 0
        elif selected_idx == 4:
            # Configure project browser default tab
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
            self.ui_state.state = AppState.PROJECT_BROWSER_TAB_SETTINGS
            self.ui_state.selected_index = 0
        elif selected_idx == 5:
            # Configure status message display
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
            self.ui_state.state = AppState.MESSAGE_DISPLAY_SETTINGS
            self.ui_state.selected_index = 0
        elif selected_idx == 6:
            # Configure stats none display
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
            self.ui_state.state = AppState.STATS_NONE_SETTINGS
            self.ui_state.selected_index = 0
        elif selected_idx == 7:
            # Configure bookmark action mode
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
            self.ui_state.state = AppState.BOOKMARK_ACTION_SETTINGS
            self.ui_state.selected_index = 0
        elif selected_idx == 8:
            # Export data (copy projects.json)
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
            export_status = self.manager.export_data()
            if export_status['success']:
                self._set_status(f"Data exported to {export_status['filename']} in Downloads", False)
            else:
                self._set_status(f"Export failed: {export_status['error']}", True)
        elif selected_idx == 9:
            # Clear logs
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
            try:
                from ..config import get_config
                config = get_config()
                log_path = Path(config.log_file_path).expanduser()
                if log_path.exists():
                    # Get file size before clearing
                    file_size = log_path.stat().st_size
                    # Format file size
                    if file_size < 1024:
                        size_str = f"{file_size} B"
                    elif file_size < 1024 * 1024:
                        size_str = f"{file_size / 1024:.1f} KB"
                    else:
                        size_str = f"{file_size / (1024 * 1024):.1f} MB"
                    # Clear the file
                    log_path.write_text("", encoding="utf-8")
                    self._set_status(f"Log file cleared ({size_str})", False)
                else:
                    self._set_status("Log file not found", False)
                logger.info("Log file cleared by user")
            except Exception as exc:
                logger.error("Failed to clear log file: %s", exc)
                self._set_status(f"Failed to clear logs: {str(exc)}", True)
        elif selected_idx == 10:
            # Show all keybindings overlay from settings
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
            self.ui_state.show_help = True
            self.ui_state.show_all_keybindings = True
            self._set_status(None)
        elif selected_idx == 11:
            # Back to main menu
            self.ui_state.state = AppState.MAIN_MENU
            self.ui_state.selected_index = 0
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
        else:
            # Back to main menu
            self.ui_state.state = AppState.MAIN_MENU
            self.ui_state.selected_index = 0
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""

    def handle_quick_stats_settings_enter(self):
        """Handle enter in quick stats configuration."""
        metrics = list(QUICK_STATS_ORDER)
        selected_idx = self.ui_state.selected_index

        if selected_idx < len(metrics):
            key = metrics[selected_idx]
            updated_selection = set(self.ui_state.quick_stats_selection)
            toggled_on = key not in updated_selection
            if toggled_on:
                updated_selection.add(key)
            else:
                updated_selection.discard(key)

            normalized = normalize_quick_stats_selection(updated_selection)
            self._context.update_quick_stats_selection(normalized)

            self._set_status(None)
        else:
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 1
            self._set_status(None)

    def handle_main_menu_tabs_settings_enter(self):
        """Handle enter in main menu tabs configuration."""
        tabs = list(MAIN_MENU_TABS_ORDER)
        selected_idx = self.ui_state.selected_index

        if selected_idx < len(tabs):
            key = tabs[selected_idx]
            updated_selection = set(self.ui_state.main_menu_tabs_selection)
            toggled_on = key not in updated_selection
            if toggled_on:
                updated_selection.add(key)
            else:
                updated_selection.discard(key)

            normalized = normalize_main_menu_tabs(updated_selection)
            self._context.update_main_menu_tabs_selection(normalized)

            self._set_status(None)
        else:
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 2
            self._set_status(None)

    def handle_deadline_settings_enter(self):
        """Handle enter in deadline display configuration."""
        from ..config import get_config, set_config, save_config

        options = ["relative", "date"]
        selected_idx = self.ui_state.selected_index

        if selected_idx < len(options):
            # Toggle deadline display mode
            new_mode = options[selected_idx]
            config = get_config()
            config.deadline_display_mode = new_mode
            set_config(config)
            save_config(config)

            self._set_status(None)
        else:
            # Back to settings
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 3
            self._set_status(None)

    def handle_project_browser_tab_settings_enter(self):
        """Handle enter in project browser default tab configuration."""
        from ..config import get_config, set_config, save_config

        options = ["all", "active"]
        selected_idx = self.ui_state.selected_index

        if selected_idx < len(options):
            # Set project browser default tab
            new_default = options[selected_idx]
            config = get_config()
            config.project_browser_default_tab = new_default
            set_config(config)
            save_config(config)

            self._set_status(None)
        else:
            # Back to settings
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 4
            self._set_status(None)

    def handle_stats_none_settings_enter(self):
        """Handle enter in project stats none display configuration."""
        from ..config import get_config, set_config, save_config

        options = ["on", "off"]
        selected_idx = self.ui_state.selected_index

        if selected_idx < len(options):
            # Toggle stats none display
            show_none = selected_idx == 0  # "on" is index 0
            config = get_config()
            config.show_none_in_stats = show_none
            set_config(config)
            save_config(config)

            self._set_status(None)
        else:
            # Back to settings
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 6
            self._set_status(None)

    def handle_message_display_settings_enter(self):
        """Handle enter in status message display configuration."""
        from ..config import get_config, set_config, save_config

        options = ["all", "errors_only"]
        selected_idx = self.ui_state.selected_index

        if selected_idx < len(options):
            config = get_config()
            config.status_message_mode = options[selected_idx]
            set_config(config)
            save_config(config)

            self._set_status(None)
        else:
            # Back to settings
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 5
            self._set_status(None)

    def handle_notes_display_settings_enter(self):
        """Handle enter in notes display configuration."""
        from ..config import get_config, set_config, save_config

        options = ["dynamic", "always"]
        selected_idx = self.ui_state.selected_index

        if selected_idx < len(options):
            config = get_config()
            config.notes_display_mode = options[selected_idx]
            set_config(config)
            save_config(config)

            self._set_status(None)
        else:
            # Back to settings
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 5
            self._set_status(None)

    def handle_bookmark_action_settings_enter(self):
        """Handle enter in bookmark action mode configuration."""
        from ..config import get_config, set_config, save_config

        options = ["copy", "open"]
        selected_idx = self.ui_state.selected_index

        if selected_idx < len(options):
            # Set bookmark action mode
            mode = options[selected_idx]
            config = get_config()
            config.bookmark_action_mode = mode
            set_config(config)
            save_config(config)

            self._set_status(None)
        else:
            # Back to settings
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 7
            self._set_status(None)

    def handle_delete_confirmation_enter(self):
        """Handle enter key in delete confirmation dialog."""
        if not self.ui_state.delete_context:
            # No delete context, just return to main menu
            self.ui_state.state = AppState.MAIN_MENU
            self.ui_state.selected_index = 0
            return

        if self.ui_state.form_field_index == 0:
            # User selected "Yes, delete it"
            delete_type = self.ui_state.delete_context.get('delete_type')
            delete_params = self.ui_state.delete_context.get('delete_params', {})
            previous_state = self.ui_state.delete_context.get('previous_state', AppState.MAIN_MENU)
            previous_selected_index = self.ui_state.delete_context.get('previous_selected_index', 0)
            previous_form_field_index = self.ui_state.delete_context.get('previous_form_field_index')
            previous_pinned_selected_index = self.ui_state.delete_context.get('previous_pinned_selected_index')
            previous_in_pinned_section = self.ui_state.delete_context.get('previous_in_pinned_section', False)

            # Execute the appropriate delete operation
            success = False
            if delete_type == 'task' and self.task_handlers:
                success = self.task_handlers.execute_confirmed_delete(delete_params)
            elif delete_type in ['bookmark', 'bookmark_from_list', 'bookmark_list_from_within', 'edit_list_bookmark'] and self.bookmark_handlers:
                success = self.bookmark_handlers.execute_confirmed_delete(delete_params, delete_type)
            elif delete_type == 'clear_completed':
                success = self.execute_clear_completed_tasks()
            elif delete_type == 'edit_list_delete':
                success = self.execute_delete_list(delete_params)
            elif delete_type == 'custom_field':
                success = self.execute_delete_custom_field(delete_params)
            elif delete_type == 'project':
                success = self.execute_delete_project(delete_params)
            elif delete_type == 'pinned_item':
                success = self.execute_delete_pinned_item(delete_params)
            elif delete_type == 'calendar_task':
                success = self.execute_delete_calendar_task(delete_params)

            # Return to previous state (or special state for some delete types)
            if delete_type == 'edit_list_delete' and success:
                self.ui_state.state = AppState.TASK_LIST
                self.ui_state.selected_index = 0
                self.ui_state.form_data = {}
                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self.ui_state.editing_list_name = None
            elif delete_type == 'bookmark_list_from_within' and success:
                # Go back to bookmarks after deleting a list
                self.ui_state.state = AppState.BOOKMARKS
                self.ui_state.selected_index = 0
                self.ui_state.current_list_index = None
            elif delete_type == 'project' and success:
                # Go back to project browser after deleting a project
                self.ui_state.state = AppState.PROJECT_BROWSER
                self.ui_state.selected_index = 0
                self.ui_state.form_data = {}
            else:
                self.ui_state.state = previous_state

            # Adjust selected_index if delete was successful
            if success and delete_type not in ['edit_list_delete', 'bookmark_list_from_within', 'pinned_item']:
                # For edit_list_bookmark, need to restore form_field_index and adjust it
                if delete_type == 'edit_list_bookmark':
                    bookmarks = self.ui_state.form_data.get('bookmarks', [])
                    bookmark_index = delete_params.get('bookmark_index', 0)

                    # Adjust form_field_index to stay in a valid position
                    if not bookmarks:
                        # Move to list title if no bookmarks left
                        self.ui_state.form_field_index = 0
                    elif bookmark_index > 0:
                        # Move to the previous bookmark's title field
                        self.ui_state.form_field_index = (bookmark_index - 1) * 2 + 1
                    else:
                        # Move to list title if we deleted the first bookmark
                        self.ui_state.form_field_index = 0
                else:
                    # For other delete types, adjust selected_index
                    # Get the current item count to determine max index
                    max_index = self._get_max_index_for_state(previous_state)
                    if previous_selected_index > max_index:
                        self.ui_state.selected_index = max(0, max_index)
                    else:
                        self.ui_state.selected_index = previous_selected_index

            # Restore pinned navigation state after pinned deletes
            if delete_type == 'pinned_item':
                previous_pinned_selected_index = self.ui_state.delete_context.get('previous_pinned_selected_index', 0)
                previous_in_pinned_section = self.ui_state.delete_context.get('previous_in_pinned_section', False)
                if previous_in_pinned_section:
                    pinned_len = len(self.manager.get_pinned_items())
                    if pinned_len == 0:
                        self.ui_state.in_pinned_section = False
                        self.ui_state.pinned_selected_index = 0
                    else:
                        self.ui_state.in_pinned_section = True
                        self.ui_state.pinned_selected_index = min(previous_pinned_selected_index, pinned_len - 1)

            # Clear delete context
            self.ui_state.delete_context = None

        else:
            # User selected "No, cancel" (or navigated to it)
            # Restore previous state without deleting
            previous_state = self.ui_state.delete_context.get('previous_state', AppState.MAIN_MENU)
            previous_selected_index = self.ui_state.delete_context.get('previous_selected_index', 0)
            previous_form_field_index = self.ui_state.delete_context.get('previous_form_field_index')
            previous_pinned_selected_index = self.ui_state.delete_context.get('previous_pinned_selected_index')
            previous_in_pinned_section = self.ui_state.delete_context.get('previous_in_pinned_section', False)

            self.ui_state.state = previous_state
            self.ui_state.selected_index = previous_selected_index

            # Restore form_field_index if it was stored (for form states)
            if previous_form_field_index is not None:
                self.ui_state.form_field_index = previous_form_field_index
            else:
                self.ui_state.form_field_index = 0

            if previous_in_pinned_section and previous_pinned_selected_index is not None:
                self.ui_state.in_pinned_section = True
                self.ui_state.pinned_selected_index = previous_pinned_selected_index

            # Clear delete context
            self.ui_state.delete_context = None
            logger.info("Cancelled delete confirmation")

    def _get_max_index_for_state(self, state: AppState) -> int:
        """Get the maximum valid index for a given state after deletion."""
        if state == AppState.BOOKMARKS:
            return max(0, len(self.manager.bookmarks) - 1)
        elif state == AppState.BOOKMARK_LIST:
            if self.ui_state.current_list_index is not None:
                from pm import BookmarkList
                bookmark_list = self.manager.bookmarks[self.ui_state.current_list_index]
                if isinstance(bookmark_list, BookmarkList):
                    # Items + Add + Rename + Delete + Back
                    return len(bookmark_list.items) + 3
        elif state == AppState.CUSTOMIZE_FIELDS:
            # Built-in fields (3) + custom fields + actions (2)
            builtin_count = 3
            custom_count = len(self.manager.custom_field_definitions)
            return builtin_count + custom_count + 1  # +1 for Add/Back actions
        # For other states, return 0 as a safe default
        return 0

    def handle_edit_list_enter(self):
        """Handle enter in edit/create list form with sections."""
        from pm import Section, LIST_COLOR_OPTIONS
        form_field_index = self.ui_state.form_field_index
        form_data = self.ui_state.form_data
        editing_list_name = self.ui_state.editing_list_name
        is_creating = editing_list_name is None

        # Get mode and sections
        mode = form_data.get('mode', 'normal')
        use_sections = mode == 'sections'
        sections = form_data.get('sections', [])

        # Calculate field indices based on mode
        # Field layout: 0=Name, 1=Color, 2=Done Section, 3=Mode, 4+=Sections
        if use_sections:
            add_section_idx = 4 + len(sections)
            save_idx = add_section_idx + 1
        else:
            add_section_idx = None
            save_idx = 4

        # When editing: Save, Pin, Delete, Cancel
        # When creating: Save, Cancel (no Pin or Delete)
        pin_idx = save_idx + 1
        delete_idx = pin_idx + 1
        cancel_idx = delete_idx + 1

        if form_field_index == 0:
            # Edit list name field
            if self.ui_state.inline_input_mode:
                # Already in inline mode, save the name and move to next field
                new_name = sanitize_input(self.ui_state.text_input_buffer).strip()
                if not new_name:
                    if is_creating:
                        self._set_status("Enter a list name.", True)
                        return
                    # If editing and name is empty, keep the old name
                    new_name = editing_list_name

                form_data['name'] = new_name
                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
                self._set_status(None)
            else:
                # Enter inline input mode
                self._set_status(None)
                self.ui_state.inline_input_mode = True
                self.ui_state.text_input_buffer = form_data.get("name", "")
                self.ui_state.text_input_cursor = len(self.ui_state.text_input_buffer)
        elif form_field_index == 1:
            # Toggle color (cycle through available colors)
            current_color = form_data.get('color', 'white')
            try:
                current_idx = LIST_COLOR_OPTIONS.index(current_color)
                next_idx = (current_idx + 1) % len(LIST_COLOR_OPTIONS)
                form_data['color'] = LIST_COLOR_OPTIONS[next_idx]
            except ValueError:
                form_data['color'] = LIST_COLOR_OPTIONS[0]
        elif form_field_index == 2:
            # Cycle through "Done Display" modes
            from pm import DONE_DISPLAY_OPTIONS
            current = form_data.get('show_done_section', 'section')
            # Handle legacy boolean values
            if isinstance(current, bool):
                current = 'section' if current else 'inline'
            # Cycle through options
            if current not in DONE_DISPLAY_OPTIONS:
                next_value = DONE_DISPLAY_OPTIONS[0]
            else:
                idx = DONE_DISPLAY_OPTIONS.index(current)
                next_value = DONE_DISPLAY_OPTIONS[(idx + 1) % len(DONE_DISPLAY_OPTIONS)]
            form_data['show_done_section'] = next_value
        elif form_field_index == 3:
            # Toggle mode between normal and sections
            current_mode = form_data.get('mode', 'normal')
            if current_mode == 'normal':
                form_data['mode'] = 'sections'
                # Preserve existing tasks when switching to sections mode
                # Get the current list's tasks from the actual data
                list_tasks_map = getattr(self.ui_state, "list_tasks", {})
                current_list_name = editing_list_name or form_data.get('name', '')
                if current_list_name and current_list_name in list_tasks_map:
                    current_sections = list_tasks_map[current_list_name]
                    # Extract tasks from the unnamed section (normal mode has single unnamed section)
                    if current_sections and len(current_sections) == 1:
                        section = current_sections[0]
                        section_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])
                        # Store tasks to be added to first new section
                        form_data['pending_tasks'] = section_tasks
                    else:
                        form_data['pending_tasks'] = []
                else:
                    form_data['pending_tasks'] = []
                # Clear sections when switching to sections mode
                form_data['sections'] = []
            else:
                form_data['mode'] = 'normal'
                # Don't clear pending_tasks - they will be merged when saving in normal mode
        elif use_sections and 4 <= form_field_index < add_section_idx:
            # Edit a section name (only in sections mode)
            section_idx = form_field_index - 4
            if 0 <= section_idx < len(sections):
                section = sections[section_idx]
                if self.ui_state.inline_input_mode:
                    # Already in inline mode, save the section name
                    is_valid, result = validate_section_name(self.ui_state.text_input_buffer)
                    if not is_valid:
                        self._set_status(result, True)
                        return

                    section['name'] = result
                    form_data['sections'] = sections
                    self.ui_state.inline_input_mode = False
                    self.ui_state.text_input_buffer = ""
                    self.ui_state.text_input_cursor = 0
                    self._set_status(None)
                else:
                    # Enter inline mode to edit section name
                    self._set_status(None)
                    self.ui_state.inline_input_mode = True
                    self.ui_state.text_input_buffer = section.get('name', '')
                    self.ui_state.text_input_cursor = len(self.ui_state.text_input_buffer)
        elif use_sections and form_field_index == add_section_idx:
            # Add new section (only in sections mode)
            if self.ui_state.inline_input_mode:
                # Already in inline mode, save the new section
                is_valid, result = validate_section_name(self.ui_state.text_input_buffer)
                if not is_valid:
                    self._set_status(result, True)
                    return

                # Check if this is the first section and there are pending tasks
                pending_tasks = form_data.get('pending_tasks', [])
                if not sections and pending_tasks:
                    # This is the first section, add the pending tasks
                    new_section = {
                        'name': result,
                        'tasks': pending_tasks
                    }
                    # Clear pending tasks after using them
                    form_data.pop('pending_tasks', None)
                else:
                    new_section = {
                        'name': result,
                        'tasks': []
                    }
                sections.append(new_section)
                form_data['sections'] = sections
                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
                self._set_status(None)
                # Keep focus on the Add Section control for quick repeats
                self.ui_state.form_field_index = 4 + len(sections)
            else:
                # Enter inline mode to add section
                self._set_status(None)
                self.ui_state.inline_input_mode = True
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
        elif form_field_index == save_idx:
            # Save the list
            # Check form_data first (in case user exited inline mode), then text_input_buffer
            new_name = form_data.get('name', '').strip()
            if not new_name:
                new_name = sanitize_input(self.ui_state.text_input_buffer).strip()

            if not new_name:
                if is_creating:
                    self._set_status("Enter a list name.", True)
                    return
                new_name = editing_list_name

            # For now, just use a default name if not provided
            if not new_name:
                new_name = f"List {len(self.ui_state.task_lists)}"

            task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])

            # Check if name already exists (excluding the current list if editing)
            for i, list_name in enumerate(task_lists):
                if list_name == new_name and (is_creating or list_name != editing_list_name):
                    self._set_status("A list with that name already exists.", True)
                    return

            # Validate based on mode
            list_mode = form_data.get('mode', 'normal')
            if list_mode == 'sections':
                # Prevent saving if sectioned mode is selected but no sections exist
                if not sections:
                    self._set_status("Add at least one section before saving.", True)
                    return
                else:
                    sections_to_save = []
                    # Start with all tasks from the existing data to preserve them
                    for section_data in sections:
                        section_obj = Section(
                            name=section_data.get('name', ''),
                            tasks=section_data.get('tasks', [])
                        )
                        sections_to_save.append(section_obj)
            else:
                sections_to_save = [Section(name='', tasks=[])]

            try:
                # Prepare sections for saving based on mode
                if list_mode == 'normal':
                    # Merge any existing section tasks into a single unnamed section
                    merged_tasks = []
                    for section_data in form_data.get('sections', []):
                        merged_tasks.extend(section_data.get('tasks', []) or [])
                    # Also include any pending tasks (from deleted sections)
                    pending_tasks = form_data.get('pending_tasks', [])
                    merged_tasks.extend(pending_tasks)
                    if not sections_to_save:
                        sections_to_save = [Section(name='', tasks=merged_tasks)]
                    else:
                        sections_to_save[0].tasks.extend(merged_tasks)

                # Get color and show_done_section from form data
                list_color = form_data.get('color', 'white')
                show_done_section = form_data.get('show_done_section', 'section')

                if is_creating:
                    # Add new list
                    self.ui_state.task_lists.append(new_name)
                    list_tasks_map = getattr(self.ui_state, "list_tasks", {})
                    list_tasks_map[new_name] = sections_to_save
                    self.ui_state.list_tasks = list_tasks_map
                    self.manager.list_tasks = list_tasks_map

                    # Store list metadata (color, show_done_section)
                    list_id = self.manager.get_list_id(new_name)
                    self.manager.list_metadata[new_name] = {
                        "id": list_id,
                        "color": list_color,
                        "show_done_section": show_done_section
                    }

                    self.manager.mark_list_tasks_modified()
                    self.manager.save()
                    self._set_status(None)
                else:
                    # Edit existing list
                    if new_name != editing_list_name:
                        # Rename list
                        list_id = self.manager.get_list_id(editing_list_name)
                        list_idx = task_lists.index(editing_list_name)
                        self.ui_state.task_lists[list_idx] = new_name

                        # Update list_tasks_map
                        list_tasks_map = getattr(self.ui_state, "list_tasks", {})
                        if editing_list_name in list_tasks_map:
                            list_tasks_map[new_name] = list_tasks_map.pop(editing_list_name)

                        # Update list_metadata
                        if editing_list_name in self.manager.list_metadata:
                            self.manager.list_metadata[new_name] = self.manager.list_metadata.pop(editing_list_name)

                        # Update pinned entries that reference this list
                        pinned_items = self.manager.get_pinned_items()
                        pinned_changed = False
                        for pinned in pinned_items:
                            p_type = pinned.get("type")
                            if p_type == "list" and (
                                pinned.get("id") == list_id or pinned.get("name") == editing_list_name
                            ):
                                pinned["name"] = new_name
                                pinned["id"] = list_id
                                pinned_changed = True
                            elif p_type == "section" and (
                                pinned.get("list_id") == list_id or pinned.get("list_name") == editing_list_name
                            ):
                                pinned["list_name"] = new_name
                                pinned["list_id"] = list_id
                                pinned_changed = True
                            elif p_type == "task":
                                if pinned.get("list_name") == editing_list_name:
                                    pinned["list_name"] = new_name
                                    pinned_changed = True
                        if pinned_changed:
                            self.manager.metadata["pinned_items"] = pinned_items
                            self.manager.mark_metadata_modified()
                    else:
                        list_tasks_map = getattr(self.ui_state, "list_tasks", {})

                    # Update sections
                    list_tasks_map[new_name] = sections_to_save
                    self.ui_state.list_tasks = list_tasks_map
                    self.manager.list_tasks = list_tasks_map

                    # Update list metadata (color, show_done_section)
                    if new_name not in self.manager.list_metadata:
                        self.manager.list_metadata[new_name] = {}
                    if not self.manager.list_metadata[new_name].get("id"):
                        self.manager.list_metadata[new_name]["id"] = self.manager.get_list_id(new_name)
                    self.manager.list_metadata[new_name]["color"] = list_color
                    self.manager.list_metadata[new_name]["show_done_section"] = show_done_section

                    self.manager.mark_list_tasks_modified()
                    self.manager.save()
                    self._set_status(None)

                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self.ui_state.form_data = {}
                self.ui_state.editing_list_name = None
                self.ui_state.state = AppState.TASK_LIST
                self.ui_state.selected_index = 0
                self._invalidate_task_cache()
            except Exception as e:
                logger.error("Failed to save list: %s", e)
                self._set_status("Failed to save list.", True)
        elif not is_creating and form_field_index == pin_idx:
            # Pin/Unpin list (only when editing, not creating)
            list_name = editing_list_name
            result = self.manager.toggle_pin(
                "list",
                {"id": self.manager.get_list_id(list_name), "name": list_name},
            )
            self.manager.save()
            if result is None:
                self._set_status("Max 10 pinned items", True)
            elif result:
                self._set_status("Pinned")
            else:
                self._set_status("Unpinned")
        elif not is_creating and form_field_index == delete_idx:
            # Delete list - show confirmation (only when editing, not creating)
            list_name = editing_list_name
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""

            # Store delete context for confirmation
            self.ui_state.delete_context = {
                'delete_type': 'edit_list_delete',
                'previous_state': AppState.EDIT_TAB,
                'previous_selected_index': 0,
                'previous_form_field_index': form_field_index,
                'delete_params': {'list_name': list_name}
            }

            # Transition to confirmation dialog
            self.ui_state.state = AppState.DELETE_CONFIRMATION
            self.ui_state.form_field_index = 1  # Default to "No" for safety
            logger.info("Showing delete confirmation for list '%s'", list_name)
        elif form_field_index == (cancel_idx if not is_creating else save_idx + 1):
            # Cancel (adjusted index based on whether pin/delete buttons exist)
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
            self.ui_state.form_data = {}
            self.ui_state.editing_list_name = None
            self.ui_state.state = AppState.TASK_LIST
            self.ui_state.selected_index = 0
            self._set_status(None)

    def execute_delete_list(self, delete_params: dict) -> bool:
        """Execute deleting a task list after confirmation.

        Handles deletion from both the tab rename screen and the list editor screen.
        Performs complete cleanup including metadata and pinned items.
        """
        try:
            # Accept either 'list_name' or 'tab_name' as the list name
            list_name = delete_params.get('list_name') or delete_params.get('tab_name')
            list_id = self.manager.get_list_id(list_name)

            # Find and remove from task_lists
            try:
                list_idx = self.ui_state.task_lists.index(list_name)
                self.ui_state.task_lists.pop(list_idx)
            except (ValueError, AttributeError):
                logger.warning("List '%s' not found in task_lists", list_name)

            # Remove from list_tasks_map
            list_tasks_map = getattr(self.ui_state, "list_tasks", {})
            if list_name in list_tasks_map:
                del list_tasks_map[list_name]

            # Remove from list_metadata
            if list_name in self.manager.list_metadata:
                del self.manager.list_metadata[list_name]

            # Drop any pinned references to this list or its sections
            self.manager.remove_pinned_item("list", {"id": list_id, "name": list_name})
            self.manager.remove_pinned_item("section", {"list_id": list_id, "list_name": list_name})

            # Update manager
            self.manager.list_tasks = list_tasks_map
            self.manager.mark_list_tasks_modified()
            self.manager.save()

            # Adjust active_tab if needed (if the deleted list was active)
            active_tab = getattr(self.ui_state, "active_tab", 0)
            if active_tab >= len(self.ui_state.task_lists):
                self.ui_state.active_tab = max(0, len(self.ui_state.task_lists) - 1)

            # Invalidate caches
            self._invalidate_task_cache()

            self._set_status(f"List '{list_name}' deleted.", False)
            return True
        except Exception as e:
            logger.error("Failed to delete list: %s", e)
            self._set_status("Failed to delete list.", True)
            return False

    def execute_clear_completed_tasks(self) -> bool:
        """Execute clearing all completed tasks after confirmation."""
        try:
            # Remove all completed tasks from every list (Option B)
            list_tasks = getattr(self.manager, "list_tasks", {"Tasks": self.manager.standalone_tasks})
            for list_name, sections in list(list_tasks.items()):
                cleaned_sections = []
                if sections and isinstance(sections[0], Task):
                    pending_tasks = [task for task in sections if getattr(task, "completed", None) is None]
                    cleaned_sections.append(Section(name="", tasks=pending_tasks))
                else:
                    for section in sections or []:
                        pending_tasks = [task for task in getattr(section, "tasks", []) if getattr(task, "completed", None) is None]
                        cleaned_sections.append(Section(name=getattr(section, "name", ""), tasks=pending_tasks))
                list_tasks[list_name] = cleaned_sections
            self.manager.list_tasks = list_tasks
            self.manager.mark_list_tasks_modified()

            # Save changes
            self.manager.save()

            # Invalidate caches
            self._invalidate_task_cache()
            self._set_status(None)
            logger.info("Cleared all completed tasks across lists")
            return True
        except Exception as e:
            logger.error("Failed to clear completed tasks: %s", e)
            self._set_status("Failed to clear completed tasks.", True)
            return False

    def execute_delete_custom_field(self, delete_params: dict) -> bool:
        """Execute deleting a custom field after confirmation."""
        try:
            field_idx = delete_params.get('field_idx')
            field_label = delete_params.get('field_label', 'Unknown')

            # Get custom fields list
            custom_fields = self.manager.custom_field_definitions

            # Validate index
            if field_idx is None or field_idx < 0 or field_idx >= len(custom_fields):
                logger.error("Invalid field index for deletion: %s", field_idx)
                self._set_status("Failed to delete field: invalid index.", True)
                return False

            # Remove the field
            custom_fields.pop(field_idx)

            # Renormalize order
            from pm_live.custom_fields import normalize_field_order
            custom_fields = normalize_field_order(custom_fields)

            # Update manager's list
            self.manager.custom_field_definitions = custom_fields

            # Save to projects.json
            self.manager.mark_dirty()
            self.manager.save()

            self._set_status(f"Field '{field_label}' deleted.", False)
            logger.info("Deleted custom field '%s'", field_label)
            return True
        except Exception as e:
            logger.error("Failed to delete custom field: %s", e)
            self._set_status("Failed to delete custom field.", True)
            return False

    def execute_delete_project(self, delete_params: dict) -> bool:
        """Execute deleting a project after confirmation."""
        try:
            project_id = delete_params.get('project_id')
            project_name = delete_params.get('project_name', 'Unknown')

            if project_id is None:
                logger.error("Invalid project ID for deletion: None")
                self._set_status("Failed to delete project: invalid ID.", True)
                return False

            self.manager.delete_project(project_id)
            self._set_status(f"Project '{project_name}' deleted.", False)
            logger.info("Deleted project '%s' (ID: %s)", project_name, project_id)
            return True
        except Exception as e:
            logger.error("Failed to delete project: %s", e)
            self._set_status("Failed to delete project.", True)
            return False

    def execute_delete_pinned_item(self, delete_params: dict) -> bool:
        """Execute deleting a pinned item after confirmation."""
        item = delete_params.get('item', {}) or {}
        item_type = item.get('type')
        if not item_type:
            self._set_status("Failed to delete pinned item: invalid type.", True)
            return False

        if item_type in ("bookmark", "bookmark_list"):
            from pm import Bookmark, BookmarkList
            target_index = None
            target_list_index = None  # For bookmarks inside lists
            target_item_index = None  # Index within the list
            title = item.get("title")
            url = item.get("url")
            bookmark_id = item.get("id")

            # Search in main bookmarks array
            for idx, b in enumerate(self.manager.bookmarks):
                if item_type == "bookmark" and isinstance(b, Bookmark):
                    if bookmark_id and getattr(b, "id", None) == bookmark_id:
                        target_index = idx
                        break
                    if b.title == title and b.url == url:
                        target_index = idx
                        break
                elif item_type == "bookmark_list" and isinstance(b, BookmarkList):
                    if bookmark_id and getattr(b, "id", None) == bookmark_id:
                        target_index = idx
                        break
                    if b.title == title:
                        target_index = idx
                        break

            # If bookmark not found in main array, search inside bookmark lists
            if target_index is None and item_type == "bookmark":
                for list_idx, b in enumerate(self.manager.bookmarks):
                    if isinstance(b, BookmarkList):
                        for item_idx, bookmark in enumerate(b.items):
                            if bookmark_id and getattr(bookmark, "id", None) == bookmark_id:
                                target_list_index = list_idx
                                target_item_index = item_idx
                                break
                            if bookmark.title == title and bookmark.url == url:
                                target_list_index = list_idx
                                target_item_index = item_idx
                                break
                        if target_list_index is not None:
                            break

            if target_index is None and target_list_index is None:
                self._set_status("Bookmark not found.", True)
                return False

            if not self.bookmark_handlers:
                self._set_status("Bookmark handler not available.", True)
                return False

            delete_type = 'bookmark'
            item_label = "list" if item_type == "bookmark_list" else "bookmark"
            success = False

            if target_index is not None:
                # Bookmark is in main list
                success = self.bookmark_handlers.execute_confirmed_delete({
                    'bookmark_index': target_index,
                    'item_type': item_label,
                    'item_title': title or item_label,
                }, delete_type)
            elif target_list_index is not None and target_item_index is not None:
                # Bookmark is inside a list - delete from the list
                bookmark_list = self.manager.bookmarks[target_list_index]
                if isinstance(bookmark_list, BookmarkList):
                    del bookmark_list.items[target_item_index]
                    self.manager.save()
                    success = True

            if success:
                # Remove from pinned items
                if item_type == "bookmark":
                    self.manager.remove_pinned_item(
                        "bookmark",
                        {"id": bookmark_id, "title": title, "url": url},
                    )
                else:
                    self.manager.remove_pinned_item(
                        "bookmark_list",
                        {"id": bookmark_id, "title": title},
                    )
            return success

        if item_type == "list":
            list_name = item.get("name")
            list_id = item.get("id")
            if not list_name and list_id:
                list_name = self.manager.get_list_name_by_id(list_id)
            if not list_name:
                self._set_status("List not found.", True)
                return False
            return self.execute_delete_list({'list_name': list_name})

        if item_type == "section":
            list_name = item.get("list_name")
            section_idx = item.get("section_idx")
            section_id = item.get("id")
            if section_id:
                resolved_list, resolved_idx, _ = self.manager.find_section_by_id(section_id)
                if resolved_list:
                    list_name = resolved_list
                if resolved_idx is not None:
                    section_idx = resolved_idx
            list_tasks_map = getattr(self.manager, "list_tasks", {}) or {}
            sections = list_tasks_map.get(list_name, [])
            if list_name is None or section_idx is None or not sections or section_idx >= len(sections):
                self._set_status("Section not found.", True)
                return False

            section = sections[section_idx]
            moved_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])
            sections.pop(section_idx)

            if sections:
                target_idx = section_idx - 1 if section_idx - 1 >= 0 else 0
                target_section = sections[target_idx]
                target_tasks = target_section.tasks if hasattr(target_section, 'tasks') else target_section.get('tasks', [])
                target_tasks.extend(moved_tasks)
                if isinstance(target_section, dict):
                    target_section['tasks'] = target_tasks
            else:
                sections.append(Section(name="", tasks=list(moved_tasks)))

            list_tasks_map[list_name] = sections
            self.manager.list_tasks = list_tasks_map
            list_id = self.manager.get_list_id(list_name)
            self.manager.remove_pinned_item(
                "section",
                {"id": section_id, "list_id": list_id, "list_name": list_name, "section_idx": section_idx},
            )
            self.manager.mark_list_tasks_modified()
            self.manager.save()
            self.ui_state.list_tasks = list_tasks_map
            self._invalidate_task_cache()
            self._set_status(f"Section deleted from '{list_name}'.", False)
            return True

        if item_type == "task":
            task_id = item.get("id")
            if not task_id or not self.task_handlers:
                self._set_status("Task not found.", True)
                return False
            task_obj, context = self.manager.resolve_task_for_pin(
                task_id,
                task_name=item.get("name", ""),
                project_id=item.get("project_id"),
                list_name=item.get("list_name"),
                section_idx=item.get("section_idx"),
            )
            if not task_obj:
                self._set_status("Task not found.", True)
                return False

            if "project_id" in context:
                project_id = context["project_id"]
                success = self.task_handlers.execute_confirmed_delete({
                    'task_id': task_obj.id,
                    'task': task_obj,
                    'is_standalone': False,
                    'current_project_id': project_id
                })
                if success:
                    self.manager.remove_pinned_item("task", task_id)
                    self._set_status(f"Task '{task_obj.name}' deleted.", False)
                else:
                    self._set_status("Failed to delete task.", True)
                return success

            if "list_name" in context:
                list_name = context["list_name"]
                list_tasks_map = getattr(self.manager, "list_tasks", {}) or {}
                task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
                if list_name not in task_lists:
                    task_lists.append(list_name)
                    self.ui_state.task_lists = task_lists
                list_idx = task_lists.index(list_name)
                original_active_tab = self.ui_state.active_tab
                try:
                    self.ui_state.active_tab = list_idx
                    self.ui_state.list_tasks = list_tasks_map
                    success = self.task_handlers.execute_confirmed_delete({
                        'task_id': task_obj.id,
                        'task': task_obj,
                        'is_standalone': True,
                        'current_project_id': None
                    })
                finally:
                    self.ui_state.active_tab = original_active_tab

                if success:
                    self.manager.remove_pinned_item("task", task_id)
                    self._set_status(f"Task '{task_obj.name}' deleted.", False)
                else:
                    self._set_status("Failed to delete task.", True)
                return success

            self._set_status("Task not found.", True)
            return False

        self._set_status("Failed to delete pinned item.", True)
        return False

    def execute_delete_calendar_task(self, delete_params: dict) -> bool:
        """Execute deleting a task from the calendar list after confirmation."""
        if not self.task_handlers:
            self._set_status("Failed to delete task.", True)
            return False

        task_id = delete_params.get('task_id')
        task = delete_params.get('task')
        is_standalone = delete_params.get('is_standalone', False)
        list_name = delete_params.get('list_name')

        if not task_id or task is None:
            self._set_status("Failed to delete task.", True)
            return False

        if is_standalone and list_name:
            task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
            if list_name not in task_lists:
                task_lists.append(list_name)
                self.ui_state.task_lists = task_lists
            list_idx = task_lists.index(list_name)
            original_active_tab = self.ui_state.active_tab
            try:
                self.ui_state.active_tab = list_idx
                if not getattr(self.ui_state, "list_tasks", None):
                    self.ui_state.list_tasks = getattr(self.manager, "list_tasks", {})
                success = self.task_handlers.execute_confirmed_delete(delete_params)
            finally:
                self.ui_state.active_tab = original_active_tab
        else:
            success = self.task_handlers.execute_confirmed_delete(delete_params)

        if success:
            task_name = getattr(task, "name", "Task")
            self._set_status(f"Task '{task_name}' deleted.", False)
        else:
            self._set_status("Failed to delete task.", True)
        return success

    def handle_edit_list_section_edit(self):
        """Handle 'e' key to edit a section's title in EDIT_TAB state."""
        # Only work in list edit mode
        if not (self.ui_state.editing_list_name is not None or (self.ui_state.form_data and 'sections' in self.ui_state.form_data)):
            return

        form_field_index = self.ui_state.form_field_index
        form_data = self.ui_state.form_data
        mode = form_data.get('mode', 'normal')
        sections = form_data.get('sections', [])

        # Only work in sections mode
        if mode != 'sections':
            return

        add_section_idx = 3 + len(sections)

        # Only work on section fields (not list name, not mode, not action buttons)
        if not (3 <= form_field_index < add_section_idx):
            return

        section_idx = form_field_index - 3
        if 0 <= section_idx < len(sections):
            section = sections[section_idx]
            # Enter inline mode to edit section name
            self._set_status(None)
            self.ui_state.inline_input_mode = True
            self.ui_state.text_input_buffer = section.get('name', '')
            self.ui_state.text_input_cursor = len(self.ui_state.text_input_buffer)
            logger.debug("Entering inline edit mode for section at index %d", section_idx)

    def handle_edit_list_section_delete(self):
        """Handle 'del' key to delete a section in EDIT_TAB state."""
        # Only work in list edit mode
        if not (self.ui_state.editing_list_name is not None or (self.ui_state.form_data and 'sections' in self.ui_state.form_data)):
            return

        form_field_index = self.ui_state.form_field_index
        form_data = self.ui_state.form_data
        mode = form_data.get('mode', 'normal')
        sections = form_data.get('sections', [])

        # Only work in sections mode
        if mode != 'sections':
            return

        add_section_idx = 3 + len(sections)

        # Only work on section fields (not list name, not mode, not action buttons)
        if not (3 <= form_field_index < add_section_idx):
            return

        section_idx = form_field_index - 3
        if 0 <= section_idx < len(sections):
            section = sections[section_idx]
            section_name = section.get('name', 'unnamed')

            # If section has tasks, move them into the previous section; if none, into next
            moved_tasks = section.get('tasks', []) or []
            sections.pop(section_idx)

            target_idx = None
            if sections:
                if section_idx - 1 >= 0:
                    target_idx = section_idx - 1  # previous section
                else:
                    target_idx = 0  # fallback to first remaining

            if target_idx is not None:
                sections[target_idx].setdefault('tasks', [])
                sections[target_idx]['tasks'].extend(moved_tasks)
            elif moved_tasks:
                # No other sections exist, save tasks to pending
                existing_pending = form_data.get('pending_tasks', [])
                form_data['pending_tasks'] = existing_pending + moved_tasks

            form_data['sections'] = sections

            # Adjust form_field_index if needed
            if not sections:
                # All sections deleted, move to Add Section field (index 3)
                self.ui_state.form_field_index = 3
            elif self.ui_state.form_field_index > 1:
                # Move to previous section or earlier field
                self.ui_state.form_field_index = max(3, self.ui_state.form_field_index - 1)

            if moved_tasks:
                if not sections:
                    self._set_status(f"Section '{section_name}' deleted (tasks will move to next section created).", False)
                else:
                    self._set_status(f"Section '{section_name}' deleted (tasks moved).", False)
            else:
                self._set_status(f"Section '{section_name}' deleted.", False)
            logger.info("Deleted section '%s' at index %d (moved %d tasks)", section_name, section_idx, len(moved_tasks))

    def handle_customize_fields_enter(self):
        """Handle enter in customize fields screen."""
        selected_idx = self.ui_state.selected_index
        custom_fields = self.manager.custom_field_definitions

        # Get builtin fields dynamically
        try:
            from ..custom_fields import get_builtin_fields
            default_visibility = getattr(self.manager, "default_field_visibility", {})
            builtin_fields = get_builtin_fields(default_visibility)
        except Exception:
            builtin_fields = []

        # Handle Progress field visibility toggle (index 0)
        if selected_idx == 0:
            field_key = "progress"
            # Toggle visibility
            self.manager.default_field_visibility[field_key] = not self.manager.default_field_visibility.get(field_key, True)

            # Save to projects.json
            self.manager.mark_dirty()
            self.manager.save()

            status = "visible" if self.manager.default_field_visibility[field_key] else "hidden"
            self._set_status(f"Built-in field '{field_key}' is now {status}.", False)
            logger.info("Toggled visibility for built-in field '%s' to %s", field_key, self.manager.default_field_visibility[field_key])
            return

        # Handle other built-in fields (indices 1 to 1+len(builtin_fields)-1)
        builtin_start = 1
        builtin_end = builtin_start + len(builtin_fields)

        if selected_idx >= builtin_start and selected_idx < builtin_end:
            field_idx = selected_idx - builtin_start
            field = builtin_fields[field_idx]
            field_key = field.key

            # Toggle visibility
            self.manager.default_field_visibility[field_key] = not self.manager.default_field_visibility.get(field_key, True)

            # Save to projects.json
            self.manager.mark_dirty()
            self.manager.save()

            status = "visible" if self.manager.default_field_visibility[field_key] else "hidden"
            self._set_status(f"Built-in field '{field_key}' is now {status}.", False)
            logger.info("Toggled visibility for built-in field '%s' to %s", field_key, self.manager.default_field_visibility[field_key])
            return

        # Handle custom field visibility toggle (start after builtin fields)
        custom_start = builtin_end
        custom_end = custom_start + len(custom_fields)
        if selected_idx >= custom_start and selected_idx < custom_end:
            field_idx = selected_idx - custom_start
            field = custom_fields[field_idx]
            field.visible = not field.visible

            # Save to projects.json
            self.manager.mark_dirty()
            self.manager.save()

            status = "visible" if field.visible else "hidden"
            self._set_status(f"Field '{field.label}' is now {status}.", False)
            logger.info("Toggled visibility for field '%s' to %s", field.key, field.visible)
            return

        # Handle actions
        actions_start = custom_end
        action_idx = selected_idx - actions_start

        if action_idx == 0:  # Add Field
            self.ui_state.state = AppState.ADD_CUSTOM_FIELD
            self.ui_state.form_data = {
                'field_type': 'text',
                'visible': True,
                'required': False,
                'number_format': 'number',
                'currency_symbol': '$',
                'select_options': []
            }
            self.ui_state.form_field_index = 0
            self.ui_state.inline_input_mode = False
            logger.info("Navigating to ADD_CUSTOM_FIELD")
        elif action_idx == 1:  # Back to Projects
            self.ui_state.state = AppState.PROJECT_BROWSER
            self.ui_state.selected_index = 0
            logger.info("Returning to PROJECT_BROWSER from CUSTOMIZE_FIELDS")

    def handle_add_custom_field_enter(self):
        """Handle enter in add custom field form (inline options)."""
        from pm_live.custom_fields import CustomField, SelectOption, FIELD_TYPES, NUMBER_FORMATS, validate_field_label, generate_field_key
        from pm_live.utils.validation import sanitize_input

        form_data = self.ui_state.form_data
        form_field_index = self.ui_state.form_field_index
        field_type = form_data.get('field_type', 'text')

        # Core fields in order: label, visible, required
        core_fields = ['label', 'visible', 'required']

        # field_type is at index len(core_fields)
        field_type_idx = len(core_fields)

        # Number format fields come after field_type (indented)
        current_idx = field_type_idx + 1
        number_format_idx = None
        currency_symbol_idx = None
        if field_type == 'number':
            number_format_idx = current_idx
            current_idx += 1
            if form_data.get('number_format') == 'currency':
                currency_symbol_idx = current_idx
                current_idx += 1

        # Inline options metadata for single_select
        options = form_data.get('select_options', []) if field_type == 'single_select' else []
        options_start = current_idx
        add_idx = options_start + len(options) if field_type == 'single_select' else None
        if field_type == 'single_select':
            save_idx = add_idx + 1
        else:
            save_idx = current_idx
        cancel_idx = save_idx + 1

        # First, commit inline input where applicable
        if self.ui_state.inline_input_mode:
            # Editing label field
            if form_field_index < len(core_fields) and core_fields[form_field_index] == 'label':
                result = sanitize_input(self.ui_state.text_input_buffer).strip()
                form_data['label'] = result
                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self._set_status(None)
                return

            # Editing currency_symbol field
            if currency_symbol_idx is not None and form_field_index == currency_symbol_idx:
                result = sanitize_input(self.ui_state.text_input_buffer).strip()
                form_data['currency_symbol'] = result
                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
                self._set_status(None)
                return

            # Editing an existing option value
            if field_type == 'single_select' and options_start <= form_field_index < (options_start + len(options)):
                opt_idx = form_field_index - options_start
                result = sanitize_input(self.ui_state.text_input_buffer).strip()
                if 0 <= opt_idx < len(options):
                    opt = options[opt_idx]
                    if isinstance(opt, dict):
                        opt['value'] = result
                    else:
                        opt.value = result
                    form_data['select_options'] = options
                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
                self._set_status(None)
                return

            # Committing a newly added option on the + row
            if field_type == 'single_select' and form_field_index == add_idx:
                result = sanitize_input(self.ui_state.text_input_buffer).strip()
                if result:
                    options.append(SelectOption(value=result, color=None))
                    form_data['select_options'] = options
                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
                self._set_status(None)
                return

        # Handle actions depending on where the cursor is
        # 1) Core fields (label, visible, required)
        if form_field_index < len(core_fields):
            field_name = core_fields[form_field_index]
            if field_name == 'label':
                # Start inline editing for text field
                self.ui_state.inline_input_mode = True
                self.ui_state.text_input_buffer = form_data.get(field_name, '')
                self.ui_state.text_input_cursor = len(self.ui_state.text_input_buffer)
            elif field_name in ['visible', 'required']:
                form_data[field_name] = not form_data.get(field_name, False)
            return

        # 2) field_type field (after core fields)
        if form_field_index == field_type_idx:
            # Cycle through field types
            current = form_data.get('field_type', 'text')
            type_idx = FIELD_TYPES.index(current) if current in FIELD_TYPES else 0
            next_idx = (type_idx + 1) % len(FIELD_TYPES)
            form_data['field_type'] = FIELD_TYPES[next_idx]
            return

        # 3) number_format field (indented below Type, only for number type)
        if number_format_idx is not None and form_field_index == number_format_idx:
            # Cycle through number formats
            current = form_data.get('number_format', 'number')
            format_idx = NUMBER_FORMATS.index(current) if current in NUMBER_FORMATS else 0
            next_idx = (format_idx + 1) % len(NUMBER_FORMATS)
            form_data['number_format'] = NUMBER_FORMATS[next_idx]
            return

        # 4) currency_symbol field (indented below Number Format, only for currency format)
        if currency_symbol_idx is not None and form_field_index == currency_symbol_idx:
            # Start inline editing for currency symbol
            self.ui_state.inline_input_mode = True
            self.ui_state.text_input_buffer = form_data.get('currency_symbol', '')
            self.ui_state.text_input_cursor = len(self.ui_state.text_input_buffer)
            return

        # 2) Existing options rows
        if field_type == 'single_select' and options_start <= form_field_index < (options_start + len(options)):
            opt_idx = form_field_index - options_start
            if 0 <= opt_idx < len(options):
                opt = options[opt_idx]
                current_value = getattr(opt, 'value', None) or (opt.get('value') if isinstance(opt, dict) else '')
                self.ui_state.inline_input_mode = True
                self.ui_state.text_input_buffer = current_value or ""
                self.ui_state.text_input_cursor = len(self.ui_state.text_input_buffer)
            return

        # 3) + Add Option row
        if field_type == 'single_select' and form_field_index == add_idx:
            self.ui_state.inline_input_mode = True
            self.ui_state.text_input_buffer = ""
            self.ui_state.text_input_cursor = 0
            return

        # 4) Save
        if form_field_index == save_idx:
            label = form_data.get('label', '').strip()
            is_valid, error = validate_field_label(label)
            if not is_valid:
                self._set_status(error, True)
                return

            key = generate_field_key(label, self.manager.custom_field_definitions)
            normalized_options = self._normalize_select_options(form_data.get('select_options', []))
            form_data['select_options'] = normalized_options
            new_field = CustomField(
                key=key,
                label=label,
                field_type=form_data.get('field_type', 'text'),
                visible=form_data.get('visible', True),
                required=form_data.get('required', False),
                order=len(self.manager.custom_field_definitions),
                number_format=form_data.get('number_format', 'number'),
                currency_symbol=form_data.get('currency_symbol', '$'),
                select_options=normalized_options
            )

            self.manager.custom_field_definitions.append(new_field)
            self.manager.mark_dirty()
            self.manager.save()

            self._set_status(f"Field '{label}' created.", False)
            logger.info("Created custom field '%s'", key)

            self.ui_state.state = AppState.CUSTOMIZE_FIELDS
            self.ui_state.selected_index = 0
            return

        # 5) Cancel
        if form_field_index == cancel_idx:
            self.ui_state.state = AppState.CUSTOMIZE_FIELDS
            self.ui_state.selected_index = 0
            logger.info("Cancelled add custom field")

    def handle_edit_custom_field_enter(self):
        """Handle enter in edit custom field form (inline options)."""
        from pm_live.custom_fields import FIELD_TYPES, NUMBER_FORMATS, validate_field_label, get_field_by_key
        from pm_live.utils.validation import sanitize_input

        form_data = self.ui_state.form_data
        form_field_index = self.ui_state.form_field_index
        field_type = form_data.get('field_type', 'text')

        # Core fields in order: label, visible, required
        core_fields = ['label', 'visible', 'required']

        # field_type is at index len(core_fields)
        field_type_idx = len(core_fields)

        # Number format fields come after field_type (indented)
        current_idx = field_type_idx + 1
        number_format_idx = None
        currency_symbol_idx = None

        if field_type == 'number':
            number_format_idx = current_idx
            current_idx += 1
            if form_data.get('number_format') == 'currency':
                currency_symbol_idx = current_idx
                current_idx += 1

        # Options metadata for single_select
        options = form_data.get('select_options', []) if field_type == 'single_select' else []
        options_start = current_idx
        add_idx = options_start + len(options) if field_type == 'single_select' else None
        if field_type == 'single_select':
            save_idx = add_idx + 1
        else:
            save_idx = current_idx
        delete_idx = save_idx + 1
        cancel_idx = save_idx + 2

        # Commit inline edits first
        if self.ui_state.inline_input_mode:
            # Editing label
            if form_field_index < len(core_fields) and core_fields[form_field_index] == 'label':
                result = sanitize_input(self.ui_state.text_input_buffer).strip()
                form_data['label'] = result
                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self._set_status(None)
                return

            # Editing currency_symbol
            if currency_symbol_idx is not None and form_field_index == currency_symbol_idx:
                result = sanitize_input(self.ui_state.text_input_buffer).strip()
                form_data['currency_symbol'] = result
                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
                self._set_status(None)
                return

            # Editing existing option value
            if field_type == 'single_select' and options_start <= form_field_index < (options_start + len(options)):
                opt_idx = form_field_index - options_start
                result = sanitize_input(self.ui_state.text_input_buffer).strip()
                if 0 <= opt_idx < len(options):
                    opt = options[opt_idx]
                    if isinstance(opt, dict):
                        opt['value'] = result
                    else:
                        opt.value = result
                    form_data['select_options'] = options
                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
                self._set_status(None)
                return

            # Committing new option on + row
            if field_type == 'single_select' and form_field_index == add_idx:
                result = sanitize_input(self.ui_state.text_input_buffer).strip()
                if result:
                    from pm_live.custom_fields import SelectOption
                    options.append(SelectOption(value=result, color=None))
                    form_data['select_options'] = options
                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
                self._set_status(None)
                return

        # 1) Core fields (label, visible, required)
        if form_field_index < len(core_fields):
            field_name = core_fields[form_field_index]
            if field_name == 'label':
                self.ui_state.inline_input_mode = True
                self.ui_state.text_input_buffer = form_data.get(field_name, '')
                self.ui_state.text_input_cursor = len(self.ui_state.text_input_buffer)
            elif field_name in ['visible', 'required']:
                form_data[field_name] = not form_data.get(field_name, False)
            return

        # 2) field_type field (after core fields)
        if form_field_index == field_type_idx:
            current = form_data.get('field_type', 'text')
            type_idx = FIELD_TYPES.index(current) if current in FIELD_TYPES else 0
            next_idx = (type_idx + 1) % len(FIELD_TYPES)
            form_data['field_type'] = FIELD_TYPES[next_idx]
            return

        # 3) number_format field (indented below Type, only for number type)
        if number_format_idx is not None and form_field_index == number_format_idx:
            current = form_data.get('number_format', 'number')
            format_idx = NUMBER_FORMATS.index(current) if current in NUMBER_FORMATS else 0
            next_idx = (format_idx + 1) % len(NUMBER_FORMATS)
            form_data['number_format'] = NUMBER_FORMATS[next_idx]
            return

        # 4) currency_symbol field (indented below Number Format, only for currency format)
        if currency_symbol_idx is not None and form_field_index == currency_symbol_idx:
            self.ui_state.inline_input_mode = True
            self.ui_state.text_input_buffer = form_data.get('currency_symbol', '')
            self.ui_state.text_input_cursor = len(self.ui_state.text_input_buffer)
            return

        # 2) Existing options
        if field_type == 'single_select' and options_start <= form_field_index < (options_start + len(options)):
            opt_idx = form_field_index - options_start
            if 0 <= opt_idx < len(options):
                opt = options[opt_idx]
                current_value = getattr(opt, 'value', None) or (opt.get('value') if isinstance(opt, dict) else '')
                self.ui_state.inline_input_mode = True
                self.ui_state.text_input_buffer = current_value or ""
                self.ui_state.text_input_cursor = len(self.ui_state.text_input_buffer)
            return

        # 3) + Add Option row
        if field_type == 'single_select' and form_field_index == add_idx:
            self.ui_state.inline_input_mode = True
            self.ui_state.text_input_buffer = ""
            self.ui_state.text_input_cursor = 0
            return

        # 4) Save
        if form_field_index == save_idx:
            label = form_data.get('label', '').strip()
            is_valid, error = validate_field_label(label)
            if not is_valid:
                self._set_status(error, True)
                return

            key = form_data.get('key')
            field = get_field_by_key(self.manager.custom_field_definitions, key)
            if not field:
                self._set_status(f"Field '{key}' not found.", True)
                return

            field.label = label
            field.field_type = form_data.get('field_type', 'text')
            field.visible = form_data.get('visible', True)
            field.required = form_data.get('required', False)
            field.number_format = form_data.get('number_format', 'number')
            field.currency_symbol = form_data.get('currency_symbol', '$')
            normalized_options = self._normalize_select_options(form_data.get('select_options', []))
            field.select_options = normalized_options
            form_data['select_options'] = normalized_options

            self.manager.mark_dirty()
            self.manager.save()

            self._set_status(f"Field '{label}' updated.", False)
            logger.info("Updated custom field '%s'", key)

            self.ui_state.state = AppState.CUSTOMIZE_FIELDS
            self.ui_state.selected_index = 0
            return

        # 4.5) Delete
        if form_field_index == delete_idx:
            key = form_data.get('key')
            label = form_data.get('label', key)
            
            # Find the field index in the manager's list
            custom_fields = self.manager.custom_field_definitions
            field_idx = -1
            for i, f in enumerate(custom_fields):
                if f.key == key:
                    field_idx = i
                    break
            
            if field_idx == -1:
                self._set_status(f"Field '{key}' not found.", True)
                return

            # Show confirmation dialog
            from pm_live.custom_fields import get_builtin_fields
            default_visibility = getattr(self.manager, "default_field_visibility", {})
            builtin_fields = get_builtin_fields(default_visibility)
            
            # Reconstruct the selected index in the CUSTOMIZE_FIELDS screen for proper return
            # Progress (1) + built-in fields + field_idx
            previous_selected_index = 1 + len(builtin_fields) + field_idx

            self.ui_state.delete_context = {
                'delete_type': 'custom_field',
                'previous_state': AppState.CUSTOMIZE_FIELDS,
                'previous_selected_index': previous_selected_index,
                'delete_params': {
                    'field_idx': field_idx,
                    'field_key': key,
                    'field_label': label
                }
            }
            self.ui_state.state = AppState.DELETE_CONFIRMATION
            self.ui_state.form_field_index = 1  # Default to "No" for safety
            logger.info("Showing delete confirmation for custom field '%s' from edit form", label)
            return

        # 5) Cancel
        if form_field_index == cancel_idx:
            self.ui_state.state = AppState.CUSTOMIZE_FIELDS
            self.ui_state.selected_index = 0
            logger.info("Cancelled edit custom field")

    # Cell editing helpers for project browser inline editing

    def _get_visible_fields_for_cell_mode(self):
        """Get the list of visible fields for cell selection mode.
        
        Returns list including pseudo-fields for status (-2) and name (-1),
        followed by actual custom fields (0+).
        """
        from ..custom_fields import CustomField, SelectOption
        
        # Create pseudo-fields for status and name
        status_field = CustomField(
            key="__status__",
            label="Status",
            field_type="single_select",
            visible=True,
            select_options=[SelectOption(value=status) for status in STATUS_DISPLAY_ORDER]
        )
        
        name_field = CustomField(
            key="__name__",
            label="Project",
            field_type="text",
            visible=True
        )

        progress_visible = getattr(self.manager, "default_field_visibility", {}).get("progress", True)
        progress_field = CustomField(
            key="__progress__",
            label="Progress",
            field_type="number",
            visible=progress_visible,
        )
        
        # Get actual custom fields
        all_fields = get_all_fields(self.manager.default_field_visibility, self.manager.custom_field_definitions)
        builtin_keys = ("timeframe", "priority", "area")
        field_by_key = {field.key: field for field in all_fields}

        visible_builtin_fields = [
            field_by_key[key]
            for key in builtin_keys
            if field_by_key.get(key) and field_by_key[key].visible
        ]
        visible_custom_fields = [
            field for field in all_fields
            if field.key not in builtin_keys and field.visible
        ]
        visible_custom_fields.sort(key=lambda f: getattr(f, "order", 0))
        
        # Return: status, name, custom fields, then progress (if visible)
        fields = [status_field, name_field] + visible_builtin_fields + visible_custom_fields
        if progress_visible:
            fields.append(progress_field)
        return fields

    def _get_cell_selected_field(self):
        """Get the field definition for the currently selected cell column."""
        visible_fields = self._get_visible_fields_for_cell_mode()
        col = self.ui_state.cell_selected_column
        if 0 <= col < len(visible_fields):
            return visible_fields[col]
        return None

    def _enter_cell_edit_mode(self):
        """Enter edit mode for the selected cell."""
        field = self._get_cell_selected_field()
        if not field or field.key == "__progress__" or self.ui_state.selected_index < 0:
            return

        filtered = self._get_filtered_projects_sorted()
        if self.ui_state.selected_index >= len(filtered):
            return

        project = filtered[self.ui_state.selected_index]
        
        # Get current value - handle special pseudo-fields
        if field.key == "__status__":
            current_value = project.status
        elif field.key == "__name__":
            current_value = project.name
        else:
            current_value = project.get_field_value(field.key)

        self.ui_state.cell_editing = True

        if field.field_type == 'single_select':
            # For single-select, cycle through options on Enter
            options = field.select_options or []
            if not options:
                self.ui_state.cell_editing = False
                return
            
            # For status field, don't include None as an option
            if field.key == "__status__":
                option_values = [opt.value for opt in options]
            else:
                option_values = [None] + [opt.value for opt in options]
            
            if current_value not in option_values:
                next_value = option_values[0]
            else:
                idx = option_values.index(current_value)
                next_value = option_values[(idx + 1) % len(option_values)]
            # Save immediately for single-select cycling
            self._save_cell_value(project, field.key, next_value)
            self.ui_state.cell_editing = False
        elif field.field_type == 'date':
            # Initialize date buffer
            if current_value:
                self.ui_state.cell_edit_date_buffer = str(current_value)
            else:
                from datetime import datetime
                today = datetime.now()
                self.ui_state.cell_edit_date_buffer = f"{today.year:04d}-{today.month:02d}-{today.day:02d}"
            self.ui_state.cell_edit_date_component = 0
        else:
            # Text and number fields
            self.ui_state.cell_edit_buffer = str(current_value) if current_value else ""

    def _save_cell_edit(self):
        """Save the edited cell value."""
        field = self._get_cell_selected_field()
        if not field or self.ui_state.selected_index < 0:
            self.ui_state.cell_editing = False
            return

        filtered = self._get_filtered_projects_sorted()
        if self.ui_state.selected_index >= len(filtered):
            self.ui_state.cell_editing = False
            return

        project = filtered[self.ui_state.selected_index]

        if field.field_type == 'date':
            new_value = self.ui_state.cell_edit_date_buffer
        else:
            new_value = self.ui_state.cell_edit_buffer.strip() if self.ui_state.cell_edit_buffer else None

        self._save_cell_value(project, field.key, new_value)

        # Reset cell editing state
        self.ui_state.cell_editing = False
        self.ui_state.cell_edit_buffer = ""
        self.ui_state.cell_edit_date_buffer = None
        self.ui_state.cell_edit_date_component = 0

    def _save_cell_value(self, project, field_key, new_value):
        """Save a value to a project's field."""
        # Handle special pseudo-fields
        if field_key == "__status__":
            if new_value:
                project.status = new_value
                self.manager.update_project(project)
                self._set_status(None)
            return
        elif field_key == "__name__":
            if new_value and new_value.strip():
                project.name = new_value.strip()
                self.manager.update_project(project)
                self._set_status(None)
            return
        
        # Handle regular custom fields
        if new_value is None or new_value == "":
            project.custom_field_values.pop(field_key, None)
        else:
            project.custom_field_values[field_key] = new_value

        # Keep legacy attributes in sync for built-in fields
        if field_key == "timeframe":
            project.timeframe = new_value

        self.manager.update_project(project)
        self._set_status(None)

    def _apply_project_sort(self):
        """Set the active sort column based on the selected header cell."""
        field = self._get_cell_selected_field()
        if not field:
            return

        current_key = getattr(self.ui_state, "project_sort_key", None)
        current_order = getattr(self.ui_state, "project_sort_order", None)

        if current_key != field.key:
            # New column: start with ascending
            self.ui_state.project_sort_key = field.key
            self.ui_state.project_sort_order = "asc"
        else:
            # Cycle order: None -> asc -> desc -> None ...
            if current_order is None:
                self.ui_state.project_sort_order = "asc"
            elif current_order == "asc":
                self.ui_state.project_sort_order = "desc"
            else:
                self.ui_state.project_sort_order = None

            self.ui_state.project_sort_key = field.key

        try:
            label = field.label
        except Exception:
            label = str(field.key)
        order = getattr(self.ui_state, "project_sort_order", None)
        if order == "asc":
            msg = f"Sorted by {label} (ascending)"
        elif order == "desc":
            msg = f"Sorted by {label} (descending)"
        else:
            msg = "Sorting cleared"
        self._set_status(msg, False)

    def _get_filtered_projects_sorted(self):
        """Filter and sort projects using the current sort key."""
        all_fields = get_all_fields(self.manager.default_field_visibility, self.manager.custom_field_definitions)
        filtered = filter_projects_by_tab(self.manager.projects, self.ui_state.active_tab)
        return sort_projects_for_display(
            filtered,
            getattr(self.ui_state, "project_sort_key", None),
            all_fields,
            getattr(self.ui_state, "project_sort_order", None),
        )

    def _restore_project_browser_selection(self, fallback_project_id: Optional[int] = None) -> None:
        """Restore the project browser selection based on last project/id."""
        filtered = self._get_filtered_projects_sorted()
        if not filtered:
            self.ui_state.selected_index = 0
            self.ui_state.project_browser_selected_index = 0
            self.ui_state.project_browser_selected_project_id = None
            return

        project_id = fallback_project_id or self.ui_state.project_browser_selected_project_id
        selected_index = None

        if project_id is not None:
            for idx, project in enumerate(filtered):
                if project.id == project_id:
                    selected_index = idx
                    break

        if selected_index is None:
            saved_index = self.ui_state.project_browser_selected_index
            if 0 <= saved_index < len(filtered):
                selected_index = saved_index
            else:
                selected_index = min(max(saved_index, 0), len(filtered) - 1)
            project_id = filtered[selected_index].id

        self.ui_state.selected_index = selected_index
        self.ui_state.project_browser_selected_index = selected_index
        self.ui_state.project_browser_selected_project_id = project_id

    def handle_project_selection_enter(self):
        """Handle Enter in project selection menu to move task to selected project or Tasks."""
        move_task_source = self.ui_state.move_task_source
        if not move_task_source:
            # No task source, go back
            self.ui_state.state = self.ui_state.previous_state or AppState.MAIN_MENU
            return
        previous_state = self.ui_state.previous_state or AppState.MAIN_MENU

        projects = self.manager.projects if self.manager else []
        selected_idx = self.ui_state.selected_index
        task = move_task_source.get("task")

        if not task:
            self._set_status("Task not found", is_error=True)
            self._clear_move_task_state()
            self.ui_state.state = previous_state
            return

        # Check if moving from a project (to allow "Move to Tasks" option)
        source_project_id = move_task_source.get("project_id")
        is_from_project = source_project_id is not None

        # Check if "Move to Tasks" option is selected
        tasks_option_index = len(projects)
        is_move_to_tasks = is_from_project and selected_idx == tasks_option_index

        # Validate selection index (but allow tasks_option_index if from project)
        if not is_move_to_tasks and (selected_idx < 0 or selected_idx >= len(projects)):
            self._set_status("Invalid selection", is_error=True)
            self._clear_move_task_state()
            self.ui_state.state = previous_state
            return

        # Check if trying to move task to the same project it's already in
        if not is_move_to_tasks and is_from_project:
            target_project = projects[selected_idx]
            if target_project.id == source_project_id:
                self._set_status("Task is already in this project", is_error=True)
                self._clear_move_task_state()
                self.ui_state.state = previous_state
                return

        if is_move_to_tasks:
            # Move task to standalone Tasks list
            source_project = self.manager.get_project(source_project_id)
            if source_project:
                try:
                    source_project.tasks.remove(task)
                    self.manager.update_project(source_project)
                except ValueError:
                    pass

            # Add to Tasks list
            list_tasks_map = getattr(self.ui_state, "list_tasks", None) or getattr(self.manager, "list_tasks", {})
            sections = list_tasks_map.get("Tasks", [])
            if not sections:
                sections = [Section(name="", tasks=[])]
                list_tasks_map["Tasks"] = sections

            # Add to first section
            section = sections[0]
            section_tasks = section.tasks if hasattr(section, "tasks") else section.get("tasks", [])
            section_tasks.append(task)

            self.manager.mark_list_tasks_modified()
            self.manager.save()

            self._set_status("Task moved to Tasks")
            # Navigate to the Tasks list so user can see the moved task
            self.ui_state.state = AppState.TASK_LIST
            # Set active tab to Tasks (index 0 is typically the Tasks list)
            task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
            try:
                tasks_tab_idx = task_lists.index("Tasks")
                self.ui_state.active_tab = tasks_tab_idx
            except ValueError:
                self.ui_state.active_tab = 0
            self.ui_state.selected_index = 0
        else:
            # Move to selected project
            target_project = projects[selected_idx]

            # Remove task from source
            source_list_name = move_task_source.get("list_name")
            source_section_idx = move_task_source.get("section_idx")

            if source_project_id is not None:
                # Task is from a project
                source_project = self.manager.get_project(source_project_id)
                if source_project:
                    try:
                        source_project.tasks.remove(task)
                        self.manager.update_project(source_project)
                    except ValueError:
                        # Task not found in source project, continue anyway
                        pass
            elif source_list_name is not None:
                # Task is from a standalone list
                list_tasks_map = getattr(self.ui_state, "list_tasks", None) or getattr(self.manager, "list_tasks", {})
                sections = list_tasks_map.get(source_list_name, [])
                if source_section_idx is not None and 0 <= source_section_idx < len(sections):
                    section = sections[source_section_idx]
                    section_tasks = section.tasks if hasattr(section, "tasks") else section.get("tasks", [])
                    try:
                        section_tasks.remove(task)
                        self.manager.mark_list_tasks_modified()
                        self.manager.save()
                    except ValueError:
                        # Task not found, continue anyway
                        pass

            # Add task to target project
            target_project.tasks.append(task)
            self.manager.update_project(target_project)

            # Show success message
            self._set_status(f"Task moved to project: {target_project.name}")

            # Return to previous state
            if previous_state == AppState.PROJECT_DETAILS:
                # If we were in project details, go to the target project
                self.ui_state.state = AppState.PROJECT_DETAILS
                self.ui_state.current_project_id = target_project.id
                self.ui_state.selected_index = 0
            elif previous_state == AppState.TASK_LIST:
                # Return to task list
                self.ui_state.state = AppState.TASK_LIST
                self.ui_state.selected_index = 0
            else:
                self.ui_state.state = AppState.MAIN_MENU
                self.ui_state.selected_index = 0

        # Clear move task state
        self._clear_move_task_state()

    def _clear_move_task_state(self):
        """Clear the move task state variables."""
        self.ui_state.move_task_source = None
        self.ui_state.move_task_target_project_idx = 0
        self.ui_state.move_task_original_index = 0
        self.ui_state.previous_state = None
