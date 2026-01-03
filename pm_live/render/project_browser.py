"""Project browser renderer."""

from rich.table import Table
from rich import box

from .base import BaseRenderer
from ..utils import (
    get_status_icon, get_status_color, get_level_color,
    filter_projects_by_tab, sort_projects_for_display,
    render_progress_bar, format_currency_value
)


class ProjectBrowserRenderer(BaseRenderer):
    """Renderer for the project browser."""

    def render(self, context: dict) -> str:
        """Render the project browser with tabs."""
        self._reset_console_buffer()

        manager = context['manager']
        selected_index = context['selected_index']
        active_tab = context['active_tab']

        # Check if progress column is visible
        default_visibility = context.get('default_field_visibility', {})
        progress_visible = default_visibility.get("progress", True)

        # Cell selection mode state
        cell_selection_mode = context.get('cell_selection_mode', False)
        cell_selected_column = context.get('cell_selected_column', 0)
        cell_editing = context.get('cell_editing', False)
        cell_edit_buffer = context.get('cell_edit_buffer', '')
        cell_edit_date_buffer = context.get('cell_edit_date_buffer')
        cell_edit_date_component = context.get('cell_edit_date_component', 0)
        header_row_selected = (selected_index == -1)
        header_active_column = cell_selected_column if header_row_selected and cell_selection_mode else None
        sort_key = context.get('project_sort_key')
        sort_order = context.get('project_sort_order')

        self._console.print("\n[bold white]PROJECTS[/bold white]\n")

        # Tabs - order based on config
        from ..config import get_config
        config = get_config()
        if config.project_browser_default_tab == "active":
            tabs = ["Active", "Done", "All"]
        else:
            tabs = ["All", "Active", "Done"]
        tab_line_parts = []
        for i, tab_name in enumerate(tabs):
            if i == active_tab:
                tab_line_parts.append(f"[bold white reverse] {tab_name} [/bold white reverse]")
            else:
                tab_line_parts.append(f"[color(245)] {tab_name} [/color(245)]")
            if i < len(tabs) - 1:
                tab_line_parts.append(" ")
        self._console.print("  " + "".join(tab_line_parts))
        self._console.print()

        # Filter projects
        filtered_projects = filter_projects_by_tab(manager.projects, active_tab)

        # Get all fields (built-in + custom)
        all_fields = context.get('all_fields') or []

        # Split fields so built-ins (timeframe/priority/area) always appear before custom fields
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

        # Apply sorting based on the active header
        filtered_projects = sort_projects_for_display(filtered_projects, sort_key, all_fields, sort_order)

        def format_header(label: str, key: str, col_idx: int) -> str:
            """Format header label with selection and sort indicators."""
            if sort_key == key and sort_order:
                arrow = "↑" if sort_order == "asc" else "↓"
                # Only show label + arrow if label has meaningful text (not just placeholder like "·")
                text = f"{label} {arrow}" if label and label != "·" else arrow
            else:
                text = label
            if header_row_selected and header_active_column == col_idx:
                return f"[on color(235)][color(250)]{text}[/color(250)][/on color(235)]"
            return f"[color(245)]{text}[/color(245)]"

        # Header indicator in the selector column
        if header_row_selected:
            selector_header = "[color(243)]›[/color(243)]" if cell_selection_mode else "[white]›[/white]"
        else:
            selector_header = ""

        # Create table - minimal style with no borders
        table = Table(
            box=None,
            show_header=True,
            header_style="",
            border_style="color(238)",
            padding=(0, 2),
        )

        # Fixed left columns
        table.add_column(selector_header, width=1, no_wrap=True)
        col_idx = 0
        table.add_column(format_header("·", "__status__", col_idx), justify="center", width=1, no_wrap=True)
        col_idx += 1
        table.add_column(format_header("Name", "__name__", col_idx), no_wrap=True)
        col_idx += 1

        # Add visible field columns in required order (built-ins first, then custom)
        for field in visible_fields:
            table.add_column(format_header(field.label, field.key, col_idx), no_wrap=True)
            col_idx += 1

        # Fixed right column (if visible)
        progress_col_idx = col_idx if progress_visible else None
        if progress_visible:
            table.add_column(format_header("Progress", "__progress__", col_idx), no_wrap=True)

        # Empty state
        if not filtered_projects:
            self._console.print(table)
            self._console.print("\n    [color(243)]No projects yet[/color(243)]\n")
        else:
            # Add separator row after header
            separator_row = ["", "", ""]
            for field in visible_fields:
                separator_row.append("")
            if progress_visible:
                separator_row.append("")
            table.add_row(*separator_row)
            
            # Populate table rows
            for i, project in enumerate(filtered_projects):
                is_selected_row = (i == selected_index)

                # Cursor: bright cyan when normal, dimmed when in cell selection mode
                if is_selected_row:
                    if cell_selection_mode:
                        selector = "[color(243)]›[/color(243)]"
                    else:
                        selector = "[white]›[/white]"
                else:
                    selector = " "
                status_icon = get_status_icon(project.status)
                status_color = get_status_color(project.status)

                # Check if status column (col 0) is selected/editing
                is_status_selected = is_selected_row and cell_selection_mode and cell_selected_column == 0
                is_status_editing = is_status_selected and cell_editing

                # Check if name column (col 1) is selected/editing
                is_name_selected = is_selected_row and cell_selection_mode and cell_selected_column == 1
                is_name_editing = is_name_selected and cell_editing

                # Format status column
                if is_status_editing:
                    status_display = f"[reverse]{status_icon}[/reverse]"
                elif is_status_selected:
                    status_display = f"[on color(235)][{status_color}]{status_icon}[/{status_color}][/on color(235)]"
                elif is_selected_row:
                    status_display = f"[{status_color}]{status_icon}[/{status_color}]"
                else:
                    status_display = f"[color(240)]{status_icon}[/color(240)]"

                # Format name column
                if is_name_editing:
                    display_value = BaseRenderer.build_text_input_display(cell_edit_buffer, len(cell_edit_buffer))
                    name_display = f"[green]{display_value}[/green]"
                elif is_name_selected:
                    name_display = f"[on color(235)][bold]{project.name}[/bold][/on color(235)]"
                elif is_selected_row:
                    name_display = f"[bold white]{project.name}[/bold white]"
                else:
                    name_display = f"[color(245)]{project.name}[/color(245)]"

                # Build row data
                row_data = [
                    selector,
                    status_display,
                    name_display,
                ]

                # Add field values with cell selection/editing support
                # Custom fields start at column 2 (0=status, 1=name)
                for col_idx, field in enumerate(visible_fields):
                    value = project.get_field_value(field.key)
                    actual_col_idx = col_idx + 2  # Offset for status and name columns
                    is_cell_selected = is_selected_row and cell_selection_mode and actual_col_idx == cell_selected_column
                    is_cell_editing = is_cell_selected and cell_editing

                    if is_cell_editing:
                        # Render editing UI based on field type
                        cell_value = self._format_editing_cell(
                            value, field, cell_edit_buffer,
                            cell_edit_date_buffer, cell_edit_date_component
                        )
                    elif is_cell_selected:
                        # Highlight selected cell with subtle gray background
                        base_value = self._format_custom_field_value(value, field, dimmed=(not is_selected_row))
                        cell_value = f"[on color(235)]{base_value}[/on color(235)]"
                    else:
                        cell_value = self._format_custom_field_value(value, field, dimmed=(not is_selected_row))
                    row_data.append(cell_value)

                # Add progress column with a compact progress bar (if visible)
                if progress_visible:
                    is_progress_selected = (
                        is_selected_row and cell_selection_mode and cell_selected_column == progress_col_idx
                    )
                    if not project.tasks:
                        value = "[color(235)]-[/color(235)]"
                    else:
                        percentage = project.progress_percentage()
                        # Use medium-weight characters for subtle but visible bars (same as pinned projects)
                        filled = int((percentage / 100) * 6)
                        empty = 6 - filled
                        if is_selected_row:
                            filled_color = "color(245)"
                            empty_color = "color(238)"
                        else:
                            filled_color = "color(240)"
                            empty_color = "color(237)"
                        bar = f"[{filled_color}]{'▬' * filled}[/{filled_color}][{empty_color}]{'▭' * empty}[/{empty_color}]"
                        value = bar

                    if is_progress_selected:
                        row_data.append(f"[on color(235)]{value}[/on color(235)]")
                    else:
                        row_data.append(value)

                # Apply continuous row background when selected (not in cell selection mode)
                row_style = "on color(233)" if (is_selected_row and not cell_selection_mode) else None
                table.add_row(*row_data, style=row_style)

            self._console.print(table)

        self._console.print()

        # Pad to push actions to bottom
        self._pad_to_bottom()

        # Actions with cleaner styling
        actions = [
            ("New Project", "+", "green"),
            ("Fields", "✎", "cyan"),
            ("Back", "←", "yellow")
        ]

        for i, (action, icon, icon_color) in enumerate(actions):
            action_idx = len(filtered_projects) + i
            if selected_index == action_idx:
                self._console.print(f"  [white]›[/white] [{icon_color}]{icon}[/{icon_color}] {action}")
            else:
                self._console.print(f"    [color(245)]{icon}[/color(245)] [color(245)]{action}[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()

    def _format_editing_cell(self, value, field, edit_buffer, date_buffer, date_component):
        """Format a cell that is being edited."""
        if field.field_type == "text":
            display_value = BaseRenderer.build_text_input_display(edit_buffer, len(edit_buffer))
            return f"[green]{display_value}[/green]"
        elif field.field_type == "number":
            display_value = BaseRenderer.build_text_input_display(edit_buffer, len(edit_buffer))
            return f"[green]{display_value}[/green]"
        elif field.field_type == "date":
            if date_buffer:
                parts = date_buffer.split('-')
                if len(parts) == 3:
                    year, month, day = parts
                    if date_component == 0:
                        return f"[reverse]{year}[/reverse]-{month}-{day}"
                    elif date_component == 1:
                        return f"{year}-[reverse]{month}[/reverse]-{day}"
                    else:
                        return f"{year}-{month}-[reverse]{day}[/reverse]"
            return self._format_custom_field_value(value, field, dimmed=False)
        elif field.field_type == "single_select":
            # Show current value with cycling indicator
            if value in (None, "", "none", "None"):
                return "[reverse]none[/reverse]"
            if field.select_options:
                option = next((opt for opt in field.select_options if opt.value == value), None)
                if option and option.color:
                    return f"[{option.color} reverse]{value}[/{option.color} reverse]"
            return f"[reverse]{value}[/reverse]"
        display_value = BaseRenderer.build_text_input_display(edit_buffer, len(edit_buffer))
        return f"[green]{display_value}[/green]"

    def _format_custom_field_value(self, value, custom_field, dimmed=False):
        """Format a custom field value for table display."""
        # Special handling for timeframe visualization (must come before generic None handling)
        if custom_field.key == "timeframe" and custom_field.field_type == "single_select":
            value_str = str(value).strip() if value else ""
            bar_color = "color(245)" if dimmed else "cyan"
            if not value_str or value_str.lower() == "none":
                return "[color(235)]-[/color(235)]"
            legacy_map = {
                "Short-Term": "▬",
                "Medium-Term": "▬ ▬",
                "Long-Term": "▬ ▬ ▬",
                "▬▬": "▬ ▬",
                "▬▬▬": "▬ ▬ ▬",
            }
            bar_value = legacy_map.get(value_str, value_str)
            if bar_value in {"▬", "▬ ▬", "▬ ▬ ▬"}:
                padding = " " * (5 - len(bar_value))
                return f"[{bar_color}]{bar_value}[/{bar_color}]{padding}"

        if value is None or value == "" or str(value).lower() == "none":
            return "[color(235)]-[/color(235)]"

        result = str(value)

        if custom_field.field_type == "text":
            # Truncate long text
            text = str(value)
            if len(text) > 20:
                result = text[:17] + "..."
            else:
                result = text

        elif custom_field.field_type == "number":
            # Format numbers with currency/percentage
            if custom_field.number_format == "currency":
                result = format_currency_value(value, custom_field.currency_symbol)
            elif custom_field.number_format == "percentage":
                result = f"{value}%"

        elif custom_field.field_type == "date":
            # Display date as-is
            result = str(value)

        elif custom_field.field_type == "single_select":
            # Find option and apply color if configured
            if custom_field.select_options:
                option = next((opt for opt in custom_field.select_options if opt.value == value), None)
                if option and option.color and not dimmed:
                    return f"[{option.color}]{value}[/{option.color}]"
            result = str(value)

        if dimmed:
            return f"[color(245)]{result}[/color(245)]"
        return result
