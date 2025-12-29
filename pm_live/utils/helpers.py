"""Helper functions for project statistics and data manipulation."""

from typing import Any, List, Optional, Tuple
from pm import Project
from ..custom_fields import CustomField, get_visible_fields_sorted


def get_stats(projects: List[Project]) -> dict:
    """Get project statistics."""
    return {
        "total": len(projects),
        "done": len([p for p in projects if p.status == "Done"]),
        "inProgress": len([p for p in projects if p.status == "In Progress"]),
        "onHold": len([p for p in projects if p.status == "On Hold"]),
        "planned": len([p for p in projects if p.status == "Planned"]),
    }


def filter_projects_by_tab(projects: List[Project], tab_idx: int) -> List[Project]:
    """Filter projects based on active tab."""
    if tab_idx == 0:  # All
        return projects
    elif tab_idx == 1:  # Uncompleted
        return [p for p in projects if p.status != "Done"]
    else:  # Completed
        return [p for p in projects if p.status == "Done"]


def get_edit_project_field_keys(all_fields: List[CustomField]) -> List[str]:
    """
    Build the ordered list of editable project fields.

    Status, name, and description are always first, followed by built-in
    custom fields (timeframe, priority, area) if visible, then user-defined
    custom fields sorted by their configured order.
    """
    # Split fields into built-ins and custom fields
    builtin_keys = ("timeframe", "priority", "area")
    field_by_key = {field.key: field for field in all_fields}
    
    visible_builtin_fields = [
        field_by_key[key]
        for key in builtin_keys
        if field_by_key.get(key) and field_by_key[key].visible
    ]
    visible_custom_fields = [
        field for field in all_fields
        if field.key not in builtin_keys and field.visible
    ]
    visible_custom_fields.sort(key=lambda f: getattr(f, "order", 0))
    
    # Build final field key list
    field_keys = ["status", "name", "description"]
    field_keys.extend([field.key for field in visible_builtin_fields])
    field_keys.extend([field.key for field in visible_custom_fields])
    
    return field_keys


def _project_field_value(project: Project, field_key: str, field_def: Optional[CustomField]) -> Any:
    """Safely fetch a field value for sorting."""
    if field_key in ("__status__", "status"):
        return project.status
    if field_key in ("__name__", "name"):
        return project.name
    if field_key in ("__progress__", "progress"):
        try:
            # Treat projects with no tasks as missing for ordering
            if not getattr(project, "tasks", None):
                return None
        except Exception:
            return None
        try:
            return project.progress_percentage()
        except Exception:
            return 0

    value = project.get_field_value(field_key)
    # Built-in fields may also live as attributes
    if value in (None, "") and hasattr(project, field_key):
        try:
            value = getattr(project, field_key)
        except Exception:
            value = None
    return value


def _is_missing_value(value: Any) -> bool:
    """Determine if a value should be treated as missing for ordering."""
    if value is None:
        return True
    if isinstance(value, str):
        if not value.strip():
            return True
        if value.strip().lower() == "none":
            return True
    return False


def sort_projects_for_display(
    projects: List[Project],
    sort_key: Optional[str],
    all_fields: List[CustomField],
    sort_order: Optional[str] = None,
) -> List[Project]:
    """Sort projects for the browser based on a column key and order."""
    if not sort_key or not sort_order:
        return projects

    field_map = {field.key: field for field in all_fields}
    # Custom status order requested for sorting
    status_order = ["In Progress", "On Hold", "Planned", "Done"]
    status_rank = {status: idx for idx, status in enumerate(status_order)}

    def number_key(raw: Any) -> float:
        try:
            cleaned = str(raw).replace(",", "")
            return float(cleaned)
        except Exception:
            return 0.0

    def text_key(raw: Any) -> str:
        return str(raw).lower()

    def sort_key_for(project: Project, value: Any) -> Tuple:
        """Return a tuple key for sorting non-missing values."""
        field_def = field_map.get(sort_key)

        if sort_key in ("__status__", "status"):
            primary = status_rank.get(value, len(status_rank))
            return (primary, (project.name or "").lower())

        if sort_key in ("__name__", "name"):
            return (text_key(value), project.id)

        if sort_key in ("__progress__", "progress"):
            return (number_key(value), (project.name or "").lower())

        if field_def:
            if field_def.field_type == "number":
                return (number_key(value), (project.name or "").lower())
            if field_def.field_type == "single_select":
                return (text_key(value), (project.name or "").lower())
            if field_def.field_type == "date":
                return (text_key(value), (project.name or "").lower())
            return (text_key(value), (project.name or "").lower())

        return (text_key(value), (project.name or "").lower())

    reverse = sort_order == "desc"
    non_missing: List[Tuple[Project, Any]] = []
    missing: List[Tuple[Project, Any]] = []

    for project in projects:
        field_def = field_map.get(sort_key)
        value = _project_field_value(project, sort_key, field_def)
        if _is_missing_value(value):
            missing.append((project, value))
        else:
            non_missing.append((project, value))

    try:
        sorted_non_missing = sorted(
            non_missing,
            key=lambda item: sort_key_for(item[0], item[1]),
            reverse=reverse,
        )
    except Exception:
        return projects

    return [proj for proj, _ in sorted_non_missing] + [proj for proj, _ in missing]
