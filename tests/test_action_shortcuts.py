"""Regression tests for numeric footer action shortcuts."""

from unittest.mock import Mock

import pytest

from pm_live.handlers.enter_handlers import EnterHandlers
from pm_live.handlers.key_handlers import KeyHandlers
from pm_live.interfaces import HandlerContext
from pm_live.ui_state import UIState
from pm_live.states import AppState


@pytest.fixture
def ui_state() -> UIState:
    state = UIState()
    state.state = AppState.TASK_LIST
    state.selected_index = 0
    state.active_tab = 0
    state.inline_input_mode = False
    state.inline_task_edit_mode = False
    state.text_input_buffer = ""
    state.collapsed_tasks = set()
    state.task_lists = ["Tasks"]
    # Minimal mapping: one default list with an empty list/section.
    state.list_tasks = {"Tasks": []}
    return state


@pytest.fixture
def manager() -> Mock:
    m = Mock()
    m.projects = []
    m.bookmarks = []
    m.list_tasks = {"Tasks": []}
    m.list_metadata = {"Tasks": {"show_done_section": True}}
    m.custom_field_definitions = []
    m.default_field_visibility = {}
    m.standalone_tasks = []
    m.save = Mock(return_value=True)
    m.mark_list_tasks_modified = Mock()
    return m


@pytest.fixture
def context(manager: Mock, ui_state: UIState) -> Mock:
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


def test_task_list_number_shortcut_triggers_footer_action(context: Mock, ui_state: UIState) -> None:
    """Pressing 1 on TASK_LIST should execute the first footer action (New List) immediately."""
    task_handlers = Mock()
    bookmark_handlers = Mock()
    enter_handlers = EnterHandlers(context, bookmark_handlers, task_handlers)
    key_handlers = KeyHandlers(context, task_handlers, enter_handlers)
    enter_handlers.set_key_handlers(key_handlers)

    # Sanity: action 1 should map to the "New List" footer action.
    layout = enter_handlers.build_task_list_layout()
    assert layout
    assert layout["new_list_index"] is not None

    # Trigger the numeric shortcut.
    key_handlers.on_action_shortcut(1)

    assert ui_state.state == AppState.EDIT_TAB
