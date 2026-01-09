"""Input sanitization and validation helpers."""

from __future__ import annotations

import re
from typing import Tuple

from ..config import get_config


def _max_length() -> int:
    """Return the current maximum name length from configuration."""
    return get_config().max_project_name_length


def get_max_name_length() -> int:
    """Get the current maximum name length from configuration.

    This function should be used instead of a constant to ensure
    the value reflects any runtime configuration changes.
    """
    return _max_length()

# Control characters that should never persist into stored text
_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f]")

# Same as above, but preserve LF (\n) for multiline fields.
_CONTROL_CHAR_PATTERN_MULTILINE = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")


def sanitize_input(text: str | None) -> str:
    """Normalize user supplied text so it is safe for JSON persistence.

    - Replace control characters with spaces
    - Collapse repeated whitespace
    - Replace problematic JSON delimiters with safe equivalents
    - Trim leading/trailing whitespace
    """
    if not text:
        return ""

    sanitized = _CONTROL_CHAR_PATTERN.sub(" ", text)
    sanitized = sanitized.replace('"', "'").replace("\\", "/")
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized.strip()


def sanitize_multiline_input(text: str | None) -> str:
    """Normalize user supplied text for multiline JSON persistence.

    - Preserve newlines (\n)
    - Replace other control characters with spaces
    - Replace problematic JSON delimiters with safe equivalents
    - Trim trailing whitespace on each line
    - Trim leading/trailing blank lines
    """
    if not text:
        return ""

    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    sanitized = _CONTROL_CHAR_PATTERN_MULTILINE.sub(" ", normalized)
    sanitized = sanitized.replace('"', "'").replace("\\", "/")

    lines = [line.rstrip() for line in sanitized.split("\n")]
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def validate_project_name(name: str) -> Tuple[bool, str]:
    """Validate project names, returning (is_valid, sanitized_or_error)."""
    sanitized = sanitize_input(name)
    if not sanitized:
        return False, "Project name cannot be empty."
    limit = _max_length()
    if len(sanitized) > limit:
        return False, f"Project name must be at most {limit} characters."
    return True, sanitized


def validate_task_name(name: str) -> Tuple[bool, str]:
    """Validate task names, returning (is_valid, sanitized_or_error)."""
    sanitized = sanitize_input(name)
    if not sanitized:
        return False, "Task name cannot be empty."
    limit = _max_length()
    if len(sanitized) > limit:
        return False, f"Task name must be at most {limit} characters."
    return True, sanitized


def validate_section_name(name: str) -> Tuple[bool, str]:
    """Validate section names, returning (is_valid, sanitized_or_error)."""
    sanitized = sanitize_input(name)
    if not sanitized:
        return False, "Section name cannot be empty."
    limit = _max_length()
    if len(sanitized) > limit:
        return False, f"Section name must be at most {limit} characters."
    return True, sanitized


def validate_bookmark_title(title: str) -> Tuple[bool, str]:
    """Validate bookmark title, returning (is_valid, sanitized_or_error)."""
    sanitized = sanitize_input(title)
    if not sanitized:
        return False, "Bookmark title cannot be empty."
    limit = _max_length()
    if len(sanitized) > limit:
        return False, f"Bookmark title must be at most {limit} characters."
    return True, sanitized


def validate_url(url: str) -> Tuple[bool, str]:
    """Validate URL, returning (is_valid, sanitized_or_error).

    Basic URL validation checking for protocol and structure.
    If no protocol is provided, https:// is automatically prepended.
    """
    # Basic sanitization - preserve more characters for URLs
    if not url:
        return False, "URL cannot be empty."

    # Remove control characters but preserve URL-safe characters
    sanitized = _CONTROL_CHAR_PATTERN.sub("", url.strip())

    if not sanitized:
        return False, "URL cannot be empty."

    # Auto-prepend https:// if no protocol is provided
    if not sanitized.startswith(('http://', 'https://')):
        sanitized = 'https://' + sanitized

    # Basic URL pattern check (protocol + domain)
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    if not url_pattern.match(sanitized):
        return False, "Invalid URL format. Must be a valid domain or IP address."

    return True, sanitized
