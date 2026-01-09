"""Tests for form handler operations (pm_live/handlers/form_handlers.py)."""

import pytest
from unittest.mock import Mock, patch

from pm import Project, TIMEFRAME_OPTIONS, STATUS_OPTIONS
from pm_live.handlers.form_handlers import FormHandlers
from pm_live.interfaces import HandlerContext
from pm_live.ui_state import UIState
from pm_live.states import AppState


# ==================== Fixtures ====================


@pytest.fixture
def mock_manager():
    """Create a mock DataManagerProtocol."""
    manager = Mock()
    manager.projects = []
    manager.mark_dirty = Mock()
    manager.save = Mock(return_value=True)
    manager.next_id = Mock(return_value=1)
    return manager


@pytest.fixture
def mock_ui_state():
    """Create a mock UIState."""
    ui_state = UIState()
    ui_state.state = AppState.ADD_PROJECT
    ui_state.form_field_index = 0
    ui_state.form_data = {}
    ui_state.inline_input_mode = False
    ui_state.text_input_buffer = ""
    ui_state.status_message = None
    ui_state.status_is_error = False
    return ui_state


@pytest.fixture
def mock_context(mock_manager, mock_ui_state):
    """Create a mock HandlerContext."""
    context = Mock(spec=HandlerContext)
    context.manager = mock_manager
    context.ui_state = mock_ui_state
    context.show_status = Mock()
    return context


@pytest.fixture
def form_handlers(mock_context):
    """Create a FormHandlers instance."""
    return FormHandlers(mock_context)


@pytest.fixture
def sample_project():
     """Create a sample project."""
     return Project(
         id=1,
         name="Existing Project",
         status="In Progress",
         description="Sample description",
         tasks=[]
     )


# ==================== Name Field Tests ====================


def test_edit_form_field_name_enter_input_mode(form_handlers, mock_ui_state):
    """Entering on name field activates inline input mode."""
    mock_ui_state.inline_input_mode = False
    mock_ui_state.form_data = {}

    form_handlers.edit_form_field("name", is_add_form=True)

    assert mock_ui_state.inline_input_mode is True
    assert mock_ui_state.text_input_buffer == ""


def test_edit_form_field_name_enter_input_mode_with_existing_value(form_handlers, mock_ui_state):
    """Entering input mode loads existing name value."""
    mock_ui_state.inline_input_mode = False
    mock_ui_state.form_data = {"name": "My Project"}

    form_handlers.edit_form_field("name", is_add_form=True)

    assert mock_ui_state.inline_input_mode is True
    assert mock_ui_state.text_input_buffer == "My Project"


def test_edit_form_field_name_enter_input_mode_edit_form(form_handlers, mock_ui_state, sample_project):
    """Entering input mode in edit form loads project name."""
    mock_ui_state.inline_input_mode = False
    mock_ui_state.form_data = {}

    form_handlers.edit_form_field("name", is_add_form=False, project=sample_project)

    assert mock_ui_state.inline_input_mode is True
    assert mock_ui_state.text_input_buffer == "Existing Project"


@patch('pm_live.handlers.form_handlers.validate_project_name')
def test_edit_form_field_name_save_valid_name(mock_validate, form_handlers, mock_ui_state):
    """Saving valid name stores it in form_data."""
    mock_validate.return_value = (True, "Valid Project")
    mock_ui_state.inline_input_mode = True
    mock_ui_state.text_input_buffer = "Valid Project"

    form_handlers.edit_form_field("name", is_add_form=True)

    assert mock_ui_state.form_data["name"] == "Valid Project"
    assert mock_ui_state.inline_input_mode is False
    assert mock_ui_state.text_input_buffer == ""


@patch('pm_live.handlers.form_handlers.validate_project_name')
def test_edit_form_field_name_save_invalid_name(mock_validate, form_handlers, mock_ui_state, mock_context):
    """Saving invalid name shows error and stays in input mode."""
    mock_validate.return_value = (False, "Name cannot be empty")
    mock_ui_state.inline_input_mode = True
    mock_ui_state.text_input_buffer = ""

    form_handlers.edit_form_field("name", is_add_form=True)

    # Should show error
    mock_context.show_status.assert_called_with("Name cannot be empty", True)
    # Should stay in input mode
    assert "name" not in mock_ui_state.form_data


# ==================== Description Field Tests ====================


def test_edit_form_field_description_enter_input_mode(form_handlers, mock_ui_state):
    """Entering on description field activates inline input mode."""
    mock_ui_state.inline_input_mode = False
    mock_ui_state.form_data = {}

    form_handlers.edit_form_field("description", is_add_form=True)

    assert mock_ui_state.inline_input_mode is True
    assert mock_ui_state.text_input_buffer == ""


@patch('pm_live.handlers.form_handlers.sanitize_multiline_input')
def test_edit_form_field_description_save(mock_sanitize, form_handlers, mock_ui_state):
    """Saving description sanitizes and stores it."""
    mock_sanitize.return_value = "Clean description"
    mock_ui_state.inline_input_mode = True
    mock_ui_state.text_input_buffer = "Clean description"

    form_handlers.edit_form_field("description", is_add_form=True)

    assert mock_ui_state.form_data["description"] == "Clean description"
    assert mock_ui_state.inline_input_mode is False


def test_edit_form_field_description_edit_form(form_handlers, mock_ui_state, sample_project):
    """Editing description in edit form loads existing value."""
    mock_ui_state.inline_input_mode = False
    mock_ui_state.form_data = {}

    form_handlers.edit_form_field("description", is_add_form=False, project=sample_project)

    assert mock_ui_state.inline_input_mode is True
    assert mock_ui_state.text_input_buffer == "Sample description"


# ==================== Timeframe Field Tests ====================


def test_edit_form_field_timeframe_cycle_from_empty(form_handlers, mock_ui_state):
    """Timeframe cycles from empty to first option."""
    mock_ui_state.form_data = {}

    form_handlers.edit_form_field("timeframe", is_add_form=True)

    assert mock_ui_state.form_data["timeframe"] == TIMEFRAME_OPTIONS[0]


def test_edit_form_field_timeframe_cycle_through_options(form_handlers, mock_ui_state):
    """Timeframe cycles through all options."""
    mock_ui_state.form_data = {}

    # Cycle through all options
    for i in range(len(TIMEFRAME_OPTIONS)):
        form_handlers.edit_form_field("timeframe", is_add_form=True)
        assert mock_ui_state.form_data["timeframe"] == TIMEFRAME_OPTIONS[i]

    # Should wrap around
    form_handlers.edit_form_field("timeframe", is_add_form=True)
    assert mock_ui_state.form_data["timeframe"] == TIMEFRAME_OPTIONS[0]


def test_edit_form_field_timeframe_edit_form(form_handlers, mock_ui_state, sample_project):
    """Timeframe in edit form cycles from project's current value."""
    mock_ui_state.form_data = {}

    form_handlers.edit_form_field("timeframe", is_add_form=False, project=sample_project)

    # Should cycle from "Short-Term" to next option
    current_idx = TIMEFRAME_OPTIONS.index(TIMEFRAME_OPTIONS[1])
    next_idx = (current_idx + 1) % len(TIMEFRAME_OPTIONS)
    assert mock_ui_state.form_data["timeframe"] == TIMEFRAME_OPTIONS[next_idx]


# ==================== Status Field Tests ====================


def test_edit_form_field_status_cycle_from_empty(form_handlers, mock_ui_state):
    """Status cycles from empty to first option."""
    mock_ui_state.form_data = {}

    form_handlers.edit_form_field("status", is_add_form=True)

    assert mock_ui_state.form_data["status"] == STATUS_OPTIONS[0]


def test_edit_form_field_status_cycle_through_options(form_handlers, mock_ui_state):
    """Status cycles through all options."""
    mock_ui_state.form_data = {}

    # Cycle through all options
    for i in range(len(STATUS_OPTIONS)):
        form_handlers.edit_form_field("status", is_add_form=True)
        assert mock_ui_state.form_data["status"] == STATUS_OPTIONS[i]

    # Should wrap around
    form_handlers.edit_form_field("status", is_add_form=True)
    assert mock_ui_state.form_data["status"] == STATUS_OPTIONS[0]





# ==================== Integration Tests ====================


def test_complete_form_workflow_add_project(form_handlers, mock_ui_state):
     """Test complete workflow of filling out add project form."""
     # Start with empty form
     mock_ui_state.form_data = {}

     # Step 1: Enter name
     form_handlers.edit_form_field("name", is_add_form=True)
     assert mock_ui_state.inline_input_mode is True

     # Step 2: Type and save name
     with patch('pm_live.handlers.form_handlers.validate_project_name', return_value=(True, "New Project")):
         mock_ui_state.text_input_buffer = "New Project"
         form_handlers.edit_form_field("name", is_add_form=True)
     assert mock_ui_state.form_data["name"] == "New Project"
     assert mock_ui_state.inline_input_mode is False

     # Step 3: Select timeframe
     form_handlers.edit_form_field("timeframe", is_add_form=True)
     assert mock_ui_state.form_data["timeframe"] in TIMEFRAME_OPTIONS

     # Step 4: Select status
     form_handlers.edit_form_field("status", is_add_form=True)
     assert mock_ui_state.form_data["status"] in STATUS_OPTIONS

     # Verify all required fields are set
     assert "name" in mock_ui_state.form_data
     assert "timeframe" in mock_ui_state.form_data
     assert "status" in mock_ui_state.form_data


def test_edit_existing_project_loads_values(form_handlers, mock_ui_state, sample_project):
    """Test editing existing project loads current values."""
    # Name field should load existing name
    form_handlers.edit_form_field("name", is_add_form=False, project=sample_project)
    assert mock_ui_state.text_input_buffer == "Existing Project"
    mock_ui_state.inline_input_mode = False

    # Description field should load existing description
    form_handlers.edit_form_field("description", is_add_form=False, project=sample_project)
    assert mock_ui_state.text_input_buffer == "Sample description"


# ==================== Status Callback Tests ====================


def test_set_status_calls_context_callback(form_handlers, mock_context):
    """_set_status should call context.show_status."""
    form_handlers._set_status("Test message", True)

    mock_context.show_status.assert_called_once_with("Test message", True)


def test_set_status_clear_message(form_handlers, mock_context):
    """_set_status can clear status message."""
    form_handlers._set_status(None, False)

    mock_context.show_status.assert_called_once_with(None, False)


# ==================== Edge Cases ====================


def test_edit_form_field_unknown_field(form_handlers, mock_ui_state):
    """Editing unknown field does nothing (no crash)."""
    original_form_data = mock_ui_state.form_data.copy()

    # Should not crash
    form_handlers.edit_form_field("unknown_field", is_add_form=True)

    # Form data should be unchanged
    assert mock_ui_state.form_data == original_form_data


def test_edit_form_field_name_with_none_project(form_handlers, mock_ui_state):
    """Editing name in edit form with None project uses empty default."""
    mock_ui_state.inline_input_mode = False

    form_handlers.edit_form_field("name", is_add_form=False, project=None)

    assert mock_ui_state.inline_input_mode is True
    assert mock_ui_state.text_input_buffer == ""


def test_edit_form_field_timeframe_with_none_project(form_handlers, mock_ui_state):
    """Editing timeframe in edit form with None project raises ValueError."""
    mock_ui_state.form_data = {}

    # With no project and no form_data timeframe, this causes ValueError
    # This documents the current behavior - edit form expects project to exist
    with pytest.raises(ValueError):
        form_handlers.edit_form_field("timeframe", is_add_form=False, project=None)


def test_multiple_field_edits(form_handlers, mock_ui_state):
     """Test editing multiple fields in sequence."""
     # Edit timeframe multiple times
     form_handlers.edit_form_field("timeframe", is_add_form=True)
     first_value = mock_ui_state.form_data["timeframe"]

     form_handlers.edit_form_field("timeframe", is_add_form=True)
     second_value = mock_ui_state.form_data["timeframe"]

     # Should be different values
     assert first_value != second_value
     # Both should be valid options
     assert first_value in TIMEFRAME_OPTIONS
     assert second_value in TIMEFRAME_OPTIONS
