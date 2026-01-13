from io import StringIO

from rich.console import Console
from rich.markup import escape as rich_escape

from pm_live.render.base import BaseRenderer


class _DummyRenderer(BaseRenderer):
    def render(self, context: dict) -> str:  # pragma: no cover
        return ""


def test_wrap_with_prefix_preserves_rich_markup_integrity_when_wrapping():
    console = Console(file=StringIO(), force_terminal=True, width=50, legacy_windows=False)
    renderer = _DummyRenderer(console=console)

    escaped = rich_escape(
        "This is a long user note that contains many words and will definitely need to wrap across multiple lines when displayed"
    )
    marked = f"[color(238)]{escaped}[/color(238)]"

    wrapped = renderer.wrap_with_prefix(marked, "    ", 50)

    # If markup tags were split incorrectly, rendering would raise rich.errors.MarkupError.
    console.print(wrapped)
