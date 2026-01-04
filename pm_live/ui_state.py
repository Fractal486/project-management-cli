"""UI state management for the live CLI."""

from datetime import datetime
from typing import Set, Optional, List, Dict
from dataclasses import dataclass, field

from .states import AppState
from .quick_stats import DEFAULT_QUICK_STATS
from .main_menu_tabs import DEFAULT_MAIN_MENU_TABS


@dataclass
class UIState:
    """Mutable snapshot of the UI layer.

    Attributes
    ----------
    state:
        Current :class:`~pm_live.states.AppState` representing the active screen.
    selected_index:
        Row index selected inside the current screen (list position or menu entry).
    active_tab:
        Tab index (for example, project browser filters or task list tabs).
    current_project_id:
        Identifier of the project currently in focus, used by detail screens.
    text_input_buffer:
        Contents of the inline text field when the user is typing.
    text_input_cursor:
        Cursor position for inline text input buffers.
    form_data:
        Accumulator for multi-field forms such as project creation or editing.
    form_field_index:
        Index of the active form field when editing multi-step forms.
    history_stack:
        Optional stack reserved for future back-navigation use.
    inline_input_mode:
        ``True`` when keystrokes are captured into ``text_input_buffer``.
    collapsed_tasks:
        Set of task ids (plus section keys) that are currently collapsed in the tree view.
        Persisted between sessions via metadata on the projects file.
    task_lists:
        Labels for task list tabs. Defaults to a single \"Tasks\" list. New lists
        can be added from the Tasks screen.
    quick_add_priority:
        Optional priority shortcut used by the quick-add flow in the main menu.
    quick_add_field_index:
        Index of the active quick-add option (0=title, 1=priority, 2=deadline, 3=add).
    quick_add_deadline:
        Optional deadline in YYYY-MM-DD format for the quick-add flow.
    quick_add_deadline_component:
        Index of the active deadline component when editing (0=year, 1=month, 2=day).
    quick_add_deadline_edit_mode:
        ``True`` when the deadline field is in edit mode with arrow key navigation.
    status_message / status_is_error:
        Pair used to display transient feedback banners in the UI.
    show_help:
        ``True`` when the keyboard shortcuts help overlay is visible.
    quick_stats_selection:
        Set of quick stat keys that should be rendered on the main menu banner.
    """
    state: AppState = AppState.MAIN_MENU
    previous_state: Optional[AppState] = None
    selected_index: int = 0
    active_tab: int = 0
    current_project_id: Optional[int] = None
    # Search state
    search_query: str = ""
    search_results: List[dict] = field(default_factory=list)
    search_selected_index: int = 0
    current_list_index: Optional[int] = None  # Index of bookmark list being viewed
    delete_context: Optional[dict] = None  # Context for delete confirmation dialog
    text_input_buffer: str = ""
    text_input_cursor: int = 0
    form_data: dict = field(default_factory=dict)
    form_field_index: int = 0
    editing_list_name: Optional[str] = None  # Name of list being edited (None when creating new list)
    history_stack: list = field(default_factory=list)
    inline_input_mode: bool = False
    inline_task_edit_mode: bool = False  # True when editing an existing task inline
    inline_edit_task_id: Optional[str] = None  # Task id being edited (for project details and lists)
    inline_edit_task: Optional[object] = None  # Direct reference to the task being edited (not persisted)
    inline_edit_origin: Optional[str] = None  # "task_list" or "project"
    inline_edit_list_name: Optional[str] = None  # List name when editing in task list
    inline_edit_project_id: Optional[int] = None  # Project id when editing inside a project
    inline_edit_field_index: int = 0  # 0=name, 1=deadline, 2=priority, 3=notes
    inline_edit_deadline_component: int = 0  # 0=year, 1=month, 2=day within deadline field
    inline_edit_name: str = ""
    inline_edit_name_cursor: int = 0
    inline_edit_deadline: Optional[str] = None
    inline_edit_priority: Optional[str] = None
    inline_edit_notes: Optional[str] = None
    inline_edit_notes_cursor: int = 0
    inline_edit_original: dict = field(default_factory=dict)  # Snapshot for cancel
    pending_section_add: bool = False  # True when capturing a new section title inline
    # Collapsed sections: includes "section_completed" for the special completed section,
    # and format "list_name:section_name" for user-defined sections
    collapsed_tasks: Set[str] = field(default_factory=lambda: {"section_completed"})
    # Dynamic task lists (tabs)
    task_lists: List[str] = field(default_factory=lambda: ["Tasks"])
    # Per-list task containers (session-only). Defaults set in LiveCLI to map "Tasks" -> manager.standalone_tasks.
    list_tasks: Dict[str, List] = field(default_factory=dict)
    # Context for add-task form in TASK_LIST
    add_task_list_name: Optional[str] = None  # List name where a new task is being added
    add_task_section_index: Optional[int] = None  # Target section index within the list
    quick_add_priority: Optional[str] = None
    quick_add_field_index: int = 0
    quick_add_deadline: Optional[str] = None  # Deadline in YYYY-MM-DD format
    quick_add_deadline_component: int = 0  # 0=year, 1=month, 2=day
    quick_add_deadline_edit_mode: bool = False  # True when editing deadline
    quick_add_list: str = "Tasks"  # Task list name for quick add (defaults to "Tasks")
    # Calendar state
    calendar_year: int = field(default_factory=lambda: datetime.now().year)
    calendar_month: int = field(default_factory=lambda: datetime.now().month)
    calendar_selected_day: Optional[int] = None  # Day number (1-31) currently selected
    calendar_navigation_focus: str = "day"  # "day" | "prev" | "next" | "tasks" | "back"
    calendar_task_selected_index: int = 0
    calendar_tasks_tab: int = 0  # 0=Selected Day, 1=Overdue, 2=Upcoming
    calendar_upcoming_collapsed: Set[str] = field(default_factory=set)  # Collapsed sections: "today", "next_week", "next_month"
    quick_stats_selection: Set[str] = field(default_factory=lambda: set(DEFAULT_QUICK_STATS))
    main_menu_tabs_selection: Set[str] = field(default_factory=lambda: set(DEFAULT_MAIN_MENU_TABS))
    status_message: Optional[str] = None
    status_is_error: bool = False
    show_help: bool = False
    show_all_keybindings: bool = False  # True when showing all keybindings (vs context-dependent)

    # Custom field date editing state
    custom_field_date_edit_mode: bool = False
    custom_field_date_component: int = 0  # 0=year, 1=month, 2=day
    custom_field_date_buffer: Optional[str] = None  # YYYY-MM-DD

    # Cache for flattened tasks keyed by (scope, collapse state hash)
    _flat_tasks_cache: dict = field(default_factory=dict)

    # Cell selection mode for project browser inline editing
    cell_selection_mode: bool = False
    cell_selected_column: int = 0  # 0-indexed column within editable field cells
    cell_editing: bool = False     # True when actively editing a cell value

    # Transient expanded state for pinned items (not persisted)
    expanded_pinned_lists: Set[str] = field(default_factory=set)  # List ids
    expanded_pinned_sections: Set[str] = field(default_factory=set)  # Section ids
    expanded_pinned_list_sections: Set[str] = field(default_factory=set)  # Section ids within a pinned list
    pinned_display_items: List = field(default_factory=list)  # Flattened pinned list including expanded children
    cell_edit_buffer: str = ""     # Buffer for text/number input in cells
    cell_edit_date_buffer: Optional[str] = None  # YYYY-MM-DD for date editing
    cell_edit_date_component: int = 0  # For date field editing (0=year, 1=month, 2=day)
    # Project browser sorting
    project_sort_key: Optional[str] = None  # Column key currently used for sorting
    project_sort_order: Optional[str] = None  # 'asc', 'desc', or None (default order)
    # Project browser selection persistence
    project_browser_selected_index: int = 0
    project_browser_selected_project_id: Optional[int] = None

    # Pinned items navigation (main menu)
    in_pinned_section: bool = False  # True when navigating pinned items on home screen
    pinned_selected_index: int = 0   # Index within pinned items list
    reordered_pinned_items: List = field(default_factory=list)  # Display order: projects, tasks, bookmarks, lists, sections
