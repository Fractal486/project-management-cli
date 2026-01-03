"""Main application controller for the live CLI."""

import logging
import re
from io import StringIO
from typing import Optional, Sequence

from rich.console import Console
from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, HSplit, Window, FormattedTextControl
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.layout.dimension import Dimension
try:
    # Windows-only, but safe to import conditionally
    from prompt_toolkit.output.win32 import NoConsoleScreenBufferError  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - non-Windows or older prompt_toolkit
    NoConsoleScreenBufferError = Exception  # type: ignore[assignment]
from prompt_toolkit.output import DummyOutput

from pm import ProjectManager
from .config import get_config, set_config
from .interfaces import HandlerContext
from .states import AppState
from .ui_state import UIState
from .keybindings import create_key_bindings
from .quick_stats import DEFAULT_QUICK_STATS, normalize_quick_stats_selection
from .main_menu_tabs import (
    normalize_main_menu_tabs,
    build_main_menu_items,
    is_quick_add_enabled,
)
from .render import (
    rich_to_formatted_text, MainMenuRenderer, ProjectBrowserRenderer,
    ProjectDetailsRenderer, TaskListRenderer, StatisticsRenderer,
    SettingsRenderer, QuickStatsSettingsRenderer, MainMenuTabsRenderer, DeadlineSettingsRenderer, ProjectBrowserDefaultTabRenderer, StatsNoneSettingsRenderer, MessageDisplaySettingsRenderer, NotesDisplaySettingsRenderer, BookmarkActionSettingsRenderer, CustomFieldsRenderer, AddCustomFieldRenderer, EditCustomFieldRenderer, EditProjectRenderer, ChangeStatusRenderer, EditListRenderer, CalendarRenderer,
    BookmarksRenderer, AddBookmarkRenderer, EditBookmarkRenderer, BookmarkListRenderer,
    DeleteConfirmationRenderer, HelpRenderer,
    SearchRenderer
)
from .tasks import flatten_tasks
from .handlers import KeyHandlers, EnterHandlers, TaskHandlers, BookmarkHandlers

logger = logging.getLogger(__name__)

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
RICH_TAG_RE = re.compile(r"\[[^\]]+\]")

HORIZONTAL_DIVIDER_CHARS = {
    "-", "\u2500", "\u2501", "\u2550", "=", "~", "\u2015", "\u2014", "\u2013",
    "\u203e", "_", "\u00b7", "\u2022", "\u22c5"
}
VERTICAL_DIVIDER_CHARS = {
    "|", "\u2502", "\u2503", "\u2551", "\u2506", "\u2507", "\u250a", "\u250b",
    "\u257f", "\u257d"
}


class LiveCLI:
    """Live terminal CLI with single persistent box - lightweight coordinator."""

    def __init__(self, manager: ProjectManager):
        self.manager = manager
        self.ui_state = UIState()
        self._last_state = self.ui_state.state
        # Initialize per-list task containers from manager (Option B)
        try:
            self.ui_state.list_tasks = getattr(self.manager, "list_tasks", {"Tasks": self.manager.standalone_tasks})
        except Exception:
            self.ui_state.list_tasks = {"Tasks": []}

        # Initialize task list tabs from loaded list_tasks keys
        self.ui_state.task_lists = list(self.ui_state.list_tasks.keys())

        initial_config = get_config()
        quick_stats = normalize_quick_stats_selection(initial_config.quick_stats_metrics)
        if not quick_stats:
            quick_stats = list(DEFAULT_QUICK_STATS)
        self.ui_state.quick_stats_selection = set(quick_stats)
        main_menu_tabs = normalize_main_menu_tabs(initial_config.main_menu_tabs)
        self.ui_state.main_menu_tabs_selection = set(main_menu_tabs)
        self._restore_collapsed_tasks()
        self._initialize_console(initial_config.console_width)
        logger.debug("Console initialised with width %s", initial_config.console_width)

        # Shared handler context and handlers
        self._handler_context = HandlerContext(
            manager=self.manager,
            ui_state=self.ui_state,
            get_flat_tasks=self._get_flat_tasks,
            invalidate_task_cache=self._invalidate_task_cache,
            exit_application=self._exit_application,
            show_status=self._show_status,
            update_console_width=self.update_console_width,
            update_quick_stats_selection=self.update_quick_stats_selection,
            update_main_menu_tabs_selection=self.update_main_menu_tabs_selection,
            persist_collapsed_tasks=self._persist_collapsed_tasks,
        )

        self.task_handlers = TaskHandlers(self._handler_context)
        self.bookmark_handlers = BookmarkHandlers(self._handler_context)
        self.enter_handlers = EnterHandlers(self._handler_context, self.bookmark_handlers, self.task_handlers)
        self.key_handlers = KeyHandlers(self._handler_context, self.task_handlers, self.enter_handlers)
        # Allow enter handlers to clamp form cursor movement based on key handler logic
        self.enter_handlers.set_key_handlers(self.key_handlers)
        logger.debug("Handlers created and bound to context")

        # Create the application
        self.kb = create_key_bindings(self)
        self.app = self._create_application()
        logger.debug("Application layout initialised")

    def _restore_collapsed_tasks(self) -> None:
        """Load persisted collapsed task ids into the UI state."""
        try:
            metadata = getattr(self.manager, "metadata", {}) or {}
        except Exception:
            metadata = {}
        if "collapsed_tasks" not in metadata:
            return

        raw = metadata.get("collapsed_tasks")
        collapsed_raw: set[str] = set()
        if isinstance(raw, str):
            # Handle string (e.g., 'item1, item2')
            collapsed_raw = {item.strip() for item in raw.split(',') if item and item.strip()}
        elif isinstance(raw, (list, tuple, set)):
            # Handle list/tuple/set of items
            collapsed_raw = {str(item).strip() for item in raw if str(item).strip()}

        collapsed = collapsed_raw

        # Only override the default if the key exists (so empty list means expand all)
        # Always keep the special Done section collapsed by default (transient UI behavior).
        collapsed.add("section_completed")
        self.ui_state.collapsed_tasks = collapsed
        logger.debug("Restored %d collapsed task entries from metadata", len(collapsed))

    def _persist_collapsed_tasks(self) -> None:
        """Persist collapsed task ids to metadata and save to disk."""
        try:
            # Do not persist the Done section collapse/expand state; it should reset when leaving the task list.
            collapsed_list = sorted(
                str(item)
                for item in self.ui_state.collapsed_tasks
                if str(item) != "section_completed"
            )
            if not isinstance(getattr(self.manager, "metadata", None), dict):
                self.manager.metadata = {}
            current = self.manager.metadata.get("collapsed_tasks")
            if current == collapsed_list:
                return
            self.manager.metadata["collapsed_tasks"] = collapsed_list
            if hasattr(self.manager, "mark_metadata_modified"):
                self.manager.mark_metadata_modified()
            elif hasattr(self.manager, "mark_dirty"):
                self.manager.mark_dirty()
            self.manager.save()
            logger.debug("Persisted %d collapsed task entries", len(collapsed_list))
        except Exception as exc:
            logger.debug("Failed to persist collapsed tasks: %s", exc, exc_info=True)

    def _create_application(self) -> Application:
        """Create the prompt_toolkit application."""
        # Create the main content window (expands to fill space)
        content_control = FormattedTextControl(
            text=self._get_formatted_text,
            focusable=True
        )

        content_window = Window(
            content=content_control,
            wrap_lines=True,
            always_hide_cursor=True,  # Hide the actual cursor, we use > selector
            dont_extend_height=True  # Only take space needed for content
        )

        # Create the footer window (pinned at bottom, adapts to content height)
        footer_control = FormattedTextControl(
            text=self._get_footer_text
        )

        footer_window = Window(
            content=footer_control,
            wrap_lines=True,
            dont_extend_height=True  # Keep footer sized to its content
        )

        # Create layout: content (takes what it needs) + spacer (expands) + footer (fixed at bottom)
        layout = Layout(
            HSplit([
                content_window,  # Main content (only takes space it needs)
                Window(height=Dimension(weight=1)),  # Flexible spacer that expands
                footer_window   # Fixed height, always at bottom
            ])
        )

        try:
            app = Application(
                layout=layout,
                key_bindings=self.kb,
                full_screen=True,
                mouse_support=False,
            )
        except NoConsoleScreenBufferError:
            # When running under environments without a real Windows console
            # (e.g. unit tests, CI, redirected output), fall back to an in-memory
            # dummy output so the Application can still be constructed.
            logger.warning("No Windows console detected; using DummyOutput for Application")
            app = Application(
                layout=layout,
                key_bindings=self.kb,
                full_screen=True,
                mouse_support=False,
                output=DummyOutput(),
            )
        logger.debug("prompt_toolkit Application created (full_screen=%s)", True)
        return app

    def _get_formatted_text(self) -> FormattedText:
        """Get the formatted text for the current state."""
        # Reset console buffer for reuse
        self._console_buffer.seek(0)
        self._console_buffer.truncate(0)

        # Build context for renderer
        context = self._build_render_context()

        # If help overlay is active, show help instead of normal content
        if self.ui_state.show_help:
            renderer = self.help_renderer
        else:
            # Render using appropriate renderer
            renderer = self.renderers[self.ui_state.state]

        rich_content = renderer.render(context)

        # Remove footer from content (it will be displayed in the footer window)
        content_without_footer = self._remove_footer_from_content(rich_content)

        # Convert Rich output to prompt_toolkit formatted text
        return rich_to_formatted_text(content_without_footer)

    def _get_footer_text(self) -> FormattedText:
        """Get the footer/action buttons for the current state."""
        context = self._build_render_context()

        # Get the current renderer
        if self.ui_state.show_help:
            renderer = self.help_renderer
        else:
            renderer = self.renderers.get(self.ui_state.state)

        if renderer:
            # Render the full content
            rich_content = renderer.render(context)

            # Extract footer from rendered content (last 3-5 lines that contain actions)
            footer_content = self._extract_footer_from_content(rich_content)
            if footer_content:
                return rich_to_formatted_text(footer_content)

        # Default: show status message if available
        status_message = context.get('status_message')
        if status_message:
            # Status messages are already rendered within the main content renderers.
            # Returning an empty footer avoids showing the same status twice.
            return FormattedText([])

        return FormattedText([])

    def _find_divider_index(self, lines: list) -> int:
        """Find the divider that separates the main content from footer/actions."""
        for index in range(len(lines) - 1, -1, -1):
            raw_line = lines[index]
            visible_line = self._strip_formatting(raw_line).strip()

            if not visible_line:
                continue

            if "Actions:" in visible_line:
                if not any(self._has_visible_content(line) for line in lines[index + 1:]):
                    continue
                candidate = index - 1
                while candidate >= 0 and not self._has_visible_content(lines[candidate]):
                    candidate -= 1
                if candidate >= 0 and self._is_divider_line(lines[candidate]):
                    return candidate
                return index

            if self._is_divider_line(raw_line):
                if any(self._has_visible_content(line) for line in lines[index + 1:]):
                    return index

        return -1

    def _strip_formatting(self, line: str) -> str:
        """Remove Rich markup and ANSI escape codes from a line."""
        if not line:
            return ""
        without_tags = RICH_TAG_RE.sub("", line)
        return ANSI_ESCAPE_RE.sub("", without_tags)

    def _has_visible_content(self, line: str) -> bool:
        """Return True when the line contains non-formatting visible characters."""
        return bool(self._strip_formatting(line).strip())

    def _is_divider_line(self, line: str) -> bool:
        """Return True if the given line is a horizontal divider."""
        if not line:
            return False

        stripped = line.strip()
        cleaned = self._strip_formatting(stripped).strip()
        if not cleaned:
            return False

        cleaned_no_space = cleaned.replace(" ", "")
        if not cleaned_no_space:
            return False

        unique_chars = set(cleaned_no_space)
        if unique_chars <= VERTICAL_DIVIDER_CHARS:
            return False

        return unique_chars <= HORIZONTAL_DIVIDER_CHARS

    def _remove_footer_from_content(self, content: str) -> str:
        """Remove footer/actions from the rendered content."""
        lines = content.split('\n')

        divider_index = self._find_divider_index(lines)

        if divider_index >= 0:
            # Return everything before the divider (and optionally the blank line before it)
            content_lines = lines[:divider_index]
            # Remove trailing empty lines
            while content_lines and not content_lines[-1].strip():
                content_lines.pop()
            return '\n'.join(content_lines)

        # No footer found, return as-is
        return content

    def _extract_footer_from_content(self, content: str) -> str:
        """Extract footer/actions from the rendered content."""
        lines = content.split('\n')

        divider_index = self._find_divider_index(lines)

        if divider_index >= 0:
            # Return divider and everything after it
            footer_lines = lines[divider_index:]
            # Filter out empty lines at the end
            while footer_lines and not footer_lines[-1].strip():
                footer_lines.pop()
            return '\n'.join(footer_lines)

        return ""

    def _build_render_context(self) -> dict:
        """Build context dictionary for renderers."""
        from pm_live.config import get_config
        config = get_config()

        if self.ui_state.state != self._last_state:
            self._show_status(None)
            self._last_state = self.ui_state.state

        # Refresh pinned metadata (e.g., deadlines/priorities) from source items
        try:
            if hasattr(self.manager, "refresh_pinned_metadata"):
                self.manager.refresh_pinned_metadata()
        except Exception:
            logger.debug("refresh_pinned_metadata failed", exc_info=True)

        custom_field_definitions = getattr(self.manager, 'custom_field_definitions', [])
        default_field_visibility = getattr(self.manager, 'default_field_visibility', {})

        # Collect overdue and upcoming entries for calendar if in calendar state
        overdue_entries = []
        total_overdue_count = 0
        upcoming_entries = {}
        if self.ui_state.state == AppState.CALENDAR:
            from .utils.calendar import collect_overdue_entries, collect_upcoming_entries
            from datetime import datetime
            list_tasks_map = getattr(
                self.ui_state,
                'list_tasks',
                getattr(self.manager, "list_tasks", {"Tasks": getattr(self.manager, 'standalone_tasks', [])}),
            )
            all_overdue = collect_overdue_entries(
                self.manager,
                list_tasks_map,
                datetime.now().date(),
                max_items=20
            )
            total_overdue_count = len(all_overdue)
            overdue_entries = all_overdue
            
            # Collect upcoming entries
            upcoming_entries = collect_upcoming_entries(
                self.manager,
                list_tasks_map,
                datetime.now().date()
            )

        return {
            'manager': self.manager,
            'state': self.ui_state.state,
            'selected_index': self.ui_state.selected_index,
            'active_tab': self.ui_state.active_tab,
            'task_lists': self.ui_state.task_lists,
            'list_tasks': getattr(
                self.ui_state,
                'list_tasks',
                getattr(self.manager, "list_tasks", {"Tasks": getattr(self.manager, 'standalone_tasks', [])}),
            ),
            'current_project_id': self.ui_state.current_project_id,
            'current_list_index': self.ui_state.current_list_index,
            'is_new': self.ui_state.current_list_index is None,
            'text_input_buffer': self.ui_state.text_input_buffer,
            'text_input_cursor': self.ui_state.text_input_cursor,
            'form_data': self.ui_state.form_data,
            'editing_list_name': self.ui_state.editing_list_name,
            'form_field_index': self.ui_state.form_field_index,
            'inline_input_mode': self.ui_state.inline_input_mode,
            'inline_list_create_mode': getattr(self.ui_state, 'inline_list_create_mode', False),
            'inline_list_edit_mode': getattr(self.ui_state, 'inline_list_edit_mode', False),
            'inline_task_edit_mode': self.ui_state.inline_task_edit_mode,
            'inline_edit_origin': self.ui_state.inline_edit_origin,
            'inline_edit_task_id': self.ui_state.inline_edit_task_id,
            'inline_edit_task': self.ui_state.inline_edit_task,
            'inline_edit_field_index': self.ui_state.inline_edit_field_index,
            'inline_edit_deadline_component': self.ui_state.inline_edit_deadline_component,
            'inline_edit_name': self.ui_state.inline_edit_name,
            'inline_edit_name_cursor': self.ui_state.inline_edit_name_cursor,
            'inline_edit_deadline': self.ui_state.inline_edit_deadline,
            'inline_edit_priority': self.ui_state.inline_edit_priority,
            'inline_edit_notes': self.ui_state.inline_edit_notes,
            'inline_edit_notes_cursor': self.ui_state.inline_edit_notes_cursor,
            'custom_field_date_edit_mode': self.ui_state.custom_field_date_edit_mode,
            'custom_field_date_component': self.ui_state.custom_field_date_component,
            'custom_field_date_buffer': self.ui_state.custom_field_date_buffer,
            'pending_section_add': getattr(self.ui_state, 'pending_section_add', False),
            'collapsed_tasks': self.ui_state.collapsed_tasks,
            'quick_add_priority': self.ui_state.quick_add_priority,
            'quick_add_field_index': self.ui_state.quick_add_field_index,
            'quick_add_deadline': self.ui_state.quick_add_deadline,
            'quick_add_deadline_component': self.ui_state.quick_add_deadline_component,
            'quick_add_deadline_edit_mode': self.ui_state.quick_add_deadline_edit_mode,
            'quick_add_list': self.ui_state.quick_add_list,
            'calendar_year': self.ui_state.calendar_year,
            'calendar_month': self.ui_state.calendar_month,
            'calendar_selected_day': self.ui_state.calendar_selected_day,
            'calendar_navigation_focus': self.ui_state.calendar_navigation_focus,
            'calendar_task_selected_index': self.ui_state.calendar_task_selected_index,
            'calendar_tasks_tab': self.ui_state.calendar_tasks_tab,
            'calendar_upcoming_collapsed': self.ui_state.calendar_upcoming_collapsed,
            'overdue_entries': overdue_entries,
            'total_overdue_count': total_overdue_count,
            'upcoming_entries': upcoming_entries,
            'quick_stats_selection': self.ui_state.quick_stats_selection,
            'main_menu_tabs_selection': self.ui_state.main_menu_tabs_selection,
            'status_message': self.ui_state.status_message,
            'status_is_error': self.ui_state.status_is_error,
            'delete_context': self.ui_state.delete_context,
            'show_all_keybindings': self.ui_state.show_all_keybindings,
            'custom_field_definitions': custom_field_definitions,
            'custom_fields': getattr(self.ui_state, 'custom_fields', custom_field_definitions),
            'default_field_visibility': default_field_visibility,
            'all_fields': self._get_all_fields(),
            'select_options': getattr(self.ui_state, 'select_options', []),
            'field_label': getattr(self.ui_state, 'field_label', ''),
            # Cell selection mode for project browser inline editing
            'cell_selection_mode': self.ui_state.cell_selection_mode,
            'cell_selected_column': self.ui_state.cell_selected_column,
            'cell_editing': self.ui_state.cell_editing,
            'cell_edit_buffer': self.ui_state.cell_edit_buffer,
            'cell_edit_date_buffer': self.ui_state.cell_edit_date_buffer,
            'cell_edit_date_component': self.ui_state.cell_edit_date_component,
            'project_sort_key': getattr(self.ui_state, 'project_sort_key', None),
            'project_sort_order': getattr(self.ui_state, 'project_sort_order', None),
            # Temp project for ADD_PROJECT mode
            'temp_project': getattr(self.ui_state, '_temp_project', None),
            # Pinned items navigation
            'in_pinned_section': self.ui_state.in_pinned_section,
            'pinned_selected_index': self.ui_state.pinned_selected_index,
            # Search state
            'search_query': self.ui_state.search_query,
            'search_results': self.ui_state.search_results,
            'search_selected_index': self.ui_state.search_selected_index,
            # Pass ui_state itself for renderers that need to update it
            'ui_state': self.ui_state,
        }

    def _input_blocked_in_help(self, *, allow_escape: bool = False, allow_help: bool = False) -> bool:
        """Return True if a keypress should be ignored while the help overlay is visible."""
        if not getattr(self.ui_state, "show_help", False):
            return False
        if allow_escape or allow_help:
            return False
        return True

    # Delegate key bindings to handlers
    def on_up(self):
        """Handle up key."""
        if self._input_blocked_in_help():
            return
        self.key_handlers.on_up()

    def on_down(self):
        """Handle down key."""
        if self._input_blocked_in_help():
            return
        self.key_handlers.on_down()

    def on_tab(self):
        """Handle tab key."""
        if self._input_blocked_in_help():
            return
        self.key_handlers.on_tab()

    def on_shift_tab(self):
        """Handle Shift+Tab key."""
        if self._input_blocked_in_help():
            return
        self.key_handlers.on_shift_tab()

    def on_collapse(self):
        """Handle 'c' key."""
        if self._input_blocked_in_help():
            return
        self.key_handlers.on_collapse()

    def on_enter(self):
        """Handle enter key."""
        if self._input_blocked_in_help():
            return
        self.enter_handlers.handle_enter()

    def on_escape(self):
        """Handle escape key (Esc)."""
        if self._input_blocked_in_help(allow_escape=True):
            return
        # Optimize help overlay closing: handle it directly here (same path as 'h')
        # to avoid extra branching in key handlers.
        if self.ui_state.show_help:
            self.ui_state.show_help = False
            self.ui_state.show_all_keybindings = False
            return

        self.key_handlers.on_escape()

    def on_edit(self):
        """Handle edit key (e) across contexts."""
        if self._input_blocked_in_help():
            return

        # Pinned section edit: jump to source and start edit
        if self.ui_state.state == AppState.MAIN_MENU and getattr(self.ui_state, "in_pinned_section", False):
            # Reset pinned expansions when switching screens from the pinned section.
            self.ui_state.expanded_pinned_lists = set()
            self.ui_state.expanded_pinned_sections = set()
            self.ui_state.expanded_pinned_list_sections = set()

            pinned_idx = getattr(self.ui_state, "pinned_selected_index", 0)
            display_items = getattr(self.ui_state, "pinned_display_items", None)
            items = getattr(self.ui_state, "reordered_pinned_items", None)
            if not items:
                pinned_items = self.manager.get_pinned_items()
                pinned_projects = [p for p in pinned_items if p.get("type") == "project"]
                pinned_tasks = [p for p in pinned_items if p.get("type") in ("task", "list", "section")]
                pinned_bookmarks = [p for p in pinned_items if p.get("type") in ("bookmark", "bookmark_list")]
                items = pinned_projects + pinned_tasks + pinned_bookmarks
            target_list = display_items or items
            if 0 <= pinned_idx < len(target_list):
                if display_items:
                    entry = target_list[pinned_idx]
                    kind = entry.get("kind")
                    # Jump into tasks inside pinned lists/sections
                    if kind in ("list_task", "section_task"):
                        list_name = entry.get("list_name", "Tasks")
                        section_idx = entry.get("section_idx", 0)
                        list_id = entry.get("list_id")
                        section_id = entry.get("section_id")
                        if section_id:
                            resolved_list, resolved_idx, _ = self.manager.find_section_by_id(section_id)
                            if resolved_list:
                                list_name = resolved_list
                            if resolved_idx is not None:
                                section_idx = resolved_idx
                        elif list_id:
                            resolved_name = self.manager.get_list_name_by_id(list_id)
                            if resolved_name:
                                list_name = resolved_name
                        task_name = entry.get("task_name", "")
                        task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
                        if list_name not in task_lists:
                            task_lists.append(list_name)
                            self.ui_state.task_lists = task_lists
                        self.ui_state.active_tab = task_lists.index(list_name)
                        self.ui_state.state = AppState.TASK_LIST
                        self.ui_state.inline_task_edit_mode = False
                        layout = self.enter_handlers._build_task_list_layout()
                        if layout:
                            idx_map = layout.get("task_index_to_data", {})
                            section_map = layout.get("index_to_section_idx", {})
                            match_index = None
                            for idx, (task_id, task, section_tasks) in idx_map.items():
                                if getattr(task, "name", None) == task_name and section_map.get(idx) == section_idx:
                                    match_index = idx
                                    break
                            if match_index is not None:
                                self.ui_state.selected_index = match_index
                                self.task_handlers.begin_inline_edit()
                        return
                    if kind == "list_section":
                        list_name = entry.get("list_name", "Tasks")
                        section_idx = entry.get("section_idx", 0)
                        list_id = entry.get("list_id")
                        section_id = entry.get("section_id")
                        if section_id:
                            resolved_list, resolved_idx, _ = self.manager.find_section_by_id(section_id)
                            if resolved_list:
                                list_name = resolved_list
                            if resolved_idx is not None:
                                section_idx = resolved_idx
                        elif list_id:
                            resolved_name = self.manager.get_list_name_by_id(list_id)
                            if resolved_name:
                                list_name = resolved_name
                        task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
                        if list_name not in task_lists:
                            task_lists.append(list_name)
                            self.ui_state.task_lists = task_lists
                        self.ui_state.active_tab = task_lists.index(list_name)
                        self.ui_state.state = AppState.TASK_LIST
                        self.ui_state.inline_task_edit_mode = False
                        layout = self.enter_handlers._build_task_list_layout()
                        if layout:
                            header_indices = layout.get("section_header_indices", {})
                            header_idx = header_indices.get(section_idx, 0)
                            self.ui_state.selected_index = header_idx
                        return
                    item = entry.get("item", {})
                    item_type = item.get("type")
                else:
                    item = target_list[pinned_idx]
                    item_type = item.get("type")

                # Projects -> open details and jump into Edit Project action
                if item_type == "project":
                    project_id = item.get("id")
                    project = self.manager.get_project(project_id)
                    if project:
                        self.ui_state.state = AppState.PROJECT_DETAILS
                        self.ui_state.current_project_id = project_id
                        flat_tasks = self._get_flat_tasks(project.tasks, True)
                        # In project details enter handler: add_index = len(flat_tasks); actions start at add_index+1; edit project is action_idx 1 => selection add_index+2
                        self.ui_state.selected_index = len(flat_tasks) + 2
                        # Trigger the edit action immediately
                        self.enter_handlers.handle_project_details_enter()
                    return

                # Tasks -> start inline editing
                if item_type == "task":
                    task_id = item.get("id")
                    task_name = item.get("name", "")
                    task_obj, _ = self.manager.resolve_task_for_pin(
                        task_id,
                        task_name=task_name,
                        project_id=item.get("project_id"),
                        list_name=item.get("list_name"),
                        section_idx=item.get("section_idx"),
                    )

                    # Start inline editing if task found
                    if task_obj:
                        self.ui_state.inline_task_edit_mode = True
                        self.ui_state.inline_edit_task = task_obj
                        self.ui_state.inline_edit_task_id = None
                        self.ui_state.inline_edit_field_index = 0
                        self.ui_state.inline_edit_name = getattr(task_obj, "name", "")
                        self.ui_state.inline_edit_name_cursor = len(self.ui_state.inline_edit_name)
                        self.ui_state.inline_edit_deadline = getattr(task_obj, "deadline", None)
                        self.ui_state.inline_edit_priority = getattr(task_obj, "priority", None)
                        self.ui_state.inline_edit_notes = getattr(task_obj, "notes", None) or None
                        self.ui_state.inline_edit_notes_cursor = len(self.ui_state.inline_edit_notes or "")
                        self.ui_state.inline_edit_deadline_component = 0
                    return

                # Views (lists) -> open task list editor (EDIT_TAB)
                if item_type == "list":
                    list_name = item.get("name", "")
                    self.ui_state.editing_list_name = list_name
                    self.ui_state.state = AppState.EDIT_TAB
                    self.ui_state.selected_index = 0
                    self.ui_state.form_field_index = 0
                    # Pre-populate form data with current sections and color
                    list_meta = getattr(self.manager, "list_metadata", {}).get(list_name, {})
                    current_sections = self.manager.list_tasks.get(list_name, [])
                    sections_data = []
                    for section in current_sections or []:
                        section_name = getattr(section, "name", "") if hasattr(section, "name") else section.get("name", "")
                        section_tasks = getattr(section, "tasks", []) if hasattr(section, "tasks") else section.get("tasks", [])
                        sections_data.append({"name": section_name, "tasks": section_tasks})
                    if len(sections_data) == 1 and sections_data[0].get("name", "") == "":
                        list_mode = "normal"
                        sections_data = []
                    else:
                        list_mode = "sections"
                    self.ui_state.form_data = {
                        "name": list_name,
                        "color": list_meta.get("color", "white"),
                        "mode": list_mode,
                        "sections": sections_data,
                    }
                    self.ui_state.inline_input_mode = False
                    self.ui_state.text_input_buffer = ""
                    return

                # Sections -> jump to task list with section header selected
                if item_type == "section":
                    list_name = item.get("list_name", "Tasks")
                    section_idx = item.get("section_idx", 0)
                    task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
                    if list_name not in task_lists:
                        task_lists.append(list_name)
                        self.ui_state.task_lists = task_lists
                    self.ui_state.active_tab = task_lists.index(list_name)
                    self.ui_state.state = AppState.TASK_LIST
                    self.ui_state.inline_task_edit_mode = False
                    layout = self.enter_handlers._build_task_list_layout()
                    if layout:
                        header_indices = layout.get("section_header_indices", {})
                        header_idx = header_indices.get(section_idx, 0)
                        self.ui_state.selected_index = header_idx
                    return

                # Bookmarks -> jump to list and edit
                if item_type in ("bookmark", "bookmark_list"):
                    from pm import Bookmark, BookmarkList
                    bookmarks = self.manager.bookmarks
                    item_id = item.get("id")
                    target_index = None
                    target_list_index = None  # For bookmarks inside lists
                    target_item_index = None  # Index within the list

                    if item_type == "bookmark":
                        if item_id:
                            for idx, b in enumerate(bookmarks):
                                if isinstance(b, Bookmark) and getattr(b, "id", None) == item_id:
                                    target_index = idx
                                    break
                        if target_index is None:
                            for idx, b in enumerate(bookmarks):
                                if isinstance(b, Bookmark) and b.title == item.get("title") and b.url == item.get("url"):
                                    target_index = idx
                                    break
                    elif item_type == "bookmark_list":
                        if item_id:
                            for idx, b in enumerate(bookmarks):
                                if isinstance(b, BookmarkList) and getattr(b, "id", None) == item_id:
                                    target_index = idx
                                    break
                        if target_index is None:
                            for idx, b in enumerate(bookmarks):
                                if isinstance(b, BookmarkList) and b.title == item.get("title"):
                                    target_index = idx
                                    break

                    # If not found in main list, search inside bookmark lists
                    if target_index is None and item_type == "bookmark":
                        if item_id:
                            for list_idx, b in enumerate(bookmarks):
                                if isinstance(b, BookmarkList):
                                    for item_idx, bookmark in enumerate(b.items):
                                        if getattr(bookmark, "id", None) == item_id:
                                            target_list_index = list_idx
                                            target_item_index = item_idx
                                            break
                                    if target_list_index is not None:
                                        break
                        if target_list_index is None:
                            for list_idx, b in enumerate(bookmarks):
                                if isinstance(b, BookmarkList):
                                    for item_idx, bookmark in enumerate(b.items):
                                        if bookmark.title == item.get("title") and bookmark.url == item.get("url"):
                                            target_list_index = list_idx
                                            target_item_index = item_idx
                                            break
                                    if target_list_index is not None:
                                        break

                    if target_index is not None:
                        self.ui_state.current_list_index = target_index if item_type == "bookmark_list" else None
                        self.ui_state.state = AppState.BOOKMARKS
                        self.ui_state.selected_index = target_index
                        # Delegate to existing bookmark edit handler (lists enter inline rename mode)
                        self.bookmark_handlers.handle_bookmarks_edit()
                    elif target_list_index is not None and target_item_index is not None:
                        # Bookmark is inside a list - navigate to the list and edit the bookmark
                        self.ui_state.state = AppState.BOOKMARK_LIST
                        self.ui_state.current_list_index = target_list_index
                        self.ui_state.selected_index = target_item_index
                        # Trigger edit for the bookmark inside the list
                        self.bookmark_handlers.handle_bookmark_list_edit()
                    return

        # Calendar task edit: inline editing (same as main menu pinned section)
        if self.ui_state.state == AppState.CALENDAR and self.ui_state.calendar_navigation_focus == "tasks":
            tasks = self.key_handlers._get_calendar_tasks_for_active_tab()
            task_index = self.ui_state.calendar_task_selected_index
            if 0 <= task_index < len(tasks):
                item = tasks[task_index]
                # Extract actual entry (handle tuples for upcoming tab and overdue tab)
                if isinstance(item, tuple):
                    if isinstance(item[0], str):
                        # Upcoming tab: could be ("task", entry) or ("header", ...)
                        if item[0] == "header":
                            # User selected a section header, not a task - ignore edit
                            return
                        # Must be ("task", entry)
                        entry = item[1]
                    else:
                        # Overdue tab: (entry, days_overdue)
                        entry = item[0]
                else:
                    # Selected Day tab: just entry
                    entry = item
                if entry.kind != "task":
                    project = entry.item
                    project_id = getattr(project, "id", None)
                    if project_id is None:
                        self._show_status("Project not found", is_error=True)
                        return

                    self.ui_state.state = AppState.PROJECT_DETAILS
                    self.ui_state.current_project_id = project_id
                    flat_tasks = self._get_flat_tasks(project.tasks, True)
                    # In project details enter handler: add_index = len(flat_tasks); actions start at add_index+1; edit project is action_idx 1 => selection add_index+2
                    self.ui_state.selected_index = len(flat_tasks) + 2
                    self.enter_handlers.handle_project_details_enter()
                    return

                task = entry.item
                # Start inline edit mode
                self.ui_state.inline_task_edit_mode = True
                self.ui_state.inline_edit_task = task
                self.ui_state.inline_edit_task_id = None
                self.ui_state.inline_edit_origin = "calendar"
                self.ui_state.inline_edit_field_index = 0
                self.ui_state.inline_edit_name = getattr(task, "name", "")
                self.ui_state.inline_edit_name_cursor = len(self.ui_state.inline_edit_name)
                self.ui_state.inline_edit_deadline = getattr(task, "deadline", None)
                self.ui_state.inline_edit_priority = getattr(task, "priority", None)
                self.ui_state.inline_edit_deadline_component = 0
            return

        if self.ui_state.inline_input_mode:
            # Inline typing: insert the character instead of triggering actions
            self.ui_state.text_input_buffer += 'e'
            return

        # Project browser header: edit the selected field definition
        if (
            self.ui_state.state == AppState.PROJECT_BROWSER
            and self.ui_state.selected_index == -1
            and getattr(self.ui_state, "cell_selection_mode", False)
        ):
            field = self.key_handlers._get_cell_selected_field()
            if field and field.key not in ("__status__", "__name__", "__progress__"):
                custom_fields = getattr(self.manager, "custom_field_definitions", [])
                for idx, cf in enumerate(custom_fields):
                    if getattr(cf, "key", None) == field.key:
                        self.enter_handlers.start_edit_custom_field(idx)
                        return
            return

        # Project browser: edit the selected project
        if (
            self.ui_state.state == AppState.PROJECT_BROWSER
            and self.ui_state.selected_index >= 0
            and not getattr(self.ui_state, "cell_selection_mode", False)
        ):
            from .utils import filter_projects_by_tab, sort_projects_for_display
            filtered = filter_projects_by_tab(self.manager.projects, self.ui_state.active_tab)
            filtered = sort_projects_for_display(
                filtered,
                self.ui_state.project_sort_key,
                self.manager.custom_field_definitions,
                self.ui_state.project_sort_order,
            )
            
            if self.ui_state.selected_index < len(filtered):
                project = filtered[self.ui_state.selected_index]
                self.ui_state.current_project_id = project.id
                
                self.ui_state.form_data = {
                    "name": project.name,
                    "description": getattr(project, "description", ""),
                    "status": project.status,
                }
                # Pre-fill custom fields (including built-ins like timeframe)
                self.ui_state.form_data.update(project.custom_field_values)
                
                self.ui_state.previous_state = self.ui_state.state
                self.ui_state.state = AppState.EDIT_PROJECT
                self.ui_state.selected_index = 0
                self.ui_state.form_field_index = 0
                logger.info("Opening edit project form for project %s via 'e' key", project.id)
                return

        if self.ui_state.state == AppState.CUSTOMIZE_FIELDS:
            try:
                from pm_live.custom_fields import get_builtin_fields
                default_visibility = getattr(self.manager, "default_field_visibility", {})
                builtin_fields = get_builtin_fields(default_visibility)
            except Exception:
                builtin_fields = []
            custom_fields = getattr(self.manager, "custom_field_definitions", [])
            selected_idx = self.ui_state.selected_index
            # Custom fields start after: Progress (1) + builtin fields
            custom_start = 1 + len(builtin_fields)
            custom_end = custom_start + len(custom_fields)
            if custom_start <= selected_idx < custom_end:
                field_idx = selected_idx - custom_start
                self.enter_handlers.start_edit_custom_field(field_idx)
            return

        if self.ui_state.state == AppState.BOOKMARKS:
            self.bookmark_handlers.handle_bookmarks_edit()
        elif self.ui_state.state == AppState.BOOKMARK_LIST:
            self.bookmark_handlers.handle_bookmark_list_edit()
        elif self.ui_state.state == AppState.EDIT_TAB:
            self.enter_handlers.handle_edit_list_section_edit()
        elif self.ui_state.state in [AppState.TASK_LIST, AppState.PROJECT_DETAILS]:
            self.task_handlers.begin_inline_edit()

    def on_goto(self):
        """Handle go-to-source key (g) in pinned section."""
        if self._input_blocked_in_help():
            return

        def _activate_task_list_screen(list_name: str) -> None:
            task_lists = getattr(self.ui_state, "task_lists", ["Tasks"])
            if list_name not in task_lists:
                task_lists.append(list_name)
                self.ui_state.task_lists = task_lists
            self.ui_state.active_tab = task_lists.index(list_name)
            self.ui_state.state = AppState.TASK_LIST
            self.ui_state.inline_task_edit_mode = False
            self.ui_state.in_pinned_section = False

        def _find_task_path(tasks: list, target: object) -> list:
            """Return ancestor path to target (excluding target), or empty list."""
            for task in tasks:
                if task is target:
                    return []
                subtasks = getattr(task, "subtasks", None)
                if subtasks:
                    path = _find_task_path(list(subtasks), target)
                    if path is not None:
                        return [task] + path
            return None

        def _expand_task_ancestors(tasks: list, target: object) -> bool:
            """Expand all ancestor tasks for target by removing them from collapsed set."""
            path = _find_task_path(tasks, target)
            if not path:
                return False
            before = set(self.ui_state.collapsed_tasks)
            for ancestor in path:
                ancestor_id = getattr(ancestor, "id", None)
                if ancestor_id in self.ui_state.collapsed_tasks:
                    self.ui_state.collapsed_tasks.discard(ancestor_id)
            return before != self.ui_state.collapsed_tasks

        def _find_task_by_name(tasks: list, name: str) -> object | None:
            for task in tasks:
                if getattr(task, "name", None) == name:
                    return task
                subtasks = getattr(task, "subtasks", None)
                if subtasks:
                    found = _find_task_by_name(list(subtasks), name)
                    if found:
                        return found
            return None

        def _select_task_in_list(
            list_name: str,
            section_idx: int,
            task_name: str,
            task_obj: object | None = None,
        ) -> None:
            _activate_task_list_screen(list_name)
            before_collapsed = set(self.ui_state.collapsed_tasks)
            list_sections = self.manager.list_tasks.get(list_name, [])
            if 0 <= section_idx < len(list_sections):
                section_obj = list_sections[section_idx]
                section_id = section_obj.get("id") if isinstance(section_obj, dict) else getattr(section_obj, "id", None)
                if section_id:
                    self.ui_state.collapsed_tasks.discard(f"section:{section_id}")
                section_tasks = section_obj.tasks if hasattr(section_obj, "tasks") else section_obj.get("tasks", [])
                target_task = task_obj or _find_task_by_name(section_tasks, task_name)
                if target_task:
                    _expand_task_ancestors(section_tasks, target_task)
            if before_collapsed != self.ui_state.collapsed_tasks:
                self._persist_collapsed_tasks()

            layout = self.enter_handlers._build_task_list_layout()
            if not layout:
                self.ui_state.selected_index = 0
                return

            idx_map = layout.get("task_index_to_data", {})
            section_map = layout.get("index_to_section_idx", {})
            match_index = None
            for idx, (_, task, _) in idx_map.items():
                if (
                    section_map.get(idx) == section_idx
                    and ((task_obj is not None and task is task_obj) or getattr(task, "name", None) == task_name)
                ):
                    match_index = idx
                    break

            if match_index is not None:
                self.ui_state.selected_index = match_index
                return

            completed_offset = None
            for idx, (_, task, _, _, completed_section_idx) in enumerate(layout.get("all_completed_flat", [])):
                if (
                    completed_section_idx == section_idx
                    and ((task_obj is not None and task is task_obj) or getattr(task, "name", None) == task_name)
                ):
                    completed_offset = idx
                    break

            if completed_offset is None:
                self.ui_state.selected_index = 0
                return

            if layout.get("is_completed_collapsed") and layout.get("completed_header_index") is not None:
                self.ui_state.collapsed_tasks.discard("section_completed")
                layout = self.enter_handlers._build_task_list_layout()
                completed_offset = None
                for idx, (_, task, _, _, completed_section_idx) in enumerate(layout.get("all_completed_flat", [])):
                    if (
                        completed_section_idx == section_idx
                        and ((task_obj is not None and task is task_obj) or getattr(task, "name", None) == task_name)
                    ):
                        completed_offset = idx
                        break

            completed_start = layout.get("completed_items_start")
            if completed_start is None or completed_offset is None:
                self.ui_state.selected_index = 0
                return

            self.ui_state.selected_index = completed_start + completed_offset

        if self.ui_state.state == AppState.CALENDAR and self.ui_state.calendar_navigation_focus == "tasks":
            tasks = self.key_handlers._get_calendar_tasks_for_active_tab()
            task_index = self.ui_state.calendar_task_selected_index
            if 0 <= task_index < len(tasks):
                item = tasks[task_index]
                if isinstance(item, tuple):
                    if isinstance(item[0], str):
                        if item[0] == "header":
                            return
                        entry = item[1]
                    else:
                        entry = item[0]
                else:
                    entry = item

                if entry.kind == "task":
                    task_obj = entry.item
                    project_match = None
                    project_index = None
                    for project in getattr(self.manager, "projects", []):
                        expanded = _expand_task_ancestors(project.tasks, task_obj)
                        if expanded:
                            self._persist_collapsed_tasks()
                        flat_tasks = self._get_flat_tasks(project.tasks, True)
                        for idx, (_, task, _) in enumerate(flat_tasks):
                            if task is task_obj:
                                project_match = project
                                project_index = idx
                                break
                        if project_match is not None:
                            break

                    if project_match is not None:
                        self.ui_state.state = AppState.PROJECT_DETAILS
                        self.ui_state.current_project_id = project_match.id
                        self.ui_state.selected_index = project_index or 0
                        return

                    list_tasks_map = getattr(
                        self.ui_state,
                        "list_tasks",
                        getattr(self.manager, "list_tasks", {"Tasks": getattr(self.manager, "standalone_tasks", [])}),
                    )
                    from .tasks import collect_all_tasks
                    list_match = None
                    for list_name, sections in list_tasks_map.items():
                        if not sections or not isinstance(sections, list):
                            continue

                        first = sections[0]
                        looks_like_section = (
                            (isinstance(first, dict) and "tasks" in first)
                            or hasattr(first, "tasks")
                        )

                        if looks_like_section:
                            for section_idx, section in enumerate(sections):
                                section_tasks = (
                                    section.tasks if hasattr(section, "tasks") else section.get("tasks", [])
                                )
                                for task in collect_all_tasks(section_tasks):
                                    if task is task_obj:
                                        list_match = (list_name, section_idx)
                                        break
                                if list_match:
                                    break
                        else:
                            for task in collect_all_tasks(sections):
                                if task is task_obj:
                                    list_match = (list_name, 0)
                                    break

                        if list_match:
                            break

                    if list_match:
                        list_name, section_idx = list_match
                        _select_task_in_list(
                            list_name,
                            section_idx,
                            getattr(task_obj, "name", ""),
                            task_obj=task_obj,
                        )
                        return

                    self._show_status("Task not found", True)
                    return

                project = entry.item
                project_id = getattr(project, "id", None)
                if project_id is None:
                    self._show_status("Project not found", True)
                    return
                self.ui_state.state = AppState.PROJECT_BROWSER
                self.ui_state.active_tab = 0
                filtered = self.key_handlers._get_filtered_projects_sorted()
                self.ui_state.selected_index = 0
                if project in filtered:
                    self.ui_state.selected_index = filtered.index(project)
                return
            return

        if not (self.ui_state.state == AppState.MAIN_MENU and getattr(self.ui_state, "in_pinned_section", False)):
            return

        def _reset_pinned_expanded_state() -> None:
            self.ui_state.expanded_pinned_lists = set()
            self.ui_state.expanded_pinned_sections = set()
            self.ui_state.expanded_pinned_list_sections = set()

        def _select_section_header(section_idx: int) -> None:
            layout = self.enter_handlers._build_task_list_layout()
            if layout:
                header_indices = layout.get("section_header_indices", {})
                self.ui_state.selected_index = header_indices.get(section_idx, 0)
            else:
                self.ui_state.selected_index = 0

        def _goto_bookmark(item: dict) -> bool:
            from pm import Bookmark, BookmarkList

            item_type = item.get("type")
            bookmarks = self.manager.bookmarks
            item_id = item.get("id")
            target_index = None
            target_list_index = None
            target_item_index = None

            if item_type == "bookmark":
                if item_id:
                    for idx, b in enumerate(bookmarks):
                        if isinstance(b, Bookmark) and getattr(b, "id", None) == item_id:
                            target_index = idx
                            break
                if target_index is None:
                    for idx, b in enumerate(bookmarks):
                        if isinstance(b, Bookmark) and b.title == item.get("title") and b.url == item.get("url"):
                            target_index = idx
                            break
            elif item_type == "bookmark_list":
                if item_id:
                    for idx, b in enumerate(bookmarks):
                        if isinstance(b, BookmarkList) and getattr(b, "id", None) == item_id:
                            target_index = idx
                            break
                if target_index is None:
                    for idx, b in enumerate(bookmarks):
                        if isinstance(b, BookmarkList) and b.title == item.get("title"):
                            target_index = idx
                            break

            if target_index is None and item_type == "bookmark":
                if item_id:
                    for list_idx, b in enumerate(bookmarks):
                        if isinstance(b, BookmarkList):
                            for item_idx, bookmark in enumerate(b.items):
                                if getattr(bookmark, "id", None) == item_id:
                                    target_list_index = list_idx
                                    target_item_index = item_idx
                                    break
                            if target_list_index is not None:
                                break
                if target_list_index is None:
                    for list_idx, b in enumerate(bookmarks):
                        if isinstance(b, BookmarkList):
                            for item_idx, bookmark in enumerate(b.items):
                                if bookmark.title == item.get("title") and bookmark.url == item.get("url"):
                                    target_list_index = list_idx
                                    target_item_index = item_idx
                                    break
                            if target_list_index is not None:
                                break

            if target_index is not None:
                self.ui_state.state = AppState.BOOKMARKS
                self.ui_state.current_list_index = target_index if item_type == "bookmark_list" else None
                self.ui_state.selected_index = target_index
                self.ui_state.in_pinned_section = False
                return True

            if target_list_index is not None and target_item_index is not None:
                self.ui_state.state = AppState.BOOKMARK_LIST
                self.ui_state.current_list_index = target_list_index
                self.ui_state.selected_index = target_item_index
                self.ui_state.in_pinned_section = False
                return True

            return False

        _reset_pinned_expanded_state()

        pinned_idx = getattr(self.ui_state, "pinned_selected_index", 0)
        display_items = getattr(self.ui_state, "pinned_display_items", None)
        items = getattr(self.ui_state, "reordered_pinned_items", None)
        if not items:
            pinned_items = self.manager.get_pinned_items()
            pinned_projects = [p for p in pinned_items if p.get("type") == "project"]
            pinned_tasks = [p for p in pinned_items if p.get("type") in ("task", "list", "section")]
            pinned_bookmarks = [p for p in pinned_items if p.get("type") in ("bookmark", "bookmark_list")]
            items = pinned_projects + pinned_tasks + pinned_bookmarks

        target_list = display_items or items
        if not (0 <= pinned_idx < len(target_list)):
            return

        if display_items:
            entry = target_list[pinned_idx]
            kind = entry.get("kind")
            if kind in ("list_task", "section_task"):
                list_name = entry.get("list_name", "Tasks")
                section_idx = entry.get("section_idx", 0)
                list_id = entry.get("list_id")
                section_id = entry.get("section_id")
                if section_id:
                    resolved_list, resolved_idx, _ = self.manager.find_section_by_id(section_id)
                    if resolved_list:
                        list_name = resolved_list
                    if resolved_idx is not None:
                        section_idx = resolved_idx
                elif list_id:
                    resolved_name = self.manager.get_list_name_by_id(list_id)
                    if resolved_name:
                        list_name = resolved_name
                _select_task_in_list(list_name, section_idx, entry.get("task_name", ""))
                return
            if kind == "list_section":
                list_name = entry.get("list_name", "Tasks")
                section_idx = entry.get("section_idx", 0)
                list_id = entry.get("list_id")
                section_id = entry.get("section_id")
                if section_id:
                    resolved_list, resolved_idx, _ = self.manager.find_section_by_id(section_id)
                    if resolved_list:
                        list_name = resolved_list
                    if resolved_idx is not None:
                        section_idx = resolved_idx
                elif list_id:
                    resolved_name = self.manager.get_list_name_by_id(list_id)
                    if resolved_name:
                        list_name = resolved_name
                _activate_task_list_screen(list_name)
                _select_section_header(section_idx)
                return
            if kind != "pinned":
                return
            item = entry.get("item", {})
        else:
            item = target_list[pinned_idx]

        item_type = item.get("type")

        if item_type == "project":
            project_id = item.get("id")
            project = self.manager.get_project(project_id)
            if not project:
                self._show_status("Project not found", True)
                return
            self.ui_state.state = AppState.PROJECT_BROWSER
            self.ui_state.active_tab = 0
            self.ui_state.in_pinned_section = False
            filtered = self.key_handlers._get_filtered_projects_sorted()
            self.ui_state.selected_index = 0
            if project in filtered:
                self.ui_state.selected_index = filtered.index(project)
            return

        if item_type == "task":
            task_id = item.get("id")
            task_name = item.get("name", "")
            task_obj, context = self.manager.resolve_task_for_pin(
                task_id,
                task_name=task_name,
                project_id=item.get("project_id"),
                list_name=item.get("list_name"),
                section_idx=item.get("section_idx"),
            )
            if "project_id" in context:
                project = self.manager.get_project(context["project_id"])
                if not project:
                    self._show_status("Project not found", True)
                    return
                if task_obj is not None:
                    expanded = _expand_task_ancestors(project.tasks, task_obj)
                    if expanded:
                        self._persist_collapsed_tasks()
                self.ui_state.state = AppState.PROJECT_DETAILS
                self.ui_state.current_project_id = project.id
                self.ui_state.in_pinned_section = False
                flat_tasks = self._get_flat_tasks(project.tasks, True)
                match_index = None
                for idx, (_, task, _) in enumerate(flat_tasks):
                    if task_obj is not None and task is task_obj:
                        match_index = idx
                        break
                self.ui_state.selected_index = match_index if match_index is not None else 0
                return

            if "list_name" in context:
                _select_task_in_list(
                    context["list_name"],
                    context.get("section_idx", 0),
                    task_name,
                    task_obj,
                )
                return
            if task_obj is None:
                self._show_status("Task not found", True)
            return

        if item_type == "list":
            list_name = item.get("name", "Tasks")
            list_id = item.get("id")
            resolved_name = self.manager.get_list_name_by_id(list_id) if list_id else None
            if resolved_name:
                list_name = resolved_name
            _activate_task_list_screen(list_name)
            _select_section_header(0)
            return

        if item_type == "section":
            list_name = item.get("list_name", "Tasks")
            section_idx = item.get("section_idx", 0)
            section_id = item.get("id")
            if section_id:
                resolved_list, resolved_idx, _ = self.manager.find_section_by_id(section_id)
                if resolved_list:
                    list_name = resolved_list
                if resolved_idx is not None:
                    section_idx = resolved_idx
            _activate_task_list_screen(list_name)
            _select_section_header(section_idx)
            return

        if item_type in ("bookmark", "bookmark_list"):
            if not _goto_bookmark(item):
                self._show_status("Bookmark not found", True)
            return

    def on_search(self):
        """Handle search key (/) - open global search."""
        if self._input_blocked_in_help():
            return

        # Don't open search if already in search mode
        if self.ui_state.state == AppState.SEARCH:
            return

        # Save previous state to return to later
        self.ui_state.previous_state = self.ui_state.state

        # Switch to search state
        self.ui_state.state = AppState.SEARCH
        self.ui_state.search_query = ""
        self.ui_state.search_results = []
        self.ui_state.search_selected_index = 0
        self.ui_state.selected_index = 0

    def on_add(self):
        """Handle add key (a) across contexts."""
        if self._input_blocked_in_help():
            return
        state = self.ui_state.state

        if state == AppState.PROJECT_BROWSER:
            self.enter_handlers.start_add_project_form()
        elif state == AppState.PROJECT_DETAILS:
            self.enter_handlers.start_inline_task_add_for_project()
        elif state == AppState.TASK_LIST:
            layout = self.enter_handlers.build_task_list_layout()
            if not layout:
                return

            selected = self.ui_state.selected_index
            section_add_indices = layout.get("section_add_indices", {})
            target_section_idx = None

            for idx, add_idx in section_add_indices.items():
                if selected == add_idx:
                    target_section_idx = idx
                    break

            if target_section_idx is None:
                index_lookup = layout.get("index_to_section_idx", {})
                target_section_idx = index_lookup.get(selected)

            if target_section_idx is None and layout.get("all_section_data"):
                target_section_idx = layout["all_section_data"][0][0]

            if target_section_idx is None:
                return

            if layout.get("show_section_headers") and target_section_idx not in section_add_indices:
                section_idx_to_id = layout.get("section_idx_to_id", {})
                section_id = section_idx_to_id.get(target_section_idx)
                collapse_key = f"section:{section_id}"
                self.ui_state.collapsed_tasks.discard(collapse_key)
                self._persist_collapsed_tasks()
                layout = self.enter_handlers.build_task_list_layout()

            self.enter_handlers.start_inline_task_add_for_list(target_section_idx, layout)
        elif state == AppState.BOOKMARKS:
            self.ui_state.selected_index = len(self.manager.bookmarks)
            self.bookmark_handlers.handle_bookmarks_enter()
        elif state == AppState.BOOKMARK_LIST:
            self._show_status(None)
            self.ui_state.form_data = {}
            self.ui_state.form_field_index = 0
            self.ui_state.state = AppState.ADD_BOOKMARK
            self.ui_state.selected_index = 0
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
        elif state == AppState.CALENDAR:
            if self.ui_state.calendar_tasks_tab == 0 and self.ui_state.calendar_navigation_focus in (
                "tasks",
                "day",
                "prev",
                "next",
            ):
                self.key_handlers.start_inline_task_add_for_calendar()
        elif state == AppState.CUSTOMIZE_FIELDS:
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
            logger.info("Navigating to ADD_CUSTOM_FIELD via 'a' key")
        elif state == AppState.MAIN_MENU:
            if is_quick_add_enabled(self.ui_state.main_menu_tabs_selection):
                self._show_status(None)
                self.ui_state.inline_input_mode = True
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
                self.ui_state.quick_add_priority = None
                self.ui_state.quick_add_field_index = 0
                self.ui_state.selected_index = 0
                self.ui_state.quick_add_deadline = None
                self.ui_state.quick_add_deadline_component = 0
                self.ui_state.quick_add_deadline_edit_mode = False
                self.ui_state.quick_add_list = "Tasks"
                logger.info("Quick add mode activated via 'a' key")

    def on_pin(self):
        """Handle pin key (p) to toggle pin status of selected item."""
        if self._input_blocked_in_help():
            return

        state = self.ui_state.state

        # Handle pinning from MAIN_MENU when in pinned section (toggle off)
        if state == AppState.MAIN_MENU and self.ui_state.in_pinned_section:
            display_items = getattr(self.ui_state, "pinned_display_items", None)
            pinned_items = self.ui_state.reordered_pinned_items or self.manager.get_pinned_items()
            target_list = display_items or pinned_items
            if 0 <= self.ui_state.pinned_selected_index < len(target_list):
                entry = target_list[self.ui_state.pinned_selected_index]
                if display_items:
                    kind = entry.get("kind")
                    if kind != "pinned":
                        return  # Only unpin top-level pinned entries
                    item = entry.get("item", {})
                else:
                    item = entry
                item_type = item.get("type")
                if item_type == "project":
                    self.manager.toggle_pin("project", item.get("id"))
                elif item_type == "task":
                    self.manager.toggle_pin("task", item.get("id"))
                elif item_type == "bookmark":
                    self.manager.toggle_pin(
                        "bookmark",
                        {"id": item.get("id"), "title": item.get("title"), "url": item.get("url")},
                    )
                elif item_type == "bookmark_list":
                    self.manager.toggle_pin(
                        "bookmark_list",
                        {"id": item.get("id"), "title": item.get("title")},
                    )
                elif item_type == "list":
                    self.manager.toggle_pin(
                        "list",
                        {"id": item.get("id"), "name": item.get("name")},
                    )
                    expanded_lists = set(getattr(self.ui_state, "expanded_pinned_lists", set()))
                    expanded_lists.discard(item.get("id"))
                    self.ui_state.expanded_pinned_lists = expanded_lists
                elif item_type == "section":
                    section_id = {
                        "id": item.get("id"),
                        "list_id": item.get("list_id"),
                        "list_name": item.get("list_name"),
                        "section_idx": item.get("section_idx"),
                    }
                    self.manager.toggle_pin("section", section_id)
                    key = item.get("id")
                    expanded_sections = set(getattr(self.ui_state, "expanded_pinned_sections", set()))
                    expanded_sections.discard(key)
                    self.ui_state.expanded_pinned_sections = expanded_sections
                self.manager.save()
                self._show_status("Unpinned")
                new_len = len(self.manager.get_pinned_items())
                if new_len == 0:
                    self.ui_state.in_pinned_section = False
                    self.ui_state.pinned_selected_index = 0
                    max_index = self.key_handlers._get_max_index()
                    if max_index is not None:
                        self.ui_state.selected_index = max_index
                else:
                    new_display_len = max(0, len(target_list) - 1)
                    if self.ui_state.pinned_selected_index >= new_display_len:
                        self.ui_state.pinned_selected_index = max(0, new_display_len - 1)
            return

        # Handle pinning from PROJECT_BROWSER
        if state == AppState.PROJECT_BROWSER:
            from .utils import filter_projects_by_tab, sort_projects_for_display
            filtered = filter_projects_by_tab(self.manager.projects, self.ui_state.active_tab)
            filtered = sort_projects_for_display(
                filtered,
                self.ui_state.project_sort_key,
                self.manager.custom_field_definitions,
                self.ui_state.project_sort_order,
            )
            selected = self.ui_state.selected_index
            if 0 <= selected < len(filtered):
                project = filtered[selected]
                result = self.manager.toggle_pin("project", project.id)
                self.manager.save()
                if result is None:
                    self._show_status("Max 10 pinned items", is_error=True)
                elif result:
                    self._show_status("Pinned")
                else:
                    self._show_status("Unpinned")
            return

        # Handle pinning from CALENDAR (tasks section)
        if state == AppState.CALENDAR and self.ui_state.calendar_navigation_focus == "tasks":
            tasks = self.key_handlers._get_calendar_tasks_for_active_tab()
            idx = self.ui_state.calendar_task_selected_index
            if 0 <= idx < len(tasks):
                item = tasks[idx]
                # Extract actual entry (handle tuples for upcoming tab)
                if isinstance(item, tuple) and item[0] == "task":
                    entry = item[1]
                else:
                    entry = item
                if entry.kind == "project_field":
                    project = entry.item
                    project_id = getattr(project, "id", None)
                    if project_id is None:
                        return
                    result = self.manager.toggle_pin("project", project_id)
                    self.manager.save()
                    if result is None:
                        self._show_status("Max 10 pinned items", is_error=True)
                    elif result:
                        self._show_status("Pinned")
                    else:
                        self._show_status("Unpinned")
                    return
                if entry.kind == "task":
                    task = entry.item
                    # Try project-scoped tasks first
                    for project in self.manager.projects:
                        flat_tasks = self._get_flat_tasks(project.tasks, True)
                        for _, project_task, _ in flat_tasks:
                            if project_task is task:
                                task_id = getattr(task, "id", None)
                                extra_data = {
                                    "name": task.name,
                                    "completed": task.completed,
                                    "project_id": project.id,
                                    "deadline": getattr(task, "deadline", None),
                                    "priority": getattr(task, "priority", None),
                                }
                                result = self.manager.toggle_pin("task", task_id, extra_data)
                                self.manager.save()
                                if result is None:
                                    self._show_status("Max 10 pinned items", is_error=True)
                                elif result:
                                    self._show_status("Pinned")
                                else:
                                    self._show_status("Unpinned")
                                return

                    # Standalone/list tasks
                    from pm_live.tasks import collect_all_tasks
                    list_tasks_map = getattr(self.manager, "list_tasks", {}) or {}
                    for list_name, sections in list_tasks_map.items():
                        if not sections:
                            continue
                        first = sections[0]
                        looks_like_section = (
                            (isinstance(first, dict) and "tasks" in first)
                            or hasattr(first, "tasks")
                        )
                        if looks_like_section:
                            for section_idx, section in enumerate(sections):
                                section_tasks = section.tasks if hasattr(section, "tasks") else section.get("tasks", [])
                                if task in collect_all_tasks(section_tasks):
                                    task_id = getattr(task, "id", None)
                                    extra_data = {
                                        "name": task.name,
                                        "completed": task.completed,
                                        "list_name": list_name,
                                        "section_idx": section_idx,
                                        "deadline": getattr(task, "deadline", None),
                                        "priority": getattr(task, "priority", None),
                                    }
                                    result = self.manager.toggle_pin("task", task_id, extra_data)
                                    self.manager.save()
                                    if result is None:
                                        self._show_status("Max 10 pinned items", is_error=True)
                                    elif result:
                                        self._show_status("Pinned")
                                    else:
                                        self._show_status("Unpinned")
                                    return
                        else:
                            if task in collect_all_tasks(sections):
                                task_id = getattr(task, "id", None)
                                extra_data = {
                                    "name": task.name,
                                    "completed": task.completed,
                                    "list_name": list_name,
                                    "section_idx": 0,
                                    "deadline": getattr(task, "deadline", None),
                                    "priority": getattr(task, "priority", None),
                                }
                                result = self.manager.toggle_pin("task", task_id, extra_data)
                                self.manager.save()
                                if result is None:
                                    self._show_status("Max 10 pinned items", is_error=True)
                                elif result:
                                    self._show_status("Pinned")
                                else:
                                    self._show_status("Unpinned")
                                return
            return

        # Handle pinning from TASK_LIST
        if state == AppState.TASK_LIST:
            layout = self.enter_handlers.build_task_list_layout()
            if not layout:
                return
            task_index_to_data = layout.get("task_index_to_data", {})
            index_to_section_idx = layout.get("index_to_section_idx", {})
            section_header_indices = layout.get("section_header_indices", {})
            section_idx_to_id = layout.get("section_idx_to_id", {})
            all_section_data = layout.get("all_section_data", [])
            all_completed_flat = layout.get("all_completed_flat", [])
            completed_items_start = layout.get("completed_items_start")
            is_completed_collapsed = layout.get("is_completed_collapsed", False)
            selected = self.ui_state.selected_index
            list_name = layout.get("active_list_name", "Tasks")

            # Check if selected is a section header
            for section_idx, header_idx in section_header_indices.items():
                if selected == header_idx:
                    # Get section name
                    section_name = ""
                    section_id = section_idx_to_id.get(section_idx)
                    for s_idx, s_id, s_name, section_obj, _, _ in all_section_data:
                        if s_idx == section_idx:
                            section_name = s_name
                            if not section_id:
                                section_id = s_id
                            break
                    list_id = self.manager.get_list_id(list_name)
                    section_id_payload = {
                        "id": section_id,
                        "list_id": list_id,
                        "list_name": list_name,
                        "section_idx": section_idx,
                    }
                    extra_data = {"section_name": section_name or "Tasks"}
                    result = self.manager.toggle_pin("section", section_id_payload, extra_data)
                    self.manager.save()
                    if result is None:
                        self._show_status("Max 10 pinned items", is_error=True)
                    elif result:
                        self._show_status("Pinned section")
                    else:
                        self._show_status("Unpinned section")
                    return

            # Check if selected is a task
            if selected in task_index_to_data:
                task_id, task, section_tasks = task_index_to_data[selected]
                section_idx = index_to_section_idx.get(selected, 0)
                task_id = getattr(task, "id", None)
                extra_data = {
                    "name": task.name,
                    "completed": task.completed,
                    "list_name": list_name,
                    "section_idx": section_idx,
                    "deadline": getattr(task, "deadline", None),
                    "priority": getattr(task, "priority", None),
                }
                result = self.manager.toggle_pin("task", task_id, extra_data)
                self.manager.save()
                if result is None:
                    self._show_status("Max 10 pinned items", is_error=True)
                elif result:
                    self._show_status("Pinned")
                else:
                    self._show_status("Unpinned")
                return

            # Check if selected is a completed task (section/bottom modes)
            if (
                completed_items_start is not None
                and not is_completed_collapsed
                and completed_items_start <= selected < completed_items_start + len(all_completed_flat)
            ):
                idx = selected - completed_items_start
                task_id, task, _, section_tasks, section_idx = all_completed_flat[idx]
                task_id = getattr(task, "id", None)
                extra_data = {
                    "name": task.name,
                    "completed": task.completed,
                    "list_name": list_name,
                    "section_idx": section_idx,
                    "deadline": getattr(task, "deadline", None),
                    "priority": getattr(task, "priority", None),
                }
                result = self.manager.toggle_pin("task", task_id, extra_data)
                self.manager.save()
                if result is None:
                    self._show_status("Max 10 pinned items", is_error=True)
                elif result:
                    self._show_status("Pinned")
                else:
                    self._show_status("Unpinned")
            return

        # Handle pinning from PROJECT_DETAILS (tasks within project)
        if state == AppState.PROJECT_DETAILS:
            project = self.manager.get_project(self.ui_state.current_project_id)
            if not project:
                return
            flat_tasks = self._get_flat_tasks(project.tasks, True)
            selected = self.ui_state.selected_index
            if 0 <= selected < len(flat_tasks):
                # _get_flat_tasks returns tuples of (task_id, task, depth)
                _, task, _ = flat_tasks[selected]
                task_id = getattr(task, "id", None)
                extra_data = {
                    "name": task.name,
                    "completed": task.completed,
                    "project_id": project.id,
                    "deadline": getattr(task, "deadline", None),
                    "priority": getattr(task, "priority", None),
                }
                result = self.manager.toggle_pin("task", task_id, extra_data)
                self.manager.save()
                if result is None:
                    self._show_status("Max 10 pinned items", is_error=True)
                elif result:
                    self._show_status("Pinned")
                else:
                    self._show_status("Unpinned")
            return

        # Handle pinning from BOOKMARKS
        if state == AppState.BOOKMARKS:
            bookmarks = self.manager.bookmarks
            selected = self.ui_state.selected_index
            if 0 <= selected < len(bookmarks):
                from pm import Bookmark, BookmarkList
                item = bookmarks[selected]
                if isinstance(item, Bookmark):
                    result = self.manager.toggle_pin(
                        "bookmark",
                        {"id": getattr(item, "id", None), "title": item.title, "url": item.url},
                    )
                    self.manager.save()
                    if result is None:
                        self._show_status("Max 10 pinned items", is_error=True)
                    elif result:
                        self._show_status("Pinned")
                    else:
                        self._show_status("Unpinned")
                elif isinstance(item, BookmarkList):
                    extra_data = {"title": item.title, "count": len(item.items)}
                    result = self.manager.toggle_pin(
                        "bookmark_list",
                        {"id": getattr(item, "id", None), "title": item.title},
                        extra_data,
                    )
                    self.manager.save()
                    if result is None:
                        self._show_status("Max 10 pinned items", is_error=True)
                    elif result:
                        self._show_status("Pinned")
                    else:
                        self._show_status("Unpinned")
            return

        # Handle pinning from BOOKMARK_LIST (inside a list)
        if state == AppState.BOOKMARK_LIST:
            from pm import BookmarkList
            list_index = self.ui_state.current_list_index
            if list_index is not None and 0 <= list_index < len(self.manager.bookmarks):
                bookmark_list = self.manager.bookmarks[list_index]
                if isinstance(bookmark_list, BookmarkList):
                    selected = self.ui_state.selected_index
                    if 0 <= selected < len(bookmark_list.items):
                        item = bookmark_list.items[selected]
                        result = self.manager.toggle_pin(
                            "bookmark",
                            {"id": getattr(item, "id", None), "title": item.title, "url": item.url},
                        )
                        self.manager.save()
                        if result is None:
                            self._show_status("Max 10 pinned items", is_error=True)
                        elif result:
                            self._show_status("Pinned")
                        else:
                            self._show_status("Unpinned")
                    # If selected index is out of range, user is on an action item (New/Rename/Delete/Back)
                    # No pin action needed for those items
                else:
                    self._show_status("Error: Invalid list type", is_error=True)
            else:
                self._show_status("Error: Invalid list index", is_error=True)
            return

    def on_action_shortcut(self, number: int) -> None:
        """Trigger the numbered footer action when not typing."""
        if self._input_blocked_in_help():
            return
        self.key_handlers.on_action_shortcut(number)

    def on_left(self):
        """Handle left key."""
        if self._input_blocked_in_help():
            return
        if (
            self.ui_state.custom_field_date_edit_mode
            or self.ui_state.inline_input_mode
            or self.ui_state.inline_task_edit_mode
            or self.ui_state.cell_selection_mode
            or self.ui_state.cell_editing
            or self.ui_state.state == AppState.CALENDAR
        ):
            # Delegate to key_handlers for date / inline / inline-edit / cell modes
            self.key_handlers.on_left()
        elif self.ui_state.state in [AppState.PROJECT_DETAILS, AppState.TASK_LIST]:
            self.task_handlers.handle_outdent()

    def on_right(self):
        """Handle right key."""
        if self._input_blocked_in_help():
            return
        if (
            self.ui_state.custom_field_date_edit_mode
            or self.ui_state.inline_input_mode
            or self.ui_state.inline_task_edit_mode
            or self.ui_state.cell_selection_mode
            or self.ui_state.cell_editing
            or self.ui_state.state == AppState.PROJECT_BROWSER
            or self.ui_state.state == AppState.CALENDAR
        ):
            # Delegate to key_handlers for date / inline / inline-edit / cell modes, and PROJECT_BROWSER
            self.key_handlers.on_right()
        elif self.ui_state.state in [AppState.PROJECT_DETAILS, AppState.TASK_LIST]:
            self.task_handlers.handle_indent()

    def on_shift_left(self):
        """Handle Shift+Left key."""
        if self._input_blocked_in_help():
            return

    def on_shift_right(self):
        """Handle Shift+Right key."""
        if self._input_blocked_in_help():
            return

    def on_delete(self):
        """Handle delete key."""
        if self._input_blocked_in_help():
            return
        # When typing inline, Delete modifies text only.
        if self.ui_state.inline_input_mode:
            self.key_handlers.on_delete()
            return
        if self.ui_state.inline_task_edit_mode:
            return

        # Bookmark-related deletes stay here
        if self.ui_state.state == AppState.BOOKMARKS:
            self.bookmark_handlers.handle_bookmarks_delete()
            return
        if self.ui_state.state == AppState.BOOKMARK_LIST:
            self.bookmark_handlers.handle_bookmark_list_delete()
            return

        # All other delete behavior (tasks, sections, custom field options) is delegated
        # to KeyHandlers so it can branch on state appropriately.
        self.key_handlers.on_delete()

    def on_ctrl_up(self):
        """Handle Ctrl+Up key."""
        if self._input_blocked_in_help():
            return

        if self.ui_state.state == AppState.MAIN_MENU and self.ui_state.in_pinned_section:
            self._handle_pinned_move_up()
            return

        if not self.ui_state.inline_input_mode and not self.ui_state.inline_task_edit_mode:
            if self.ui_state.state == AppState.PROJECT_BROWSER:
                self._handle_project_move_up()
            elif self.ui_state.state in [AppState.PROJECT_DETAILS, AppState.TASK_LIST]:
                self.task_handlers.handle_task_move_up()
            elif self.ui_state.state == AppState.CUSTOMIZE_FIELDS:
                self._handle_field_move_up()
            elif self.ui_state.state == AppState.EDIT_TAB:
                self._handle_section_move_up()
            elif self.ui_state.state == AppState.BOOKMARKS:
                self.bookmark_handlers.handle_bookmarks_move_up()
            elif self.ui_state.state == AppState.BOOKMARK_LIST:
                self.bookmark_handlers.handle_bookmark_list_move_up()

    def on_ctrl_down(self):
        """Handle Ctrl+Down key."""
        if self._input_blocked_in_help():
            return

        if self.ui_state.state == AppState.MAIN_MENU and self.ui_state.in_pinned_section:
            self._handle_pinned_move_down()
            return

        if not self.ui_state.inline_input_mode and not self.ui_state.inline_task_edit_mode:
            if self.ui_state.state == AppState.PROJECT_BROWSER:
                self._handle_project_move_down()
            elif self.ui_state.state in [AppState.PROJECT_DETAILS, AppState.TASK_LIST]:
                self.task_handlers.handle_task_move_down()
            elif self.ui_state.state == AppState.CUSTOMIZE_FIELDS:
                self._handle_field_move_down()
            elif self.ui_state.state == AppState.EDIT_TAB:
                self._handle_section_move_down()
            elif self.ui_state.state == AppState.BOOKMARKS:
                self.bookmark_handlers.handle_bookmarks_move_down()
            elif self.ui_state.state == AppState.BOOKMARK_LIST:
                self.bookmark_handlers.handle_bookmark_list_move_down()

    def on_ctrl_left(self):
        """Handle Ctrl+Left key."""
        if self._input_blocked_in_help():
            return
        
        # Call key handlers for state-specific ctrl-left actions (e.g. calendar month navigation)
        self.key_handlers.on_ctrl_left()

        if not self.ui_state.inline_input_mode and not self.ui_state.inline_task_edit_mode:
            if self.ui_state.state == AppState.TASK_LIST:
                self.task_handlers.handle_task_move_left()

    def on_ctrl_right(self):
        """Handle Ctrl+Right key."""
        if self._input_blocked_in_help():
            return
            
        # Call key handlers for state-specific ctrl-right actions (e.g. calendar month navigation)
        self.key_handlers.on_ctrl_right()

        if not self.ui_state.inline_input_mode and not self.ui_state.inline_task_edit_mode:
            if self.ui_state.state == AppState.TASK_LIST:
                self.task_handlers.handle_task_move_right()

    def _handle_project_move_up(self):
        """Move selected project up in the list (manual reordering)."""
        # Disable manual reordering if sorting is active
        if getattr(self.ui_state, "project_sort_key", None):
            return

        filtered_projects = self.key_handlers._get_filtered_projects_sorted()
        if not filtered_projects:
            return

        selected_idx = self.ui_state.selected_index
        if selected_idx <= 0 or selected_idx >= len(filtered_projects):
            return

        project = filtered_projects[selected_idx]
        prev_project = filtered_projects[selected_idx - 1]

        # Get their global indices
        all_projects = self.manager.projects
        try:
            curr_global_idx = all_projects.index(project)
            prev_global_idx = all_projects.index(prev_project)
        except ValueError:
            return

        # Move project before the previous project
        all_projects.pop(curr_global_idx)
        # Note: If curr was before prev (unlikely in filtered view if filtered view respects order),
        # the index of prev might have shifted. But here we are moving UP, so curr is usually after prev.
        # If curr_global_idx > prev_global_idx, removing curr doesn't affect prev_global_idx.
        # If curr_global_idx < prev_global_idx (unlikely given move UP in sorted/filtered list), we need to adjust.
        # In filtered view sorted by default (order in list), curr must be after prev.
        
        all_projects.insert(prev_global_idx, project)
        
        self.manager.mark_dirty()
        self.manager.save()
        self.ui_state.selected_index -= 1

    def _handle_project_move_down(self):
        """Move selected project down in the list (manual reordering)."""
        # Disable manual reordering if sorting is active
        if getattr(self.ui_state, "project_sort_key", None):
            return

        filtered_projects = self.key_handlers._get_filtered_projects_sorted()
        if not filtered_projects:
            return

        selected_idx = self.ui_state.selected_index
        if selected_idx < 0 or selected_idx >= len(filtered_projects) - 1:
            return

        project = filtered_projects[selected_idx]
        next_project = filtered_projects[selected_idx + 1]

        # Get their global indices
        all_projects = self.manager.projects
        try:
            curr_global_idx = all_projects.index(project)
            next_global_idx = all_projects.index(next_project)
        except ValueError:
            return

        # Move project after the next project
        all_projects.pop(curr_global_idx)
        
        # We need to find the new index of next_project because popping might have shifted it
        # If curr was before next (expected), next's index decreased by 1.
        # So we want to insert AFTER next. 
        # Original next_global_idx. New next index is next_global_idx - 1.
        # We want to insert at (next_global_idx - 1) + 1 = next_global_idx.
        
        # However, it's safer to re-fetch index or just calculate carefully.
        # Case: [A, B(next), C]. Move A down.
        # curr=0, next=1.
        # pop 0 -> [B, C]. next is at 0.
        # insert at 0+1 = 1 -> [B, A, C]. Correct.
        
        # Case with hidden items: [A, H, B(next)]. Move A down.
        # curr=0, next=2.
        # pop 0 -> [H, B]. next is at 1.
        # insert at 1+1 = 2 -> [H, B, A]. Correct.
        
        if curr_global_idx < next_global_idx:
             all_projects.insert(next_global_idx, project)
        else:
             # Should not happen in consistent order, but if it does (curr > next), 
             # popping curr doesn't shift next.
             # Insert after next means index(next) + 1.
             all_projects.insert(next_global_idx + 1, project)
        
        self.manager.mark_dirty()
        self.manager.save()
        self.ui_state.selected_index += 1

    def _handle_pinned_move_up(self):
        """Move selected pinned item up within its type group."""
        display_items = getattr(self.ui_state, "pinned_display_items", [])
        if not display_items:
            return

        selected_idx = self.ui_state.pinned_selected_index
        if selected_idx < 0 or selected_idx >= len(display_items):
            return

        current_item_entry = display_items[selected_idx]
        if current_item_entry.get("kind") != "pinned":
            return  # Can only reorder top-level pinned items

        current_item = current_item_entry.get("item")
        if not current_item:
            return

        item_type = current_item.get("type")
        pinned_items = self.manager.metadata.get("pinned_items", [])
        
        # Treat bookmarks and bookmark lists as the same group
        bookmark_types = ("bookmark", "bookmark_list")
        # Treat pinned task lists and tasks as the same group
        task_types = ("task", "list", "section")
        if item_type in task_types:
            type_indices = [i for i, item in enumerate(pinned_items) if item.get("type") in task_types]
        elif item_type in bookmark_types:
            type_indices = [i for i, item in enumerate(pinned_items) if item.get("type") in bookmark_types]
        else:
            type_indices = [i for i, item in enumerate(pinned_items) if item.get("type") == item_type]
        
        try:
            current_global_idx = pinned_items.index(current_item)
        except ValueError:
            return 

        try:
            current_type_rank = type_indices.index(current_global_idx)
        except ValueError:
            return

        if current_type_rank <= 0:
            return # Already at top of its group

        # Identify swap target (the item above in the same type group)
        swap_global_idx = type_indices[current_type_rank - 1]
        swap_target_item = pinned_items[swap_global_idx]

        # Swap in metadata
        pinned_items[current_global_idx], pinned_items[swap_global_idx] = pinned_items[swap_global_idx], pinned_items[current_global_idx]
        
        self.manager.mark_metadata_modified()
        self.manager.save()

        # Update selection to follow the moved item
        target_display_idx = -1
        for i, entry in enumerate(display_items):
            if entry.get("kind") == "pinned" and entry.get("item") is swap_target_item:
                target_display_idx = i
                break
        
        if target_display_idx != -1:
            self.ui_state.pinned_selected_index = target_display_idx

    def _handle_pinned_move_down(self):
        """Move selected pinned item down within its type group."""
        display_items = getattr(self.ui_state, "pinned_display_items", [])
        if not display_items:
            return

        selected_idx = self.ui_state.pinned_selected_index
        if selected_idx < 0 or selected_idx >= len(display_items):
            return

        current_item_entry = display_items[selected_idx]
        if current_item_entry.get("kind") != "pinned":
            return

        current_item = current_item_entry.get("item")
        if not current_item:
            return

        item_type = current_item.get("type")
        pinned_items = self.manager.metadata.get("pinned_items", [])
        
        # Treat bookmarks and bookmark lists as the same group
        bookmark_types = ("bookmark", "bookmark_list")
        # Treat pinned task lists and tasks as the same group
        task_types = ("task", "list", "section")
        if item_type in task_types:
            type_indices = [i for i, item in enumerate(pinned_items) if item.get("type") in task_types]
        elif item_type in bookmark_types:
            type_indices = [i for i, item in enumerate(pinned_items) if item.get("type") in bookmark_types]
        else:
            type_indices = [i for i, item in enumerate(pinned_items) if item.get("type") == item_type]
        
        try:
            current_global_idx = pinned_items.index(current_item)
        except ValueError:
            return 

        try:
            current_type_rank = type_indices.index(current_global_idx)
        except ValueError:
            return

        if current_type_rank >= len(type_indices) - 1:
            return # Already at bottom of its group

        # Identify swap target (the item below in the same type group)
        swap_global_idx = type_indices[current_type_rank + 1]
        swap_target_item = pinned_items[swap_global_idx]

        # Swap in metadata
        pinned_items[current_global_idx], pinned_items[swap_global_idx] = pinned_items[swap_global_idx], pinned_items[current_global_idx]
        
        self.manager.mark_metadata_modified()
        self.manager.save()

        # Update selection to follow the moved item
        target_display_idx = -1
        for i, entry in enumerate(display_items):
            if entry.get("kind") == "pinned" and entry.get("item") is swap_target_item:
                target_display_idx = i
                break
        
        if target_display_idx != -1:
            self.ui_state.pinned_selected_index = target_display_idx


    def on_char(self, char: str):
        """Handle character input."""
        if self._input_blocked_in_help(allow_help=(char == 'h')):
            return

        state = getattr(self.ui_state, "state", None)
        in_text_mode = bool(
            getattr(self.ui_state, "inline_input_mode", False)
            or getattr(self.ui_state, "inline_task_edit_mode", False)
            or (state == AppState.PROJECT_BROWSER and getattr(self.ui_state, "cell_editing", False))
            or state == AppState.SEARCH
        )

        # Handle 'e' for edit when not typing.
        if char == 'e' and not in_text_mode:
            self.on_edit()
            return

        # Handle 'h' for help overlay (uppercase 'H' is also bound separately)
        if char == 'h' and not in_text_mode:
            self.on_help()
            return

        # Otherwise, delegate to key_handlers for text input
        self.key_handlers.on_char(char)

    def on_backspace(self):
        """Handle backspace."""
        if self._input_blocked_in_help():
            return
        self.key_handlers.on_backspace()

    def on_paste(self, event):
        """Handle paste from clipboard (Ctrl+V)."""
        if self._input_blocked_in_help():
            return
        logger.info(
            "Paste triggered, inline_input_mode: %s, inline_task_edit_mode: %s",
            self.ui_state.inline_input_mode,
            getattr(self.ui_state, "inline_task_edit_mode", False),
        )

        def _apply_paste(text: str):
            """Apply pasted text to the correct buffer/cursor."""
            if self.ui_state.inline_task_edit_mode and self.ui_state.inline_edit_field_index == 0:
                idx = self.ui_state.inline_edit_name_cursor
                self.ui_state.inline_edit_name = (
                    self.ui_state.inline_edit_name[:idx] + text + self.ui_state.inline_edit_name[idx:]
                )
                self.ui_state.inline_edit_name_cursor += len(text)
            elif self.ui_state.inline_task_edit_mode and self.ui_state.inline_edit_field_index == 3:
                idx = self.ui_state.inline_edit_notes_cursor
                notes = self.ui_state.inline_edit_notes or ""
                self.ui_state.inline_edit_notes = notes[:idx] + text + notes[idx:]
                self.ui_state.inline_edit_notes_cursor += len(text)
            elif self.ui_state.inline_input_mode:
                if self.ui_state.state == AppState.MAIN_MENU and self.ui_state.quick_add_field_index != 0:
                    return
                from .handlers.text_input import TextInputBuffer
                buffer, cursor = TextInputBuffer.insert(
                    self.ui_state.text_input_buffer,
                    self.ui_state.text_input_cursor,
                    text,
                )
                self.ui_state.text_input_buffer = buffer
                self.ui_state.text_input_cursor = cursor

        if not self.ui_state.inline_input_mode and not getattr(self.ui_state, "inline_task_edit_mode", False):
            return

        pasted_text = getattr(event, "data", None)
        if pasted_text:
            cleaned = pasted_text.replace("\r", "").replace("\n", "")
            if cleaned:
                _apply_paste(cleaned)
                logger.debug("Pasted text from key event data: %s", cleaned)
                return

        try:
            # Try to get clipboard data from prompt_toolkit
            clipboard_data = event.app.clipboard.get_data()
            if clipboard_data and clipboard_data.text:
                _apply_paste(clipboard_data.text)
                logger.debug("Pasted text from prompt_toolkit clipboard: %s", clipboard_data.text)
        except Exception as e:
            # Fallback to system clipboard on Windows
            logger.warning("prompt_toolkit clipboard failed, trying system clipboard: %s", e)
            try:
                import subprocess
                result = subprocess.run(
                    ['powershell', '-command', 'Get-Clipboard'],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                if result.returncode == 0 and result.stdout:
                    clipboard_text = result.stdout.strip()
                    _apply_paste(clipboard_text)
                    logger.debug("Pasted text from system clipboard: %s", clipboard_text)
            except Exception as e2:
                logger.error("System clipboard also failed: %s", e2, exc_info=True)

    def on_exit(self):
        """Handle exit."""
        if self._input_blocked_in_help():
            return
        self.key_handlers.on_exit()

    def on_today(self):
        """Handle today key (t) to jump to current date in calendar."""
        if self._input_blocked_in_help():
            return
        if self.ui_state.state == AppState.CALENDAR:
            self.key_handlers.on_today()

    def on_help(self):
        """Handle help key - toggle help overlay."""
        if self._input_blocked_in_help(allow_help=True):
            return
        # Don't show help when in inline input mode or when typing 'h' in a form
        if not self.ui_state.inline_input_mode:
            if self.ui_state.show_help:
                # Closing help overlay - reset to context-dependent mode
                self.ui_state.show_help = False
                self.ui_state.show_all_keybindings = False
            else:
                # Opening help overlay - show context-dependent keybindings
                self.ui_state.show_help = True
                # show_all_keybindings stays False for context-dependent view
        else:
            # If in inline input mode, type 'h' instead
            self.ui_state.text_input_buffer += 'h'

    # Helper methods for handlers to access
    def _get_flat_tasks(self, tasks, is_project: bool):
        """Get flattened tasks with caching."""
        # Include the identity of the task list in the cache key to support per-list task sets
        cache_key = f"{'project' if is_project else 'standalone'}_{id(tasks)}_{hash(frozenset(self.ui_state.collapsed_tasks))}"
        if cache_key not in self.ui_state._flat_tasks_cache:
            flat_tasks = []
            flatten_tasks(tasks, flat_tasks, collapsed_tasks=self.ui_state.collapsed_tasks)
            self.ui_state._flat_tasks_cache[cache_key] = flat_tasks
        return self.ui_state._flat_tasks_cache[cache_key]

    def _invalidate_task_cache(self):
        """Invalidate the task cache when tasks change."""
        self.ui_state._flat_tasks_cache.clear()

    def _get_all_fields(self):
        """Get all fields (built-in + custom) merged and sorted."""
        from .custom_fields import get_all_fields
        default_visibility = getattr(self.manager, 'default_field_visibility', {})
        custom_field_definitions = getattr(self.manager, 'custom_field_definitions', [])
        return get_all_fields(
            default_visibility,
            custom_field_definitions,
        )

    def _handle_field_move_up(self):
        """Move selected custom field up in order."""
        from .custom_fields import normalize_field_order

        fields = self.manager.custom_field_definitions
        builtin_count = 3  # timeframe, priority, area
        
        # Check if a custom field is selected
        selected_idx = self.ui_state.selected_index
        custom_start = builtin_count
        custom_end = custom_start + len(fields)
        
        if selected_idx < custom_start or selected_idx >= custom_end:
            return  # Not on a custom field
        
        # Convert to index within custom fields array
        field_idx = selected_idx - custom_start
        
        if field_idx <= 0:
            return  # Already at the top of custom fields

        # Swap with previous field
        fields[field_idx], fields[field_idx - 1] = fields[field_idx - 1], fields[field_idx]

        # Update order attributes to match new positions
        for i, field in enumerate(fields):
            field.order = i

        # Save to projects.json
        self.manager.mark_dirty()
        self.manager.save()

        # Move selection up to follow the field
        self.ui_state.selected_index = selected_idx - 1

    def _handle_field_move_down(self):
        """Move selected custom field down in order."""
        from .custom_fields import normalize_field_order

        fields = self.manager.custom_field_definitions
        builtin_count = 3  # timeframe, priority, area
        
        # Check if a custom field is selected
        selected_idx = self.ui_state.selected_index
        custom_start = builtin_count
        custom_end = custom_start + len(fields)
        
        if selected_idx < custom_start or selected_idx >= custom_end:
            return  # Not on a custom field
        
        # Convert to index within custom fields array
        field_idx = selected_idx - custom_start
        
        if field_idx >= len(fields) - 1:
            return  # Already at the bottom of custom fields

        # Swap with next field
        fields[field_idx], fields[field_idx + 1] = fields[field_idx + 1], fields[field_idx]

        # Update order attributes to match new positions
        for i, field in enumerate(fields):
            field.order = i

        # Save to projects.json
        self.manager.mark_dirty()
        self.manager.save()

        # Move selection down to follow the field
        self.ui_state.selected_index = selected_idx + 1

    def _handle_section_move_up(self):
        """Move selected section up in EDIT_TAB state."""
        # Check if we're in sectioned mode
        form_data = self.ui_state.form_data
        mode = form_data.get('mode', 'normal')
        if mode != 'sections':
            return  # Not in sectioned mode

        sections = form_data.get('sections', [])
        if not sections:
            return  # No sections to move

        # Field indices: 0=Name, 1=Color, 2=Done Section, 3=Mode, 4+=Sections
        field_idx = self.ui_state.form_field_index
        section_start = 4
        section_end = section_start + len(sections)

        # Check if a section is selected (not the "add section" button)
        if field_idx < section_start or field_idx >= section_end:
            return  # Not on a section

        # Convert to index within sections array
        section_idx = field_idx - section_start

        # Can't move up if already at the top
        if section_idx <= 0:
            return

        # Swap with previous section
        sections[section_idx], sections[section_idx - 1] = sections[section_idx - 1], sections[section_idx]

        # Move selection up to follow the section
        self.ui_state.form_field_index = field_idx - 1

        logger.info("Moved section up: %s (index %d -> %d)",
                   sections[section_idx - 1].get('name', ''), section_idx, section_idx - 1)

    def _handle_section_move_down(self):
        """Move selected section down in EDIT_TAB state."""
        # Check if we're in sectioned mode
        form_data = self.ui_state.form_data
        mode = form_data.get('mode', 'normal')
        if mode != 'sections':
            return  # Not in sectioned mode

        sections = form_data.get('sections', [])
        if not sections:
            return  # No sections to move

        # Field indices: 0=Name, 1=Color, 2=Done Section, 3=Mode, 4+=Sections
        field_idx = self.ui_state.form_field_index
        section_start = 4
        section_end = section_start + len(sections)

        # Check if a section is selected (not the "add section" button)
        if field_idx < section_start or field_idx >= section_end:
            return  # Not on a section

        # Convert to index within sections array
        section_idx = field_idx - section_start

        # Can't move down if already at the bottom
        if section_idx >= len(sections) - 1:
            return

        # Swap with next section
        sections[section_idx], sections[section_idx + 1] = sections[section_idx + 1], sections[section_idx]

        # Move selection down to follow the section
        self.ui_state.form_field_index = field_idx + 1

        logger.info("Moved section down: %s (index %d -> %d)",
                   sections[section_idx + 1].get('name', ''), section_idx, section_idx + 1)

    def _show_status(self, message: Optional[str], is_error: bool = False) -> None:
        """Update UI status feedback shared across renderers and handlers."""
        self.ui_state.status_message = message
        self.ui_state.status_is_error = is_error

    def _exit_application(self) -> None:
        """Exit the prompt_toolkit application safely."""
        application: Optional[Application] = getattr(self, "app", None)
        if application:
            logger.info("Exiting LiveCLI application")
            application.exit()

    def _initialize_console(self, width: int) -> None:
        """Create console/buffer pair and instantiate renderers."""
        self._console_buffer = StringIO()
        self._console = Console(
            file=self._console_buffer,
            force_terminal=True,
            width=width,
            legacy_windows=False,
        )
        self.renderers = {
            AppState.MAIN_MENU: MainMenuRenderer(self._console),
            AppState.PROJECT_BROWSER: ProjectBrowserRenderer(self._console),
            AppState.PROJECT_DETAILS: ProjectDetailsRenderer(self._console),
            AppState.TASK_LIST: TaskListRenderer(self._console),
            AppState.STATISTICS: StatisticsRenderer(self._console),
            AppState.CALENDAR: CalendarRenderer(self._console),
            AppState.SEARCH: SearchRenderer(self._console),
            AppState.SETTINGS: SettingsRenderer(self._console),
            AppState.QUICK_STATS_SETTINGS: QuickStatsSettingsRenderer(self._console),
            AppState.BOOKMARKS: BookmarksRenderer(self._console),
            AppState.MAIN_MENU_TABS_SETTINGS: MainMenuTabsRenderer(self._console),
            AppState.DEADLINE_SETTINGS: DeadlineSettingsRenderer(self._console),
            AppState.PROJECT_BROWSER_TAB_SETTINGS: ProjectBrowserDefaultTabRenderer(self._console),
            AppState.STATS_NONE_SETTINGS: StatsNoneSettingsRenderer(self._console),
            AppState.MESSAGE_DISPLAY_SETTINGS: MessageDisplaySettingsRenderer(self._console),
            AppState.NOTES_DISPLAY_SETTINGS: NotesDisplaySettingsRenderer(self._console),
            AppState.BOOKMARK_ACTION_SETTINGS: BookmarkActionSettingsRenderer(self._console),
            AppState.CUSTOMIZE_FIELDS: CustomFieldsRenderer(self._console),
            AppState.ADD_CUSTOM_FIELD: AddCustomFieldRenderer(self._console),
            AppState.EDIT_CUSTOM_FIELD: EditCustomFieldRenderer(self._console),
            AppState.BOOKMARK_LIST: BookmarkListRenderer(self._console),
            AppState.ADD_PROJECT: EditProjectRenderer(self._console),
            AppState.EDIT_PROJECT: EditProjectRenderer(self._console),
            AppState.CHANGE_STATUS: ChangeStatusRenderer(self._console),
            AppState.ADD_BOOKMARK: AddBookmarkRenderer(self._console),
            AppState.EDIT_BOOKMARK: EditBookmarkRenderer(self._console),
            AppState.EDIT_TAB: EditListRenderer(self._console),
            AppState.DELETE_CONFIRMATION: DeleteConfirmationRenderer(self._console),
        }
        # Help overlay renderer (not tied to a specific state)
        self.help_renderer = HelpRenderer(self._console)

    def update_console_width(self, width: int) -> None:
        """Persist and apply a new console width at runtime."""
        current_config = get_config().copy()
        current_config.console_width = width
        set_config(current_config)
        self._initialize_console(width)
        self._show_status(None)
        logger.info("Console width updated to %s", width)

    def update_quick_stats_selection(self, selection: Sequence[str]) -> None:
        """Update quick stats selection in state and config."""
        normalized = normalize_quick_stats_selection(selection)
        self.ui_state.quick_stats_selection = set(normalized)
        current_config = get_config().copy()
        current_config.quick_stats_metrics = list(normalized)
        set_config(current_config)
        logger.info("Quick stats selection updated: %s", normalized)

    def update_main_menu_tabs_selection(self, selection: Sequence[str]) -> None:
        """Update main menu tabs selection in state and config."""
        normalized = normalize_main_menu_tabs(selection)
        self.ui_state.main_menu_tabs_selection = set(normalized)
        if "tasks" not in self.ui_state.main_menu_tabs_selection:
            # Exit quick add mode if tasks tab is hidden.
            self.ui_state.inline_input_mode = False
            self.ui_state.text_input_buffer = ""
            self.ui_state.pending_section_add = False
            self.ui_state.quick_add_priority = None
        menu_items = build_main_menu_items(self.ui_state.main_menu_tabs_selection)
        total_entries = len(menu_items) + 2  # Settings and Exit
        if is_quick_add_enabled(self.ui_state.main_menu_tabs_selection):
            total_entries += 1
        max_index = max(0, total_entries - 1)
        if self.ui_state.selected_index > max_index:
            self.ui_state.selected_index = max_index
        current_config = get_config().copy()
        current_config.main_menu_tabs = list(normalized)
        set_config(current_config)
        logger.info("Main menu tabs selection updated: %s", normalized)

    def run(self):
        """Run the application."""
        logger.info("Starting LiveCLI event loop")
        self.app.run()
