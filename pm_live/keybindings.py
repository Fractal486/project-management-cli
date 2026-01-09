"""Key bindings for the live CLI with callback-based approach."""

from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys

from .states import AppState


def create_key_bindings(controller) -> KeyBindings:
    """Create key bindings that call methods on the controller.
    
    Args:
        controller: Object with navigation and action methods
        
    Returns:
        KeyBindings object for prompt_toolkit
    """
    kb = KeyBindings()

    def _in_text_mode() -> bool:
        ui = getattr(controller, 'ui_state', None)
        if ui is None:
            return False
        state = getattr(ui, 'state', None)
        return bool(
            state == AppState.SEARCH
            or getattr(ui, 'inline_input_mode', False)
            or getattr(ui, 'inline_task_edit_mode', False)
            or (state == AppState.PROJECT_BROWSER and getattr(ui, 'cell_editing', False))
        )

    @kb.add('up')
    def _(event):
        """Move selection up"""
        controller.on_up()

    @kb.add('down')
    def _(event):
        """Move selection down"""
        controller.on_down()

    @kb.add('tab')
    def _(event):
        """Switch tabs in project browser"""
        controller.on_tab()

    @kb.add('s-tab')
    def _(event):
        """Switch focus (Shift+Tab)"""
        controller.on_shift_tab()

    @kb.add('c')
    def _(event):
        """Collapse/expand task or section"""
        if _in_text_mode():
            controller.on_char('c')
        else:
            controller.on_collapse()

    @kb.add('enter')
    def _(event):
        """Confirm selection / Submit"""
        controller.on_enter()

    @kb.add('c-j')
    def _(event):
        """Insert newline while editing notes/description."""
        controller.on_insert_newline()

    @kb.add('escape')
    def _(event):
        """Go back or cancel"""
        controller.on_escape()

    @kb.add('left')
    def _(event):
        """Outdent task"""
        controller.on_left()

    @kb.add('right')
    def _(event):
        """Indent task"""
        controller.on_right()

    @kb.add('delete')
    def _(event):
        """Delete selected task"""
        controller.on_delete()

    @kb.add('c-up')
    def _(event):
        """Move task up"""
        controller.on_ctrl_up()

    @kb.add('c-down')
    def _(event):
        """Move task down"""
        controller.on_ctrl_down()

    @kb.add('c-left')
    def _(event):
        """Move task to previous list"""
        controller.on_ctrl_left()

    @kb.add('c-right')
    def _(event):
        """Move task to next list"""
        controller.on_ctrl_right()

    @kb.add('c-c')
    def _(event):
        """Exit application"""
        controller.on_exit()

    # 'H' (uppercase) still bound for help overlay
    @kb.add('H')
    def _(event):
        """Toggle help overlay (uppercase)"""
        controller.on_help()

    @kb.add('e')
    def _(event):
        """Edit selected item, or type 'e' when already editing.

        - When NOT in any edit mode: treat 'e' as the edit command (edit task,
          bookmark, custom field, etc.).
        - When typing in any field (inline_input_mode, inline_task_edit_mode, or
          project-browser cell edit), insert literal 'e' instead of triggering
          edit again.
        """
        if _in_text_mode():
            controller.on_char('e')
        else:
            controller.on_edit()

    @kb.add('a')
    def _(event):
        """Add a new project/task/bookmark depending on context."""
        if _in_text_mode():
            controller.on_char('a')
        else:
            controller.on_add()

    @kb.add('p')
    def _(event):
        """Toggle pin status of selected item."""
        if _in_text_mode():
            controller.on_char('p')
        else:
            controller.on_pin()

    @kb.add('t')
    def _(event):
        """Jump to today in calendar."""
        if _in_text_mode():
            controller.on_char('t')
        else:
            controller.on_today()

    @kb.add('g')
    def _(event):
        """Go to source item from pinned section."""
        if _in_text_mode():
            controller.on_char('g')
        else:
            controller.on_goto()

    @kb.add('m')
    def _(event):
        """Move task to project."""
        if _in_text_mode():
            controller.on_char('m')
        else:
            controller.on_move_to_project()

    @kb.add('/')
    def _(event):
        """Open global search."""
        if _in_text_mode():
            controller.on_char('/')
        else:
            controller.on_search()

    # Numeric shortcuts for footer actions (disabled while typing)
    for digit in "123456789":
        @kb.add(digit)
        def _handler(event, d=digit):
            if _in_text_mode():
                controller.on_char(d)
            else:
                try:
                    controller.on_action_shortcut(int(d))
                except Exception:
                    controller.on_char(d)

    # Handle text input for inline editing mode
    # Lowercase 'c', 'h' and uppercase 'C' have special handling via dedicated keybindings
    # They will trigger collapse/help when NOT in inline input mode, or add the character when in inline mode
    # Note: 'c', 'e', 'a', 'p', 't', 'g', 'm', and '/' are excluded here since they have dedicated keybindings above
    printable_chars = 'bdfhijklnoqrsuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0 .,!?-_()[]{}:;\\@#$%^&*+=~`"\' '
    for char in printable_chars:
        @kb.add(char)
        def _handler(event, c=char):
            controller.on_char(c)

    @kb.add('backspace')
    def _(event):
        """Delete last character in text input"""
        controller.on_backspace()

    @kb.add('c-v')
    def _(event):
        """Paste from clipboard"""
        controller.on_paste(event)

    @kb.add(Keys.BracketedPaste)
    def _(event):
        """Handle terminal bracketed paste sequences"""
        controller.on_paste(event)

    @kb.add('s-insert')
    def _(event):
        """Handle Shift+Insert paste fallback"""
        controller.on_paste(event)

    return kb


# Context-dependent keybindings for help overlay
KEYBINDINGS_BY_SCREEN = {
    AppState.MAIN_MENU: [
        ("↑/↓", "Navigate menu items"),
        ("Enter", "Select/Confirm action / Cycle task status (pinned)"),
        ("/", "Open search"),
        ("a", "Quick add task"),
        ("e", "Edit selected item (pinned section)"),
        ("g", "Go to source (pinned section)"),
        ("Backspace", "Clear field"),
        ("Del", "Delete pinned item"),
        ("Ctrl+↑/↓", "Reorder pinned item (pinned section)"),
        ("p", "Unpin selected item (pinned section)"),
        ("c", "Cycle project status (pinned section)"),
        ("Escape", "Cancel inline edit"),
        ("h", "Toggle keyboard shortcuts help"),
        ("Ctrl+C", "Exit application"),
    ],
    AppState.PROJECT_BROWSER: [
        ("↑/↓", "Navigate projects / Adjust date in cell edit mode"),
        ("→", "Enter cell selection mode / Move to next column"),
        ("←", "Move to previous column / Exit cell selection mode"),
        ("Ctrl+↑/↓", "Reorder project (manual order)"),
        ("Tab", "Switch between tabs (All/Active/Archived)"),
        ("a", "Add project"),
        ("Enter", "Open project / Edit cell (status/name/fields) / Save / Cycle column sort when header selected"),
        ("e", "Edit project / Edit field definition (header)"),
        ("c", "Cycle project status"),
        ("p", "Pin/Unpin project"),
        ("Escape", "Cancel edit / Exit cell selection / Back to main menu"),
        ("Text input", "Edit cell value (text/number fields)"),
        ("Backspace", "Clear selected field / Delete char in edit mode"),
        ("h", "Toggle keyboard shortcuts help"),
        ("Ctrl+C", "Exit application"),
    ],
    AppState.PROJECT_DETAILS: [
        ("↑/↓", "Navigate tasks/actions"),
        ("→/←", "Indent/Outdent task"),
        ("Ctrl+↑/↓", "Move task up/down"),
        ("m", "Move task to another project or Tasks"),
        ("Ctrl+J", "New line (notes/description)"),
        ("c", "Collapse/Expand task"),
        ("e", "Edit task inline"),
        ("Del", "Delete selected task"),
        ("p", "Pin/Unpin task or section"),
        ("Enter", "Select/Confirm action"),
        ("Escape", "Back to project browser"),
        ("h", "Toggle keyboard shortcuts help"),
        ("Ctrl+C", "Exit application"),
    ],
    AppState.TASK_LIST: [
        ("↑/↓", "Navigate tasks/actions"),
        ("Tab", "Switch between task lists"),
        ("→/←", "Indent/Outdent task"),
        ("Ctrl+↑/↓", "Move task up/down"),
        ("Ctrl+←/→", "Move task to previous/next list"),
        ("m", "Move task to a project"),
        ("Ctrl+J", "New line (notes/description)"),
        ("a", "Add task inline"),
        ("c", "Collapse/Expand task"),
        ("e", "Edit task inline"),
        ("Del", "Delete selected task"),
        ("p", "Pin/Unpin task"),
        ("Enter", "Select/Confirm action"),
        ("Escape", "Back to main menu"),
        ("h", "Toggle keyboard shortcuts help"),
        ("Ctrl+C", "Exit application"),
    ],
    AppState.BOOKMARKS: [
        ("↑/↓", "Navigate bookmarks/lists"),
        ("Ctrl+↑/↓", "Move bookmark/list up/down"),
        ("Enter", "Open bookmark/list"),
        ("a", "Add bookmark"),
        ("e", "Edit bookmark/Rename list"),
        ("Del", "Delete selected item"),
        ("p", "Pin/Unpin bookmark or list"),
        ("Escape", "Back to main menu"),
        ("h", "Toggle keyboard shortcuts help"),
        ("Ctrl+C", "Exit application"),
    ],
    AppState.BOOKMARK_LIST: [
        ("↑/↓", "Navigate bookmarks"),
        ("Ctrl+↑/↓", "Move bookmark up/down"),
        ("Enter", "Open bookmark"),
        ("a", "Add bookmark to this list"),
        ("e", "Edit selected bookmark"),
        ("Del", "Delete selected bookmark"),
        ("p", "Pin/Unpin bookmark"),
        ("Escape", "Back to bookmarks"),
        ("h", "Toggle keyboard shortcuts help"),
        ("Ctrl+C", "Exit application"),
    ],
    "SETTINGS": [
        ("↑/↓", "Navigate options"),
        ("Enter", "Select/Toggle option"),
        ("Escape", "Back"),
        ("Text input", "Type values"),
        ("h", "Toggle keyboard shortcuts help"),
        ("Ctrl+C", "Exit application"),
    ],
    AppState.CUSTOMIZE_FIELDS: [
        ("↑/↓", "Navigate fields/actions"),
        ("Ctrl+↑/↓", "Move custom field up/down"),
        ("Enter", "Toggle visibility/Select action"),
        ("a", "Add custom field"),
        ("e", "Edit field"),
        ("Del", "Delete custom field"),
        ("Escape", "Back to project browser"),
        ("h", "Toggle keyboard shortcuts help"),
        ("Ctrl+C", "Exit application"),
    ],
    AppState.STATISTICS: [
        ("Escape", "Back to main menu"),
        ("h", "Toggle keyboard shortcuts help"),
        ("Ctrl+C", "Exit application"),
    ],
    AppState.CALENDAR: [
        ("Arrows", "Move within calendar grid or task list"),
        ("Shift+Tab", "Switch focus between calendar and tasks"),
        ("Tab", "Cycle through tabs (when in tasks section)"),
        ("Ctrl+←/→", "Change month (calendar) / Move task date (tasks)"),
        ("t", "Jump to today"),
        ("Enter", "Select month arrow / Focus tasks / Cycle task status / Back"),
        ("c", "Cycle project status (project entries)"),
        ("g", "Go to source item (tasks)"),
        ("p", "Pin/Unpin item (tasks section)"),
        ("e", "Edit task inline (task list)"),
        ("Del", "Delete task (task list)"),
        ("Escape", "Cancel inline edit / Back to main menu"),
        ("h", "Toggle keyboard shortcuts help"),
        ("Ctrl+C", "Exit application"),
    ],
    AppState.PROJECT_SELECTION_MENU: [
        ("↑/↓", "Navigate projects"),
        ("Enter", "Move task to selected project"),
        ("Escape", "Cancel and go back"),
        ("h", "Toggle keyboard shortcuts help"),
        ("Ctrl+C", "Exit application"),
    ],
    # Group all form screens together
    "FORMS": [
        ("↑/↓", "Navigate form fields / adjust date value in date edit mode"),
        ("←/→", "Change active date component (year/month/day) in date edit mode"),
        ("Ctrl+↑/↓", "Move selected section/option up or down"),
        ("Enter", "Confirm/Submit form or commit field edit"),
        ("Escape", "Cancel and go back / exit field edit"),
        ("Tab", "Cycle option color (single-select custom field options)"),
        ("Text input", "Type to fill fields"),
        ("Ctrl+J", "New line (notes/description)"),
        ("Backspace", "Delete characters or clear current field"),
        ("Ctrl+V", "Paste from clipboard"),
        ("Del", "Delete item (lists/options)"),
        ("h", "Toggle keyboard shortcuts help"),
        ("Ctrl+C", "Exit application"),
    ],
}

# Map form states to the FORMS keybindings
FORM_STATES = {
    AppState.ADD_PROJECT,
    AppState.EDIT_PROJECT,
    AppState.ADD_BOOKMARK,
    AppState.EDIT_BOOKMARK,
    AppState.EDIT_TAB,
    AppState.ADD_CUSTOM_FIELD,
    AppState.EDIT_CUSTOM_FIELD,
    AppState.CHANGE_STATUS,
    AppState.DELETE_CONFIRMATION,
}

SETTINGS_STATES = {
    AppState.SETTINGS,
    AppState.QUICK_STATS_SETTINGS,
    AppState.MAIN_MENU_TABS_SETTINGS,
    AppState.DEADLINE_SETTINGS,
    AppState.MESSAGE_DISPLAY_SETTINGS,
    AppState.STATS_NONE_SETTINGS,
    AppState.BOOKMARK_ACTION_SETTINGS,
    AppState.NOTES_DISPLAY_SETTINGS,
}


def get_keybindings_for_state(state: AppState) -> list:
    """Get keybindings for a specific state.
    
    Args:
        state: The current application state
        
    Returns:
        List of (key, description) tuples for the state
    """
    if state in SETTINGS_STATES:
        return KEYBINDINGS_BY_SCREEN["SETTINGS"]
    if state in FORM_STATES:
        return KEYBINDINGS_BY_SCREEN["FORMS"]
    return KEYBINDINGS_BY_SCREEN.get(state, [])







