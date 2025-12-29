"""Formatting utilities for status icons, colors, and progress bars."""

from typing import Optional, Union

from pm import STATUS_META, LEVEL_COLORS


def get_status_icon(status: str) -> str:
    """Get icon for status using pm.py constants."""
    return STATUS_META.get(status, {}).get("icon", "?")


def get_status_color(status: str) -> str:
    """Get color for status using pm.py constants."""
    return STATUS_META.get(status, {}).get("color", "white")


def get_level_color(level: str) -> str:
    """Get color for a level value using pm.py constants."""
    return LEVEL_COLORS.get(level, "white")


def render_progress_bar(percentage: int, width: int = 6) -> str:
    """Render a minimal progress bar string.

    Args:
        percentage: Progress percentage (0-100)
        width: Width of the bar in characters

    Returns:
        Progress bar string using the compact bar characters (filled "▬", empty "▭")
    """
    filled = int((percentage / 100) * width)
    empty = width - filled
    return "▬" * filled + "▭" * empty


def format_currency_value(value: Union[str, int, float], symbol: str) -> str:
    """Format a numeric value with thousands separators and trailing currency symbol.

    Args:
        value: Numeric value to format (can be string or number)
        symbol: Currency symbol to append (e.g., "$", "€")

    Returns:
        Formatted string like "1,234.56 $"
    """
    try:
        raw = str(value).replace(",", "").strip()
        if not raw:
            return f"0 {symbol}"
        sign = ""
        if raw and raw[0] in "+-":
            sign, raw = raw[0], raw[1:]
        if "." in raw:
            int_part, frac_part = raw.split(".", 1)
        else:
            int_part, frac_part = raw, ""
        int_part_num = int(int_part) if int_part else 0
        int_formatted = f"{int_part_num:,}"
        frac_display = f".{frac_part}" if frac_part else ""
        return f"{sign}{int_formatted}{frac_display} {symbol}"
    except Exception:
        return f"{value} {symbol}"


def format_deadline(deadline: str) -> str:
    """Format deadline string for display.

    Args:
        deadline: ISO format string (YYYY-MM-DD) or None

    Returns:
        Formatted deadline string with relative date if applicable.
        Display mode is controlled by config.deadline_display_mode:
        - "relative": Shows days remaining (3d, today, overdue)
        - "date": Shows exact date (YYYY-MM-DD)
    """
    if not deadline:
        return ""

    from datetime import datetime
    from ..config import get_config

    config = get_config()
    display_mode = config.deadline_display_mode

    try:
        deadline_date = datetime.strptime(deadline, "%Y-%m-%d").date()
        today = datetime.now().date()

        # Calculate days until deadline
        delta = (deadline_date - today).days

        if display_mode == "date":
            # Show exact date in consistent format
            date_label = deadline_date.strftime("%Y %b %d")
            return f" {date_label}"
        else:
            # Show relative time (default: "relative")
            if delta < 0:
                # Past deadline
                days_overdue = abs(delta)
                return f" {days_overdue}d overdue"
            elif delta == 0:
                # Today
                return f" today"
            elif delta == 1:
                # Tomorrow
                return f" tomorrow"
            elif delta <= 7:
                # Within a week
                return f" {delta}d"
            else:
                # More than a week away
                return f" {delta}d"
    except (ValueError, TypeError):
        # Invalid date format - just show the raw value
        return f" {deadline}"


def get_task_completion_icon(completed: Optional[bool]) -> str:
    """Return the task completion icon for None/True/False."""
    if completed is True:
        return "û"
    if completed is False:
        return "?"
    return "	"


def get_task_completion_color(completed: Optional[bool]) -> str:
    """Return the color token for a task completion icon."""
    if completed is None:
        return "color(245)"
    return "color(238)"
