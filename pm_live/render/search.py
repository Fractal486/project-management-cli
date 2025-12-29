"""Search screen renderer."""

from rich.markup import escape as rich_escape
from .base import BaseRenderer
from pm import STATUS_META


class SearchRenderer(BaseRenderer):
    """Renderer for the global search screen."""

    def _highlight_match(self, text: str, query: str) -> str:
        """Highlight the matched portion of text (case-insensitive).
        
        Args:
            text: The text to search in
            query: The search query to highlight
            
        Returns:
            Text with matched portion highlighted using Rich markup
        """
        if not query or not text:
            return rich_escape(text)
        
        # Find the match (case-insensitive)
        text_lower = text.lower()
        query_lower = query.lower()
        
        try:
            match_start = text_lower.index(query_lower)
            match_end = match_start + len(query)
            
            # Build highlighted string
            before = rich_escape(text[:match_start])
            matched = rich_escape(text[match_start:match_end])
            after = rich_escape(text[match_end:])
            
            return f"{before}[bold cyan]{matched}[/bold cyan]{after}"
        except ValueError:
            # No match found (shouldn't happen, but handle gracefully)
            return rich_escape(text)

    def render(self, context: dict) -> str:
        """Render the search screen with query input and results."""
        self._reset_console_buffer()

        search_query = context.get('search_query', '')
        search_results = context.get('search_results', [])
        search_selected_index = context.get('search_selected_index', 0)

        # Header
        self._console.print()
        
        # Search input with inline label
        query_display = self.build_text_input_display(
            search_query,
            len(search_query)  # Cursor at end
        )
        
        # Display query with visual separator (always show cursor)
        if search_query.strip():
            # Active search - show query prominently
            self._console.print(f"  [color(245)]/[/color(245)] {query_display}")
        else:
            # Empty - show cursor with placeholder hint
            self._console.print(f"  [color(245)]/[/color(245)] {query_display}  [color(238)]type to search...[/color(238)]")
        
        self._console.print()
        self._console.print()

        # Results
        if not search_query.strip():
            self._console.print("  [color(243)]Type to search across projects, tasks, and bookmarks...[/color(243)]")
        elif not search_results:
            self._console.print("  [color(243)]No results found[/color(243)]")
        else:
            # Group results by type
            projects = [r for r in search_results if r['type'] == 'project']
            tasks = [r for r in search_results if r['type'] == 'task']
            bookmarks = [r for r in search_results if r['type'] in ('bookmark', 'bookmark_list')]

            result_index = 0

            # Render Projects
            if projects:
                self._console.print("  [color(250)]Projects[/color(250)]")
                self._console.print("  [color(238)]┌[/color(238)]")
                for i, result in enumerate(projects):
                    is_selected = result_index == search_selected_index
                    result_index += 1

                    name = result['name']
                    status = result.get('status', 'Planned')
                    status_meta = STATUS_META.get(status, {})
                    status_icon = status_meta.get("icon", "?")
                    status_color = status_meta.get("color", "white")

                    # Highlight match
                    match_field = result.get('match_field', 'name')
                    if match_field == 'name':
                        name_display = self._highlight_match(name, search_query)
                        match_indicator = ""
                    else:
                        name_display = rich_escape(name)
                        match_indicator = f"[color(238)]({match_field})[/color(238)]"

                    if is_selected:
                        self._console.print(
                            f"  [color(238)]│[/color(238)] [white]›[/white] "
                            f"[{status_color}]{status_icon}[/{status_color}] {name_display} {match_indicator}"
                        )
                    else:
                        if match_field == 'name':
                            # Keep highlighting visible when not selected
                            self._console.print(
                                f"  [color(238)]│[/color(238)]   "
                                f"[color(243)]{status_icon}[/color(243)] [color(243)]{name_display}[/color(243)]"
                            )
                        else:
                            self._console.print(
                                f"  [color(238)]│[/color(238)]   "
                                f"[color(243)]{status_icon}[/color(243)] [color(243)]{name_display}[/color(243)] {match_indicator}"
                            )

                self._console.print("  [color(238)]└[/color(238)]")
                self._console.print()

            # Render Tasks
            if tasks:
                self._console.print("  [color(250)]Tasks[/color(250)]")
                self._console.print("  [color(238)]┌[/color(238)]")
                for i, result in enumerate(tasks):
                    is_selected = result_index == search_selected_index
                    result_index += 1

                    name = result['name']
                    completed = result.get('completed')

                    # Status icon
                    if completed is True:
                        status_icon = "[green]✓[/green]" if is_selected else "[color(238)]✓[/color(238)]"
                    elif completed is False:
                        status_icon = "[red]✗[/red]" if is_selected else "[color(238)]✗[/color(238)]"
                    else:
                        status_icon = "[cyan]○[/cyan]" if is_selected else "[color(243)]○[/color(243)]"

                    # Context (project or list name)
                    if 'project_name' in result:
                        context_str = f"[color(238)]in {result['project_name']}[/color(238)]"
                    elif 'list_name' in result:
                        context_str = f"[color(238)]in {result['list_name']}[/color(238)]"
                    else:
                        context_str = ""

                    # Highlight match
                    match_field = result.get('match_field', 'name')
                    if match_field == 'name':
                        name_display = self._highlight_match(name, search_query)
                        match_indicator = ""
                    else:
                        name_display = rich_escape(name)
                        match_indicator = f"[color(238)](notes)[/color(238)]"

                    if is_selected:
                        self._console.print(
                            f"  [color(238)]│[/color(238)] [white]›[/white] "
                            f"{status_icon} {name_display} {context_str} {match_indicator}"
                        )
                    else:
                        if match_field == 'name':
                            # Keep highlighting visible
                            name_color = "color(238)" if completed is not None else "color(243)"
                            self._console.print(
                                f"  [color(238)]│[/color(238)]   "
                                f"{status_icon} [{name_color}]{name_display}[/{name_color}] {context_str}"
                            )
                        else:
                            name_color = "color(238)" if completed is not None else "color(243)"
                            self._console.print(
                                f"  [color(238)]│[/color(238)]   "
                                f"{status_icon} [{name_color}]{name_display}[/{name_color}] {context_str} {match_indicator}"
                            )

                self._console.print("  [color(238)]└[/color(238)]")
                self._console.print()

            # Render Bookmarks
            if bookmarks:
                self._console.print("  [color(250)]Bookmarks[/color(250)]")
                self._console.print("  [color(238)]┌[/color(238)]")
                for i, result in enumerate(bookmarks):
                    is_selected = result_index == search_selected_index
                    result_index += 1

                    name = result['name']
                    result_type = result['type']

                    if result_type == 'bookmark_list':
                        icon = "[color(243)]□[/color(243)]"
                        count = result.get('bookmark_count', 0)
                        # Highlight list title matches
                        name_display = self._highlight_match(name, search_query)
                        extra = f"[color(238)]({count} bookmarks)[/color(238)]"
                    else:
                        icon = "[color(243)]○[/color(243)]"
                        match_field = result.get('match_field', 'title')
                        if match_field == 'title':
                            name_display = self._highlight_match(name, search_query)
                            extra = ""
                        else:
                            # URL match
                            name_display = rich_escape(name)
                            extra = f"[color(238)](url)[/color(238)]"

                    if is_selected:
                        self._console.print(
                            f"  [color(238)]│[/color(238)] [white]›[/white] "
                            f"{icon} {name_display} {extra}"
                        )
                    else:
                        self._console.print(
                            f"  [color(238)]│[/color(238)]   "
                            f"{icon} [color(243)]{name_display}[/color(243)] {extra}"
                        )

                self._console.print("  [color(238)]└[/color(238)]")
                self._console.print()

            # Result count
            total_count = len(search_results)
            result_word = "result" if total_count == 1 else "results"
            self._console.print(f"  [color(243)]{total_count} {result_word}[/color(243)]")

        # Help text at bottom
        self._console.print()
        self._console.print()
        self._console.print("  [color(243)]Press [/color(243)][color(245)]Enter[/color(245)][color(243)] to jump to selected item  •  [/color(243)][color(245)]Esc[/color(245)][color(243)] to close[/color(243)]")

        self._render_status_message(context)
        return self._get_console_output()
