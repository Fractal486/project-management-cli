#!/usr/bin/env python3
"""Live terminal interface for project management - Thin entry point to modular system."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from pm import ProjectManager
from pm_live import LiveCLI
from pm_live.logging_setup import configure_logging
from pm_live.config import get_config, set_config


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for the live interface."""
    parser = argparse.ArgumentParser(description="Project Manager live terminal interface.")
    parser.add_argument(
        "-d",
        "--data-file",
        dest="data_file",
        help="Path to the projects data file (overrides configuration).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    """Main entry point."""
    args = parse_args(argv)

    config = get_config().copy()
    if args.data_file:
        config.data_file_path = args.data_file

    set_config(config)

    data_file = Path(config.data_file_path).expanduser()
    configure_logging(config, base_path=data_file.parent, disable_console=True)
    manager = ProjectManager(data_file)
    cli = LiveCLI(manager)

    try:
        cli.run()
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # pragma: no cover - runtime safeguard
        print(f"Error: {exc}")
        import traceback

        traceback.print_exc()
    finally:
        manager.force_save()


if __name__ == "__main__":
    main()
