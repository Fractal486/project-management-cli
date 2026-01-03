"""Settings renderer."""

from ..quick_stats import QUICK_STATS, QUICK_STATS_ORDER
from ..main_menu_tabs import MAIN_MENU_TABS, MAIN_MENU_TABS_ORDER
from .base import BaseRenderer
from ..states import AppState


class SettingsRenderer(BaseRenderer):
    """Renderer for settings view."""

    def render(self, context: dict) -> str:
        """Render settings view."""
        self._reset_console_buffer()

        selected_index = context['selected_index']
        text_input_buffer = context.get('text_input_buffer', '')
        text_input_cursor = context.get('text_input_cursor', len(text_input_buffer))
        quick_stats_selection = context.get('quick_stats_selection', set())
        main_menu_tabs_selection = context.get('main_menu_tabs_selection', set())


        # HEADER SECTION
        self._console.print()
        self._console.print("  [bold]Settings[/bold]")
        self._console.print("  [color(243)]Manage your CLI preferences[/color(243)]")
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

        settings_items = [
            ("Clear Completed Tasks", "clear_completed"),
            ("Configure Quick Stats", "quick_stats"),
            ("Configure Main Menu Tabs", "main_menu_tabs"),
            ("Deadline Display Mode", "deadline_display"),
            ("Task Metadata Display", "task_metadata"),
            ("Project Browser Default Tab", "project_browser_tab"),
            ("Status Message Display", "message_display"),
            ("Show 'None' in Project Stats", "stats_none_toggle"),
            ("Bookmark Action Mode", "bookmark_action"),
            ("Export Data", "export_data"),
            ("Clear Logs", "clear_logs"),
            ("Press 'h' to open keybindings overlay", "help_overlay"),
        ]

        self._console.print(header_line())

        for i, (label, action) in enumerate(settings_items):
            is_selected = i == selected_index
            selector = "[white]›[/white] " if is_selected else "  "

            # Dim unselected items
            if is_selected:
                self._console.print(left_line(f"{selector}{label}"))
            else:
                self._console.print(left_line(f"{selector}[color(245)]{label}[/color(245)]"))

        self._console.print(footer_line())

        # ACTION SECTION (pushed to bottom)
        self._pad_to_bottom()

        # Back
        if selected_index == len(settings_items):
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Back")
        else:
            self._console.print("    [color(245)]← Back[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class QuickStatsSettingsRenderer(BaseRenderer):
    """Renderer for configuring quick stats metrics."""

    def render(self, context: dict) -> str:
        """Render the quick stats configuration screen."""
        self._reset_console_buffer()

        selected_index = context['selected_index']
        quick_stats_selection = context.get('quick_stats_selection', set())

        metrics = list(QUICK_STATS_ORDER)

        self._console.print()
        self._console.print("  [bold]Quick Stats[/bold]")
        self._console.print("  [color(243)]Toggle which metrics appear on the main menu quick stats line[/color(243)]")
        self._console.print()

        for i, key in enumerate(metrics):
            item_selected = selected_index == i
            selector = "[white]›[/white] " if item_selected else "  "
            enabled = key in quick_stats_selection

            # Dim marker when not selected
            if item_selected:
                marker = "[green]✓[/green]" if enabled else "[color(243)]○[/color(243)]"
            else:
                marker = "[color(245)]✓[/color(245)]" if enabled else "[color(243)]○[/color(243)]"

            label = QUICK_STATS[key].label_plural.title()

            # Dim unselected items
            display_label = label if item_selected else f"[color(245)]{label}[/color(245)]"

            self._console.print(f"  {selector}{marker} {display_label}")

        # Pad to push actions to bottom
        self._pad_to_bottom()

        back_index = len(metrics)
        if selected_index == back_index:
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Back")
        else:
            self._console.print("    [color(245)]← Back[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()

class DeadlineSettingsRenderer(BaseRenderer):
    """Renderer for configuring deadline display mode."""

    def render(self, context: dict) -> str:
        """Render the deadline settings screen."""
        self._reset_console_buffer()

        selected_index = context['selected_index']
        from ..config import get_config
        config = get_config()
        display_mode = config.deadline_display_mode

        self._console.print()
        self._console.print("  [bold]Deadline Display[/bold]")
        self._console.print("  [color(243)]Choose how deadlines are shown in task lists[/color(243)]")
        self._console.print()

        options = [
            ("relative", "Relative Time", "Show days remaining (e.g., '3d', 'today', '2d overdue')"),
            ("date", "Exact Date", "Show full date (e.g., '2025-10-31')"),
        ]

        for i, (mode, label, description) in enumerate(options):
            item_selected = selected_index == i
            selector = "[white]›[/white] " if item_selected else "  "
            enabled = mode == display_mode
            marker = "[green]●[/green]" if enabled else "[color(243)]○[/color(243)]"

            # Dim unselected items
            display_label = label if item_selected else f"[color(245)]{label}[/color(245)]"

            self._console.print(f"  {selector}{marker} {display_label}")
            self._console.print(f"    [color(243)]{description}[/color(243)]")

        # Pad to push actions to bottom
        # Pad to push actions to bottom
        self._pad_to_bottom()

        back_index = len(options)
        if selected_index == back_index:
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Back")
        else:
            self._console.print("    [color(245)]← Back[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class TaskMetadataSettingsRenderer(BaseRenderer):
    """Renderer for configuring task metadata display position."""

    def render(self, context: dict) -> str:
        """Render the task metadata settings screen."""
        self._reset_console_buffer()

        selected_index = context['selected_index']
        from ..config import get_config
        config = get_config()
        position = config.task_metadata_position

        self._console.print()
        self._console.print("  [bold]Task Metadata[/bold]")
        self._console.print("  [color(243)]Choose where to display priority and deadline for tasks[/color(243)]")
        self._console.print()

        options = [
            ("below", "Below Task Name", "Display priority and deadline on a separate line below the task name"),
            ("next_to", "Next to Task Name", "Display priority and deadline on the same line as the task name"),
        ]

        for i, (pos, label, description) in enumerate(options):
            item_selected = selected_index == i
            selector = "[white]›[/white] " if item_selected else "  "
            enabled = pos == position
            marker = "[green]●[/green]" if enabled else "[color(243)]○[/color(243)]"

            # Dim unselected items
            display_label = label if item_selected else f"[color(245)]{label}[/color(245)]"

            self._console.print(f"  {selector}{marker} {display_label}")
            self._console.print(f"    [color(243)]{description}[/color(243)]")

        # Pad to push actions to bottom
        self._pad_to_bottom()

        back_index = len(options)
        if selected_index == back_index:
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Back")
        else:
            self._console.print("    [color(245)]← Back[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class StatsNoneSettingsRenderer(BaseRenderer):
    """Renderer for configuring whether to show 'None' in project stats."""

    def render(self, context: dict) -> str:
        """Render the stats none settings screen."""
        self._reset_console_buffer()

        selected_index = context['selected_index']
        from ..config import get_config
        config = get_config()
        show_none = config.show_none_in_stats

        self._console.print()
        self._console.print("  [bold]Project Stats Display[/bold]")
        self._console.print("  [color(243)]Choose whether to display 'None' values in project stats panels[/color(243)]")
        self._console.print()

        options = [
            ("on", "Show 'None'", "Display fields set to 'none' in project stats"),
            ("off", "Hide 'None'", "Only display fields with actual values"),
        ]

        for i, (mode, label, description) in enumerate(options):
            item_selected = selected_index == i
            selector = "[white]›[/white] " if item_selected else "  "
            enabled = (mode == "on" and show_none) or (mode == "off" and not show_none)
            marker = "[green]●[/green]" if enabled else "[color(243)]○[/color(243)]"

            # Dim unselected items
            display_label = label if item_selected else f"[color(245)]{label}[/color(245)]"

            self._console.print(f"  {selector}{marker} {display_label}")
            self._console.print(f"    [color(243)]{description}[/color(243)]")

        # Pad to push actions to bottom
        self._pad_to_bottom()

        back_index = len(options)
        if selected_index == back_index:
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Back")
        else:
            self._console.print("    [color(245)]← Back[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class MessageDisplaySettingsRenderer(BaseRenderer):
    """Renderer for configuring status message display behavior."""

    def render(self, context: dict) -> str:
        """Render the status message display settings screen."""
        self._reset_console_buffer()

        selected_index = context['selected_index']
        from ..config import get_config
        config = get_config()
        mode = config.status_message_mode

        self._console.print()
        self._console.print("  [bold]Status Messages[/bold]")
        self._console.print("  [color(243)]Choose which status messages appear in the CLI[/color(243)]")
        self._console.print()

        options = [
            ("all", "Show All Messages", "Display both success/info and error messages"),
            ("errors_only", "Show Errors Only", "Hide non-error status messages"),
        ]

        for i, (value, label, description) in enumerate(options):
            item_selected = selected_index == i
            selector = "[white]›[/white] " if item_selected else "  "
            enabled = value == mode
            marker = "[green]●[/green]" if enabled else "[color(243)]○[/color(243)]"

            # Dim unselected items
            display_label = label if item_selected else f"[color(245)]{label}[/color(245)]"

            self._console.print(f"  {selector}{marker} {display_label}")
            self._console.print(f"    [color(243)]{description}[/color(243)]")

        # Pad to push actions to bottom
        self._pad_to_bottom()

        back_index = len(options)
        if selected_index == back_index:
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Back")
        else:
            self._console.print("    [color(245)]← Back[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class NotesDisplaySettingsRenderer(BaseRenderer):
    """Renderer for configuring notes display mode."""

    def render(self, context: dict) -> str:
        """Render the notes display settings screen."""
        self._reset_console_buffer()

        selected_index = context['selected_index']
        from ..config import get_config
        config = get_config()
        mode = config.notes_display_mode

        self._console.print()
        self._console.print("  [bold]Notes Display[/bold]")
        self._console.print("  [color(243)]Choose when task notes are visible[/color(243)]")
        self._console.print()

        options = [
            ("dynamic", "Show When Selected", "Notes appear only when a task is selected"),
            ("always", "Show Always", "Notes are always visible for all tasks"),
        ]

        for i, (value, label, description) in enumerate(options):
            item_selected = selected_index == i
            selector = "[white]›[/white] " if item_selected else "  "
            enabled = value == mode
            marker = "[green]●[/green]" if enabled else "[color(243)]○[/color(243)]"

            # Dim unselected items
            display_label = label if item_selected else f"[color(245)]{label}[/color(245)]"

            self._console.print(f"  {selector}{marker} {display_label}")
            self._console.print(f"    [color(243)]{description}[/color(243)]")

        # Pad to push actions to bottom
        self._pad_to_bottom()

        back_index = len(options)
        if selected_index == back_index:
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Back")
        else:
            self._console.print("    [color(245)]← Back[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class ProjectBrowserDefaultTabRenderer(BaseRenderer):
    """Renderer for configuring the default tab in project browser."""

    def render(self, context: dict) -> str:
        """Render the project browser default tab settings screen."""
        self._reset_console_buffer()

        selected_index = context['selected_index']
        from ..config import get_config
        config = get_config()
        default_tab = config.project_browser_default_tab

        self._console.print()
        self._console.print("  [bold]Project Browser Default Tab[/bold]")
        self._console.print("  [color(243)]Choose which tab opens first in the project browser[/color(243)]")
        self._console.print()

        options = [
            ("all", "All Projects First", "Tab order: All   Active   Done"),
            ("active", "Active Projects First", "Tab order: Active   Done   All"),
        ]

        for i, (value, label, description) in enumerate(options):
            item_selected = selected_index == i
            selector = "[white]›[/white] " if item_selected else "  "
            enabled = value == default_tab
            marker = "[green]●[/green]" if enabled else "[color(243)]○[/color(243)]"

            # Dim unselected items
            display_label = label if item_selected else f"[color(245)]{label}[/color(245)]"

            self._console.print(f"  {selector}{marker} {display_label}")
            self._console.print(f"    [color(243)]{description}[/color(243)]")

        # Pad to push actions to bottom
        self._pad_to_bottom()

        back_index = len(options)
        if selected_index == back_index:
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Back")
        else:
            self._console.print("    [color(245)]← Back[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class MainMenuTabsRenderer(BaseRenderer):
    """Renderer for configuring main menu tabs."""

    def render(self, context: dict) -> str:
        """Render the main menu tabs configuration screen."""
        self._reset_console_buffer()

        selected_index = context['selected_index']
        main_menu_tabs_selection = context.get('main_menu_tabs_selection', set())

        tabs = list(MAIN_MENU_TABS_ORDER)

        self._console.print()
        self._console.print("  [bold]Main Menu Tabs[/bold]")
        self._console.print("  [color(243)]Toggle which tabs appear in the main menu[/color(243)]")
        self._console.print()

        for i, key in enumerate(tabs):
            item_selected = selected_index == i
            selector = "[white]›[/white] " if item_selected else "  "
            enabled = key in main_menu_tabs_selection

            # Dim marker when not selected
            if item_selected:
                marker = "[green]✓[/green]" if enabled else "[color(243)]○[/color(243)]"
            else:
                marker = "[color(245)]✓[/color(245)]" if enabled else "[color(243)]○[/color(243)]"

            label = MAIN_MENU_TABS[key].label

            # Dim unselected items
            display_label = label if item_selected else f"[color(245)]{label}[/color(245)]"

            self._console.print(f"  {selector}{marker} {display_label}")

        # Pad to push actions to bottom
        self._pad_to_bottom()

        back_index = len(tabs)
        if selected_index == back_index:
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Back")
        else:
            self._console.print("    [color(245)]← Back[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class BookmarkActionSettingsRenderer(BaseRenderer):
    """Renderer for configuring bookmark action mode."""

    def render(self, context: dict) -> str:
        """Render the bookmark action settings screen."""
        self._reset_console_buffer()

        selected_index = context['selected_index']
        from ..config import get_config
        config = get_config()
        action_mode = config.bookmark_action_mode

        self._console.print()
        self._console.print("  [bold]Bookmark Action[/bold]")
        self._console.print("  [color(243)]Choose what happens when you press Enter on a bookmark[/color(243)]")
        self._console.print()

        options = [
            ("copy", "Copy to Clipboard", "Copy the bookmark URL to your clipboard"),
            ("open", "Open in Browser", "Open the bookmark in your default browser"),
        ]

        for i, (mode, label, description) in enumerate(options):
            item_selected = selected_index == i
            selector = "[white]›[/white] " if item_selected else "  "
            enabled = mode == action_mode
            marker = "[green]●[/green]" if enabled else "[color(243)]○[/color(243)]"

            # Dim unselected items
            display_label = label if item_selected else f"[color(245)]{label}[/color(245)]"

            self._console.print(f"  {selector}{marker} {display_label}")
            self._console.print(f"    [color(243)]{description}[/color(243)]")

        # Pad to push actions to bottom
        self._pad_to_bottom()

        back_index = len(options)
        if selected_index == back_index:
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Back")
        else:
            self._console.print("    [color(245)]← Back[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class CustomFieldsRenderer(BaseRenderer):
    """Renderer for the Customize Fields screen."""

    def render(self, context: dict) -> str:
        """Render the customize fields screen."""
        self._reset_console_buffer()
        selected_index = context['selected_index']

        # Get built-in and custom fields separately
        default_visibility = context.get('default_field_visibility', {})
        custom_fields = context.get('custom_field_definitions', [])

        # Import helper to get built-in fields
        from ..custom_fields import get_builtin_fields
        builtin_fields = get_builtin_fields(default_visibility)

        # Header
        self._console.print()
        self._console.print("  [bold]Customize Fields[/bold]")
        self._console.print("  [color(243)]Toggle field visibility[/color(243)]")
        self._console.print()

        # Left-side border helper
        left_border = "[color(238)]  │[/color(238)] "
        def header_line() -> str:
            return "[color(238)]  ┌[/color(238)]"
        def footer_line() -> str:
            return "[color(238)]  └[/color(238)]"
        def left_line(content: str = "") -> str:
            return f"{left_border}{content}"

        current_index = 0

        self._console.print(header_line())

        # Display built-in fields
        if builtin_fields or True:  # Always show section for progress
            self._console.print(left_line("  [color(243)]Built-in[/color(243)]"))

            # Progress field with visibility toggle (no mode selection)
            progress_selected = selected_index == current_index
            progress_selector = "[white]›[/white] " if progress_selected else "  "
            progress_visible = default_visibility.get("progress", True)

            if progress_selected:
                progress_marker = "[green]✓[/green]" if progress_visible else "[color(243)]○[/color(243)]"
            else:
                progress_marker = "[color(245)]✓[/color(245)]" if progress_visible else "[color(243)]○[/color(243)]"

            label = "Progress"
            if progress_selected:
                self._console.print(left_line(f"    {progress_selector}{progress_marker} {label}"))
            else:
                self._console.print(left_line(f"    {progress_selector}{progress_marker} [color(245)]{label}[/color(245)]"))
            current_index += 1

            # Other built-in fields (visibility toggle only)
            for field in builtin_fields:
                item_selected = selected_index == current_index
                selector = "[white]›[/white] " if item_selected else "  "

                if item_selected:
                    marker = "[green]✓[/green]" if field.visible else "[color(243)]○[/color(243)]"
                else:
                    marker = "[color(245)]✓[/color(245)]" if field.visible else "[color(243)]○[/color(243)]"

                label = field.label
                if item_selected:
                    self._console.print(left_line(f"    {selector}{marker} {label}"))
                else:
                    self._console.print(left_line(f"    {selector}{marker} [color(245)]{label}[/color(245)]"))
                current_index += 1

        # Display custom fields (fully editable)
        if custom_fields:
            self._console.print(left_line())
            self._console.print(left_line("  [color(243)]Custom[/color(243)]"))
            
            for field in custom_fields:
                item_selected = selected_index == current_index
                selector = "[white]›[/white] " if item_selected else "  "

                if item_selected:
                    marker = "[green]✓[/green]" if field.visible else "[color(243)]○[/color(243)]"
                else:
                    marker = "[color(245)]✓[/color(245)]" if field.visible else "[color(243)]○[/color(243)]"

                req_indicator = "[red]*[/red]" if field.required else ""

                label = field.label
                if item_selected:
                    self._console.print(left_line(f"    {selector}{marker} {label}{req_indicator}"))
                else:
                    self._console.print(left_line(f"    {selector}{marker} [color(245)]{label}[/color(245)]{req_indicator}"))
                current_index += 1

        self._console.print(footer_line())

        # Pad to push actions to bottom
        self._pad_to_bottom()

        # Actions
        actions_start = current_index
        actions = [
            ("Add Field", "[green]+[/green]", "[color(245)]+[/color(245)]"),
            ("Back", "[yellow]←[/yellow]", "[color(245)]←[/color(245)]"),
        ]

        for i, (label, selected_icon, unselected_icon) in enumerate(actions):
            action_index = actions_start + i
            if selected_index == action_index:
                self._console.print(f"  [white]›[/white] {selected_icon} {label}")
            else:
                self._console.print(f"    {unselected_icon} [color(245)]{label}[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()
