import errno
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pm import Project, ProjectManager, Task, fresh_default_data


class ProjectManagerPersistenceTests(unittest.TestCase):
    def test_initializes_default_structure_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "projects.json"
            manager = ProjectManager(data_path)

            self.assertTrue(data_path.exists())
            self.assertEqual(manager.projects, [])
            self.assertIn("version", manager.metadata)

    def test_recovers_from_corrupt_file_and_creates_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "projects.json"
            data_path.write_text("{not-json", encoding="utf-8")

            manager = ProjectManager(data_path)

            self.assertEqual(manager.projects, [])
            backup = data_path.with_name("projects.json.corrupt")
            self.assertTrue(backup.exists())
            self.assertIn("recoveryNote", manager.metadata)

    def test_update_project_replaces_existing_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "projects.json"
            data = fresh_default_data()
            data["projects"] = [
                {
                    "id": 1,
                    "name": "Original",
                    "status": "Planned",
                    "tasks": [],
                }
            ]
            data_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

            manager = ProjectManager(data_path)
            project = manager.get_project(1)
            assert project is not None
            project.name = "Updated"
            manager.update_project(project)

            reloaded = json.loads(data_path.read_text(encoding="utf-8"))
            self.assertEqual(reloaded["projects"][0]["name"], "Updated")

    def test_update_project_raises_for_unknown_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "projects.json"
            manager = ProjectManager(data_path)

            ghost = Project(
                id=999,
                name="Ghost",
                status="Planned",
                tasks=[],
            )

            with self.assertRaises(ValueError):
                manager.update_project(ghost)

    def test_save_handles_permission_error_with_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "projects.json"
            manager = ProjectManager(data_path)
            manager.standalone_tasks.append(Task(name="Blocked"))
            manager._dirty = True

            original_write = Path.write_text

            def fake_write_text(self, *args, **kwargs):
                if self.name.endswith(".tmp"):
                    raise PermissionError("Permission denied")
                return original_write(self, *args, **kwargs)

            with mock.patch("pathlib.Path.write_text", new=fake_write_text):
                success = manager.save()

            self.assertFalse(success)
            self.assertIsNotNone(manager.last_autosave_path)
            assert manager.last_autosave_path is not None
            self.assertTrue(manager.last_autosave_path.exists())
            self.assertIn("permission denied", manager.last_error_message.lower())
            self.assertTrue(manager._dirty)

            # Clean up generated fallback file
            manager.last_autosave_path.unlink(missing_ok=True)

    def test_save_handles_disk_full_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "projects.json"
            manager = ProjectManager(data_path)
            manager.standalone_tasks.append(Task(name="Big"))
            manager._dirty = True

            original_write = Path.write_text

            def fake_write_text(self, *args, **kwargs):
                if self.name.endswith(".tmp"):
                    raise OSError(errno.ENOSPC, "No space left on device")
                return original_write(self, *args, **kwargs)

            with mock.patch("pathlib.Path.write_text", new=fake_write_text):
                success = manager.save()

            self.assertFalse(success)
            self.assertIsNotNone(manager.last_autosave_path)
            assert manager.last_autosave_path is not None
            self.assertTrue(manager.last_autosave_path.exists())
            self.assertIn("disk is full", manager.last_error_message.lower())
            self.assertTrue(manager._dirty)

            manager.last_autosave_path.unlink(missing_ok=True)

    def test_load_handles_read_failure_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "projects.json"

            original_read = Path.read_text

            def fake_read_text(self, *args, **kwargs):
                if self == data_path:
                    raise PermissionError("File is locked")
                return original_read(self, *args, **kwargs)

            with mock.patch("pathlib.Path.read_text", new=fake_read_text):
                manager = ProjectManager(data_path)

            self.assertEqual(manager.projects, [])
            self.assertIsNotNone(manager.last_error_message)
            assert manager.last_error_message is not None
            self.assertIn("cannot load data", manager.last_error_message.lower())


class ProjectManagerPinnedItemRemovalTests(unittest.TestCase):
    def test_remove_pinned_section_with_empty_criteria_removes_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "projects.json"
            manager = ProjectManager(data_path)
            manager.metadata["pinned_items"] = [
                {"type": "section", "id": "sec1", "list_name": "Work", "section_idx": 0},
                {"type": "section", "id": "sec2", "list_name": "Home", "section_idx": 1},
                {"type": "task", "id": "task1"},
            ]
            manager._dirty = False

            manager.remove_pinned_item("section", {})

            self.assertEqual(
                manager.metadata["pinned_items"],
                [
                    {"type": "section", "id": "sec1", "list_name": "Work", "section_idx": 0},
                    {"type": "section", "id": "sec2", "list_name": "Home", "section_idx": 1},
                    {"type": "task", "id": "task1"},
                ],
            )
            self.assertFalse(manager._dirty)

            manager.remove_pinned_item("section", {"list_name": None})
            self.assertEqual(
                manager.metadata["pinned_items"],
                [
                    {"type": "section", "id": "sec1", "list_name": "Work", "section_idx": 0},
                    {"type": "section", "id": "sec2", "list_name": "Home", "section_idx": 1},
                    {"type": "task", "id": "task1"},
                ],
            )
            self.assertFalse(manager._dirty)

    def test_remove_pinned_section_by_list_name_removes_matching_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "projects.json"
            manager = ProjectManager(data_path)
            manager.metadata["pinned_items"] = [
                {"type": "section", "id": "sec1", "list_name": "Work", "section_idx": 0},
                {"type": "section", "id": "sec2", "list_name": "Home", "section_idx": 1},
                {"type": "task", "id": "task1"},
            ]
            manager._dirty = False

            manager.remove_pinned_item("section", {"list_name": "Work"})

            self.assertEqual(
                manager.metadata["pinned_items"],
                [
                    {"type": "section", "id": "sec2", "list_name": "Home", "section_idx": 1},
                    {"type": "task", "id": "task1"},
                ],
            )
            self.assertTrue(manager._dirty)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

