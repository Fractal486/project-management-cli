"""Tests for the edit project keybind in Project Browser."""

import pytest
from unittest.mock import Mock, patch

from pm import Project
from pm_live.app import LiveCLI
from pm_live.states import AppState
from pm_live.ui_state import UIState


@pytest.fixture
def mock_manager():
    """Create a mock ProjectManager."""
    manager = Mock()
    manager.projects = []
    manager.custom_field_definitions = []
    manager.default_field_visibility = {}
    manager.list_tasks = {"Tasks": []}
    manager.standalone_tasks = []
    manager.metadata = {}
    return manager


@pytest.fixture
def live_cli(mock_manager):
    """Create a LiveCLI instance with mocked dependencies."""
    with patch("pm_live.app.get_config"), \
         patch("pm_live.app.create_key_bindings"):
        cli = LiveCLI(mock_manager)
    return cli


def test_on_edit_opens_project_edit_form(live_cli, mock_manager):
    """Pressing 'e' on a project in Project Browser opens the edit form."""
    # Setup project
    project = Project(id=1, name="Test Project", status="Active", description="Desc")
    project.custom_field_values = {"custom_1": "value"}
    mock_manager.projects = [project]

    # Setup state
    live_cli.ui_state.state = AppState.PROJECT_BROWSER
    live_cli.ui_state.selected_index = 0
    live_cli.ui_state.active_tab = 0  # Assuming 'All' tab covers this
    live_cli.ui_state.cell_selection_mode = False

    # Patch utils to return our project
    with patch("pm_live.utils.filter_projects_by_tab", return_value=[project]), \
         patch("pm_live.utils.sort_projects_for_display", return_value=[project]):
        
        # Action
        live_cli.on_edit()

    # Assertions
    assert live_cli.ui_state.state == AppState.EDIT_PROJECT
    assert live_cli.ui_state.current_project_id == 1
    assert live_cli.ui_state.form_data["name"] == "Test Project"
    assert live_cli.ui_state.form_data["status"] == "Active"
    assert live_cli.ui_state.form_data["description"] == "Desc"
    assert live_cli.ui_state.form_data["custom_1"] == "value"
    assert live_cli.ui_state.selected_index == 0
    assert live_cli.ui_state.form_field_index == 0


def test_on_edit_ignored_in_cell_selection_mode(live_cli, mock_manager):
    """Pressing 'e' in cell selection mode should not trigger project edit (unless handled elsewhere)."""
    # Setup project
    project = Project(id=1, name="Test Project", status="Planned")
    mock_manager.projects = [project]

    # Setup state
    live_cli.ui_state.state = AppState.PROJECT_BROWSER
    live_cli.ui_state.selected_index = 0
    live_cli.ui_state.cell_selection_mode = True  # Enabled

    # Patch utils
    with patch("pm_live.utils.filter_projects_by_tab", return_value=[project]), \
         patch("pm_live.utils.sort_projects_for_display", return_value=[project]):
        
        # Action
        live_cli.on_edit()

    # Assertions - State should NOT change to EDIT_PROJECT
    # Note: on_edit might trigger other things (like cell edit), but shouldn't go to EDIT_PROJECT form
    assert live_cli.ui_state.state != AppState.EDIT_PROJECT


def test_on_edit_ignored_if_no_project_selected(live_cli, mock_manager):
    """Pressing 'e' with invalid selection should not trigger project edit."""
    mock_manager.projects = []

    # Setup state
    live_cli.ui_state.state = AppState.PROJECT_BROWSER
    live_cli.ui_state.selected_index = 0 # Invalid index as list is empty
    live_cli.ui_state.cell_selection_mode = False

    # Patch utils
    with patch("pm_live.utils.filter_projects_by_tab", return_value=[]), \
         patch("pm_live.utils.sort_projects_for_display", return_value=[]):
        
        # Action
        live_cli.on_edit()

    # Assertions
    assert live_cli.ui_state.state == AppState.PROJECT_BROWSER
