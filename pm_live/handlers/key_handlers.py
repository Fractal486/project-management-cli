"""Key event handlers for the live CLI."""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from pm import STATUS_DISPLAY_ORDER

from ..interfaces import HandlerContext
from ..states import AppState
from .text_input import TextInputBuffer
from ..quick_stats import QUICK_STATS_ORDER
from ..utils import filter_projects_by_tab, get_edit_project_field_keys, get_visible_fields_sorted, sort_projects_for_display
from ..utils.calendar import CalendarEntry, collect_deadline_map, parse_deadline_date
from ..main_menu_tabs import build_main_menu_items, is_quick_add_enabled, MAIN_MENU_TABS_ORDER
from ..custom_fields import get_all_fields
from ..tasks import flatten_tasks

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - only for type checking
    from .enter_handlers import EnterHandlers
    from .task_handlers import TaskHandlers


class KeyHandlers:
    """Handles keyboard input events."""

    def __init__(
        self,
        context: HandlerContext,
        task_handlers: "TaskHandlers",
        enter_handlers: "EnterHandlers",
    ):
        """Initialize with shared handler context and collaborators."""
        self._context = context
        self.manager = context.manager
        self.ui_state = context.ui_state
        self._get_flat_tasks = context.get_flat_tasks
        self._invalidate_task_cache = context.invalidate_task_cache
        self._exit_application = context.exit_application
        self._task_handlers = task_handlers
        self._enter_handlers = enter_handlers

    def on_up(self):
        """Handle up key with bounds clamping."""
        # Navigate search results
        if self.ui_state.state == AppState.SEARCH:
            if self.ui_state.search_selected_index > 0:
                self.ui_state.search_selected_index -= 1
            return

        if self.ui_state.state == AppState.CALENDAR:
            # If in inline edit mode, let the inline edit handlers below handle it
            if not self.ui_state.inline_task_edit_mode:
                focus = self.ui_state.calendar_navigation_focus
                if focus == "tasks":
                    tasks = self._get_calendar_tasks_for_active_tab()
                    if not tasks:
                        self.ui_state.calendar_navigation_focus = "back"
                    elif self.ui_state.calendar_task_selected_index > 0:
                        self.ui_state.calendar_task_selected_index -= 1
                    return
                if focus == "back":
                    # Move to tasks section (Add button or last task)
                    self.ui_state.calendar_navigation_focus = "tasks"
                    tasks = self._get_calendar_tasks_for_active_tab()
                    has_add = self._has_add_button_in_calendar()
                    max_idx = len(tasks) if has_add else (len(tasks) - 1 if tasks else 0)
                    self.ui_state.calendar_task_selected_index = max_idx
                    return
                # If on navigation arrows, do nothing (already at top)
                if focus in ["prev", "next"]:
                    return

                # Check if we're on the first week of the month
                from calendar import monthrange
                year = self.ui_state.calendar_year
                month = self.ui_state.calendar_month
                selected_day = self.ui_state.calendar_selected_day or 1

                # Get the weekday of the 1st day of the month (0=Monday, 6=Sunday)
                first_weekday, _ = monthrange(year, month)
                # Adjust to Sunday=0 (calendar module uses Monday=0)
                first_weekday_sunday = (first_weekday + 1) % 7

                # Days on the first week: 1 to (7 - first_weekday_sunday)
                first_week_last_day = 7 - first_weekday_sunday

                if selected_day <= first_week_last_day:
                    # Move to navigation arrows (default to left arrow)
                    self.ui_state.calendar_navigation_focus = "prev"
                else:
                    # Move up one week within the calendar
                    self._calendar_move_day(-7, allow_month_wrap=False)
                return

        # Cell editing mode in project browser - adjust date or cycle value
        if self.ui_state.state == AppState.PROJECT_BROWSER and self.ui_state.cell_editing:
            field = self._get_cell_selected_field()
            if field and field.field_type == 'date':
                self._adjust_cell_edit_date(1)
            return

        # Cell selection mode in project browser - move row, keep column
        if self.ui_state.state == AppState.PROJECT_BROWSER and self.ui_state.cell_selection_mode and not self.ui_state.cell_editing:
            if self.ui_state.selected_index > 0:
                self.ui_state.selected_index -= 1
            else:
                self.ui_state.selected_index = -1
            return

        # Custom field date edit mode
        if self.ui_state.custom_field_date_edit_mode:
            self._adjust_custom_field_date(1)
            return

        # Inline task edit: use arrows to edit fields rather than moving selection
        if self.ui_state.inline_task_edit_mode:
            if self.ui_state.inline_edit_field_index == 1:
                self._adjust_inline_edit_deadline(1)
            elif self.ui_state.inline_edit_field_index == 2:
                self._cycle_inline_edit_priority(1)
            elif self.ui_state.inline_edit_field_index == 3:
                # Up from notes → go to name field
                self.ui_state.inline_edit_field_index = 0
                self.ui_state.inline_edit_name_cursor = len(self.ui_state.inline_edit_name)
            return

        if self.ui_state.inline_input_mode:
            if self.ui_state.state == AppState.MAIN_MENU:
                # Check if in deadline edit mode
                if self.ui_state.quick_add_deadline_edit_mode and self.ui_state.quick_add_field_index == 2:
                    self._cycle_deadline_component(1)  # Increment
                    return
                self.ui_state.quick_add_field_index = max(0, self.ui_state.quick_add_field_index - 1)
            elif self.ui_state.state in [AppState.ADD_PROJECT, AppState.EDIT_PROJECT, AppState.ADD_BOOKMARK, AppState.EDIT_BOOKMARK, AppState.EDIT_TAB, AppState.ADD_CUSTOM_FIELD, AppState.EDIT_CUSTOM_FIELD]:
                # For form states, save input, exit inline input mode and navigate with arrow keys
                self._save_current_inline_input()
                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
                max_field_index = self._get_max_form_index()
                self.ui_state.form_field_index = max(0, min(self.ui_state.form_field_index - 1, max_field_index))
            return

        if self.ui_state.state == AppState.PROJECT_BROWSER and not self.ui_state.cell_selection_mode:
            if self.ui_state.selected_index > 0:
                self.ui_state.selected_index -= 1
            elif self.ui_state.selected_index == 0:
                self.ui_state.selected_index = -1
            return

        if self.ui_state.state in [AppState.ADD_PROJECT, AppState.EDIT_PROJECT, AppState.ADD_BOOKMARK, AppState.EDIT_BOOKMARK, AppState.EDIT_TAB, AppState.ADD_CUSTOM_FIELD, AppState.EDIT_CUSTOM_FIELD, AppState.DELETE_CONFIRMATION]:
            # For form states, navigate form fields with clamping
            max_field_index = self._get_max_form_index()
            self.ui_state.form_field_index = max(0, min(self.ui_state.form_field_index - 1, max_field_index))
        elif self.ui_state.state == AppState.MAIN_MENU and self.ui_state.in_pinned_section:
            # In pinned section - move up within pinned items or exit to regular menu
            display_len = len(getattr(self.ui_state, "pinned_display_items", []) or self.manager.get_pinned_items())
            if self.ui_state.pinned_selected_index > 0:
                self.ui_state.pinned_selected_index -= 1
            else:
                # Exit pinned section, go to last regular menu item (Exit)
                self.ui_state.in_pinned_section = False
                self.ui_state.pinned_selected_index = 0
                max_index = self._get_max_index()
                self.ui_state.selected_index = max_index
        else:
            # Clamp selected_index to valid range [0, max_index]
            max_index = self._get_max_index()
            new_index = max(0, min(self.ui_state.selected_index - 1, max_index))
            self.ui_state.selected_index = new_index

    def on_down(self):
        """Handle down key with bounds clamping."""
        # Navigate search results
        if self.ui_state.state == AppState.SEARCH:
            max_index = max(0, len(self.ui_state.search_results) - 1)
            if self.ui_state.search_selected_index < max_index:
                self.ui_state.search_selected_index += 1
            return

        if self.ui_state.state == AppState.CALENDAR:
            # If in inline edit mode, let the inline edit handlers below handle it
            if not self.ui_state.inline_task_edit_mode:
                focus = self.ui_state.calendar_navigation_focus
                # If on navigation arrows, move to first week of calendar
                if focus in ["prev", "next"]:
                    self.ui_state.calendar_navigation_focus = "day"
                    if not self.ui_state.calendar_selected_day:
                        self.ui_state.calendar_selected_day = 1
                    return
                
                if focus == "tasks":
                    tasks = self._get_calendar_tasks_for_active_tab()
                    has_add = self._has_add_button_in_calendar()
                    # Max index depends on whether tab has '+' button
                    max_task_idx = len(tasks) if has_add else (len(tasks) - 1 if tasks else 0)
                    if not tasks:
                        self.ui_state.calendar_navigation_focus = "back"
                    elif self.ui_state.calendar_task_selected_index < max_task_idx:
                        self.ui_state.calendar_task_selected_index += 1
                    else:
                        self.ui_state.calendar_navigation_focus = "back"
                    return
                
                if focus == "back":
                    return

                if not self.ui_state.calendar_selected_day:
                    self.ui_state.calendar_selected_day = 1
                    return

                year = self.ui_state.calendar_year
                month = self.ui_state.calendar_month
                selected_day = self.ui_state.calendar_selected_day
                if self._calendar_is_last_week_day(year, month, selected_day):
                    return
                else:
                    # Move down one week within the calendar
                    self._calendar_move_day(7, allow_month_wrap=False)
                return

        # Cell editing mode in project browser - adjust date or cycle value
        if self.ui_state.state == AppState.PROJECT_BROWSER and self.ui_state.cell_editing:
            field = self._get_cell_selected_field()
            if field and field.field_type == 'date':
                self._adjust_cell_edit_date(-1)
            return

        # Cell selection mode in project browser - move row, keep column
        if self.ui_state.state == AppState.PROJECT_BROWSER and self.ui_state.cell_selection_mode and not self.ui_state.cell_editing:
            filtered = self._get_filtered_projects_sorted()
            if self.ui_state.selected_index == -1 and filtered:
                self.ui_state.selected_index = 0
            else:
                max_project_idx = len(filtered) - 1
                if self.ui_state.selected_index < max_project_idx:
                    self.ui_state.selected_index += 1
            return

        # Custom field date edit mode
        if self.ui_state.custom_field_date_edit_mode:
            self._adjust_custom_field_date(-1)
            return

        if self.ui_state.inline_task_edit_mode:
            if self.ui_state.inline_edit_field_index == 0:
                # Down from name → go to notes field
                self.ui_state.inline_edit_field_index = 3
                self.ui_state.inline_edit_notes_cursor = len(self.ui_state.inline_edit_notes or "")
            elif self.ui_state.inline_edit_field_index == 1:
                self._adjust_inline_edit_deadline(-1)
            elif self.ui_state.inline_edit_field_index == 2:
                self._cycle_inline_edit_priority(-1)
            return

        if self.ui_state.inline_input_mode:
            if self.ui_state.state == AppState.MAIN_MENU:
                # Check if in deadline edit mode
                if self.ui_state.quick_add_deadline_edit_mode and self.ui_state.quick_add_field_index == 2:
                    self._cycle_deadline_component(-1)  # Decrement
                    return
                self.ui_state.quick_add_field_index = min(4, self.ui_state.quick_add_field_index + 1)
            elif self.ui_state.state in [AppState.ADD_PROJECT, AppState.EDIT_PROJECT, AppState.ADD_BOOKMARK, AppState.EDIT_BOOKMARK, AppState.EDIT_TAB, AppState.ADD_CUSTOM_FIELD, AppState.EDIT_CUSTOM_FIELD]:
                # For form states, save input, exit inline input mode and navigate with arrow keys
                self._save_current_inline_input()
                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
                max_field_index = self._get_max_form_index()
                self.ui_state.form_field_index = max(0, min(self.ui_state.form_field_index + 1, max_field_index))
            return

        if self.ui_state.state in [AppState.ADD_PROJECT, AppState.EDIT_PROJECT, AppState.ADD_BOOKMARK, AppState.EDIT_BOOKMARK, AppState.EDIT_TAB, AppState.ADD_CUSTOM_FIELD, AppState.EDIT_CUSTOM_FIELD, AppState.DELETE_CONFIRMATION]:
            # For form states, navigate form fields with clamping
            max_field_index = self._get_max_form_index()
            self.ui_state.form_field_index = max(0, min(self.ui_state.form_field_index + 1, max_field_index))
        elif self.ui_state.state == AppState.MAIN_MENU and self.ui_state.in_pinned_section:
            # In pinned section - move down within pinned items
            display_len = len(getattr(self.ui_state, "pinned_display_items", []) or self.manager.get_pinned_items())
            max_pinned = display_len - 1
            if self.ui_state.pinned_selected_index < max_pinned:
                self.ui_state.pinned_selected_index += 1
        elif self.ui_state.state == AppState.MAIN_MENU and not self.ui_state.in_pinned_section:
            # In regular menu - check if at last item and there are pinned items
            max_index = self._get_max_index()
            if self.ui_state.selected_index >= max_index:
                # At last regular menu item (Exit) - check if there are pinned items
                pinned_items = self.manager.get_pinned_items()
                if pinned_items:
                    # Enter pinned section
                    self.ui_state.in_pinned_section = True
                    self.ui_state.pinned_selected_index = 0
            else:
                # Move down in regular menu
                new_index = max(0, min(self.ui_state.selected_index + 1, max_index))
                self.ui_state.selected_index = new_index
        else:
            # Clamp selected_index to valid range [0, max_index]
            max_index = self._get_max_index()
            new_index = max(0, min(self.ui_state.selected_index + 1, max_index))
            self.ui_state.selected_index = new_index

    def on_left(self):
        """Handle left arrow key."""
        if self.ui_state.state == AppState.CALENDAR:
            # If in inline edit mode, let the inline edit handlers below handle it
            if not self.ui_state.inline_task_edit_mode:
                focus = self.ui_state.calendar_navigation_focus
                if focus in ["tasks", "back"]:
                    return
                # If on navigation arrows, switch to prev arrow
                if focus in ["prev", "next"]:
                    self.ui_state.calendar_navigation_focus = "prev"
                else:
                    # Normal day navigation
                    if not self.ui_state.calendar_selected_day:
                        self.ui_state.calendar_selected_day = 1
                    self._calendar_move_day(-1)
                return

        # Cell editing mode in project browser - navigate date components
        if self.ui_state.state == AppState.PROJECT_BROWSER and self.ui_state.cell_editing:
            field = self._get_cell_selected_field()
            if field and field.field_type == 'date':
                self.ui_state.cell_edit_date_component = (self.ui_state.cell_edit_date_component - 1) % 3
            return

        # Cell selection mode in project browser - move column or exit
        if self.ui_state.state == AppState.PROJECT_BROWSER and self.ui_state.cell_selection_mode:
            if self.ui_state.cell_selected_column > 0:
                self.ui_state.cell_selected_column -= 1
            else:
                # Exit cell selection mode when moving left from first column
                self._exit_cell_selection_mode()
            return

        if self.ui_state.custom_field_date_edit_mode:
            # Cycle date component left: day -> month -> year
            self.ui_state.custom_field_date_component = (self.ui_state.custom_field_date_component - 1) % 3
            return

        if self.ui_state.inline_task_edit_mode:
            if self.ui_state.inline_edit_field_index == 0:
                self.ui_state.inline_edit_name_cursor = max(0, self.ui_state.inline_edit_name_cursor - 1)
            elif self.ui_state.inline_edit_field_index == 1:
                self.ui_state.inline_edit_deadline_component = (self.ui_state.inline_edit_deadline_component - 1) % 3
            elif self.ui_state.inline_edit_field_index == 3:
                self.ui_state.inline_edit_notes_cursor = max(0, self.ui_state.inline_edit_notes_cursor - 1)
            return

        # Outdent (left arrow) for tasks in TASK_LIST or PROJECT_DETAILS
        if not self.ui_state.inline_input_mode:
            if self.ui_state.state in (AppState.TASK_LIST, AppState.PROJECT_DETAILS):
                self._task_handlers.handle_outdent()
                return

        if self.ui_state.inline_input_mode:
            if self.ui_state.state == AppState.MAIN_MENU:
                # Check if in deadline edit mode
                if self.ui_state.quick_add_deadline_edit_mode and self.ui_state.quick_add_field_index == 2:
                    # Move to previous component: wrap day -> month -> year
                    self.ui_state.quick_add_deadline_component = (self.ui_state.quick_add_deadline_component - 1) % 3
                    return
                if self.ui_state.quick_add_field_index != 0:
                    return
            self.ui_state.text_input_cursor = TextInputBuffer.move_left(
                self.ui_state.text_input_buffer,
                self.ui_state.text_input_cursor,
            )
            return

    def on_right(self):
        """Handle right arrow key."""
        if self.ui_state.state == AppState.CALENDAR:
            # If in inline edit mode, let the inline edit handlers below handle it
            if not self.ui_state.inline_task_edit_mode:
                focus = self.ui_state.calendar_navigation_focus
                if focus in ["tasks", "back"]:
                    return
                # If on navigation arrows, switch to next arrow
                if focus in ["prev", "next"]:
                    self.ui_state.calendar_navigation_focus = "next"
                else:
                    # Normal day navigation
                    if not self.ui_state.calendar_selected_day:
                        self.ui_state.calendar_selected_day = 1
                    self._calendar_move_day(1)
                return

        # Cell editing mode in project browser - navigate date components
        if self.ui_state.state == AppState.PROJECT_BROWSER and self.ui_state.cell_editing:
            field = self._get_cell_selected_field()
            if field and field.field_type == 'date':
                self.ui_state.cell_edit_date_component = (self.ui_state.cell_edit_date_component + 1) % 3
            return

        # Cell selection mode in project browser - move column or enter cell mode
        if self.ui_state.state == AppState.PROJECT_BROWSER and not self.ui_state.cell_selection_mode:
            # Check if we're on a project row (not an action)
            filtered = self._get_filtered_projects_sorted()
            if self.ui_state.selected_index < len(filtered):
                # Enter cell selection mode
                self._enter_cell_selection_mode()
                return

        if self.ui_state.state == AppState.PROJECT_BROWSER and self.ui_state.cell_selection_mode:
            # Move to next column
            visible_fields = self._get_visible_fields_for_cell_mode()
            max_col = len(visible_fields) - 1
            if self.ui_state.cell_selected_column < max_col:
                self.ui_state.cell_selected_column += 1
            return

        if self.ui_state.custom_field_date_edit_mode:
            # Cycle date component right: year -> month -> day
            self.ui_state.custom_field_date_component = (self.ui_state.custom_field_date_component + 1) % 3
            return

        if self.ui_state.inline_task_edit_mode:
            if self.ui_state.inline_edit_field_index == 0:
                name_len = len(self.ui_state.inline_edit_name)
                self.ui_state.inline_edit_name_cursor = min(name_len, self.ui_state.inline_edit_name_cursor + 1)
            elif self.ui_state.inline_edit_field_index == 1:
                self.ui_state.inline_edit_deadline_component = (self.ui_state.inline_edit_deadline_component + 1) % 3
            elif self.ui_state.inline_edit_field_index == 3:
                notes_len = len(self.ui_state.inline_edit_notes or "")
                self.ui_state.inline_edit_notes_cursor = min(notes_len, self.ui_state.inline_edit_notes_cursor + 1)
            return

        # Indent (right arrow) for tasks in TASK_LIST or PROJECT_DETAILS
        if not self.ui_state.inline_input_mode:
            if self.ui_state.state in (AppState.TASK_LIST, AppState.PROJECT_DETAILS):
                self._task_handlers.handle_indent()
                return

        if self.ui_state.inline_input_mode:
            if self.ui_state.state == AppState.MAIN_MENU:
                # Check if in deadline edit mode
                if self.ui_state.quick_add_deadline_edit_mode and self.ui_state.quick_add_field_index == 2:
                    # Move to next component: wrap year -> month -> day
                    self.ui_state.quick_add_deadline_component = (self.ui_state.quick_add_deadline_component + 1) % 3
                    return
                if self.ui_state.quick_add_field_index != 0:
                    return
            self.ui_state.text_input_cursor = TextInputBuffer.move_right(
                self.ui_state.text_input_buffer,
                self.ui_state.text_input_cursor,
            )
            return

    def on_tab(self):
        """Handle tab key.

        - In inline task edit mode: cycle inline task fields.
        - In ADD/EDIT_CUSTOM_FIELD on a select option row: cycle option color.
        - In calendar: toggle between calendar grid and tasks section.
        - Otherwise: switch tabs in project browser / task list.
        """
        if self.ui_state.inline_task_edit_mode:
            # Tab order: name -> priority -> deadline (notes not in tab cycle, only via down arrow)
            tab_order = [0, 2, 1]
            current = self.ui_state.inline_edit_field_index
            # If currently on notes (3), tab goes back to name
            if current == 3:
                next_idx = 0
            else:
                try:
                    next_idx = tab_order[(tab_order.index(current) + 1) % len(tab_order)]
                except ValueError:
                    next_idx = 0
            self.ui_state.inline_edit_field_index = next_idx
            if self.ui_state.inline_edit_field_index == 0:
                self.ui_state.inline_edit_name_cursor = len(self.ui_state.inline_edit_name)
            return

        # Inline color cycling for single-select options in custom field forms
        if self.ui_state.state in (AppState.ADD_CUSTOM_FIELD, AppState.EDIT_CUSTOM_FIELD):
            form_data = self.ui_state.form_data
            field_type = form_data.get('field_type', 'text')
            if field_type == 'single_select':
                from pm import LIST_COLOR_OPTIONS
                options = form_data.get('select_options', []) or []
                core_count = 4  # label, field_type, visible, required
                if field_type == 'number':  # not used here but keep logic symmetric
                    core_count += 1
                    if form_data.get('number_format') == 'currency':
                        core_count += 1
                options_start = core_count
                idx = self.ui_state.form_field_index
                # Only operate when cursor is over an existing option row
                if options_start <= idx < options_start + len(options):
                    opt_idx = idx - options_start
                    opt = options[opt_idx]
                    current_color = getattr(opt, 'color', None) if not isinstance(opt, dict) else opt.get('color')
                    colors = [None] + list(LIST_COLOR_OPTIONS)
                    try:
                        cur_i = colors.index(current_color)
                    except ValueError:
                        cur_i = 0
                    next_i = (cur_i + 1) % len(colors)
                    new_color = colors[next_i]
                    if isinstance(opt, dict):
                        opt['color'] = new_color
                    else:
                        opt.color = new_color
                    form_data['select_options'] = options
                    return

        if self.ui_state.state == AppState.CALENDAR:
            focus = self.ui_state.calendar_navigation_focus
            if focus == "tasks":
                # Cycle through tabs: 0 -> 1 -> 2 -> 0
                self.ui_state.calendar_tasks_tab = (self.ui_state.calendar_tasks_tab + 1) % 3
                self.ui_state.calendar_task_selected_index = 0  # Reset selection
            # When focus is on calendar grid, Tab does nothing (use Shift+Tab to switch focus)
            return

        if self.ui_state.state == AppState.PROJECT_BROWSER:
            self.ui_state.active_tab = (self.ui_state.active_tab + 1) % 3
            self.ui_state.selected_index = 0
        elif self.ui_state.state == AppState.TASK_LIST:
            # Cycle through dynamically added task lists
            num_lists = max(1, len(getattr(self.ui_state, "task_lists", ["Tasks"])))
            self.ui_state.active_tab = (self.ui_state.active_tab + 1) % num_lists
            self.ui_state.selected_index = 0
            self._invalidate_task_cache()

    def on_shift_tab(self):
        """Handle Shift+Tab key - switch focus in calendar."""
        if self.ui_state.state == AppState.CALENDAR:
            focus = self.ui_state.calendar_navigation_focus
            if focus in ["day", "prev", "next"]:
                # Switch from calendar grid to tasks section
                self.ui_state.calendar_navigation_focus = "tasks"
                self.ui_state.calendar_task_selected_index = 0
            elif focus == "tasks":
                # Switch from tasks section back to calendar grid
                self.ui_state.calendar_navigation_focus = "day"
                if not self.ui_state.calendar_selected_day:
                    self.ui_state.calendar_selected_day = 1
            elif focus == "back":
                # From back button, go to tasks section
                self.ui_state.calendar_navigation_focus = "tasks"
                self.ui_state.calendar_task_selected_index = 0

    def on_collapse(self):
        """Handle 'c' key - collapse/expand or type 'c' in input mode."""
        if self.ui_state.inline_task_edit_mode:
            if self.ui_state.inline_edit_field_index == 0:
                self._insert_inline_edit_char('c')
            elif self.ui_state.inline_edit_field_index == 3:
                self._insert_inline_notes_char('c')
            return

        # If in text input mode, type the character
        if self.ui_state.inline_input_mode:
            if self.ui_state.state == AppState.MAIN_MENU and self.ui_state.quick_add_field_index != 0:
                return
            from .text_input import TextInputBuffer

            # When tests (or callers) prefill the buffer without the cursor, default to appending.
            if (
                self.ui_state.state == AppState.MAIN_MENU
                and self.ui_state.quick_add_field_index == 0
                and self.ui_state.text_input_buffer
                and self.ui_state.text_input_cursor == 0
            ):
                self.ui_state.text_input_cursor = len(self.ui_state.text_input_buffer)

            buffer, cursor = TextInputBuffer.insert(
                self.ui_state.text_input_buffer,
                self.ui_state.text_input_cursor,
                'c',
            )
            self.ui_state.text_input_buffer = buffer
            self.ui_state.text_input_cursor = cursor
        # Project browser: cycle project status
        elif self.ui_state.state == AppState.PROJECT_BROWSER and not self.ui_state.cell_editing:
            if self.ui_state.cell_selection_mode:
                return
            filtered = self._get_filtered_projects_sorted()
            idx = self.ui_state.selected_index
            if 0 <= idx < len(filtered):
                project = filtered[idx]
                current_status = getattr(project, "status", None)
                order = STATUS_DISPLAY_ORDER
                if current_status in order:
                    next_status = order[(order.index(current_status) + 1) % len(order)]
                else:
                    next_status = order[0] if order else current_status
                if next_status is not None:
                    project.status = next_status
                    try:
                        self.manager.save()
                    except Exception:
                        pass
            return
        # Calendar: cycle project status for project date entries
        elif self.ui_state.state == AppState.CALENDAR and self.ui_state.calendar_navigation_focus == "tasks":
            tasks = self._get_calendar_tasks_for_active_tab()
            idx = self.ui_state.calendar_task_selected_index
            if 0 <= idx < len(tasks):
                entry = tasks[idx]
                if entry.kind == "project_field":
                    project = entry.item
                    current_status = getattr(project, "status", None)
                    order = STATUS_DISPLAY_ORDER
                    if current_status in order:
                        next_status = order[(order.index(current_status) + 1) % len(order)]
                    else:
                        next_status = order[0] if order else current_status
                    if next_status is not None:
                        project.status = next_status
                        try:
                            self.manager.save()
                        except Exception:
                            pass
                    return
        # Main menu pinned projects: cycle project status
        elif self.ui_state.state == AppState.MAIN_MENU and self.ui_state.in_pinned_section:
            display_items = getattr(self.ui_state, "pinned_display_items", None)
            items = getattr(self.ui_state, "reordered_pinned_items", None)
            if not items:
                pinned_items = self.manager.get_pinned_items()
                pinned_projects = [p for p in pinned_items if p.get("type") == "project"]
                pinned_tasks = [p for p in pinned_items if p.get("type") in ("task", "list", "section")]
                pinned_bookmarks = [p for p in pinned_items if p.get("type") in ("bookmark", "bookmark_list")]
                items = pinned_projects + pinned_tasks + pinned_bookmarks
            target_list = display_items or items
            idx = self.ui_state.pinned_selected_index
            if 0 <= idx < len(target_list):
                entry = target_list[idx]
                if display_items:
                    if entry.get("kind") != "pinned":
                        return
                    item = entry.get("item", {})
                else:
                    item = entry
                if item.get("type") != "project":
                    return
                project_id = item.get("id")
                project = self.manager.get_project(project_id)
                if not project:
                    return
                current_status = getattr(project, "status", None)
                order = STATUS_DISPLAY_ORDER
                if current_status in order:
                    next_status = order[(order.index(current_status) + 1) % len(order)]
                else:
                    next_status = order[0] if order else current_status
                if next_status is not None:
                    project.status = next_status
                    try:
                        self.manager.save()
                    except Exception:
                        pass
                return
        # Otherwise handle collapse/expand
        elif self.ui_state.state in [AppState.PROJECT_DETAILS, AppState.TASK_LIST]:
            self._task_handlers.handle_collapse_toggle()

    def on_char(self, char: str):
        """Handle character input."""
        # Search mode - update query and perform search
        if self.ui_state.state == AppState.SEARCH:
            self.ui_state.search_query += char
            # Perform search and update results
            from ..utils import perform_search
            self.ui_state.search_results = perform_search(self.manager, self.ui_state.search_query)
            self.ui_state.search_selected_index = 0
            return

        # Cell editing mode - add character to buffer for text/number fields
        if self.ui_state.state == AppState.PROJECT_BROWSER and self.ui_state.cell_editing:
            field = self._get_cell_selected_field()
            if field and field.field_type in ('text', 'number'):
                if field.field_type == 'number':
                    # Only allow numeric characters for number fields
                    if not (char.isdigit() or char in ['.', '-']):
                        return
                self.ui_state.cell_edit_buffer += char
            return

        if self.ui_state.inline_task_edit_mode:
            if self.ui_state.inline_edit_field_index == 0:
                self._insert_inline_edit_char(char)
            elif self.ui_state.inline_edit_field_index == 3:
                self._insert_inline_notes_char(char)
            return

        if self.ui_state.inline_input_mode:
            if self.ui_state.state == AppState.MAIN_MENU and self.ui_state.quick_add_field_index != 0:
                return

            # Check if we're in a project form (add/edit) and need to validate number field input
            if self.ui_state.state in [AppState.ADD_PROJECT, AppState.EDIT_PROJECT]:
                # Get the current field being edited
                all_fields = get_all_fields(self.manager.default_field_visibility, self.manager.custom_field_definitions)

                # Determine which field is being edited based on form_field_index
                if self.ui_state.state == AppState.ADD_PROJECT:
                    # For add project: name, status, then custom fields in order
                    field_keys = ["name", "status"] + [field.key for field in get_visible_fields_sorted(all_fields)]
                else:  # EDIT_PROJECT
                    from ..utils import get_edit_project_field_keys
                    field_keys = get_edit_project_field_keys(all_fields)

                # Get the current field being edited
                if 0 <= self.ui_state.form_field_index < len(field_keys):
                    current_field_name = field_keys[self.ui_state.form_field_index]

                    # Check if this is a custom field and whether it's a number field
                    field_def = next((f for f in all_fields if f.key == current_field_name), None)
                    if field_def and field_def.field_type == 'number':
                        # Only allow numeric characters, decimal point, and negative sign for number fields
                        if not (char.isdigit() or char in ['.', '-']):
                            # Optionally show status message about invalid input
                            return

            buffer, cursor = TextInputBuffer.insert(
                self.ui_state.text_input_buffer,
                self.ui_state.text_input_cursor,
                char,
            )
            self.ui_state.text_input_buffer = buffer
            self.ui_state.text_input_cursor = cursor
            return

    def on_backspace(self):
        """Handle backspace."""
        # Search mode - delete character from query
        if self.ui_state.state == AppState.SEARCH:
            if self.ui_state.search_query:
                self.ui_state.search_query = self.ui_state.search_query[:-1]
                # Perform search with updated query
                from ..utils import perform_search
                self.ui_state.search_results = perform_search(self.manager, self.ui_state.search_query)
                self.ui_state.search_selected_index = 0
            return

        if self.ui_state.custom_field_date_edit_mode:
            # Clear the date, clear the underlying field, and exit date edit mode so arrow keys return to navigation
            self._clear_current_project_form_field()
            self.ui_state.custom_field_date_buffer = None
            self.ui_state.custom_field_date_edit_mode = False
            self.ui_state.custom_field_date_component = 0
            return

        # Cell editing mode - handle backspace
        if self.ui_state.state == AppState.PROJECT_BROWSER and self.ui_state.cell_editing:
            field = self._get_cell_selected_field()
            if field:
                if field.field_type in ('text', 'number'):
                    if self.ui_state.cell_edit_buffer:
                        self.ui_state.cell_edit_buffer = self.ui_state.cell_edit_buffer[:-1]
                elif field.field_type == 'date':
                    # Clear date, save empty value, and return to cell selection mode
                    if self.ui_state.selected_index >= 0:
                        filtered = self._get_filtered_projects_sorted()
                        if self.ui_state.selected_index < len(filtered):
                            project = filtered[self.ui_state.selected_index]
                            self._enter_handlers._save_cell_value(project, field.key, None)
                    self.ui_state.cell_editing = False
                    self.ui_state.cell_edit_date_buffer = None
                    self.ui_state.cell_edit_date_component = 0
            return

        # Cell selection mode (not editing) - clear the selected field
        if self.ui_state.state == AppState.PROJECT_BROWSER and self.ui_state.cell_selection_mode and not self.ui_state.cell_editing:
            field = self._get_cell_selected_field()
            if field and field.key not in ("__progress__",) and self.ui_state.selected_index >= 0:
                filtered = self._get_filtered_projects_sorted()
                if self.ui_state.selected_index < len(filtered):
                    project = filtered[self.ui_state.selected_index]
                    # Clear the field by setting it to None
                    self._enter_handlers._save_cell_value(project, field.key, None)
            return

        if self.ui_state.inline_task_edit_mode:
            if self.ui_state.inline_edit_field_index == 0:
                if self.ui_state.inline_edit_name_cursor > 0 and self.ui_state.inline_edit_name:
                    idx = self.ui_state.inline_edit_name_cursor
                    self.ui_state.inline_edit_name = (
                        self.ui_state.inline_edit_name[:idx - 1] + self.ui_state.inline_edit_name[idx:]
                    )
                    self.ui_state.inline_edit_name_cursor -= 1
                return
            if self.ui_state.inline_edit_field_index == 1:
                # Clear deadline when backspacing in deadline field
                self.ui_state.inline_edit_deadline = None
                return
            if self.ui_state.inline_edit_field_index == 2:
                # Reset priority when backspacing in priority field
                self.ui_state.inline_edit_priority = "none"
                return
            if self.ui_state.inline_edit_field_index == 3:
                if self.ui_state.inline_edit_notes_cursor > 0 and self.ui_state.inline_edit_notes:
                    idx = self.ui_state.inline_edit_notes_cursor
                    self.ui_state.inline_edit_notes = (
                        self.ui_state.inline_edit_notes[:idx - 1] + self.ui_state.inline_edit_notes[idx:]
                    )
                    self.ui_state.inline_edit_notes_cursor -= 1
                return

        # When not typing inline, treat backspace as "clear current form field" in project forms
        if not self.ui_state.inline_input_mode:
            if self.ui_state.state in [AppState.ADD_PROJECT, AppState.EDIT_PROJECT]:
                self._clear_current_project_form_field()
            return

        # Handle quick add task form field clearing
        if self.ui_state.state == AppState.MAIN_MENU and self.ui_state.inline_input_mode:
            field_idx = self.ui_state.quick_add_field_index
            if field_idx == 1:
                # Clear priority
                self.ui_state.quick_add_priority = None
                return
            elif field_idx == 2:
                # Clear deadline and exit deadline edit mode
                self.ui_state.quick_add_deadline = None
                self.ui_state.quick_add_deadline_edit_mode = False
                self.ui_state.quick_add_deadline_component = 0
                return
            elif field_idx == 3:
                # Reset list to default "Tasks"
                self.ui_state.quick_add_list = "Tasks"
                return
            elif field_idx != 0:
                # For other fields (like Add button), do nothing
                return
            else:
                buffer, cursor = TextInputBuffer.backspace(
                    self.ui_state.text_input_buffer,
                    self.ui_state.text_input_cursor,
                )
                self.ui_state.text_input_buffer = buffer
                self.ui_state.text_input_cursor = cursor
                return

        if self.ui_state.inline_input_mode:
            buffer, cursor = TextInputBuffer.backspace(
                self.ui_state.text_input_buffer,
                self.ui_state.text_input_cursor,
            )
            self.ui_state.text_input_buffer = buffer
            self.ui_state.text_input_cursor = cursor
            return

        # Check if we're in a project form (add/edit) and need to handle number field input
        if self.ui_state.state in [AppState.ADD_PROJECT, AppState.EDIT_PROJECT]:
            all_fields = get_all_fields(self.manager.default_field_visibility, self.manager.custom_field_definitions)

            # Determine which field is being edited based on form_field_index
            if self.ui_state.state == AppState.ADD_PROJECT:
                # For add project: name, status, then custom fields in order
                field_keys = ["name", "status"] + [field.key for field in get_visible_fields_sorted(all_fields)]
            else:  # EDIT_PROJECT
                from ..utils import get_edit_project_field_keys
                field_keys = get_edit_project_field_keys(all_fields)

            # Get the current field being edited
            if 0 <= self.ui_state.form_field_index < len(field_keys):
                current_field_name = field_keys[self.ui_state.form_field_index]

                # Check if this is a custom field and whether it's a number field
                field_def = next((f for f in all_fields if f.key == current_field_name), None)
                if field_def and field_def.field_type == 'number':
                    # For number fields, allow backspace normally
                    if self.ui_state.text_input_buffer:
                        self.ui_state.text_input_buffer = self.ui_state.text_input_buffer[:-1]
                    return

        if self.ui_state.text_input_buffer:
            self.ui_state.text_input_buffer = self.ui_state.text_input_buffer[:-1]

    def on_delete(self):
        """Handle Delete key.

        - In DELETE_CONFIRMATION: confirm deletion (equivalent to "Yes, delete it").
        - In EDIT_TAB list-edit mode: delete section (existing behavior).
        - In ADD/EDIT_CUSTOM_FIELD on a select option row: delete that option.
        - In MAIN_MENU pinned section: delete selected pinned item (with confirmation).
        - In BOOKMARKS: delete selected bookmark or list.
        - In BOOKMARK_LIST: delete selected bookmark.
        - Otherwise: delegate to task delete.
        """
        # View sections delete (existing behavior)
        from ..states import AppState as _AS

        if self.ui_state.inline_task_edit_mode:
            if self.ui_state.inline_edit_field_index == 0:
                # Delete at cursor in name field
                if self.ui_state.inline_edit_name_cursor < len(self.ui_state.inline_edit_name):
                    idx = self.ui_state.inline_edit_name_cursor
                    self.ui_state.inline_edit_name = (
                        self.ui_state.inline_edit_name[:idx] + self.ui_state.inline_edit_name[idx + 1:]
                    )
                return
            if self.ui_state.inline_edit_field_index == 3:
                # Delete at cursor in notes field
                notes = self.ui_state.inline_edit_notes or ""
                if self.ui_state.inline_edit_notes_cursor < len(notes):
                    idx = self.ui_state.inline_edit_notes_cursor
                    self.ui_state.inline_edit_notes = notes[:idx] + notes[idx + 1:]
                return

        if self.ui_state.inline_input_mode:
            if self.ui_state.state == _AS.MAIN_MENU and self.ui_state.quick_add_field_index != 0:
                return
            buffer, cursor = TextInputBuffer.delete(
                self.ui_state.text_input_buffer,
                self.ui_state.text_input_cursor,
            )
            self.ui_state.text_input_buffer = buffer
            self.ui_state.text_input_cursor = cursor
            return
        
        # Delete confirmation: treat DEL as "Yes, delete it"
        if self.ui_state.state == _AS.DELETE_CONFIRMATION:
            self.ui_state.form_field_index = 0  # Select "Yes, delete it"
            self._enter_handlers.handle_delete_confirmation_enter()
            return

        # Main menu pinned item delete (with confirmation)
        if self.ui_state.state == _AS.MAIN_MENU and self.ui_state.in_pinned_section:
            display_items = getattr(self.ui_state, "pinned_display_items", None)
            pinned_items = self.ui_state.reordered_pinned_items or self.manager.get_pinned_items()
            target_list = display_items or pinned_items
            idx = self.ui_state.pinned_selected_index
            if 0 <= idx < len(target_list):
                entry = target_list[idx]
                if display_items:
                    if entry.get("kind") != "pinned":
                        return  # Only delete top-level pinned entries
                    item = entry.get("item", {})
                else:
                    item = entry

                # Enhance item with display name for better delete confirmation
                enhanced_item = dict(item)  # Copy to avoid modifying original
                item_type = item.get('type')
                if item_type == 'project':
                    project_id = item.get('id')
                    project = self.manager.get_project(project_id)
                    if project:
                        enhanced_item['project_name'] = project.name

                self.ui_state.delete_context = {
                    'delete_type': 'pinned_item',
                    'previous_state': _AS.MAIN_MENU,
                    'previous_selected_index': self.ui_state.selected_index,
                    'previous_pinned_selected_index': idx,
                    'previous_in_pinned_section': True,
                    'delete_params': {
                        'item': enhanced_item,
                    }
                }
                self.ui_state.state = _AS.DELETE_CONFIRMATION
                self.ui_state.form_field_index = 1  # Default to "No" for safety
                logger.info("Showing delete confirmation for pinned item (%s)", item.get("type"))
            return

        # Calendar task delete (tasks only)
        if self.ui_state.state == _AS.CALENDAR and self.ui_state.calendar_navigation_focus == "tasks":
            tasks = self._get_calendar_tasks_for_active_tab()
            idx = self.ui_state.calendar_task_selected_index
            if 0 <= idx < len(tasks):
                item = tasks[idx]
                if isinstance(item, tuple):
                    if item[0] == "header":
                        return
                    if item[0] == "task":
                        entry = item[1]
                    else:
                        return
                else:
                    entry = item

                if getattr(entry, "kind", None) != "task":
                    return

                task = getattr(entry, "item", None)
                if task is None:
                    return

                target_task_id = None
                project_id = None
                list_name = None
                is_standalone = False

                for project in self.manager.projects:
                    flat = self._get_flat_tasks(project.tasks, True)
                    for task_id, task_obj, _ in flat:
                        if task_obj is task:
                            target_task_id = getattr(task_obj, "id", None)
                            project_id = project.id
                            is_standalone = False
                            break
                    if target_task_id is not None:
                        break

                if target_task_id is None:
                    list_tasks_map = getattr(self.ui_state, "list_tasks", None) or getattr(
                        self.manager,
                        "list_tasks",
                        {"Tasks": getattr(self.manager, "standalone_tasks", [])},
                    )
                    for candidate_list_name, sections in list_tasks_map.items():
                        if not sections or not isinstance(sections, list):
                            continue
                        first = sections[0]
                        looks_like_section = (
                            (isinstance(first, dict) and "tasks" in first)
                            or hasattr(first, "tasks")
                        )
                        if looks_like_section:
                            for section in sections:
                                section_tasks = section.tasks if hasattr(section, "tasks") else section.get("tasks", [])
                                flat = []
                                flatten_tasks(section_tasks, flat, collapsed_tasks=self.ui_state.collapsed_tasks)
                                for task_id, task_obj, _ in flat:
                                    if task_obj is task:
                                        target_task_id = getattr(task_obj, "id", None)
                                        list_name = candidate_list_name
                                        is_standalone = True
                                        break
                                if target_task_id is not None:
                                    break
                        else:
                            flat = []
                            flatten_tasks(sections, flat, collapsed_tasks=self.ui_state.collapsed_tasks)
                            for task_id, task_obj, _ in flat:
                                if task_obj is task:
                                    target_task_id = getattr(task_obj, "id", None)
                                    list_name = candidate_list_name
                                    is_standalone = True
                                    break

                        if target_task_id is not None:
                            break

                if target_task_id is None:
                    return

                self.ui_state.delete_context = {
                    'delete_type': 'calendar_task',
                    'previous_state': _AS.CALENDAR,
                    'previous_selected_index': 0,
                    'delete_params': {
                        'task_id': target_task_id,
                        'task': task,
                        'is_standalone': is_standalone,
                        'current_project_id': project_id,
                        'list_name': list_name,
                    }
                }
                self.ui_state.state = _AS.DELETE_CONFIRMATION
                self.ui_state.form_field_index = 1  # Default to "No" for safety
                logger.info("Showing delete confirmation for calendar task")
            return

        if self.ui_state.state == _AS.EDIT_TAB:
            from .enter_handlers import EnterHandlers  # avoid cycle at import-time
            # Reuse existing section delete handler
            try:
                # EnterHandlers instance isn't available here; instead mimic its logic by
                # calling handle_edit_list_section_delete via a small helper on self._enter_handlers
                if hasattr(self, '_enter_handlers'):
                    self._enter_handlers.handle_edit_list_section_delete()
                    return
            except Exception:
                pass

        # Inline select option deletion in custom field forms
        if self.ui_state.state in (_AS.ADD_CUSTOM_FIELD, _AS.EDIT_CUSTOM_FIELD):
            form_data = self.ui_state.form_data
            field_type = form_data.get('field_type', 'text')
            if field_type == 'single_select':
                options = form_data.get('select_options', []) or []
                core_count = 4  # label, field_type, visible, required
                if field_type == 'number':
                    core_count += 1
                    if form_data.get('number_format') == 'currency':
                        core_count += 1
                options_start = core_count
                idx = self.ui_state.form_field_index
                if options_start <= idx < options_start + len(options):
                    opt_idx = idx - options_start
                    if 0 <= opt_idx < len(options):
                        deleted = options.pop(opt_idx)
                        form_data['select_options'] = options
                        # Move cursor up to previous option or stay in place
                        if opt_idx > 0:
                            self.ui_state.form_field_index -= 1
                        # If we deleted the last option, clamp to last valid index
                        max_idx = options_start + max(0, len(options) - 1)
                        self.ui_state.form_field_index = max(options_start, min(self.ui_state.form_field_index, max_idx))
                    return

        # Delete custom field in CUSTOMIZE_FIELDS screen
        if self.ui_state.state == _AS.CUSTOMIZE_FIELDS:
            try:
                from ..custom_fields import get_builtin_fields
                default_visibility = getattr(self.manager, "default_field_visibility", {})
                builtin_fields = get_builtin_fields(default_visibility)
            except Exception:
                builtin_fields = []
            custom_fields = self.manager.custom_field_definitions
            selected_idx = self.ui_state.selected_index

            # Check if a custom field is selected (not a built-in field or action)
            # Custom fields start after: Progress (1) + builtin_fields
            custom_start = 1 + len(builtin_fields)
            custom_end = custom_start + len(custom_fields)
            if selected_idx >= custom_start and selected_idx < custom_end:
                field_idx = selected_idx - custom_start
                field = custom_fields[field_idx]

                # Show confirmation dialog
                self.ui_state.delete_context = {
                    'delete_type': 'custom_field',
                    'previous_state': _AS.CUSTOMIZE_FIELDS,
                    'previous_selected_index': selected_idx,
                    'delete_params': {
                        'field_idx': field_idx,
                        'field_key': field.key,
                        'field_label': field.label
                    }
                }
                self.ui_state.state = _AS.DELETE_CONFIRMATION
                self.ui_state.form_field_index = 1  # Default to "No" for safety
                logger.info("Showing delete confirmation for custom field '%s'", field.label)
                return

        # Delete bookmark or list in BOOKMARKS screen
        if self.ui_state.state == _AS.BOOKMARKS:
            if self._bookmark_handlers:
                self._bookmark_handlers.handle_bookmarks_delete()
                return

        # Delete bookmark in BOOKMARK_LIST screen
        if self.ui_state.state == _AS.BOOKMARK_LIST:
            if self._bookmark_handlers:
                self._bookmark_handlers.handle_bookmark_list_delete()
                return

        # Fallback: task delete
        self._task_handlers.handle_delete()

    def on_escape(self):
        """Handle escape key press."""
        def _reset_pinned_nav():
            self.ui_state.in_pinned_section = False
            self.ui_state.pinned_selected_index = 0

        def _reset_pinned_expanded_state():
            self.ui_state.expanded_pinned_lists = set()
            self.ui_state.expanded_pinned_sections = set()
            self.ui_state.expanded_pinned_list_sections = set()

        # Cell editing mode - cancel edit and stay in cell selection
        if self.ui_state.state == AppState.PROJECT_BROWSER and self.ui_state.cell_editing:
            self._cancel_cell_edit()
            return

        # Cell selection mode - exit and restore normal navigation
        if self.ui_state.state == AppState.PROJECT_BROWSER and self.ui_state.cell_selection_mode:
            self._exit_cell_selection_mode()
            return

        if self.ui_state.custom_field_date_edit_mode:
            self.ui_state.custom_field_date_edit_mode = False
            self.ui_state.custom_field_date_buffer = None
            return

        # Only use cancel_inline_edit for project details and task list
        # (calendar and main menu handle inline edit cancellation separately)
        if self.ui_state.inline_task_edit_mode and self.ui_state.state in (AppState.PROJECT_DETAILS, AppState.TASK_LIST):
            self._task_handlers.cancel_inline_edit()
            return

        if getattr(self.ui_state, 'inline_list_create_mode', False):
            # Cancel inline list creation
            self.ui_state.inline_list_create_mode = False
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
            self.ui_state.status_message = None
            self.ui_state.status_is_error = False
            return

        if getattr(self.ui_state, 'inline_list_edit_mode', False):
            # Cancel inline list editing
            self.ui_state.inline_list_edit_mode = False
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
            self.ui_state.status_message = None
            self.ui_state.status_is_error = False
            return

        # Main menu inline edit mode - just exit edit mode without deleting
        if self.ui_state.state == AppState.MAIN_MENU and self.ui_state.inline_task_edit_mode:
            self.ui_state.inline_task_edit_mode = False
            return

        if self.ui_state.inline_input_mode:
            # Check if we're in deadline edit mode first
            if self.ui_state.quick_add_deadline_edit_mode:
                # Exit deadline edit mode and clear the deadline
                self.ui_state.quick_add_deadline_edit_mode = False
                self.ui_state.quick_add_deadline = None
                self.ui_state.quick_add_deadline_component = 0
                return
            # Exit inline input mode
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
            self.ui_state.quick_add_priority = None
            self.ui_state.quick_add_field_index = 0
            self.ui_state.quick_add_deadline = None
            self.ui_state.quick_add_deadline_component = 0
            self.ui_state.quick_add_deadline_edit_mode = False
            self.ui_state.quick_add_list = "Tasks"
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.PROJECT_BROWSER:
            self.ui_state.state = AppState.MAIN_MENU
            self.ui_state.selected_index = 0
            self.ui_state.project_sort_key = None
            self.ui_state.project_sort_order = None
            _reset_pinned_expanded_state()
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.PROJECT_DETAILS:
            self.ui_state.state = AppState.PROJECT_BROWSER
            self.ui_state.selected_index = 0
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.TASK_LIST:
            # Done section should always reset to collapsed when leaving the task list.
            self.ui_state.collapsed_tasks.add("section_completed")
            _reset_pinned_expanded_state()
            self.ui_state.state = AppState.MAIN_MENU
            self.ui_state.selected_index = 0
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.STATISTICS:
            _reset_pinned_expanded_state()
            self.ui_state.state = AppState.MAIN_MENU
            self.ui_state.selected_index = 0
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.SEARCH:
            # Close search and return to previous state
            previous_state = self.ui_state.previous_state or AppState.MAIN_MENU
            self.ui_state.state = previous_state
            self.ui_state.search_query = ""
            self.ui_state.search_results = []
            self.ui_state.search_selected_index = 0
            self.ui_state.selected_index = 0
        elif self.ui_state.state == AppState.CALENDAR:
            # If in inline edit mode, cancel editing
            if self.ui_state.inline_task_edit_mode:
                # Remember if it was a new task (empty name) before canceling
                task = getattr(self.ui_state, "inline_edit_task", None)
                was_new_task = task and not getattr(task, "name", "")

                self._task_handlers.cancel_inline_edit()

                # Only reset cursor to "+" button if we canceled a new task
                # For existing tasks, cursor stays where it was
                if was_new_task:
                    tasks_for_day = self._get_calendar_tasks_for_selected_day()
                    self.ui_state.calendar_task_selected_index = len(tasks_for_day)
                return

            _reset_pinned_expanded_state()
            self.ui_state.state = AppState.MAIN_MENU
            self.ui_state.selected_index = 0
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.BOOKMARKS:
            _reset_pinned_expanded_state()
            self.ui_state.state = AppState.MAIN_MENU
            self.ui_state.selected_index = 0
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.SETTINGS:
            _reset_pinned_expanded_state()
            self.ui_state.state = AppState.MAIN_MENU
            self.ui_state.selected_index = 0
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.CUSTOMIZE_FIELDS:
            self.ui_state.state = AppState.PROJECT_BROWSER
            self.ui_state.selected_index = 0
            _reset_pinned_nav()
        elif self.ui_state.state in (AppState.ADD_CUSTOM_FIELD, AppState.EDIT_CUSTOM_FIELD):
            self.ui_state.form_data = {}
            self.ui_state.state = AppState.CUSTOMIZE_FIELDS
            self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.QUICK_STATS_SETTINGS:
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 1
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.MAIN_MENU_TABS_SETTINGS:
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 2
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.DEADLINE_SETTINGS:
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 3
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.TASK_METADATA_SETTINGS:
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 4
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.MESSAGE_DISPLAY_SETTINGS:
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 5
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.STATS_NONE_SETTINGS:
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 6
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.BOOKMARK_ACTION_SETTINGS:
            self.ui_state.state = AppState.SETTINGS
            self.ui_state.selected_index = 7
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.ADD_PROJECT:
            self.ui_state.form_data = {}
            self.ui_state.state = AppState.PROJECT_BROWSER
            self.ui_state.selected_index = 0
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.EDIT_PROJECT:
            self.ui_state.form_data = {}
            # Return to previous state if available, otherwise fallback to project details
            target_state = self.ui_state.previous_state or AppState.PROJECT_DETAILS
            self.ui_state.state = target_state
            self.ui_state.previous_state = None  # Clear it
            self.ui_state.selected_index = 0
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.CHANGE_STATUS:
            self.ui_state.state = AppState.PROJECT_DETAILS
            self.ui_state.selected_index = 0
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.BOOKMARK_LIST:
            self.ui_state.state = AppState.BOOKMARKS
            self.ui_state.current_list_index = None
            self.ui_state.selected_index = 0
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.ADD_BOOKMARK:
            self.ui_state.form_data = {}
            # Return to appropriate state based on context
            if self.ui_state.current_list_index is not None:
                self.ui_state.state = AppState.BOOKMARK_LIST
            else:
                self.ui_state.state = AppState.BOOKMARKS
            self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.EDIT_BOOKMARK:
            # Return to appropriate state based on context
            from_list = self.ui_state.form_data.get('from_list', False)
            self.ui_state.form_data = {}
            if from_list:
                self.ui_state.state = AppState.BOOKMARK_LIST
            else:
                self.ui_state.state = AppState.BOOKMARKS
            self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.EDIT_TAB:
            self.ui_state.form_data = {}
            self.ui_state.state = AppState.TASK_LIST
            self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            _reset_pinned_nav()
        elif self.ui_state.state == AppState.DELETE_CONFIRMATION:
            # Cancel delete and return to previous state
            self._handle_delete_cancel()

    def _get_max_index(self) -> int:
        """Get maximum index for current state."""
        if self.ui_state.state == AppState.MAIN_MENU:
            menu_items = build_main_menu_items(self.ui_state.main_menu_tabs_selection)
            total_entries = len(menu_items) + 2  # Settings + Exit
            if is_quick_add_enabled(self.ui_state.main_menu_tabs_selection):
                total_entries += 1
            return max(0, total_entries - 1)
        elif self.ui_state.state == AppState.PROJECT_BROWSER:
            filtered = filter_projects_by_tab(self.manager.projects, self.ui_state.active_tab)
            # Project browser menu structure:
            #   0..N-1: projects
            #   N:     Add Project
            #   N+1:   Customize Fields
            #   N+2:   Back
            # => max index = N + 2
            return len(filtered) + 2
        elif self.ui_state.state == AppState.PROJECT_DETAILS:
            project = self.manager.get_project(self.ui_state.current_project_id)
            if project:
                flat_tasks = self._get_flat_tasks(project.tasks, True)
                # Last index mapping:
                # all tasks (0..T-1) + add (T) + actions (3 items) => last = T + 3
                return len(flat_tasks) + 3
            return 0
        elif self.ui_state.state == AppState.TASK_LIST:
            # Use the active list's tasks
            task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
            active_tab = getattr(self.ui_state, "active_tab", 0)
            active_list_name = task_lists[active_tab] if 0 <= active_tab < len(task_lists) else "Tasks"
            list_tasks_map = getattr(self.ui_state, "list_tasks", {"Tasks": self.manager.standalone_tasks})
            sections_for_list = list_tasks_map.get(active_list_name, [])
            
            list_metadata = self.manager.list_metadata
            done_mode = list_metadata.get(active_list_name, {}).get("show_done_section", "section")
            # Handle legacy boolean values
            if isinstance(done_mode, bool):
                done_mode = "section" if done_mode else "inline"

            # Handle both old format (list of tasks) and new format (list of sections)
            all_pending_tasks = []
            all_completed_tasks = []
            section_data = []  # Track sections for header counting

            if sections_for_list:
                first = sections_for_list[0]
                looks_like_section = (
                    (isinstance(first, dict) and 'tasks' in first)
                    or hasattr(first, 'tasks')
                )
            else:
                looks_like_section = False

            if sections_for_list and not looks_like_section:
                # Old format: direct list of tasks
                all_flat_tasks = self._get_flat_tasks(sections_for_list, False)
                if done_mode in ["section", "bottom"]:
                    pending = [t for t in all_flat_tasks if t[1].completed is None]
                    completed = [t for t in all_flat_tasks if t[1].completed is not None]
                    section_data.append(("", pending, completed))
                    all_pending_tasks.extend(pending)
                    all_completed_tasks.extend(completed)
                else:  # "inline"
                    section_data.append(("", all_flat_tasks, []))
                    all_pending_tasks.extend(all_flat_tasks)
            else:
                # New format: list of sections
                for section in sections_for_list:
                    section_name = section.name if hasattr(section, 'name') else section.get('name', '')
                    section_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])

                    flat_for_section = self._get_flat_tasks(section_tasks, False)

                    if done_mode in ["section", "bottom"]:
                        pending = [t for t in flat_for_section if t[1].completed is None]
                        completed = [t for t in flat_for_section if t[1].completed is not None]
                    else:  # "inline"
                        pending = flat_for_section
                        completed = []

                    section_id = section.get("id") if isinstance(section, dict) else getattr(section, "id", None)
                    section_data.append((section_id, section_name, pending, completed))
                    all_pending_tasks.extend(pending)
                    all_completed_tasks.extend(completed)

            pending_flat = all_pending_tasks
            completed_flat = all_completed_tasks
            is_completed_collapsed = "section_completed" in self.ui_state.collapsed_tasks
            # Check if we can edit the current tab (not the default "Tasks" tab)
            can_edit_tab = active_tab > 0 and active_tab < len(task_lists)

            # Check if section headers are shown (matching task_list.py render logic)
            show_section_headers = len(section_data) > 1 or (len(section_data) == 1 and section_data[0][1])

            # Calculate max index based on actual rendered structure
            if show_section_headers:
                # For each section: 1 (header) + num_pending_in_section + 1 (+ button)
                current_index = 0
                for idx, (section_id, _, pending, completed) in enumerate(section_data):
                    section_collapse_key = f"section:{section_id}"
                    is_section_collapsed = section_collapse_key in self.ui_state.collapsed_tasks
                    current_index += 1  # Section header
                    if not is_section_collapsed:
                        current_index += len(pending)  # Tasks in section
                        current_index += 1  # + button for section
                # Blank line is non-selectable (does not advance index)

                # Completed tasks
                if done_mode == "section":
                    current_index += 1  # Completed header
                    if not is_completed_collapsed:
                        current_index += len(completed_flat)  # Completed tasks
                elif done_mode == "bottom":
                    current_index += len(completed_flat)  # Completed tasks (no header)

                # New list + Edit List (if applicable) + Back
                current_index += 1  # New list
                if can_edit_tab:
                    current_index += 1  # Edit list
                current_index += 1  # Back
                return current_index - 1  # Max index is count - 1
            else:
                # No section headers
                current_index = len(pending_flat) # Pending tasks (or all tasks if done section disabled)
                current_index += 1 # Add button

                if done_mode == "section":
                    current_index += 1 # Completed header
                    if not is_completed_collapsed:
                        current_index += len(completed_flat)
                elif done_mode == "bottom":
                    current_index += len(completed_flat)  # Completed tasks (no header)

                current_index += 1 # New list
                if can_edit_tab:
                    current_index += 1 # Edit list
                current_index += 1 # Back
                
                return current_index - 1
        elif self.ui_state.state == AppState.CALENDAR:
            return 0
        elif self.ui_state.state == AppState.CHANGE_STATUS:
            return len(STATUS_DISPLAY_ORDER)  # Status options + Cancel
        elif self.ui_state.state == AppState.SETTINGS:
            # Settings menu exposes 11 visible entries (0-10) plus Back (11).
            return 11
        elif self.ui_state.state == AppState.QUICK_STATS_SETTINGS:
            return len(QUICK_STATS_ORDER)  # Metrics + Back
        elif self.ui_state.state == AppState.MAIN_MENU_TABS_SETTINGS:
            return len(MAIN_MENU_TABS_ORDER)  # Tabs + Back
        elif self.ui_state.state == AppState.DEADLINE_SETTINGS:
            return 2  # Two display modes (relative, date) + Back
        elif self.ui_state.state == AppState.TASK_METADATA_SETTINGS:
            return 2  # Two display positions (below, next_to) + Back
        elif self.ui_state.state == AppState.MESSAGE_DISPLAY_SETTINGS:
            return 2  # Two options (all, errors_only) + Back
        elif self.ui_state.state == AppState.NOTES_DISPLAY_SETTINGS:
            return 2  # Two options (dynamic, always) + Back
        elif self.ui_state.state == AppState.STATS_NONE_SETTINGS:
            return 2  # Two options (show, hide) + Back
        elif self.ui_state.state == AppState.BOOKMARK_ACTION_SETTINGS:
            return 2  # Two options (copy, open) + Back
        elif self.ui_state.state == AppState.BOOKMARKS:
            return len(self.manager.bookmarks) + 2  # Bookmarks + Add Bookmark + Add List + Back
        elif self.ui_state.state == AppState.BOOKMARK_LIST:
            if self.ui_state.current_list_index is not None and self.ui_state.current_list_index < len(self.manager.bookmarks):
                from pm import BookmarkList
                bookmark_list = self.manager.bookmarks[self.ui_state.current_list_index]
                if isinstance(bookmark_list, BookmarkList):
                    return len(bookmark_list.items) + 3  # Items + Add + Rename + Delete + Back
            return 3  # Add + Rename + Delete + Back if list not found
        elif self.ui_state.state == AppState.CUSTOMIZE_FIELDS:
            # Progress (1) + built-in fields + custom fields + 2 actions (Add, Back)
            try:
                from ..custom_fields import get_builtin_fields
                default_visibility = getattr(self.manager, "default_field_visibility", {})
                builtin_fields = get_builtin_fields(default_visibility)
            except Exception:
                builtin_fields = []
            custom_count = len(self.manager.custom_field_definitions)
            # Total: 1 (Progress) + builtin_fields + custom_fields + 2 (actions)
            # Max index (0-based): total - 1
            return 1 + len(builtin_fields) + custom_count + 2 - 1
        return 0

    def _get_max_form_index(self) -> int:
        """Get maximum form field index."""
        if self.ui_state.state == AppState.ADD_PROJECT:
            # ADD_PROJECT now uses same layout as EDIT_PROJECT but with 2 actions (Create + Cancel)
            all_fields = get_all_fields(self.manager.default_field_visibility, self.manager.custom_field_definitions)
            field_keys = get_edit_project_field_keys(all_fields)
            # Max index = fields + Create + Cancel
            # Actions are at indices: len(field_keys), len(field_keys)+1
            return len(field_keys) + 1
        elif self.ui_state.state == AppState.EDIT_PROJECT:
            all_fields = get_all_fields(self.manager.default_field_visibility, self.manager.custom_field_definitions)
            field_keys = get_edit_project_field_keys(all_fields)
            # Max index = fields + Save + Delete + Cancel
            # Actions are at indices: len(field_keys), len(field_keys)+1, len(field_keys)+2
            return len(field_keys) + 2
        elif self.ui_state.state == AppState.ADD_BOOKMARK:
            return 3  # 2 fields + Submit + Cancel
        elif self.ui_state.state == AppState.EDIT_BOOKMARK:
            return 3  # 2 fields + Submit + Cancel
        elif self.ui_state.state == AppState.EDIT_TAB:
            # Check if this is a list edit (with sections) or tab edit (old style)
            if self.ui_state.editing_list_name is not None or (self.ui_state.form_data and 'sections' in self.ui_state.form_data):
                # list edit mode: name + color + Done Section + mode + sections (conditional) + actions
                mode = self.ui_state.form_data.get('mode', 'normal')
                use_sections = mode == 'sections'
                sections = self.ui_state.form_data.get('sections', [])
                is_creating = self.ui_state.editing_list_name is None
                # Field 0 = list name
                # Field 1 = color
                # Field 2 = Done Section
                # Field 3 = mode
                # Fields 4 to N+3 = sections (only if mode == 'sections')
                # Field N+4 or 4 = Add Section (only if mode == 'sections')
                # Field N+5 or 4 = Save
                # Field N+6 or 5 = Pin (if editing, not creating)
                # Field N+7 or 6 = Delete (if editing, not creating)
                # Field N+8 or N+6 or 5 or 7 = Cancel
                if use_sections:
                    add_section_idx = 4 + len(sections)
                    save_idx = add_section_idx + 1
                else:
                    save_idx = 4

                if is_creating:
                    # No pin or delete button
                    return save_idx + 1  # Save + Cancel
                else:
                    # With pin and delete button
                    return save_idx + 3  # Save + Pin + Delete + Cancel
            else:
                # Tab edit mode (old style): 1 field + Save + Delete + Cancel
                return 3
        elif self.ui_state.state == AppState.DELETE_CONFIRMATION:
            return 1  # 2 options: Yes (0) and No (1)
        elif self.ui_state.state == AppState.ADD_CUSTOM_FIELD:
            # Field indices:
            # 0-2: label, visible, required (core_fields)
            # 3: field_type (Type)
            # 4+: format fields (number) or options (single_select)
            # last-1, last: Save, Cancel
            form_data = self.ui_state.form_data
            field_type = form_data.get('field_type', 'text')
            next_idx = 4  # After field_type (index 3)
            
            if field_type == 'number':
                next_idx += 1  # number_format at index 4
                if form_data.get('number_format') == 'currency':
                    next_idx += 1  # currency_symbol at index 5
                # indices: 0-3 (core+type) + format fields + Save (next_idx) + Cancel (next_idx+1)
                return next_idx + 1
            if field_type == 'single_select':
                options = form_data.get('select_options', []) or []
                # indices: 0-3 (core+type) + options + '+ Add' + Save + Cancel
                options_idx = next_idx
                add_idx = options_idx + len(options)
                save_idx = add_idx + 1
                return save_idx + 1
            # text/date: indices 0-3 (core+type) + Save + Cancel
            return next_idx + 1
        elif self.ui_state.state == AppState.EDIT_CUSTOM_FIELD:
            # Same as ADD_CUSTOM_FIELD but with 3 actions (Save, Delete, Cancel)
            form_data = self.ui_state.form_data
            field_type = form_data.get('field_type', 'text')
            next_idx = 4  # After field_type (index 3)
            
            if field_type == 'number':
                next_idx += 1  # number_format at index 4
                if form_data.get('number_format') == 'currency':
                    next_idx += 1  # currency_symbol at index 5
                # core(3)+type(1)+formats(1or2) = 5 or 6 items. 
                # Actions follow. Save, Delete, Cancel.
                return next_idx + 2
            if field_type == 'single_select':
                options = form_data.get('select_options', []) or []
                options_idx = next_idx
                add_idx = options_idx + len(options)
                save_idx = add_idx + 1
                return save_idx + 2
            # text/date
            return next_idx + 2
        return 0

    def _get_action_range_for_state(self):
        """Return (start_index, action_count, use_form_field) for footer actions."""
        state = self.ui_state.state

        if state == AppState.PROJECT_BROWSER:
            filtered = self._get_filtered_projects_sorted()
            return len(filtered), 3, False
        if state == AppState.PROJECT_DETAILS:
            project = self.manager.get_project(self.ui_state.current_project_id)
            if not project:
                return None
            flat_tasks = self._get_flat_tasks(project.tasks, True)
            return len(flat_tasks) + 1, 3, False
        if state == AppState.TASK_LIST:
            layout = self._enter_handlers.build_task_list_layout()
            if not layout:
                return None
            action_count = 2 + (1 if layout.get("can_edit_tab") else 0)
            return layout.get("new_list_index"), action_count, False
        if state == AppState.CUSTOMIZE_FIELDS:
            try:
                from ..custom_fields import get_builtin_fields
                default_visibility = getattr(self.manager, "default_field_visibility", {})
                builtin_fields = get_builtin_fields(default_visibility)
            except Exception:
                builtin_fields = []
            custom_fields = getattr(self.manager, "custom_field_definitions", [])
            # Progress row + builtin fields + custom fields precede the footer actions
            start_index = 1 + len(builtin_fields) + len(custom_fields)
            return start_index, 2, False
        if state == AppState.BOOKMARKS:
            return len(self.manager.bookmarks), 3, False
        if state == AppState.BOOKMARK_LIST:
            current_idx = self.ui_state.current_list_index
            if current_idx is None or current_idx >= len(self.manager.bookmarks):
                return None
            from pm import BookmarkList
            bookmark_list = self.manager.bookmarks[current_idx]
            if not isinstance(bookmark_list, BookmarkList):
                return None
            return len(bookmark_list.items), 4, False

        # Form states (use form_field_index)
        form_action_counts = {
            AppState.ADD_PROJECT: 2,
            AppState.EDIT_PROJECT: 3,
            AppState.ADD_BOOKMARK: 2,
            AppState.EDIT_BOOKMARK: 2,
            AppState.ADD_CUSTOM_FIELD: 2,
            AppState.EDIT_CUSTOM_FIELD: 3,
        }

        if state in form_action_counts:
            action_count = form_action_counts[state]
            max_idx = self._get_max_form_index()
            if max_idx < action_count - 1:
                return None
            return max_idx - action_count + 1, action_count, True

        if state == AppState.EDIT_TAB:
            form_data = self.ui_state.form_data or {}
            is_list_mode = self.ui_state.editing_list_name is not None or ("sections" in form_data)
            is_creating = self.ui_state.editing_list_name is None
            if is_list_mode:
                action_count = 2 if is_creating else 4
            else:
                action_count = 3
            max_idx = self._get_max_form_index()
            if max_idx < action_count - 1:
                return None
            return max_idx - action_count + 1, action_count, True

        if state == AppState.DELETE_CONFIRMATION:
            action_count = 2
            max_idx = self._get_max_form_index()
            if max_idx < action_count - 1:
                return None
            return max_idx - action_count + 1, action_count, True

        return None

    def on_action_shortcut(self, number: int) -> None:
        """Jump to a footer action by number and trigger it."""
        if number < 1:
            return

        if getattr(self.ui_state, "show_help", False):
            return

        if getattr(self.ui_state, "inline_input_mode", False) or getattr(self.ui_state, "inline_task_edit_mode", False):
            return

        if self.ui_state.state == AppState.PROJECT_BROWSER and getattr(self.ui_state, "cell_editing", False):
            return

        action_meta = self._get_action_range_for_state()
        if not action_meta:
            return

        start_index, action_count, use_form_field = action_meta
        if start_index is None or action_count <= 0:
            return

        target_index = start_index + number - 1
        if target_index > start_index + action_count - 1:
            return

        if use_form_field:
            self.ui_state.form_field_index = target_index
        else:
            self.ui_state.selected_index = target_index
            if (
                self.ui_state.state == AppState.PROJECT_BROWSER
                and self.ui_state.cell_selection_mode
                and not self.ui_state.cell_editing
            ):
                self._exit_cell_selection_mode()

        self._enter_handlers.handle_enter()

    def _handle_delete_cancel(self):
        """Cancel delete confirmation and return to previous state."""
        if self.ui_state.delete_context:
            previous_state = self.ui_state.delete_context.get('previous_state', AppState.MAIN_MENU)
            previous_selected_index = self.ui_state.delete_context.get('previous_selected_index', 0)
            previous_form_field_index = self.ui_state.delete_context.get('previous_form_field_index')

            # Restore previous state
            self.ui_state.state = previous_state
            self.ui_state.selected_index = previous_selected_index

            # Restore form_field_index if it was stored (for form states)
            if previous_form_field_index is not None:
                self.ui_state.form_field_index = previous_form_field_index
            else:
                self.ui_state.form_field_index = 0

            # Clear delete context
            self.ui_state.delete_context = None
            logger.info("Cancelled delete confirmation, returned to %s", previous_state)

    def _get_filtered_projects_sorted(self):
        """Return filtered projects for the active tab, applying header sort if set."""
        all_fields = get_all_fields(self.manager.default_field_visibility, self.manager.custom_field_definitions)
        filtered = filter_projects_by_tab(self.manager.projects, self.ui_state.active_tab)
        return sort_projects_for_display(
            filtered,
            getattr(self.ui_state, "project_sort_key", None),
            all_fields,
            getattr(self.ui_state, "project_sort_order", None),
        )

    def _cycle_deadline_component(self, direction: int):
        """Cycle the current deadline component value.

        Args:
            direction: 1 to increment, -1 to decrement
        """
        if not self.ui_state.quick_add_deadline:
            return

        # Parse current deadline
        parts = self.ui_state.quick_add_deadline.split('-')
        if len(parts) != 3:
            return

        try:
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
        except ValueError:
            return

        # Cycle the selected component
        if self.ui_state.quick_add_deadline_component == 0:  # Year
            year += direction
            # Clamp year to reasonable range
            year = max(2000, min(2100, year))
        elif self.ui_state.quick_add_deadline_component == 1:  # Month
            month += direction
            # Wrap month around 1-12
            if month > 12:
                month = 1
            elif month < 1:
                month = 12
        else:  # Day
            # Get days in current month
            import calendar
            max_day = calendar.monthrange(year, month)[1]
            day += direction
            # Wrap day around 1-max_day
            if day > max_day:
                day = 1
            elif day < 1:
                day = max_day

        # Update deadline
        self.ui_state.quick_add_deadline = f"{year:04d}-{month:02d}-{day:02d}"
        logger.debug("Cycled deadline component to: %s", self.ui_state.quick_add_deadline)

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

    def _get_calendar_tasks_for_active_tab(self):
        """Return tasks for the currently active calendar tab."""
        tab = self.ui_state.calendar_tasks_tab
        if tab == 0:
            # Selected Day
            return self._get_calendar_tasks_for_selected_day()
        elif tab == 1:
            # Overdue - return just the entries (not tuples)
            from ..utils.calendar import collect_overdue_entries
            from datetime import datetime
            list_tasks_map = getattr(self.ui_state, "list_tasks", None) or getattr(
                self.manager,
                "list_tasks",
                {"Tasks": getattr(self.manager, "standalone_tasks", [])},
            )
            overdue_data = collect_overdue_entries(
                self.manager,
                list_tasks_map,
                datetime.now().date(),
                max_items=20
            )
            return [entry for entry, days_overdue in overdue_data]
        elif tab == 2:
            # Upcoming - return flat list of items (headers + tasks)
            return self._get_upcoming_flat_items()
        return []
    
    def _get_upcoming_flat_items(self):
        """Build flat list for navigation in upcoming tab (headers + tasks)."""
        from ..utils.calendar import collect_upcoming_entries, CalendarEntry
        from datetime import datetime
        
        list_tasks_map = getattr(self.ui_state, "list_tasks", None) or getattr(
            self.manager,
            "list_tasks",
            {"Tasks": getattr(self.manager, "standalone_tasks", [])},
        )
        upcoming_data = collect_upcoming_entries(
            self.manager,
            list_tasks_map,
            datetime.now().date()
        )
        
        collapsed_sections = self.ui_state.calendar_upcoming_collapsed
        sections = [
            ("today", "Today"),
            ("next_week", "Next Week"),
            ("next_month", "Next Month"),
        ]
        
        flat_items = []
        for section_key, section_label in sections:
            entries = upcoming_data.get(section_key, [])
            
            # Always add section header (even if empty)
            flat_items.append(("header", section_key, section_label, len(entries)))
            
            # Add tasks if section is not collapsed and has entries
            if section_key not in collapsed_sections and entries:
                for entry in entries:
                    flat_items.append(("task", entry))
        
        return flat_items

    def _has_add_button_in_calendar(self) -> bool:
        """Return True if current calendar tab has a '+' button."""
        tab = self.ui_state.calendar_tasks_tab
        return tab == 0  # Only Selected Day tab has '+' button

    def _move_calendar_task(self, delta: int):
        """Move selected task in calendar to a different day."""
        tasks_for_day = self._get_calendar_tasks_for_selected_day()
        idx = self.ui_state.calendar_task_selected_index
        
        # Check if we're on a task (not the '+' button)
        if 0 <= idx < len(tasks_for_day):
            entry = tasks_for_day[idx]
            if entry.kind != "task":
                self._context.show_status("Only tasks can be moved here")
                return

            task = entry.item
            project_name = entry.project_name
            current_deadline = getattr(task, "deadline", None)
            date_value = parse_deadline_date(current_deadline)
            if not date_value:
                return

            new_date = date_value + timedelta(days=delta)
            task.deadline = new_date.strftime("%Y-%m-%d")

            # Save changes
            if project_name:
                self.manager.save()
            else:
                self.manager.mark_list_tasks_modified()
                self.manager.save()

            # Move calendar selection with the task
            self.ui_state.calendar_year = new_date.year
            self.ui_state.calendar_month = new_date.month
            self.ui_state.calendar_selected_day = new_date.day

            # Find new index of the task in the target day's list to maintain focus
            new_tasks = self._get_calendar_tasks_for_selected_day()
            for i, new_entry in enumerate(new_tasks):
                if new_entry.kind == "task" and new_entry.item is task:
                    self.ui_state.calendar_task_selected_index = i
                    break
            
            self._context.show_status(f"Moved task to {task.deadline}")

    @staticmethod
    def _calendar_is_last_week_day(year: int, month: int, day: int) -> bool:
        """Return True if the day falls on the last week row of the month."""
        import calendar

        weeks = calendar.Calendar(firstweekday=6).monthdayscalendar(year, month)
        for idx, week in enumerate(weeks):
            if day in week:
                return idx == len(weeks) - 1
        return False

    def _calendar_move_day(self, delta: int, allow_month_wrap: bool = True) -> None:
        """Move calendar selection by delta days.

        Args:
            delta: Number of days to move (negative for backward)
            allow_month_wrap: If False, prevent moving to different month
        """
        from datetime import datetime, timedelta
        from calendar import monthrange

        year = self.ui_state.calendar_year
        month = self.ui_state.calendar_month
        selected_day = self.ui_state.calendar_selected_day or 1

        try:
            current_date = datetime(year, month, selected_day)
        except ValueError:
            _, max_day = monthrange(year, month)
            selected_day = max(1, min(selected_day, max_day))
            current_date = datetime(year, month, selected_day)

        new_date = current_date + timedelta(days=delta)

        # If month wrapping not allowed and we'd change months, clamp to month boundary
        if not allow_month_wrap and new_date.month != month:
            if delta > 0:
                # Moving forward - clamp to last day of current month
                _, max_day = monthrange(year, month)
                self.ui_state.calendar_selected_day = max_day
            else:
                # Moving backward - clamp to first day of current month
                self.ui_state.calendar_selected_day = 1
            return

        self.ui_state.calendar_year = new_date.year
        self.ui_state.calendar_month = new_date.month
        self.ui_state.calendar_selected_day = new_date.day

    def _calendar_change_month(self, delta: int) -> None:
        """Change calendar month by delta months."""
        from calendar import monthrange

        year = self.ui_state.calendar_year
        month = self.ui_state.calendar_month + delta
        selected_day = self.ui_state.calendar_selected_day or 1

        while month > 12:
            month -= 12
            year += 1
        while month < 1:
            month += 12
            year -= 1

        _, max_day = monthrange(year, month)
        selected_day = max(1, min(selected_day, max_day))

        self.ui_state.calendar_year = year
        self.ui_state.calendar_month = month
        self.ui_state.calendar_selected_day = selected_day

    def on_ctrl_left(self):
        """Handle Ctrl+Left key."""
        if self.ui_state.state == AppState.CALENDAR:
            focus = self.ui_state.calendar_navigation_focus
            if focus in ["day", "prev", "next"]:
                self._calendar_change_month(-1)
                self.ui_state.calendar_task_selected_index = 0
            elif focus == "tasks":
                # Only allow moving tasks in Selected Day tab
                if self.ui_state.calendar_tasks_tab == 0:
                    self._move_calendar_task(-1)

    def on_ctrl_right(self):
        """Handle Ctrl+Right key."""
        if self.ui_state.state == AppState.CALENDAR:
            focus = self.ui_state.calendar_navigation_focus
            if focus in ["day", "prev", "next"]:
                self._calendar_change_month(1)
                self.ui_state.calendar_task_selected_index = 0
            elif focus == "tasks":
                # Only allow moving tasks in Selected Day tab
                if self.ui_state.calendar_tasks_tab == 0:
                    self._move_calendar_task(1)

    def _ensure_inline_edit_deadline(self):
        """Ensure inline edit deadline has an initialized value."""
        if not self.ui_state.inline_edit_deadline:
            from datetime import datetime

            today = datetime.now()
            self.ui_state.inline_edit_deadline = f"{today.year:04d}-{today.month:02d}-{today.day:02d}"

    def _adjust_inline_edit_deadline(self, direction: int):
        """Increment/decrement a deadline component for inline task edit."""
        # If deadline was None, just initialize it to today without adjusting
        was_none = not self.ui_state.inline_edit_deadline
        self._ensure_inline_edit_deadline()
        if was_none:
            # Just initialized the deadline, don't adjust it further
            return

        parts = (self.ui_state.inline_edit_deadline or "0000-00-00").split('-')
        if len(parts) != 3:
            return
        try:
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
        except ValueError:
            return

        comp = self.ui_state.inline_edit_deadline_component
        if comp == 0:
            year = max(2000, min(2100, year + direction))
        elif comp == 1:
            month += direction
            if month > 12:
                month = 1
            elif month < 1:
                month = 12
            # Clamp day to the number of days in the new month
            import calendar

            max_day = calendar.monthrange(year, month)[1]
            day = min(day, max_day)
        else:
            import calendar

            max_day = calendar.monthrange(year, month)[1]
            day += direction
            if day > max_day:
                day = 1
            elif day < 1:
                day = max_day

        self.ui_state.inline_edit_deadline = f"{year:04d}-{month:02d}-{day:02d}"

    def _cycle_inline_edit_priority(self, direction: int):
        """Cycle inline priority between none/!, !!, !!!."""
        priorities = ["none", "!", "!!", "!!!"]
        current = self.ui_state.inline_edit_priority
        idx = priorities.index(current) if current in priorities else 0
        idx = (idx + direction) % len(priorities)
        self.ui_state.inline_edit_priority = priorities[idx]

    def _clear_current_project_form_field(self):
        """Clear the currently focused project form field, setting it to None/empty.

        This is used when Backspace is pressed while *not* in inline input mode.
        """
        # Only applies to project add/edit forms for now
        if self.ui_state.state not in [AppState.ADD_PROJECT, AppState.EDIT_PROJECT]:
            return

        all_fields = get_all_fields(self.manager.default_field_visibility, self.manager.custom_field_definitions)

        if self.ui_state.state == AppState.ADD_PROJECT:
            # For add project: name, status, then custom fields in order
            field_keys = ["name", "status"] + [field.key for field in get_visible_fields_sorted(all_fields)]
        else:  # EDIT_PROJECT
            field_keys = get_edit_project_field_keys(all_fields)

        idx = self.ui_state.form_field_index
        if not (0 <= idx < len(field_keys)):
            return

        field_name = field_keys[idx]

        # Name field: clear to empty string instead of None for better UX/validation
        if field_name == "name":
            self.ui_state.form_data["name"] = ""
            return

        # All other fields are set to explicit None (including custom date/select/number/text)
        self.ui_state.form_data[field_name] = None

    def _save_current_inline_input(self):
        """Save the current inline input buffer to form data if valid."""
        if not self.ui_state.inline_input_mode:
            return

        from ..utils import sanitize_input

        # Determine field key based on state and index
        field_key = None
        if self.ui_state.state in [AppState.ADD_BOOKMARK, AppState.EDIT_BOOKMARK]:
            if self.ui_state.form_field_index == 0:
                field_key = "title"
            elif self.ui_state.form_field_index == 1:
                field_key = "url"
        elif self.ui_state.state in [AppState.ADD_PROJECT, AppState.EDIT_PROJECT]:
            all_fields = get_all_fields(self.manager.default_field_visibility, self.manager.custom_field_definitions)
            if self.ui_state.state == AppState.ADD_PROJECT:
                field_keys = ["name", "status"] + [field.key for field in get_visible_fields_sorted(all_fields)]
            else:
                field_keys = get_edit_project_field_keys(all_fields)
            
            if 0 <= self.ui_state.form_field_index < len(field_keys):
                field_key = field_keys[self.ui_state.form_field_index]
        
        # Save if we found a key
        if field_key:
            sanitized = sanitize_input(self.ui_state.text_input_buffer)
            self.ui_state.form_data[field_key] = sanitized
            logger.debug("Saved inline input for '%s': %s", field_key, sanitized)

    def _insert_inline_edit_char(self, char: str):
        """Insert character into inline edit name buffer respecting cursor position."""
        idx = self.ui_state.inline_edit_name_cursor
        self.ui_state.inline_edit_name = (
            self.ui_state.inline_edit_name[:idx] + char + self.ui_state.inline_edit_name[idx:]
        )
        self.ui_state.inline_edit_name_cursor += len(char)

    def _insert_inline_notes_char(self, char: str):
        """Insert character into inline edit notes buffer respecting cursor position."""
        notes = self.ui_state.inline_edit_notes or ""
        idx = self.ui_state.inline_edit_notes_cursor
        self.ui_state.inline_edit_notes = notes[:idx] + char + notes[idx:]
        self.ui_state.inline_edit_notes_cursor += len(char)

    def _ensure_custom_field_date_buffer(self):
        """Ensure custom field date buffer has an initialized value."""
        if not self.ui_state.custom_field_date_buffer:
            from datetime import datetime
            today = datetime.now()
            self.ui_state.custom_field_date_buffer = f"{today.year:04d}-{today.month:02d}-{today.day:02d}"

    def _adjust_custom_field_date(self, direction: int):
        """Increment/decrement a custom field date component."""
        self._ensure_custom_field_date_buffer()

        parts = self.ui_state.custom_field_date_buffer.split('-')
        if len(parts) != 3:
            return

        try:
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
        except ValueError:
            return

        comp = self.ui_state.custom_field_date_component
        if comp == 0:
            year = max(2000, min(2100, year + direction))
        elif comp == 1:
            month += direction
            if month > 12:
                month = 1
            elif month < 1:
                month = 12
            # Clamp day to the number of days in the new month
            import calendar
            max_day = calendar.monthrange(year, month)[1]
            day = min(day, max_day)
        else:
            import calendar
            max_day = calendar.monthrange(year, month)[1]
            day += direction
            if day > max_day:
                day = 1
            elif day < 1:
                day = max_day

        self.ui_state.custom_field_date_buffer = f"{year:04d}-{month:02d}-{day:02d}"

    def on_exit(self):
        """Handle exit cleanup.

        This should persist any pending data changes and then exit the
        application. Tests expect ``force_save`` to be invoked once when
        available.
        """
        try:
            save = getattr(self.manager, "force_save", None)
            if callable(save):
                save()
        except Exception:
            # Log but still attempt to exit the application so the UI
            # doesn't get stuck on an unresponsive exit.
            logger.exception("Error during force_save on exit")

        # Always attempt to exit the application (may be mocked in tests)
        try:
            self._exit_application()
        except Exception:
            logger.exception("Error while exiting application")

    def on_today(self):
        """Reset calendar to current date."""
        from datetime import datetime
        now = datetime.now()
        self.ui_state.calendar_year = now.year
        self.ui_state.calendar_month = now.month
        self.ui_state.calendar_selected_day = now.day
        self.ui_state.calendar_navigation_focus = "day"
        self.ui_state.calendar_task_selected_index = 0
        logger.info("Calendar jumped to today: %04d-%02d-%02d", now.year, now.month, now.day)

    def start_inline_task_add_for_calendar(self):
        """Start adding a task from the calendar with selected date as deadline."""
        from pm import Task
        
        year = self.ui_state.calendar_year
        month = self.ui_state.calendar_month
        day = self.ui_state.calendar_selected_day
        if not (year and month and day):
            return

        deadline = f"{year:04d}-{month:02d}-{day:02d}"
        new_task = Task(name="", deadline=deadline)
        
        # Add to default 'Tasks' list
        list_tasks_map = getattr(self.manager, "list_tasks", {})
        if "Tasks" not in list_tasks_map:
            from pm import Section
            list_tasks_map["Tasks"] = [Section(name="", tasks=[])]

        first_section = list_tasks_map["Tasks"][0]
        if hasattr(first_section, "tasks"):
            first_section.tasks.append(new_task)
        else:
            first_section.setdefault("tasks", []).append(new_task)
            
        self.manager.mark_list_tasks_modified()
        # Do not save yet - wait for inline edit commit
        
        # Determine the index for selection
        tasks_for_day = self._get_calendar_tasks_for_selected_day()
        # The new task is already in tasks_for_day.
        # We want to stay on the '+' button position, which is now len(tasks_for_day) - 1 + 1 = len(tasks_for_day).
        # Actually, the '+' button is always at len(tasks_for_day).
        self.ui_state.calendar_task_selected_index = len(tasks_for_day)
        
        self.ui_state.inline_task_edit_mode = True
        self.ui_state.inline_edit_task_id = None
        self.ui_state.inline_edit_task = new_task
        self.ui_state.inline_edit_origin = "calendar"
        self.ui_state.inline_edit_list_name = "Tasks"
        self.ui_state.inline_edit_field_index = 0
        self.ui_state.inline_edit_name = ""
        self.ui_state.inline_edit_name_cursor = 0
        self.ui_state.inline_edit_deadline = deadline
        self.ui_state.inline_edit_priority = "none"
        self.ui_state.inline_edit_notes = None
        self.ui_state.inline_edit_notes_cursor = 0
        self.ui_state.inline_edit_deadline_component = 0
        self.ui_state.inline_input_mode = False
        self.ui_state.text_input_buffer = ""
        
        logger.info("Starting inline task add from calendar for %s", deadline)

    # Cell selection mode helpers for project browser inline editing

    def _get_visible_fields_for_cell_mode(self):
        """Get the list of visible fields for cell selection mode.
        
        Returns list including pseudo-fields for status (0) and name (1),
        followed by actual custom fields (2+).
        """
        from pm_live.custom_fields import CustomField, SelectOption
        from pm import STATUS_DISPLAY_ORDER
        
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

    def _enter_cell_selection_mode(self):
        """Enter cell selection mode in project browser."""
        self.ui_state.cell_selection_mode = True
        self.ui_state.cell_selected_column = 0
        self.ui_state.cell_editing = False
        self.ui_state.cell_edit_buffer = ""
        self.ui_state.cell_edit_date_buffer = None
        self.ui_state.cell_edit_date_component = 0

    def _exit_cell_selection_mode(self):
        """Exit cell selection mode and return to normal project navigation."""
        self.ui_state.cell_selection_mode = False
        self.ui_state.cell_selected_column = 0
        self.ui_state.cell_editing = False
        self.ui_state.cell_edit_buffer = ""
        self.ui_state.cell_edit_date_buffer = None
        self.ui_state.cell_edit_date_component = 0

    def _cancel_cell_edit(self):
        """Cancel editing the current cell and return to cell selection mode."""
        self.ui_state.cell_editing = False
        self.ui_state.cell_edit_buffer = ""
        self.ui_state.cell_edit_date_buffer = None
        self.ui_state.cell_edit_date_component = 0

    def _ensure_cell_edit_date_buffer(self):
        """Ensure cell edit date buffer has an initialized value."""
        if not self.ui_state.cell_edit_date_buffer:
            from datetime import datetime
            today = datetime.now()
            self.ui_state.cell_edit_date_buffer = f"{today.year:04d}-{today.month:02d}-{today.day:02d}"

    def _adjust_cell_edit_date(self, direction: int):
        """Increment/decrement a cell edit date component."""
        self._ensure_cell_edit_date_buffer()

        parts = self.ui_state.cell_edit_date_buffer.split('-')
        if len(parts) != 3:
            return

        try:
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
        except ValueError:
            return

        comp = self.ui_state.cell_edit_date_component
        if comp == 0:
            year = max(2000, min(2100, year + direction))
        elif comp == 1:
            month += direction
            if month > 12:
                month = 1
            elif month < 1:
                month = 12
            import calendar
            max_day = calendar.monthrange(year, month)[1]
            day = min(day, max_day)
        else:
            import calendar
            max_day = calendar.monthrange(year, month)[1]
            day += direction
            if day > max_day:
                day = 1
            elif day < 1:
                day = max_day

        self.ui_state.cell_edit_date_buffer = f"{year:04d}-{month:02d}-{day:02d}"
