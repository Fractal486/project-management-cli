import unittest

from pm import Project, Task


class TaskModelTests(unittest.TestCase):
    def test_counts_include_nested_subtasks(self) -> None:
        deep_child = Task(name="Deep", completed=True)
        child_1 = Task(name="Child 1", completed=True)
        child_2 = Task(name="Child 2", completed=False, subtasks=[deep_child])
        root = Task(name="Root", completed=None, subtasks=[child_1, child_2])

        self.assertEqual(root.count_total(), 4)
        self.assertEqual(root.count_completed(), 3)  # Now includes both True and False (only None doesn't count)

    def test_to_dict_omits_none_completed(self) -> None:
        task = Task(name="Sample", completed=None)
        payload = task.to_dict()

        self.assertNotIn("completed", payload)
        self.assertEqual(payload["name"], "Sample")


class ProjectModelTests(unittest.TestCase):
    def test_progress_calculations(self) -> None:
        tasks = [
            Task(name="A", completed=True),
            Task(name="B", completed=False),
            Task(name="C", completed=None),
        ]
        project = Project(
            id=1,
            name="Demo",
            status="In Progress",
            tasks=tasks,
        )

        self.assertEqual(project.count_total_tasks(), 3)
        self.assertEqual(project.count_completed_tasks(), 2)  # Now includes both True and False (only None doesn't count)
        self.assertEqual(project.progress_str(), "2/3")
        self.assertEqual(project.progress_percentage(), 66)  # 2/3 = 66.666... which rounds down to 66


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

