#!/usr/bin/env python3
"""Data models for project management system."""

from __future__ import annotations

import errno
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Union, Tuple

# Status and level constants
STATUS_OPTIONS = ["Planned", "In Progress", "On Hold", "Done"]
STATUS_DISPLAY_ORDER = ["Done", "In Progress", "On Hold", "Planned"]
STATUS_META = {
    "Planned": {"icon": "○", "color": "blue"},
    "In Progress": {"icon": "◉", "color": "cyan"},
    "On Hold": {"icon": "⊙", "color": "yellow"},
    "Done": {"icon": "✓", "color": "green"},
}
STATUS_STAT_KEYS = {
    "Planned": "planned",
    "In Progress": "inProgress",
    "On Hold": "onHold",
    "Done": "done",
}
TIMEFRAME_OPTIONS = ["None", "▬", "▬ ▬", "▬ ▬ ▬"]
LEVEL_COLORS = {"High": "red", "Medium": "yellow", "Low": "green"}
LIST_COLOR_OPTIONS = ["white", "cyan", "blue", "green", "yellow", "magenta", "red"]
DONE_DISPLAY_OPTIONS = ["section", "inline", "bottom"]
DONE_DISPLAY_LABELS = {
    "section": "Section",
    "inline": "Inline",
    "bottom": "Bottom"
}

DEFAULT_DATA_TEMPLATE = {
    "projects": [],
    "standalone_tasks": [],
    "bookmarks": [],
    "list_tasks": {},  # Mapping of list name -> list of sections (each section has name and tasks)
    "list_metadata": {},  # Mapping of list name -> metadata (color, etc.)
    "metadata": {
        "lastUpdated": "",
        "version": "1.0",
        # Persisted UI hints
        "collapsed_tasks": ["section_completed"],
        # List of pinned items: {"type": "task"|"project"|"bookmark"|"bookmark_list"|"list"|"section", "id": ..., ...}
        "pinned_items": [],
    },
}
def fresh_default_data() -> dict:
    return json.loads(json.dumps(DEFAULT_DATA_TEMPLATE))


logger = logging.getLogger(__name__)


class DataSaveError(Exception):
    """Raised when persisting data to disk fails."""

    def __init__(self, message: str, original_error: OSError) -> None:
        super().__init__(message)
        self.original_error = original_error


@dataclass
class Section:
    """A section within a task list containing a list of tasks."""

    name: str
    id: Optional[str] = None
    tasks: List["Task"] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _generate_section_id())
        elif not isinstance(self.id, str):
            object.__setattr__(self, "id", str(self.id))

    def to_dict(self) -> dict:
        """Serialize section to dictionary."""
        return {
            "name": self.name,
            "id": self.id,
            "tasks": [task.to_dict() for task in self.tasks]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Section":
        """Deserialize section from dictionary."""
        tasks = [Task.from_dict(task_data) for task_data in data.get("tasks", [])]
        return cls(
            name=data.get("name", ""),
            id=data.get("id") or data.get("section_id"),
            tasks=tasks,
        )


def _generate_task_id() -> str:
    return uuid.uuid4().hex


def _generate_section_id() -> str:
    return uuid.uuid4().hex


def _generate_list_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Task:
    """Task with optional subtasks and tri-state completion (None/True/False)."""

    name: str
    id: Optional[str] = None
    completed: Optional[bool] = None  # None = empty, True = done, False = not done
    subtasks: List["Task"] = field(default_factory=list)
    priority: Optional[str] = None  # Low, Medium, High, or None
    deadline: Optional[str] = None  # Optional deadline in YYYY-MM-DD format
    notes: Optional[str] = None  # Optional notes/description for the task
    _project_ref: Optional["Project"] = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        """Wrap subtasks in observable list for cache invalidation."""
        if not self.id:
            object.__setattr__(self, "id", _generate_task_id())
        elif not isinstance(self.id, str):
            object.__setattr__(self, "id", str(self.id))
        if isinstance(self.subtasks, TaskList):
            self.subtasks._set_project(self._project_ref)
        else:
            original_subtasks = list(self.subtasks)
            self.subtasks = TaskList(owner=self, project=self._project_ref, iterable=original_subtasks)

    def __setattr__(self, key, value):
        object.__setattr__(self, key, value)
        if key == "completed":
            project = getattr(self, "_project_ref", None)
            if project:
                project._invalidate_cache()

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        subtasks_data = data.get("subtasks", [])
        subtasks = [cls.from_dict(st) for st in subtasks_data]
        task_id = data.get("id") or data.get("task_id") or data.get("uid")

        # Handle tri-state: None, True, False
        completed_value = data.get("completed")
        if completed_value is None:
            completed = None
        else:
            completed = bool(completed_value)

        # Handle priority with default for backwards compatibility
        priority = data.get("priority", None)

        # Handle deadline with default for backwards compatibility
        deadline = data.get("deadline")

        # Handle notes with default for backwards compatibility
        notes = data.get("notes")

        return cls(
            name=data.get("name", ""),
            id=task_id,
            completed=completed,
            subtasks=subtasks,
            priority=priority,
            deadline=deadline,
            notes=notes
        )

    def to_dict(self) -> dict:
        result = {"id": self.id, "name": self.name}
        # Only include completed if it's not None
        if self.completed is not None:
            result["completed"] = self.completed
        # Include priority if it's set
        if self.priority is not None:
            result["priority"] = self.priority
        # Include deadline if it's set
        if self.deadline is not None:
            result["deadline"] = self.deadline
        # Include notes if it's set
        if self.notes is not None:
            result["notes"] = self.notes
        if self.subtasks:
            result["subtasks"] = [st.to_dict() for st in self.subtasks]
        return result

    def count_total(self) -> int:
        """Count total tasks including subtasks."""
        total = 1
        for subtask in self.subtasks:
            total += subtask.count_total()
        return total

    def count_completed(self) -> int:
        """Count completed tasks including subtasks (True/False both count as completed, None means not started)."""
        count = 1 if self.completed is not None else 0  # Both True and False count as completed
        for subtask in self.subtasks:
            count += subtask.count_completed()
        return count

    def _attach_to_project(self, project: Optional["Project"]) -> None:
        """Attach this task (and descendants) to a project for cache invalidation."""
        object.__setattr__(self, "_project_ref", project)
        if isinstance(self.subtasks, TaskList):
            self.subtasks._set_project(project)
        else:
            original_subtasks = list(self.subtasks)
            self.subtasks = TaskList(owner=self, project=project, iterable=original_subtasks)

    def _detach_from_project(self) -> None:
        """Detach this task from any project (used when removing tasks)."""
        self._attach_to_project(None)


class TaskList(list):
    """List wrapper that invalidates project caches when mutated."""

    def __init__(self, owner: object, project: Optional["Project"], iterable: Iterable["Task"] = ()):
        self._owner = owner
        self._project = project
        self._suspend_invalidation = True
        super().__init__()
        if iterable:
            self.extend(iterable)
        self._suspend_invalidation = False

    def _set_project(self, project: Optional["Project"]) -> None:
        self._project = project
        self._suspend_invalidation = True
        for task in self:
            task._attach_to_project(project)
        self._suspend_invalidation = False

    def _invalidate(self) -> None:
        if not self._suspend_invalidation and self._project:
            self._project._invalidate_cache()

    def _prepare_item(self, task: "Task") -> "Task":
        if not isinstance(task, Task):
            raise TypeError("TaskList can only contain Task instances")
        task._attach_to_project(self._project)
        return task

    def _detach_item(self, task: "Task") -> None:
        if isinstance(task, Task):
            task._detach_from_project()

    def append(self, task: "Task") -> None:
        super().append(self._prepare_item(task))
        self._invalidate()

    def extend(self, iterable: Iterable["Task"]) -> None:
        items = [self._prepare_item(task) for task in iterable]
        super().extend(items)
        self._invalidate()

    def insert(self, index: int, task: "Task") -> None:
        super().insert(index, self._prepare_item(task))
        self._invalidate()

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            values = [self._prepare_item(task) for task in value]
            for task in self[index]:
                self._detach_item(task)
            super().__setitem__(index, values)
        else:
            self._detach_item(self[index])
            super().__setitem__(index, self._prepare_item(value))
        self._invalidate()

    def __delitem__(self, index):
        removed = self[index]
        if isinstance(index, slice):
            for task in removed:
                self._detach_item(task)
        else:
            self._detach_item(removed)
        super().__delitem__(index)
        self._invalidate()

    def pop(self, index: int = -1) -> "Task":
        task = super().pop(index)
        self._detach_item(task)
        self._invalidate()
        return task

    def remove(self, task: "Task") -> None:
        super().remove(task)
        self._detach_item(task)
        self._invalidate()

    def clear(self) -> None:
        for task in list(self):
            self._detach_item(task)
        super().clear()
        self._invalidate()

    def sort(self, *args, **kwargs) -> None:
        super().sort(*args, **kwargs)
        self._invalidate()


@dataclass
class Bookmark:
    """Bookmark with title and URL."""

    title: str
    url: str
    id: Optional[str] = None
    copied: bool = False

    def __post_init__(self) -> None:
        if not self.id:
            self.id = uuid.uuid4().hex
        elif not isinstance(self.id, str):
            self.id = str(self.id)

    @classmethod
    def from_dict(cls, data: dict) -> "Bookmark":
        return cls(
            title=data.get("title", ""),
            url=data.get("url", ""),
            id=data.get("id"),
        )

    def to_dict(self) -> dict:
        return {
            "type": "bookmark",
            "title": self.title,
            "url": self.url,
            "id": self.id,
        }


@dataclass
class BookmarkList:
    """List of bookmarks with a title."""

    title: str
    id: Optional[str] = None
    items: List[Bookmark] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = uuid.uuid4().hex
        elif not isinstance(self.id, str):
            self.id = str(self.id)

    @classmethod
    def from_dict(cls, data: dict) -> "BookmarkList":
        items_data = data.get("items", [])
        items = [Bookmark.from_dict(item) for item in items_data]
        return cls(
            title=data.get("title", ""),
            id=data.get("id"),
            items=items,
        )

    def to_dict(self) -> dict:
        return {
            "type": "list",
            "title": self.title,
            "id": self.id,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass
class Project:
    """Project with tasks"""
    id: int
    name: str
    status: str
    tasks: List[Task] = field(default_factory=list)
    description: str = ""  # Optional project description
    # Dynamic custom fields (replaces hardcoded timeframe)
    custom_field_values: Dict[str, Any] = field(default_factory=dict)
    # Legacy field - kept for backwards compatibility during loading
    timeframe: Optional[str] = field(default=None, init=False, repr=False)
    # Cache fields for expensive operations
    _total_tasks_cache: Optional[int] = field(default=None, init=False, repr=False)
    _completed_tasks_cache: Optional[int] = field(default=None, init=False, repr=False)
    _progress_cache: Optional[int] = field(default=None, init=False, repr=False)
    _progress_str_cache: Optional[str] = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        """Wrap project tasks in observable list and attach tasks to this project."""
        if isinstance(self.tasks, TaskList):
            self.tasks._set_project(self)
        else:
            original_tasks = list(self.tasks)
            self.tasks = TaskList(owner=self, project=self, iterable=original_tasks)

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        tasks = [Task.from_dict(t) for t in data.get("tasks", [])]

        # Handle custom fields
        custom_field_values = data.get("custom_field_values", {})

        project = cls(
            id=int(data.get("id")),
            name=data.get("name", "Unnamed"),
            status=data.get("status", "Planned"),
            tasks=tasks,
            description=data.get("description", ""),
            custom_field_values=custom_field_values,
        )

        return project

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "tasks": [task.to_dict() for task in self.tasks],
        }
        # Only include description if it's not empty
        if self.description:
            result["description"] = self.description
        # Include custom field values
        if self.custom_field_values:
            result["custom_field_values"] = self.custom_field_values
        return result

    def get_field_value(self, field_key: str, default: Any = None) -> Any:
        """Get a custom field value by key."""
        return self.custom_field_values.get(field_key, default)

    def set_field_value(self, field_key: str, value: Any) -> None:
        """Set a custom field value by key."""
        self.custom_field_values[field_key] = value

    def has_field_value(self, field_key: str) -> bool:
        """Check if a custom field value exists."""
        return field_key in self.custom_field_values

    def _invalidate_cache(self) -> None:
        """Invalidate cached values when tasks change"""
        self._total_tasks_cache = None
        self._completed_tasks_cache = None
        self._progress_cache = None
        self._progress_str_cache = None

    def count_total_tasks(self) -> int:
        """Count all tasks including subtasks"""
        if self._total_tasks_cache is None:
            self._total_tasks_cache = sum(task.count_total() for task in self.tasks)
        return self._total_tasks_cache

    def count_completed_tasks(self) -> int:
        """Count all completed tasks including subtasks"""
        if self._completed_tasks_cache is None:
            self._completed_tasks_cache = sum(task.count_completed() for task in self.tasks)
        return self._completed_tasks_cache

    def progress_percentage(self) -> int:
        """Get completion percentage"""
        if self._progress_cache is None:
            total = self.count_total_tasks()
            if total == 0:
                self._progress_cache = 0
            else:
                self._progress_cache = int((self.count_completed_tasks() / total) * 100)
        return self._progress_cache

    def progress_str(self) -> str:
        """Get progress as string"""
        if self._progress_str_cache is None:
            total = self.count_total_tasks()
            completed = self.count_completed_tasks()
            if total == 0:
                self._progress_str_cache = "No tasks"
            else:
                self._progress_str_cache = f"{completed}/{total}"
        return self._progress_str_cache


class ProjectManager:
    """Manages projects data"""

    def __init__(self, data_path: Path) -> None:
        self.data_path = data_path
        self.projects: List[Project] = []
        self.standalone_tasks: List[Task] = []
        self.bookmarks: List[Union[Bookmark, BookmarkList]] = []
        self.list_tasks: dict[str, List[Section]] = {}  # Option B: per-list task sections
        self.list_metadata: dict[str, dict] = {}  # Metadata for each list (color, etc.)
        self.metadata: dict = {}
        self._dirty = False  # Flag to track if data needs to be saved
        self._project_dict: dict = {}  # For O(1) project lookup
        self.last_error_message: Optional[str] = None
        self.last_autosave_path: Optional[Path] = None
        self._pending_autosave_payload: Optional[str] = None

        # Custom fields (user-created) and built-in field visibility
        self.custom_field_definitions: List = []  # List[CustomField]
        self.default_field_visibility: dict = {
            "timeframe": True,
            "priority": True,
            "area": True,
        }

        self.load()

    def mark_dirty(self) -> None:
        """Flag the in-memory data as needing persistence."""
        if not self._dirty:
            logger.debug("Data marked dirty")
        self._dirty = True

    def mark_standalone_tasks_modified(self) -> None:
        """Mark standalone tasks as modified."""
        self.mark_dirty()

    def mark_list_tasks_modified(self) -> None:
        """Mark per-list task containers as modified."""
        self.mark_dirty()

    def mark_bookmarks_modified(self) -> None:
        """Mark bookmarks as modified."""
        self.mark_dirty()

    def mark_metadata_modified(self) -> None:
        """Mark metadata as modified."""
        self.mark_dirty()

    def _ensure_list_metadata(self, list_name: str) -> dict:
        """Ensure list metadata entry exists and includes a stable ID."""
        changed = False
        if list_name not in self.list_metadata:
            self.list_metadata[list_name] = {"color": "white"}
            changed = True
        meta = self.list_metadata[list_name]
        if not meta.get("id"):
            meta["id"] = _generate_list_id()
            changed = True
        if changed:
            self.mark_list_tasks_modified()
        return meta

    def get_list_id(self, list_name: str) -> Optional[str]:
        """Return the stable ID for a list name, creating one if needed."""
        if not list_name:
            return None
        meta = self._ensure_list_metadata(list_name)
        return meta.get("id")

    def get_list_name_by_id(self, list_id: str) -> Optional[str]:
        """Return the list name for a stable list ID."""
        if not list_id:
            return None
        for name, meta in self.list_metadata.items():
            if meta.get("id") == list_id:
                return name
        return None

    def find_section_by_id(self, section_id: str) -> Tuple[Optional[str], Optional[int], Optional[Section]]:
        """Return (list_name, section_idx, section) for a section ID."""
        if not section_id:
            return None, None, None
        for list_name, sections in self.list_tasks.items():
            for idx, section in enumerate(sections):
                if getattr(section, "id", None) == section_id:
                    return list_name, idx, section
        return None, None, None

    def get_section_id(self, list_name: str, section_idx: int) -> Optional[str]:
        """Return the section ID for a list + index."""
        sections = self.list_tasks.get(list_name, [])
        if section_idx is None or not (0 <= section_idx < len(sections)):
            return None
        return getattr(sections[section_idx], "id", None)

    def load(self) -> None:
        """Load projects from JSON file."""
        try:
            self._ensure_data_file()
        except DataSaveError as exc:
            message = self._friendly_message_for_save_error(exc.original_error)
            logger.error("Failed to create data file %s: %s", self.data_path, exc.original_error, exc_info=True)
            self._notify_user(message)
            self.last_error_message = message
            self.last_autosave_path = None
            self._apply_data(fresh_default_data())
            return

        try:
            raw_text = self.data_path.read_text(encoding="utf-8")
        except OSError as exc:
            message = self._friendly_message_for_load_error(exc)
            logger.error("Failed to read data file %s: %s", self.data_path, exc, exc_info=True)
            self._notify_user(message)
            self.last_error_message = message
            self.last_autosave_path = None
            self._apply_data(fresh_default_data())
            return

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            backup_path = self._backup_corrupt_payload(raw_text)
            from datetime import datetime

            data = fresh_default_data()
            data.setdefault("metadata", {})
            data["metadata"]["recoveryNote"] = (
                f"Recovered on {datetime.now().isoformat(timespec='seconds')} "
                f"from {backup_path.name if backup_path else 'temporary backup'}"
            )
            payload_serialized = json.dumps(data, indent=2)
            try:
                self._write_data(payload_serialized)
            except DataSaveError as exc:
                self._handle_save_error(exc, payload_serialized)
            warning_message = (
                f"Warning: Corrupted data detected in {self.data_path.name}. "
                + (
                    f"A backup was created at {backup_path} and a fresh data file was generated."
                    if backup_path
                    else "Backup creation failed; a fresh data file was generated."
                )
            )
            self.last_error_message = warning_message
            self._notify_user(warning_message)
        else:
            self._clear_error_state()
            self.last_error_message = None

        self._apply_data(data)
        self._pending_autosave_payload = None

    def _save_internal(self, force: bool = False) -> bool:
        """Internal save implementation with optional force flag.

        Args:
            force: If True, save regardless of dirty status

        Returns:
            True if save succeeded, False otherwise
        """
        # Check dirty flag unless force is True
        if not force and not self._dirty:
            logger.debug("Save skipped; data not dirty")
            return True

        from datetime import datetime

        self.metadata["lastUpdated"] = datetime.now().strftime("%Y-%m-%d")
        payload = self._build_payload()

        action_verb = "Force persisting" if force else "Persisting"
        logger.debug("%s data to %s", action_verb, self.data_path)

        if self._persist_payload(payload):
            self._dirty = False
            success_msg = "Force-saved" if force else "Saved"
            logger.info("%s data to %s", success_msg, self.data_path)
            return True

        fail_msg = "force-save" if force else "save"
        logger.error("Failed to %s data to %s", fail_msg, self.data_path)
        return False

    def save(self) -> bool:
        """Save projects to JSON file - only if data is dirty."""
        return self._save_internal(force=False)

    def force_save(self) -> bool:
        """Force save projects to JSON file regardless of dirty status."""
        return self._save_internal(force=True)

    def _apply_data(self, data: dict) -> None:
        """Populate in-memory models from raw data (Option B-aware)."""
        projects_raw = [Project.from_dict(item) for item in data.get("projects", [])]
        self.projects = projects_raw
        # Build project dictionary for O(1) lookup
        self._project_dict = {p.id: p for p in projects_raw}

        # Per-list tasks mapping with sections
        raw_list_tasks = data.get("list_tasks", {}) or {}
        list_tasks: dict[str, List[Section]] = {}

        for list_name, list_data in raw_list_tasks.items():
            try:
                # Check if this is old format (list of tasks) or new format (list of sections)
                if isinstance(list_data, list) and len(list_data) > 0:
                    # Check first item to determine format
                    first_item = list_data[0]
                    if isinstance(first_item, dict) and "name" in first_item and "tasks" in first_item:
                        # New format: list of sections
                        list_tasks[list_name] = [Section.from_dict(section) for section in list_data]
                    else:
                        # Old format: list of tasks - migrate to section format
                        tasks = [Task.from_dict(item) for item in list_data]
                        list_tasks[list_name] = [Section(name="", tasks=tasks)]
                else:
                    # Empty list, create default section
                    list_tasks[list_name] = [Section(name="", tasks=[])]
            except Exception:
                list_tasks[list_name] = [Section(name="", tasks=[])]

        # Backward compatibility: if list_tasks is empty, fall back to standalone_tasks under "Tasks"
        if not list_tasks:
            standalone_raw = data.get("standalone_tasks", []) or []
            tasks = [Task.from_dict(item) for item in standalone_raw]
            list_tasks["Tasks"] = [Section(name="", tasks=tasks)]

        # Set list_tasks and ensure standalone_tasks alias points to the tasks in "Tasks" list
        self.list_tasks = list_tasks
        # Get all tasks from "Tasks" list sections
        tasks_list_tasks = []
        for section in self.list_tasks.get("Tasks", []):
            tasks_list_tasks.extend(section.tasks)
        self.standalone_tasks = tasks_list_tasks

        # Load list metadata (colors, etc.)
        self.list_metadata = data.get("list_metadata", {}) or {}
        # Ensure default "Tasks" list has metadata with default color
        if "Tasks" not in self.list_metadata:
            self.list_metadata["Tasks"] = {"color": "white"}
        elif self.list_metadata["Tasks"].get("color") == "cyan":
            # Migrate existing cyan Tasks list to white
            self.list_metadata["Tasks"]["color"] = "white"
        # Ensure list metadata entries exist and have stable IDs
        for list_name in self.list_tasks.keys():
            self._ensure_list_metadata(list_name)

        # Load bookmarks with type discrimination
        bookmarks_raw = []
        for item in data.get("bookmarks", []):
            item_type = item.get("type", "bookmark")  # Default to bookmark for backward compatibility
            if item_type == "list":
                bookmarks_raw.append(BookmarkList.from_dict(item))
            else:
                bookmarks_raw.append(Bookmark.from_dict(item))
        self.bookmarks = bookmarks_raw

        self.metadata = data.get("metadata", {}) or {}

        # Load custom field definitions
        custom_fields_data = data.get("custom_field_definitions", []) or []
        try:
            from pm_live.custom_fields import CustomField
            self.custom_field_definitions = [
                CustomField.from_dict(field_dict) if isinstance(field_dict, dict) else field_dict
                for field_dict in custom_fields_data
            ]
        except (ImportError, KeyError, TypeError):
            self.custom_field_definitions = []

        # Load built-in field visibility (with defaults)
        visibility = data.get("default_field_visibility", {}) or {}
        self.default_field_visibility = {
            "timeframe": visibility.get("timeframe", True),
            "priority": visibility.get("priority", True),
            "area": visibility.get("area", True),
        }


        # Calculate total tasks across all lists and sections
        total_tasks = sum(len(section.tasks) for sections in self.list_tasks.values() for section in sections)
        logger.info(
            "Data applied: %s projects, %s lists (%s total list tasks), %s bookmarks, %s custom fields",
            len(self.projects),
            len(self.list_tasks),
            total_tasks,
            len(self.bookmarks),
            len(self.custom_field_definitions),
        )

    def _build_payload(self) -> dict:
        """Construct the data payload for persistence (section-aware)."""
        # Flatten standalone_tasks from "Tasks" list sections for backward compatibility
        standalone_tasks = []
        for section in self.list_tasks.get("Tasks", []):
            standalone_tasks.extend(section.tasks)

        # Serialize custom field definitions
        custom_fields_json = []
        for field in self.custom_field_definitions:
            if hasattr(field, 'to_dict'):
                custom_fields_json.append(field.to_dict())
            else:
                custom_fields_json.append(field)

        payload = {
            "projects": [project.to_dict() for project in self.projects],
            # Keep standalone_tasks for backward compatibility (flattened from "Tasks" list sections)
            "standalone_tasks": [task.to_dict() for task in standalone_tasks],
            "bookmarks": [bookmark.to_dict() for bookmark in self.bookmarks],
            # Serialize list_tasks with sections
            "list_tasks": {list_name: [section.to_dict() for section in sections] for list_name, sections in self.list_tasks.items()},
            # Serialize list metadata (colors, etc.)
            "list_metadata": self.list_metadata,
            "metadata": self.metadata,
            # Custom fields (user-created)
            "custom_field_definitions": custom_fields_json,
            # Built-in field visibility
            "default_field_visibility": {
                "timeframe": self.default_field_visibility.get("timeframe", True),
                "priority": self.default_field_visibility.get("priority", True),
                "area": self.default_field_visibility.get("area", True),
            },
        }
        return payload

    def _persist_payload(self, payload: dict) -> bool:
        """Serialize and persist payload, handling errors gracefully."""
        serialized = json.dumps(payload, indent=2)
        try:
            self._write_data(serialized)
        except DataSaveError as exc:
            self._handle_save_error(exc, serialized)
            return False

        self._clear_error_state()
        self._pending_autosave_payload = None
        return True

    def _write_data(self, serialized_payload: str, target_path: Optional[Path] = None) -> None:
        """Persist serialized data to disk using an atomic write."""
        path = target_path or self.data_path
        temp_path = path.with_name(f"{path.name}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(serialized_payload, encoding="utf-8")
            temp_path.replace(path)
            logger.debug("Wrote data atomically to %s", path)
        except OSError as exc:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                logger.debug("Failed to clean up temp file %s", temp_path, exc_info=True)
            raise DataSaveError(f"Unable to write data to {path}", exc)

    def _ensure_data_file(self) -> None:
        """Ensure the backing data file exists."""
        if self.data_path.exists():
            return
        serialized = json.dumps(fresh_default_data(), indent=2)
        self._write_data(serialized)
        logger.info("Created new data file at %s", self.data_path)

    def _backup_corrupt_payload(self, raw_text: str) -> Optional[Path]:
        """Save corrupt JSON to a sidecar file for debugging."""
        base_name = self.data_path.name
        counter = 0
        while True:
            suffix = "" if counter == 0 else f".{counter}"
            candidate = self.data_path.with_name(f"{base_name}.corrupt{suffix}")
            try:
                candidate.write_text(raw_text, encoding="utf-8")
                return candidate
            except OSError as exc:
                logger.error("Failed to write corrupt payload backup to %s: %s", candidate, exc, exc_info=True)
                counter += 1
                if counter > 3:
                    break

        temp_dir = Path(tempfile.gettempdir())
        fallback = temp_dir / f"{self.data_path.stem}.corrupt.json"
        try:
            fallback.write_text(raw_text, encoding="utf-8")
            return fallback
        except OSError as exc:
            logger.error("Failed to write fallback corrupt payload backup to %s: %s", fallback, exc, exc_info=True)
            return None

    def get_project(self, project_id: int) -> Optional[Project]:
        """Get project by ID - O(1) lookup using dictionary"""
        return self._project_dict.get(project_id)

    def add_project(self, project: Project) -> None:
        """Add new project"""
        self.projects.append(project)
        # Add to project dictionary for O(1) lookup
        self._project_dict[project.id] = project

        self._dirty = True
        logger.info("Project added: %s (id=%s)", project.name, project.id)
        # Save immediately to ensure data consistency
        self.save()

    def update_project(self, project: Project) -> None:
        """Persist changes to an existing project identified by ID."""
        for index, existing in enumerate(self.projects):
            if existing.id == project.id:
                self.projects[index] = project
                # Update project dictionary
                self._project_dict[project.id] = project
                break
        else:
            raise ValueError(f"Project with id {project.id} not found")
        self._dirty = True
        logger.info("Project updated: %s (id=%s)", project.name, project.id)
        # Save immediately to ensure data consistency
        self.save()

    def delete_project(self, project_id: int) -> None:
        """Delete project"""
        self.projects = [p for p in self.projects if p.id != project_id]
        # Remove from project dictionary
        removed = self._project_dict.pop(project_id, None)
        self._dirty = True
        logger.info("Project deleted: id=%s", project_id)
        # Save immediately to ensure data consistency
        self.save()

    def next_id(self) -> int:
        """Get next available project ID"""
        if not self.projects:
            return 1
        return max(p.id for p in self.projects) + 1

    def filter_projects(self, status: Optional[str] = None) -> List[Project]:
        """Filter projects by status - optimized version"""
        if not status:
            return self.projects
        # Use generator expression and list conversion - more memory efficient
        return [p for p in self.projects if p.status == status]

    def export_data(self) -> dict:
        """Export data to Downloads folder with timestamped filename.
        
        Returns:
            dict with 'success' (bool), 'filename' (str if success) or 'error' (str if failure)
        """
        try:
            from datetime import datetime
            
            # Generate export filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_name = f"projects_export_{timestamp}.json"
            
            # Export to user's Downloads folder
            downloads_path = Path.home() / "Downloads"
            downloads_path.mkdir(parents=True, exist_ok=True)
            export_path = downloads_path / export_name
            
            # Build the payload
            payload = self._build_payload()
            serialized = json.dumps(payload, indent=2)
            
            # Write export file
            export_path.write_text(serialized, encoding="utf-8")
            logger.info("Data exported to %s", export_path)
            
            return {
                'success': True,
                'filename': export_name
            }
        except OSError as exc:
            error_msg = getattr(exc, 'strerror', '') or str(exc)
            logger.error("Failed to export data: %s", exc, exc_info=True)
            return {
                'success': False,
                'error': error_msg
            }
        except Exception as exc:
            logger.error("Unexpected error during export: %s", exc, exc_info=True)
            return {
                'success': False,
                'error': str(exc)
            }

    # --- Internal helpers -------------------------------------------------

    def _handle_save_error(self, error: DataSaveError, serialized_payload: str) -> None:
        """Handle save failures with fallback logic and user messaging."""
        self._pending_autosave_payload = serialized_payload
        base_message = self._friendly_message_for_save_error(error.original_error)
        fallback_path = self._try_fallback_save(serialized_payload)
        if fallback_path:
            message = f"{base_message} Data was written to a temporary backup at {fallback_path}."
        else:
            message = (
                f"{base_message} Changes are kept in memory and will be retried automatically."
            )

        self.last_error_message = message
        self.last_autosave_path = fallback_path
        logger.error(
            "Failed to persist data to %s: %s",
            self.data_path,
            error.original_error,
            exc_info=True,
        )
        self._notify_user(message)

    def _try_fallback_save(self, serialized_payload: str) -> Optional[Path]:
        """Attempt to save data to a safe temporary location."""
        temp_dir = Path(tempfile.gettempdir())
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        fallback = temp_dir / f"{self.data_path.stem}_autosave_{timestamp}.json"
        try:
            fallback.write_text(serialized_payload, encoding="utf-8")
        except OSError as exc:
            logger.error(
                "Fallback autosave failed for %s: %s", fallback, exc, exc_info=True
            )
            return None
        return fallback

    def _friendly_message_for_save_error(self, error: OSError) -> str:
        """Create a user-friendly message for save failures."""
        code = getattr(error, "errno", None)
        winerror = getattr(error, "winerror", None)

        if code == errno.ENOSPC:
            return "Cannot save: disk is full. Free up space and try again."

        permission_codes = {errno.EACCES, errno.EPERM}
        if code in permission_codes or isinstance(error, PermissionError):
            if winerror in (32, 33):
                return "Cannot save: file is locked. Close other programs using this file."
            return "Cannot save: permission denied. Check file permissions."

        busy_codes = {getattr(errno, "EBUSY", None), getattr(errno, "ETXTBSY", None)}
        busy_codes = {c for c in busy_codes if c is not None}
        if code in busy_codes or winerror in (32, 33):
            return "Cannot save: file is locked. Close other programs using this file."

        strerror = getattr(error, "strerror", "") or str(error)
        return f"Cannot save data: {strerror}."

    def _friendly_message_for_load_error(self, error: OSError) -> str:
        """Create a user-friendly message for load failures."""
        code = getattr(error, "errno", None)
        winerror = getattr(error, "winerror", None)

        if code == errno.ENOENT:
            return (
                "Data file missing and could not be recreated. Using in-memory data; "
                "recent changes may not be saved."
            )

        if code == errno.EACCES or isinstance(error, PermissionError):
            if winerror in (32, 33):
                return (
                    "Cannot load data: the file is locked by another program. "
                    "Close the program and restart."
                )
            return (
                "Cannot load data: permission denied. "
                "Check file permissions before restarting."
            )

        strerror = getattr(error, "strerror", "") or str(error)
        return (
            f"Unable to read data file ({strerror}). "
            "Using in-memory data; changes will be retried on save."
        )

    def _clear_error_state(self) -> None:
        """Reset error tracking attributes."""
        self.last_error_message = None
        self.last_autosave_path = None
        self._pending_autosave_payload = None

    def _notify_user(self, message: str) -> None:
        """Display a message to the user without exposing raw tracebacks.
        Styled using ANSI so that messages are visually distinct even outside the TUI.
        - Errors: bold red
        - Warnings: yellow
        - Info: bright black (color(243) substitute on Windows)
        """
        if not message:
            return
        try:
            text = str(message)
        except Exception:
            text = message  # best attempt fallback

        lower = text.lower()
        RED_BOLD = "\x1b[1;31m"
        YELLOW = "\x1b[33m"
        BRIGHT_BLACK = "\x1b[90m"
        RESET = "\x1b[0m"

        if any(k in lower for k in ("error", "failed", "cannot", "unable")):
            print(f"{RED_BOLD}{text}{RESET}")
        elif "warning" in lower:
            print(f"{YELLOW}{text}{RESET}")
        else:
            print(f"{BRIGHT_BLACK}{text}{RESET}")

    # -------------------------------------------------------------------------
    # Pinned Items Management
    # -------------------------------------------------------------------------
    MAX_PINNED_ITEMS = None  # Unlimited pinned items

    def get_pinned_items(self) -> List[dict]:
        """Get all pinned items."""
        pinned = self.metadata.get("pinned_items", [])
        return pinned

    def _items_match(self, item_type: str, pinned_item: dict, item_id) -> bool:
        """Check if a pinned item matches the given item_id.

        Args:
            item_type: Type of item being matched
            pinned_item: The pinned item dict from metadata
            item_id: The item identifier to match against (int, str, or dict)

        Returns:
            True if the items match, False otherwise
        """
        if item_type in ("project", "task"):
            return pinned_item.get("id") == item_id

        if item_type == "bookmark":
            if isinstance(item_id, dict):
                # Match by ID if both have it
                if pinned_item.get("id") and pinned_item.get("id") == item_id.get("id"):
                    return True
                # Otherwise match by title + url
                return (pinned_item.get("title") == item_id.get("title") and
                        pinned_item.get("url") == item_id.get("url"))
            return pinned_item.get("id") == item_id

        if item_type == "bookmark_list":
            if isinstance(item_id, dict):
                if pinned_item.get("id") and pinned_item.get("id") == item_id.get("id"):
                    return True
                return pinned_item.get("title") == item_id.get("title")
            return pinned_item.get("id") == item_id

        if item_type == "list":
            if isinstance(item_id, dict):
                if pinned_item.get("id") and pinned_item.get("id") == item_id.get("id"):
                    return True
                return pinned_item.get("name") == item_id.get("name")
            return pinned_item.get("id") == item_id

        if item_type == "section":
            if isinstance(item_id, dict):
                if pinned_item.get("id") and pinned_item.get("id") == item_id.get("id"):
                    return True
                return (pinned_item.get("list_name") == item_id.get("list_name") and
                        pinned_item.get("section_idx") == item_id.get("section_idx"))
            return False

        return False

    def is_pinned(self, item_type: str, item_id) -> bool:
        """Check if an item is pinned.

        Args:
            item_type: "task", "project", "bookmark", "bookmark_list", "list", or "section"
            item_id: Task id, project id (int), bookmark/list id or dict with id/title/url, list dict with id/name,
                     or section dict with id/list_id/list_name
        """
        pinned = self.get_pinned_items()
        for item in pinned:
            if item.get("type") == item_type and self._items_match(item_type, item, item_id):
                return True
        return False

    def _create_pin_dict(self, item_type: str, item_id, extra_data: dict = None) -> dict:
        """Create a pin dictionary for the given item.

        Args:
            item_type: Type of item to pin
            item_id: Item identifier
            extra_data: Additional data to include in pin dict

        Returns:
            Dictionary representing the pinned item
        """
        new_pin = {"type": item_type}

        if item_type in ("project", "task"):
            new_pin["id"] = item_id
        elif item_type == "bookmark":
            if isinstance(item_id, dict):
                new_pin["title"] = item_id.get("title")
                new_pin["url"] = item_id.get("url")
                if item_id.get("id"):
                    new_pin["id"] = item_id.get("id")
            else:
                new_pin["id"] = item_id
        elif item_type == "bookmark_list":
            if isinstance(item_id, dict):
                new_pin["title"] = item_id.get("title")
                if item_id.get("id"):
                    new_pin["id"] = item_id.get("id")
            else:
                new_pin["id"] = item_id
        elif item_type == "list":
            if isinstance(item_id, dict):
                new_pin["name"] = item_id.get("name")
                if item_id.get("id"):
                    new_pin["id"] = item_id.get("id")
            else:
                new_pin["id"] = item_id
        elif item_type == "section":
            if isinstance(item_id, dict):
                if item_id.get("list_name"):
                    new_pin["list_name"] = item_id.get("list_name")
                if item_id.get("list_id"):
                    new_pin["list_id"] = item_id.get("list_id")
                if item_id.get("id"):
                    new_pin["id"] = item_id.get("id")
                if item_id.get("section_idx") is not None:
                    new_pin["section_idx"] = item_id.get("section_idx")

        if extra_data:
            new_pin.update(extra_data)

        return new_pin

    def toggle_pin(self, item_type: str, item_id, extra_data: dict = None) -> bool:
        """Toggle pin status of an item.

        Args:
            item_type: "task", "project", "bookmark", "bookmark_list", "list", or "section"
            item_id: Task id, project id (int), bookmark dict with id/title/url, bookmark list dict with id/title,
                     list dict with id/name, or section dict with id/list_id/list_name
            extra_data: Additional data to store (e.g., task name for display, bookmark list title, section name)

        Returns:
            True if item is now pinned, False if unpinned
        """
        pinned = self.metadata.get("pinned_items", [])

        # Check if already pinned and remove if found
        for i, item in enumerate(pinned):
            if item.get("type") == item_type and self._items_match(item_type, item, item_id):
                pinned.pop(i)
                self.metadata["pinned_items"] = pinned
                self.mark_metadata_modified()
                return False

        # Not pinned - add it
        new_pin = self._create_pin_dict(item_type, item_id, extra_data)
        pinned.append(new_pin)
        self.metadata["pinned_items"] = pinned
        self.mark_metadata_modified()
        return True

    def _find_task_by_id(self, tasks: List, task_id: str) -> Optional[Task]:
        for task in tasks:
            if getattr(task, "id", None) == task_id:
                return task
            subtasks = getattr(task, "subtasks", None)
            if subtasks:
                found = self._find_task_by_id(subtasks, task_id)
                if found:
                    return found
        return None

    def _find_task_by_name(self, tasks: List, name: str) -> Optional[Task]:
        for task in tasks:
            if getattr(task, "name", None) == name:
                return task
            subtasks = getattr(task, "subtasks", None)
            if subtasks:
                found = self._find_task_by_name(subtasks, name)
                if found:
                    return found
        return None

    def _iter_section_tasks(self, section: object) -> List[Task]:
        if hasattr(section, "tasks"):
            return list(getattr(section, "tasks", []))
        if isinstance(section, dict):
            return list(section.get("tasks", []))
        return []

    def _find_task_in_list(self, list_name: str, section_idx: Optional[int], task_id: Optional[str], task_name: Optional[str]) -> Optional[Task]:
        sections = getattr(self, "list_tasks", {}).get(list_name, [])
        if not sections:
            return None
        if section_idx is None:
            section_indices = range(len(sections))
        else:
            section_indices = [section_idx]
        for idx in section_indices:
            if 0 <= idx < len(sections):
                section_tasks = self._iter_section_tasks(sections[idx])
                if task_id:
                    found = self._find_task_by_id(section_tasks, task_id)
                    if found:
                        return found
                if task_name:
                    found = self._find_task_by_name(section_tasks, task_name)
                    if found:
                        return found
        return None

    def _find_task_in_projects_by_id(self, task_id: str) -> Tuple[Optional[Task], dict]:
        for project in self.projects:
            task = self._find_task_by_id(project.tasks, task_id)
            if task:
                return task, {"project_id": project.id}
        return None, {}

    def _find_task_in_lists_by_id(self, task_id: str) -> Tuple[Optional[Task], dict]:
        for list_name, sections in self.list_tasks.items():
            for section_idx, section in enumerate(sections):
                section_tasks = self._iter_section_tasks(section)
                task = self._find_task_by_id(section_tasks, task_id)
                if task:
                    return task, {"list_name": list_name, "section_idx": section_idx}
        return None, {}

    def resolve_task_for_pin(
        self,
        task_id: Optional[str],
        task_name: Optional[str] = None,
        project_id: Optional[int] = None,
        list_name: Optional[str] = None,
        section_idx: Optional[int] = None,
    ) -> Tuple[Optional[Task], dict]:
        if project_id is not None:
            project = self.get_project(project_id)
            if project:
                task = None
                if task_id:
                    task = self._find_task_by_id(project.tasks, task_id)
                if not task and task_name:
                    task = self._find_task_by_name(project.tasks, task_name)
                if task:
                    return task, {"project_id": project_id}

        if list_name:
            task = self._find_task_in_list(list_name, section_idx, task_id, task_name)
            if task:
                return task, {"list_name": list_name, "section_idx": section_idx or 0}

        if task_id:
            task, context = self._find_task_in_projects_by_id(task_id)
            if task:
                return task, context
            task, context = self._find_task_in_lists_by_id(task_id)
            if task:
                return task, context

        return None, {}

    def _pin_matches_task(self, item: dict, task: Task, context: dict) -> bool:
        item_id = item.get("id")
        if item_id == task.id:
            return True
        return False

    def _find_bookmark_by_id(self, bookmark_id: str) -> Optional[Bookmark]:
        for item in getattr(self, "bookmarks", []):
            if isinstance(item, Bookmark):
                if getattr(item, "id", None) == bookmark_id:
                    return item
            elif isinstance(item, BookmarkList):
                for bm in getattr(item, "items", []):
                    if getattr(bm, "id", None) == bookmark_id:
                        return bm
        return None

    def _find_bookmark_list_by_id(self, list_id: str) -> Optional[BookmarkList]:
        for item in getattr(self, "bookmarks", []):
            if isinstance(item, BookmarkList) and getattr(item, "id", None) == list_id:
                return item
        return None

    def update_pinned_task_status(self, task_id: str, completed: Optional[bool]) -> None:
        """Update the completion status of a pinned task and underlying data.

        Args:
            task_id: Task id
            completed: New completion status
        """
        if not task_id:
            return
        pinned = self.metadata.get("pinned_items", [])
        task_obj, context = self.resolve_task_for_pin(task_id)

        updated_pins = False
        for item in pinned:
            if item.get("type") != "task":
                continue
            if task_obj and self._pin_matches_task(item, task_obj, context):
                item["completed"] = completed
                item["name"] = task_obj.name
                item["deadline"] = getattr(task_obj, "deadline", None)
                item["priority"] = getattr(task_obj, "priority", None)
                item["notes"] = getattr(task_obj, "notes", None)
                item["id"] = task_obj.id
                if "project_id" in context:
                    item["project_id"] = context["project_id"]
                if "list_name" in context:
                    item["list_name"] = context["list_name"]
                    item["section_idx"] = context.get("section_idx", 0)
                updated_pins = True
            elif item.get("id") == task_id:
                item["completed"] = completed
                updated_pins = True

        if updated_pins:
            self.mark_metadata_modified()

        if task_obj:
            task_obj.completed = completed
            if "project_id" in context:
                project = self.get_project(context["project_id"])
                if project:
                    self.update_project(project)
            elif "list_name" in context:
                self.mark_list_tasks_modified()

    def update_pinned_bookmark(self, old_title: str, old_url: str, new_title: str, new_url: str) -> None:
        """Update a pinned bookmark's details.

        Args:
            old_title: The original title of the bookmark.
            old_url: The original URL of the bookmark.
            new_title: The new title.
            new_url: The new URL.
        """
        pinned = self.metadata.get("pinned_items", [])
        updated = False

        for item in pinned:
            if item.get("type") != "bookmark":
                continue
            item_id = item.get("id")
            if item_id:
                bookmark = self._find_bookmark_by_id(item_id)
                if bookmark:
                    item["title"] = new_title
                    item["url"] = new_url
                    updated = True
                continue
            if item.get("title") == old_title and item.get("url") == old_url:
                item["title"] = new_title
                item["url"] = new_url
                updated = True

        if updated:
            self.mark_metadata_modified()

    def update_pinned_bookmark_list(self, old_title: str, new_title: str) -> None:
        """Update a pinned bookmark list's title.

        Args:
            old_title: The original title of the list.
            new_title: The new title.
        """
        pinned = self.metadata.get("pinned_items", [])
        updated = False

        for item in pinned:
            if item.get("type") != "bookmark_list":
                continue
            item_id = item.get("id")
            if item_id:
                blist = self._find_bookmark_list_by_id(item_id)
                if blist:
                    item["title"] = new_title
                    updated = True
                continue
            if item.get("title") == old_title:
                item["title"] = new_title
                updated = True

        if updated:
            self.mark_metadata_modified()

    def remove_pinned_item(self, item_type: str, item_id) -> None:
        """Remove an item from pinned list (e.g., when deleted).

        Args:
            item_type: "task", "project", "bookmark", "bookmark_list", "list", or "section"
            item_id: Item identifier
        """
        pinned = self.metadata.get("pinned_items", [])
        new_pinned = []

        for item in pinned:
            if item.get("type") != item_type:
                new_pinned.append(item)
                continue

            # Special handling for sections: support partial matching by list_name only
            if item_type == "section" and isinstance(item_id, dict):
                list_name = item_id.get("list_name")
                section_idx = item_id.get("section_idx")

                # Check if it's an exact match first
                if self._items_match(item_type, item, item_id):
                    continue  # Skip this item (remove it)

                # If no partial match criteria provided, don't treat this as a wildcard.
                if list_name is None and section_idx is None:
                    new_pinned.append(item)
                    continue

                # If list_name provided but doesn't match, keep the item
                if list_name is not None and item.get("list_name") != list_name:
                    new_pinned.append(item)
                    continue

                # If section_idx provided but doesn't match, keep the item
                if section_idx is not None and item.get("section_idx") != section_idx:
                    new_pinned.append(item)
                    continue

                # If we get here, it's a partial match - remove it
                continue

            # Standard matching for all other types
            if self._items_match(item_type, item, item_id):
                continue  # Skip this item (remove it)

            new_pinned.append(item)

        if len(new_pinned) != len(pinned):
            self.metadata["pinned_items"] = new_pinned
            self.mark_metadata_modified()

    def refresh_pinned_metadata(self) -> None:
        """Sync pinned metadata and drop entries whose sources no longer exist."""
        pinned = self.metadata.get("pinned_items", [])
        changed = False
        new_pinned = []

        def _bookmark_exists(bookmark_id: Optional[str], title: str, url: str) -> bool:
            if bookmark_id:
                return self._find_bookmark_by_id(bookmark_id) is not None
            for b in getattr(self, "bookmarks", []):
                if getattr(b, "title", None) == title and getattr(b, "url", None) == url:
                    return True
                if hasattr(b, "items"):
                    for item in b.items:
                        if getattr(item, "title", None) == title and getattr(item, "url", None) == url:
                            return True
            return False

        def _bookmark_list_exists(list_id: Optional[str], title: str) -> bool:
            if list_id:
                return self._find_bookmark_list_by_id(list_id) is not None
            for b in getattr(self, "bookmarks", []):
                if getattr(b, "title", None) == title and hasattr(b, "items"):
                    return True
            return False

        for item in pinned:
            item_type = item.get("type")
            if item_type == "project":
                project_id = item.get("id")
                if project_id is None or not self.get_project(project_id):
                    changed = True
                    continue
                new_pinned.append(item)
                continue
            if item_type == "bookmark":
                b_id = item.get("id")
                title = item.get("title")
                url = item.get("url")
                bookmark = self._find_bookmark_by_id(b_id) if b_id else None
                if bookmark:
                    if item.get("title") != bookmark.title:
                        item["title"] = bookmark.title
                        changed = True
                    if item.get("url") != bookmark.url:
                        item["url"] = bookmark.url
                        changed = True
                    new_pinned.append(item)
                    continue
                if not title or not url or not _bookmark_exists(b_id, title, url):
                    changed = True
                    continue
                new_pinned.append(item)
                continue
            if item_type == "bookmark_list":
                list_id = item.get("id")
                title = item.get("title")
                blist = self._find_bookmark_list_by_id(list_id) if list_id else None
                if blist:
                    if item.get("title") != blist.title:
                        item["title"] = blist.title
                        changed = True
                    new_pinned.append(item)
                    continue
                if not title or not _bookmark_list_exists(list_id, title):
                    changed = True
                    continue
                new_pinned.append(item)
                continue
            if item_type == "list":
                list_id = item.get("id")
                list_name = item.get("name")
                resolved_name = self.get_list_name_by_id(list_id) if list_id else list_name
                if not resolved_name or resolved_name not in getattr(self, "list_tasks", {}):
                    changed = True
                    continue
                if item.get("name") != resolved_name:
                    item["name"] = resolved_name
                    changed = True
                if not item.get("id"):
                    item["id"] = self.get_list_id(resolved_name)
                    changed = True
                new_pinned.append(item)
                continue
            if item_type == "section":
                section_id = item.get("id")
                if section_id:
                    list_name, section_idx, section = self.find_section_by_id(section_id)
                    if not list_name or section is None:
                        changed = True
                        continue
                    list_id = self.get_list_id(list_name)
                    if item.get("list_name") != list_name:
                        item["list_name"] = list_name
                        changed = True
                    if item.get("list_id") != list_id:
                        item["list_id"] = list_id
                        changed = True
                    if item.get("section_idx") != section_idx:
                        item["section_idx"] = section_idx
                        changed = True
                    section_name = section.name or "Tasks"
                    if item.get("section_name") != section_name:
                        item["section_name"] = section_name
                        changed = True
                    new_pinned.append(item)
                    continue
                list_name = item.get("list_name")
                section_idx = item.get("section_idx")
                sections = getattr(self, "list_tasks", {}).get(list_name, [])
                if not list_name or section_idx is None or not (0 <= section_idx < len(sections)):
                    changed = True
                    continue
                section = sections[section_idx]
                item["id"] = getattr(section, "id", None)
                item["list_id"] = self.get_list_id(list_name)
                item["section_name"] = section.name or "Tasks"
                changed = True
                new_pinned.append(item)
                continue
            if item_type != "task":
                new_pinned.append(item)
                continue
            task_id = item.get("id")
            task_obj, context = self.resolve_task_for_pin(
                task_id,
                task_name=item.get("name"),
                project_id=item.get("project_id"),
                list_name=item.get("list_name"),
                section_idx=item.get("section_idx"),
            )

            if task_obj:
                source_name = getattr(task_obj, "name", None)
                source_deadline = getattr(task_obj, "deadline", None)
                source_priority = getattr(task_obj, "priority", None)
                source_completed = getattr(task_obj, "completed", None)
                source_notes = getattr(task_obj, "notes", None)

                if source_name and item.get("name") != source_name:
                    item["name"] = source_name
                    changed = True
                if item.get("deadline") != source_deadline:
                    item["deadline"] = source_deadline
                    changed = True
                if item.get("priority") != source_priority:
                    item["priority"] = source_priority
                    changed = True
                if item.get("completed") != source_completed:
                    item["completed"] = source_completed
                    changed = True
                if item.get("notes") != source_notes:
                    item["notes"] = source_notes
                    changed = True
                if item.get("id") != task_obj.id:
                    item["id"] = task_obj.id
                    changed = True
                if "project_id" in context and item.get("project_id") != context["project_id"]:
                    item["project_id"] = context["project_id"]
                    changed = True
                if "list_name" in context:
                    if item.get("list_name") != context["list_name"]:
                        item["list_name"] = context["list_name"]
                        changed = True
                    if item.get("section_idx") != context.get("section_idx", 0):
                        item["section_idx"] = context.get("section_idx", 0)
                        changed = True
                new_pinned.append(item)
            else:
                changed = True

        if changed or len(new_pinned) != len(pinned):
            self.metadata["pinned_items"] = new_pinned
            self.mark_metadata_modified()
