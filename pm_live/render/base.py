"""Base renderer class and utilities for converting Rich output to prompt_toolkit formatted text."""

from abc import ABC, abstractmethod
from io import StringIO
from typing import Any
import shutil

from rich.console import Console
from rich.markup import escape as rich_escape
from prompt_toolkit.formatted_text import FormattedText, ANSI

from ..config import get_config

class BaseRenderer(ABC):
    """Base class for all renderers."""

    def __init__(self, console: Console = None):
        """Initialize renderer with optional reusable console."""
        # Use actual terminal width instead of configured width
        try:
            width = shutil.get_terminal_size().columns
        except (AttributeError, ValueError, OSError):
            width = get_config().console_width
        self._console = console or Console(
            file=StringIO(),
            force_terminal=True,
            width=width,
            legacy_windows=False
        )

    @abstractmethod
    def render(self, context: dict) -> str:
        """Render the content for this renderer.
        
        Args:
            context: Dictionary containing all necessary data for rendering
            
        Returns:
            Rich-formatted string ready for display
        """
        pass

    def _reset_console_buffer(self):
        """Reset the console buffer for reuse."""
        if hasattr(self._console.file, 'seek'):
            self._console.file.seek(0)
            self._console.file.truncate(0)

    def _get_console_output(self) -> str:
        """Get the current console output."""
        if hasattr(self._console.file, 'getvalue'):
            return self._console.file.getvalue()
        return ""

    def _pad_to_bottom(self):
        """Add blank lines to push following content to bottom of screen."""
        # Get current output and count lines
        output = self._get_console_output()
        current_lines = len(output.split('\n')) - 1  # -1 because split adds an extra count

        # Calculate how many blank lines needed to push actions near the bottom
        # Leave room for status message (2 lines) and actions (3-5 lines)
        reserved_lines = 6
        target_position = self._console.height - reserved_lines

        lines_to_add = max(0, target_position - current_lines)
        for _ in range(lines_to_add):
            self._console.print()

    def _render_status_message(self, context: dict):
        """Render status message at the bottom if one exists.

        All status banners use a neutral gray color so they are visually
        consistent and less "alarm-like" than bright green/red messages.
        """
        status_message = context.get('status_message')
        status_is_error = context.get('status_is_error', False)
        display_mode = get_config().status_message_mode

        always_show = {
            "Pinned",
            "Unpinned",
            "Pinned section",
            "Unpinned section",
        }

        if display_mode == "errors_only" and not status_is_error and status_message not in always_show:
            return

        if status_message:
            # Add small separation from previous content
            self._console.print()
            # Use a neutral gray tone for all status messages (including errors)
            self._console.print(f"[color(243)]{status_message}[/color(243)]")

    @staticmethod
    def build_inline_name_display(name_value: str, inline_edit_field_index: int, inline_edit_name_cursor: int) -> str:
        """Render editable name with inline cursor indicator."""
        name_value = name_value or ""
        if inline_edit_field_index == 0:
            caret_pos = max(0, min(len(name_value), inline_edit_name_cursor))
            if name_value and caret_pos < len(name_value):
                left = rich_escape(name_value[:caret_pos])
                current = rich_escape(name_value[caret_pos])
                right = rich_escape(name_value[caret_pos + 1:])
                display = f"{left}[reverse]{current}[/reverse]{right}"
            else:
                display = f"{rich_escape(name_value)}[reverse] [/reverse]"
            return f"[white]{display}[/white]"
        if name_value:
            return f"[color(243)]{rich_escape(name_value)}[/color(243)]"
        return "[color(243)]none[/color(243)]"

    @staticmethod
    def build_inline_notes_display(notes_value: str | None, inline_edit_field_index: int, inline_edit_notes_cursor: int) -> str:
        """Render notes field with inline cursor indicator or placeholder."""
        if not notes_value:
            # Empty placeholder - show with cursor if editing
            if inline_edit_field_index == 3:
                # Show cursor on first character of placeholder
                return "[white reverse]n[/white reverse][color(238)]otes[/color(238)]"
            else:
                return "[color(238)]notes[/color(238)]"

        # Show notes with cursor if actively editing this field
        if inline_edit_field_index == 3:
            caret_pos = max(0, min(len(notes_value), inline_edit_notes_cursor))
            if caret_pos < len(notes_value):
                left = rich_escape(notes_value[:caret_pos])
                current = rich_escape(notes_value[caret_pos])
                right = rich_escape(notes_value[caret_pos + 1:])
                return f"[white]{left}[/white][white reverse]{current}[/white reverse][white]{right}[/white]"
            else:
                # Cursor at end
                escaped = rich_escape(notes_value)
                return f"[white]{escaped}[/white][white reverse] [/white reverse]"
        else:
            # Not editing notes, just display dimmed
            escaped = rich_escape(notes_value)
            return f"[color(238)]{escaped}[/color(238)]"

    @staticmethod
    def build_text_input_display(value: str, cursor: int) -> str:
        """Render an inline text input buffer with reverse-highlight cursor."""
        value = value or ""
        caret_pos = max(0, min(len(value), cursor))
        if value and caret_pos < len(value):
            left = rich_escape(value[:caret_pos])
            current = rich_escape(value[caret_pos])
            right = rich_escape(value[caret_pos + 1:])
            return f"{left}[reverse]{current}[/reverse]{right}"
        return f"{rich_escape(value)}[reverse] [/reverse]"

    @staticmethod
    def build_inline_deadline_display(deadline_value: str | None, inline_edit_field_index: int, inline_edit_deadline_component: int) -> str:
        """Render deadline inline with component highlighting."""
        active = inline_edit_field_index == 1
        if not deadline_value:
            return "[white]none[/white]" if active else "[color(243)]none[/color(243)]"
        parts = deadline_value.split('-')
        if len(parts) != 3:
            return f"[white]{deadline_value}[/white]" if active else f"[color(243)]{deadline_value}[/color(243)]"
        year, month, day = parts
        if not active:
            return f"[color(243)]{year}-{month}-{day}[/color(243)]"
        # Highlight active component
        comp_displays = [year, month, day]
        comp_displays[inline_edit_deadline_component] = f"[reverse]{comp_displays[inline_edit_deadline_component]}[/reverse]"
        return f"[white]{comp_displays[0]}-{comp_displays[1]}-{comp_displays[2]}[/white]"

    @staticmethod
    def build_inline_priority_display(priority_value: str | None, inline_edit_field_index: int) -> str:
        """Render priority cycling field with selection highlight."""
        priority_colors = {"!!!": "red", "!!": "yellow", "!": "green"}
        if priority_value in (None, "none"):
            return "[white]none[/white]" if inline_edit_field_index == 2 else "[color(243)]none[/color(243)]"
        color = priority_colors.get(priority_value, "white")
        colored = f"[{color}]{priority_value}[/{color}]"
        if inline_edit_field_index == 2:
            return colored
        return f"[color(243)]{priority_value}[/color(243)]"


def rich_to_formatted_text(rich_content: str) -> FormattedText:
    """Convert Rich console output to prompt_toolkit FormattedText.
    
    Rich outputs ANSI escape codes, which prompt_toolkit can handle directly.
    """
    return ANSI(rich_content)
