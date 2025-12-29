"""Tests for UI state management (pm_live/ui_state.py)."""

import pytest
from datetime import datetime
from copy import deepcopy

from pm_live.ui_state import UIState
from pm_live.states import AppState
from pm_live.quick_stats import DEFAULT_QUICK_STATS
from pm_live.main_menu_tabs import DEFAULT_MAIN_MENU_TABS


# ==================== Initialization Tests ====================


def test_ui_state_default_initialization():
    """UIState initializes with correct default values."""
    state = UIState()

    assert state.state == AppState.MAIN_MENU
    assert state.selected_index == 0
    assert state.active_tab == 0
    assert state.current_project_id is None
    assert state.current_list_index is None
    assert state.delete_context is None
    assert state.text_input_buffer == ""
    assert state.form_data == {}
    assert state.form_field_index == 0
    assert state.editing_list_name is None
    assert state.history_stack == []
    assert state.inline_input_mode is False
    assert state.pending_section_add is False
    assert state.collapsed_tasks == {"section_completed"}
    assert state.task_lists == ["Tasks"]
    assert state.list_tasks == {}
    assert state.quick_add_priority is None
    assert state.quick_add_field_index == 0
    assert state.quick_add_deadline is None
    assert state.quick_add_deadline_component == 0
    assert state.quick_add_deadline_edit_mode is False
    now = datetime.now()
    assert state.calendar_year == now.year
    assert state.calendar_month == now.month
    assert state.calendar_selected_day is None
    assert state.calendar_navigation_focus == "day"
    assert state.calendar_task_selected_index == 0
    assert state.quick_stats_selection == set(DEFAULT_QUICK_STATS)
    assert state.main_menu_tabs_selection == set(DEFAULT_MAIN_MENU_TABS)
    assert state.status_message is None
    assert state.status_is_error is False
    assert state.show_help is False


def test_ui_state_custom_initialization():
    """UIState can be initialized with custom values."""
    state = UIState(
        state=AppState.PROJECT_DETAILS,
        selected_index=5,
        active_tab=2,
        current_project_id=42,
        text_input_buffer="Test input",
        inline_input_mode=True,
    )

    assert state.state == AppState.PROJECT_DETAILS
    assert state.selected_index == 5
    assert state.active_tab == 2
    assert state.current_project_id == 42
    assert state.text_input_buffer == "Test input"
    assert state.inline_input_mode is True


def test_ui_state_mutable_defaults():
    """UIState creates separate default objects for each instance."""
    state1 = UIState()
    state2 = UIState()

    # Modify mutable fields on state1
    state1.form_data["key"] = "value"
    state1.history_stack.append("item")
    state1.collapsed_tasks.add("new_task")
    state1.task_lists.append("New List")

    # state2 should have independent defaults
    assert state2.form_data == {}
    assert state2.history_stack == []
    assert state2.collapsed_tasks == {"section_completed"}
    assert state2.task_lists == ["Tasks"]


# ==================== State Transition Tests ====================


def test_change_app_state():
    """Can change the active app state."""
    state = UIState()
    assert state.state == AppState.MAIN_MENU

    state.state = AppState.PROJECT_BROWSER
    assert state.state == AppState.PROJECT_BROWSER

    state.state = AppState.TASK_LIST
    assert state.state == AppState.TASK_LIST


def test_all_app_states_accessible():
    """All AppState values can be assigned to UIState."""
    state = UIState()

    for app_state in AppState:
        state.state = app_state
        assert state.state == app_state


# ==================== Navigation State Tests ====================


def test_update_selected_index():
    """Can update the selected index."""
    state = UIState()
    assert state.selected_index == 0

    state.selected_index = 10
    assert state.selected_index == 10

    state.selected_index = 0
    assert state.selected_index == 0


def test_update_active_tab():
    """Can update the active tab."""
    state = UIState()
    assert state.active_tab == 0

    state.active_tab = 2
    assert state.active_tab == 2


def test_update_current_project_id():
    """Can update the current project ID."""
    state = UIState()
    assert state.current_project_id is None

    state.current_project_id = 123
    assert state.current_project_id == 123

    state.current_project_id = None
    assert state.current_project_id is None


def test_update_current_list_index():
    """Can update the current list index."""
    state = UIState()
    assert state.current_list_index is None

    state.current_list_index = 5
    assert state.current_list_index == 5


# ==================== Input Mode Tests ====================


def test_toggle_inline_input_mode():
    """Can toggle inline input mode."""
    state = UIState()
    assert state.inline_input_mode is False

    state.inline_input_mode = True
    assert state.inline_input_mode is True

    state.inline_input_mode = False
    assert state.inline_input_mode is False


def test_text_input_buffer_management():
    """Can manage text input buffer."""
    state = UIState()
    assert state.text_input_buffer == ""

    state.text_input_buffer = "Hello"
    assert state.text_input_buffer == "Hello"

    state.text_input_buffer += " World"
    assert state.text_input_buffer == "Hello World"

    state.text_input_buffer = ""
    assert state.text_input_buffer == ""


def test_pending_section_add_flag():
    """Can toggle pending section add flag."""
    state = UIState()
    assert state.pending_section_add is False

    state.pending_section_add = True
    assert state.pending_section_add is True


# ==================== Form Management Tests ====================


def test_form_data_management():
    """Can manage form data dictionary."""
    state = UIState()
    assert state.form_data == {}

    state.form_data["name"] = "Test Project"
    state.form_data["timeframe"] = "Short-Term"

    assert state.form_data["name"] == "Test Project"
    assert state.form_data["timeframe"] == "Short-Term"

    state.form_data.clear()
    assert state.form_data == {}


def test_form_field_index_navigation():
    """Can navigate through form fields."""
    state = UIState()
    assert state.form_field_index == 0

    state.form_field_index = 1
    assert state.form_field_index == 1

    state.form_field_index = 3
    assert state.form_field_index == 3


def test_editing_list_name():
    """Can track which list is being edited."""
    state = UIState()
    assert state.editing_list_name is None

    state.editing_list_name = "Work Tasks"
    assert state.editing_list_name == "Work Tasks"

    state.editing_list_name = None
    assert state.editing_list_name is None


# ==================== Collapsed Tasks Tests ====================


def test_collapsed_tasks_default():
    """Collapsed tasks defaults to completed section collapsed."""
    state = UIState()
    assert "section_completed" in state.collapsed_tasks


def test_add_collapsed_task():
    """Can add tasks to collapsed set."""
    state = UIState()

    state.collapsed_tasks.add("task_path_1")
    assert "task_path_1" in state.collapsed_tasks
    assert "section_completed" in state.collapsed_tasks


def test_remove_collapsed_task():
    """Can remove tasks from collapsed set."""
    state = UIState()
    state.collapsed_tasks.add("task_path_1")

    state.collapsed_tasks.remove("task_path_1")
    assert "task_path_1" not in state.collapsed_tasks


def test_collapsed_tasks_list_sections():
    """Can collapse list-specific sections."""
    state = UIState()

    state.collapsed_tasks.add("Work:Important")
    state.collapsed_tasks.add("Personal:Urgent")

    assert "Work:Important" in state.collapsed_tasks
    assert "Personal:Urgent" in state.collapsed_tasks


# ==================== Task Views Tests ====================


def test_task_lists_default():
    """Task lists default to a single Tasks list."""
    state = UIState()
    assert state.task_lists == ["Tasks"]


def test_add_task_list():
    """Can add new task lists."""
    state = UIState()

    state.task_lists.append("Work")
    state.task_lists.append("Personal")

    assert state.task_lists == ["Tasks", "Work", "Personal"]


def test_list_tasks_mapping():
    """Can map list names to task lists."""
    state = UIState()

    state.list_tasks["Tasks"] = [Mock(name="Task 1")]
    state.list_tasks["Work"] = [Mock(name="Work Task")]

    assert "Tasks" in state.list_tasks
    assert "Work" in state.list_tasks


# ==================== Quick Add Tests ====================


def test_quick_add_priority():
    """Can set quick add priority."""
    state = UIState()
    assert state.quick_add_priority is None

    state.quick_add_priority = "High"
    assert state.quick_add_priority == "High"


def test_quick_add_field_index():
    """Can navigate quick add fields."""
    state = UIState()
    assert state.quick_add_field_index == 0

    state.quick_add_field_index = 1
    assert state.quick_add_field_index == 1

    state.quick_add_field_index = 2
    assert state.quick_add_field_index == 2


def test_quick_add_deadline():
    """Can set quick add deadline."""
    state = UIState()
    assert state.quick_add_deadline is None

    state.quick_add_deadline = "2025-12-31"
    assert state.quick_add_deadline == "2025-12-31"


def test_quick_add_deadline_component():
    """Can navigate deadline components."""
    state = UIState()
    assert state.quick_add_deadline_component == 0

    state.quick_add_deadline_component = 1  # Month
    assert state.quick_add_deadline_component == 1

    state.quick_add_deadline_component = 2  # Day
    assert state.quick_add_deadline_component == 2


def test_quick_add_deadline_edit_mode():
    """Can toggle deadline edit mode."""
    state = UIState()
    assert state.quick_add_deadline_edit_mode is False

    state.quick_add_deadline_edit_mode = True
    assert state.quick_add_deadline_edit_mode is True


# ==================== Quick Stats Tests ====================


def test_quick_stats_selection_default():
    """Quick stats selection defaults to DEFAULT_QUICK_STATS."""
    state = UIState()
    assert state.quick_stats_selection == set(DEFAULT_QUICK_STATS)


def test_quick_stats_selection_modification():
    """Can modify quick stats selection."""
    state = UIState()

    state.quick_stats_selection.add("bookmarks")
    assert "bookmarks" in state.quick_stats_selection

    state.quick_stats_selection.remove("uncompleted_projects")
    assert "uncompleted_projects" not in state.quick_stats_selection


def test_main_menu_tabs_selection_default():
    """Main menu tabs selection defaults to DEFAULT_MAIN_MENU_TABS."""
    state = UIState()
    assert state.main_menu_tabs_selection == set(DEFAULT_MAIN_MENU_TABS)


def test_main_menu_tabs_selection_modification():
    """Can modify main menu tabs selection."""
    state = UIState()

    state.main_menu_tabs_selection.add("quick_add")
    assert "quick_add" in state.main_menu_tabs_selection


# ==================== Status Message Tests ====================


def test_status_message_display():
    """Can set and clear status messages."""
    state = UIState()
    assert state.status_message is None
    assert state.status_is_error is False

    state.status_message = "Operation successful"
    assert state.status_message == "Operation successful"

    state.status_message = None
    assert state.status_message is None


def test_status_message_error_flag():
    """Can set error flag for status messages."""
    state = UIState()

    state.status_message = "An error occurred"
    state.status_is_error = True

    assert state.status_message == "An error occurred"
    assert state.status_is_error is True


# ==================== History Stack Tests ====================


def test_history_stack_navigation():
    """Can manage history stack for back navigation."""
    state = UIState()
    assert state.history_stack == []

    state.history_stack.append(AppState.MAIN_MENU)
    state.history_stack.append(AppState.PROJECT_BROWSER)

    assert len(state.history_stack) == 2

    previous = state.history_stack.pop()
    assert previous == AppState.PROJECT_BROWSER
    assert len(state.history_stack) == 1


# ==================== Delete Confirmation Tests ====================


def test_delete_context():
    """Can store delete confirmation context."""
    state = UIState()
    assert state.delete_context is None

    state.delete_context = {
        "type": "project",
        "id": 123,
        "name": "Test Project"
    }

    assert state.delete_context["type"] == "project"
    assert state.delete_context["id"] == 123


# ==================== Help and Conflict Tests ====================


def test_show_help_toggle():
    """Can toggle help overlay visibility."""
    state = UIState()
    assert state.show_help is False

    state.show_help = True
    assert state.show_help is True

    state.show_help = False
    assert state.show_help is False


# ==================== Integration Tests ====================


def test_complete_workflow_main_to_project_details():
    """Test complete workflow from main menu to project details."""
    state = UIState()

    # Start at main menu
    assert state.state == AppState.MAIN_MENU
    assert state.selected_index == 0

    # Navigate to project browser
    state.state = AppState.PROJECT_BROWSER
    state.selected_index = 0
    state.active_tab = 0

    # Select a project
    state.selected_index = 2
    state.current_project_id = 5

    # Navigate to project details
    state.state = AppState.PROJECT_DETAILS
    assert state.state == AppState.PROJECT_DETAILS
    assert state.current_project_id == 5


def test_form_workflow():
    """Test complete form workflow for adding a project."""
    state = UIState()

    # Enter add project state
    state.state = AppState.ADD_PROJECT
    state.form_field_index = 0
    state.inline_input_mode = False

    # Fill form data
    state.form_data = {
        "name": "New Project",
        "timeframe": "Short-Term",
        "status": "Planned",
    }

    # Navigate through form fields
    state.form_field_index = 1
    state.form_field_index = 2
    state.form_field_index = 3

    # Submit form (reset)
    state.form_data.clear()
    state.form_field_index = 0
    state.state = AppState.PROJECT_BROWSER

    assert state.form_data == {}
    assert state.state == AppState.PROJECT_BROWSER


def test_task_list_workflow_with_lists():
    """Test task list workflow with multiple lists."""
    state = UIState()

    # Start with default task list
    assert state.task_lists == ["Tasks"]
    assert state.active_tab == 0

    # Add new lists
    state.task_lists.append("Work")
    state.task_lists.append("Personal")

    # Switch between tabs
    state.active_tab = 1  # Work
    assert state.task_lists[state.active_tab] == "Work"

    state.active_tab = 2  # Personal
    assert state.task_lists[state.active_tab] == "Personal"

    # Collapse sections in lists
    state.collapsed_tasks.add("Work:Important")
    assert "Work:Important" in state.collapsed_tasks


def test_quick_add_workflow():
    """Test complete quick add workflow."""
    state = UIState()

    # Enter quick add mode
    state.inline_input_mode = True
    state.quick_add_field_index = 0
    state.text_input_buffer = "New task from quick add"

    # Navigate to priority
    state.quick_add_field_index = 1
    state.quick_add_priority = "High"

    # Navigate to deadline
    state.quick_add_field_index = 2
    state.quick_add_deadline = "2025-12-31"
    state.quick_add_deadline_edit_mode = True
    state.quick_add_deadline_component = 0  # Year

    # Submit (reset)
    state.text_input_buffer = ""
    state.quick_add_priority = None
    state.quick_add_deadline = None
    state.quick_add_field_index = 0
    state.inline_input_mode = False
    state.quick_add_deadline_edit_mode = False

    assert state.text_input_buffer == ""
    assert state.quick_add_priority is None


def test_status_message_workflow():
    """Test status message display and clearing."""
    state = UIState()

    # Show success message
    state.status_message = "Project created successfully"
    state.status_is_error = False

    assert state.status_message == "Project created successfully"
    assert state.status_is_error is False

    # Show error message
    state.status_message = "Failed to save project"
    state.status_is_error = True

    assert state.status_message == "Failed to save project"
    assert state.status_is_error is True

    # Clear message
    state.status_message = None
    state.status_is_error = False

    assert state.status_message is None


# ==================== Edge Cases ====================


def test_negative_indices():
    """UIState accepts negative indices (Python allows this)."""
    state = UIState()

    state.selected_index = -1
    assert state.selected_index == -1


def test_very_large_indices():
    """UIState accepts very large indices."""
    state = UIState()

    state.selected_index = 999999
    assert state.selected_index == 999999


def test_empty_task_lists():
    """Can clear task lists (though UI should prevent this)."""
    state = UIState()
    state.task_lists.clear()
    assert state.task_lists == []


def test_deep_nested_form_data():
    """Can store nested structures in form_data."""
    state = UIState()

    state.form_data = {
        "project": {
            "name": "Test",
            "tasks": [
                {"name": "Task 1"},
                {"name": "Task 2"},
            ]
        }
    }

    assert state.form_data["project"]["tasks"][0]["name"] == "Task 1"


# Mock class for testing
class Mock:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
