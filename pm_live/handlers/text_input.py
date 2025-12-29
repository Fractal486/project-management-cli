"""Shared text input helpers for buffer editing with a cursor."""


class TextInputBuffer:
    """Minimal cursor-aware text buffer helpers."""

    @staticmethod
    def clamp_cursor(buffer: str, cursor: int) -> int:
        """Clamp cursor to valid bounds for the current buffer."""
        return max(0, min(len(buffer), cursor))

    @staticmethod
    def move_left(buffer: str, cursor: int) -> int:
        """Move cursor left within the buffer."""
        return TextInputBuffer.clamp_cursor(buffer, cursor - 1)

    @staticmethod
    def move_right(buffer: str, cursor: int) -> int:
        """Move cursor right within the buffer."""
        return TextInputBuffer.clamp_cursor(buffer, cursor + 1)

    @staticmethod
    def insert(buffer: str, cursor: int, text: str) -> tuple[str, int]:
        """Insert text at the cursor position."""
        cursor = TextInputBuffer.clamp_cursor(buffer, cursor)
        buffer = buffer[:cursor] + text + buffer[cursor:]
        return buffer, cursor + len(text)

    @staticmethod
    def backspace(buffer: str, cursor: int) -> tuple[str, int]:
        """Delete the character before the cursor."""
        cursor = TextInputBuffer.clamp_cursor(buffer, cursor)
        if cursor <= 0:
            return buffer, cursor
        buffer = buffer[:cursor - 1] + buffer[cursor:]
        return buffer, cursor - 1

    @staticmethod
    def delete(buffer: str, cursor: int) -> tuple[str, int]:
        """Delete the character at the cursor."""
        cursor = TextInputBuffer.clamp_cursor(buffer, cursor)
        if cursor >= len(buffer):
            return buffer, cursor
        buffer = buffer[:cursor] + buffer[cursor + 1:]
        return buffer, cursor
