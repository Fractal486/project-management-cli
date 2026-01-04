"""Calendar renderer for task deadlines."""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .base import BaseRenderer
from ..utils.calendar import CalendarEntry, collect_deadline_map


class CalendarRenderer(BaseRenderer):
    """Renderer for the calendar view."""

    def render(self, context: dict) -> str:
        """Render calendar view with a grid and tasks for the selected day."""
        self._reset_console_buffer()

        manager = context["manager"]
        year = context.get("calendar_year")
        month = context.get("calendar_month")
        selected_day = context.get("calendar_selected_day")
        list_tasks_map = context.get("list_tasks") or getattr(
            manager,
            "list_tasks",
            {"Tasks": getattr(manager, "standalone_tasks", [])},
        )

        deadline_map = collect_deadline_map(manager, list_tasks_map)

        if not year or not month:
            now = datetime.now()
            year = year or now.year
            month = month or now.month

        self._console.print("\n[bold]Calendar[/bold]\n")
        self._render_calendar_grid(year, month, selected_day, deadline_map, context)
        self._console.print()
        self._render_day_tasks(year, month, selected_day, deadline_map, context)

        # Pad to push back button to bottom
        self._pad_to_bottom()

        # Back button
        navigation_focus = context.get("calendar_navigation_focus", "day")
        if navigation_focus == "back":
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Back", highlight=False)
        else:
            self._console.print("    [color(245)]←[/color(245)] [color(245)]Back[/color(245)]", highlight=False)

        self._render_status_message(context)
        return self._get_console_output()

    def _render_calendar_grid(
        self,
        year: int,
        month: int,
        selected_day: Optional[int],
        deadline_map: Dict[str, List[CalendarEntry]],
        context: dict,
    ) -> None:
        """Render the monthly calendar grid."""
        navigation_focus = context.get("calendar_navigation_focus", "day")

        # Use lighter border when calendar is focused
        is_calendar_focused = navigation_focus in ("day", "prev", "next")
        border_color = "243" if is_calendar_focused else "238"
        left_border = f"[color({border_color})]  │[/color({border_color})] "

        def header_line() -> str:
            return f"[color({border_color})]  ┌[/color({border_color})]"

        def footer_line() -> str:
            return f"[color({border_color})]  └[/color({border_color})]"

        def left_line(content: str = "") -> str:
            return f"{left_border}{content}"

        month_name = calendar.month_name[month]

        # Month navigation header with selectable arrows
        if navigation_focus == "prev":
            left_arrow = "[white]←[/white]"
            right_arrow = "[color(243)]→[/color(243)]"
        elif navigation_focus == "next":
            left_arrow = "[color(243)]←[/color(243)]"
            right_arrow = "[white]→[/white]"
        else:
            left_arrow = "[color(243)]←[/color(243)]"
            right_arrow = "[color(243)]→[/color(243)]"

        self._console.print(f"  {left_arrow} {month_name} {str(year)} {right_arrow}", highlight=False)
        self._console.print()

        self._console.print(header_line(), highlight=False)
        self._console.print(left_line("[color(243)]Sun  Mon  Tue  Wed  Thu  Fri  Sat[/color(243)]"), highlight=False)
        self._console.print(left_line(), highlight=False)

        # Use monthdatescalendar to get full weeks including padding days from neighbor months
        weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(year, month)
        
        # Get today's date for highlighting
        today = datetime.now().date()

        for i, week in enumerate(weeks):
            cells: List[str] = []
            for d in week:
                is_this_month = (d.month == month and d.year == year)
                day = d.day

                if not is_this_month:
                    # Gray out days from other months in the "corners"
                    day_text = f"[color(238)]{day:2d}[/color(238)]"
                    cells.append(f" {day_text}  ")
                    continue

                day_text = f"{day:2d}"
                is_today = (d == today)

                # Highlighting priority: selected (focused) > selected (unfocused) > today > tasks
                if selected_day == day and navigation_focus == "day":
                    # Selected day when calendar is focused: bright reverse highlight
                    day_text = f"[reverse]{day_text}[/reverse]"
                elif selected_day == day:
                    # Selected day when calendar is not focused: lighter highlight
                    day_text = f"[on color(238)]{day_text}[/on color(238)]"
                elif is_today:
                    # Today: bold
                    day_text = f"[bold]{day_text}[/bold]"

                cells.append(f" {day_text}  ")

            self._console.print(left_line("".join(cells)), highlight=False)

            # Add spacing between rows (but not after the last row)
            if i < len(weeks) - 1:
                self._console.print(left_line(), highlight=False)

        self._console.print(footer_line(), highlight=False)


    def _render_day_tasks(
        self,
        year: int,
        month: int,
        selected_day: Optional[int],
        deadline_map: Dict[str, List[CalendarEntry]],
        context: dict,
    ) -> None:
        """Render tasks for the selected day."""
        navigation_focus = context.get("calendar_navigation_focus", "day")

        # Use lighter border when tasks section is focused
        is_tasks_focused = navigation_focus == "tasks"
        border_color = "243" if is_tasks_focused else "238"
        left_border = f"[color({border_color})]  │[/color({border_color})] "

        def header_line() -> str:
            return f"[color({border_color})]  ┌[/color({border_color})]"

        def footer_line() -> str:
            return f"[color({border_color})]  └[/color({border_color})]"

        def left_line(content: str = "") -> str:
            return f"{left_border}{content}"

        if not selected_day:
            self._console.print()
            self._console.print("  [color(243)]No day selected[/color(243)]", highlight=False)
            self._console.print(header_line(), highlight=False)
            self._console.print(left_line("[color(243)]Use arrow keys to select a day[/color(243)]"), highlight=False)
            self._console.print(footer_line(), highlight=False)
            return

        date_key = f"{year:04d}-{month:02d}-{selected_day:02d}"
        tasks_for_day = deadline_map.get(date_key, [])
        date_label = datetime(year, month, selected_day).strftime("%Y %b %d")
        count = len(tasks_for_day)
        task_selected_index = context.get("calendar_task_selected_index", 0)
        calendar_tasks_tab = context.get("calendar_tasks_tab", 0)

        # Tab header
        self._console.print()
        tab_labels = ["Selected Day", "Overdue", "Upcoming"]
        tab_parts = []
        for i, label in enumerate(tab_labels):
            if i == calendar_tasks_tab:
                tab_parts.append(f"[bold white reverse] {label} [/bold white reverse]")
            else:
                tab_parts.append(f"[color(245)] {label} [/color(245)]")
            if i < len(tab_labels) - 1:
                tab_parts.append(" ")
        tabs_line = "  " + "".join(tab_parts)
        self._console.print(tabs_line, highlight=False)
        self._console.print()

        self._console.print(header_line(), highlight=False)

        # Render content based on active tab
        if calendar_tasks_tab == 0:
            # Tab 0: Selected Day (existing functionality)
            self._render_selected_day_tab(
                year, month, selected_day, tasks_for_day, date_label, count,
                task_selected_index, navigation_focus, left_line, context
            )
        elif calendar_tasks_tab == 1:
            # Tab 1: Overdue
            overdue_data = context.get("overdue_entries", [])
            self._render_overdue_tab(
                overdue_data, task_selected_index, navigation_focus, left_line, context
            )
        elif calendar_tasks_tab == 2:
            # Tab 2: Upcoming
            upcoming_data = context.get("upcoming_entries", {})
            collapsed_sections = context.get("calendar_upcoming_collapsed", set())
            self._render_upcoming_tab(
                upcoming_data, collapsed_sections, task_selected_index, navigation_focus, left_line, context
            )

        self._console.print(footer_line(), highlight=False)

    def _render_selected_day_tab(
        self,
        year: int,
        month: int,
        selected_day: Optional[int],
        tasks_for_day: List[CalendarEntry],
        date_label: str,
        count: int,
        task_selected_index: int,
        navigation_focus: str,
        left_line,
        context: dict,
    ) -> None:
        """Render the Selected Day tab content."""
        # Header with date and count
        item_word = "item" if count == 1 else "items"
        self._console.print(left_line(f"[bold]{date_label}[/bold]  [color(243)]{count} {item_word}[/color(243)]"), highlight=False)
        self._console.print(left_line(), highlight=False)
        
        inline_task_edit_mode = context.get("inline_task_edit_mode", False)
        inline_edit_task = context.get("inline_edit_task")
        inline_edit_field_index = context.get("inline_edit_field_index", 0)
        inline_edit_name = context.get("inline_edit_name", "")
        inline_edit_name_cursor = context.get("inline_edit_name_cursor", len(inline_edit_name))
        inline_edit_deadline = context.get("inline_edit_deadline")
        inline_edit_priority = context.get("inline_edit_priority")
        inline_edit_notes = context.get("inline_edit_notes")
        inline_edit_notes_cursor = context.get("inline_edit_notes_cursor", 0)
        inline_edit_deadline_component = context.get("inline_edit_deadline_component", 0)

        from ..config import get_config
        config = get_config()

        for i, entry in enumerate(tasks_for_day):
            is_selected = navigation_focus == "tasks" and i == task_selected_index
            selector = "[white]›[/white] " if is_selected else "  "

            task = entry.item if entry.kind == "task" else None
            project = entry.item if entry.kind == "project_field" else None

            # Check if this task is being edited inline (same as main menu pinned section)
            is_inline_edit_target = False
            if inline_task_edit_mode and inline_edit_task and task is not None:
                if task is inline_edit_task:
                    is_inline_edit_target = True

            completed = getattr(task, "completed", None) if task is not None else None
            if is_selected:
                if completed is True:
                    status_icon = "[green]✓[/green]"
                elif completed is False:
                    status_icon = "[red]✗[/red]"
                else:
                    status_icon = "[white]○[/white]"
            else:
                # Use same logic as main menu pinned section
                status_icon = "[color(238)]✓[/color(238)]" if completed is True else (
                    "[color(238)]✗[/color(238)]" if completed is False else "[color(243)]○[/color(243)]"
                )

            # If adding a new task (not editing existing), skip it here - will be rendered at bottom
            if is_inline_edit_target and task_selected_index == len(tasks_for_day):
                continue

            # If editing an existing task inline, show edit fields in-place (same as main menu)
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
                dim_selector = "[color(238)]›[/color(238)] " if is_selected else selector
                self._console.print(left_line(f"{dim_selector}  {status_icon} {name_display}  {priority_display}  {deadline_display}"), highlight=False)
                
                # Show notes field during inline edit
                notes_display = self.build_inline_notes_display(
                    inline_edit_notes, inline_edit_field_index, inline_edit_notes_cursor
                )
                self._console.print(
                    self.wrap_with_prefix(notes_display, left_line("    ")),
                    highlight=False,
                )
                continue

            if project is not None:
                from ..utils import get_status_icon, get_status_color
                status_icon = get_status_icon(getattr(project, "status", None))
                status_color = get_status_color(getattr(project, "status", None))
                if is_selected:
                    status_icon = f"[{status_color}]{status_icon}[/{status_color}]"
                else:
                    status_icon = f"[color(243)]{status_icon}[/color(243)]"

            if task is not None:
                task_name = getattr(task, "name", "Untitled")
            else:
                task_name = getattr(project, "name", "Untitled")
            if is_selected:
                name_display = task_name
            else:
                name_color = "color(238)" if completed is not None else "color(243)"
                name_display = f"[{name_color}]{task_name}[/{name_color}]"

            metadata_parts: List[str] = []
            if task is not None:
                priority = getattr(task, "priority", None)
                if priority:
                    metadata_parts.append(priority)
            elif project is not None:
                field_label = entry.field_label or "Date"
                metadata_parts.append(f"({field_label})")

            # Dim all metadata uniformly with separator
            if metadata_parts:
                meta_content = " · ".join(metadata_parts)
                if is_selected:
                    meta_suffix = f"   [color(243)]{meta_content}[/color(243)]"
                else:
                    meta_suffix = f"   [color(238)]{meta_content}[/color(238)]"
            else:
                meta_suffix = ""
            self._console.print(left_line(f"{selector}  {status_icon} {name_display}{meta_suffix}"), highlight=False)

            # Show task notes in Selected Day tab
            notes_value = getattr(task, "notes", None) if task is not None else None
            if notes_value:
                show_notes = False
                if config.notes_display_mode == "always":
                    show_notes = True
                elif config.notes_display_mode == "dynamic" and is_selected:
                    show_notes = True

                if show_notes:
                    from rich.markup import escape as rich_escape
                    escaped_notes = rich_escape(notes_value)
                    self._console.print(
                        self.wrap_with_prefix(
                            f"[color(238)]{escaped_notes}[/color(238)]",
                            left_line("    "),
                        ),
                        highlight=False,
                    )

        # Add Task button (+) or Inline Editor for NEW tasks
        # Show inline editor only when adding a new task (index == len), not when editing existing task
        is_adding_new = inline_task_edit_mode and task_selected_index == len(tasks_for_day)
        if is_adding_new:
            add_selector = "[white]›[/white] "
            name_display = self.build_inline_name_display(
                inline_edit_name, inline_edit_field_index, inline_edit_name_cursor
            )
            priority_display = self.build_inline_priority_display(
                inline_edit_priority, inline_edit_field_index
            )
            deadline_display = self.build_inline_deadline_display(
                inline_edit_deadline, inline_edit_field_index, inline_edit_deadline_component
            )
            self._console.print(left_line(f"{add_selector}  [green]+[/green] {name_display}  {priority_display}  {deadline_display}"), highlight=False)
            
            # Show notes field during inline add
            notes_display = self.build_inline_notes_display(
                inline_edit_notes, inline_edit_field_index, inline_edit_notes_cursor
            )
            self._console.print(
                self.wrap_with_prefix(notes_display, left_line("    ")),
                highlight=False,
            )
        else:
            add_selected = navigation_focus == "tasks" and task_selected_index == len(tasks_for_day)
            add_selector = "[white]›[/white] " if add_selected else "  "
            plus_icon = "[green]+[/green]" if add_selected else "[color(245)]+[/color(245)]"
            self._console.print(left_line(f"{add_selector}  {plus_icon}"), highlight=False)

    def _render_overdue_tab(
        self,
        overdue_data: List,
        task_selected_index: int,
        navigation_focus: str,
        left_line,
        context: dict,
    ) -> None:
        """Render the Overdue tab content."""
        from ..utils.calendar import CalendarEntry
        
        # Count total overdue before truncation
        total_overdue = context.get("total_overdue_count", len(overdue_data))
        count = len(overdue_data)
        
        # Header with count
        item_word = "item" if count == 1 else "items"
        self._console.print(left_line(f"[bold]Overdue[/bold]  [color(243)]{count} {item_word}[/color(243)]"), highlight=False)
        
        if count == 0:
            # Empty state
            self._console.print(left_line(), highlight=False)
            self._console.print(left_line("[color(243)]No overdue items[/color(243)]"), highlight=False)
            return
        
        self._console.print(left_line(), highlight=False)
        
        inline_task_edit_mode = context.get("inline_task_edit_mode", False)
        inline_edit_task = context.get("inline_edit_task")
        inline_edit_field_index = context.get("inline_edit_field_index", 0)
        inline_edit_name = context.get("inline_edit_name", "")
        inline_edit_name_cursor = context.get("inline_edit_name_cursor", len(inline_edit_name))
        inline_edit_deadline = context.get("inline_edit_deadline")
        inline_edit_priority = context.get("inline_edit_priority")
        inline_edit_notes = context.get("inline_edit_notes")
        inline_edit_notes_cursor = context.get("inline_edit_notes_cursor", 0)
        inline_edit_deadline_component = context.get("inline_edit_deadline_component", 0)
        
        from ..config import get_config
        config = get_config()

        # Render overdue entries
        for i, (entry, days_overdue) in enumerate(overdue_data):
            is_selected = navigation_focus == "tasks" and i == task_selected_index
            selector = "[white]›[/white] " if is_selected else "  "
            
            task = entry.item if entry.kind == "task" else None
            project = entry.item if entry.kind == "project_field" else None
            
            # Check if this task is being edited inline
            is_inline_edit_target = False
            if inline_task_edit_mode and inline_edit_task and task is not None:
                if task is inline_edit_task:
                    is_inline_edit_target = True
            
            completed = getattr(task, "completed", None) if task is not None else None
            if is_selected:
                if completed is True:
                    status_icon = "[green]✓[/green]"
                elif completed is False:
                    status_icon = "[red]✗[/red]"
                else:
                    status_icon = "[white]○[/white]"
            else:
                status_icon = "[color(238)]✓[/color(238)]" if completed is True else (
                    "[color(238)]✗[/color(238)]" if completed is False else "[color(243)]○[/color(243)]"
                )
            
            # If editing an existing task inline, show edit fields in-place
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
                dim_selector = "[color(238)]›[/color(238)] " if is_selected else selector
                self._console.print(left_line(f"{dim_selector}  {status_icon} {name_display}  {priority_display}  {deadline_display}"), highlight=False)
                
                # Show notes field during inline edit
                notes_display = self.build_inline_notes_display(
                    inline_edit_notes, inline_edit_field_index, inline_edit_notes_cursor
                )
                self._console.print(
                    self.wrap_with_prefix(notes_display, left_line("    ")),
                    highlight=False,
                )
                continue
            if project is not None:
                from ..utils import get_status_icon, get_status_color
                status_icon = get_status_icon(getattr(project, "status", None))
                status_color = get_status_color(getattr(project, "status", None))
                if is_selected:
                    status_icon = f"[{status_color}]{status_icon}[/{status_color}]"
                else:
                    status_icon = f"[color(243)]{status_icon}[/color(243)]"

            if task is not None:
                task_name = getattr(task, "name", "Untitled")
            else:
                task_name = getattr(project, "name", "Untitled")

            if is_selected:
                name_display = task_name
            else:
                name_color = "color(238)" if completed is not None else "color(243)"
                name_display = f"[{name_color}]{task_name}[/{name_color}]"

            metadata_parts: List[str] = []
            if task is not None:
                priority = getattr(task, "priority", None)
                if priority:
                    metadata_parts.append(priority)

            # Add days overdue
            days_text = "1d overdue" if days_overdue == 1 else f"{days_overdue}d overdue"
            if project is not None:
                field_label = entry.field_label or "Date"
                combined = f"{field_label} {days_text}".strip()
                metadata_parts.append(f"({combined})")
            else:
                metadata_parts.append(days_text)

            # Dim all metadata uniformly with separator
            if metadata_parts:
                meta_content = " · ".join(metadata_parts)
                if is_selected:
                    meta_suffix = f"   [color(243)]{meta_content}[/color(243)]"
                else:
                    meta_suffix = f"   [color(238)]{meta_content}[/color(238)]"
            else:
                meta_suffix = ""
            self._console.print(left_line(f"{selector}  {status_icon} {name_display}{meta_suffix}"), highlight=False)

            # Show task notes in Overdue tab
            notes_value = getattr(task, "notes", None) if task is not None else None
            if notes_value:
                show_notes = False
                if config.notes_display_mode == "always":
                    show_notes = True
                elif config.notes_display_mode == "dynamic" and is_selected:
                    show_notes = True

                if show_notes:
                    from rich.markup import escape as rich_escape
                    escaped_notes = rich_escape(notes_value)
                    self._console.print(
                        self.wrap_with_prefix(
                            f"[color(238)]{escaped_notes}[/color(238)]",
                            left_line("    "),
                        ),
                        highlight=False,
                    )
        
        # Show "... and N more overdue" if truncated
        if total_overdue > count:
            more_count = total_overdue - count
            self._console.print(left_line(), highlight=False)
            self._console.print(left_line(f"[color(243)]... and {more_count} more overdue[/color(243)]"), highlight=False)

    def _render_upcoming_tab(
        self,
        upcoming_data: Dict[str, List],
        collapsed_sections: Set[str],
        task_selected_index: int,
        navigation_focus: str,
        left_line,
        context: dict,
    ) -> None:
        """Render the Upcoming tab content with collapsible sections."""
        from ..utils.calendar import CalendarEntry
        from ..utils import format_deadline
        
        # Section definitions
        sections = [
            ("today", "Today"),
            ("next_week", "Next Week"),
            ("next_month", "Next Month"),
        ]
        
        # Count total items
        total_count = sum(len(upcoming_data.get(key, [])) for key, _ in sections)
        
        # Header with count
        item_word = "item" if total_count == 1 else "items"
        self._console.print(left_line(f"[bold]Upcoming[/bold]  [color(243)]{total_count} {item_word}[/color(243)]"), highlight=False)
        
        if total_count == 0:
            # Empty state
            self._console.print(left_line(), highlight=False)
            self._console.print(left_line("[color(243)]No upcoming items[/color(243)]"), highlight=False)
            return
        
        self._console.print(left_line(), highlight=False)
        
        inline_task_edit_mode = context.get("inline_task_edit_mode", False)
        inline_edit_task = context.get("inline_edit_task")
        inline_edit_field_index = context.get("inline_edit_field_index", 0)
        inline_edit_name = context.get("inline_edit_name", "")
        inline_edit_name_cursor = context.get("inline_edit_name_cursor", len(inline_edit_name))
        inline_edit_deadline = context.get("inline_edit_deadline")
        inline_edit_priority = context.get("inline_edit_priority")
        inline_edit_notes = context.get("inline_edit_notes")
        inline_edit_notes_cursor = context.get("inline_edit_notes_cursor", 0)
        inline_edit_deadline_component = context.get("inline_edit_deadline_component", 0)
        
        from ..config import get_config
        config = get_config()

        # Build flat list for navigation: headers + tasks (skipping collapsed)
        flat_items = []  # List of ("header", section_key, label, count) or ("task", entry)
        for section_key, section_label in sections:
            entries = upcoming_data.get(section_key, [])
            
            # Always add section header (even if empty)
            flat_items.append(("header", section_key, section_label, len(entries)))
            
            # Add tasks if section is not collapsed and has entries
            if section_key not in collapsed_sections and entries:
                for entry in entries:
                    flat_items.append(("task", entry))
        
        # Render sections and tasks
        for i, item in enumerate(flat_items):
            is_selected = navigation_focus == "tasks" and i == task_selected_index
            
            if item[0] == "header":
                # Section header
                _, section_key, section_label, count = item
                is_collapsed = section_key in collapsed_sections
                arrow = "▸" if is_collapsed else "▾"
                
                if is_selected:
                    self._console.print(left_line(f"[white]›[/white] [white]{arrow}[/white] [bold white]{section_label}[/bold white] [color(238)]{count}[/color(238)]"), highlight=False)
                else:
                    self._console.print(left_line(f"  [color(245)]{arrow}[/color(245)] [bold color(245)]{section_label}[/bold color(245)] [color(238)]{count}[/color(238)]"), highlight=False)
            
            elif item[0] == "task":
                # Task entry
                entry = item[1]
                selector = "[white]›[/white] " if is_selected else "  "
                
                task = entry.item if entry.kind == "task" else None
                project = entry.item if entry.kind == "project_field" else None
                
                # Check if this task is being edited inline
                is_inline_edit_target = False
                if inline_task_edit_mode and inline_edit_task and task is not None:
                    if task is inline_edit_task:
                        is_inline_edit_target = True
                
                completed = getattr(task, "completed", None) if task is not None else None
                if is_selected:
                    if completed is True:
                        status_icon = "[green]✓[/green]"
                    elif completed is False:
                        status_icon = "[red]✗[/red]"
                    else:
                        status_icon = "[white]○[/white]"
                else:
                    status_icon = "[color(238)]✓[/color(238)]" if completed is True else (
                        "[color(238)]✗[/color(238)]" if completed is False else "[color(243)]○[/color(243)]"
                    )
                
                # If editing an existing task inline, show edit fields in-place
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
                    dim_selector = "[color(238)]›[/color(238)] " if is_selected else selector
                    self._console.print(left_line(f"{dim_selector}  {status_icon} {name_display}  {priority_display}  {deadline_display}"), highlight=False)
                    
                    # Show notes field during inline edit
                    notes_display = self.build_inline_notes_display(
                        inline_edit_notes, inline_edit_field_index, inline_edit_notes_cursor
                    )
                    self._console.print(
                        self.wrap_with_prefix(notes_display, left_line("    ")),
                        highlight=False,
                    )
                    continue
                if project is not None:
                    from ..utils import get_status_icon, get_status_color
                    status_icon = get_status_icon(getattr(project, "status", None))
                    status_color = get_status_color(getattr(project, "status", None))
                    if is_selected:
                        status_icon = f"[{status_color}]{status_icon}[/{status_color}]"
                    else:
                        status_icon = f"[color(243)]{status_icon}[/color(243)]"

                if task is not None:
                    task_name = getattr(task, "name", "Untitled")
                else:
                    task_name = getattr(project, "name", "Untitled")

                if is_selected:
                    name_display = task_name
                else:
                    name_color = "color(238)" if completed is not None else "color(243)"
                    name_display = f"[{name_color}]{task_name}[/{name_color}]"

                metadata_parts: List[str] = []
                if task is not None:
                    # Show priority before deadline to match global metadata order.
                    priority = getattr(task, "priority", None)
                    if priority:
                        metadata_parts.append(priority)

                    deadline = getattr(task, "deadline", None)
                    if deadline:
                        from ..utils import format_deadline
                        formatted_dl = format_deadline(deadline).strip() or deadline
                        metadata_parts.append(formatted_dl)
                elif project is not None:
                    field_label = entry.field_label or "Date"
                    # Show date for project fields
                    # We need to get the actual date value
                    value = None
                    if entry.field_key:
                        custom_values = getattr(project, "custom_field_values", {}) or {}
                        value = custom_values.get(entry.field_key, getattr(project, entry.field_key, None))
                    combined_parts = [field_label]
                    if value:
                        combined_parts.append(str(value))
                    combined = " ".join(combined_parts).strip()
                    metadata_parts.append(f"({combined})")

                # Dim all metadata uniformly with separator
                if metadata_parts:
                    meta_content = " · ".join(metadata_parts)
                    if is_selected:
                        meta_suffix = f"   [color(243)]{meta_content}[/color(243)]"
                    else:
                        meta_suffix = f"   [color(238)]{meta_content}[/color(238)]"
                else:
                    meta_suffix = ""
                self._console.print(left_line(f"{selector}  {status_icon} {name_display}{meta_suffix}"), highlight=False)

                # Show task notes in Upcoming tab
                notes_value = getattr(task, "notes", None) if task is not None else None
                if notes_value:
                    show_notes = False
                    if config.notes_display_mode == "always":
                        show_notes = True
                    elif config.notes_display_mode == "dynamic" and is_selected:
                        show_notes = True

                    if show_notes:
                        from rich.markup import escape as rich_escape
                        escaped_notes = rich_escape(notes_value)
                        self._console.print(
                            self.wrap_with_prefix(
                                f"[color(238)]{escaped_notes}[/color(238)]",
                                left_line("    "),
                            ),
                            highlight=False,
                        )
