"""Search functionality for the live CLI."""

from typing import List, Dict, Any, Optional


def perform_search(manager, query: str) -> List[Dict[str, Any]]:
    """Search across projects, tasks, and bookmarks.

    Args:
        manager: ProjectManager instance
        query: Search query string (case-insensitive)

    Returns:
        List of search results, each with:
        - type: "project", "task", or "bookmark"
        - name: Display name
        - id: Reference ID
        - project_id: For tasks, the parent project ID (optional)
        - project_name: For tasks, the parent project name (optional)
        - list_name: For standalone tasks, the list name (optional)
        - match_field: Which field matched (e.g., "name", "notes", "url")
    """
    if not query or not query.strip():
        return []

    query_lower = query.lower().strip()
    results = []

    # Search projects
    for project in manager.projects:
        # Search project name
        if query_lower in project.name.lower():
            results.append({
                "type": "project",
                "name": project.name,
                "id": project.id,
                "match_field": "name",
                "status": project.status,
            })
            continue

        # Search custom fields (all types converted to string)
        custom_fields = getattr(project, 'custom_field_values', None)
        if custom_fields is None:
            custom_fields = getattr(project, 'custom_fields', {})
        if custom_fields:
            for field_key, field_value in custom_fields.items():
                if field_value is not None:
                    field_value_str = str(field_value).lower()
                    if query_lower in field_value_str:
                        results.append({
                            "type": "project",
                            "name": project.name,
                            "id": project.id,
                            "match_field": field_key,
                            "status": project.status,
                        })
                        break

    # Search tasks in projects
    for project in manager.projects:
        _search_tasks_recursive(
            project.tasks,
            query_lower,
            results,
            project_id=project.id,
            project_name=project.name
        )

    # Search standalone tasks (in lists)
    list_tasks = getattr(manager, 'list_tasks', {})
    for list_name, sections in list_tasks.items():
        for section in sections:
            tasks = getattr(section, 'tasks', [])
            _search_tasks_recursive(
                tasks,
                query_lower,
                results,
                list_name=list_name
            )

    # Search bookmarks and bookmark lists
    # Both are stored in manager.bookmarks together
    bookmarks = getattr(manager, 'bookmarks', [])
    for item in bookmarks:
        # Check if this is a BookmarkList (has 'items' attribute)
        if hasattr(item, 'items'):
            # This is a BookmarkList
            title = getattr(item, 'title', '')
            list_id = getattr(item, 'id', None)
            bookmarks_in_list = getattr(item, 'items', [])

            # Search list title
            if title and query_lower in title.lower():
                results.append({
                    "type": "bookmark_list",
                    "name": title,
                    "id": list_id,
                    "match_field": "title",
                    "bookmark_count": len(bookmarks_in_list),
                })

            # Search bookmarks within the list
            for bookmark in bookmarks_in_list:
                bookmark_title = getattr(bookmark, 'title', '')
                bookmark_url = getattr(bookmark, 'url', '')
                bookmark_id = getattr(bookmark, 'id', None)

                # Search bookmark title
                if bookmark_title and query_lower in bookmark_title.lower():
                    results.append({
                        "type": "bookmark",
                        "name": bookmark_title,
                        "id": bookmark_id,
                        "url": bookmark_url,
                        "match_field": "title",
                        "list_id": list_id,
                        "list_name": title,
                    })
                    continue

                # Search bookmark URL
                if bookmark_url and query_lower in bookmark_url.lower():
                    results.append({
                        "type": "bookmark",
                        "name": bookmark_title,
                        "id": bookmark_id,
                        "url": bookmark_url,
                        "match_field": "url",
                        "list_id": list_id,
                        "list_name": title,
                    })
        else:
            # This is a standalone Bookmark
            title = getattr(item, 'title', '')
            url = getattr(item, 'url', '')
            bookmark_id = getattr(item, 'id', None)

            # Search bookmark title
            if title and query_lower in title.lower():
                results.append({
                    "type": "bookmark",
                    "name": title,
                    "id": bookmark_id or url,  # Use ID if available, otherwise URL
                    "url": url,
                    "match_field": "title",
                })
                continue

            # Search bookmark URL
            if url and query_lower in url.lower():
                results.append({
                    "type": "bookmark",
                    "name": title,
                    "id": bookmark_id or url,
                    "url": url,
                    "match_field": "url",
                })

    return results


def _search_tasks_recursive(
    tasks: List,
    query_lower: str,
    results: List[Dict[str, Any]],
    project_id: Optional[int] = None,
    project_name: Optional[str] = None,
    list_name: Optional[str] = None,
    parent_path: str = ""
) -> None:
    """Recursively search through tasks and subtasks.

    Args:
        tasks: List of Task objects
        query_lower: Lowercase search query
        results: Results list to append to
        project_id: Parent project ID (if task is in a project)
        project_name: Parent project name (if task is in a project)
        list_name: List name (if task is standalone)
        parent_path: Dot-separated path of parent tasks
    """
    for task in tasks:
        task_name = getattr(task, 'name', '')
        task_notes = getattr(task, 'notes', None)
        task_path = f"{parent_path}.{task_name}" if parent_path else task_name

        matched = False
        match_field = "name"

        # Search task name
        if query_lower in task_name.lower():
            matched = True
            match_field = "name"
        # Search task notes
        elif task_notes and query_lower in task_notes.lower():
            matched = True
            match_field = "notes"

        if matched:
            result = {
                "type": "task",
                "name": task_name,
                "id": task_path,  # Use path as ID for navigation
                "match_field": match_field,
                "completed": getattr(task, 'completed', None),
                "priority": getattr(task, 'priority', None),
                "deadline": getattr(task, 'deadline', None),
            }

            if project_id is not None:
                result["project_id"] = project_id
                result["project_name"] = project_name
            elif list_name:
                result["list_name"] = list_name

            results.append(result)

        # Search subtasks recursively
        subtasks = getattr(task, 'subtasks', [])
        if subtasks:
            _search_tasks_recursive(
                subtasks,
                query_lower,
                results,
                project_id=project_id,
                project_name=project_name,
                list_name=list_name,
                parent_path=task_path
            )
