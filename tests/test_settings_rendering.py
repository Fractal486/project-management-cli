import pytest
import re
from unittest.mock import MagicMock, patch
import pytest
from pm_live.render.settings import DeadlineSettingsRenderer, StatsNoneSettingsRenderer

def strip_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

@pytest.fixture
def mock_config():
    with patch("pm_live.config.get_config") as mock:
        config = MagicMock()
        mock.return_value = config
        yield config

def test_deadline_settings_renderer_always_shows_description(mock_config):
    mock_config.deadline_display_mode = "relative"
    renderer = DeadlineSettingsRenderer()
    context = {"selected_index": 0} # Select first item
    
    output = renderer.render(context)
    clean_output = strip_ansi(output)
    
    # Check if description for the SECOND item (not selected) is present
    # "Show full date (e.g., '2025-10-31')" is the description for "Exact Date"
    assert "Show full date (e.g., '2025-10-31')" in clean_output

def test_stats_none_settings_renderer_always_shows_description(mock_config):
    mock_config.show_none_in_stats = True
    renderer = StatsNoneSettingsRenderer()
    context = {"selected_index": 0} # Select first item
    
    output = renderer.render(context)
    clean_output = strip_ansi(output)
    
    # Check if description for the SECOND item (not selected) is present
    # "Only display fields with actual values" is for "Hide 'None'"
    assert "Only display fields with actual values" in clean_output

from pm_live.render.settings import SettingsRenderer

def test_settings_renderer_stats_none_toggle_display(mock_config):
    mock_config.show_none_in_stats = True
    renderer = SettingsRenderer()
    context = {"selected_index": 0}
    
    output = renderer.render(context)
    clean_output = strip_ansi(output)
    
    # Check that it prints "Show 'None' in Project Stats" WITHOUT ": On" or ": Off"
    # Note: strip_ansi removes colors, but text "On" or "Off" would remain if printed.
    
    assert "Show 'None' in Project Stats" in clean_output
    assert "Show 'None' in Project Stats: On" not in clean_output
    assert "Show 'None' in Project Stats: Off" not in clean_output

def test_settings_renderer_help_overlay_display(mock_config):
    renderer = SettingsRenderer()
    # Select the help overlay option (index 10 based on settings_items list)
    context = {"selected_index": 10} 
    
    output = renderer.render(context)
    clean_output = strip_ansi(output)
    
    # Check that it prints the label without the note
    assert "Press 'h' to open keybindings overlay" in clean_output
    assert "(press Enter to open now)" not in clean_output
