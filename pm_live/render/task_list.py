"""Task list renderer."""

from rich.markup import escape as rich_escape

from .base import BaseRenderer
from ..tasks import flatten_tasks
from ..utils import format_deadline


class TaskListRenderer(BaseRenderer):
    """Renderer for the standalone task list."""

    def render(self, context: dict) -> str:
        """Render standalone task list."""
        self._reset_console_buffer()

        manager = context['manager']
        selected_index = context['selected_index']
        active_tab = context['active_tab']
        task_lists = context.get('task_lists', ["Tasks"])
        inline_input_mode = context.get('inline_input_mode', False)
        text_input_buffer = context.get('text_input_buffer', '')
        text_input_cursor = context.get('text_input_cursor', len(text_input_buffer))
        inline_task_edit_mode = context.get('inline_task_edit_mode', False)
        inline_edit_task = context.get('inline_edit_task')
        inline_edit_task_id = context.get('inline_edit_task_id')
        inline_edit_field_index = context.get('inline_edit_field_index', 0)
        inline_edit_deadline_component = context.get('inline_edit_deadline_component', 0)
        inline_edit_name = context.get('inline_edit_name', '')
        inline_edit_name_cursor = context.get('inline_edit_name_cursor', len(inline_edit_name))
        inline_edit_deadline = context.get('inline_edit_deadline')
        inline_edit_priority = context.get('inline_edit_priority')
        inline_edit_notes = context.get('inline_edit_notes')
        inline_edit_notes_cursor = context.get('inline_edit_notes_cursor', 0)
        collapsed_tasks = context.get('collapsed_tasks', set())

        self._console.print("\n[bold]Tasks[/bold]\n")

        # Tabs - dynamic lists (default: one "Tasks" list)
        tab_line_parts = []
        list_metadata = manager.list_metadata
        for i, tab_name in enumerate(task_lists):
            if i == active_tab:
                # Get custom color for this list, default to white
                tab_color = list_metadata.get(tab_name, {}).get("color", "white")
                tab_line_parts.append(f"[bold {tab_color} reverse] {tab_name} [/bold {tab_color} reverse]")
            else:
                tab_line_parts.append(f"[color(245)] {tab_name} [/color(245)]")
            if i < len(task_lists) - 1:
                tab_line_parts.append(" ")
        tabs_line = "  " + "".join(tab_line_parts)
        self._console.print(f"{tabs_line}\n")

        # Determine sections for the active list
        list_tasks_map = context.get('list_tasks', {"Tasks": manager.standalone_tasks})
        active_list_name = task_lists[active_tab] if 0 <= active_tab < len(task_lists) else "Tasks"

        # Handle both old format (list of tasks) and new format (list of sections)
        sections_for_list = list_tasks_map.get(active_list_name, [])

        # Legacy format: direct list of Task objects (not sections)
        if sections_for_list:
            first = sections_for_list[0]
            looks_like_section = (
                (isinstance(first, dict) and 'tasks' in first)
                or hasattr(first, 'tasks')
            )
            if not looks_like_section:
                default_section = type('Section', (), {'name': '', 'tasks': sections_for_list})()
                sections_for_list = [default_section]

        # Flatten tasks from all sections, tracking section context
        all_section_data = []  # List of (section_id, section_name, pending_flat, completed_flat)
        current_index = 0

        # Track indices for navigation
        section_indices = {}  # section_name -> (header_index, items_start, items_end)

        # Check done display mode
        done_mode = list_metadata.get(active_list_name, {}).get("show_done_section", "section")
        # Handle legacy boolean values
        if isinstance(done_mode, bool):
            done_mode = "section" if done_mode else "inline"
        # Validate
        from pm import DONE_DISPLAY_OPTIONS
        if done_mode not in DONE_DISPLAY_OPTIONS:
            done_mode = "section"

        for section in sections_for_list:
            section_id = section.get("id") if isinstance(section, dict) else getattr(section, "id", None)
            section_name = section.name if hasattr(section, 'name') else section.get('name', '')
            section_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])

            # Flatten tasks in this section
            flat_for_section = []
            flatten_tasks(section_tasks, flat_for_section, collapsed_tasks=collapsed_tasks)

            # Split into pending and completed for "section" and "bottom" modes
            # Keep tasks in original order for "inline" mode
            if done_mode in ["section", "bottom"]:
                pending = [(task_id, task, depth) for task_id, task, depth in flat_for_section if task.completed is None]
                completed = [(task_id, task, depth) for task_id, task, depth in flat_for_section if task.completed is not None]
            else:  # "inline"
                # Keep all tasks in original order, don't separate completed ones
                pending = flat_for_section
                completed = []

            all_section_data.append((section_id, section_name, pending, completed))

        # Separate out completed tasks (they go to special section)
        # Store as (task_id, task, depth, section_idx) to preserve section context for pin checking
        all_completed_tasks = []
        for section_idx, (section_id, section_name, pending, completed) in enumerate(all_section_data):
            for task_id, task, depth in completed:
                all_completed_tasks.append((task_id, task, depth, section_idx))

        # Helper to render a single task
        def render_task(task_id, task, depth, selected_index, current_index, is_completed=False, section_idx=0):
            """Render a single task."""
            indent = "  " * (depth + 1)
            metadata_color = "color(238)" if is_completed else "color(243)"
            if is_completed:
                # Use same colors as projects for completed tasks
                dim_color = "color(238)"
                if task.completed is True:
                    checkbox = f"[{dim_color}]✓[/{dim_color}]"
                else:
                    checkbox = f"[{dim_color}]✗[/{dim_color}]"
                task_text = f"[{dim_color}]{task.name}[/{dim_color}]"
            else:
                checkbox = "[color(245)]○[/color(245)]"
                task_text = f"[white]{task.name}[/white]"

            # Prepare metadata (priority and deadline)
            from ..config import get_config
            config = get_config()

            metadata_parts = []
            if task.priority:
                metadata_parts.append(task.priority)
            if task.deadline:
                deadline_text = format_deadline(task.deadline).strip()
                metadata_parts.append(deadline_text)

            # Task text with metadata on same line
            task_text_with_metadata = task_text
            if metadata_parts:
                metadata_content = " ".join(metadata_parts)
                task_text_with_metadata = f"{task_text} [{metadata_color}]{metadata_content}[/{metadata_color}]"

            # Indicate collapsed subtree if applicable
            collapse_indicator = ""
            if task.subtasks and getattr(task, "id", None) in collapsed_tasks:
                collapse_indicator = " [color(243)]⌵[/color(243)]"

            # Inline edit mode replaces task text/metadata with editable fields
            is_inline_edit_target = inline_task_edit_mode and (
                task is inline_edit_task or getattr(task, "id", None) == inline_edit_task_id
            )
            if is_inline_edit_target:
                selector = "[color(238)]›[/color(238)] " if current_index == selected_index else "  "
                name_display = self.build_inline_name_display(
                    inline_edit_name, inline_edit_field_index, inline_edit_name_cursor
                )
                priority_display = self.build_inline_priority_display(
                    inline_edit_priority, inline_edit_field_index
                )
                deadline_display = self.build_inline_deadline_display(
                    inline_edit_deadline, inline_edit_field_index, inline_edit_deadline_component
                )
                self._console.print(
                    f"{selector}{indent}{checkbox} {name_display}  {priority_display}  {deadline_display}{collapse_indicator}"
                )

                # Add notes line below
                notes_display = self.build_inline_notes_display(
                    inline_edit_notes, inline_edit_field_index, inline_edit_notes_cursor
                )
                notes_indent = "  " + indent  # Align with status icon
                self._console.print(f"{notes_indent}{notes_display}")
                return

            selector = "[white]›[/white] " if current_index == selected_index else "  "
            self._console.print(f"{selector}{indent}{checkbox} {task_text_with_metadata}{collapse_indicator}")

            # Display notes line based on notes_display_mode setting
            notes_value = getattr(task, "notes", None)
            if notes_value and not is_completed:
                show_notes = False
                if config.notes_display_mode == "always":
                    show_notes = True
                elif config.notes_display_mode == "dynamic" and current_index == selected_index:
                    show_notes = True

                if show_notes:
                    notes_indent = "  " + indent  # Align with status icon
                    escaped_notes = rich_escape(notes_value)
                    self._console.print(f"{notes_indent}[color(238)]{escaped_notes}[/color(238)]")

            # Metadata is shown on same line with task name (see above)

        # Render sections with headers (only show section headers if list has multiple named sections)
        current_index = 0
        show_section_headers = len(all_section_data) > 1 or (len(all_section_data) == 1 and all_section_data[0][1])

        for section_idx, (section_id, section_name, pending, completed) in enumerate(all_section_data):
            # Show section header if we have multiple sections or a named section
            if show_section_headers:
                # Blank line between sections (non-selectable)
                if section_idx > 0:
                    self._console.print("")

                section_collapse_key = f"section:{section_id}"
                is_section_collapsed = section_collapse_key in collapsed_tasks
                collapse_indicator = " [color(243)]⌵[/color(243)]" if is_section_collapsed else ""
                header_selector = "[white]›[/white] " if selected_index == current_index else "  "
                self._console.print(f"{header_selector}[bold]{section_name if section_name else 'Tasks'}[/bold]{collapse_indicator}")
                current_index += 1

                # Show tasks only if section is not collapsed
                if not is_section_collapsed:
                    # Render tasks (in original order when Done section is disabled)
                    for task_id, task, depth in pending:
                        # Auto-detect completion status
                        is_completed = task.completed is not None
                        render_task(task_id, task, depth, selected_index, current_index, is_completed=is_completed, section_idx=section_idx)
                        current_index += 1

                    # Add + button for this section
                    add_selector = "[white]›[/white] " if selected_index == current_index else "  "
                    if inline_input_mode and selected_index == current_index:
                        display_value = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                        self._console.print(f"{add_selector}  [color(245)]+[/color(245)] {display_value}")
                    else:
                        self._console.print(f"{add_selector}  [color(245)]+[/color(245)]")
                    current_index += 1
            else:
                # No section headers, just render tasks directly (in original order when Done section is disabled)
                for task_id, task, depth in pending:
                    # Auto-detect completion status
                    is_completed = task.completed is not None
                    render_task(task_id, task, depth, selected_index, current_index, is_completed=is_completed, section_idx=section_idx)
                    current_index += 1

        # Add New Task (only when not showing section headers - single + button for normal lists)
        if not show_section_headers:
            add_selector = "[white]›[/white] " if selected_index == current_index else "  "
            if inline_input_mode and selected_index == current_index:
                display_value = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                self._console.print(f"{add_selector}  [color(245)]+[/color(245)] {display_value}\n")
            else:
                self._console.print(f"{add_selector}  [color(245)]+[/color(245)]\n")
            current_index += 1
        else:
            # Add blank line after sections (non-selectable, does not advance index)
            self._console.print()

        # Render completed tasks based on done_mode
        if done_mode == "section":
            # Show Done section with header and collapse functionality
            completed_header_index = current_index
            is_completed_collapsed = "section_completed" in collapsed_tasks
            done_arrow = "[color(238)]▸[/color(238)]" if is_completed_collapsed else "[color(243)]▾[/color(243)]"
            header_selector = "[white]›[/white] " if selected_index == completed_header_index else "  "
            self._console.print(f"{header_selector}{done_arrow} [color(243)]Done[/color(243)]")

            # Completed tasks list (shown only when expanded)
            current_index = completed_header_index + 1
            if not is_completed_collapsed:
                for task_id, task, depth, section_idx in all_completed_tasks:
                    render_task(task_id, task, depth, selected_index, current_index, is_completed=True, section_idx=section_idx)
                    current_index += 1
        elif done_mode == "bottom":
            # Render completed tasks at bottom without section header
            for task_id, task, depth, section_idx in all_completed_tasks:
                render_task(task_id, task, depth, selected_index, current_index, is_completed=True, section_idx=section_idx)
                current_index += 1
        # else: "inline" mode - completed tasks already rendered inline with pending tasks above

        # Pad to push actions to bottom
        self._pad_to_bottom()

        # Determine if we can edit the current list (not the default "Tasks" tab)
        can_edit_list = active_tab > 0 and active_tab < len(task_lists)

        new_list_index = current_index
        if selected_index == new_list_index:
            if inline_input_mode:
                display_value = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                self._console.print(f"  [white]›[/white] [green]+[/green] New List: {display_value}")
            else:
                self._console.print("  [white]›[/white] [green]+[/green] New List")
        else:
            self._console.print("    [color(245)]+[/color(245)] [color(245)]New List[/color(245)]")

        # Edit list (only for non-default tabs)
        actions_start = new_list_index + 1
        if can_edit_list:
            edit_list_index = actions_start
            if selected_index == edit_list_index:
                self._console.print("  [white]›[/white] [cyan]✎[/cyan] Edit List")
            else:
                self._console.print("    [color(245)]✎[/color(245)] [color(245)]Edit List[/color(245)]")
            back_index = edit_list_index + 1
        else:
            back_index = actions_start

        # Back to Main Menu
        if selected_index == back_index:
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Back")
        else:
            self._console.print("    [color(245)]←[/color(245)] [color(245)]Back[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()
