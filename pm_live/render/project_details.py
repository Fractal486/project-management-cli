"""Project details renderer."""

import re

from rich.markup import escape as rich_escape

from .base import BaseRenderer
from ..utils import (
    get_status_icon, get_status_color, get_level_color, format_deadline,
    render_progress_bar, format_currency_value
)
from ..tasks import flatten_tasks
from ..custom_fields import get_all_fields
from ..config import get_config


def _strip_markup(text: str) -> str:
    """Remove Rich markup tags to get plain text length."""
    return re.sub(r'\[/?[^\]]*\]', '', text)


class ProjectDetailsRenderer(BaseRenderer):
    """Renderer for project details with tasks."""

    def render(self, context: dict) -> str:
        """Render project details with tasks."""
        self._reset_console_buffer()
        
        manager = context['manager']
        current_project_id = context['current_project_id']
        selected_index = context['selected_index']
        inline_input_mode = context.get('inline_input_mode', False)
        text_input_buffer = context.get('text_input_buffer', '')
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
        
        project = manager.get_project(current_project_id)
        if not project:
            self._console.print("[red]Project not found[/red]")
            return self._get_console_output()

        status_color = get_status_color(project.status)
        status_icon = get_status_icon(project.status)

        total = project.count_total_tasks()
        completed = project.count_completed_tasks()
        percentage = project.progress_percentage()

        # Gather all fields first to calculate box width
        all_fields = context.get("all_fields") or get_all_fields(
            manager.default_field_visibility, manager.custom_field_definitions
        )
        
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
        visible_fields = visible_builtin_fields + visible_custom_fields

        cfg = get_config()
        show_none = getattr(cfg, "show_none_in_stats", True)

        def _format_custom_field_value(field, value):
            """Format custom field values for display."""
            if field.field_type == "single_select":
                if value in (None, "", "none", "None"):
                    return "[color(238)]-[/color(238)]" if show_none else None
                if field.select_options:
                    option = next((opt for opt in field.select_options if opt.value == value), None)
                    if option and option.color:
                        return f"[{option.color}]{value}[/{option.color}]"
                return str(value)

            if value is None or value == "":
                return "[color(238)]-[/color(238)]" if show_none else None

            if field.field_type == "number":
                if field.number_format == "currency":
                    return format_currency_value(value, field.currency_symbol)
                if field.number_format == "percentage":
                    return f"{value}%"
                return str(value)

            if field.field_type == "date":
                return f"[white]{value}[/white]"

            return str(value)

        # Build field parts
        field_parts = []
        field_parts_plain = []
        for field in visible_fields:
            value = project.custom_field_values.get(field.key, getattr(project, field.key, None))
            formatted_value = _format_custom_field_value(field, value)
            if formatted_value is None:
                continue
            field_parts.append(f"[color(245)]{field.label}:[/color(245)] {formatted_value}")
            field_parts_plain.append(f"{field.label}: {_strip_markup(formatted_value)}")

        # Calculate content widths
        name_line = f"  {status_icon}  {project.name}"
        desc_line = f"     {project.description}" if project.description else ""
        
        bar = render_progress_bar(percentage, width=12) if total > 0 else ""
        progress_line = f"     {bar}  {completed}/{total}  ({percentage}%)" if total > 0 else "     No tasks yet"
        
        fields_line = "     " + "  ·  ".join(field_parts_plain) if field_parts_plain else ""
        
        # Find max width
        content_widths = [len(name_line), len(progress_line)]
        if desc_line:
            content_widths.append(len(desc_line))
        if fields_line:
            content_widths.append(len(fields_line))
        
        box_width = max(content_widths) + 4  # padding
        box_width = max(box_width, 30)  # minimum width

        # Helper to print a line with only a left border and padded content
        def print_box_line(content_plain: str, content_rich: str):
            padding = box_width - len(content_plain)
            self._console.print(f"  [color(238)]│[/color(238)]{content_rich}{' ' * max(0, padding)}")

        # Render box
        self._console.print()
        self._console.print(f"  [color(238)]┌[/color(238)]")
        
        # Name line
        name_content = f"  [{status_color}]{status_icon}[/{status_color}]  [bold white]{project.name}[/bold white]"
        name_plain = f"  {status_icon}  {project.name}"
        print_box_line(name_plain, name_content)
        
        # Description
        if project.description:
            desc_content = f"     [color(243)]{project.description}[/color(243)]"
            desc_plain = f"     {project.description}"
            print_box_line(desc_plain, desc_content)
        
        # Progress
        if total > 0:
            bar_width = 12
            filled = int((percentage / 100) * bar_width)
            empty = bar_width - filled
            bar_rich = f"[color(245)]{'▬' * filled}[/color(245)][color(238)]{'▭' * empty}[/color(238)]"
            progress_content = f"  {bar_rich}  [color(245)]{completed}/{total}[/color(245)]  [color(243)]({percentage}%)[/color(243)]"
            progress_plain = f"  {bar}  {completed}/{total}  ({percentage}%)"
            print_box_line(progress_plain, progress_content)
        else:
            print_box_line("  No tasks yet", "  [color(243)]No tasks yet[/color(243)]")
        
        # Fields
        if field_parts:
            print_box_line("", "")  # Empty line
            fields_content = "  " + "   ".join(field_parts)
            fields_plain = "  " + "   ".join(field_parts_plain)
            print_box_line(fields_plain, fields_content)
        
        self._console.print(f"  [color(238)]└[/color(238)]")
        self._console.print()

        # Flatten tasks (show all in one list)
        all_flat_tasks = []
        flatten_tasks(project.tasks, all_flat_tasks, collapsed_tasks=collapsed_tasks)

        # Render tasks
        inline_add_mode = inline_task_edit_mode and inline_edit_task_id is None
        if not all_flat_tasks:
            self._console.print("     [color(243)]No tasks yet[/color(243)]")
        else:
            for i, (task_id, task, depth) in enumerate(all_flat_tasks):
                indent = "  " * depth
                dim_color = "color(238)"
                metadata_color = dim_color if task.completed is not None else "color(243)"

                if task.completed is True:
                    checkbox = f"[{dim_color}]✓[/{dim_color}]"
                    base_text = f"[{dim_color}]{task.name}[/{dim_color}]"
                elif task.completed is False:
                    checkbox = f"[{dim_color}]✗[/{dim_color}]"
                    base_text = f"[{dim_color}]{task.name}[/{dim_color}]"
                else:
                    checkbox = "[color(245)]○[/color(245)]"
                    base_text = f"[white]{task.name}[/white]"

                # Prepare metadata (priority and deadline)
                config = get_config()

                metadata_parts = []
                if task.priority:
                    metadata_parts.append(f"[{metadata_color}]{task.priority}[/{metadata_color}]")
                if task.deadline:
                    deadline_text = format_deadline(task.deadline).strip()
                    metadata_parts.append(f"[{metadata_color}]{deadline_text}[/{metadata_color}]")

                # Task text with metadata on same line
                task_text = base_text
                if metadata_parts:
                    metadata_content = " ".join(metadata_parts)
                    task_text = f"{task_text}  {metadata_content}"

                # Indicate collapsed subtree if applicable
                collapse_indicator = ""
                if task.subtasks and getattr(task, "id", None) in collapsed_tasks:
                    collapse_indicator = " [color(243)]⌵[/color(243)]"

                # Inline edit mode: render editable fields inline
                is_inline_edit_target = inline_task_edit_mode and (
                    task is inline_edit_task or getattr(task, "id", None) == inline_edit_task_id
                )
                if is_inline_edit_target:
                    # When adding a brand-new task, render the inline fields on the add line instead of a separate row
                    if inline_add_mode:
                        continue
                    selector = "[color(238)]›[/color(238)] " if i == selected_index else "  "
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
                        f"  {selector}  {indent}{checkbox} {name_display}  {priority_display}  {deadline_display}{collapse_indicator}"
                    )

                    # Add notes line below
                    notes_display = self.build_inline_notes_display(
                        inline_edit_notes, inline_edit_field_index, inline_edit_notes_cursor
                    )
                    notes_indent = "  " + "    " + indent  # Align with status icon
                    self._console.print(f"{notes_indent}{notes_display}")
                    continue

                if i == selected_index:
                    selector = "[white]›[/white]"
                else:
                    selector = " "
                self._console.print(f"  {selector}   {indent}{checkbox} {task_text}{collapse_indicator}")

                # Display notes line based on notes_display_mode setting
                notes_value = getattr(task, "notes", None)
                if notes_value:
                    show_notes = False
                    if config.notes_display_mode == "always":
                        show_notes = True
                    elif config.notes_display_mode == "dynamic" and i == selected_index:
                        show_notes = True

                    if show_notes:
                        notes_indent = "  " + "    " + indent  # Align with status icon
                        escaped_notes = rich_escape(notes_value)
                        self._console.print(f"{notes_indent}[color(238)]{escaped_notes}[/color(238)]")

                # Metadata is shown on same line with task name (see above)

        self._console.print()

        # Add New Task option (with inline input when in mode) - skip if selected_index is -1
        add_index = len(all_flat_tasks)
        if selected_index >= 0:
            if inline_add_mode:
                # Use the add line itself for the inline fields (mirrors task list inline add)
                selected_for_add = selected_index in (add_index, max(0, add_index - 1))
                add_selector = "[white]›[/white]" if selected_for_add else " "
                name_display = self.build_inline_name_display(
                    inline_edit_name, inline_edit_field_index, inline_edit_name_cursor
                )
                priority_display = self.build_inline_priority_display(
                    inline_edit_priority, inline_edit_field_index
                )
                deadline_display = self.build_inline_deadline_display(
                    inline_edit_deadline, inline_edit_field_index, inline_edit_deadline_component
                )
                self._console.print(f"  {add_selector}   [green]+[/green] {name_display}  {priority_display}  {deadline_display}")

                # Add notes line below for inline add
                notes_display = self.build_inline_notes_display(
                    inline_edit_notes, inline_edit_field_index, inline_edit_notes_cursor
                )
                self._console.print(f"      {notes_display}")
            elif selected_index == add_index:
                self._console.print(f"  [white]›[/white]   [green]+[/green] [color(245)]Add task[/color(245)]")
            else:
                self._console.print(f"      [green]+[/green] [color(245)]Add task[/color(245)]")

            self._console.print()

        # Pad to push actions to bottom (only in interactive mode)
        if selected_index >= 0:
            self._pad_to_bottom()

        # Actions with cleaner styling (skip if selected_index is -1, e.g., when called from command line)
        if selected_index >= 0:
            actions = [
                ("Status", "↻", "cyan"),
                ("Edit", "✎", "cyan"),
                ("Back", "←", "yellow")
            ]

            current_index = add_index + 1
            for i, (action, icon, icon_color) in enumerate(actions):
                action_idx = current_index + i
                if selected_index == action_idx:
                    self._console.print(f"  [white]›[/white] [{icon_color}]{icon}[/{icon_color}] {action}")
                else:
                    self._console.print(f"    [color(245)]{icon}[/color(245)] [color(245)]{action}[/color(245)]")

        # Only render status message if not in inline input mode (avoid duplicate error messages)
        if not inline_input_mode:
            self._render_status_message(context)
        return self._get_console_output()
