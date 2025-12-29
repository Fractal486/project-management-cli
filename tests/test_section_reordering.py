
import pytest
from unittest.mock import MagicMock, patch
from pm_live.app import LiveCLI
from pm_live.states import AppState
from pm_live.ui_state import UIState

class MockManager:
    def __init__(self):
        self.config = MagicMock()
        self.list_tasks = {}
        self.standalone_tasks = []
        self.metadata = {}
        self.is_pinned = MagicMock(return_value=False)
    def save(self):
        pass

@pytest.fixture
def mock_cli():
    with patch('pm_live.app.get_config'), \
         patch('pm_live.app.create_key_bindings'), \
         patch('pm_live.app.Console'):
        manager = MockManager()
        cli = LiveCLI(manager)
        return cli

def test_handle_section_move_up(mock_cli):
    cli = mock_cli
    cli.ui_state.state = AppState.EDIT_TAB
    
    # Setup sections
    sections = [
        {'name': 'Section 1', 'tasks': []},
        {'name': 'Section 2', 'tasks': []},
        {'name': 'Section 3', 'tasks': []}
    ]
    cli.ui_state.form_data = {
        'mode': 'sections',
        'sections': sections
    }
    
    # Select Section 2
    # Field indices: 0=Name, 1=Color, 2=Done Section, 3=Mode, 4+=Sections
    cli.ui_state.form_field_index = 5
    
    # Move up
    cli._handle_section_move_up()
    
    # Check order: Section 2 should now be at index 0 in sections list
    assert cli.ui_state.form_data['sections'][0]['name'] == 'Section 2'
    assert cli.ui_state.form_data['sections'][1]['name'] == 'Section 1'
    # Check selection: should follow Section 2 to index 4
    assert cli.ui_state.form_field_index == 4

def test_handle_section_move_up_top_edge_case(mock_cli):
    cli = mock_cli
    cli.ui_state.state = AppState.EDIT_TAB
    
    sections = [
        {'name': 'Section 1', 'tasks': []},
        {'name': 'Section 2', 'tasks': []}
    ]
    cli.ui_state.form_data = {
        'mode': 'sections',
        'sections': sections
    }
    
    # Select Section 1
    cli.ui_state.form_field_index = 4
    
    # Move up (should do nothing)
    cli._handle_section_move_up()
    
    assert cli.ui_state.form_data['sections'][0]['name'] == 'Section 1'
    assert cli.ui_state.form_field_index == 4

def test_handle_section_move_down(mock_cli):
    cli = mock_cli
    cli.ui_state.state = AppState.EDIT_TAB
    
    sections = [
        {'name': 'Section 1', 'tasks': []},
        {'name': 'Section 2', 'tasks': []},
        {'name': 'Section 3', 'tasks': []}
    ]
    cli.ui_state.form_data = {
        'mode': 'sections',
        'sections': sections
    }
    
    # Select Section 2
    cli.ui_state.form_field_index = 5
    
    # Move down
    cli._handle_section_move_down()
    
    # Check order: Section 2 should now be at index 2 in sections list
    assert cli.ui_state.form_data['sections'][1]['name'] == 'Section 3'
    assert cli.ui_state.form_data['sections'][2]['name'] == 'Section 2'
    # Check selection: should follow Section 2 to index 6
    assert cli.ui_state.form_field_index == 6

def test_handle_section_move_down_bottom_edge_case(mock_cli):
    cli = mock_cli
    cli.ui_state.state = AppState.EDIT_TAB
    
    sections = [
        {'name': 'Section 1', 'tasks': []},
        {'name': 'Section 2', 'tasks': []}
    ]
    cli.ui_state.form_data = {
        'mode': 'sections',
        'sections': sections
    }
    
    # Select Section 2
    cli.ui_state.form_field_index = 5
    
    # Move down (should do nothing)
    cli._handle_section_move_down()
    
    assert cli.ui_state.form_data['sections'][1]['name'] == 'Section 2'
    assert cli.ui_state.form_field_index == 5

def test_handle_section_move_not_on_section(mock_cli):
    cli = mock_cli
    cli.ui_state.state = AppState.EDIT_TAB
    
    sections = [
        {'name': 'Section 1', 'tasks': []}
    ]
    cli.ui_state.form_data = {
        'mode': 'sections',
        'sections': sections
    }
    
    # Select Mode (index 2)
    cli.ui_state.form_field_index = 2
    
    cli._handle_section_move_up()
    assert cli.ui_state.form_field_index == 2
    
    cli._handle_section_move_down()
    assert cli.ui_state.form_field_index == 2

def test_handle_section_move_wrong_mode(mock_cli):
    cli = mock_cli
    cli.ui_state.state = AppState.EDIT_TAB
    
    sections = [
        {'name': 'Section 1', 'tasks': []},
        {'name': 'Section 2', 'tasks': []}
    ]
    cli.ui_state.form_data = {
        'mode': 'normal', # Not 'sections'
        'sections': sections
    }
    
    cli.ui_state.form_field_index = 3
    cli._handle_section_move_down()
    
    # Should not move
    assert cli.ui_state.form_data['sections'][0]['name'] == 'Section 1'
    assert cli.ui_state.form_field_index == 3

def test_handle_section_move_add_button(mock_cli):
    cli = mock_cli
    cli.ui_state.state = AppState.EDIT_TAB
    
    sections = [
        {'name': 'Section 1', 'tasks': []}
    ]
    cli.ui_state.form_data = {
        'mode': 'sections',
        'sections': sections
    }
    
    # Select Add Section button (index 3 + len(sections) = 4)
    cli.ui_state.form_field_index = 4
    
    cli._handle_section_move_up()
    assert cli.ui_state.form_field_index == 4
    
    cli._handle_section_move_down()
    assert cli.ui_state.form_field_index == 4
