import pytest
from unittest.mock import MagicMock
from pm_live.handlers.key_handlers import KeyHandlers
from pm_live.states import AppState

@pytest.fixture
def key_handler_context():
    context = MagicMock()
    context.ui_state = MagicMock()
    # Configure boolean flags to be False by default so they don't evaluate as Truthy Mocks
    context.ui_state.inline_input_mode = False
    context.ui_state.inline_task_edit_mode = False
    context.ui_state.custom_field_date_edit_mode = False
    context.ui_state.cell_editing = False
    context.ui_state.cell_selection_mode = False
    context.ui_state.inline_list_create_mode = False
    context.ui_state.inline_list_edit_mode = False
    
    context.manager = MagicMock()
    # Mock pinned items to avoid errors in other handlers
    context.manager.get_pinned_items.return_value = []
    return context

@pytest.fixture
def key_handlers(key_handler_context):
    return KeyHandlers(key_handler_context, MagicMock(), MagicMock())

def test_escape_from_main_menu_tabs_settings(key_handlers, key_handler_context):
    """Test escaping from Main Menu Tabs Settings returns to Settings."""
    # Setup state
    key_handler_context.ui_state.state = AppState.MAIN_MENU_TABS_SETTINGS
    
    # Action
    key_handlers.on_escape()
    
    # Assert
    # Expectation: Should transition to SETTINGS and select "Configure Main Menu Tabs" (index 2)
    assert key_handler_context.ui_state.state == AppState.SETTINGS
    assert key_handler_context.ui_state.selected_index == 2

def test_escape_from_quick_stats_settings(key_handlers, key_handler_context):
    """Test escaping from Quick Stats Settings returns to Settings."""
    key_handler_context.ui_state.state = AppState.QUICK_STATS_SETTINGS
    key_handlers.on_escape()
    assert key_handler_context.ui_state.state == AppState.SETTINGS
    assert key_handler_context.ui_state.selected_index == 1

def test_escape_from_deadline_settings(key_handlers, key_handler_context):
    """Test escaping from Deadline Settings returns to Settings."""
    key_handler_context.ui_state.state = AppState.DEADLINE_SETTINGS
    key_handlers.on_escape()
    assert key_handler_context.ui_state.state == AppState.SETTINGS
    assert key_handler_context.ui_state.selected_index == 3

def test_escape_from_task_metadata_settings(key_handlers, key_handler_context):
    """Test escaping from Task Metadata Settings returns to Settings."""
    key_handler_context.ui_state.state = AppState.TASK_METADATA_SETTINGS
    key_handlers.on_escape()
    assert key_handler_context.ui_state.state == AppState.SETTINGS
    assert key_handler_context.ui_state.selected_index == 4

def test_escape_from_stats_none_settings(key_handlers, key_handler_context):
    """Test escaping from Stats None Settings returns to Settings."""
    key_handler_context.ui_state.state = AppState.STATS_NONE_SETTINGS
    key_handlers.on_escape()
    assert key_handler_context.ui_state.state == AppState.SETTINGS
    assert key_handler_context.ui_state.selected_index == 6

def test_escape_from_message_display_settings(key_handlers, key_handler_context):
    """Test escaping from Status Message Settings returns to Settings."""
    key_handler_context.ui_state.state = AppState.MESSAGE_DISPLAY_SETTINGS
    key_handlers.on_escape()
    assert key_handler_context.ui_state.state == AppState.SETTINGS
    assert key_handler_context.ui_state.selected_index == 5
