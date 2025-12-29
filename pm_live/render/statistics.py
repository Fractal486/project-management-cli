"""Statistics renderer."""

from .base import BaseRenderer
from ..utils import get_stats, get_status_icon, get_status_color
from ..tasks import collect_all_tasks
from pm import STATUS_DISPLAY_ORDER, STATUS_STAT_KEYS


class StatisticsRenderer(BaseRenderer):
    """Renderer for statistics view."""

    def render(self, context: dict) -> str:
        """Render statistics view."""
        self._reset_console_buffer()

        manager = context['manager']
        selected_index = context.get('selected_index', 0)

        self._console.print("\n[bold]Stats[/bold]")

        # === PROJECTS OVERVIEW ===
        stats = get_stats(manager.projects)
        total_projects = stats.get("total", 0)

        # Left-side border helper (angled start/end markers)
        left_border = "[color(238)]  │[/color(238)] "
        def header_line(title: str) -> str:
            return f"[color(238)]  ┌[/color(238)] [color(250)]{title}[/color(250)]"
        def footer_line() -> str:
            return "[color(238)]  └[/color(238)]"

        def left_line(content: str = "") -> str:
            return f"{left_border}{content}"

        self._console.print()
        self._console.print(header_line("Projects"))
        self._console.print(left_line())

        if total_projects > 0:
            # Render each status as a clean row with mini progress bar
            max_count = max(stats.get(STATUS_STAT_KEYS[s], 0) for s in STATUS_DISPLAY_ORDER)

            for status in STATUS_DISPLAY_ORDER:
                stat_key = STATUS_STAT_KEYS[status]
                count = stats.get(stat_key, 0)
                color = get_status_color(status)
                icon = get_status_icon(status)

                # Create a subtle mini bar (width proportional to count)
                bar_width = 12
                if max_count > 0:
                    filled = int((count / max_count) * bar_width)
                else:
                    filled = 0
                bar = "▄" * filled + "[color(238)]▁[/color(238)]" * (bar_width - filled)

                # Clean row: icon, status name, bar, count
                self._console.print(left_line(f"[{color}]{icon}[/{color}] [color(250)]{status:<12}[/color(250)] [{color}]{bar}[/{color}]  [color(243)]{count}[/color(243)]"))

            self._console.print(left_line())
            self._console.print(left_line())

            # Total and completion stats
            total_project_tasks = sum(p.count_total_tasks() for p in manager.projects)
            completed_project_tasks = sum(p.count_completed_tasks() for p in manager.projects)
            task_pct = int((completed_project_tasks / max(total_project_tasks, 1)) * 100)

            self._console.print(left_line(f"[color(243)]Total[/color(243)]  [white]{total_projects}[/white]"))
            if total_project_tasks > 0:
                self._console.print(left_line(f"[color(243)]Tasks[/color(243)]  [white]{completed_project_tasks}[/white][color(243)]/{total_project_tasks} ({task_pct}%)[/color(243)]"))
            self._console.print(left_line())

            # Top 3 projects by completion (excluding 100%)
            projects_with_progress = []
            for project in manager.projects:
                total_tasks = project.count_total_tasks()
                if total_tasks > 0:
                    completed_tasks = project.count_completed_tasks()
                    completion_pct = int((completed_tasks / total_tasks) * 100)
                    if completion_pct < 100:
                        projects_with_progress.append((project.name, completion_pct))

            if projects_with_progress:
                self._console.print(left_line())
                self._console.print(left_line())
                # Sort by percentage (highest first) and take top 3
                projects_with_progress.sort(key=lambda x: x[1], reverse=True)
                for name, pct in projects_with_progress[:3]:
                    # Show a complete progress bar with filled and unfilled portions
                    prog_bar_width = 10
                    filled = int(pct / 10)  # 0-10 dots
                    unfilled = prog_bar_width - filled
                    bar = "[green]•[/green]" * filled + "[color(238)]•[/color(238)]" * unfilled
                    # Truncate name if too long
                    display_name = name[:20] + "..." if len(name) > 20 else name
                    self._console.print(left_line(f"{bar} [color(245)]{display_name}[/color(245)] [color(243)]{pct}%[/color(243)]"))
        else:
            self._console.print(left_line("[color(243)]No projects yet[/color(243)]"))

        self._console.print(footer_line())

        # === STANDALONE TASKS ===
        self._console.print()
        self._console.print()
        self._console.print()
        self._console.print(header_line("Tasks"))
        self._console.print(left_line())

        # Get all tasks from all lists
        list_tasks_map = context.get('list_tasks', {"Tasks": getattr(manager, 'standalone_tasks', [])})
        all_tasks = []
        for _, sections in list_tasks_map.items():
            if not sections or not isinstance(sections, list):
                continue

            first = sections[0]
            looks_like_section = (
                (isinstance(first, dict) and 'tasks' in first)
                or hasattr(first, 'tasks')
            )

            if looks_like_section:
                for section in sections:
                    section_tasks = section.tasks if hasattr(section, 'tasks') else section.get('tasks', [])
                    all_tasks.extend(section_tasks)
            else:
                # Flat list of Task objects
                all_tasks.extend(sections)

        # Flatten nested tasks
        all_flat_tasks = collect_all_tasks(all_tasks)
        total_standalone = len(all_flat_tasks)

        if total_standalone > 0:
            standalone_done = sum(1 for t in all_flat_tasks if t.completed is True)
            standalone_pending = sum(1 for t in all_flat_tasks if t.completed is None)
            standalone_failed = sum(1 for t in all_flat_tasks if t.completed is False)
            standalone_pct = int((standalone_done / max(total_standalone, 1)) * 100)

            # Elegant segmented progress bar
            bar_width = 24
            done_width = int((standalone_done / total_standalone) * bar_width)
            pending_width = int((standalone_pending / total_standalone) * bar_width)
            failed_width = bar_width - done_width - pending_width

            bar = ""
            if done_width > 0:
                bar += f"[green]{'━' * done_width}[/green]"
            if pending_width > 0:
                bar += f"[color(243)]{'━' * pending_width}[/color(243)]"
            if failed_width > 0:
                bar += f"[red]{'━' * failed_width}[/red]"

            self._console.print(left_line(f"{bar}  [color(243)]{standalone_pct}%[/color(243)]"))
            self._console.print(left_line())

            # Stats row - always show all statuses, reusing task list icons (done/none/failed)
            self._console.print(left_line(f"[green]✓[/green] [color(243)]{standalone_done}[/color(243)]   [color(243)]○[/color(243)] [color(243)]{standalone_pending}[/color(243)]   [red]✗[/red] [color(243)]{standalone_failed}[/color(243)]"))
            self._console.print(left_line())
            self._console.print(left_line())

            # Priority breakdown (standard !/!!/!!! labels only)
            def classify_priority(raw_priority):
                if raw_priority is None:
                    return "none"
                if isinstance(raw_priority, str):
                    value = raw_priority.strip()
                    symbol_map = {"!!!": "high", "!!": "medium", "!": "low", "none": "none", "None": "none", "": "none"}
                    if value in symbol_map:
                        return symbol_map[value]
                return "none"

            priority_high = 0
            priority_medium = 0
            priority_low = 0
            priority_none = 0
            for task in all_flat_tasks:
                bucket = classify_priority(getattr(task, "priority", None))
                if bucket == "high":
                    priority_high += 1
                elif bucket == "medium":
                    priority_medium += 1
                elif bucket == "low":
                    priority_low += 1
                else:
                    priority_none += 1

            # Priority bar - segmented by priority level
            bar_width = 24
            high_width = int((priority_high / total_standalone) * bar_width)
            medium_width = int((priority_medium / total_standalone) * bar_width)
            low_width = int((priority_low / total_standalone) * bar_width)
            none_width = bar_width - high_width - medium_width - low_width

            priority_bar = ""
            if high_width > 0:
                priority_bar += f"[color(167)]{'▄' * high_width}[/color(167)]"  # Muted red
            if medium_width > 0:
                priority_bar += f"[color(179)]{'▄' * medium_width}[/color(179)]"  # Muted yellow/gold
            if low_width > 0:
                priority_bar += f"[color(108)]{'▄' * low_width}[/color(108)]"  # Muted green
            if none_width > 0:
                priority_bar += f"[color(238)]{'▄' * none_width}[/color(238)]"

            self._console.print(left_line(priority_bar))
            self._console.print(left_line())
            self._console.print(left_line(f"[red]!!![/red] [color(243)]{priority_high}[/color(243)]   [yellow]!![/yellow] [color(243)]{priority_medium}[/color(243)]   [green]![/green] [color(243)]{priority_low}[/color(243)]   [color(238)]-[/color(238)] [color(243)]{priority_none}[/color(243)]"))
            self._console.print(left_line())

            # Top 3 highest priority tasks (by priority level, excluding tasks without priority)
            priority_order = {"high": 0, "medium": 1, "low": 2, "none": 3}
            tasks_with_priority = []
            for task in all_flat_tasks:
                bucket = classify_priority(getattr(task, "priority", None))
                # Only include tasks that have an actual priority (not "none")
                if bucket != "none":
                    tasks_with_priority.append((task, priority_order[bucket], bucket))

            # Sort by priority level
            tasks_with_priority.sort(key=lambda x: x[1])

            if tasks_with_priority:
                self._console.print(left_line())
                self._console.print(left_line("[color(243)]Highest Priority[/color(243)]"))
                for task, _, bucket in tasks_with_priority[:3]:
                    task_name = getattr(task, 'name', 'Untitled')
                    # Truncate long names
                    if len(task_name) > 36:
                        task_name = task_name[:33] + "..."

                    # Display with appropriate priority indicator
                    if bucket == "high":
                        indicator = "[red]!!![/red]"
                    elif bucket == "medium":
                        indicator = "[yellow]!![/yellow]"
                    elif bucket == "low":
                        indicator = "[green]![/green]"
                    else:
                        indicator = "[color(238)]-[/color(238)]"

                    self._console.print(left_line(f"  {indicator} [color(245)]{task_name}[/color(245)]"))
                self._console.print(left_line())

            # Top 3 tasks with closest deadlines
            from datetime import datetime
            tasks_with_deadlines = []
            for task in all_flat_tasks:
                deadline = getattr(task, 'deadline', None)
                if deadline:
                    try:
                        if isinstance(deadline, str):
                            deadline_date = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
                        else:
                            deadline_date = deadline
                        tasks_with_deadlines.append((task, deadline_date))
                    except:
                        pass

            if tasks_with_deadlines:
                # Sort by deadline (soonest first)
                tasks_with_deadlines.sort(key=lambda x: x[1])
                self._console.print(left_line())
                self._console.print(left_line("[color(243)]Closest Deadlines[/color(243)]"))
                for task, deadline_date in tasks_with_deadlines[:3]:
                    task_name = getattr(task, 'name', 'Untitled')
                    # Truncate long names
                    if len(task_name) > 28:
                        task_name = task_name[:25] + "..."

                    # Format deadline as relative or absolute
                    now = datetime.now(deadline_date.tzinfo) if deadline_date.tzinfo else datetime.now()
                    # Compare dates only, not times
                    days_until = (deadline_date.date() - now.date()).days

                    if days_until < 0:
                        deadline_str = f"[red]{abs(days_until)}d overdue[/red]"
                    elif days_until == 0:
                        deadline_str = "[yellow]today[/yellow]"
                    elif days_until == 1:
                        deadline_str = "[yellow]tomorrow[/yellow]"
                    elif days_until < 7:
                        deadline_str = f"[color(243)]in {days_until}d[/color(243)]"
                    else:
                        date_label = deadline_date.strftime("%Y %b %d")
                        deadline_str = f"[color(243)]{date_label}[/color(243)]"

                    self._console.print(left_line(f"  [color(243)]◷[/color(243)] [color(245)]{task_name}[/color(245)]  {deadline_str}"))
                self._console.print(left_line())
        else:
            self._console.print(left_line("[color(243)]No tasks yet[/color(243)]"))

        self._console.print(footer_line())

        # === BOOKMARKS ===
        self._console.print()
        self._console.print()
        self._console.print()
        self._console.print(header_line("Bookmarks"))
        self._console.print(left_line())

        from pm import BookmarkList
        bookmarks = getattr(manager, 'bookmarks', [])

        total_bookmarks = 0
        num_lists = 0
        standalone_bm = 0

        for item in bookmarks:
            if isinstance(item, BookmarkList):
                num_lists += 1
                total_bookmarks += len(getattr(item, "items", []))
            else:
                standalone_bm += 1
                total_bookmarks += 1

        # Total bookmarks should only count bookmark items, not lists themselves
        total_items = total_bookmarks

        if total_bookmarks > 0 or num_lists > 0:
            # Simple count display
            self._console.print(left_line(f"[color(243)]Total[/color(243)]  [white]{total_bookmarks}[/white]"))
            if num_lists > 0:
                self._console.print(left_line(f"[color(243)]Lists[/color(243)]  [white]{num_lists}[/white]"))
            if standalone_bm > 0:
                self._console.print(left_line(f"[color(243)]Loose[/color(243)]  [white]{standalone_bm}[/white]"))
        else:
            self._console.print(left_line("[color(243)]No bookmarks yet[/color(243)]"))

        self._console.print(footer_line())

        # Pad to push back button to bottom
        self._pad_to_bottom()

        # Back action (skip if selected_index is -1, e.g., when called from command line)
        if selected_index >= 0:
            if selected_index == 0:
                self._console.print("  [white]›[/white] [yellow]←[/yellow] Back")
            else:
                self._console.print("    [color(245)]←[/color(245)] [color(245)]Back[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()
