"""Quick stats metric definitions and helpers used across the live CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Sequence, Set

from pm import BookmarkList


@dataclass(frozen=True)
class QuickStatDefinition:
    """Definition for a single quick stat entry."""

    key: str
    label_plural: str
    label_singular: str
    compute: Callable[[Any], int]

    def render(self, manager: Any) -> str:
        """Return formatted string for the metric."""
        count = self.compute(manager)
        label = self.label_singular if count == 1 else self.label_plural
        return f"{count} {label}"


def _count_uncompleted_projects(manager: Any) -> int:
    projects = getattr(manager, "projects", [])
    return sum(1 for project in projects if getattr(project, "status", None) != "Done")


def _count_uncompleted_standalone_tasks(manager: Any) -> int:
    tasks = getattr(manager, "standalone_tasks", [])
    return sum(1 for task in tasks if getattr(task, "completed", None) is None)


def _count_total_uncompleted_tasks(manager: Any) -> int:
    return _count_uncompleted_standalone_tasks(manager)


def _count_bookmarks(manager: Any) -> int:
    bookmarks = getattr(manager, "bookmarks", [])
    total = 0
    for item in bookmarks:
        if isinstance(item, BookmarkList):
            total += len(getattr(item, "items", []))
        else:
            total += 1
    return total


QUICK_STATS_ORDER: Sequence[str] = (
    "uncompleted_projects",
    "uncompleted_tasks",
    "bookmarks",
)

QUICK_STATS: dict[str, QuickStatDefinition] = {
    "uncompleted_projects": QuickStatDefinition(
        key="uncompleted_projects",
        label_plural="uncompleted projects",
        label_singular="uncompleted project",
        compute=_count_uncompleted_projects,
    ),
    "uncompleted_tasks": QuickStatDefinition(
        key="uncompleted_tasks",
        label_plural="uncompleted tasks",
        label_singular="uncompleted task",
        compute=_count_total_uncompleted_tasks,
    ),
    "bookmarks": QuickStatDefinition(
        key="bookmarks",
        label_plural="bookmarks",
        label_singular="bookmark",
        compute=_count_bookmarks,
    ),
}

DEFAULT_QUICK_STATS: Sequence[str] = (
    "uncompleted_projects",
    "uncompleted_tasks",
)


def normalize_quick_stats_selection(selection: Iterable[str]) -> List[str]:
    """Return a stable list of valid quick stat keys."""
    selected_set: Set[str] = {key for key in selection if key in QUICK_STATS}
    normalized: List[str] = []
    for key in QUICK_STATS_ORDER:
        if key in selected_set:
            normalized.append(key)
    return normalized


def format_quick_stats(manager: Any, selection: Iterable[str]) -> List[str]:
    """Format quick stats for display given a selection."""
    selected_set: Set[str] = set(selection)
    formatted: List[str] = []
    for key in QUICK_STATS_ORDER:
        if key in selected_set:
            definition = QUICK_STATS[key]
            formatted.append(definition.render(manager))
    return formatted
