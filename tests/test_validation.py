import pytest

from pm_live.utils.validation import (
    get_max_name_length,
    sanitize_input,
    sanitize_multiline_input,
    validate_project_name,
    validate_task_name,
)


def test_sanitize_input_normalizes_whitespace_and_quotes():
    raw = '  \tNew\nProject "Name" \\Extra '
    sanitized = sanitize_input(raw)
    assert sanitized == "New Project 'Name' /Extra"


def test_sanitize_multiline_input_preserves_newlines():
    raw = 'Line 1\r\nLine 2\t"Name" \\Extra\n'
    sanitized = sanitize_multiline_input(raw)
    assert sanitized == "Line 1\nLine 2 'Name' /Extra"


@pytest.mark.parametrize(
    "validator, value",
    [
        (validate_project_name, "  Valid Project  "),
        (validate_task_name, "\nValid Task\t"),
    ],
)
def test_name_validators_succeed_with_clean_value(validator, value):
    is_valid, cleaned = validator(value)
    assert is_valid is True
    expected = "Valid Project" if validator is validate_project_name else "Valid Task"
    assert cleaned == expected


@pytest.mark.parametrize(
    "validator",
    [validate_project_name, validate_task_name],
)
def test_name_validators_reject_empty(validator):
    is_valid, message = validator("   ")
    assert is_valid is False
    assert "cannot be empty" in message


@pytest.mark.parametrize(
    "validator",
    [validate_project_name, validate_task_name],
)
def test_name_validators_enforce_length_limit(validator):
    max_length = get_max_name_length()
    overlong = "a" * (max_length + 1)
    is_valid, message = validator(overlong)
    assert is_valid is False
    assert str(max_length) in message
