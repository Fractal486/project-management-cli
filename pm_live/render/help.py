"""Help overlay renderer for keyboard shortcuts."""

from rich.panel import Panel

from .base import BaseRenderer
from ..states import AppState
from ..keybindings import get_keybindings_for_state, KEYBINDINGS_BY_SCREEN, FORM_STATES


class HelpRenderer(BaseRenderer):
    """Renders the help overlay showing keyboard shortcuts."""

    def render(self, context: dict) -> str:
        """Render help overlay as a centered panel."""
        self._reset_console_buffer()
        
        show_all = context.get('show_all_keybindings', False)
        
        if show_all:
            self._render_all_keybindings()
        else:
            current_state = context.get('state', AppState.MAIN_MENU)
            self._render_screen_keybindings(current_state)
        
        self._render_status_message(context)
        return self._get_console_output()
    
    def _render_screen_keybindings(self, state: AppState):
        """Render keybindings for the current screen only."""
        keybindings = get_keybindings_for_state(state)
        screen_name = self._get_screen_name(state)
        
        # Build content lines
        lines = []
        lines.append(f"[bold white]{screen_name}[/bold white]")
        lines.append("")
        
        # Filter out Ctrl+C to add it last
        main_bindings = [(k, a) for k, a in keybindings if k != "Ctrl+C"]
        
        for key, action in main_bindings:
            lines.append(f"  [yellow]{key:<12}[/yellow] [color(243)]{action}[/color(243)]")
        
        # Add footer shortcuts (skip for settings/stats screens which only have 'Back')
        settings_states = (
            AppState.SETTINGS, AppState.QUICK_STATS_SETTINGS, AppState.MAIN_MENU_TABS_SETTINGS,
            AppState.DEADLINE_SETTINGS, AppState.TASK_METADATA_SETTINGS,
            AppState.STATS_NONE_SETTINGS, AppState.MESSAGE_DISPLAY_SETTINGS, AppState.BOOKMARK_ACTION_SETTINGS, AppState.STATISTICS
        )
        if state not in settings_states:
            lines.append(f"  [yellow]{'1-4':<12}[/yellow] [color(243)]Footer actions[/color(243)]")
        
        # Separator and exit
        lines.append("")
        lines.append(f"  [yellow]{'Ctrl+C':<12}[/yellow] [color(243)]Exit[/color(243)]")
        
        content = "\n".join(lines)
        
        help_panel = Panel(
            content,
            title="[bold white]Shortcuts[/bold white]",
            subtitle="[color(243)]H to close[/color(243)]",
            border_style="color(238)",
            padding=(1, 2),
        )
        
        self._console.print(help_panel)
    
    def _render_all_keybindings(self):
        """Render all keybindings grouped by key."""
        # Collect all actions for each key
        keybindings_map = {}  # key -> [actions]
        
        for state, bindings in KEYBINDINGS_BY_SCREEN.items():
            for key, action in bindings:
                if key not in keybindings_map:
                    keybindings_map[key] = []
                if action not in keybindings_map[key]:
                    keybindings_map[key].append(action)
        
        # Add footer shortcuts entry
        if "1-4" not in keybindings_map:
            keybindings_map["1-4"] = ["Footer actions"]
        
        # Build content
        lines = []
        lines.append("[bold white]All Screens[/bold white]")
        lines.append("")
        
        # Sort keys, excluding Ctrl+C
        sorted_keys = sorted(k for k in keybindings_map.keys() if k != "Ctrl+C")
        
        for key in sorted_keys:
            actions = keybindings_map[key]
            # Truncate long action lists
            if len(actions) > 2:
                action_str = f"{actions[0]}; +{len(actions)-1} more"
            else:
                action_str = "; ".join(actions)
            lines.append(f"  [yellow]{key:<12}[/yellow] [color(243)]{action_str}[/color(243)]")
        
        # Separator and exit
        lines.append("")
        if "Ctrl+C" in keybindings_map:
            lines.append(f"  [yellow]{'Ctrl+C':<12}[/yellow] [color(243)]Exit[/color(243)]")
        
        content = "\n".join(lines)
        
        help_panel = Panel(
            content,
            title="[bold white]Shortcuts[/bold white]",
            subtitle="[color(243)]H to close[/color(243)]",
            border_style="color(238)",
            padding=(1, 2),
        )
        
        self._console.print(help_panel)
    
    def _get_screen_name(self, state: AppState) -> str:
        """Get a human-readable name for a screen state."""
        if state in FORM_STATES:
            return "Forms"
        
        name_map = {
            AppState.MAIN_MENU: "Main Menu",
            AppState.PROJECT_BROWSER: "Project Browser",
            AppState.PROJECT_DETAILS: "Project Details",
            AppState.TASK_LIST: "Task List",
            AppState.BOOKMARKS: "Bookmarks",
            AppState.BOOKMARK_LIST: "Bookmark List",
            AppState.SETTINGS: "Settings",
            AppState.QUICK_STATS_SETTINGS: "Quick Stats",
            AppState.MAIN_MENU_TABS_SETTINGS: "Menu Tabs",
            AppState.DEADLINE_SETTINGS: "Deadlines",
            AppState.TASK_METADATA_SETTINGS: "Task Metadata",
            AppState.MESSAGE_DISPLAY_SETTINGS: "Status Messages",
            AppState.CUSTOMIZE_FIELDS: "Custom Fields",
            AppState.STATISTICS: "Statistics",
        }
        
        return name_map.get(state, "Help")
