"""Bookmark operation handlers for the live CLI."""

import logging

from ..interfaces import HandlerContext
from ..states import AppState
from ..utils import validate_bookmark_title, validate_url
from pm import Bookmark, BookmarkList

logger = logging.getLogger(__name__)


class BookmarkHandlers:
    """Handles bookmark-related operations."""

    def __init__(self, context: HandlerContext):
        """Initialize with shared handler context."""
        self._context = context
        self.manager = context.manager
        self.ui_state = context.ui_state

    def _set_status(self, message, is_error=False):
        """Set status message."""
        self.ui_state.status_message = message
        self.ui_state.status_is_error = is_error

    def _copy_to_clipboard(self, url: str):
        """Copy a URL to the system clipboard using platform-appropriate tools."""
        import platform
        import subprocess

        system = platform.system()
        if system == "Windows":
            subprocess.run(["clip"], input=url.encode("utf-16le"), check=True)
        elif system == "Darwin":
            subprocess.run(["pbcopy"], input=url.encode(), check=True)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"], input=url.encode(), check=True)

    def handle_bookmarks_enter(self):
        """Handle enter in bookmarks list."""
        from pm import BookmarkList

        selected_idx = self.ui_state.selected_index

        # Check if we're in inline edit mode for a list
        if getattr(self.ui_state, 'inline_list_edit_mode', False):
            # Save the edited list title
            new_title = self.ui_state.text_input_buffer.strip()
            if new_title:
                bookmark_list = self.manager.bookmarks[selected_idx]
                if isinstance(bookmark_list, BookmarkList):
                    old_title = bookmark_list.title
                    
                    # Update pinned status if needed
                    was_pinned = self.manager.is_pinned(
                        "bookmark_list",
                        {"id": getattr(bookmark_list, "id", None), "title": old_title},
                    )
                    
                    bookmark_list.title = new_title
                    
                    if was_pinned:
                        self.manager.update_pinned_bookmark_list(old_title, new_title)
                    
                    self.manager.mark_dirty()
                    self.manager.save()
                    self.ui_state.inline_list_edit_mode = False
                    self.ui_state.inline_input_mode = False
                    self.ui_state.text_input_buffer = ""
                    self.ui_state.text_input_cursor = 0
                    self._set_status(f"Renamed list to '{new_title}'", False)
                    logger.info("Renamed list to: %s", new_title)
                else:
                    self._set_status("Error: Not a list", True)
            else:
                self._set_status("List title cannot be empty", True)
            return

        bookmark_count = len(self.manager.bookmarks)

        if selected_idx < bookmark_count:
            # Selected a bookmark or list
            item = self.manager.bookmarks[selected_idx]

            if isinstance(item, BookmarkList):
                # Navigate into the list
                self._set_status(None)
                self.ui_state.state = AppState.BOOKMARK_LIST
                self.ui_state.current_list_index = selected_idx
                self.ui_state.selected_index = 0
                logger.info("Opening bookmark list: %s", item.title)
            else:
                # Handle bookmark action (copy or open)
                from ..config import get_config
                config = get_config()
                
                if config.bookmark_action_mode == "open":
                    # Open in browser
                    try:
                        import webbrowser
                        webbrowser.open(item.url)
                        self._set_status(f"Opening: {item.title}", False)
                        logger.info("Opened bookmark in browser: %s", item.url)
                    except Exception as e:
                        self._set_status("Failed to open in browser", True)
                        logger.error("Failed to open bookmark in browser: %s", e)
                else:
                    # Copy URL to clipboard (default)
                    try:
                        self._copy_to_clipboard(item.url)
                        item.copied = True
                        self._set_status(f"Copied to clipboard: {item.title}", False)
                        logger.info("Copied bookmark URL to clipboard: %s", item.url)
                    except Exception as e:
                        self._set_status("Failed to copy to clipboard", True)
                        logger.error("Failed to copy bookmark to clipboard: %s", e)
        elif selected_idx == bookmark_count:
            # Add new bookmark
            self._set_status(None)
            self.ui_state.state = AppState.ADD_BOOKMARK
            self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            self.ui_state.form_data = {}
        elif selected_idx == bookmark_count + 1:
            # Add new list - enter inline create mode
            if getattr(self.ui_state, 'inline_list_create_mode', False):
                # Save the list
                title = self.ui_state.text_input_buffer.strip()
                if title:
                    bookmark_list = BookmarkList(title=title, items=[])
                    self.manager.bookmarks.append(bookmark_list)
                    self.manager.mark_dirty()
                    self.manager.save()

                    # Navigate into the newly created list
                    new_list_index = len(self.manager.bookmarks) - 1
                    self.ui_state.state = AppState.BOOKMARK_LIST
                    self.ui_state.current_list_index = new_list_index
                    self.ui_state.selected_index = 0
                    self.ui_state.inline_list_create_mode = False
                    self.ui_state.inline_input_mode = False
                    self.ui_state.text_input_buffer = ""
                    self.ui_state.text_input_cursor = 0
                    self._set_status(f"Created list '{title}'", False)
                    logger.info("Created list and navigated into it: %s", title)
                else:
                    self._set_status("List title cannot be empty", True)
            else:
                # Enter inline create mode
                self.ui_state.inline_list_create_mode = True
                self.ui_state.inline_input_mode = True
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
                self._set_status(None)
        else:
            # Back to main menu
            self._set_status(None)
            self.ui_state.state = AppState.MAIN_MENU
            self.ui_state.selected_index = 0
            logger.info("Returning to main menu from bookmarks")

    def handle_bookmark_list_enter(self):
        """Handle enter in bookmark list view."""
        selected_idx = self.ui_state.selected_index
        current_list_index = self.ui_state.current_list_index

        if current_list_index is None or current_list_index >= len(self.manager.bookmarks):
            logger.error("Invalid list index")
            return

        bookmark_list = self.manager.bookmarks[current_list_index]
        if not isinstance(bookmark_list, BookmarkList):
            logger.error("Invalid list type")
            return

        item_count = len(bookmark_list.items)
        inline_list_edit_mode = getattr(self.ui_state, 'inline_list_edit_mode', False)

        if selected_idx < item_count:
            # Handle bookmark action (copy or open)
            bookmark = bookmark_list.items[selected_idx]
            from ..config import get_config
            config = get_config()

            if config.bookmark_action_mode == "open":
                # Open in browser
                try:
                    import webbrowser
                    webbrowser.open(bookmark.url)
                    self._set_status(f"Opening: {bookmark.title}", False)
                    logger.info("Opened bookmark in browser: %s", bookmark.url)
                except Exception as e:
                    self._set_status("Failed to open in browser", True)
                    logger.error("Failed to open bookmark in browser: %s", e)
            else:
                # Copy URL to clipboard (default)
                try:
                    self._copy_to_clipboard(bookmark.url)
                    bookmark.copied = True
                    self._set_status(f"Copied to clipboard: {bookmark.title}", False)
                    logger.info("Copied bookmark URL to clipboard: %s", bookmark.url)
                except Exception as e:
                    self._set_status("Failed to copy to clipboard", True)
                    logger.error("Failed to copy bookmark to clipboard: %s", e)
        elif selected_idx == item_count:
            # Add bookmark to list
            self._set_status(None)
            self.ui_state.state = AppState.ADD_BOOKMARK
            self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            self.ui_state.form_data = {}
            logger.info("Opening add bookmark form for list")
        elif selected_idx == item_count + 1:
            # Rename list (inline editing)
            if inline_list_edit_mode:
                # Save the renamed title
                new_title = self.ui_state.text_input_buffer.strip()
                if new_title:
                    old_title = bookmark_list.title
                    
                    # Update pinned status if needed
                    was_pinned = self.manager.is_pinned(
                        "bookmark_list",
                        {"id": getattr(bookmark_list, "id", None), "title": old_title},
                    )
                    
                    bookmark_list.title = new_title
                    
                    if was_pinned:
                        self.manager.update_pinned_bookmark_list(old_title, new_title)
                    
                    self.manager.mark_dirty()
                    self.manager.save()
                    self.ui_state.inline_list_edit_mode = False
                    self.ui_state.inline_input_mode = False
                    self.ui_state.text_input_buffer = ""
                    self._set_status(f"Renamed list to '{new_title}'", False)
                    logger.info("Renamed list to: %s", new_title)
                else:
                    self._set_status("List title cannot be empty", True)
            else:
                # Enter inline edit mode
                self.ui_state.inline_list_edit_mode = True
                self.ui_state.inline_input_mode = True
                self.ui_state.text_input_buffer = bookmark_list.title
                self.ui_state.text_input_cursor = len(self.ui_state.text_input_buffer)
                self._set_status(None)
                logger.info("Entering inline edit mode for list")
        elif selected_idx == item_count + 2:
            # Delete list - show confirmation dialog
            self.ui_state.delete_context = {
                'delete_type': 'bookmark_list_from_within',
                'previous_state': AppState.BOOKMARK_LIST,  # Stay in list view if cancelled
                'previous_selected_index': selected_idx,
                'delete_params': {
                    'list_index': current_list_index,
                    'list_title': bookmark_list.title,
                    'list_id': getattr(bookmark_list, "id", None),
                }
            }
            # Transition to confirmation dialog
            self.ui_state.state = AppState.DELETE_CONFIRMATION
            self.ui_state.form_field_index = 1  # Default to "No" for safety
            logger.info("Showing delete confirmation for list: %s", bookmark_list.title)
        else:
            # Back to bookmarks
            self._set_status(None)
            self.ui_state.state = AppState.BOOKMARKS
            self.ui_state.current_list_index = None
            self.ui_state.selected_index = 0
            logger.info("Returning to bookmarks from list view")

    def handle_add_bookmark_enter(self):
        """Handle enter in add bookmark form."""
        if self.ui_state.form_field_index < 2:
            # Edit field (title or url)
            field_name = ["title", "url"][self.ui_state.form_field_index]

            if self.ui_state.inline_input_mode:
                # Save the input
                self.ui_state.form_data[field_name] = self.ui_state.text_input_buffer
                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
                self._set_status(None)
                logger.debug("Saved %s field: %s", field_name, self.ui_state.form_data[field_name])
            else:
                # Enter input mode
                self._set_status(None)
                self.ui_state.inline_input_mode = True
                self.ui_state.text_input_buffer = self.ui_state.form_data.get(field_name, "")
                self.ui_state.text_input_cursor = len(self.ui_state.text_input_buffer)
                logger.debug("Editing %s field", field_name)
        elif self.ui_state.form_field_index == 2:
            # Submit form
            if "title" not in self.ui_state.form_data or "url" not in self.ui_state.form_data:
                self._set_status("Please fill in both title and URL fields.", True)
                return

            # Validate title
            is_valid, result = validate_bookmark_title(self.ui_state.form_data["title"])
            if not is_valid:
                self._set_status(result, True)
                return
            title = result

            # Validate URL
            is_valid, result = validate_url(self.ui_state.form_data["url"])
            if not is_valid:
                self._set_status(result, True)
                return
            url = result

            # Create bookmark
            bookmark = Bookmark(title=title, url=url)

            # Check if adding to a list or to main bookmarks
            if self.ui_state.current_list_index is not None:
                # Adding to a list
                bookmark_list = self.manager.bookmarks[self.ui_state.current_list_index]
                if isinstance(bookmark_list, BookmarkList):
                    bookmark_list.items.append(bookmark)
                    self.manager.mark_dirty()
                    self.manager.save()

                    # Return to list view
                    self.ui_state.form_data = {}
                    self.ui_state.state = AppState.BOOKMARK_LIST
                    self.ui_state.selected_index = 0
                    self.ui_state.form_field_index = 0
                    self._set_status("Bookmark added to list.", False)
                else:
                    logger.error("Invalid list index")
                    self._set_status("Error: Invalid list", True)
            else:
                # Adding to main bookmarks
                self.manager.bookmarks.append(bookmark)
                self.manager.mark_dirty()
                self.manager.save()

                # Return to bookmarks list
                self.ui_state.form_data = {}
                self.ui_state.state = AppState.BOOKMARKS
                self.ui_state.selected_index = 0
                self.ui_state.form_field_index = 0
                self._set_status("Bookmark created.", False)
        else:
            # Cancel
            self.ui_state.form_data = {}
            # Return to the appropriate state
            if self.ui_state.current_list_index is not None:
                self.ui_state.state = AppState.BOOKMARK_LIST
            else:
                self.ui_state.state = AppState.BOOKMARKS
            self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            self._set_status(None)
            logger.info("Cancelled add bookmark")


    def handle_bookmarks_delete(self):
        """Handle delete key in bookmarks list - show confirmation dialog."""
        selected_idx = self.ui_state.selected_index
        bookmark_count = len(self.manager.bookmarks)

        if selected_idx < bookmark_count:
            # Get the item to delete
            item = self.manager.bookmarks[selected_idx]
            item_type = "list" if isinstance(item, BookmarkList) else "bookmark"

            # Store delete context for confirmation
            self.ui_state.delete_context = {
                'delete_type': 'bookmark',
                'previous_state': AppState.BOOKMARKS,
                'previous_selected_index': self.ui_state.selected_index,
                'delete_params': {
                    'bookmark_index': selected_idx,
                    'item_type': item_type,
                    'item_title': item.title,
                    'item_id': getattr(item, "id", None),
                    'item_url': getattr(item, "url", None),
                }
            }

            # Transition to confirmation dialog
            self.ui_state.state = AppState.DELETE_CONFIRMATION
            self.ui_state.form_field_index = 1  # Default to "No" for safety
            logger.info("Showing delete confirmation for %s: %s", item_type, item.title)

    def handle_bookmark_list_delete(self):
        """Handle delete key in bookmark list view - show confirmation dialog."""
        selected_idx = self.ui_state.selected_index
        current_list_index = self.ui_state.current_list_index

        if current_list_index is None or current_list_index >= len(self.manager.bookmarks):
            logger.error("Invalid list index")
            return

        bookmark_list = self.manager.bookmarks[current_list_index]
        if not isinstance(bookmark_list, BookmarkList):
            logger.error("Invalid list type")
            return

        item_count = len(bookmark_list.items)

        if selected_idx < item_count:
            # Get the bookmark to delete
            bookmark = bookmark_list.items[selected_idx]

            # Store delete context for confirmation
            self.ui_state.delete_context = {
                'delete_type': 'bookmark_from_list',
                'previous_state': AppState.BOOKMARK_LIST,
                'previous_selected_index': self.ui_state.selected_index,
                'delete_params': {
                    'bookmark_index': selected_idx,
                    'list_index': current_list_index,
                    'bookmark_title': bookmark.title,
                    'bookmark_id': getattr(bookmark, "id", None),
                    'bookmark_url': getattr(bookmark, "url", None),
                }
            }

            # Transition to confirmation dialog
            self.ui_state.state = AppState.DELETE_CONFIRMATION
            self.ui_state.form_field_index = 1  # Default to "No" for safety
            logger.info("Showing delete confirmation for bookmark from list: %s", bookmark.title)


    def handle_bookmarks_edit(self):
        """Handle edit (e) key in bookmarks list."""
        selected_idx = self.ui_state.selected_index
        bookmark_count = len(self.manager.bookmarks)

        if selected_idx < bookmark_count:
            # Selected a bookmark or list
            item = self.manager.bookmarks[selected_idx]

            if not isinstance(item, BookmarkList):
                # Edit the bookmark
                self._set_status(None)
                self.ui_state.state = AppState.EDIT_BOOKMARK
                self.ui_state.selected_index = 0
                self.ui_state.form_field_index = 0
                self.ui_state.form_data = {
                    'title': item.title,
                    'url': item.url,
                    'bookmark_index': selected_idx,
                    'from_list': False
                }
                logger.info("Opening edit bookmark form for: %s", item.title)
            else:
                # Enter inline edit mode for list title
                self._set_status(None)
                self.ui_state.inline_list_edit_mode = True
                self.ui_state.inline_input_mode = True
                self.ui_state.text_input_buffer = item.title
                self.ui_state.text_input_cursor = len(self.ui_state.text_input_buffer)
                logger.info("Entering inline edit mode for list: %s", item.title)

    def handle_bookmark_list_edit(self):
        """Handle edit (e) key in bookmark list view."""
        selected_idx = self.ui_state.selected_index
        current_list_index = self.ui_state.current_list_index

        if current_list_index is None or current_list_index >= len(self.manager.bookmarks):
            logger.error("Invalid list index")
            return

        bookmark_list = self.manager.bookmarks[current_list_index]
        if not isinstance(bookmark_list, BookmarkList):
            logger.error("Invalid list type")
            return

        item_count = len(bookmark_list.items)

        if selected_idx < item_count:
            # Edit the bookmark
            bookmark = bookmark_list.items[selected_idx]
            self._set_status(None)
            self.ui_state.state = AppState.EDIT_BOOKMARK
            self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            self.ui_state.form_data = {
                'title': bookmark.title,
                'url': bookmark.url,
                'bookmark_index': selected_idx,
                'list_index': current_list_index,
                'from_list': True
            }
            logger.info("Opening edit bookmark form for: %s", bookmark.title)

    def handle_edit_bookmark_enter(self):
        """Handle enter in edit bookmark form."""
        if self.ui_state.form_field_index < 2:
            # Edit field (title or url)
            field_name = ["title", "url"][self.ui_state.form_field_index]

            if self.ui_state.inline_input_mode:
                # Save the input
                self.ui_state.form_data[field_name] = self.ui_state.text_input_buffer
                self.ui_state.inline_input_mode = False
                self.ui_state.text_input_buffer = ""
                self.ui_state.text_input_cursor = 0
                self._set_status(None)
                logger.debug("Saved %s field: %s", field_name, self.ui_state.form_data[field_name])
            else:
                # Enter input mode
                self._set_status(None)
                self.ui_state.inline_input_mode = True
                self.ui_state.text_input_buffer = self.ui_state.form_data.get(field_name, "")
                self.ui_state.text_input_cursor = len(self.ui_state.text_input_buffer)
                logger.debug("Editing %s field", field_name)
        elif self.ui_state.form_field_index == 2:
            # Submit form
            if "title" not in self.ui_state.form_data or "url" not in self.ui_state.form_data:
                self._set_status("Please fill in both title and URL fields.", True)
                return

            # Validate title
            is_valid, result = validate_bookmark_title(self.ui_state.form_data["title"])
            if not is_valid:
                self._set_status(result, True)
                return
            title = result

            # Validate URL
            is_valid, result = validate_url(self.ui_state.form_data["url"])
            if not is_valid:
                self._set_status(result, True)
                return
            url = result

            # Update bookmark
            bookmark_index = self.ui_state.form_data.get('bookmark_index', -1)
            from_list = self.ui_state.form_data.get('from_list', False)

            if from_list:
                # Editing a bookmark in a list
                list_index = self.ui_state.form_data.get('list_index')
                if list_index is not None and list_index < len(self.manager.bookmarks):
                    bookmark_list = self.manager.bookmarks[list_index]
                    if isinstance(bookmark_list, BookmarkList) and bookmark_index < len(bookmark_list.items):
                        item = bookmark_list.items[bookmark_index]
                        old_title = item.title
                        old_url = item.url
                        
                        # Update pinned status if needed
                        was_pinned = self.manager.is_pinned(
                            "bookmark",
                            {
                                "id": getattr(item, "id", None),
                                "title": old_title,
                                "url": old_url,
                            },
                        )
                        
                        item.title = title
                        item.url = url
                        
                        if was_pinned:
                            self.manager.update_pinned_bookmark(old_title, old_url, title, url)
                            
                        self.manager.mark_dirty()
                        self.manager.save()
                        logger.info("Updated bookmark in list: %s - %s", title, url)

                        # Return to list view
                        self.ui_state.form_data = {}
                        self.ui_state.state = AppState.BOOKMARK_LIST
                        self.ui_state.selected_index = bookmark_index
                        self.ui_state.form_field_index = 0
                        self._set_status("Bookmark updated.", False)
            else:
                # Editing a bookmark in main bookmarks
                if bookmark_index < len(self.manager.bookmarks):
                    bookmark = self.manager.bookmarks[bookmark_index]
                    if isinstance(bookmark, Bookmark):
                        old_title = bookmark.title
                        old_url = bookmark.url
                        
                        # Update pinned status if needed
                        was_pinned = self.manager.is_pinned(
                            "bookmark",
                            {
                                "id": getattr(bookmark, "id", None),
                                "title": old_title,
                                "url": old_url,
                            },
                        )
                        
                        bookmark.title = title
                        bookmark.url = url
                        
                        if was_pinned:
                            self.manager.update_pinned_bookmark(old_title, old_url, title, url)
                            
                        self.manager.mark_dirty()
                        self.manager.save()
                        logger.info("Updated bookmark: %s - %s", title, url)

                        # Return to bookmarks list
                        self.ui_state.form_data = {}
                        self.ui_state.state = AppState.BOOKMARKS
                        self.ui_state.selected_index = bookmark_index
                        self.ui_state.form_field_index = 0
                        self._set_status("Bookmark updated.", False)
        elif self.ui_state.form_field_index == 3:
            # Cancel
            from_list = self.ui_state.form_data.get('from_list', False)
            self.ui_state.form_data = {}
            if from_list:
                self.ui_state.state = AppState.BOOKMARK_LIST
            else:
                self.ui_state.state = AppState.BOOKMARKS
            self.ui_state.selected_index = 0
            self.ui_state.form_field_index = 0
            self._set_status(None)
            logger.info("Cancelled edit bookmark")

    def execute_confirmed_delete(self, delete_params: dict, delete_type: str):
        """Execute the actual bookmark deletion after confirmation."""
        if delete_type == 'bookmark':
            # Delete bookmark or list from main bookmarks
            bookmark_index = delete_params['bookmark_index']
            item_type = delete_params['item_type']
            item_title = delete_params['item_title']
            item_id = delete_params.get('item_id')
            item_url = delete_params.get('item_url')

            if bookmark_index < len(self.manager.bookmarks):
                if item_type == "bookmark":
                    self.manager.remove_pinned_item(
                        "bookmark",
                        {"id": item_id, "title": item_title, "url": item_url},
                    )
                elif item_type == "list":
                    self.manager.remove_pinned_item(
                        "bookmark_list",
                        {"id": item_id, "title": item_title},
                    )
                del self.manager.bookmarks[bookmark_index]
                self.manager.mark_dirty()
                self.manager.save()
                self._set_status(f"Deleted {item_type}.", False)
                return True

        elif delete_type == 'bookmark_from_list':
            # Delete bookmark from a list
            bookmark_index = delete_params['bookmark_index']
            list_index = delete_params['list_index']
            bookmark_title = delete_params.get('bookmark_title')
            bookmark_id = delete_params.get('bookmark_id')
            bookmark_url = delete_params.get('bookmark_url')

            if list_index < len(self.manager.bookmarks):
                bookmark_list = self.manager.bookmarks[list_index]
                if isinstance(bookmark_list, BookmarkList) and bookmark_index < len(bookmark_list.items):
                    self.manager.remove_pinned_item(
                        "bookmark",
                        {"id": bookmark_id, "title": bookmark_title, "url": bookmark_url},
                    )
                    del bookmark_list.items[bookmark_index]
                    self.manager.mark_dirty()
                    self.manager.save()
                    self._set_status("Deleted bookmark from list.", False)
                    return True

        elif delete_type == 'bookmark_list_from_within':
            # Delete list from within the list view
            list_index = delete_params['list_index']
            list_title = delete_params['list_title']
            list_id = delete_params.get('list_id')

            if list_index < len(self.manager.bookmarks):
                self.manager.remove_pinned_item(
                    "bookmark_list",
                    {"id": list_id, "title": list_title},
                )
                del self.manager.bookmarks[list_index]
                self.manager.mark_dirty()
                self.manager.save()
                self._set_status(f"Deleted list '{list_title}'.", False)
                # Clear the list index (state navigation handled by confirmation dialog)
                self.ui_state.current_list_index = None
                return True

        return False

    def handle_bookmarks_move_up(self):
        """Handle moving bookmark or list up in the main bookmarks list."""
        selected_idx = self.ui_state.selected_index
        bookmark_count = len(self.manager.bookmarks)

        if selected_idx < bookmark_count and selected_idx > 0:
            # Swap with the previous item
            self.manager.bookmarks[selected_idx], self.manager.bookmarks[selected_idx - 1] = \
                self.manager.bookmarks[selected_idx - 1], self.manager.bookmarks[selected_idx]
            self.manager.mark_dirty()
            self.manager.save()
            # Move selection up
            self.ui_state.selected_index = selected_idx - 1
            logger.info("Moved bookmark/list up at index %d", selected_idx)

    def handle_bookmarks_move_down(self):
        """Handle moving bookmark or list down in the main bookmarks list."""
        selected_idx = self.ui_state.selected_index
        bookmark_count = len(self.manager.bookmarks)

        if selected_idx < bookmark_count - 1:
            # Swap with the next item
            self.manager.bookmarks[selected_idx], self.manager.bookmarks[selected_idx + 1] = \
                self.manager.bookmarks[selected_idx + 1], self.manager.bookmarks[selected_idx]
            self.manager.mark_dirty()
            self.manager.save()
            # Move selection down
            self.ui_state.selected_index = selected_idx + 1
            logger.info("Moved bookmark/list down at index %d", selected_idx)

    def handle_bookmark_list_move_up(self):
        """Handle moving bookmark up within a bookmark list."""
        selected_idx = self.ui_state.selected_index
        current_list_index = self.ui_state.current_list_index

        if current_list_index is None or current_list_index >= len(self.manager.bookmarks):
            return

        bookmark_list = self.manager.bookmarks[current_list_index]
        if not isinstance(bookmark_list, BookmarkList):
            return

        item_count = len(bookmark_list.items)

        if selected_idx < item_count and selected_idx > 0:
            # Swap with the previous bookmark
            bookmark_list.items[selected_idx], bookmark_list.items[selected_idx - 1] = \
                bookmark_list.items[selected_idx - 1], bookmark_list.items[selected_idx]
            self.manager.mark_dirty()
            self.manager.save()
            # Move selection up
            self.ui_state.selected_index = selected_idx - 1
            logger.info("Moved bookmark up at index %d in list %d", selected_idx, current_list_index)

    def handle_bookmark_list_move_down(self):
        """Handle moving bookmark down within a bookmark list."""
        selected_idx = self.ui_state.selected_index
        current_list_index = self.ui_state.current_list_index

        if current_list_index is None or current_list_index >= len(self.manager.bookmarks):
            return

        bookmark_list = self.manager.bookmarks[current_list_index]
        if not isinstance(bookmark_list, BookmarkList):
            return

        item_count = len(bookmark_list.items)

        if selected_idx < item_count - 1:
            # Swap with the next bookmark
            bookmark_list.items[selected_idx], bookmark_list.items[selected_idx + 1] = \
                bookmark_list.items[selected_idx + 1], bookmark_list.items[selected_idx]
            self.manager.mark_dirty()
            self.manager.save()
            # Move selection down
            self.ui_state.selected_index = selected_idx + 1
            logger.info("Moved bookmark down at index %d in list %d", selected_idx, current_list_index)
