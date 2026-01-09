"""Tests for utility modules (pm_live/utils/ and quick_stats)."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
from io import StringIO

from pm import Project, Task, Bookmark, BookmarkList
from pm_live.utils.formatting import (
    get_status_icon,
    get_status_color,
    get_level_color,
    render_progress_bar,
    format_currency_value,
    format_deadline,
)
from pm_live.utils.helpers import get_stats, filter_projects_by_tab
from pm_live.quick_stats import (
    QuickStatDefinition,
    normalize_quick_stats_selection,
    format_quick_stats,
    QUICK_STATS,
)


# ==================== Fixtures ====================


@pytest.fixture
def sample_projects():
    """Create sample projects with various statuses."""
    return [
        Project(
            id=1,
            name="Project 1",
            status="Done",
            tasks=[],
        ),
        Project(
            id=2,
            name="Project 2",
            status="In Progress",
            tasks=[
                Task(name="Task 1", completed=None),
                Task(name="Task 2", completed=True),
            ],
        ),
        Project(
            id=3,
            name="Project 3",
            status="On Hold",
            tasks=[Task(name="Task 1", completed=None)],
        ),
        Project(
            id=4,
            name="Project 4",
            status="Planned",
            tasks=[],
        ),
        Project(
            id=5,
            name="Project 5",
            status="In Progress",
            tasks=[
                Task(name="Task 1", completed=True),
                Task(name="Task 2", completed=True),
            ],
        ),
    ]


@pytest.fixture
def mock_manager():
    """Create a mock data manager."""
    manager = Mock()
    manager.projects = []
    manager.standalone_tasks = []
    manager.bookmarks = []
    return manager


@pytest.fixture
def mock_console():
    """Create a mock Rich console."""
    console = Mock()
    console.file = StringIO()
    return console


# ==================== Formatting Tests ====================


def test_get_status_icon_valid_status():
    """get_status_icon returns correct icon for valid status."""
    assert get_status_icon("Done") == "✓"
    assert get_status_icon("In Progress") == "◉"
    assert get_status_icon("On Hold") == "⊙"
    assert get_status_icon("Planned") == "○"


def test_get_status_icon_invalid_status():
    """get_status_icon returns default icon for invalid status."""
    icon = get_status_icon("Invalid Status")
    assert icon == "?"


def test_get_status_color_valid_status():
    """get_status_color returns correct color for valid status."""
    assert get_status_color("Done") == "green"
    assert get_status_color("In Progress") == "cyan"
    assert get_status_color("On Hold") == "yellow"
    assert get_status_color("Planned") == "blue"


def test_get_status_color_invalid_status():
    """get_status_color returns default color for invalid status."""
    color = get_status_color("Invalid Status")
    assert color == "white"


def test_get_level_color_valid_level():
    """get_level_color returns correct color for valid level."""
    assert get_level_color("High") == "red"
    assert get_level_color("Medium") == "yellow"
    assert get_level_color("Low") == "green"


def test_get_level_color_invalid_level():
    """get_level_color returns default color for invalid level."""
    color = get_level_color("Invalid Level")
    assert color == "white"


def test_render_progress_bar_zero():
    """render_progress_bar handles zero percentage."""
    result = render_progress_bar(0, width=10)
    assert result == "▭" * 10


def test_render_progress_bar_partial():
    """render_progress_bar shows partial progress correctly."""
    result = render_progress_bar(50, width=10)
    assert "▬" in result
    assert "▭" in result
    assert len(result) == 10


def test_render_progress_bar_complete():
    """render_progress_bar shows 100% progress correctly."""
    result = render_progress_bar(100, width=10)
    assert result == "▬" * 10


def test_render_progress_bar_default_width():
    """render_progress_bar uses default width of 6."""
    result = render_progress_bar(50)
    assert len(result) == 6


def test_format_currency_value_basic():
    """format_currency_value formats simple values."""
    result = format_currency_value(1000, "$")
    assert result == "1,000 $"


def test_format_currency_value_with_decimals():
    """format_currency_value preserves decimal places."""
    result = format_currency_value("1234.56", "€")
    assert result == "1,234.56 €"


def test_format_currency_value_empty():
    """format_currency_value handles empty value."""
    result = format_currency_value("", "$")
    assert result == "0 $"


def test_format_deadline_empty():
    """format_deadline handles empty deadline."""
    result = format_deadline("")
    assert result == ""


def test_format_deadline_none():
    """format_deadline handles None deadline."""
    result = format_deadline(None)
    assert result == ""


@patch("pm_live.config.get_config")
@patch("datetime.datetime")
def test_format_deadline_relative_overdue(mock_datetime, mock_get_config):
    """format_deadline shows overdue days in relative mode."""
    mock_config = Mock()
    mock_config.deadline_display_mode = "relative"
    mock_get_config.return_value = mock_config

    # Mock today's date
    today = datetime(2025, 11, 20).date()
    mock_datetime.now.return_value = Mock(date=Mock(return_value=today))
    mock_datetime.strptime = datetime.strptime

    # Deadline 3 days ago
    result = format_deadline("2025-11-17")
    assert "overdue" in result


@patch("pm_live.config.get_config")
@patch("datetime.datetime")
def test_format_deadline_relative_today(mock_datetime, mock_get_config):
    """format_deadline shows 'today' for current date."""
    mock_config = Mock()
    mock_config.deadline_display_mode = "relative"
    mock_get_config.return_value = mock_config

    # Mock today's date
    today = datetime(2025, 11, 20).date()
    mock_datetime.now.return_value = Mock(date=Mock(return_value=today))
    mock_datetime.strptime = datetime.strptime

    result = format_deadline("2025-11-20")
    assert "today" in result


@patch("pm_live.config.get_config")
@patch("datetime.datetime")
def test_format_deadline_relative_tomorrow(mock_datetime, mock_get_config):
    """format_deadline shows 'tomorrow' for next day."""
    mock_config = Mock()
    mock_config.deadline_display_mode = "relative"
    mock_get_config.return_value = mock_config

    # Mock today's date
    today = datetime(2025, 11, 20).date()
    mock_datetime.now.return_value = Mock(date=Mock(return_value=today))
    mock_datetime.strptime = datetime.strptime

    result = format_deadline("2025-11-21")
    assert "tomorrow" in result


@patch("pm_live.config.get_config")
@patch("datetime.datetime")
def test_format_deadline_relative_days_away(mock_datetime, mock_get_config):
    """format_deadline shows days for future dates."""
    mock_config = Mock()
    mock_config.deadline_display_mode = "relative"
    mock_get_config.return_value = mock_config

    # Mock today's date
    today = datetime(2025, 11, 20).date()
    mock_datetime.now.return_value = Mock(date=Mock(return_value=today))
    mock_datetime.strptime = datetime.strptime

    result = format_deadline("2025-11-25")
    assert "d" in result  # Should show "5d"


@patch("pm_live.config.get_config")
def test_format_deadline_date_mode(mock_get_config):
    """format_deadline shows exact date in date mode."""
    mock_config = Mock()
    mock_config.deadline_display_mode = "date"
    mock_get_config.return_value = mock_config

    result = format_deadline("2025-11-25")
    assert "2025 Nov 25" in result


@patch("pm_live.config.get_config")
def test_format_deadline_invalid_format(mock_get_config):
    """format_deadline handles invalid date format."""
    mock_config = Mock()
    mock_config.deadline_display_mode = "relative"
    mock_get_config.return_value = mock_config

    result = format_deadline("invalid-date")
    assert "invalid-date" in result


# ==================== Helper Tests ====================


def test_get_stats_empty_list():
    """get_stats handles empty project list."""
    stats = get_stats([])
    assert stats["total"] == 0
    assert stats["done"] == 0
    assert stats["inProgress"] == 0
    assert stats["onHold"] == 0
    assert stats["planned"] == 0


def test_get_stats_with_projects(sample_projects):
    """get_stats computes correct statistics."""
    stats = get_stats(sample_projects)
    assert stats["total"] == 5
    assert stats["done"] == 1
    assert stats["inProgress"] == 2
    assert stats["onHold"] == 1
    assert stats["planned"] == 1


def test_get_stats_all_same_status():
    """get_stats handles projects with same status."""
    projects = [
        Project(
            id=i,
            name=f"Project {i}",
            status="Done",
            tasks=[],
        )
        for i in range(3)
    ]
    stats = get_stats(projects)
    assert stats["total"] == 3
    assert stats["done"] == 3
    assert stats["inProgress"] == 0


def test_filter_projects_by_tab_all(sample_projects):
    """filter_projects_by_tab returns all projects for tab 0."""
    filtered = filter_projects_by_tab(sample_projects, 0)
    assert len(filtered) == 5


def test_filter_projects_by_tab_uncompleted(sample_projects):
    """filter_projects_by_tab returns uncompleted projects for tab 1."""
    filtered = filter_projects_by_tab(sample_projects, 1)
    # Projects with progress < 100%
    assert len(filtered) == 4


def test_filter_projects_by_tab_completed(sample_projects):
     """filter_projects_by_tab returns completed projects for tab 2."""
     filtered = filter_projects_by_tab(sample_projects, 2)
     # Projects with status == "Done"
     assert len(filtered) == 1
     assert filtered[0].name == "Project 1"
     assert filtered[0].status == "Done"


def test_filter_projects_by_tab_empty_list():
    """filter_projects_by_tab handles empty list."""
    filtered = filter_projects_by_tab([], 0)
    assert len(filtered) == 0


# ==================== Quick Stats Tests ====================


def test_quick_stat_definition_render_singular():
    """QuickStatDefinition renders singular label for count of 1."""
    definition = QuickStatDefinition(
        key="test",
        label_plural="items",
        label_singular="item",
        compute=lambda m: 1,
    )
    manager = Mock()
    result = definition.render(manager)
    assert "1 item" in result


def test_quick_stat_definition_render_plural():
    """QuickStatDefinition renders plural label for count != 1."""
    definition = QuickStatDefinition(
        key="test",
        label_plural="items",
        label_singular="item",
        compute=lambda m: 5,
    )
    manager = Mock()
    result = definition.render(manager)
    assert "5 items" in result


def test_quick_stat_definition_render_zero():
    """QuickStatDefinition renders plural label for count of 0."""
    definition = QuickStatDefinition(
        key="test",
        label_plural="items",
        label_singular="item",
        compute=lambda m: 0,
    )
    manager = Mock()
    result = definition.render(manager)
    assert "0 items" in result


def test_normalize_quick_stats_selection_valid():
    """normalize_quick_stats_selection returns ordered valid keys."""
    selection = ["uncompleted_tasks", "uncompleted_projects", "bookmarks"]
    result = normalize_quick_stats_selection(selection)
    # Should be in QUICK_STATS_ORDER
    assert result == ["uncompleted_projects", "uncompleted_tasks", "bookmarks"]


def test_normalize_quick_stats_selection_invalid_keys():
    """normalize_quick_stats_selection filters out invalid keys."""
    selection = ["uncompleted_projects", "invalid_key", "bookmarks"]
    result = normalize_quick_stats_selection(selection)
    assert "invalid_key" not in result
    assert "uncompleted_projects" in result
    assert "bookmarks" in result


def test_normalize_quick_stats_selection_empty():
    """normalize_quick_stats_selection handles empty selection."""
    result = normalize_quick_stats_selection([])
    assert result == []


def test_normalize_quick_stats_selection_duplicates():
    """normalize_quick_stats_selection removes duplicates."""
    selection = ["uncompleted_projects", "uncompleted_projects", "bookmarks"]
    result = normalize_quick_stats_selection(selection)
    assert result.count("uncompleted_projects") == 1


def test_format_quick_stats_single_metric(mock_manager):
    """format_quick_stats formats single metric."""
    mock_manager.projects = [
        Mock(status="In Progress"),
        Mock(status="Planned"),
        Mock(status="Done"),
    ]
    selection = ["uncompleted_projects"]
    result = format_quick_stats(mock_manager, selection)
    assert len(result) == 1
    assert "uncompleted project" in result[0]


def test_format_quick_stats_multiple_metrics(mock_manager):
    """format_quick_stats formats multiple metrics."""
    mock_manager.projects = [Mock(status="In Progress")]
    mock_manager.standalone_tasks = [Mock(completed=None)]
    mock_manager.bookmarks = [Bookmark(title="Test", url="http://test.com")]

    selection = ["uncompleted_projects", "uncompleted_tasks", "bookmarks"]
    result = format_quick_stats(mock_manager, selection)
    assert len(result) == 3


def test_format_quick_stats_empty_selection(mock_manager):
    """format_quick_stats handles empty selection."""
    mock_manager.projects = []
    result = format_quick_stats(mock_manager, [])
    assert result == []


def test_format_quick_stats_uncompleted_projects(mock_manager):
    """format_quick_stats counts uncompleted projects correctly."""
    mock_manager.projects = [
        Mock(status="Done"),
        Mock(status="In Progress"),
        Mock(status="Planned"),
    ]
    selection = ["uncompleted_projects"]
    result = format_quick_stats(mock_manager, selection)
    assert "2 uncompleted projects" in result[0]


def test_format_quick_stats_uncompleted_tasks(mock_manager):
    """format_quick_stats counts uncompleted tasks correctly."""
    mock_manager.standalone_tasks = [
        Mock(completed=None),
        Mock(completed=None),
        Mock(completed=True),
    ]
    selection = ["uncompleted_tasks"]
    result = format_quick_stats(mock_manager, selection)
    assert "2 uncompleted tasks" in result[0]


def test_format_quick_stats_bookmarks_flat(mock_manager):
    """format_quick_stats counts flat bookmarks correctly."""
    mock_manager.bookmarks = [
        Bookmark(title="Link 1", url="http://test1.com"),
        Bookmark(title="Link 2", url="http://test2.com"),
    ]
    selection = ["bookmarks"]
    result = format_quick_stats(mock_manager, selection)
    assert "2 bookmarks" in result[0]


def test_format_quick_stats_bookmarks_in_lists(mock_manager):
    """format_quick_stats counts bookmarks in lists correctly."""
    bookmark_list = BookmarkList(
        title="My List",
        items=[
            Bookmark(title="Link 1", url="http://test1.com"),
            Bookmark(title="Link 2", url="http://test2.com"),
        ],
    )
    mock_manager.bookmarks = [bookmark_list]
    selection = ["bookmarks"]
    result = format_quick_stats(mock_manager, selection)
    assert "2 bookmarks" in result[0]


def test_format_quick_stats_mixed_bookmarks(mock_manager):
    """format_quick_stats counts mixed bookmarks correctly."""
    bookmark_list = BookmarkList(
        title="List",
        items=[
            Bookmark(title="Link 1", url="http://test1.com"),
        ],
    )
    mock_manager.bookmarks = [
        bookmark_list,
        Bookmark(title="Link 2", url="http://test2.com"),
    ]
    selection = ["bookmarks"]
    result = format_quick_stats(mock_manager, selection)
    assert "2 bookmarks" in result[0]


def test_format_quick_stats_preserves_order(mock_manager):
    """format_quick_stats preserves QUICK_STATS_ORDER."""
    mock_manager.projects = [Mock(status="In Progress")]
    mock_manager.standalone_tasks = [Mock(completed=None)]
    mock_manager.bookmarks = []

    # Request in reverse order
    selection = ["bookmarks", "uncompleted_tasks", "uncompleted_projects"]
    result = format_quick_stats(mock_manager, selection)

    # Should still be in QUICK_STATS_ORDER
    assert "uncompleted project" in result[0]
    assert "uncompleted task" in result[1]
    assert "bookmark" in result[2]


# ==================== Edge Cases ====================


def test_get_stats_with_none_status():
    """get_stats handles projects with None status."""
    projects = [
        Project(
            id=1,
            name="Project",
            status="In Progress",
            tasks=[],
        )
    ]
    # Manually set status to None (shouldn't happen in practice)
    projects[0].status = None
    stats = get_stats(projects)
    assert stats["total"] == 1
    assert stats["done"] == 0


def test_format_quick_stats_with_missing_attributes(mock_manager):
    """format_quick_stats handles manager with missing attributes."""
    # Manager without projects attribute
    delattr(mock_manager, "projects")
    selection = ["uncompleted_projects"]
    result = format_quick_stats(mock_manager, selection)
    assert "0 uncompleted projects" in result[0]


def test_render_progress_bar_custom_width():
    """render_progress_bar respects custom width."""
    result = render_progress_bar(50, width=20)
    assert len(result) == 20
    assert "▬" in result
    assert "▭" in result


def test_filter_projects_by_tab_invalid_index(sample_projects):
    """filter_projects_by_tab handles invalid tab index."""
    # Out-of-bounds index should return all projects
    filtered = filter_projects_by_tab(sample_projects, 99)
    assert len(filtered) == len(sample_projects)
