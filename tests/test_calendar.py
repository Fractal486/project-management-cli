"""Tests for calendar rendering and deadline collection."""

from unittest.mock import Mock

from pm import Project, Task, Section
from pm_live.custom_fields import CustomField, FIELD_TYPE_DATE
from pm_live.render.calendar import CalendarRenderer
from pm_live.utils.calendar import collect_deadline_map


def test_calendar_collects_deadlines_from_projects_and_lists():
    """Calendar collects deadlines from projects and standalone lists."""
    manager = Mock()
    manager.projects = [
        Project(
            id=1,
            name="Calendar Project",
            status="Planned",
            tasks=[Task(name="Project Task", deadline="2025-01-15")],
        )
    ]
    manager.standalone_tasks = []
    manager.list_tasks = {
        "Tasks": [
            Section(name="", tasks=[Task(name="Standalone Task", deadline="2025-01-15T10:00:00Z")])
        ]
    }

    deadline_map = collect_deadline_map(manager, manager.list_tasks)

    assert "2025-01-15" in deadline_map
    entries = deadline_map["2025-01-15"]
    names = {entry.item.name for entry in entries if entry.kind == "task"}
    projects = {entry.project_name for entry in entries if entry.kind == "task" and entry.project_name}

    assert "Project Task" in names
    assert "Standalone Task" in names
    assert "Calendar Project" in projects


def test_calendar_collects_project_date_fields():
    """Calendar collects project custom date fields as entries."""
    manager = Mock()
    manager.custom_field_definitions = [
        CustomField(key="kickoff", label="Kickoff", field_type=FIELD_TYPE_DATE),
        CustomField(key="ship_date", label="Ship Date", field_type=FIELD_TYPE_DATE),
    ]
    manager.projects = [
        Project(
            id=1,
            name="Calendar Project",
            status="Planned",
            tasks=[],
            custom_field_values={
                "kickoff": "2025-01-15",
                "ship_date": "2025-01-15",
            },
        )
    ]
    manager.standalone_tasks = []
    manager.list_tasks = {"Tasks": []}

    deadline_map = collect_deadline_map(manager, manager.list_tasks)

    entries = deadline_map["2025-01-15"]
    project_entries = [entry for entry in entries if entry.kind == "project_field"]

    assert len(project_entries) == 2
    labels = {entry.field_label for entry in project_entries}
    assert "Kickoff" in labels
    assert "Ship Date" in labels


def test_calendar_renderer_shows_selected_day_tasks():
    """Calendar renderer shows tasks for the selected day."""
    manager = Mock()
    manager.projects = [
        Project(
            id=1,
            name="Calendar Project",
            status="Planned",
            tasks=[Task(name="Project Task", deadline="2025-01-15")],
        )
    ]
    manager.standalone_tasks = []
    manager.list_tasks = {"Tasks": []}

    renderer = CalendarRenderer()
    context = {
        "manager": manager,
        "selected_index": 0,
        "calendar_year": 2025,
        "calendar_month": 1,
        "calendar_selected_day": 15,
        "calendar_navigation_focus": "day",
        "list_tasks": manager.list_tasks,
    }

    output = renderer.render(context)

    # Check for month and year (separately due to Rich auto-highlighting numbers)
    assert "January" in output
    assert "2025" in output
    assert "Project Task" in output
