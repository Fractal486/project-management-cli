"""Utility functions for the live CLI."""

from .formatting import (
    get_status_icon, get_status_color, get_level_color,
    render_progress_bar, format_currency_value, format_deadline,
    get_task_completion_icon, get_task_completion_color
)
from .helpers import get_stats, filter_projects_by_tab, get_edit_project_field_keys, get_visible_fields_sorted, sort_projects_for_display
from .validation import (
    sanitize_input,
    sanitize_multiline_input,
    validate_project_name,
    validate_task_name,
    validate_bookmark_title,
    validate_url,
    validate_section_name,
)
from .search import perform_search

__all__ = [
    'get_status_icon', 'get_status_color', 'get_level_color',
    'render_progress_bar', 'format_currency_value', 'format_deadline',
    'get_task_completion_icon', 'get_task_completion_color',
    'get_stats', 'filter_projects_by_tab', 'get_edit_project_field_keys', 'get_visible_fields_sorted', 'sort_projects_for_display',
    'sanitize_input', 'sanitize_multiline_input', 'validate_project_name', 'validate_task_name',
    'validate_bookmark_title', 'validate_url', 'validate_section_name',
    'perform_search'
]
