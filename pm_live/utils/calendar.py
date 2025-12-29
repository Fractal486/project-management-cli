"""Calendar utilities for deadline-based task lists."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from ..tasks import collect_all_tasks


@dataclass(frozen=True)
class CalendarEntry:
    """Entry for calendar lists (task or project date field)."""

    kind: str  # "task" | "project_field"
    item: object
    project_name: Optional[str] = None
    field_label: Optional[str] = None
    field_key: Optional[str] = None


def parse_deadline_date(deadline: Optional[str]):
    """Parse a deadline value into a date object."""
    if not deadline:
        return None

    if not isinstance(deadline, str):
        try:
            return deadline.date()
        except Exception:
            return None

    raw = deadline.strip()
    if not raw:
        return None

    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except Exception:
        pass

    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except Exception:
        return None


def collect_deadline_map(
    manager,
    list_tasks_map: Optional[dict] = None,
) -> Dict[str, List[CalendarEntry]]:
    """Collect all tasks with deadlines into a date-keyed map."""
    deadline_map: Dict[str, List[CalendarEntry]] = {}

    # Project tasks
    for project in getattr(manager, "projects", []):
        tasks = collect_all_tasks(getattr(project, "tasks", []))
        for task in tasks:
            date_value = parse_deadline_date(getattr(task, "deadline", None))
            if not date_value:
                continue
            date_key = date_value.strftime("%Y-%m-%d")
            deadline_map.setdefault(date_key, []).append(
                CalendarEntry(
                    kind="task",
                    item=task,
                    project_name=getattr(project, "name", None),
                )
            )

    # Project custom date fields
    date_fields: List[Tuple[str, str]] = []
    raw_fields = getattr(manager, "custom_field_definitions", None)
    if raw_fields is None:
        custom_fields = []
    elif isinstance(raw_fields, list):
        custom_fields = list(raw_fields)
    else:
        try:
            custom_fields = list(raw_fields)
        except TypeError:
            custom_fields = []

    for field in custom_fields:
        field_type = getattr(field, "field_type", None)
        if field_type is None and isinstance(field, dict):
            field_type = field.get("field_type")
        if field_type != "date":
            continue

        field_key = getattr(field, "key", None)
        field_label = getattr(field, "label", None)
        if isinstance(field, dict):
            field_key = field_key or field.get("key")
            field_label = field_label or field.get("label")
        if not field_key:
            continue
        date_fields.append((field_key, field_label or field_key))

    if date_fields:
        for project in getattr(manager, "projects", []):
            custom_values = getattr(project, "custom_field_values", {}) or {}
            for field_key, field_label in date_fields:
                value = custom_values.get(field_key, getattr(project, field_key, None))
                date_value = parse_deadline_date(value)
                if not date_value:
                    continue
                date_key = date_value.strftime("%Y-%m-%d")
                deadline_map.setdefault(date_key, []).append(
                    CalendarEntry(
                        kind="project_field",
                        item=project,
                        project_name=getattr(project, "name", None),
                        field_label=field_label,
                        field_key=field_key,
                    )
                )

    # Standalone tasks (from all lists)
    if list_tasks_map is None:
        list_tasks_map = getattr(manager, "list_tasks", {"Tasks": getattr(manager, "standalone_tasks", [])})

    all_tasks: List[object] = []
    for _, sections in list_tasks_map.items():
        if not sections or not isinstance(sections, list):
            continue

        first = sections[0]
        looks_like_section = (
            (isinstance(first, dict) and "tasks" in first)
            or hasattr(first, "tasks")
        )

        if looks_like_section:
            for section in sections:
                section_tasks = section.tasks if hasattr(section, "tasks") else section.get("tasks", [])
                all_tasks.extend(section_tasks)
        else:
            all_tasks.extend(sections)

    for task in collect_all_tasks(all_tasks):
        date_value = parse_deadline_date(getattr(task, "deadline", None))
        if not date_value:
            continue
        date_key = date_value.strftime("%Y-%m-%d")
        deadline_map.setdefault(date_key, []).append(
            CalendarEntry(
                kind="task",
                item=task,
                project_name=None,
            )
        )

    # Sort tasks within each date: tasks first, then projects, then by completion status and priority
    def sort_key(entry):
        """Sort key: kind (task/project), completion status, then priority descending."""
        # Kind: tasks (0) before project_fields (1)
        kind_order = 0 if entry.kind == "task" else 1
        
        # Completion status (only applies to tasks)
        completed = getattr(entry.item, "completed", None) is not None
        
        # Priority order: !!! (0), !! (1), ! (2), None (3)
        priority = getattr(entry.item, "priority", None) if entry.kind == "task" else None
        if priority == "!!!":
            priority_order = 0
        elif priority == "!!":
            priority_order = 1
        elif priority == "!":
            priority_order = 2
        else:
            priority_order = 3
        
        return (kind_order, completed, priority_order)
    
    for date_key in deadline_map:
        deadline_map[date_key].sort(key=sort_key)

    return deadline_map


def collect_overdue_entries(
    manager,
    list_tasks_map: Optional[dict] = None,
    current_date=None,
    max_items: int = 20,
) -> List[Tuple[CalendarEntry, int]]:
    """Collect overdue tasks and project date fields.
    
    Returns list of (CalendarEntry, days_overdue) tuples sorted by days overdue descending.
    Only includes incomplete tasks (completed=None or False counts as incomplete for filtering).
    """
    if current_date is None:
        current_date = datetime.now().date()
    
    overdue_entries: List[Tuple[CalendarEntry, int]] = []
    
    # Project tasks
    for project in getattr(manager, "projects", []):
        tasks = collect_all_tasks(getattr(project, "tasks", []))
        for task in tasks:
            # Skip completed tasks
            completed = getattr(task, "completed", None)
            if completed is True:
                continue
            
            deadline = getattr(task, "deadline", None)
            date_value = parse_deadline_date(deadline)
            if not date_value or date_value >= current_date:
                continue
            
            days_overdue = (current_date - date_value).days
            entry = CalendarEntry(
                kind="task",
                item=task,
                project_name=getattr(project, "name", None),
            )
            overdue_entries.append((entry, days_overdue))
    
    # Project custom date fields (these don't have completion status, always show if overdue)
    date_fields: List[Tuple[str, str]] = []
    raw_fields = getattr(manager, "custom_field_definitions", None)
    if raw_fields is None:
        custom_fields = []
    elif isinstance(raw_fields, list):
        custom_fields = list(raw_fields)
    else:
        try:
            custom_fields = list(raw_fields)
        except TypeError:
            custom_fields = []
    
    for field in custom_fields:
        field_type = getattr(field, "field_type", None)
        if field_type is None and isinstance(field, dict):
            field_type = field.get("field_type")
        if field_type != "date":
            continue
        
        field_key = getattr(field, "key", None)
        field_label = getattr(field, "label", None)
        if isinstance(field, dict):
            field_key = field_key or field.get("key")
            field_label = field_label or field.get("label")
        if not field_key:
            continue
        date_fields.append((field_key, field_label or field_key))
    
    if date_fields:
        for project in getattr(manager, "projects", []):
            custom_values = getattr(project, "custom_field_values", {}) or {}
            for field_key, field_label in date_fields:
                value = custom_values.get(field_key, getattr(project, field_key, None))
                date_value = parse_deadline_date(value)
                if not date_value or date_value >= current_date:
                    continue
                
                days_overdue = (current_date - date_value).days
                entry = CalendarEntry(
                    kind="project_field",
                    item=project,
                    project_name=getattr(project, "name", None),
                    field_label=field_label,
                    field_key=field_key,
                )
                overdue_entries.append((entry, days_overdue))
    
    # Standalone tasks (from all lists)
    if list_tasks_map is None:
        list_tasks_map = getattr(manager, "list_tasks", {"Tasks": getattr(manager, "standalone_tasks", [])})

    all_tasks: List[object] = []
    for _, sections in list_tasks_map.items():
        if not sections or not isinstance(sections, list):
            continue
        
        first = sections[0]
        looks_like_section = (
            (isinstance(first, dict) and "tasks" in first)
            or hasattr(first, "tasks")
        )
        
        if looks_like_section:
            for section in sections:
                section_tasks = section.tasks if hasattr(section, "tasks") else section.get("tasks", [])
                all_tasks.extend(section_tasks)
        else:
            all_tasks.extend(sections)
    
    for task in collect_all_tasks(all_tasks):
        # Skip completed tasks
        completed = getattr(task, "completed", None)
        if completed is True:
            continue
        
        deadline = getattr(task, "deadline", None)
        date_value = parse_deadline_date(deadline)
        if not date_value or date_value >= current_date:
            continue
        
        days_overdue = (current_date - date_value).days
        entry = CalendarEntry(
            kind="task",
            item=task,
            project_name=None,
        )
        overdue_entries.append((entry, days_overdue))
    
    # Sort by days_overdue descending (most overdue first)
    overdue_entries.sort(key=lambda x: x[1], reverse=True)
    
    # Return top max_items
    return overdue_entries[:max_items]


def collect_upcoming_entries(
    manager,
    list_tasks_map: Optional[dict] = None,
    current_date=None,
) -> Dict[str, List[CalendarEntry]]:
    """Collect upcoming tasks and project date fields organized by time period.
    
    Returns dict with keys "today", "next_week", "next_month".
    Each value is a list of CalendarEntry objects sorted by deadline ascending.
    """
    if current_date is None:
        current_date = datetime.now().date()
    
    # Calculate date ranges
    end_of_week = current_date + timedelta(days=7)
    end_of_month = current_date + timedelta(days=30)
    
    upcoming: Dict[str, List[Tuple[CalendarEntry, datetime.date]]] = {
        "today": [],
        "next_week": [],
        "next_month": [],
    }
    
    # Project tasks
    for project in getattr(manager, "projects", []):
        tasks = collect_all_tasks(getattr(project, "tasks", []))
        for task in tasks:
            deadline = getattr(task, "deadline", None)
            date_value = parse_deadline_date(deadline)
            if not date_value or date_value < current_date:
                continue
            
            entry = CalendarEntry(
                kind="task",
                item=task,
                project_name=getattr(project, "name", None),
            )
            
            # Categorize by date range
            if date_value == current_date:
                upcoming["today"].append((entry, date_value))
            elif date_value <= end_of_week:
                upcoming["next_week"].append((entry, date_value))
            elif date_value <= end_of_month:
                upcoming["next_month"].append((entry, date_value))
    
    # Project custom date fields
    date_fields: List[Tuple[str, str]] = []
    raw_fields = getattr(manager, "custom_field_definitions", None)
    if raw_fields is None:
        custom_fields = []
    elif isinstance(raw_fields, list):
        custom_fields = list(raw_fields)
    else:
        try:
            custom_fields = list(raw_fields)
        except TypeError:
            custom_fields = []
    
    for field in custom_fields:
        field_type = getattr(field, "field_type", None)
        if field_type is None and isinstance(field, dict):
            field_type = field.get("field_type")
        if field_type != "date":
            continue
        
        field_key = getattr(field, "key", None)
        field_label = getattr(field, "label", None)
        if isinstance(field, dict):
            field_key = field_key or field.get("key")
            field_label = field_label or field.get("label")
        if not field_key:
            continue
        date_fields.append((field_key, field_label or field_key))
    
    if date_fields:
        for project in getattr(manager, "projects", []):
            custom_values = getattr(project, "custom_field_values", {}) or {}
            for field_key, field_label in date_fields:
                value = custom_values.get(field_key, getattr(project, field_key, None))
                date_value = parse_deadline_date(value)
                if not date_value or date_value < current_date:
                    continue
                
                entry = CalendarEntry(
                    kind="project_field",
                    item=project,
                    project_name=getattr(project, "name", None),
                    field_label=field_label,
                    field_key=field_key,
                )
                
                # Categorize by date range
                if date_value == current_date:
                    upcoming["today"].append((entry, date_value))
                elif date_value <= end_of_week:
                    upcoming["next_week"].append((entry, date_value))
                elif date_value <= end_of_month:
                    upcoming["next_month"].append((entry, date_value))
    
    # Standalone tasks (from all lists)
    if list_tasks_map is None:
        list_tasks_map = getattr(manager, "list_tasks", {"Tasks": getattr(manager, "standalone_tasks", [])})

    all_tasks: List[object] = []
    for _, sections in list_tasks_map.items():
        if not sections or not isinstance(sections, list):
            continue
        
        first = sections[0]
        looks_like_section = (
            (isinstance(first, dict) and "tasks" in first)
            or hasattr(first, "tasks")
        )
        
        if looks_like_section:
            for section in sections:
                section_tasks = section.tasks if hasattr(section, "tasks") else section.get("tasks", [])
                all_tasks.extend(section_tasks)
        else:
            all_tasks.extend(sections)
    
    for task in collect_all_tasks(all_tasks):
        deadline = getattr(task, "deadline", None)
        date_value = parse_deadline_date(deadline)
        if not date_value or date_value < current_date:
            continue
        
        entry = CalendarEntry(
            kind="task",
            item=task,
            project_name=None,
        )
        
        # Categorize by date range
        if date_value == current_date:
            upcoming["today"].append((entry, date_value))
        elif date_value <= end_of_week:
            upcoming["next_week"].append((entry, date_value))
        elif date_value <= end_of_month:
            upcoming["next_month"].append((entry, date_value))
    
    # Sort each section: "today" by priority, others by deadline only
    result: Dict[str, List[CalendarEntry]] = {}
    for key, entries_with_dates in upcoming.items():
        if key == "today":
            # Today section: sort by kind (tasks first), completion status, then priority descending
            def sort_key_today(entry_with_date):
                """Sort key for today: kind, completion status, then priority descending."""
                entry, date_value = entry_with_date
                
                # Kind: tasks (0) before project_fields (1)
                kind_order = 0 if entry.kind == "task" else 1
                
                # Completion status (only applies to tasks)
                completed = getattr(entry.item, "completed", None) is not None
                
                # Priority order: !!! (0), !! (1), ! (2), None (3)
                priority = getattr(entry.item, "priority", None) if entry.kind == "task" else None
                if priority == "!!!":
                    priority_order = 0
                elif priority == "!!":
                    priority_order = 1
                elif priority == "!":
                    priority_order = 2
                else:
                    priority_order = 3
                
                return (kind_order, completed, priority_order)
            
            entries_with_dates.sort(key=sort_key_today)
        else:
            # Next week and next month sections: sort by deadline, then kind (tasks first)
            def sort_key_deadline(entry_with_date):
                """Sort key: deadline first, then kind (tasks before projects)."""
                entry, date_value = entry_with_date
                kind_order = 0 if entry.kind == "task" else 1
                return (date_value, kind_order)
            
            entries_with_dates.sort(key=sort_key_deadline)
        
        result[key] = [entry for entry, _ in entries_with_dates]
    
    return result
