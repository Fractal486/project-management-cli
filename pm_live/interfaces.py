"""Shared protocol and context definitions for the live CLI architecture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Protocol, Sequence, Tuple

from pm import Project, Task
from .ui_state import UIState


class DataManagerProtocol(Protocol):
    """Subset of project manager behaviour required by the live CLI."""

    projects: List[Project]
    standalone_tasks: List[Task]

    def get_project(self, project_id: int) -> Optional[Project]:
        ...

    def add_project(self, project: Project) -> None:
        ...

    def update_project(self, project: Project) -> None:
        ...

    def delete_project(self, project_id: int) -> None:
        ...

    def next_id(self) -> int:
        ...

    def filter_projects(self, status: Optional[str] = None) -> List[Project]:
        ...

    def save(self) -> bool:
        ...

    def force_save(self) -> bool:
        ...

    def mark_dirty(self) -> None:
        ...


TaskEntry = Tuple[str, Task, int]
FlattenTaskFn = Callable[[Sequence[Task], bool], List[TaskEntry]]


@dataclass(slots=True)
class HandlerContext:
    """Context object shared by interactive handlers."""

    manager: DataManagerProtocol
    ui_state: UIState
    get_flat_tasks: FlattenTaskFn
    invalidate_task_cache: Callable[[], None]
    exit_application: Callable[[], None]
    show_status: Callable[[Optional[str], bool], None]
    update_console_width: Callable[[int], None]
    update_quick_stats_selection: Callable[[Sequence[str]], None]
    update_main_menu_tabs_selection: Callable[[Sequence[str]], None]
    persist_collapsed_tasks: Callable[[], None]
