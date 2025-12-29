"""Tests for deeply nested task hierarchies and edge cases."""

import tempfile
import unittest
from pathlib import Path

from pm import Project, ProjectManager, Task


class DeepNestingTests(unittest.TestCase):
    """Test deeply nested task structures."""

    def setUp(self) -> None:
        """Set up temporary data file for each test."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.data_path = Path(self.tmpdir.name) / "test_projects.json"
        self.manager = ProjectManager(self.data_path)

    def tearDown(self) -> None:
        """Clean up temporary directory."""
        self.tmpdir.cleanup()

    def test_deeply_nested_tasks_10_levels(self) -> None:
        """Test that 10+ levels of nesting works correctly."""
        # Create deeply nested task structure
        level_10 = Task(name="Level 10", completed=True)
        level_9 = Task(name="Level 9", completed=None, subtasks=[level_10])
        level_8 = Task(name="Level 8", completed=False, subtasks=[level_9])
        level_7 = Task(name="Level 7", completed=None, subtasks=[level_8])
        level_6 = Task(name="Level 6", completed=True, subtasks=[level_7])
        level_5 = Task(name="Level 5", completed=None, subtasks=[level_6])
        level_4 = Task(name="Level 4", completed=False, subtasks=[level_5])
        level_3 = Task(name="Level 3", completed=None, subtasks=[level_4])
        level_2 = Task(name="Level 2", completed=True, subtasks=[level_3])
        level_1 = Task(name="Level 1", completed=None, subtasks=[level_2])

        project = Project(
            id=self.manager.next_id(),
            name="Deep Nesting Test",
            status="In Progress",
            tasks=[level_1]
        )
        self.manager.add_project(project)

        # Verify counts work correctly with deep nesting
        self.assertEqual(project.count_total_tasks(), 10)
        # Completed: levels 10, 8, 6, 4, 2 = 5 tasks
        self.assertEqual(project.count_completed_tasks(), 5)
        self.assertEqual(project.progress_percentage(), 50)

        # Verify it persists and reloads correctly
        self.manager.force_save()
        new_manager = ProjectManager(self.data_path)
        reloaded = new_manager.get_project(project.id)

        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.count_total_tasks(), 10)
        self.assertEqual(reloaded.count_completed_tasks(), 5)

    def test_very_deeply_nested_tasks_20_levels(self) -> None:
        """Test extreme nesting (20 levels) to ensure no stack overflow."""
        # Create 20 levels of nesting
        task = Task(name="Level 20", completed=True)
        for level in range(19, 0, -1):
            task = Task(name=f"Level {level}", completed=None, subtasks=[task])

        project = Project(
            id=self.manager.next_id(),
            name="Extreme Nesting Test",
            status="In Progress",
            tasks=[task]
        )
        self.manager.add_project(project)

        # Verify counts work without recursion errors
        total = project.count_total_tasks()
        self.assertEqual(total, 20)

        # Verify saving and loading works
        self.manager.force_save()
        new_manager = ProjectManager(self.data_path)
        reloaded = new_manager.get_project(project.id)

        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.count_total_tasks(), 20)

    def test_empty_project_list_navigation(self) -> None:
        """Test navigation with no projects."""
        # Manager starts with empty project list
        self.assertEqual(len(self.manager.projects), 0)

        # Verify no crashes when accessing empty list
        projects = self.manager.projects
        self.assertIsInstance(projects, list)
        self.assertEqual(len(projects), 0)

    def test_single_item_list_bounds(self) -> None:
        """Test bounds checking with single item lists."""
        project = Project(
            id=self.manager.next_id(),
            name="Single Project",
            status="Planned",
            tasks=[]
        )
        self.manager.add_project(project)

        # Only one project, index should be 0
        self.assertEqual(len(self.manager.projects), 1)
        retrieved = self.manager.get_project(project.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Single Project")

    def test_task_with_no_subtasks(self) -> None:
        """Test tasks without subtasks."""
        task = Task(name="Simple Task", completed=None)

        project = Project(
            id=self.manager.next_id(),
            name="Simple Project",
            status="In Progress",
            tasks=[task]
        )
        self.manager.add_project(project)

        # Verify counts
        self.assertEqual(project.count_total_tasks(), 1)
        self.assertEqual(project.count_completed_tasks(), 0)
        self.assertEqual(task.subtasks, [])

    def test_mixed_depth_hierarchy(self) -> None:
        """Test tasks with varying depths in same project."""
        # Task 1: No subtasks
        task1 = Task(name="Task 1", completed=True)

        # Task 2: 1 level of subtasks
        task2_sub = Task(name="Task 2.1", completed=False)
        task2 = Task(name="Task 2", completed=None, subtasks=[task2_sub])

        # Task 3: 3 levels of subtasks
        task3_sub_sub = Task(name="Task 3.1.1", completed=True)
        task3_sub = Task(name="Task 3.1", completed=None, subtasks=[task3_sub_sub])
        task3 = Task(name="Task 3", completed=False, subtasks=[task3_sub])

        project = Project(
            id=self.manager.next_id(),
            name="Mixed Depth Project",
            status="In Progress",
            tasks=[task1, task2, task3]
        )
        self.manager.add_project(project)

        # Verify counts: 1 + (1+1) + (1+1+1) = 6 total tasks
        self.assertEqual(project.count_total_tasks(), 6)
        # Completed: task1(True), task2_sub(False), task3(False), task3_sub_sub(True) = 4
        self.assertEqual(project.count_completed_tasks(), 4)


class EdgeCaseTests(unittest.TestCase):
    """Test edge cases and defensive programming."""

    def setUp(self) -> None:
        """Set up temporary data file for each test."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.data_path = Path(self.tmpdir.name) / "test_projects.json"
        self.manager = ProjectManager(self.data_path)

    def tearDown(self) -> None:
        """Clean up temporary directory."""
        self.tmpdir.cleanup()

    def test_get_nonexistent_project(self) -> None:
        """Test getting a project that doesn't exist returns None."""
        result = self.manager.get_project(999999)
        self.assertIsNone(result)

    def test_update_nonexistent_project(self) -> None:
        """Test updating a project that doesn't exist raises error."""
        fake_project = Project(
            id=999999,
            name="Ghost",
            status="Planned",
            tasks=[]
        )

        with self.assertRaises(ValueError):
            self.manager.update_project(fake_project)

    def test_delete_nonexistent_project(self) -> None:
        """Test deleting a project that doesn't exist."""
        # Should not crash, just do nothing
        initial_count = len(self.manager.projects)
        self.manager.delete_project(999999)
        self.assertEqual(len(self.manager.projects), initial_count)

    def test_project_with_empty_tasks_list(self) -> None:
        """Test project with no tasks."""
        project = Project(
            id=self.manager.next_id(),
            name="Empty Project",
            status="Planned",
            tasks=[]
        )
        self.manager.add_project(project)

        self.assertEqual(project.count_total_tasks(), 0)
        self.assertEqual(project.count_completed_tasks(), 0)
        self.assertEqual(project.progress_percentage(), 0)
        # When there are no tasks, progress_str() returns "No tasks"
        self.assertEqual(project.progress_str(), "No tasks")


if __name__ == "__main__":
    unittest.main()
