"""Base renderer class and utilities for converting Rich output to prompt_toolkit formatted text."""

from abc import ABC, abstractmethod
from io import StringIO
from typing import Any
import re
import shutil
import textwrap

from rich.console import Console
from rich.markup import MarkupError
from rich.markup import escape as rich_escape
from rich.text import Text
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
    def _strip_markup(text: str) -> str:
        """Return plain text by removing Rich markup tags."""
        if not text:
            return ""
        return re.sub(r"\[[^\]]+\]", "", text)

    def wrap_with_prefix(self, text: str, prefix: str, width: int | None = None) -> Text:
        """Wrap text to console width and prefix every line (including wrapped lines).

        Returns a Rich Text renderable so markup styles remain valid across line breaks.
        """
        if text is None:
            return Text("")
        normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
        if width is None:
            width = getattr(self._console, "width", 80)
        visible_prefix = self._strip_markup(prefix)
        available = max(1, width - len(visible_prefix))

        try:
            prefix_text = Text.from_markup(prefix)
        except MarkupError:
            prefix_text = Text(prefix)

        output_lines: list[Text] = []
        for raw_line in normalized.split("\n"):
            if raw_line == "":
                output_lines.append(prefix_text.copy())
                continue

            try:
                rich_text = Text.from_markup(raw_line)
                wrapped = rich_text.wrap(self._console, available)
                if not wrapped:
                    wrapped = [Text("")]

                for line in wrapped:
                    prefixed = prefix_text.copy()
                    prefixed.append_text(line)
                    output_lines.append(prefixed)
                continue
            except MarkupError:
                pass

            lines = textwrap.wrap(
                raw_line,
                width=available,
                break_long_words=False,
                break_on_hyphens=False,
            )
            if not lines:
                lines = [""]

            for line in lines:
                prefixed = prefix_text.copy()
                prefixed.append(line)
                output_lines.append(prefixed)

        result = Text("")
        for i, line in enumerate(output_lines):
            result.append_text(line)
            if i != len(output_lines) - 1:
                result.append("\n")
        return result

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

        normalized = str(notes_value).replace("\r\n", "\n").replace("\r", "\n")

        # Show notes with cursor if actively editing this field
        if inline_edit_field_index == 3:
            display = BaseRenderer.build_multiline_text_input_display(normalized, inline_edit_notes_cursor)
            lines = display.split("\n")
            return "\n".join((f"[white]{line}[/white]" if line else "") for line in lines)

        # Not editing notes, just display dimmed (line-safe markup)
        lines = normalized.split("\n")
        return "\n".join((f"[color(238)]{rich_escape(line)}[/color(238)]" if line else "") for line in lines)

    @staticmethod
    def indent_multiline(text: str, prefix: str) -> str:
        """Indent existing newline breaks by prefix without altering the first line."""
        if not text:
            return text
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return normalized.replace("\n", "\n" + prefix)

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
    def build_multiline_text_input_display(value: str, cursor: int) -> str:
        """Render a multiline text input buffer with reverse-highlight cursor.

        If the cursor is positioned on a newline character, render a visible
        glyph (↵) for the cursor and keep the line break.
        """
        value = (value or "").replace("\r\n", "\n").replace("\r", "\n")
        caret_pos = max(0, min(len(value), cursor))
        if value and caret_pos < len(value):
            current_raw = value[caret_pos]
            left = rich_escape(value[:caret_pos])
            right = rich_escape(value[caret_pos + 1:])
            if current_raw == "\n":
                return f"{left}[reverse]↵[/reverse]\n{right}"
            current = rich_escape(current_raw)
            return f"{left}[reverse]{current}[/reverse]{right}"

        # Cursor at end.
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
