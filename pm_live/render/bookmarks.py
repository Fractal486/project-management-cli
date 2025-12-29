"""Bookmarks renderers for list view and add form."""

from .base import BaseRenderer
from pm import Bookmark, BookmarkList


class BookmarksRenderer(BaseRenderer):
    """Renderer for bookmarks list."""

    def render(self, context: dict) -> str:
        """Render bookmarks list."""
        self._reset_console_buffer()

        manager = context['manager']
        selected_index = context['selected_index']
        text_input_buffer = context.get('text_input_buffer', '')
        text_input_cursor = context.get('text_input_cursor', len(text_input_buffer))
        inline_list_edit_mode = context.get('inline_list_edit_mode', False)

        self._console.print("\n[bold]Bookmarks[/bold]\n")

        if manager.bookmarks:
            for i, item in enumerate(manager.bookmarks):
                item_selected = selected_index == i
                selector = "[white]›[/white] " if item_selected else "  "

                if isinstance(item, BookmarkList):
                    # Display list with folder icon and item count
                    item_count = len(item.items)
                    if item_selected and inline_list_edit_mode:
                        # Show inline edit mode with cursor
                        display_value = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
                        self._console.print(f"{selector}[color(243)]□[/color(243)] {display_value} [color(238)]{item_count}[/color(238)]")
                    elif item_selected:
                        self._console.print(f"{selector}[color(243)]□[/color(243)] {item.title} [color(238)]{item_count}[/color(238)]")
                    else:
                        self._console.print(f"{selector}[color(243)]□[/color(243)] [color(245)]{item.title}[/color(245)] [color(238)]{item_count}[/color(238)]")
                else:
                    # Display regular bookmark with link icon
                    # Handle copied state
                    copied = getattr(item, 'copied', False)

                    # Auto-reset: if copied but not selected, reset the flag
                    if copied and not item_selected:
                        item.copied = False
                        copied = False

                    # Determine URL color
                    if item_selected and copied:
                        url_color = "[green]"
                        url_color_end = "[/green]"
                    else:
                        url_color = "[color(236)]"
                        url_color_end = "[/color(236)]"

                    if item_selected:
                        self._console.print(f"{selector}[color(243)]○[/color(243)] {item.title}")
                        self._console.print(f"  {url_color}{item.url}{url_color_end}")
                    else:
                        self._console.print(f"{selector}[color(243)]○[/color(243)] [color(245)]{item.title}[/color(245)]")
                        self._console.print(f"  {url_color}{item.url}{url_color_end}")

                # Add spacing between bookmarks
                self._console.print()

        # Pad to push actions to bottom
        self._pad_to_bottom()

        # Add New Bookmark
        add_bookmark_index = len(manager.bookmarks)
        if selected_index == add_bookmark_index:
            self._console.print("  [white]›[/white] [green]+[/green] Add Bookmark")
        else:
            self._console.print("    [color(245)]+[/color(245)] [color(245)]Add Bookmark[/color(245)]")

        # Add New List
        add_list_index = add_bookmark_index + 1
        inline_list_create_mode = context.get('inline_list_create_mode', False)
        if inline_list_create_mode and selected_index == add_list_index:
            display_value = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
            self._console.print(f"  [white]›[/white] [green]+[/green] [color(245)]Title:[/color(245)] {display_value}")
        elif selected_index == add_list_index:
            self._console.print("  [white]›[/white] [green]+[/green] Add List")
        else:
            self._console.print("    [color(245)]+[/color(245)] [color(245)]Add List[/color(245)]")

        # Back to Main Menu
        back_index = add_list_index + 1
        if selected_index == back_index:
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Back")
        else:
            self._console.print("    [color(245)]←[/color(245)] [color(245)]Back[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class BookmarkListRenderer(BaseRenderer):
    """Renderer for viewing bookmarks inside a list."""

    def render(self, context: dict) -> str:
        """Render bookmark list view."""
        self._reset_console_buffer()

        manager = context['manager']
        selected_index = context['selected_index']
        current_list_index = context.get('current_list_index')
        inline_list_edit_mode = context.get('inline_list_edit_mode', False)
        text_input_buffer = context.get('text_input_buffer', '')
        text_input_cursor = context.get('text_input_cursor', len(text_input_buffer))

        if current_list_index is None or current_list_index >= len(manager.bookmarks):
            self._console.print("[red]List not found[/red]")
            self._render_status_message(context)
            return self._get_console_output()

        bookmark_list = manager.bookmarks[current_list_index]
        if not isinstance(bookmark_list, BookmarkList):
            self._console.print("[red]Invalid list[/red]")
            self._render_status_message(context)
            return self._get_console_output()

        # Header with list title (or inline edit mode)
        self._console.print()
        if inline_list_edit_mode:
            display_value = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
            self._console.print(f"  [bold]{display_value}[/bold]")
        else:
            self._console.print(f"  [bold]{bookmark_list.title}[/bold]")

        # Subtitle with count
        count = len(bookmark_list.items)
        if count > 0:
            self._console.print(f"  [color(243)]{count} bookmark{'s' if count != 1 else ''}[/color(243)]")
        self._console.print()

        # Left-side border helper
        left_border = "[color(238)]  │[/color(238)] "
        def header_line() -> str:
            return "[color(238)]  ┌[/color(238)]"
        def footer_line() -> str:
            return "[color(238)]  └[/color(238)]"
        def left_line(content: str = "") -> str:
            return f"{left_border}{content}"

        if bookmark_list.items:
            self._console.print(header_line())
            
            for i, bookmark in enumerate(bookmark_list.items):
                bookmark_selected = selected_index == i

                # Handle copied state
                copied = getattr(bookmark, 'copied', False)
                if copied and not bookmark_selected:
                    bookmark.copied = False
                    copied = False

                # Selector and styling
                if bookmark_selected:
                    selector = "[white]›[/white] "
                    # URL turns green when copied
                    if copied:
                        url_style = "[green]"
                        url_style_end = "[/green]"
                    else:
                        url_style = "[color(236)]"
                        url_style_end = "[/color(236)]"
                    self._console.print(left_line(f"{selector}[color(243)]○[/color(243)] {bookmark.title}"))
                    self._console.print(left_line(f"  {url_style}{bookmark.url}{url_style_end}"))
                else:
                    self._console.print(left_line(f"  [color(243)]○[/color(243)] [color(245)]{bookmark.title}[/color(245)]"))
                    self._console.print(left_line(f"  [color(236)]{bookmark.url}[/color(236)]"))

                # Spacing between items (except last)
                if i < len(bookmark_list.items) - 1:
                    self._console.print(left_line())
            
            self._console.print(footer_line())
        else:
            self._console.print("  [color(243)]No bookmarks yet[/color(243)]")

        # Pad to push actions to bottom (reserve more space for bookmark list screens)
        # Get current output and count lines
        output = self._get_console_output()
        current_lines = len(output.split('\n')) - 1

        # Reserve space for: 4 action lines + 2 status message lines + 1 extra = 7 lines
        reserved_lines = 7
        target_position = self._console.height - reserved_lines
        lines_to_add = max(0, target_position - current_lines)
        for _ in range(lines_to_add):
            self._console.print()

        # Actions
        add_index = len(bookmark_list.items)
        edit_index = add_index + 1
        delete_index = edit_index + 1
        back_index = delete_index + 1

        # Add Bookmark
        if selected_index == add_index:
            self._console.print("  [white]›[/white] [green]+[/green] New")
        else:
            self._console.print("    [color(245)]+ New[/color(245)]")

        # Edit List Title (inline mode or trigger)
        if inline_list_edit_mode and selected_index == edit_index:
            self._console.print("  [white]›[/white] [green]✓[/green] Save")
        elif selected_index == edit_index:
            self._console.print("  [white]›[/white] [cyan]✎[/cyan] Rename")
        else:
            self._console.print("    [color(245)]✎ Rename[/color(245)]")

        # Delete List
        if selected_index == delete_index:
            self._console.print("  [white]›[/white] [red]×[/red] Delete List")
        else:
            self._console.print("    [color(245)]× Delete List[/color(245)]")

        # Back
        if selected_index == back_index:
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Back")
        else:
            self._console.print("    [color(245)]← Back[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class EditBookmarkRenderer(BaseRenderer):
    """Renderer for add/edit bookmark form."""

    def render(self, context: dict) -> str:
        """Render add/edit bookmark form."""
        from ..states import AppState

        self._reset_console_buffer()

        form_field_index = context['form_field_index']
        form_data = context['form_data']
        inline_input_mode = context.get('inline_input_mode', False)
        text_input_buffer = context.get('text_input_buffer', '')
        text_input_cursor = context.get('text_input_cursor', len(text_input_buffer))
        state = context.get('state')

        # Determine if adding or editing based on state
        is_adding = (state == AppState.ADD_BOOKMARK)

        # HEADER SECTION
        self._console.print()
        if is_adding:
            self._console.print("  [bold]New Bookmark[/bold]")
        else:
            bookmark_title = form_data.get('title', '')
            if bookmark_title:
                title_display = f"[bold]{bookmark_title}[/bold]"
            else:
                title_display = "-"
            self._console.print(f"  [color(243)]Edit Bookmark:[/color(243)] {title_display}")
        self._console.print()

        # CONTENT SECTION
        # Left-side border helper
        left_border = "[color(238)]  │[/color(238)] "
        def header_line() -> str:
            return "[color(238)]  ┌[/color(238)]"
        def footer_line() -> str:
            return "[color(238)]  └[/color(238)]"
        def left_line(content: str = "") -> str:
            return f"{left_border}{content}"

        self._console.print(header_line())

        fields = ["title", "url"]
        field_labels = {"title": "Title", "url": "URL"}

        for i, field in enumerate(fields):
            is_selected = i == form_field_index
            selector = "[white]›[/white] " if is_selected else "  "
            value = form_data.get(field, "")

            if inline_input_mode and is_selected:
                display_value = BaseRenderer.build_text_input_display(text_input_buffer, text_input_cursor)
            else:
                display_value = value if value else "[color(238)]-[/color(238)]"

            if is_selected:
                self._console.print(left_line(f"{selector}[color(245)]{field_labels[field]}[/color(245)]  {display_value}"))
            else:
                self._console.print(left_line(f"{selector}[color(243)]{field_labels[field]}[/color(243)]  [color(243)]{display_value}[/color(243)]"))

        self._console.print(footer_line())

        # ACTION SECTION (pushed to bottom)
        self._pad_to_bottom()

        # Save/Create action
        save_index = len(fields)
        action_label = "Create" if is_adding else "Save"
        if form_field_index == save_index:
            self._console.print(f"  [white]›[/white] [green]✓[/green] {action_label}")
        else:
            self._console.print(f"    [color(245)]✓ {action_label}[/color(245)]")
        
        # Cancel action
        cancel_index = save_index + 1
        if form_field_index == cancel_index:
            self._console.print("  [white]›[/white] [yellow]←[/yellow] Cancel")
        else:
            self._console.print("    [color(245)]← Cancel[/color(245)]")

        self._render_status_message(context)
        return self._get_console_output()


class AddBookmarkRenderer(EditBookmarkRenderer):
    """Backward-compatible alias for the add bookmark form."""

    # Bookmark creation now reuses :class:`EditBookmarkRenderer` for layout, but
    # tests and external callers may still import ``AddBookmarkRenderer``.
    pass
