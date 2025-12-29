"""Tests for bookmark reordering with Ctrl+Up/Down arrows."""

import pytest
from unittest.mock import Mock, MagicMock
from pm import Bookmark, BookmarkList
from pm_live.handlers.bookmark_handlers import BookmarkHandlers
from pm_live.interfaces import HandlerContext


@pytest.fixture
def mock_manager():
    """Create a mock manager."""
    manager = Mock()
    manager.bookmarks = [
        Bookmark(title="Google", url="https://google.com"),
        Bookmark(title="GitHub", url="https://github.com"),
        BookmarkList(title="Dev Resources", items=[
            Bookmark(title="Stack Overflow", url="https://stackoverflow.com"),
            Bookmark(title="MDN", url="https://mdn.org"),
        ]),
    ]
    manager.mark_dirty = Mock()
    manager.save = Mock()
    return manager


@pytest.fixture
def mock_ui_state():
    """Create a mock UI state."""
    ui_state = Mock()
    ui_state.selected_index = 0
    ui_state.current_list_index = None
    ui_state.status_message = ""
    ui_state.status_is_error = False
    return ui_state


@pytest.fixture
def mock_context(mock_manager, mock_ui_state):
    """Create a mock handler context."""
    context = Mock(spec=HandlerContext)
    context.manager = mock_manager
    context.ui_state = mock_ui_state
    return context


@pytest.fixture
def bookmark_handlers(mock_context):
    """Create a BookmarkHandlers instance."""
    return BookmarkHandlers(mock_context)


def test_handle_bookmarks_move_up_success(bookmark_handlers, mock_manager, mock_ui_state):
    """Move a bookmark up in the main bookmarks list."""
    mock_ui_state.selected_index = 1  # Selected "GitHub"

    bookmark_handlers.handle_bookmarks_move_up()

    # "GitHub" should move to index 0, "Google" to index 1
    assert mock_manager.bookmarks[0].title == "GitHub"
    assert mock_manager.bookmarks[1].title == "Google"
    assert mock_ui_state.selected_index == 0
    mock_manager.mark_dirty.assert_called_once()
    mock_manager.save.assert_called_once()


def test_handle_bookmarks_move_up_first_item(bookmark_handlers, mock_manager, mock_ui_state):
    """Cannot move up when already first."""
    mock_ui_state.selected_index = 0  # Selected "Google"

    bookmark_handlers.handle_bookmarks_move_up()

    # Should not move
    assert mock_manager.bookmarks[0].title == "Google"
    mock_manager.mark_dirty.assert_not_called()


def test_handle_bookmarks_move_down_success(bookmark_handlers, mock_manager, mock_ui_state):
    """Move a bookmark down in the main bookmarks list."""
    mock_ui_state.selected_index = 0  # Selected "Google"

    bookmark_handlers.handle_bookmarks_move_down()

    # "Google" should move to index 1, "GitHub" to index 0
    assert mock_manager.bookmarks[0].title == "GitHub"
    assert mock_manager.bookmarks[1].title == "Google"
    assert mock_ui_state.selected_index == 1
    mock_manager.mark_dirty.assert_called_once()
    mock_manager.save.assert_called_once()


def test_handle_bookmarks_move_down_last_item(bookmark_handlers, mock_manager, mock_ui_state):
    """Cannot move down when already last."""
    mock_ui_state.selected_index = 2  # Selected "Dev Resources" list

    bookmark_handlers.handle_bookmarks_move_down()

    # Should not move
    assert mock_manager.bookmarks[2].title == "Dev Resources"
    mock_manager.mark_dirty.assert_not_called()


def test_handle_bookmark_list_move_up_success(bookmark_handlers, mock_manager, mock_ui_state):
    """Move a bookmark up within a list."""
    mock_ui_state.selected_index = 1  # Selected "MDN"
    mock_ui_state.current_list_index = 2  # In "Dev Resources" list

    bookmark_handlers.handle_bookmark_list_move_up()

    # "MDN" should move to index 0, "Stack Overflow" to index 1
    dev_list = mock_manager.bookmarks[2]
    assert dev_list.items[0].title == "MDN"
    assert dev_list.items[1].title == "Stack Overflow"
    assert mock_ui_state.selected_index == 0
    mock_manager.mark_dirty.assert_called_once()
    mock_manager.save.assert_called_once()


def test_handle_bookmark_list_move_up_first_item(bookmark_handlers, mock_manager, mock_ui_state):
    """Cannot move up when already first in list."""
    mock_ui_state.selected_index = 0  # Selected "Stack Overflow"
    mock_ui_state.current_list_index = 2  # In "Dev Resources" list

    bookmark_handlers.handle_bookmark_list_move_up()

    # Should not move
    dev_list = mock_manager.bookmarks[2]
    assert dev_list.items[0].title == "Stack Overflow"
    mock_manager.mark_dirty.assert_not_called()


def test_handle_bookmark_list_move_down_success(bookmark_handlers, mock_manager, mock_ui_state):
    """Move a bookmark down within a list."""
    mock_ui_state.selected_index = 0  # Selected "Stack Overflow"
    mock_ui_state.current_list_index = 2  # In "Dev Resources" list

    bookmark_handlers.handle_bookmark_list_move_down()

    # "Stack Overflow" should move to index 1, "MDN" to index 0
    dev_list = mock_manager.bookmarks[2]
    assert dev_list.items[0].title == "MDN"
    assert dev_list.items[1].title == "Stack Overflow"
    assert mock_ui_state.selected_index == 1
    mock_manager.mark_dirty.assert_called_once()
    mock_manager.save.assert_called_once()


def test_handle_bookmark_list_move_down_last_item(bookmark_handlers, mock_manager, mock_ui_state):
    """Cannot move down when already last in list."""
    mock_ui_state.selected_index = 1  # Selected "MDN"
    mock_ui_state.current_list_index = 2  # In "Dev Resources" list

    bookmark_handlers.handle_bookmark_list_move_down()

    # Should not move
    dev_list = mock_manager.bookmarks[2]
    assert dev_list.items[1].title == "MDN"
    mock_manager.mark_dirty.assert_not_called()
