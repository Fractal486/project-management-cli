"""Main menu tab definitions and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Set, Tuple


@dataclass(frozen=True)
class MainMenuTabDefinition:
    """Definition for a single main menu tab entry."""

    key: str
    label: str
    action: str


MAIN_MENU_TABS_ORDER: Sequence[str] = (
    "projects",
    "tasks",
    "bookmarks",
    "calendar",
)

MAIN_MENU_TABS: dict[str, MainMenuTabDefinition] = {
    "projects": MainMenuTabDefinition(
        key="projects",
        label="Projects",
        action="browse",
    ),
    "tasks": MainMenuTabDefinition(
        key="tasks",
        label="Tasks",
        action="tasks",
    ),
    "bookmarks": MainMenuTabDefinition(
        key="bookmarks",
        label="Bookmarks",
        action="bookmarks",
    ),
    "calendar": MainMenuTabDefinition(
        key="calendar",
        label="Calendar",
        action="calendar",
    ),
}

DEFAULT_MAIN_MENU_TABS: Sequence[str] = MAIN_MENU_TABS_ORDER


def normalize_main_menu_tabs(selection: Iterable[str]) -> List[str]:
    """Return a stable list of valid main menu tab keys."""
    selected_set: Set[str] = {key for key in selection if key in MAIN_MENU_TABS}
    normalized: List[str] = []
    for key in MAIN_MENU_TABS_ORDER:
        if key in selected_set:
            normalized.append(key)
    return normalized


def build_main_menu_items(selection: Iterable[str]) -> List[Tuple[str, str]]:
    """Build menu items (label, action) for rendering/navigation."""
    selected_set: Set[str] = set(selection)
    items: List[Tuple[str, str]] = []
    for key in MAIN_MENU_TABS_ORDER:
        if key in selected_set:
            definition = MAIN_MENU_TABS[key]
            items.append((definition.label, definition.action))
    items.append(("Statistics", "stats"))
    return items


def is_quick_add_enabled(selection: Iterable[str]) -> bool:
    """Return True if quick add task should be shown."""
    return "tasks" in set(selection)

