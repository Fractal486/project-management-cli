"""Renderer for project selection menu when moving tasks."""

from pm import STATUS_META
from .base import BaseRenderer


class ProjectSelectionRenderer(BaseRenderer):
    """Renderer for project selection menu."""

    def render(self, context: dict) -> str:
        """Render the project selection menu."""
        self._reset_console_buffer()
        
        manager = context.get("manager")
        selected_index = context.get("selected_index", 0)
        move_task_source = context.get("move_task_source")

        if not move_task_source:
            self._console.print()
            self._console.print("  [red]Error: No task source information[/red]")
            return self._get_console_output()

        task = move_task_source.get("task")
        task_name = getattr(task, "name", "Unknown Task")

        # Get all projects
        projects = manager.projects if manager else []

        # HEADER
        self._console.print()
        self._console.print("  [bold]Move Task to Project[/bold]")
        self._console.print(f"  [color(243)]{task_name}[/color(243)]")
        self._console.print()

        # Check if moving from a project (to show "Move to Tasks" option)
        source_project_id = move_task_source.get("project_id")
        is_from_project = source_project_id is not None
        
        if not projects and not is_from_project:
            # Empty state - no projects and can't move to tasks
            self._console.print("  [color(243)]No projects available. Create a project first.[/color(243)]")
        else:
            # CONTENT - Bordered box with project list
            left_border = "[color(238)]  │[/color(238)] "
            self._console.print("[color(238)]  ┌[/color(238)]")

            for idx, project in enumerate(projects):
                is_selected = idx == selected_index

                # Get status icon and color
                status_meta = STATUS_META.get(project.status, {})
                status_icon = status_meta.get("icon", "?")
                status_color = status_meta.get("color", "white")
                
                if is_selected:
                    selector = "[cyan]›[/cyan] "
                    icon_display = f"[{status_color}]{status_icon}[/{status_color}]"
                    name_display = project.name
                else:
                    selector = "  "
                    icon_display = f"[color(243)]{status_icon}[/color(243)]"
                    name_display = f"[color(245)]{project.name}[/color(245)]"
                
                self._console.print(f"{left_border}{selector}{icon_display} {name_display}")

            # Add "Move to Tasks" option if moving from a project (separated from projects)
            if is_from_project:
                # Add blank line separator
                self._console.print(f"{left_border}")
                
                tasks_option_index = len(projects)
                is_selected = tasks_option_index == selected_index
                
                if is_selected:
                    selector = "[cyan]›[/cyan] "
                    name = "Move to Tasks"
                else:
                    selector = "  "
                    name = "[color(245)]Move to Tasks[/color(245)]"
                
                self._console.print(f"{left_border}{selector}{name}")

            self._console.print("[color(238)]  └[/color(238)]")

        # ACTIONS - Pushed to bottom
        self._pad_to_bottom()
        
        if not projects:
            # Show escape hint for empty state
            self._console.print("    [color(245)]← Cancel[/color(245)]")
        
        self._render_status_message(context)
        return self._get_console_output()
