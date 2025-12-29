"""Form renderers for add/edit project and change status."""

from rich.text import Text

from .base import BaseRenderer
from ..utils import get_status_icon, get_status_color, get_edit_project_field_keys, format_currency_value
from ..states import AppState
from pm import STATUS_DISPLAY_ORDER
from ..custom_fields import FIELD_TYPE_DISPLAY, get_default_custom_fields, get_visible_fields_sorted


class EditProjectRenderer(BaseRenderer):
    """Renderer for edit project form."""

    def render(self, context: dict) -> str:
        """Render edit project form."""
        self._reset_console_buffer()

        manager = context['manager']
        current_project_id = context.get('current_project_id')
        form_field_index = context['form_field_index']
        form_data = context['form_data']
        inline_input_mode = context.get('inline_input_mode', False)
        text_input_buffer = context.get('text_input_buffer', '')
        text_input_cursor = context.get('text_input_cursor', len(text_input_buffer))
        all_fields = context.get('all_fields', [])
        if not all_fields:
            all_fields = get_default_custom_fields()

        # Check for temp project (ADD_PROJECT mode)
        state = context.get('state')
        is_adding = (state == AppState.ADD_PROJECT)
        
        if is_adding:
            # Get temp project from context
            project = context.get('temp_project')
            if not project:
                self._console.print("[red]Temporary project not found[/red]")
                self._render_status_message(context)
                return self._get_console_output()
        else:
            # Regular edit mode
            if current_project_id is None:
                self._console.print("[red]Project not found[/red]")
                self._render_status_message(context)
                return self._get_console_output()

            project = manager.get_project(current_project_id)
            if not project:
                self._console.print("[red]Project not found[/red]")
                self._render_status_message(context)
                return self._get_console_output()

        field_labels = {
            "status": "Status",
            "name": "Name",
            "description": "Description",
        }
        visible_fields = get_visible_fields_sorted(all_fields)
        field_keys = get_edit_project_field_keys(all_fields)

        for custom_field in visible_fields:
            field_labels[custom_field.key] = custom_field.label

        # Header
        self._console.print()
        if is_adding:
            self._console.print("  [bold]New Project[/bold]")
        else:
            self._console.print(f"  [color(243)]Edit Project:[/color(243)] [bold]{project.name}[/bold]")
        self._console.print()

        # Left-side border helper
        left_border = "[color(238)]  │[/color(238)] "
        def header_line() -> str:
            return "[color(238)]  ┌[/color(238)]"
        def footer_line() -> str:
            return "[color(238)]  └[/color(238)]"
        def left_line(content: str = "") -> str:
            return f"{left_border}{content}"

        visible_custom_fields = {f.key: f for f in visible_fields}

        self._console.print(header_line())

        # Track previous field for spacing
        builtin_fields = ["status", "name", "description"]
        
        for i, field in enumerate(field_keys):
            # Add separator after description (between builtin and custom fields)
            if i > 0 and field_keys[i-1] == "description" and field not in builtin_fields:
                self._console.print(left_line())
            
            is_selected = i == form_field_index
            selector = "[white]›[/white] " if is_selected else "  "
            custom_field = next((f for f in visible_fields if f.key == field), None)
            
            if field in form_data:
                value = form_data.get(field)
            elif custom_field:
                value = project.custom_field_values.get(field, getattr(project, field, ""))
            else:
                value = getattr(project, field, "")

            # Format the display value based on field type
            wrap_value = True
            if field == "status":
                status_value = value or project.status
                status_color = get_status_color(status_value)
                if is_selected:
                    display_value = f"[{status_color}]{get_status_icon(status_value)} {status_value}[/{status_color}]"
                else:
                    display_value = f"[color(243)]{get_status_icon(status_value)} {status_value}[/color(243)]"
            elif field == "name":
                if inline_input_mode and is_selected:
                    display_value = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                else:
                    display_value = value or project.name
            elif field == "description":
                if inline_input_mode and is_selected:
                    display_value = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                else:
                    display_value = f"[color(243)]{value}[/color(243)]" if value else "[color(238)]—[/color(238)]"
            elif custom_field:
                if custom_field.field_type == "text":
                    if inline_input_mode and is_selected:
                        display_value = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                    else:
                        if value:
                            display_value = f"[white]{value}[/white]" if is_selected else value
                        else:
                            display_value = "[color(238)]—[/color(238)]"
                elif custom_field.field_type == "number":
                    if inline_input_mode and is_selected:
                        display_value = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                    else:
                        if value:
                            if custom_field.number_format == "currency":
                                display_value = format_currency_value(value, custom_field.currency_symbol)
                            elif custom_field.number_format == "percentage":
                                display_value = f"{value}%"
                            else:
                                display_value = str(value)
                        else:
                            display_value = "[color(238)]—[/color(238)]"
                elif custom_field.field_type == "date":
                    if is_selected and context.get('custom_field_date_edit_mode'):
                        buffer = context.get('custom_field_date_buffer')
                        component = context.get('custom_field_date_component', 0)
                        if buffer:
                            parts = buffer.split('-')
                            if len(parts) == 3:
                                year, month, day = parts
                                if component == 0:
                                    display_value = (
                                        f"[white][reverse]{year}[/reverse][/white]"
                                        f"-[white]{month}[/white]"
                                        f"-[white]{day}[/white]"
                                    )
                                elif component == 1:
                                    display_value = (
                                        f"[white]{year}[/white]"
                                        f"-[white][reverse]{month}[/reverse][/white]"
                                        f"-[white]{day}[/white]"
                                    )
                                else:
                                    display_value = (
                                        f"[white]{year}[/white]"
                                        f"-[white]{month}[/white]"
                                        f"-[white][reverse]{day}[/reverse][/white]"
                                    )
                            else:
                                display_value = buffer
                        else:
                            display_value = "[color(238)]—[/color(238)]"
                    else:
                        if value:
                            display_value = f"[white]{value}[/white]" if is_selected else value
                        else:
                            display_value = "[color(238)]—[/color(238)]"
                elif custom_field.field_type == "single_select":
                    if value in (None, "", "none", "None"):
                        display_value = "[color(238)]-[/color(238)]"
                        wrap_value = False
                    elif custom_field.select_options:
                        option = next((opt for opt in custom_field.select_options if opt.value == value), None)
                        if option and option.color:
                            if is_selected:
                                display_value = f"[{option.color}]{value}[/{option.color}]"
                            else:
                                display_value = f"[color(243)]{value}[/color(243)]"
                        else:
                            display_value = value if is_selected else f"[color(243)]{value}[/color(243)]"
                    else:
                        display_value = value if value else "[color(238)]-[/color(238)]"
                else:
                    display_value = value if value else "[color(238)]—[/color(238)]"
            else:
                display_value = value if value else "[color(238)]—[/color(238)]"

            # Required marker
            required_marker = "[red]*[/red]" if custom_field and custom_field.required else ""
            
            # Format label
            label = field_labels.get(field, field)
            if is_selected:
                self._console.print(left_line(f"{selector}[color(245)]{label}[/color(245)]{required_marker}  {display_value}"))
            else:
                if wrap_value:
                    value_display = f"[color(243)]{display_value}[/color(243)]"
                else:
                    value_display = display_value
                self._console.print(left_line(f"{selector}[color(243)]{label}[/color(243)]{required_marker}  {value_display}"))

        self._console.print(footer_line())

        # Pad to push actions to bottom
        self._pad_to_bottom()

        # Actions
        if is_adding:
            actions = [
                ("Create", "[green]+[/green]", "[color(245)]+[/color(245)]"),
                ("Cancel", "[yellow]←[/yellow]", "[color(245)]←[/color(245)]")
            ]
        else:
            actions = [
                ("Save", "[green]✓[/green]", "[color(245)]✓[/color(245)]"),
                ("Delete", "[red]✗[/red]", "[color(245)]✗[/color(245)]"),
                ("Cancel", "[yellow]←[/yellow]", "[color(245)]←[/color(245)]")
            ]

        for i, (action, selected_icon, unselected_icon) in enumerate(actions):
            action_idx = len(field_keys) + i
            is_selected = form_field_index == action_idx
            if is_selected:
                self._console.print(f"  [white]›[/white] {selected_icon} {action}")
            else:
                self._console.print(f"    {unselected_icon} [color(245)]{action}[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class ChangeStatusRenderer(BaseRenderer):
    """Renderer for change status menu."""

    def render(self, context: dict) -> str:
        """Render change status menu."""
        self._reset_console_buffer()

        manager = context['manager']
        current_project_id = context['current_project_id']
        selected_index = context['selected_index']

        project = manager.get_project(current_project_id)
        if not project:
            self._console.print("[red]Project not found[/red]")
            self._render_status_message(context)
            return self._get_console_output()

        # HEADER SECTION
        self._console.print()
        self._console.print("  [bold]Change Status[/bold]")
        self._console.print(f"  [color(243)]{project.name}[/color(243)]")
        self._console.print()

        # CONTENT SECTION
        # Left-side border helper
        left_border = "[color(238)]  │[/color(238)] "
        def header_line() -> str:
            return "[color(238)]  ┌[/color(238)]"
        def footer_line() -> str:
            return "[color(238)]  └[/color(238)]"
        def left_line(content: str = "") -> str:
            return f"{left_border}{content}"

        self._console.print(header_line())

        # Current status (always shown, not selectable)
        current_color = get_status_color(project.status)
        current_icon = get_status_icon(project.status)
        self._console.print(left_line(f"[color(245)]Current[/color(245)]  [{current_color}]{current_icon} {project.status}[/{current_color}]"))

        # Blank line separator
        self._console.print(left_line())

        # Status options
        status_options = STATUS_DISPLAY_ORDER

        for i, status in enumerate(status_options):
            is_selected = i == selected_index
            selector = "[white]›[/white] " if is_selected else "  "

            color = get_status_color(status)
            icon = get_status_icon(status)

            if is_selected:
                # Full color when selected
                self._console.print(left_line(f"{selector}[{color}]{icon} {status}[/{color}]"))
            else:
                # Dimmed when unselected
                self._console.print(left_line(f"{selector}[color(243)]{icon} {status}[/color(243)]"))

        self._console.print(footer_line())

        # ACTION SECTION (pushed to bottom)
        self._pad_to_bottom()

        # Cancel action
        cancel_index = len(status_options)
        is_cancel_selected = selected_index == cancel_index

        if is_cancel_selected:
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Cancel")
        else:
            self._console.print("    [color(245)]← Cancel[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class DeleteConfirmationRenderer(BaseRenderer):
    """Renderer for delete confirmation dialog."""

    def render(self, context: dict) -> str:
        """Render delete confirmation dialog."""
        self._reset_console_buffer()

        form_field_index = context['form_field_index']
        delete_context = context.get('delete_context', {})
        delete_type = delete_context.get('delete_type', '')
        delete_params = delete_context.get('delete_params', {})

        # Compact confirmation dialog box
        self._console.print()
        self._console.print("  [bold]Delete Confirmation[/bold]")
        self._console.print()

        # Left-side border helper
        left_border = "[color(238)]  │[/color(238)] "
        def header_line() -> str:
            return "[color(238)]  ┌[/color(238)]"
        def footer_line() -> str:
            return "[color(238)]  └[/color(238)]"
        def left_line(content: str = "") -> str:
            return f"{left_border}{content}"

        # Map delete_type to display name and extract item identifier
        item_type = 'item'
        item_name = ''

        if delete_type == 'project':
            item_type = 'project'
            item_name = delete_params.get('project_name', '')
        elif delete_type in ('task', 'calendar_task'):
            item_type = 'task'
            task = delete_params.get('task')
            item_name = task.name if task else ''
        elif delete_type in ('bookmark', 'bookmark_from_list'):
            raw_type = delete_params.get('item_type')
            if raw_type == 'list':
                item_type = 'bookmark list'
                item_name = delete_params.get('item_title', '')
            else:
                item_type = 'bookmark'
                item_name = delete_params.get('item_title', '') or delete_params.get('bookmark_title', '')
        elif delete_type == 'bookmark_list_from_within':
            item_type = 'bookmark list'
            item_name = delete_params.get('list_title', '')
        elif delete_type == 'custom_field':
            item_type = 'custom field'
            item_name = delete_params.get('field_label', '')
        elif delete_type == 'edit_list_delete':
            item_type = 'list'
            item_name = delete_params.get('list_name', '')
        elif delete_type == 'pinned_item':
            pinned_item = delete_params.get('item', {})
            # Extract the actual type of the pinned item
            pinned_type = pinned_item.get('type', 'item')

            # Map pinned types to display names
            if pinned_type == 'bookmark_list':
                item_type = 'bookmark list'
            else:
                item_type = pinned_type  # project, task, bookmark, list, section

            # Extract the display name based on type
            if pinned_type == 'project':
                # Try to use the looked-up project name, fallback to ID
                item_name = pinned_item.get('project_name', f"Project #{pinned_item.get('id', '?')}")
            elif pinned_type == 'task':
                item_name = pinned_item.get('name', '')
            elif pinned_type in ('bookmark', 'bookmark_list'):
                item_name = pinned_item.get('title', '')
            elif pinned_type == 'list':
                item_name = pinned_item.get('name', '')
            elif pinned_type == 'section':
                # Sections have list_name and section_idx
                list_name = pinned_item.get('list_name', '')
                section_name = pinned_item.get('section_name', '')
                item_name = section_name or f"Section in {list_name}"
            else:
                item_name = ''
        elif delete_type == 'clear_completed':
            item_type = 'all completed tasks'
            item_name = ''

        self._console.print(header_line())

        # Display specific confirmation message based on item type and name
        if item_name:
            self._console.print(left_line(f"Are you sure you want to delete this {item_type}?"))
            self._console.print(left_line("[color(243)]This action cannot be undone.[/color(243)]"))
            self._console.print(left_line())
            self._console.print(left_line(f"[white]{item_name}[/white]"))
            self._console.print(left_line())
        else:
            # Fallback for items without names
            if delete_type == 'clear_completed':
                self._console.print(left_line("Are you sure you want to clear all completed tasks?"))
            else:
                self._console.print(left_line(f"Are you sure you want to delete this {item_type}?"))
            self._console.print(left_line("[color(243)]This action cannot be undone.[/color(243)]"))
            self._console.print(left_line())

        # Actions inside the box
        is_yes_selected = form_field_index == 0
        if is_yes_selected:
            self._console.print(left_line("[white]›[/white] [red]✓[/red] Yes, delete it"))
        else:
            self._console.print(left_line("  [color(245)]✓ Yes, delete it[/color(245)]"))

        is_no_selected = form_field_index == 1
        if is_no_selected:
            self._console.print(left_line("[white]›[/white] [yellow]✗[/yellow] No, cancel"))
        else:
            self._console.print(left_line("  [color(245)]✗ No, cancel[/color(245)]"))

        self._console.print(footer_line())

        self._render_status_message(context)
        return self._get_console_output()


class EditListRenderer(BaseRenderer):
    """Renderer for creating and editing task lists with sections."""

    def render(self, context: dict) -> str:
        """Render edit/create list form with sections."""
        from pm import LIST_COLOR_OPTIONS

        self._reset_console_buffer()

        form_field_index = context['form_field_index']
        form_data = context['form_data']
        inline_input_mode = context.get('inline_input_mode', False)
        text_input_buffer = context.get('text_input_buffer', '')
        text_input_cursor = context.get('text_input_cursor', len(text_input_buffer))
        editing_list_name = context.get('editing_list_name')

        is_creating = editing_list_name is None
        
        # Header
        self._console.print()
        if is_creating:
            self._console.print("  [bold]New List[/bold]")
        else:
            self._console.print(f"  [color(243)]Edit Task List:[/color(243)] [bold]{editing_list_name}[/bold]")
        self._console.print()

        # Left-side border helper
        left_border = "[color(238)]  │[/color(238)] "
        def header_line() -> str:
            return "[color(238)]  ┌[/color(238)]"
        def footer_line() -> str:
            return "[color(238)]  └[/color(238)]"
        def left_line(content: str = "") -> str:
            return f"{left_border}{content}"

        self._console.print(header_line())

        # List name field (field index 0)
        is_selected = form_field_index == 0
        selector = "[white]›[/white] " if is_selected else "  "
        if inline_input_mode and is_selected:
            display_text = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
            self._console.print(left_line(f"{selector}[color(245)]Name[/color(245)]  {display_text}"))
        else:
            list_name = form_data.get('name', '')
            if is_selected:
                self._console.print(left_line(f"{selector}[color(245)]Name[/color(245)]  {list_name}"))
            else:
                self._console.print(left_line(f"{selector}[color(243)]Name[/color(243)]  [color(243)]{list_name}[/color(243)]"))

        # Color selection field (field index 1)
        is_selected = form_field_index == 1
        selector = "[white]›[/white] " if is_selected else "  "
        color = form_data.get('color', 'white')
        if is_selected:
            color_display = f"[{color}]■[/{color}] {color}"
            self._console.print(left_line(f"{selector}[color(245)]Color[/color(245)]  {color_display}"))
        else:
            color_display = f"[color(243)]■[/color(243)] [color(243)]{color}[/color(243)]"
            self._console.print(left_line(f"{selector}[color(243)]Color[/color(243)]  {color_display}"))

        # Done Display mode selection (field index 2)
        is_selected = form_field_index == 2
        selector = "[white]›[/white] " if is_selected else "  "
        from pm import DONE_DISPLAY_LABELS
        done_mode = form_data.get('show_done_section', 'section')
        # Handle legacy boolean values
        if isinstance(done_mode, bool):
            done_mode = 'section' if done_mode else 'inline'
        done_display = DONE_DISPLAY_LABELS.get(done_mode, 'Section')
        if is_selected:
            self._console.print(left_line(f"{selector}[color(245)]Done Display[/color(245)]  {done_display}"))
        else:
            self._console.print(left_line(f"{selector}[color(243)]Done Display[/color(243)]  [color(245)]{done_display}[/color(245)]"))

        # Mode selection field (field index 3)
        is_selected = form_field_index == 3
        selector = "[white]›[/white] " if is_selected else "  "
        mode = form_data.get('mode', 'normal')
        mode_display = "Normal" if mode == 'normal' else "Sectioned"
        if is_selected:
            self._console.print(left_line(f"{selector}[color(245)]Mode[/color(245)]  {mode_display}"))
        else:
            self._console.print(left_line(f"{selector}[color(243)]Mode[/color(243)]  [color(245)]{mode_display}[/color(245)]"))

        # Sections management (only show if mode is 'sections')
        use_sections = mode == 'sections'
        sections = form_data.get('sections', [])

        if use_sections:
            if sections:
                for i, section in enumerate(sections):
                    field_idx = 4 + i
                    is_selected = form_field_index == field_idx
                    selector = "[white]›[/white] " if is_selected else "  "
                    section_name = section.get('name', '')
                    section_tasks_count = len(section.get('tasks', []))

                    if inline_input_mode and is_selected:
                        display_text = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                        self._console.print(left_line(f"    {selector}{display_text}  [color(243)]{section_tasks_count}[/color(243)]"))
                    else:
                        if section_name:
                            display = f"{section_name}  [color(243)]{section_tasks_count}[/color(243)]"
                        else:
                            display = f"[color(238)]—[/color(238)]  [color(243)]{section_tasks_count}[/color(243)]"
                        if is_selected:
                            self._console.print(left_line(f"    {selector}{display}"))
                        else:
                            self._console.print(left_line(f"    {selector}[color(245)]{display}[/color(245)]"))

            # Add section button (inside the box, indented)
            add_section_idx = 4 + len(sections)
            is_selected = form_field_index == add_section_idx
            selector = "[white]›[/white] " if is_selected else "  "
            
            if inline_input_mode and is_selected:
                display_text = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                self._console.print(left_line(f"    {selector}[green]+[/green] {display_text}"))
            else:
                if is_selected:
                    self._console.print(left_line(f"    {selector}[green]+[/green]"))
                else:
                    self._console.print(left_line(f"    {selector}[color(245)]+[/color(245)]"))

        self._console.print(footer_line())

        # Pad to push actions to bottom
        self._pad_to_bottom()

        # Action buttons
        if use_sections:
            add_section_idx = 4 + len(sections)
            save_idx = add_section_idx + 1
        else:
            save_idx = 4

        pin_idx = save_idx + 1
        delete_idx = pin_idx + 1
        cancel_idx = delete_idx + 1

        # Save button
        is_selected = form_field_index == save_idx
        if is_selected:
            self._console.print("  [white]›[/white] [green]✓[/green] Save")
        else:
            self._console.print("    [color(245)]✓ Save[/color(245)]")

        # Pin button (only show if editing, not creating)
        manager = context.get('manager')
        is_list_pinned = False
        if not is_creating and manager and editing_list_name:
            is_list_pinned = manager.is_pinned(
                "list",
                {"id": manager.get_list_id(editing_list_name), "name": editing_list_name},
            )
            
            is_selected = form_field_index == pin_idx
            pin_label = "Unpin" if is_list_pinned else "Pin"
            pin_icon = "◆" if is_list_pinned else "◇"
            if is_selected:
                self._console.print(f"  [white]›[/white] [cyan]{pin_icon}[/cyan] {pin_label}")
            else:
                self._console.print(f"    [color(245)]{pin_icon} {pin_label}[/color(245)]")
            actual_delete_idx = delete_idx
        else:
            actual_delete_idx = pin_idx

        # Delete button (only show if editing, not creating)
        if not is_creating:
            is_selected = form_field_index == actual_delete_idx
            if is_selected:
                self._console.print("  [white]›[/white] [red]✗[/red] Delete")
            else:
                self._console.print("    [color(245)]✗ Delete[/color(245)]")
            actual_cancel_idx = cancel_idx
        else:
            actual_cancel_idx = actual_delete_idx

        # Cancel button
        is_selected = form_field_index == actual_cancel_idx
        if is_selected:
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Cancel")
        else:
            self._console.print("    [color(245)]← Cancel[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class AddCustomFieldRenderer(BaseRenderer):
    """Renderer for adding a new custom field."""

    def render(self, context: dict) -> str:
        """Render the add custom field form with inline option management."""
        self._reset_console_buffer()
        form_data = context.get('form_data', {})
        form_field_index = context.get('form_field_index', 0)
        inline_input_mode = context.get('inline_input_mode', False)
        text_input_buffer = context.get('text_input_buffer', "")
        text_input_cursor = context.get('text_input_cursor', len(text_input_buffer))

        # Header
        self._console.print()
        self._console.print("  [bold]New Field[/bold]")
        self._console.print()

        # Left-side border helper
        left_border = "[color(238)]  │[/color(238)] "
        def header_line() -> str:
            return "[color(238)]  ┌[/color(238)]"
        def footer_line() -> str:
            return "[color(238)]  └[/color(238)]"
        def left_line(content: str = "") -> str:
            return f"{left_border}{content}"

        field_type = form_data.get('field_type', 'text')

        # Base field labels
        field_labels = {
            'label': 'Title',
            'field_type': 'Type',
            'visible': 'Visible',
            'required': 'Required',
            'number_format': 'Format',
            'currency_symbol': 'Currency Symbol',
        }

        # Render fields in specific order: Title, Visible, Required
        core_fields = ['label', 'visible', 'required']

        self._console.print(header_line())

        for i, field in enumerate(core_fields):
            is_selected = i == form_field_index
            selector = "[white]›[/white] " if is_selected else "  "
            value = form_data.get(field, "")

            if field == 'label':
                if inline_input_mode and is_selected:
                    display_value = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                else:
                    display_value = value if value else "[color(238)]—[/color(238)]"

                if is_selected:
                    self._console.print(left_line(f"{selector}[color(245)]{field_labels[field]}[/color(245)]  {display_value}"))
                else:
                    self._console.print(left_line(f"{selector}[color(243)]{field_labels[field]}[/color(243)]  [color(245)]{display_value}[/color(245)]"))

            elif field in ['visible', 'required']:
                display_value = "Yes" if value else "No"

                if is_selected:
                    self._console.print(left_line(f"{selector}[color(245)]{field_labels[field]}[/color(245)]  {display_value}"))
                else:
                    self._console.print(left_line(f"{selector}[color(243)]{field_labels[field]}[/color(243)]  [color(245)]{display_value}[/color(245)]"))

        # Blank line separator before Type field
        self._console.print(left_line())

        # Render Type field
        type_field_idx = len(core_fields)
        is_selected = type_field_idx == form_field_index
        selector = "[white]›[/white] " if is_selected else "  "
        type_value = form_data.get('field_type', '')

        if type_value:
            display_value = FIELD_TYPE_DISPLAY.get(type_value, type_value)
        else:
            display_value = "[color(238)]—[/color(238)]"

        if is_selected:
            self._console.print(left_line(f"{selector}[color(245)]Type[/color(245)]  {display_value}"))
        else:
            self._console.print(left_line(f"{selector}[color(243)]Type[/color(243)]  [color(245)]{display_value}[/color(245)]"))

        # Number format fields (indented, below Type, only for number type)
        current_idx = type_field_idx + 1
        if field_type == 'number':
            # Number Format field
            is_selected = current_idx == form_field_index
            selector = "[white]›[/white] " if is_selected else "  "
            number_format_value = form_data.get('number_format', '')
            display_value = number_format_value if number_format_value else "[color(238)]—[/color(238)]"

            if is_selected:
                self._console.print(left_line(f"    {selector}[color(245)]Format[/color(245)]  {display_value}"))
            else:
                self._console.print(left_line(f"    {selector}[color(243)]Format[/color(243)]  [color(245)]{display_value}[/color(245)]"))
            current_idx += 1

            # Currency Symbol field (only if format is currency)
            if form_data.get('number_format') == 'currency':
                is_selected = current_idx == form_field_index
                selector = "[white]›[/white] " if is_selected else "  "
                currency_value = form_data.get('currency_symbol', '')

                if inline_input_mode and is_selected:
                    display_value = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                else:
                    display_value = currency_value if currency_value else "[color(238)]—[/color(238)]"

                if is_selected:
                    self._console.print(left_line(f"    {selector}[color(245)]Currency Symbol[/color(245)]  {display_value}"))
                else:
                    self._console.print(left_line(f"    {selector}[color(243)]Currency Symbol[/color(243)]  [color(245)]{display_value}[/color(245)]"))
                current_idx += 1

        # Inline option management for single_select fields
        options = form_data.get('select_options', []) if field_type == 'single_select' else []
        options_start_idx = current_idx

        if field_type == 'single_select':
            # Existing options
            for idx, opt in enumerate(options):
                field_idx = options_start_idx + idx
                is_selected = form_field_index == field_idx
                selector = "[white]›[/white] " if is_selected else "  "

                # Determine display value and color (support SelectOption or dict)
                opt_value = getattr(opt, 'value', None) or (opt.get('value') if isinstance(opt, dict) else str(opt))
                opt_color = getattr(opt, 'color', None) if not isinstance(opt, dict) else opt.get('color')

                if inline_input_mode and is_selected:
                    display_text = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                else:
                    if opt_color:
                        if is_selected:
                            display_text = f"[bold {opt_color} reverse] {opt_value} [/bold {opt_color} reverse]"
                        else:
                            display_text = f"[color(243)]{opt_value}[/color(243)]"
                    else:
                        if opt_value:
                            display_text = (
                                f"[white]{opt_value}[/white]"
                                if is_selected
                                else f"[color(243)]{opt_value}[/color(243)]"
                            )
                        else:
                            display_text = "[color(243)]unnamed option[/color(243)]"

                self._console.print(left_line(f"    {selector}{display_text}"))

            # + Add Option row
            add_idx = options_start_idx + len(options)
            is_selected = form_field_index == add_idx
            add_selector = "[white]›[/white] " if is_selected else "  "

            if inline_input_mode and is_selected:
                display_text = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                self._console.print(left_line(f"    {add_selector}[green]+[/green] {display_text}"))
            else:
                if is_selected:
                    self._console.print(left_line(f"    {add_selector}[green]+[/green]"))
                else:
                    self._console.print(left_line(f"    {add_selector}[color(245)]+[/color(245)]"))

        self._console.print(footer_line())

        # Pad to push actions to bottom
        self._pad_to_bottom()

        # Actions
        if field_type == 'single_select':
            save_idx = options_start_idx + len(options) + 1
        else:
            save_idx = current_idx
        cancel_idx = save_idx + 1

        actions = [
            ("Create", "[green]✓[/green]", "[color(245)]✓[/color(245)]"),
            ("Cancel", "[yellow]←[/yellow]", "[color(245)]←[/color(245)]"),
        ]

        for i, (label, selected_icon, unselected_icon) in enumerate(actions):
            action_idx = save_idx + i
            if form_field_index == action_idx:
                self._console.print(f"  [white]›[/white] {selected_icon} {label}")
            else:
                self._console.print(f"    {unselected_icon} [color(245)]{label}[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class EditCustomFieldRenderer(BaseRenderer):
    """Renderer for editing an existing custom field."""

    def render(self, context: dict) -> str:
        """Render the edit custom field form with inline option management."""
        self._reset_console_buffer()
        form_data = context.get('form_data', {})
        form_field_index = context.get('form_field_index', 0)
        inline_input_mode = context.get('inline_input_mode', False)
        text_input_buffer = context.get('text_input_buffer', "")
        text_input_cursor = context.get('text_input_cursor', len(text_input_buffer))

        # Header - show the field label
        field_label = form_data.get('label', 'Edit Field')
        self._console.print()
        self._console.print(f"  [color(243)]Edit Project Field:[/color(243)] [bold]{field_label}[/bold]")
        self._console.print()

        # Left-side border helper
        left_border = "[color(238)]  │[/color(238)] "
        def header_line() -> str:
            return "[color(238)]  ┌[/color(238)]"
        def footer_line() -> str:
            return "[color(238)]  └[/color(238)]"
        def left_line(content: str = "") -> str:
            return f"{left_border}{content}"

        field_type = form_data.get('field_type', 'text')

        # Base field labels
        field_labels = {
            'label': 'Title',
            'field_type': 'Type',
            'visible': 'Visible',
            'required': 'Required',
            'number_format': 'Format',
            'currency_symbol': 'Currency Symbol',
        }

        # Render fields in specific order: Title, Visible, Required
        core_fields = ['label', 'visible', 'required']

        self._console.print(header_line())

        for i, field in enumerate(core_fields):
            is_selected = i == form_field_index
            selector = "[white]›[/white] " if is_selected else "  "
            value = form_data.get(field, "")

            if field == 'label':
                if inline_input_mode and is_selected:
                    display_value = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                else:
                    display_value = value if value else "[color(238)]—[/color(238)]"

                if is_selected:
                    self._console.print(left_line(f"{selector}[color(245)]{field_labels[field]}[/color(245)]  {display_value}"))
                else:
                    self._console.print(left_line(f"{selector}[color(243)]{field_labels[field]}[/color(243)]  [color(245)]{display_value}[/color(245)]"))

            elif field in ['visible', 'required']:
                display_value = "Yes" if value else "No"

                if is_selected:
                    self._console.print(left_line(f"{selector}[color(245)]{field_labels[field]}[/color(245)]  {display_value}"))
                else:
                    self._console.print(left_line(f"{selector}[color(243)]{field_labels[field]}[/color(243)]  [color(245)]{display_value}[/color(245)]"))

        # Blank line separator before Type field
        self._console.print(left_line())

        # Render Type field
        type_field_idx = len(core_fields)
        is_selected = type_field_idx == form_field_index
        selector = "[white]›[/white] " if is_selected else "  "
        type_value = form_data.get('field_type', '')

        if type_value:
            display_value = FIELD_TYPE_DISPLAY.get(type_value, type_value)
        else:
            display_value = "[color(238)]—[/color(238)]"

        if is_selected:
            self._console.print(left_line(f"{selector}[color(245)]Type[/color(245)]  {display_value}"))
        else:
            self._console.print(left_line(f"{selector}[color(243)]Type[/color(243)]  [color(245)]{display_value}[/color(245)]"))

        # Number format fields (indented, below Type, only for number type)
        current_idx = type_field_idx + 1
        if field_type == 'number':
            # Number Format field
            is_selected = current_idx == form_field_index
            selector = "[white]›[/white] " if is_selected else "  "
            number_format_value = form_data.get('number_format', '')
            display_value = number_format_value if number_format_value else "[color(238)]—[/color(238)]"

            if is_selected:
                self._console.print(left_line(f"    {selector}[color(245)]Format[/color(245)]  {display_value}"))
            else:
                self._console.print(left_line(f"    {selector}[color(243)]Format[/color(243)]  [color(245)]{display_value}[/color(245)]"))
            current_idx += 1

            # Currency Symbol field (only if format is currency)
            if form_data.get('number_format') == 'currency':
                is_selected = current_idx == form_field_index
                selector = "[white]›[/white] " if is_selected else "  "
                currency_value = form_data.get('currency_symbol', '')

                if inline_input_mode and is_selected:
                    display_value = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                else:
                    display_value = currency_value if currency_value else "[color(238)]—[/color(238)]"

                if is_selected:
                    self._console.print(left_line(f"    {selector}[color(245)]Currency Symbol[/color(245)]  {display_value}"))
                else:
                    self._console.print(left_line(f"    {selector}[color(243)]Currency Symbol[/color(243)]  [color(245)]{display_value}[/color(245)]"))
                current_idx += 1

        # Inline option management for single_select fields
        options = form_data.get('select_options', []) if field_type == 'single_select' else []
        options_start_idx = current_idx

        if field_type == 'single_select':
            # Existing options
            for idx, opt in enumerate(options):
                field_idx = options_start_idx + idx
                is_selected = form_field_index == field_idx
                selector = "[white]›[/white] " if is_selected else "  "

                opt_value = getattr(opt, 'value', None) or (opt.get('value') if isinstance(opt, dict) else str(opt))
                opt_color = getattr(opt, 'color', None) if not isinstance(opt, dict) else opt.get('color')

                if inline_input_mode and is_selected:
                    display_text = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                else:
                    if opt_color:
                        if is_selected:
                            display_text = f"[bold {opt_color} reverse] {opt_value} [/bold {opt_color} reverse]"
                        else:
                            display_text = f"[color(243)]{opt_value}[/color(243)]"
                    else:
                        if opt_value:
                            display_text = (
                                f"[white]{opt_value}[/white]"
                                if is_selected
                                else f"[color(243)]{opt_value}[/color(243)]"
                            )
                        else:
                            display_text = "[color(243)]unnamed option[/color(243)]"

                self._console.print(left_line(f"    {selector}{display_text}"))

            # + Add Option row
            add_idx = options_start_idx + len(options)
            is_selected = form_field_index == add_idx
            add_selector = "[white]›[/white] " if is_selected else "  "

            if inline_input_mode and is_selected:
                display_text = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                self._console.print(left_line(f"    {add_selector}[green]+[/green] {display_text}"))
            else:
                if is_selected:
                    self._console.print(left_line(f"    {add_selector}[green]+[/green]"))
                else:
                    self._console.print(left_line(f"    {add_selector}[color(245)]+[/color(245)]"))

        self._console.print(footer_line())

        # Pad to push actions to bottom
        self._pad_to_bottom()

        # Actions
        if field_type == 'single_select':
            save_idx = options_start_idx + len(options) + 1
        else:
            save_idx = current_idx
        delete_idx = save_idx + 1
        cancel_idx = save_idx + 2

        actions = [
            ("Save", "[green]✓[/green]", "[color(245)]✓[/color(245)]"),
            ("Delete", "[red]✗[/red]", "[color(245)]✗[/color(245)]"),
            ("Cancel", "[yellow]←[/yellow]", "[color(245)]←[/color(245)]"),
        ]

        for i, (label, selected_icon, unselected_icon) in enumerate(actions):
            action_idx = save_idx + i
            if form_field_index == action_idx:
                self._console.print(f"  [white]›[/white] {selected_icon} {label}")
            else:
                self._console.print(f"    {unselected_icon} [color(245)]{label}[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class AddProjectRenderer(EditProjectRenderer):
    """Backward-compatible alias for the add project form."""

    # Project creation now reuses :class:`EditProjectRenderer` for layout, but
    # tests and external callers may still import ``AddProjectRenderer``.
    pass
