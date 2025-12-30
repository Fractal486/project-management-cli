# Project Management CLI Tool

A modern, full-screen terminal-based project management tool built with Python. Features a live, persistent interface with comprehensive task management, project tracking, bookmarks, and extensive customization options.

> **Note:** This entire application was vibe-coded using AI coding assistants including Claude Code, Droid, Codex CLI, and Gemini CLI.

## Features

### Core Features
- **Live Terminal Interface**: Single persistent full-screen view with no scrollback, powered by `prompt_toolkit` and `rich`
- **Projects**: Manage projects with status tracking, custom fields, progress visualization, and metadata
- **Hierarchical Tasks**: Unlimited nested subtasks with tri-state completion (☐ pending, ✓ done, ✗ failed)
- **Task Lists**: Organize tasks into named lists with sections for better structure
- **Task Metadata**: Priority levels (!, !!, !!!), deadlines, and notes for each task
- **Bookmarks**: Save and organize URLs in lists with copy/open actions
- **Calendar View**: View tasks by day of the month with deadline tracking
- **Search**: Quickly search across projects, tasks, and bookmarks
- **Statistics**: Comprehensive stats dashboard with project metrics
- **Pinning System**: Pin frequently accessed projects, tasks, and bookmarks to main menu

### Customization
- **Custom Fields**: Define project fields with multiple types:
  - Text, Number (plain/currency/percentage), Date, Single Select
  - Configurable visibility, ordering, and required status
  - Color-coded select options
- **Quick Stats**: Choose which metrics display on main menu
- **Main Menu Tabs**: Customize which tabs appear in main menu
- **Display Settings**:
  - Deadline display mode (relative days / exact dates)
  - Task metadata position (below / next to task name)
  - Notes display mode (dynamic / always visible)
  - Bookmark action mode (copy URL / open in browser)
  - Status message mode (all / errors only)
- **List Customization**: Custom colors for task lists, configurable done section display

### Data Management
- **Local Storage**: JSON-based persistence with caching for performance
- **Atomic Operations**: Safe concurrent data access with conflict detection

## Installation

1.  **Prerequisites**:
    -   Python 3.7 or higher
    -   pip

2.  **Setup**:
    ```bash
    # Install dependencies
    pip install -r requirements.txt

    # (Optional) Install development/test tooling
    pip install -r requirements-dev.txt
    ```

## Quick Start

### Launch the Application

**Windows:**
```cmd
pm live
```

**General:**
```bash
# Launch interactive interface
python pm_cli.py live
# OR
python pm_live.py
```

The live interface provides full keyboard navigation for all features. Press `H` for help within the app.

## CLI Commands

Access information quickly without launching the interactive mode:

### Basic Commands
```bash
pm live                          # Launch interactive interface (default)
pm projects                      # List all projects with progress bars
pm projects "Project Name"       # Show detailed project view (supports multi-word names)
pm tasks                         # List all tasks grouped by list
pm bookmarks                     # List bookmarks and bookmark lists
pm stats                         # Display statistics dashboard
pm pinned                        # Show all pinned items
```

### Task Management
```bash
pm add "Task name"               # Add task to default "Tasks" list
pm add "Task name" -p !!!        # Add high priority task (!, !!, or !!!)
pm add "Task name" -l "Work"     # Add task to specific list
pm day                           # Show tasks for today
pm day 15                        # Show tasks for 15th of current month
pm overdue                       # Show overdue tasks and deadlines
pm upcoming                      # Show upcoming tasks and deadlines
```

### Options
```bash
-d, --data-file <path>           # Use custom data file (overrides config)
-h, --help                       # Show help message
```

**Examples:**
```bash
# Add urgent task to work list
python pm_cli.py add "Finish quarterly report" -p !!! -l "Work"

# View specific project details
python pm_cli.py projects "Website Redesign"

# Check what's due soon
python pm_cli.py upcoming

# Use custom data file
python pm_cli.py -d ~/projects_backup.json stats
```

## Testing

-   To run all tests:
    ```bash
    python -m pytest tests/
    ```
-   To run a specific test file:
    ```bash
    python -m pytest tests/test_models.py
    ```

## Configuration

Configuration is managed via `.pm_config.toml` with environment variable overrides.

### Configuration File (`.pm_config.toml`)

```toml
# Display settings
console_width = 120
deadline_display_mode = "relative"     # or "date"
task_metadata_position = "below"       # or "next_to"
notes_display_mode = "dynamic"         # or "always"

# Data file
data_file_path = "projects.json"

# Bookmarks
bookmark_action_mode = "copy"          # or "open"

# UI preferences
show_none_in_stats = true              # Show/hide "none" values in stats
status_message_mode = "all"            # or "errors_only"

# Logging
enable_file_logging = true
log_level_console = "INFO"
log_level_file = "DEBUG"
log_file_path = "pm_app.log"
```

### Environment Variables

Override any config value with `PM_<KEY>` environment variables:
```bash
export PM_DATA_FILE_PATH="~/my_projects.json"
export PM_DEADLINE_DISPLAY_MODE="relative"
export PM_BOOKMARK_ACTION_MODE="copy"
```

## Code Architecture

### Core Structure
```
project-management-cli/
├── pm.py                      # Core data models (Task, Project, ProjectManager)
├── pm_cli.py                  # CLI dispatcher with subcommands
├── pm_live.py                 # Entry point for live mode
├── start.py                   # Main launcher script
├── pm_live/                   # Live UI package
│   ├── app.py                 # Main application controller
│   ├── states.py              # Application state machine
│   ├── ui_state.py            # UI state management
│   ├── config.py              # Configuration management
│   ├── keybindings.py         # Keyboard input handling
│   ├── custom_fields.py       # Custom field definitions
│   ├── quick_stats.py         # Quick stats configuration
│   ├── handlers/              # Event handlers
│   │   ├── key_handlers.py    # Keyboard event routing
│   │   ├── enter_handlers.py  # Enter key actions
│   │   ├── task_handlers.py   # Task operations
│   │   └── bookmark_handlers.py # Bookmark operations
│   ├── render/                # Screen renderers
│   │   ├── main_menu.py       # Main menu
│   │   ├── project_browser.py # Project list
│   │   ├── project_details.py # Project detail view
│   │   ├── task_list.py       # Task list view
│   │   ├── bookmarks.py       # Bookmark views
│   │   ├── calendar.py        # Calendar view
│   │   ├── statistics.py      # Statistics dashboard
│   │   ├── search.py          # Search interface
│   │   └── settings.py        # Settings screens
│   └── utils/                 # Utility modules
├── tests/                     # Test suite (pytest)
├── .pm_config.toml            # User configuration
├── projects.json              # Data storage (auto-created)
└── requirements.txt           # Python dependencies
```

### Architecture Patterns
- **State Machine**: Application uses explicit state machine with defined screens
- **Handler Pattern**: Specialized handlers for keyboard input and actions
- **Renderer Pattern**: Pure rendering functions that read UI state
- **Data Layer**: `ProjectManager` handles all persistence and caching


## License

MIT
