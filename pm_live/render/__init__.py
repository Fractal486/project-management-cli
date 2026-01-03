"""Rendering system for the live CLI."""

from .base import BaseRenderer, rich_to_formatted_text
from .main_menu import MainMenuRenderer
from .project_browser import ProjectBrowserRenderer
from .project_details import ProjectDetailsRenderer
from .task_list import TaskListRenderer
from .statistics import StatisticsRenderer
from .calendar import CalendarRenderer
from .settings import SettingsRenderer, QuickStatsSettingsRenderer, MainMenuTabsRenderer, DeadlineSettingsRenderer, ProjectBrowserDefaultTabRenderer, StatsNoneSettingsRenderer, MessageDisplaySettingsRenderer, NotesDisplaySettingsRenderer, BookmarkActionSettingsRenderer, CustomFieldsRenderer
from .forms import EditProjectRenderer, ChangeStatusRenderer, DeleteConfirmationRenderer, EditListRenderer, AddCustomFieldRenderer, EditCustomFieldRenderer, AddProjectRenderer
from .bookmarks import BookmarksRenderer, AddBookmarkRenderer, EditBookmarkRenderer, BookmarkListRenderer
from .help import HelpRenderer
from .search import SearchRenderer

__all__ = [
    'BaseRenderer', 'rich_to_formatted_text',
    'MainMenuRenderer', 'ProjectBrowserRenderer', 'ProjectDetailsRenderer',
    'TaskListRenderer', 'StatisticsRenderer', 'CalendarRenderer', 'SettingsRenderer', 'QuickStatsSettingsRenderer', 'MainMenuTabsRenderer', 'DeadlineSettingsRenderer', 'ProjectBrowserDefaultTabRenderer', 'StatsNoneSettingsRenderer', 'MessageDisplaySettingsRenderer', 'NotesDisplaySettingsRenderer', 'BookmarkActionSettingsRenderer', 'CustomFieldsRenderer',
    'EditProjectRenderer', 'ChangeStatusRenderer', 'DeleteConfirmationRenderer', 'EditListRenderer', 'AddCustomFieldRenderer', 'EditCustomFieldRenderer', 'AddProjectRenderer',
    'BookmarksRenderer', 'AddBookmarkRenderer', 'EditBookmarkRenderer', 'BookmarkListRenderer',
    'HelpRenderer', 'SearchRenderer'
]
