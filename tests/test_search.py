from types import SimpleNamespace

from pm import Project
from pm_live.utils.search import perform_search


def test_perform_search_matches_project_custom_field_values_case_insensitive():
    project = Project(
        id=1,
        name="Alpha",
        status="Planned",
        custom_field_values={"Owner": "Alice", "Budget": 1200},
    )
    manager = SimpleNamespace(projects=[project], list_tasks={}, bookmarks=[])

    results = perform_search(manager, "ali")

    assert any(
        r["type"] == "project" and r["id"] == 1 and r["match_field"] == "Owner"
        for r in results
    )


def test_perform_search_matches_project_custom_field_values_non_string():
    project = Project(
        id=1,
        name="Alpha",
        status="Planned",
        custom_field_values={"Budget": 1200},
    )
    manager = SimpleNamespace(projects=[project], list_tasks={}, bookmarks=[])

    results = perform_search(manager, "1200")

    assert any(
        r["type"] == "project" and r["id"] == 1 and r["match_field"] == "Budget"
        for r in results
    )
