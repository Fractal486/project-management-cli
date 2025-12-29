
import pytest
from unittest.mock import Mock

from pm_live.handlers.enter_handlers import EnterHandlers
from pm_live.interfaces import HandlerContext
from pm_live.ui_state import UIState
from pm_live.states import AppState
from pm_live.custom_fields import FIELD_TYPES, NUMBER_FORMATS

@pytest.fixture
def mock_manager():
    """Create a mock DataManagerProtocol."""
    manager = Mock()
    manager.custom_field_definitions = []
    manager.mark_dirty = Mock()
    manager.save = Mock(return_value=True)
    return manager

@pytest.fixture
def mock_ui_state():
    """Create a mock UIState."""
    ui_state = UIState()
    ui_state.state = AppState.EDIT_CUSTOM_FIELD
    ui_state.form_field_index = 0
    ui_state.form_data = {}
    ui_state.inline_input_mode = False
    ui_state.text_input_buffer = ""
    ui_state.status_message = None
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
def mock_bookmark_handlers():
    """Create a mock BookmarkHandlers."""
    return Mock()

@pytest.fixture
def enter_handlers(mock_context, mock_bookmark_handlers):
    """Create a EnterHandlers instance."""
    return EnterHandlers(mock_context, mock_bookmark_handlers)

def test_handle_edit_custom_field_enter_cycles_type_correctly(enter_handlers, mock_ui_state):
    """Test that selecting Type field (index 3) cycles type, even when type is Number."""
    # Setup: Type is 'number', so Format field exists below it.
    mock_ui_state.form_data = {
        'field_type': 'number',
        'number_format': 'number'
    }
    
    # Core fields are 3 (label, visible, required). Type is at index 3.
    mock_ui_state.form_field_index = 3 
    
    # Action
    enter_handlers.handle_edit_custom_field_enter()
    
    # Assert
    # Should cycle from 'number' to next type ('date')
    assert mock_ui_state.form_data['field_type'] == 'date'
    # Should NOT have cycled number_format (it should remain 'number')
    assert mock_ui_state.form_data['number_format'] == 'number'

def test_handle_edit_custom_field_enter_cycles_format_correctly(enter_handlers, mock_ui_state):
    """Test that selecting Format field (index 4) cycles format when type is Number."""
    # Setup: Type is 'number'.
    mock_ui_state.form_data = {
        'field_type': 'number',
        'number_format': 'number'
    }
    
    # Core fields (3) + Type (1) = 4. Format is at index 4.
    mock_ui_state.form_field_index = 4
    
    # Action
    enter_handlers.handle_edit_custom_field_enter()
    
    # Assert
    # Type should stay 'number'
    assert mock_ui_state.form_data['field_type'] == 'number'
    # Format should cycle from 'number' to next format ('currency')
    assert mock_ui_state.form_data['number_format'] == 'currency'

def test_handle_edit_custom_field_enter_cycles_currency_symbol(enter_handlers, mock_ui_state):
    """Test that selecting Currency Symbol field enters inline edit."""
    # Setup: Type is 'number', Format is 'currency'.
    mock_ui_state.form_data = {
        'field_type': 'number',
        'number_format': 'currency',
        'currency_symbol': '$'
    }
    
    # Core (3) + Type (1) + Format (1) = 5. Currency Symbol at index 5.
    mock_ui_state.form_field_index = 5
    
    # Action
    enter_handlers.handle_edit_custom_field_enter()
    
    # Assert
    assert mock_ui_state.inline_input_mode is True
    assert mock_ui_state.text_input_buffer == '$'
