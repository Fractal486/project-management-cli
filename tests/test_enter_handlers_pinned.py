"""Tests for pinned-section enter interactions in the main menu."""

from unittest.mock import Mock

import pytest

from pm_live.handlers.enter_handlers import EnterHandlers
from pm_live.interfaces import HandlerContext
from pm_live.states import AppState
from pm_live.ui_state import UIState


@pytest.fixture
def mock_context() -> Mock:
    manager = Mock()
    manager.get_pinned_items.return_value = []
    manager.list_tasks = {}
    ui_state = UIState()
    ui_state.state = AppState.MAIN_MENU
    ctx = Mock(spec=HandlerContext)
    ctx.manager = manager
    ctx.ui_state = ui_state
    ctx.get_flat_tasks = Mock(return_value=[])
    ctx.invalidate_task_cache = Mock()
    ctx.exit_application = Mock()
    ctx.show_status = Mock()
    ctx.update_console_width = Mock()
    ctx.update_quick_stats_selection = Mock()
    ctx.update_main_menu_tabs_selection = Mock()
    ctx.persist_collapsed_tasks = Mock()
    return ctx


def test_main_menu_pinned_list_section_toggles_expansion(mock_context: Mock) -> None:
    ui_state = mock_context.ui_state
    ui_state.in_pinned_section = True
    ui_state.pinned_selected_index = 0
    ui_state.pinned_display_items = [
        {"kind": "list_section", "list_name": "Work", "section_idx": 2}
    ]

    enter_handlers = EnterHandlers(mock_context, Mock())

    enter_handlers.handle_main_menu_enter()
    assert "Work:2" in ui_state.expanded_pinned_list_sections

    enter_handlers.handle_main_menu_enter()
    assert "Work:2" not in ui_state.expanded_pinned_list_sections


def test_main_menu_pinned_list_toggle_resets_section_expansion_for_list(mock_context: Mock) -> None:
    ui_state = mock_context.ui_state
    ui_state.in_pinned_section = True
    ui_state.pinned_selected_index = 0
    ui_state.expanded_pinned_list_sections = {"Work:2", "Other:0"}
    ui_state.pinned_display_items = [
        {"kind": "pinned", "item": {"type": "list", "name": "Work"}}
    ]

    enter_handlers = EnterHandlers(mock_context, Mock())
    enter_handlers.handle_main_menu_enter()

    assert "Work" in ui_state.expanded_pinned_lists
    assert "Work:2" not in ui_state.expanded_pinned_list_sections
    assert "Other:0" in ui_state.expanded_pinned_list_sections
