"""Integration tests for core project management workflows."""

import json
import tempfile
import unittest
from pathlib import Path

from pm import Project, ProjectManager, Task


class ProjectWorkflowTests(unittest.TestCase):
    """Test complete project management workflows."""

    def setUp(self) -> None:
        """Set up temporary data file for each test."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.data_path = Path(self.tmpdir.name) / "test_projects.json"
        self.manager = ProjectManager(self.data_path)

    def tearDown(self) -> None:
        """Clean up temporary directory."""
        self.tmpdir.cleanup()

    def test_create_project_workflow(self) -> None:
        """Test creating a new project with all attributes."""
        # Create a project
        project = Project(
            id=self.manager.next_id(),
            name="Test Project",
            status="In Progress",
            tasks=[]
        )
        self.manager.add_project(project)

        # Verify project was added
        self.assertEqual(len(self.manager.projects), 1)
        saved_project = self.manager.get_project(project.id)
        self.assertIsNotNone(saved_project)
        self.assertEqual(saved_project.name, "Test Project")
        self.assertEqual(saved_project.status, "In Progress")

    def test_add_tasks_to_project(self) -> None:
        """Test adding multiple tasks to a project."""
        # Create project
        project = Project(
            id=self.manager.next_id(),
            name="Test Project",
            status="In Progress",
            tasks=[]
        )
        self.manager.add_project(project)

        # Add tasks
        project.tasks.append(Task(name="Task 1", completed=None))
        project.tasks.append(Task(name="Task 2", completed=None))
        project.tasks.append(Task(name="Task 3", completed=True))
        self.manager.update_project(project)

        # Verify tasks were added
        reloaded_project = self.manager.get_project(project.id)
        self.assertEqual(len(reloaded_project.tasks), 3)
        self.assertEqual(reloaded_project.count_total_tasks(), 3)
        self.assertEqual(reloaded_project.count_completed_tasks(), 1)

    def test_toggle_task_completion(self) -> None:
        """Test toggling task completion states."""
        # Create project with task
        project = Project(
            id=self.manager.next_id(),
            name="Test Project",
            status="In Progress",
            tasks=[Task(name="Test Task", completed=None)]
        )
        self.manager.add_project(project)

        # Toggle to completed
        project.tasks[0].completed = True
        self.manager.update_project(project)
        reloaded = self.manager.get_project(project.id)
        self.assertTrue(reloaded.tasks[0].completed)

        # Toggle to failed
        project.tasks[0].completed = False
        self.manager.update_project(project)
        reloaded = self.manager.get_project(project.id)
        self.assertFalse(reloaded.tasks[0].completed)

        # Toggle back to not started
        project.tasks[0].completed = None
        self.manager.update_project(project)
        reloaded = self.manager.get_project(project.id)
        self.assertIsNone(reloaded.tasks[0].completed)

    def test_progress_calculation(self) -> None:
        """Test that progress is calculated correctly."""
        # Create project with mixed task states
        project = Project(
            id=self.manager.next_id(),
            name="Test Project",
            status="In Progress",
            tasks=[
                Task(name="Task 1", completed=True),
                Task(name="Task 2", completed=False),
                Task(name="Task 3", completed=None),
                Task(name="Task 4", completed=True),
            ]
        )
        self.manager.add_project(project)

        # Verify progress: 3 completed out of 4 total (True and False count as completed, None doesn't)
        self.assertEqual(project.count_total_tasks(), 4)
        self.assertEqual(project.count_completed_tasks(), 3)
        self.assertEqual(project.progress_percentage(), 75)
        self.assertEqual(project.progress_str(), "3/4")

    def test_progress_invalidation_on_task_change(self) -> None:
        """Progress should update immediately when task state changes."""
        project = Project(
            id=self.manager.next_id(),
            name="Cache Project",
            status="In Progress",
            tasks=[Task(name="A", completed=None), Task(name="B", completed=None)],
        )
        self.manager.add_project(project)

        # Prime caches
        self.assertEqual(project.progress_percentage(), 0)

        # Toggle completion and ensure caches reset automatically
        project.tasks[0].completed = True
        self.assertEqual(project.count_completed_tasks(), 1)
        self.assertEqual(project.progress_percentage(), 50)

    def test_nested_tasks_progress(self) -> None:
        """Test progress calculation with nested subtasks."""
        # Create project with nested tasks
        subtask1 = Task(name="Subtask 1", completed=True)
        subtask2 = Task(name="Subtask 2", completed=None)
        main_task = Task(name="Main Task", completed=None, subtasks=[subtask1, subtask2])

        project = Project(
            id=self.manager.next_id(),
            name="Test Project",
            status="In Progress",
            tasks=[main_task]
        )
        self.manager.add_project(project)

        # Verify nested counting: 3 total (main + 2 subtasks), 1 completed
        self.assertEqual(project.count_total_tasks(), 3)
        self.assertEqual(project.count_completed_tasks(), 1)
        self.assertEqual(project.progress_percentage(), 33)  # 1/3 = 33.33%

    def test_save_and_reload_data(self) -> None:
        """Test that data persists correctly across save/load cycles."""
        # Create and save projects (get ID before each add to avoid duplicates)
        project1 = Project(
            id=self.manager.next_id(),
            name="Project 1",
            status="Done",
            tasks=[Task(name="Task 1", completed=True)]
        )
        self.manager.add_project(project1)

        project2 = Project(
            id=self.manager.next_id(),
            name="Project 2",
            status="Planned",
            tasks=[]
        )
        self.manager.add_project(project2)

        # Force save
        self.manager.force_save()

        # Create new manager to reload data
        new_manager = ProjectManager(self.data_path)

        # Verify data was reloaded correctly
        self.assertEqual(len(new_manager.projects), 2)
        # Note: Projects are sorted by ID, so get them by ID not by position
        reloaded1 = new_manager.get_project(project1.id)
        reloaded2 = new_manager.get_project(project2.id)
        self.assertIsNotNone(reloaded1)
        self.assertIsNotNone(reloaded2)

        self.assertEqual(reloaded1.name, "Project 1")
        self.assertEqual(reloaded1.status, "Done")
        self.assertEqual(len(reloaded1.tasks), 1)
        self.assertTrue(reloaded1.tasks[0].completed)

        self.assertEqual(reloaded2.name, "Project 2")
        self.assertEqual(reloaded2.status, "Planned")
        self.assertEqual(len(reloaded2.tasks), 0)

    def test_delete_project(self) -> None:
        """Test deleting a project removes it from data."""
        # Create project
        project = Project(
            id=self.manager.next_id(),
            name="To Delete",
            status="Planned",
            tasks=[]
        )
        self.manager.add_project(project)
        self.assertEqual(len(self.manager.projects), 1)

        # Delete project
        self.manager.delete_project(project.id)

        # Verify deletion
        self.assertEqual(len(self.manager.projects), 0)
        self.assertIsNone(self.manager.get_project(project.id))

    def test_update_project_status(self) -> None:
        """Test changing project status."""
        # Create project
        project = Project(
            id=self.manager.next_id(),
            name="Test Project",
            status="Planned",
            tasks=[]
        )
        self.manager.add_project(project)

        # Update status
        project.status = "In Progress"
        self.manager.update_project(project)

        # Verify update
        reloaded = self.manager.get_project(project.id)
        self.assertEqual(reloaded.status, "In Progress")

        # Update to Done
        project.status = "Done"
        self.manager.update_project(project)
        reloaded = self.manager.get_project(project.id)
        self.assertEqual(reloaded.status, "Done")


class TaskManipulationTests(unittest.TestCase):
    """Test task manipulation operations."""

    def setUp(self) -> None:
        """Set up temporary data file for each test."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.data_path = Path(self.tmpdir.name) / "test_projects.json"
        self.manager = ProjectManager(self.data_path)

    def tearDown(self) -> None:
        """Clean up temporary directory."""
        self.tmpdir.cleanup()

    def test_add_subtask(self) -> None:
        """Test adding subtasks to existing tasks."""
        # Create task with subtask
        main_task = Task(name="Main Task", completed=None)
        main_task.subtasks.append(Task(name="Subtask", completed=None))

        project = Project(
            id=self.manager.next_id(),
            name="Test Project",
            status="In Progress",
            tasks=[main_task]
        )
        self.manager.add_project(project)

        # Verify subtask structure
        reloaded = self.manager.get_project(project.id)
        self.assertEqual(len(reloaded.tasks), 1)
        self.assertEqual(len(reloaded.tasks[0].subtasks), 1)
        self.assertEqual(reloaded.tasks[0].subtasks[0].name, "Subtask")

    def test_task_priority_levels(self) -> None:
        """Test that task priority is preserved."""
        # Create tasks with different priorities
        high_task = Task(name="High Priority", priority="High")
        med_task = Task(name="Medium Priority", priority="Medium")
        low_task = Task(name="Low Priority", priority="Low")

        project = Project(
            id=self.manager.next_id(),
            name="Test Project",
            status="In Progress",
            tasks=[high_task, med_task, low_task]
        )
        self.manager.add_project(project)

        # Verify priorities
        reloaded = self.manager.get_project(project.id)
        self.assertEqual(reloaded.tasks[0].priority, "High")
        self.assertEqual(reloaded.tasks[1].priority, "Medium")
        self.assertEqual(reloaded.tasks[2].priority, "Low")


if __name__ == "__main__":
    unittest.main()
