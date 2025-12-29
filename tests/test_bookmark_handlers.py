"""Tests for bookmark handler operations (pm_live/handlers/bookmark_handlers.py)."""

import pytest
from unittest.mock import Mock, MagicMock, patch

from pm import Bookmark, BookmarkList
from pm_live.handlers.bookmark_handlers import BookmarkHandlers
from pm_live.interfaces import HandlerContext
from pm_live.ui_state import UIState
from pm_live.states import AppState


# ==================== Fixtures ====================


@pytest.fixture
def mock_manager():
    """Create a mock DataManagerProtocol with bookmarks."""
    manager = Mock()
    manager.bookmarks = []
    manager.mark_dirty = Mock()
    manager.save = Mock(return_value=True)
    return manager


@pytest.fixture
def mock_ui_state():
    """Create a mock UIState."""
    ui_state = UIState()
    ui_state.state = AppState.BOOKMARKS
    ui_state.selected_index = 0
    ui_state.form_field_index = 0
    ui_state.form_data = {}
    ui_state.inline_input_mode = False
    ui_state.text_input_buffer = ""
    ui_state.current_list_index = None
    ui_state.delete_context = None
    ui_state.status_message = None
    ui_state.status_is_error = False
    return ui_state


@pytest.fixture
def mock_context(mock_manager, mock_ui_state):
    """Create a mock HandlerContext."""
    context = Mock(spec=HandlerContext)
    context.manager = mock_manager
    context.ui_state = mock_ui_state
    context.exit_application = Mock()
    context.show_status = Mock()
    return context


@pytest.fixture
def bookmark_handlers(mock_context):
    """Create a BookmarkHandlers instance."""
    return BookmarkHandlers(mock_context)


@pytest.fixture
def sample_bookmarks():
    """Create sample bookmarks."""
    return [
        Bookmark(title="GitHub", url="https://github.com"),
        Bookmark(title="Stack Overflow", url="https://stackoverflow.com"),
        BookmarkList(title="Dev Resources", items=[
            Bookmark(title="MDN", url="https://developer.mozilla.org"),
            Bookmark(title="W3Schools", url="https://www.w3schools.com"),
        ]),
    ]


# ==================== Bookmark Navigation Tests ====================


def test_handle_bookmarks_enter_navigate_to_list(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Entering on a bookmark list navigates to BOOKMARK_LIST state."""
    mock_manager.bookmarks = sample_bookmarks
    mock_ui_state.selected_index = 2  # Select the BookmarkList

    bookmark_handlers.handle_bookmarks_enter()

    assert mock_ui_state.state == AppState.BOOKMARK_LIST
    assert mock_ui_state.current_list_index == 2
    assert mock_ui_state.selected_index == 0


def test_handle_bookmarks_enter_add_bookmark(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Entering on 'Add Bookmark' transitions to ADD_BOOKMARK state."""
    mock_manager.bookmarks = sample_bookmarks
    mock_ui_state.selected_index = len(sample_bookmarks)  # Add bookmark option

    bookmark_handlers.handle_bookmarks_enter()

    assert mock_ui_state.state == AppState.ADD_BOOKMARK
    assert mock_ui_state.form_field_index == 0
    assert mock_ui_state.form_data == {}


def test_handle_bookmarks_enter_add_list(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Entering on 'Add List' starts inline list-create mode (no screen transition)."""
    mock_manager.bookmarks = sample_bookmarks
    mock_ui_state.selected_index = len(sample_bookmarks) + 1  # Add list option

    bookmark_handlers.handle_bookmarks_enter()

    assert mock_ui_state.state == AppState.BOOKMARKS
    assert mock_ui_state.inline_list_create_mode is True
    assert mock_ui_state.inline_input_mode is True
    assert mock_ui_state.text_input_buffer == ""


def test_handle_bookmarks_enter_back_to_main(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Entering on 'Back' returns to MAIN_MENU state."""
    mock_manager.bookmarks = sample_bookmarks
    mock_ui_state.selected_index = len(sample_bookmarks) + 2  # Back option

    bookmark_handlers.handle_bookmarks_enter()

    assert mock_ui_state.state == AppState.MAIN_MENU
    assert mock_ui_state.selected_index == 0


def test_handle_bookmark_list_enter_back_to_bookmarks(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Entering on 'Back' from bookmark list returns to BOOKMARKS state."""
    mock_manager.bookmarks = sample_bookmarks
    mock_ui_state.state = AppState.BOOKMARK_LIST
    mock_ui_state.current_list_index = 2
    bookmark_list = sample_bookmarks[2]
    # In BOOKMARK_LIST: items, then "Add Bookmark" (item_count), "Rename" (item_count+1), "Delete List" (item_count+2), "Back" (item_count+3)
    mock_ui_state.selected_index = len(bookmark_list.items) + 3  # Back option

    bookmark_handlers.handle_bookmark_list_enter()

    assert mock_ui_state.state == AppState.BOOKMARKS
    assert mock_ui_state.current_list_index is None


# ==================== Bookmark Creation Tests ====================


def test_handle_add_bookmark_enter_edit_field(bookmark_handlers, mock_ui_state):
    """Entering on a field enables input mode."""
    mock_ui_state.state = AppState.ADD_BOOKMARK
    mock_ui_state.form_field_index = 0  # Title field
    mock_ui_state.inline_input_mode = False

    bookmark_handlers.handle_add_bookmark_enter()

    assert mock_ui_state.inline_input_mode is True
    assert mock_ui_state.text_input_buffer == ""


def test_handle_add_bookmark_enter_save_field(bookmark_handlers, mock_ui_state):
    """Entering while in input mode saves the field value."""
    mock_ui_state.state = AppState.ADD_BOOKMARK
    mock_ui_state.form_field_index = 0  # Title field
    mock_ui_state.inline_input_mode = True
    mock_ui_state.text_input_buffer = "My Bookmark"

    bookmark_handlers.handle_add_bookmark_enter()

    assert mock_ui_state.form_data["title"] == "My Bookmark"
    assert mock_ui_state.inline_input_mode is False
    assert mock_ui_state.text_input_buffer == ""


@patch('pm_live.handlers.bookmark_handlers.validate_bookmark_title')
@patch('pm_live.handlers.bookmark_handlers.validate_url')
def test_handle_add_bookmark_enter_submit_success(mock_validate_url, mock_validate_title,
                                                    bookmark_handlers, mock_manager, mock_ui_state):
    """Submitting add bookmark form creates a new bookmark."""
    mock_ui_state.state = AppState.ADD_BOOKMARK
    mock_ui_state.form_field_index = 2  # Submit button
    mock_ui_state.form_data = {"title": "GitHub", "url": "https://github.com"}
    mock_validate_title.return_value = (True, "GitHub")
    mock_validate_url.return_value = (True, "https://github.com")

    bookmark_handlers.handle_add_bookmark_enter()

    assert len(mock_manager.bookmarks) == 1
    assert mock_manager.bookmarks[0].title == "GitHub"
    assert mock_manager.bookmarks[0].url == "https://github.com"
    mock_manager.mark_dirty.assert_called_once()
    mock_manager.save.assert_called_once()
    assert mock_ui_state.state == AppState.BOOKMARKS
    assert "Bookmark created" in mock_ui_state.status_message


@patch('pm_live.handlers.bookmark_handlers.validate_bookmark_title')
def test_handle_add_bookmark_enter_submit_invalid_title(mock_validate_title, bookmark_handlers, mock_ui_state):
    """Submitting with invalid title shows error."""
    mock_ui_state.state = AppState.ADD_BOOKMARK
    mock_ui_state.form_field_index = 2
    mock_ui_state.form_data = {"title": "", "url": "https://github.com"}
    mock_validate_title.return_value = (False, "Bookmark title cannot be empty.")

    bookmark_handlers.handle_add_bookmark_enter()

    assert mock_ui_state.status_is_error is True
    assert "empty" in mock_ui_state.status_message


@patch('pm_live.handlers.bookmark_handlers.validate_bookmark_title')
@patch('pm_live.handlers.bookmark_handlers.validate_url')
def test_handle_add_bookmark_enter_submit_invalid_url(mock_validate_url, mock_validate_title,
                                                       bookmark_handlers, mock_ui_state):
    """Submitting with invalid URL shows error."""
    mock_ui_state.state = AppState.ADD_BOOKMARK
    mock_ui_state.form_field_index = 2
    mock_ui_state.form_data = {"title": "GitHub", "url": "invalid-url"}
    mock_validate_title.return_value = (True, "GitHub")
    mock_validate_url.return_value = (False, "Invalid URL format.")

    bookmark_handlers.handle_add_bookmark_enter()

    assert mock_ui_state.status_is_error is True
    assert "Invalid URL" in mock_ui_state.status_message


def test_handle_add_bookmark_enter_cancel(bookmark_handlers, mock_ui_state):
    """Canceling add bookmark returns to BOOKMARKS state."""
    mock_ui_state.state = AppState.ADD_BOOKMARK
    mock_ui_state.form_field_index = 3  # Cancel button
    mock_ui_state.form_data = {"title": "Test"}

    bookmark_handlers.handle_add_bookmark_enter()

    assert mock_ui_state.state == AppState.BOOKMARKS
    assert mock_ui_state.form_data == {}


# ==================== Bookmark Editing Tests ====================


def test_handle_bookmarks_edit_opens_edit_form(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Editing a bookmark opens EDIT_BOOKMARK state."""
    mock_manager.bookmarks = sample_bookmarks
    mock_ui_state.selected_index = 0  # Select first bookmark

    bookmark_handlers.handle_bookmarks_edit()

    assert mock_ui_state.state == AppState.EDIT_BOOKMARK
    assert mock_ui_state.form_data["title"] == "GitHub"
    assert mock_ui_state.form_data["url"] == "https://github.com"
    assert mock_ui_state.form_data["bookmark_index"] == 0
    assert mock_ui_state.form_data["from_list"] is False


def test_handle_bookmarks_edit_navigates_into_list(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Editing a BookmarkList enters inline edit mode for the list title."""
    mock_manager.bookmarks = sample_bookmarks
    mock_ui_state.selected_index = 2  # Select BookmarkList

    bookmark_handlers.handle_bookmarks_edit()

    # Should enter inline edit mode
    assert mock_ui_state.state == AppState.BOOKMARKS
    assert mock_ui_state.inline_list_edit_mode == True
    assert mock_ui_state.inline_input_mode == True
    assert mock_ui_state.text_input_buffer == "Dev Resources"


@patch('pm_live.handlers.bookmark_handlers.validate_bookmark_title')
@patch('pm_live.handlers.bookmark_handlers.validate_url')
def test_handle_edit_bookmark_enter_submit_success(mock_validate_url, mock_validate_title,
                                                     bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Submitting edit bookmark form updates the bookmark."""
    mock_manager.bookmarks = sample_bookmarks
    mock_ui_state.state = AppState.EDIT_BOOKMARK
    mock_ui_state.form_field_index = 2  # Submit button
    mock_ui_state.form_data = {
        "title": "GitHub Updated",
        "url": "https://github.com/new",
        "bookmark_index": 0,
        "from_list": False
    }
    mock_validate_title.return_value = (True, "GitHub Updated")
    mock_validate_url.return_value = (True, "https://github.com/new")

    bookmark_handlers.handle_edit_bookmark_enter()

    assert mock_manager.bookmarks[0].title == "GitHub Updated"
    assert mock_manager.bookmarks[0].url == "https://github.com/new"
    mock_manager.mark_dirty.assert_called_once()
    mock_manager.save.assert_called_once()
    assert mock_ui_state.state == AppState.BOOKMARKS
    assert "updated" in mock_ui_state.status_message.lower()


def test_handle_edit_bookmark_enter_cancel(bookmark_handlers, mock_ui_state):
    """Canceling edit bookmark returns to BOOKMARKS state."""
    mock_ui_state.state = AppState.EDIT_BOOKMARK
    mock_ui_state.form_field_index = 3  # Cancel button
    mock_ui_state.form_data = {"from_list": False}

    bookmark_handlers.handle_edit_bookmark_enter()

    assert mock_ui_state.state == AppState.BOOKMARKS
    assert mock_ui_state.form_data == {}


# ==================== Bookmark Deletion Tests ====================


def test_handle_bookmarks_delete_shows_confirmation(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Deleting a bookmark shows confirmation dialog."""
    mock_manager.bookmarks = sample_bookmarks
    mock_ui_state.selected_index = 0  # Select first bookmark

    bookmark_handlers.handle_bookmarks_delete()

    assert mock_ui_state.state == AppState.DELETE_CONFIRMATION
    assert mock_ui_state.delete_context is not None
    assert mock_ui_state.delete_context["delete_type"] == "bookmark"
    assert mock_ui_state.delete_context["delete_params"]["bookmark_index"] == 0
    assert mock_ui_state.form_field_index == 1  # Default to "No"


def test_execute_confirmed_delete_bookmark_success(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Executing confirmed delete removes the bookmark."""
    mock_manager.bookmarks = sample_bookmarks.copy()
    initial_count = len(mock_manager.bookmarks)
    delete_params = {
        "bookmark_index": 0,
        "item_type": "bookmark",
        "item_title": "GitHub"
    }

    result = bookmark_handlers.execute_confirmed_delete(delete_params, "bookmark")

    assert result is True
    assert len(mock_manager.bookmarks) == initial_count - 1
    assert mock_manager.bookmarks[0].title == "Stack Overflow"
    mock_manager.mark_dirty.assert_called_once()
    mock_manager.save.assert_called_once()


def test_execute_confirmed_delete_bookmark_list_success(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Executing confirmed delete on a list removes it."""
    mock_manager.bookmarks = sample_bookmarks.copy()
    delete_params = {
        "bookmark_index": 2,
        "item_type": "list",
        "item_title": "Dev Resources"
    }

    result = bookmark_handlers.execute_confirmed_delete(delete_params, "bookmark")

    assert result is True
    assert len(mock_manager.bookmarks) == 2
    # List should be removed
    assert all(not isinstance(bm, BookmarkList) for bm in mock_manager.bookmarks)


def test_handle_bookmark_list_delete_shows_confirmation(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Deleting a bookmark from a list shows confirmation."""
    mock_manager.bookmarks = sample_bookmarks
    mock_ui_state.state = AppState.BOOKMARK_LIST
    mock_ui_state.current_list_index = 2
    mock_ui_state.selected_index = 0  # Select first bookmark in list

    bookmark_handlers.handle_bookmark_list_delete()

    assert mock_ui_state.state == AppState.DELETE_CONFIRMATION
    assert mock_ui_state.delete_context["delete_type"] == "bookmark_from_list"
    assert mock_ui_state.delete_context["delete_params"]["bookmark_index"] == 0
    assert mock_ui_state.delete_context["delete_params"]["list_index"] == 2


def test_execute_confirmed_delete_bookmark_from_list(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Executing confirmed delete removes bookmark from list."""
    mock_manager.bookmarks = sample_bookmarks.copy()
    bookmark_list = mock_manager.bookmarks[2]
    initial_count = len(bookmark_list.items)
    delete_params = {
        "bookmark_index": 0,
        "list_index": 2,
        "bookmark_title": "MDN"
    }

    result = bookmark_handlers.execute_confirmed_delete(delete_params, "bookmark_from_list")

    assert result is True
    assert len(bookmark_list.items) == initial_count - 1
    assert bookmark_list.items[0].title == "W3Schools"
    mock_manager.mark_dirty.assert_called_once()
    mock_manager.save.assert_called_once()


# ==================== Bookmark List Management Tests ====================


def test_inline_rename_list_enter_edit_mode(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Pressing enter on 'Rename' action enters inline edit mode."""
    mock_manager.bookmarks = sample_bookmarks
    mock_ui_state.state = AppState.BOOKMARK_LIST
    mock_ui_state.current_list_index = 2  # "Dev Resources" list
    # The "Dev Resources" list has 2 items, so:
    # - index 0 = MDN bookmark
    # - index 1 = W3Schools bookmark
    # - index 2 = Add Bookmark
    # - index 3 = Rename
    # - index 4 = Delete List
    # - index 5 = Back
    mock_ui_state.selected_index = 3  # Rename action

    bookmark_handlers.handle_bookmark_list_enter()

    assert getattr(mock_ui_state, 'inline_list_edit_mode', False) is True
    assert mock_ui_state.inline_input_mode is True
    assert mock_ui_state.text_input_buffer == "Dev Resources"


def test_inline_rename_list_save(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Saving renamed list updates the title and exits edit mode."""
    mock_manager.bookmarks = sample_bookmarks
    mock_ui_state.state = AppState.BOOKMARK_LIST
    mock_ui_state.current_list_index = 2
    mock_ui_state.selected_index = 3  # Rename action
    setattr(mock_ui_state, 'inline_list_edit_mode', True)
    mock_ui_state.inline_input_mode = True
    mock_ui_state.text_input_buffer = "Updated Resources"

    bookmark_handlers.handle_bookmark_list_enter()

    assert mock_manager.bookmarks[2].title == "Updated Resources"
    assert getattr(mock_ui_state, 'inline_list_edit_mode', True) is False
    assert mock_ui_state.inline_input_mode is False
    assert mock_ui_state.text_input_buffer == ""
    mock_manager.mark_dirty.assert_called_once()
    mock_manager.save.assert_called_once()


def test_inline_rename_list_empty_title_error(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Saving empty title shows error and stays in edit mode."""
    mock_manager.bookmarks = sample_bookmarks
    mock_ui_state.state = AppState.BOOKMARK_LIST
    mock_ui_state.current_list_index = 2
    mock_ui_state.selected_index = 3  # Rename action
    setattr(mock_ui_state, 'inline_list_edit_mode', True)
    mock_ui_state.inline_input_mode = True
    mock_ui_state.text_input_buffer = "   "

    bookmark_handlers.handle_bookmark_list_enter()

    assert mock_ui_state.status_is_error is True
    assert "title cannot be empty" in mock_ui_state.status_message.lower()
    # Title should remain unchanged
    assert mock_manager.bookmarks[2].title == "Dev Resources"


def test_delete_list_from_bookmark_list_view_shows_confirmation(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Pressing enter on 'Delete List' action shows confirmation dialog."""
    mock_manager.bookmarks = sample_bookmarks
    mock_ui_state.state = AppState.BOOKMARK_LIST
    mock_ui_state.current_list_index = 2
    mock_ui_state.selected_index = 4  # Delete List action

    bookmark_handlers.handle_bookmark_list_enter()

    # Should transition to delete confirmation
    assert mock_ui_state.state == AppState.DELETE_CONFIRMATION
    assert mock_ui_state.delete_context is not None
    assert mock_ui_state.delete_context['delete_type'] == 'bookmark_list_from_within'
    assert mock_ui_state.delete_context['previous_state'] == AppState.BOOKMARK_LIST  # Stay in list view if cancelled
    assert mock_ui_state.delete_context['previous_selected_index'] == 4
    assert mock_ui_state.delete_context['delete_params']['list_index'] == 2
    assert mock_ui_state.delete_context['delete_params']['list_title'] == "Dev Resources"
    assert mock_ui_state.form_field_index == 1  # Default to "No"


def test_execute_confirmed_delete_list_from_within(bookmark_handlers, mock_manager, mock_ui_state, sample_bookmarks):
    """Confirming delete removes the list."""
    mock_manager.bookmarks = sample_bookmarks
    initial_count = len(mock_manager.bookmarks)
    mock_ui_state.state = AppState.DELETE_CONFIRMATION
    mock_ui_state.current_list_index = 2

    delete_params = {
        'list_index': 2,
        'list_title': 'Dev Resources'
    }

    result = bookmark_handlers.execute_confirmed_delete(delete_params, 'bookmark_list_from_within')

    assert result is True
    assert len(mock_manager.bookmarks) == initial_count - 1
    assert mock_ui_state.current_list_index is None
    # State navigation is handled by the delete confirmation dialog, not by execute_confirmed_delete
    mock_manager.mark_dirty.assert_called_once()
    mock_manager.save.assert_called_once()


# ==================== Edge Cases ====================


def test_handle_bookmark_list_enter_invalid_list_index(bookmark_handlers, mock_manager, mock_ui_state):
    """Handling enter with invalid list index does nothing."""
    mock_manager.bookmarks = []
    mock_ui_state.state = AppState.BOOKMARK_LIST
    mock_ui_state.current_list_index = 10  # Invalid index

    # Should not crash
    bookmark_handlers.handle_bookmark_list_enter()


def test_handle_bookmarks_delete_out_of_range(bookmark_handlers, mock_manager, mock_ui_state):
    """Deleting with selection out of range does nothing."""
    mock_manager.bookmarks = []
    mock_ui_state.selected_index = 10  # Out of range

    # Should not crash or show confirmation
    bookmark_handlers.handle_bookmarks_delete()
    assert mock_ui_state.state == AppState.BOOKMARKS



