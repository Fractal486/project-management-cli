from unittest.mock import Mock

from pm_live.handlers.enter_handlers import EnterHandlers
from pm_live.interfaces import HandlerContext
from pm_live.ui_state import UIState


def test_execute_delete_list_resets_quick_add_list_when_deleted():
    manager = Mock()
    manager.get_list_id.return_value = "work-id"
    manager.list_metadata = {"Work": {"id": "work-id"}, "Tasks": {"id": "tasks-id"}}
    manager.remove_pinned_item = Mock()
    manager.mark_list_tasks_modified = Mock()
    manager.save = Mock(return_value=True)

    ui_state = UIState()
    ui_state.task_lists = ["Tasks", "Work", "Personal"]
    ui_state.active_tab = 1
    ui_state.quick_add_list = "Work"
    ui_state.list_tasks = {"Tasks": [], "Work": [], "Personal": []}

    ctx = Mock(spec=HandlerContext)
    ctx.manager = manager
    ctx.ui_state = ui_state
    ctx.get_flat_tasks = Mock(return_value=[])
    ctx.invalidate_task_cache = Mock()
    ctx.exit_application = Mock()
    ctx.show_status = Mock()

    enter_handlers = EnterHandlers(ctx, Mock())

    assert enter_handlers.execute_delete_list({"list_name": "Work"}) is True

    assert "Work" not in ui_state.task_lists
    assert ui_state.quick_add_list == "Tasks"


def test_execute_delete_list_resets_quick_add_list_to_first_remaining_when_tasks_missing():
    manager = Mock()
    manager.get_list_id.return_value = "work-id"
    manager.list_metadata = {"Work": {"id": "work-id"}, "Personal": {"id": "personal-id"}}
    manager.remove_pinned_item = Mock()
    manager.mark_list_tasks_modified = Mock()
    manager.save = Mock(return_value=True)

    ui_state = UIState()
    ui_state.task_lists = ["Work", "Personal"]
    ui_state.active_tab = 0
    ui_state.quick_add_list = "Work"
    ui_state.list_tasks = {"Work": [], "Personal": []}

    ctx = Mock(spec=HandlerContext)
    ctx.manager = manager
    ctx.ui_state = ui_state
    ctx.get_flat_tasks = Mock(return_value=[])
    ctx.invalidate_task_cache = Mock()
    ctx.exit_application = Mock()
    ctx.show_status = Mock()

    enter_handlers = EnterHandlers(ctx, Mock())

    assert enter_handlers.execute_delete_list({"list_name": "Work"}) is True
    assert ui_state.quick_add_list == "Personal"
