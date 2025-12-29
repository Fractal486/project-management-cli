"""Main menu renderer."""

from ..quick_stats import format_quick_stats
from ..main_menu_tabs import build_main_menu_items, is_quick_add_enabled
from .base import BaseRenderer


class MainMenuRenderer(BaseRenderer):
    """Renderer for the main menu."""

    def render(self, context: dict) -> str:
        """Render the main menu."""
        self._reset_console_buffer()

        manager = context['manager']
        selected_index = context['selected_index']
        inline_input_mode = context.get('inline_input_mode', False)
        text_input_buffer = context.get('text_input_buffer', '')
        text_input_cursor = context.get('text_input_cursor', len(text_input_buffer))
        quick_add_priority = context.get('quick_add_priority', None)
        quick_add_field_index = context.get('quick_add_field_index', 0)
        quick_add_deadline = context.get('quick_add_deadline', None)
        quick_add_deadline_component = context.get('quick_add_deadline_component', 0)
        quick_add_deadline_edit_mode = context.get('quick_add_deadline_edit_mode', False)
        quick_add_list = context.get('quick_add_list', 'Tasks')
        quick_stats_selection = context.get('quick_stats_selection', set())
        inline_task_edit_mode = context.get('inline_task_edit_mode', False)
        inline_edit_task = context.get('inline_edit_task')
        inline_edit_field_index = context.get('inline_edit_field_index', 0)
        inline_edit_name = context.get('inline_edit_name', '')
        inline_edit_name_cursor = context.get('inline_edit_name_cursor', len(inline_edit_name))
        inline_edit_deadline = context.get('inline_edit_deadline')
        inline_edit_priority = context.get('inline_edit_priority')
        inline_edit_deadline_component = context.get('inline_edit_deadline_component', 0)
        inline_edit_notes = context.get('inline_edit_notes')
        inline_edit_notes_cursor = context.get('inline_edit_notes_cursor', 0)

        # Clean header
        self._console.print()
        self._console.print("  [bold]Project Manager[/bold]")
        
        # Quick stats as subtle subheader
        quick_stats = format_quick_stats(manager, quick_stats_selection)
        if quick_stats:
            stats_line = "  ·  ".join(quick_stats)
            self._console.print(f"  [color(243)]{stats_line}[/color(243)]")
        self._console.print()

        main_menu_tabs_selection = context.get('main_menu_tabs_selection', set())
        quick_add_enabled = is_quick_add_enabled(main_menu_tabs_selection)
        menu_items = build_main_menu_items(main_menu_tabs_selection)
        quick_add_offset = 1 if quick_add_enabled else 0

        # Quick Add Task section
        if quick_add_enabled:
            quick_add_selected = selected_index == 0

            if inline_input_mode and quick_add_selected:
                def render_input(value: str, cursor: int) -> str:
                    value = value or ""
                    caret_pos = max(0, min(len(value), cursor))
                    if value and caret_pos < len(value):
                        return (
                            f"{value[:caret_pos]}"
                            f"[reverse]{value[caret_pos]}[/reverse]"
                            f"{value[caret_pos + 1:]}"
                        )
                    return f"{value}[reverse] [/reverse]"
                # Left-side border helper for quick add form
                left_border = "[color(238)]  │[/color(238)] "
                def footer_line() -> str:
                    return "[color(238)]  └[/color(238)]"
                def left_line(content: str = "") -> str:
                    return f"{left_border}{content}"
                
                # Show header inline with border corner
                self._console.print("  [color(238)]┌[/color(238)] [green]+[/green] Quick Add Task")
                
                # Task name field
                title_selector = "[white]›[/white] " if quick_add_field_index == 0 else "  "
                if quick_add_field_index == 0:
                    input_display = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                else:
                    input_display = text_input_buffer if text_input_buffer else "[color(238)]—[/color(238)]"
                
                if quick_add_field_index == 0:
                    self._console.print(left_line(f"{title_selector}[color(245)]Task[/color(245)]  {input_display}"))
                else:
                    self._console.print(left_line(f"{title_selector}[color(243)]Task[/color(243)]  {input_display}"))

                # Priority field
                priority_selector = "[white]›[/white] " if quick_add_field_index == 1 else "  "
                priority_colors = {"!!!": "red", "!!": "yellow", "!": "green"}
                if quick_add_priority:
                    priority_color = priority_colors.get(quick_add_priority, "white")
                    priority_text = f"[{priority_color}]{quick_add_priority}[/{priority_color}]"
                else:
                    priority_text = "[color(238)]—[/color(238)]"
                
                if quick_add_field_index == 1:
                    self._console.print(left_line(f"{priority_selector}[color(245)]Priority[/color(245)]  {priority_text}"))
                else:
                    self._console.print(left_line(f"{priority_selector}[color(243)]Priority[/color(243)]  [color(245)]{priority_text}[/color(245)]"))

                # Deadline field
                deadline_selector = "[white]›[/white] " if quick_add_field_index == 2 else "  "
                if quick_add_deadline_edit_mode and quick_add_field_index == 2:
                    if quick_add_deadline:
                        parts = quick_add_deadline.split('-')
                        year = parts[0] if len(parts) > 0 else "2025"
                        month = parts[1] if len(parts) > 1 else "01"
                        day = parts[2] if len(parts) > 2 else "01"
                    else:
                        from datetime import datetime
                        today = datetime.now()
                        year = str(today.year)
                        month = f"{today.month:02d}"
                        day = f"{today.day:02d}"

                    if quick_add_deadline_component == 0:
                        deadline_text = f"[white][reverse]{year}[/reverse][/white]-[white]{month}[/white]-[white]{day}[/white]"
                    elif quick_add_deadline_component == 1:
                        deadline_text = f"[white]{year}[/white]-[white][reverse]{month}[/reverse][/white]-[white]{day}[/white]"
                    else:
                        deadline_text = f"[white]{year}[/white]-[white]{month}[/white]-[white][reverse]{day}[/reverse][/white]"
                    self._console.print(left_line(f"{deadline_selector}[color(245)]Deadline[/color(245)]  {deadline_text}"))
                elif quick_add_deadline:
                    deadline_display = quick_add_deadline
                    if quick_add_field_index == 2:
                        self._console.print(left_line(f"{deadline_selector}[color(245)]Deadline[/color(245)]  [white]{deadline_display}[/white]"))
                    else:
                        self._console.print(left_line(f"{deadline_selector}[color(243)]Deadline[/color(243)]  [color(245)]{deadline_display}[/color(245)]"))
                else:
                    deadline_display = "[color(238)]—[/color(238)]"
                    if quick_add_field_index == 2:
                        self._console.print(left_line(f"{deadline_selector}[color(245)]Deadline[/color(245)]  {deadline_display}"))
                    else:
                        self._console.print(left_line(f"{deadline_selector}[color(243)]Deadline[/color(243)]  {deadline_display}"))

                # List field
                list_selector = "[white]›[/white] " if quick_add_field_index == 3 else "  "
                list_display = quick_add_list
                if quick_add_field_index == 3:
                    self._console.print(left_line(f"{list_selector}[color(245)]List[/color(245)]  {list_display}"))
                else:
                    self._console.print(left_line(f"{list_selector}[color(243)]List[/color(243)]  [color(245)]{list_display}[/color(245)]"))
                
                # Add button
                add_selector = "[white]›[/white] " if quick_add_field_index == 4 else "  "
                if quick_add_field_index == 4:
                    self._console.print(left_line(f"{add_selector}[green]+[/green] Add"))
                else:
                    self._console.print(left_line(f"{add_selector}[color(245)]+ Add[/color(245)]"))
                
                self._console.print(footer_line())
            else:
                # Show collapsed state
                if quick_add_selected:
                    self._console.print("  [white]›[/white] [green]+[/green] Quick Add Task")
                else:
                    self._console.print("    [color(245)]+ Quick Add Task[/color(245)]")
            
            self._console.print()

        # Menu items - grouped visually
        for i, (label, action) in enumerate(menu_items):
            menu_selected = selected_index == (i + quick_add_offset)
            if menu_selected:
                self._console.print(f"  [white]›[/white] {label}")
            else:
                self._console.print(f"    [color(245)]{label}[/color(245)]")

        self._console.print()

        # Settings and Exit
        settings_index = quick_add_offset + len(menu_items)
        exit_index = settings_index + 1
        settings_selected = selected_index == settings_index
        in_pinned_section = context.get('in_pinned_section', False)
        exit_selected = (selected_index == exit_index) and (not in_pinned_section)

        if settings_selected:
            self._console.print("  [white]›[/white] Settings")
        else:
            self._console.print("    [color(245)]Settings[/color(245)]")
        
        if exit_selected:
            self._console.print("  [white]›[/white] Exit")
        else:
            self._console.print("    [color(245)]Exit[/color(245)]")

        # Pinned section
        pinned_selected_index = context.get('pinned_selected_index', 0)
        pinned_items = manager.metadata.get('pinned_items', [])

        if pinned_items:
            # Group items by type and create display order
            pinned_projects = [item for item in pinned_items if item.get("type") == "project"]
            # Keep task lists and pinned sections together with individual tasks
            # (like bookmark lists with bookmarks)
            pinned_tasks = [item for item in pinned_items if item.get("type") in ("task", "list", "section")]
            pinned_bookmarks = [item for item in pinned_items if item.get("type") in ("bookmark", "bookmark_list")]

            # Reorder items: projects, then tasks (including lists and pinned sections), then bookmarks
            reordered_items = pinned_projects + pinned_tasks + pinned_bookmarks
            
            # Store reordered items in UI state so handlers can access them
            ui_state = context.get('ui_state')
            display_items = []
            if ui_state:
                ui_state.reordered_pinned_items = reordered_items

            self._console.print()
            self._console.print()
            self._console.print()
            self._console.print("  [bold color(255)]Pinned[/bold color(255)]")
            self._console.print()

            from pm import STATUS_META
            from pm_live.utils import render_progress_bar
            
            # Left-side border helper
            left_border = "[color(238)]  │[/color(238)] "
            def header_line() -> str:
                return "[color(238)]  ┌[/color(238)]"
            def footer_line() -> str:
                return "[color(238)]  └[/color(238)]"
            def left_line(content: str = "") -> str:
                return f"{left_border}{content}"
            
            display_index = 0
            self._console.print(header_line())

            # Pinned Projects
            if pinned_projects:
                self._console.print(left_line("[color(250)]Projects[/color(250)]"))
                for item in pinned_projects:
                    is_selected = in_pinned_section and pinned_selected_index == display_index
                    display_items.append({"kind": "pinned", "item": item})
                    display_index += 1
                    project_id = item.get("id")
                    project = manager.get_project(project_id)
                    if project:
                        status_meta = STATUS_META.get(project.status, {})
                        status_icon = status_meta.get("icon", "?")
                        status_color = status_meta.get("color", "white")

                        # Display project name with stats inline
                        if project.tasks:
                            percentage = project.progress_percentage()
                            # Use medium-weight characters for subtle but visible bars
                            filled = int((percentage / 100) * 6)
                            empty = 6 - filled
                            if is_selected:
                                filled_color = "color(245)"
                                empty_color = "color(238)"
                            else:
                                filled_color = "color(238)"
                                empty_color = "color(238)"
                            bar = f"[{filled_color}]{'▬' * filled}[/{filled_color}][{empty_color}]{'▭' * empty}[/{empty_color}]"
                            stats_str = f"  {bar}"
                        else:
                            stats_str = ""

                        if is_selected:
                            self._console.print(left_line(f"[white]›[/white] [{status_color}]{status_icon}[/{status_color}] {project.name}{stats_str}"))
                        else:
                            self._console.print(left_line(f"  [color(243)]{status_icon}[/color(243)] [color(243)]{project.name}[/color(243)]{stats_str}"))
                    else:
                        fallback = f"Project #{project_id}"
                        if is_selected:
                            self._console.print(left_line(f"[white]›[/white] [color(243)]?[/color(243)] {fallback}"))
                        else:
                            self._console.print(left_line(f"  [color(243)]?[/color(243)] [color(243)]{fallback}[/color(243)]"))
                
                # Add separator if there are more sections
                if pinned_tasks or pinned_bookmarks:
                    self._console.print(left_line())

            # Pinned Tasks
            if pinned_tasks:
                self._console.print(left_line("[color(250)]Tasks[/color(250)]"))
                for item in pinned_tasks:
                    is_selected = in_pinned_section and pinned_selected_index == display_index
                    display_items.append({"kind": "pinned", "item": item})
                    display_index += 1

                    item_type = item.get("type")
                    if item_type == "task":
                        task_name = item.get("name", item.get("id", "Unknown"))
                        completed = item.get("completed")
                        deadline = item.get("deadline")
                        priority = item.get("priority")
                        task_id = item.get("id")

                        # Check if this task is being edited inline
                        # Match by task object identity if possible, otherwise by name
                        is_inline_edit_target = False
                        if inline_task_edit_mode and inline_edit_task:
                            # Try to match by task object name
                            if getattr(inline_edit_task, "name", None) == task_name:
                                is_inline_edit_target = True

                        # If this task is being edited inline, show edit fields
                        if is_inline_edit_target and is_selected:
                            name_display = self.build_inline_name_display(
                                inline_edit_name, inline_edit_field_index, inline_edit_name_cursor
                            )
                            priority_display = self.build_inline_priority_display(
                                inline_edit_priority, inline_edit_field_index
                            )
                            deadline_display = self.build_inline_deadline_display(
                                inline_edit_deadline, inline_edit_field_index, inline_edit_deadline_component
                            )
                            if completed is True:
                                status_icon = "[green]✓[/green]"
                            elif completed is False:
                                status_icon = "[red]✗[/red]"
                            else:
                                status_icon = "[cyan]○[/cyan]"
                            self._console.print(left_line(f"[color(238)]›[/color(238)] {status_icon} {name_display}  {priority_display}  {deadline_display}"))

                            # Add notes line below
                            notes_display = self.build_inline_notes_display(
                                inline_edit_notes, inline_edit_field_index, inline_edit_notes_cursor
                            )
                            self._console.print(left_line(f"  {notes_display}"))
                            continue

                        project_name = None
                        project_id = item.get("project_id")
                        if project_id is not None:
                            project = manager.get_project(project_id)
                            if project:
                                project_name = project.name
                        # If metadata missing, attempt to resolve from source tasks
                        if (deadline is None or priority is None) and isinstance(task_id, str):
                            def _find_task_by_name(tasks, name):
                                for t in tasks:
                                    if getattr(t, "name", None) == name:
                                        return t
                                    subtasks = getattr(t, "subtasks", None)
                                    if subtasks:
                                        found = _find_task_by_name(subtasks, name)
                                        if found:
                                            return found
                                return None

                            list_name = item.get("list_name")
                            section_idx = item.get("section_idx")
                            if list_name and section_idx is not None:
                                sections = getattr(manager, "list_tasks", {}).get(list_name, [])
                                if 0 <= section_idx < len(sections):
                                    tasks = getattr(sections[section_idx], "tasks", [])
                                    found_task = _find_task_by_name(tasks, task_name)
                                    if found_task:
                                        deadline = deadline or getattr(found_task, "deadline", None)
                                        priority = priority or getattr(found_task, "priority", None)
                        if is_selected:
                            if completed is True:
                                status_icon = "[green]✓[/green]"
                            elif completed is False:
                                status_icon = "[red]✗[/red]"
                            else:
                                status_icon = "[cyan]○[/cyan]"
                        else:
                            status_icon = "[color(238)]✓[/color(238)]" if completed is True else (
                                "[color(238)]✗[/color(238)]" if completed is False else "[color(243)]○[/color(243)]"
                            )

                        # Build metadata display for priority/deadline if present
                        meta_parts = []
                        if priority:
                            meta_parts.append(priority)
                        if deadline:
                            from pm_live.utils.formatting import format_deadline
                            formatted_deadline = format_deadline(deadline).strip()
                            meta_parts.append(formatted_deadline)

                        # Dim all metadata uniformly with separator
                        if meta_parts:
                            meta_content = " · ".join(meta_parts)
                            if is_selected:
                                meta_suffix = f"   [color(243)]{meta_content}[/color(243)]"
                            else:
                                meta_suffix = f"   [color(238)]{meta_content}[/color(238)]"
                        else:
                            meta_suffix = ""

                        if is_selected:
                            self._console.print(left_line(f"[white]›[/white] {status_icon} {task_name}{meta_suffix}"))
                        else:
                            name_color = "color(238)" if completed is not None else "color(243)"
                            self._console.print(left_line(f"  {status_icon} [{name_color}]{task_name}[/{name_color}]{meta_suffix}"))

                        # Display notes based on notes_display_mode setting
                        notes_value = item.get("notes")
                        if notes_value and completed is None:  # Only show notes for uncompleted tasks
                            from ..config import get_config
                            from rich.markup import escape as rich_escape
                            config = get_config()
                            show_notes = False
                            if config.notes_display_mode == "always":
                                show_notes = True
                            elif config.notes_display_mode == "dynamic" and is_selected:
                                show_notes = True

                            if show_notes:
                                escaped_notes = rich_escape(notes_value)
                                self._console.print(left_line(f"  [color(238)]{escaped_notes}[/color(238)]"))

                    elif item_type == "list":
                        list_name = item.get("name", "List")
                        list_id = item.get("id") or manager.get_list_id(list_name)
                        ui_state = context.get('ui_state')
                        expanded_lists = getattr(ui_state, "expanded_pinned_lists", set()) if ui_state else set()
                        expanded = list_id in expanded_lists
                        expanded_list_sections = getattr(ui_state, "expanded_pinned_list_sections", set()) if ui_state else set()

                        # Arrow icon - dimmed when collapsed
                        if expanded:
                            arrow = "[color(243)]▾[/color(243)]"
                        else:
                            arrow = "[color(243)]▸[/color(243)]"

                        if is_selected:
                            self._console.print(left_line(f"[white]›[/white] {arrow} {list_name}"))
                        else:
                            self._console.print(left_line(f"  {arrow} [color(243)]{list_name}[/color(243)]"))

                        # Show expanded content with all sections and tasks
                        if expanded:
                            list_sections = manager.list_tasks.get(list_name, [])
                            single_unnamed_section = (
                                len(list_sections) == 1
                                and not str(getattr(list_sections[0], 'name', '') or "").strip()
                            )
                            for section_idx, section in enumerate(list_sections):
                                section_id = section.get("id") if isinstance(section, dict) else getattr(section, "id", None)
                                section_name = getattr(section, 'name', '')
                                section_label = str(section_name or "").strip()
                                tasks = getattr(section, 'tasks', [])

                                if single_unnamed_section:
                                    for task in tasks:
                                        # Only show unstarted/unmarked tasks
                                        if getattr(task, 'completed', None) is not None:
                                            continue
                                        is_task_selected = in_pinned_section and pinned_selected_index == display_index
                                        task_name = getattr(task, 'name', 'Task')
                                        status_icon = "[cyan]○[/cyan]" if is_task_selected else "[color(243)]○[/color(243)]"
                                        display_items.append({
                                            "kind": "list_task",
                                            "list_id": list_id,
                                            "list_name": list_name,
                                            "section_idx": section_idx,
                                            "section_id": section_id,
                                            "task_name": task_name,
                                        })
                                        display_index += 1
                                        if is_task_selected:
                                            # Keep icon aligned while cursor sits at start
                                            self._console.print(left_line(f"[white]›[/white]   {status_icon} {task_name}"))
                                        else:
                                            self._console.print(left_line(f"    {status_icon} [color(243)]{task_name}[/color(243)]"))
                                    break

                                display_name = section_label or "Tasks"
                                section_expanded = section_id in expanded_list_sections
                                section_arrow = "[color(243)]▾[/color(243)]" if section_expanded else "[color(243)]▸[/color(243)]"

                                section_selected = in_pinned_section and pinned_selected_index == display_index
                                display_items.append({
                                    "kind": "list_section",
                                    "list_id": list_id,
                                    "list_name": list_name,
                                    "section_idx": section_idx,
                                    "section_id": section_id,
                                })
                                display_index += 1

                                if section_selected:
                                    self._console.print(left_line(f"[white]›[/white]   {section_arrow} {display_name}"))
                                else:
                                    self._console.print(left_line(f"    {section_arrow} [color(243)]{display_name}[/color(243)]"))

                                # Show section tasks only when expanded
                                if section_expanded:
                                    for task in tasks:
                                        # Only show unstarted/unmarked tasks
                                        if getattr(task, 'completed', None) is not None:
                                            continue
                                        is_task_selected = in_pinned_section and pinned_selected_index == display_index
                                        task_name = getattr(task, 'name', 'Task')
                                        status_icon = "[cyan]○[/cyan]" if is_task_selected else "[color(243)]○[/color(243)]"
                                        display_items.append({
                                            "kind": "list_task",
                                            "list_id": list_id,
                                            "list_name": list_name,
                                            "section_idx": section_idx,
                                            "section_id": section_id,
                                            "task_name": task_name,
                                        })
                                        display_index += 1
                                        if is_task_selected:
                                            # Keep icon aligned while cursor sits at start
                                            self._console.print(left_line(f"[white]›[/white]     {status_icon} {task_name}"))
                                        else:
                                            self._console.print(left_line(f"      {status_icon} [color(243)]{task_name}[/color(243)]"))

                    elif item_type == "section":
                        section_id = item.get("id")
                        list_id = item.get("list_id")
                        section_name = item.get("section_name", "Tasks")
                        list_name = item.get("list_name") or manager.get_list_name_by_id(list_id) or ""
                        section_idx = item.get("section_idx", 0)
                        section_obj = None
                        if section_id:
                            resolved_list, resolved_idx, resolved_section = manager.find_section_by_id(section_id)
                            if resolved_list:
                                list_name = resolved_list
                            if resolved_idx is not None:
                                section_idx = resolved_idx
                            if resolved_section is not None:
                                section_obj = resolved_section
                                section_name = section_name or (resolved_section.name or "Tasks")
                        ui_state = context.get('ui_state')
                        expanded_sections = getattr(ui_state, "expanded_pinned_sections", set()) if ui_state else set()
                        expanded = section_id in expanded_sections

                        # Arrow icon - dimmed when collapsed
                        if expanded:
                            arrow = "[color(243)]▾[/color(243)]"
                        else:
                            arrow = "[color(243)]▸[/color(243)]"

                        if is_selected:
                            self._console.print(left_line(f"[white]›[/white] {arrow} {section_name}"))
                        else:
                            self._console.print(left_line(f"  {arrow} [color(243)]{section_name}[/color(243)]"))

                        # Show expanded content with all tasks in the section
                        if expanded:
                            if section_obj is None:
                                list_sections = manager.list_tasks.get(list_name, [])
                                if 0 <= section_idx < len(list_sections):
                                    section_obj = list_sections[section_idx]
                            if section_obj is not None:
                                tasks = getattr(section_obj, 'tasks', [])
                                for task in tasks:
                                    task_name = getattr(task, 'name', 'Task')
                                    completed = getattr(task, 'completed', None)
                                    # Only show unstarted/unmarked tasks
                                    if completed is not None:
                                        continue
                                    is_task_selected = in_pinned_section and pinned_selected_index == display_index
                                    status_icon = "[cyan]○[/cyan]" if is_task_selected else "[color(243)]○[/color(243)]"
                                    display_items.append({
                                        "kind": "section_task",
                                        "list_id": list_id,
                                        "list_name": list_name,
                                        "section_idx": section_idx,
                                        "section_id": section_id,
                                        "task_name": task_name,
                                    })
                                    display_index += 1
                                    if is_task_selected:
                                        # Keep icon aligned while cursor sits at start
                                        self._console.print(left_line(f"[white]›[/white]   {status_icon} {task_name}"))
                                    else:
                                        self._console.print(left_line(f"    {status_icon} [color(243)]{task_name}[/color(243)]"))
                
                # Add separator if there are more sections
                if pinned_bookmarks:
                    self._console.print(left_line())

            # Pinned Bookmarks
            if pinned_bookmarks:
                self._console.print(left_line("[color(250)]Bookmarks[/color(250)]"))
                copied_reset = False
                for item in pinned_bookmarks:
                    is_selected = in_pinned_section and pinned_selected_index == display_index
                    display_items.append({"kind": "pinned", "item": item})
                    display_index += 1
                    item_type = item.get("type")
                    if item_type == "bookmark":
                        title = item.get("title", "Untitled")
                        bookmark_icon = "[color(243)]○[/color(243)]"
                        copied = item.get("copied")
                        if copied and not is_selected:
                            item["copied"] = False
                            copied = False
                            copied_reset = True
                        if is_selected and copied:
                            url_icon = "[green]↗[/green]"
                        elif is_selected:
                            url_icon = "[cyan]↗[/cyan]"
                        else:
                            url_icon = "[color(243)]↗[/color(243)]"
                        if is_selected:
                            self._console.print(left_line(f"[white]›[/white] {bookmark_icon} {title}  {url_icon}"))
                        else:
                            self._console.print(left_line(f"  {bookmark_icon} [color(243)]{title}[/color(243)]  {url_icon}"))
                    elif item_type == "bookmark_list":
                        title = item.get("title", "List")
                        if is_selected:
                            self._console.print(left_line(f"[white]›[/white] [color(243)]□[/color(243)] {title}"))
                        else:
                            self._console.print(left_line(f"  [color(243)]□[/color(243)] [color(243)]{title}[/color(243)]"))

                if copied_reset:
                    try:
                        manager.mark_metadata_modified()
                    except Exception:
                        pass

            self._console.print(footer_line())

            if ui_state:
                ui_state.pinned_display_items = display_items

        self._render_status_message(context)
        return self._get_console_output()
