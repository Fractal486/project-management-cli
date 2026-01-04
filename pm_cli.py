#!/usr/bin/env python3
"""CLI dispatcher with pre-configured subcommands for project management."""

import argparse
import sys
from pathlib import Path
from typing import Optional

# Force UTF-8 output on Windows
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from pm import ProjectManager, Bookmark, BookmarkList, STATUS_META
from pm_live.logging_setup import configure_logging
from pm_live.config import get_config, set_config
from pm_live.utils import format_deadline, render_progress_bar, get_status_icon, get_status_color, format_currency_value
from pm_live.custom_fields import get_all_fields
from rich.console import Console
from rich.table import Table
from rich import box


def load_manager(data_file: Optional[str] = None) -> ProjectManager:
    """Load and initialize the project manager."""
    config = get_config().copy()
    if data_file:
        config.data_file_path = data_file
    set_config(config)
    
    data_path = Path(config.data_file_path).expanduser()
    configure_logging(config, base_path=data_path.parent, disable_console=True)
    
    manager = ProjectManager(data_path)
    manager.load()
    return manager


def cmd_projects(args: argparse.Namespace) -> None:
    """List projects or tasks in a specific project."""
    manager = load_manager(args.data_file)
    console = Console(force_terminal=True, force_jupyter=False)

    # If project name provided, show tasks in that project
    if args.project_name:
        # Join multi-word project names
        project_name = ' '.join(args.project_name)

        # Find project by name
        project = None
        for p in manager.projects:
            if p.name.lower() == project_name.lower():
                project = p
                break

        if not project:
            print(f"Project '{project_name}' not found.")
            sys.exit(1)

        # Use the same renderer as the live CLI
        from pm_live.render.project_details import ProjectDetailsRenderer

        # Create context for the renderer
        context = {
            'manager': manager,
            'current_project_id': project.id,
            'selected_index': -1,  # -1 to hide selection/navigation
            'inline_input_mode': False,
            'inline_task_edit_mode': False,
            'collapsed_tasks': set(),
        }

        # Render and print the project details
        renderer = ProjectDetailsRenderer()
        output = renderer.render(context)
        print(output)
        return
    
    # List all projects (Table View)
    console.print("\n[bold white]PROJECTS[/bold white]\n")

    if not manager.projects:
        console.print("    [color(243)]No projects yet[/color(243)]\n")
        return

    all_fields = get_all_fields(manager.default_field_visibility, manager.custom_field_definitions)
    field_by_key = {field.key: field for field in all_fields}

    # Get built-in fields keys that are visible
    builtin_keys = ("timeframe", "priority", "area")
    visible_builtin_keys = [
        k for k in builtin_keys 
        if manager.default_field_visibility.get(k, True)
    ]
    
    # Get custom fields that are visible
    visible_custom_fields = [
        f for f in manager.custom_field_definitions
        if f.key not in builtin_keys and f.visible
    ]
    visible_custom_fields.sort(key=lambda f: getattr(f, "order", 0))

    # Create table - minimal style with no borders
    table = Table(
        box=None,
        show_header=True,
        header_style="",
        border_style="color(238)",
        padding=(0, 2),
    )
    
    # Fixed columns
    table.add_column("", width=1, no_wrap=True) # Selector column (empty in CLI)
    table.add_column("·", justify="center", width=1, no_wrap=True, header_style="color(245)")
    table.add_column("Name", no_wrap=True, header_style="color(245)")
    
    # Track which columns match which keys for value retrieval
    columns_to_render = []
    
    for key in visible_builtin_keys:
        columns_to_render.append((key, key.capitalize()))
        table.add_column(key.capitalize(), no_wrap=True, header_style="color(245)")
        
    for field in visible_custom_fields:
        columns_to_render.append((field.key, field.label))
        table.add_column(field.label, no_wrap=True, header_style="color(245)")
        
    # Progress column
    table.add_column("Progress", no_wrap=True, header_style="color(245)")

    # Separator row
    separator_row = ["", "", ""] + [""] * len(columns_to_render) + [""]
    table.add_row(*separator_row)

    for project in manager.projects:
        status_icon = get_status_icon(project.status)
        status_color = get_status_color(project.status)
        
        status_display = f"[{status_color}]{status_icon}[/{status_color}]"
        name_display = f"[white]{project.name}[/white]"
        
        row_data = [" ", status_display, name_display]
        
        for key, label in columns_to_render:
            # Get value
            value = project.get_field_value(key)
            if value in (None, "") and hasattr(project, key):
                 value = getattr(project, key, None)
            
            # Formatting logic
            formatted_value = str(value) if value is not None else "[color(243)]-[/color(243)]"
            
            if value is None or value == "":
                formatted_value = "[color(243)]-[/color(243)]"
            elif str(value).lower() == "none":
                formatted_value = "[color(243)]-[/color(243)]"
            else:
                # Custom formatting
                # Timeframe bars
                if key == "timeframe":
                    legacy_map = {
                        "Short-Term": "▬",
                        "Medium-Term": "▬ ▬",
                        "Long-Term": "▬ ▬ ▬",
                        "▬▬": "▬ ▬",
                        "▬▬▬": "▬ ▬ ▬",
                    }
                    bar_value = legacy_map.get(value, value)
                    if bar_value in {"▬", "▬ ▬", "▬ ▬ ▬"}:
                        padding = " " * (5 - len(bar_value))
                        formatted_value = f"[cyan]{bar_value}[/cyan]{padding}"
                
                # Check field type if available
                field_def = field_by_key.get(key)
                if field_def:
                     if field_def.field_type == "number" and field_def.number_format == "currency":
                         formatted_value = format_currency_value(value, field_def.currency_symbol)
                     elif field_def.field_type == "number" and field_def.number_format == "percentage":
                         formatted_value = f"{value}%"
                     elif field_def.field_type == "single_select":
                         if field_def.select_options:
                             opt = next((o for o in field_def.select_options if o.value == value), None)
                             if opt and opt.color:
                                 formatted_value = f"[{opt.color}]{value}[/{opt.color}]"
            
            row_data.append(formatted_value)
            
        # Progress
        if not project.tasks:
            progress_display = "[color(240)]-[/color(240)]"
        else:
            percentage = project.progress_percentage()
            filled = int((percentage / 100) * 6)
            empty = 6 - filled
            filled_color = "color(245)"
            empty_color = "color(238)"
            bar = f"[{filled_color}]{'▬' * filled}[/{filled_color}][{empty_color}]{'▭' * empty}[/{empty_color}]"
            progress_display = bar

        row_data.append(progress_display)
        table.add_row(*row_data)

    console.print(table)
    console.print()


def cmd_tasks(args: argparse.Namespace) -> None:
    """List all tasks across all lists, grouped by list."""
    manager = load_manager(args.data_file)
    console = Console(force_terminal=True, force_jupyter=False)

    console.print("\n[bold]Tasks[/bold]\n")

    # Get list tasks - handle both format variations
    list_tasks = getattr(manager, 'list_tasks', {})
    if not list_tasks:
        print("No tasks found.")
        return
    
    def print_task(task, indent=0, show_completed=False):
        # Filter completed tasks based on list settings
        if task.completed is not None and not show_completed:
            return

        # Determine status icon and color based on completion state
        if task.completed is True:
            # Completed task
            status = "[color(238)]✓[/color(238)]"
            style_open = "[color(238)]"
            style_close = "[/color(238)]"
        elif task.completed is False:
            # Failed/Cancelled task
            status = "[color(238)]✗[/color(238)]"
            style_open = "[color(238)]"
            style_close = "[/color(238)]"
        else:
            # Open/Planned task
            status = "[color(243)]○[/color(243)]"
            style_open = ""
            style_close = ""

        prefix = "  " * indent
        
        # Build metadata parts (priority and deadline)
        metadata_parts = []
        if task.priority:
            metadata_parts.append(task.priority)
        if task.deadline:
            deadline_text = format_deadline(task.deadline).strip()
            metadata_parts.append(deadline_text)
        
        metadata_str = " ".join(metadata_parts) if metadata_parts else ""
        if metadata_str:
            metadata_str = f" [color(243)]{metadata_str}[/color(243)]"
        
        console.print(f"{prefix}{status} {style_open}{task.name}{style_close}{metadata_str}")
        for subtask in task.subtasks:
            print_task(subtask, indent + 1, show_completed=show_completed)
    
    # Render each list
    for list_name, sections_data in list_tasks.items():
        # Get custom color for this list, default to white
        list_meta = manager.list_metadata.get(list_name, {})
        list_color = list_meta.get("color", "white")

        # Determine if we should show completed tasks
        # Logic:
        # 1. Default "Tasks" list: Never show completed tasks
        # 2. Custom lists: Show only if done_display is "bottom" or "inline" (not "section")
        done_mode = list_meta.get("show_done_section", "section")
        if isinstance(done_mode, bool):
             done_mode = "section" if done_mode else "inline"

        show_completed = (list_name != "Tasks") and (done_mode in ("bottom", "inline"))

        console.print(f"\n[{list_color}]{list_name}[/{list_color}]")
        
        # Handle both formats: direct list or list of sections
        if sections_data and hasattr(sections_data[0], 'name'):
            # New format: list of Section objects
            for section in sections_data:
                if section.name:
                    console.print(f"  [color(245)]{section.name}[/color(245)]")
                    for task in section.tasks:
                        print_task(task, indent=2 if section.name else 1, show_completed=show_completed)
                else:
                    for task in section.tasks:
                        print_task(task, indent=1, show_completed=show_completed)
        else:
            # Old format: direct task list
            for task in sections_data:
                print_task(task, indent=1, show_completed=show_completed)


def cmd_bookmarks(args: argparse.Namespace) -> None:
    """List bookmarks and bookmark lists."""
    manager = load_manager(args.data_file)
    console = Console(force_terminal=True, force_jupyter=False)
    
    if not manager.bookmarks:
        print("No bookmarks found.")
        return
    
    console.print("\n[bold]Bookmarks[/bold]\n")
    
    for item in manager.bookmarks:
        if isinstance(item, BookmarkList):
            # Display list title
            count = len(item.items)
            console.print(f"  [color(243)]□[/color(243)] [color(245)]{item.title}[/color(245)] [color(243)]{count}[/color(243)]")
            
            # Display bookmarks in this list
            if item.items:
                console.print("[color(238)]  ┌[/color(238)]")
                for i, bookmark in enumerate(item.items):
                    console.print(f"[color(238)]  │[/color(238)]  [color(243)]○[/color(243)] [color(245)]{bookmark.title}[/color(245)]")
                    console.print(f"[color(238)]  │[/color(238)]  [color(236)]{bookmark.url}[/color(236)]")
                console.print("[color(238)]  └[/color(238)]")
        else:
            # Display single bookmark
            console.print(f"  [color(243)]○[/color(243)] [color(245)]{item.title}[/color(245)]")
            console.print(f"  [color(236)]{item.url}[/color(236)]")
        
        console.print()


def cmd_stats(args: argparse.Namespace) -> None:
    """Display the statistics screen."""
    manager = load_manager(args.data_file)

    # Use the same renderer as the live CLI stats screen
    from pm_live.render.statistics import StatisticsRenderer

    # Create context for the renderer
    context = {
        'manager': manager,
        'selected_index': -1,  # -1 to hide the back button
        'list_tasks': getattr(manager, 'list_tasks', {}),
    }

    # Render and print the stats screen
    renderer = StatisticsRenderer()
    output = renderer.render(context)
    print(output)


def cmd_pinned(args: argparse.Namespace) -> None:
    """List all pinned items."""
    manager = load_manager(args.data_file)
    console = Console(force_terminal=True, force_jupyter=False)

    # Refresh pinned metadata to match live UI output
    try:
        if hasattr(manager, "refresh_pinned_metadata"):
            manager.refresh_pinned_metadata()
            if getattr(manager, "_dirty", False):
                manager.save()
    except Exception:
        pass

    pinned_items = manager.metadata.get('pinned_items', [])

    if not pinned_items:
        print("No pinned items.")
        return

    console.print()
    console.print()
    console.print()
    console.print("  [bold]Pinned[/bold]")
    console.print()

    # Group by type
    pinned_projects = [item for item in pinned_items if item.get("type") == "project"]
    pinned_tasks = [item for item in pinned_items if item.get("type") in ("task", "list", "section")]
    pinned_bookmarks = [item for item in pinned_items if item.get("type") in ("bookmark", "bookmark_list")]

    # Border helpers
    left_border = "[color(238)]  │[/color(238)] "
    def left_line(content: str = "") -> str:
        return f"{left_border}{content}"
    def arrow(expanded: bool) -> str:
        return "[color(243)]▾[/color(243)]" if expanded else "[color(238)]▸[/color(238)]"

    console.print("[color(238)]  ┌[/color(238)]")

    # Display pinned projects
    if pinned_projects:
        console.print(left_line("[color(250)]Projects[/color(250)]"))
        for item in pinned_projects:
            project_id = item.get("id")
            project = manager.get_project(project_id)
            if project:
                status_meta = STATUS_META.get(project.status, {})
                status_icon = status_meta.get("icon", "?")

                # Display project name with stats inline
                if project.tasks:
                    percentage = project.progress_percentage()
                    bar = render_progress_bar(percentage, width=6)
                    progress_color = "color(238)" if percentage < 100 else "color(238)"
                    stats_str = f"  [{progress_color}]{bar}[/{progress_color}]"
                else:
                    stats_str = ""

                console.print(left_line(f"[color(243)]{status_icon}[/color(243)] [color(243)]{project.name}[/color(243)]{stats_str}"))
            else:
                fallback = f"Project #{project_id}"
                console.print(left_line(f"[color(243)]?[/color(243)] [color(243)]{fallback}[/color(243)]"))

        # Add separator if there are more sections
        if pinned_tasks or pinned_bookmarks:
            console.print(left_line())

    # Display pinned tasks
    if pinned_tasks:
        console.print(left_line("[color(250)]Tasks[/color(250)]"))
        for item in pinned_tasks:
            item_type = item.get("type")
            if item_type == "task":
                task_name = item.get("name", item.get("id", "Unknown"))
                completed = item.get("completed")
                deadline = item.get("deadline")
                priority = item.get("priority")

                # Status icon matching main_menu.py format
                if completed is True:
                    status_icon = "[color(243)]✓[/color(243)]"
                elif completed is False:
                    status_icon = "[red]✗[/red]"
                else:
                    status_icon = "[color(243)]○[/color(243)]"

                # Build metadata display for priority/deadline if present
                meta_parts = []
                meta_color = "color(238)" if completed is not None else "color(243)"
                if priority:
                    meta_parts.append(f"[{meta_color}]{priority}[/{meta_color}]")
                if deadline:
                    formatted_deadline = format_deadline(deadline).strip()
                    meta_parts.append(f"[{meta_color}]{formatted_deadline}[/{meta_color}]")
                meta_suffix = f"  {' '.join(meta_parts)}" if meta_parts else ""

                name_color = "color(238)" if completed is not None else "color(243)"
                console.print(left_line(f"{status_icon} [{name_color}]{task_name}[/{name_color}]{meta_suffix}"))
            elif item_type == "list":
                list_name = item.get("name", "List")
                expanded = item.get("expanded", False)
                list_arrow = arrow(expanded)

                console.print(left_line(f"  {list_arrow} [color(243)]{list_name}[/color(243)]"))

                if expanded:
                    list_sections = manager.list_tasks.get(list_name, [])
                    for section in list_sections:
                        section_name = getattr(section, 'name', 'Tasks')
                        tasks = getattr(section, 'tasks', [])
                        console.print(left_line(f"    [color(243)]{section_name}[/color(243)]"))
                        for task in tasks:
                            task_name = getattr(task, 'name', 'Task')
                            completed = getattr(task, 'completed', None)
                            # Only show unstarted/unmarked tasks
                            if completed is not None:
                                continue
                            status_icon = "[color(243)]○[/color(243)]"
                            console.print(left_line(f"      {status_icon} [color(243)]{task_name}[/color(243)]"))
            elif item_type == "section":
                section_name = item.get("section_name", "Tasks")
                list_name = item.get("list_name", "")
                section_idx = item.get("section_idx", 0)
                expanded = item.get("expanded", False)
                section_arrow = arrow(expanded)

                console.print(left_line(f"  {section_arrow} [color(243)]{section_name}[/color(243)]"))

                if expanded:
                    list_sections = manager.list_tasks.get(list_name, [])
                    if 0 <= section_idx < len(list_sections):
                        tasks = getattr(list_sections[section_idx], 'tasks', [])
                        for task in tasks:
                            task_name = getattr(task, 'name', 'Task')
                            completed = getattr(task, 'completed', None)
                            # Only show unstarted/unmarked tasks
                            if completed is not None:
                                continue
                            status_icon = "[color(243)]○[/color(243)]"
                            console.print(left_line(f"    {status_icon} [color(243)]{task_name}[/color(243)]"))

        # Add separator if there are more sections
        if pinned_bookmarks:
            console.print(left_line())

    # Display pinned bookmarks
    if pinned_bookmarks:
        console.print(left_line("[color(250)]Bookmarks[/color(250)]"))
        for item in pinned_bookmarks:
            if item.get("type") == "bookmark_list":
                title = item.get("title", "List")
                console.print(left_line(f"[color(243)]□[/color(243)] [color(243)]{title}[/color(243)]"))
            else:
                title = item.get("title", "Untitled")
                url_icon = "[color(243)]↗[/color(243)]"
                console.print(left_line(f"[color(243)]○[/color(243)] [color(243)]{title}[/color(243)]  {url_icon}"))

    # Footer line
    console.print("[color(238)]  └[/color(238)]")
    console.print()



def cmd_day(args: argparse.Namespace) -> None:
    """Display tasks for a specific day (Selected Day calendar tab)."""
    manager = load_manager(args.data_file)
    console = Console(force_terminal=True, force_jupyter=False)

    from datetime import datetime
    import calendar as cal_module
    from pm_live.utils.calendar import collect_deadline_map

    # Get current date as default
    now = datetime.now()
    year = now.year
    month = now.month

    # If day argument provided, validate it
    if args.day is not None:
        day = args.day
        # Validate day is valid for current month
        max_day = cal_module.monthrange(year, month)[1]
        if day < 1 or day > max_day:
            console.print(f"[red]Error: Day {day} is not valid for {cal_module.month_name[month]} {year} (1-{max_day})[/red]")
            sys.exit(1)
    else:
        day = now.day

    # Get list tasks
    list_tasks_map = getattr(manager, 'list_tasks', {})

    # Collect deadline map
    deadline_map = collect_deadline_map(manager, list_tasks_map)

    # Get tasks for selected day
    date_key = f"{year:04d}-{month:02d}-{day:02d}"
    tasks_for_day = deadline_map.get(date_key, [])

    # Format date label
    day_name = datetime(year, month, day).strftime("%A")
    if day == now.day and month == now.month and year == now.year:
        date_label = f"Today ({day_name}, {cal_module.month_name[month]} {day})"
    else:
        date_label = f"{day_name}, {cal_module.month_name[month]} {day}, {year}"

    # Print header
    console.print()
    console.print(f"  [bold]{date_label}[/bold]  [color(243)]{len(tasks_for_day)} {'item' if len(tasks_for_day) == 1 else 'items'}[/color(243)]")
    console.print()

    if not tasks_for_day:
        console.print("  [color(243)]No tasks or deadlines on this day[/color(243)]")
        console.print()
        return

    # Render each task/entry
    for entry in tasks_for_day:
        task = entry.item if entry.kind == "task" else None
        project = entry.item if entry.kind == "project_field" else None

        # Determine status icon
        if task is not None:
            completed = getattr(task, "completed", None)
            if completed is True:
                status_icon = "[color(238)]✓[/color(238)]"
            elif completed is False:
                status_icon = "[color(238)]✗[/color(238)]"
            else:
                status_icon = "[color(243)]○[/color(243)]"
        else:
            from pm_live.utils import get_status_icon
            status_icon = get_status_icon(getattr(project, "status", None))
            status_icon = f"[color(243)]{status_icon}[/color(243)]"

        # Get name
        if task is not None:
            name = getattr(task, "name", "Untitled")
            completed = getattr(task, "completed", None)
            name_color = "color(238)" if completed is not None else "color(243)"
        else:
            name = getattr(project, "name", "Untitled")
            name_color = "color(243)"

        # Build metadata
        metadata_parts = []
        if task is not None:
            priority = getattr(task, "priority", None)
            if priority:
                metadata_parts.append(priority)

            # Add project name if task is in a project
            if entry.project_name:
                metadata_parts.append(f"({entry.project_name})")
        elif project is not None:
            field_label = entry.field_label or "Date"
            metadata_parts.append(f"({field_label})")

        meta_suffix = ""
        if metadata_parts:
            meta_content = " · ".join(metadata_parts)
            meta_suffix = f"  [color(238)]{meta_content}[/color(238)]"

        console.print(f"  {status_icon} [{name_color}]{name}[/{name_color}]{meta_suffix}")

        # Show notes if present and task
        if task is not None:
            notes = getattr(task, "notes", None)
            if notes:
                from rich.markup import escape as rich_escape
                escaped = rich_escape(notes).replace("\r\n", "\n").replace("\r", "\n")
                escaped = escaped.replace("\n", "\n    ")
                console.print(f"    [color(238)]{escaped}[/color(238)]")

    console.print()


def cmd_overdue(args: argparse.Namespace) -> None:
    """Display overdue tasks and project deadlines (Overdue calendar tab)."""
    manager = load_manager(args.data_file)
    console = Console(force_terminal=True, force_jupyter=False)

    from datetime import datetime
    from pm_live.utils.calendar import collect_overdue_entries

    # Get list tasks
    list_tasks_map = getattr(manager, 'list_tasks', {})

    # Collect overdue entries (capped at 20, returns (entry, days_overdue) tuples)
    overdue_data = collect_overdue_entries(manager, list_tasks_map, max_items=20)

    # Get total count (for "... and N more" display)
    # We need to collect all to get the true count
    all_overdue = collect_overdue_entries(manager, list_tasks_map, max_items=None)
    total_count = len(all_overdue)

    # Print header
    console.print()
    console.print(f"  [bold]Overdue[/bold]  [color(243)]{len(overdue_data)} {'item' if len(overdue_data) == 1 else 'items'}[/color(243)]")
    console.print()

    if not overdue_data:
        console.print("  [color(243)]No overdue items[/color(243)]")
        console.print()
        return

    # Render each overdue entry
    for entry, days_overdue in overdue_data:
        task = entry.item if entry.kind == "task" else None
        project = entry.item if entry.kind == "project_field" else None

        # Determine status icon
        if task is not None:
            completed = getattr(task, "completed", None)
            if completed is True:
                status_icon = "[color(238)]✓[/color(238)]"
            elif completed is False:
                status_icon = "[color(238)]✗[/color(238)]"
            else:
                status_icon = "[color(243)]○[/color(243)]"
        else:
            from pm_live.utils import get_status_icon
            status_icon = get_status_icon(getattr(project, "status", None))
            status_icon = f"[color(243)]{status_icon}[/color(243)]"

        # Get name
        if task is not None:
            name = getattr(task, "name", "Untitled")
            completed = getattr(task, "completed", None)
            name_color = "color(238)" if completed is not None else "color(243)"
        else:
            name = getattr(project, "name", "Untitled")
            name_color = "color(243)"

        # Build metadata
        metadata_parts = []

        # Days overdue (always show)
        days_word = "day" if days_overdue == 1 else "days"
        metadata_parts.append(f"{days_overdue} {days_word} overdue")

        if task is not None:
            priority = getattr(task, "priority", None)
            if priority:
                metadata_parts.append(priority)

            # Add project name if task is in a project
            if entry.project_name:
                metadata_parts.append(f"({entry.project_name})")
        elif project is not None:
            field_label = entry.field_label or "Date"
            metadata_parts.append(f"({field_label})")

        meta_suffix = ""
        if metadata_parts:
            meta_content = " · ".join(metadata_parts)
            meta_suffix = f"  [color(238)]{meta_content}[/color(238)]"

        console.print(f"  {status_icon} [{name_color}]{name}[/{name_color}]{meta_suffix}")

        # Show notes if present and task
        if task is not None:
            notes = getattr(task, "notes", None)
            if notes:
                from rich.markup import escape as rich_escape
                escaped = rich_escape(notes).replace("\r\n", "\n").replace("\r", "\n")
                escaped = escaped.replace("\n", "\n    ")
                console.print(f"    [color(238)]{escaped}[/color(238)]")

    # Show "... and N more" if truncated
    if total_count > len(overdue_data):
        remaining = total_count - len(overdue_data)
        console.print()
        console.print(f"  [color(238)]... and {remaining} more overdue[/color(238)]")

    console.print()


def cmd_upcoming(args: argparse.Namespace) -> None:
    """Display upcoming tasks and project deadlines (Upcoming calendar tab)."""
    manager = load_manager(args.data_file)
    console = Console(force_terminal=True, force_jupyter=False)

    from datetime import datetime
    from pm_live.utils.calendar import collect_upcoming_entries

    # Get list tasks
    list_tasks_map = getattr(manager, 'list_tasks', {})

    # Collect upcoming entries organized by time period
    upcoming_data = collect_upcoming_entries(manager, list_tasks_map)

    # Calculate total count
    total_count = sum(len(entries) for entries in upcoming_data.values())

    # Print header
    console.print()
    console.print(f"  [bold]Upcoming[/bold]  [color(243)]{total_count} {'item' if total_count == 1 else 'items'}[/color(243)]")
    console.print()

    if total_count == 0:
        console.print("  [color(243)]No upcoming tasks or deadlines[/color(243)]")
        console.print()
        return

    # Section configuration
    sections = [
        ("today", "Today"),
        ("next_week", "Next Week"),
        ("next_month", "Next Month"),
    ]

    first_section = True
    for section_key, section_label in sections:
        entries = upcoming_data.get(section_key, [])
        if not entries:
            continue

        # Add blank line between sections
        if not first_section:
            console.print()
        first_section = False

        # Section header with count
        count = len(entries)
        console.print(f"  [bold]{section_label}[/bold]  [color(243)]{count}[/color(243)]")
        console.print()

        # Render each entry in this section
        for entry in entries:
            task = entry.item if entry.kind == "task" else None
            project = entry.item if entry.kind == "project_field" else None

            # Determine status icon
            if task is not None:
                completed = getattr(task, "completed", None)
                if completed is True:
                    status_icon = "[color(238)]✓[/color(238)]"
                elif completed is False:
                    status_icon = "[color(238)]✗[/color(238)]"
                else:
                    status_icon = "[color(243)]○[/color(243)]"
            else:
                from pm_live.utils import get_status_icon
                status_icon = get_status_icon(getattr(project, "status", None))
                status_icon = f"[color(243)]{status_icon}[/color(243)]"

            # Get name
            if task is not None:
                name = getattr(task, "name", "Untitled")
                completed = getattr(task, "completed", None)
                name_color = "color(238)" if completed is not None else "color(243)"
            else:
                name = getattr(project, "name", "Untitled")
                name_color = "color(243)"

            # Build metadata
            metadata_parts = []

            # For "Next Week" and "Next Month" sections, show the deadline date
            if section_key in ("next_week", "next_month"):
                deadline = None
                if task is not None:
                    deadline = getattr(task, "deadline", None)
                elif project is not None:
                    # Get the custom field value
                    field_key = entry.field_key
                    if field_key:
                        custom_values = getattr(project, "custom_field_values", {}) or {}
                        deadline = custom_values.get(field_key, getattr(project, field_key, None))

                if deadline:
                    from pm_live.utils import format_deadline
                    deadline_text = format_deadline(deadline).strip()
                    metadata_parts.append(deadline_text)

            if task is not None:
                priority = getattr(task, "priority", None)
                if priority:
                    metadata_parts.append(priority)

                # Add project name if task is in a project
                if entry.project_name:
                    metadata_parts.append(f"({entry.project_name})")
            elif project is not None:
                field_label = entry.field_label or "Date"
                metadata_parts.append(f"({field_label})")

            meta_suffix = ""
            if metadata_parts:
                meta_content = " · ".join(metadata_parts)
                meta_suffix = f"  [color(238)]{meta_content}[/color(238)]"

            console.print(f"    {status_icon} [{name_color}]{name}[/{name_color}]{meta_suffix}")

            # Show notes if present and task
            if task is not None:
                notes = getattr(task, "notes", None)
                if notes:
                    from rich.markup import escape as rich_escape
                    escaped = rich_escape(notes).replace("\r\n", "\n").replace("\r", "\n")
                    escaped = escaped.replace("\n", "\n      ")
                    console.print(f"      [color(238)]{escaped}[/color(238)]")

    console.print()


def cmd_add(args: argparse.Namespace) -> None:
    """Add a new task."""
    manager = load_manager(args.data_file)
    console = Console(force_terminal=True, force_jupyter=False)

    # Join task name parts
    task_name = ' '.join(args.task_name)

    # Validate priority if provided
    priority = args.priority
    if priority and priority not in ['!', '!!', '!!!']:
        console.print("[red]Error: Priority must be one of: ! !! !!![/red]")
        sys.exit(1)

    # Create the task
    from pm import Task
    task = Task(name=task_name, priority=priority)

    # Determine which list to add to
    list_name = args.list if args.list else "Tasks"
    list_tasks = getattr(manager, 'list_tasks', {})

    if list_name not in list_tasks:
        # Create the list if it doesn't exist
        from pm import Section
        list_tasks[list_name] = [Section(name="", tasks=[])]
        manager.list_tasks = list_tasks

    # Add to the first section (unnamed section)
    if list_tasks[list_name] and hasattr(list_tasks[list_name][0], 'tasks'):
        list_tasks[list_name][0].tasks.append(task)
    else:
        # Fallback for old format
        list_tasks[list_name].append(task)

    # Mark as modified and save
    manager.mark_list_tasks_modified()
    manager.save()

    # Confirmation message
    priority_str = f" with priority {priority}" if priority else ""
    list_str = f" to list '{list_name}'" if list_name != "Tasks" else ""
    console.print(f"[green]✓[/green] Added task: {task_name}{priority_str}{list_str}")


def cmd_live(args: argparse.Namespace) -> None:
    """Launch the interactive live interface."""
    config = get_config().copy()
    if args.data_file:
        config.data_file_path = args.data_file
    set_config(config)
    
    data_file = Path(config.data_file_path).expanduser()
    configure_logging(config, base_path=data_file.parent, disable_console=True)
    
    from pm_live import LiveCLI
    manager = ProjectManager(data_file)
    cli = LiveCLI(manager)
    
    try:
        cli.run()
    except KeyboardInterrupt:
        pass
    finally:
        manager.force_save()


def print_custom_help() -> None:
    """Print custom styled help message."""
    console = Console(force_terminal=True, force_jupyter=False)
    
    console.print()
    console.print("  [bold]Project Manager[/bold]")
    console.print("  [color(243)]Manage projects, tasks, and bookmarks[/color(243)]")
    console.print()
    
    # Commands section
    console.print("  [color(245)]Commands[/color(245)]")
    console.print()
    
    commands = [
        ("live", "Launch interactive interface", "default"),
        ("projects", "List projects", None),
        ("projects <name>", "Show project details", None),
        ("tasks", "List tasks by list", None),
        ("bookmarks", "List bookmarks", None),
        ("stats", "Show statistics", None),
        ("pinned", "Show pinned items", None),
        ("day", "Show tasks for today", None),
        ("day <num>", "Show tasks for day in month", None),
        ("overdue", "Show overdue tasks", None),
        ("upcoming", "Show upcoming tasks", None),
        ("add <task>", "Add a new task", None),
    ]
    
    for cmd, desc, note in commands:
        note_str = f" [color(243)]({note})[/color(243)]" if note else ""
        console.print(f"    [cyan]{cmd:<14}[/cyan] [color(245)]{desc}[/color(245)]{note_str}")
    
    console.print()
    
    # Options section
    console.print("  [color(245)]Options[/color(245)]")
    console.print()
    
    options = [
        ("-h", "Show help"),
        ("-d <file>", "Use custom data file"),
    ]
    
    for opt, desc in options:
        console.print(f"    [cyan]{opt:<14}[/cyan] [color(245)]{desc}[/color(245)]")
    
    console.print()
    
    # Add task options
    console.print("  [color(245)]Add Options[/color(245)]")
    console.print()
    
    add_options = [
        ("-p <priority>", "Set priority: [red]!!![/red] [yellow]!![/yellow] [green]![/green]"),
        ("-l <list>", "Target list"),
    ]
    
    for opt, desc in add_options:
        console.print(f"    [cyan]{opt:<14}[/cyan] [color(245)]{desc}[/color(245)]")
    
    console.print()


def main(argv: Optional[list[str]] = None) -> None:
    """Main CLI dispatcher."""
    # Check for help flag before argparse
    if argv is None:
        argv = sys.argv[1:]
    
    if '-h' in argv or '--help' in argv:
        # Only show custom help for main help, not subcommand help
        if len(argv) == 1 or (len(argv) == 2 and argv[0] in ['-h', '--help']):
            print_custom_help()
            return
    
    parser = argparse.ArgumentParser(
        description="Project Manager",
        prog="pm",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True
    )
    parser.add_argument(
        "-d", "--data-file",
        dest="data_file",
        help="Path to projects data file (overrides config)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Live command (default)
    live_parser = subparsers.add_parser("live", help="Launch interactive interface")
    live_parser.set_defaults(func=cmd_live)
    
    # List projects
    projects_parser = subparsers.add_parser("projects", help="List projects or tasks in a project")
    projects_parser.add_argument("project_name", nargs="*", help="Project name (optional, supports multi-word names)")
    projects_parser.set_defaults(func=cmd_projects)
    
    # List all tasks
    tasks_parser = subparsers.add_parser("tasks", help="List all tasks grouped by list")
    tasks_parser.set_defaults(func=cmd_tasks)
    
    # List bookmarks
    bookmarks_parser = subparsers.add_parser("bookmarks", help="List bookmarks and bookmark lists")
    bookmarks_parser.set_defaults(func=cmd_bookmarks)
    
    # Stats
    stats_parser = subparsers.add_parser("stats", help="Display statistics")
    stats_parser.set_defaults(func=cmd_stats)
    
    # Pinned items
    pinned_parser = subparsers.add_parser("pinned", help="List pinned items")
    pinned_parser.set_defaults(func=cmd_pinned)

    # Day view
    day_parser = subparsers.add_parser("day", help="Show tasks for a specific day")
    day_parser.add_argument("day", nargs="?", type=int, help="Day number (1-31, defaults to today)")
    day_parser.set_defaults(func=cmd_day)

    # Overdue view
    overdue_parser = subparsers.add_parser("overdue", help="Show overdue tasks and deadlines")
    overdue_parser.set_defaults(func=cmd_overdue)

    # Upcoming view
    upcoming_parser = subparsers.add_parser("upcoming", help="Show upcoming tasks and deadlines")
    upcoming_parser.set_defaults(func=cmd_upcoming)

    # Add task
    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("task_name", nargs="+", help="Task name")
    add_parser.add_argument("-p", "--priority", choices=["!", "!!", "!!!"], help="Task priority (!, !!, or !!!)")
    add_parser.add_argument("-l", "--list", help="List name to add task to (default: Tasks)")
    add_parser.set_defaults(func=cmd_add)

    # Parse arguments
    args = parser.parse_args(argv)
    
    # If no command specified, launch live interface
    if not args.command:
        args.func = cmd_live
    
    # Execute command
    if hasattr(args, 'func'):
        try:
            args.func(args)
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(130)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
