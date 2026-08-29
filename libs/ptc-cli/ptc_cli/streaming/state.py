"""Streaming state management for CLI output."""

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

# Reasoning buffer settings - use character count since SSE events arrive in batches
REASONING_BUFFER_CHARS = 400  # buffer first N chars, then stream the rest


class StreamingState:
    """Manages streaming output state (spinner, text buffer, response tracking)."""

    def __init__(self, console: "Console", status_message: str, colors: Mapping[str, str]) -> None:
        """Initialize streaming state.

        Args:
            console: Rich console instance for output
            status_message: Initial status message for spinner
            colors: Color configuration dictionary
        """
        self.has_responded = False
        self.pending_text = ""
        self._console = console
        self._colors = colors
        self._status = console.status(status_message, spinner="dots")
        self._status.start()
        self._spinner_active = True

        # Reasoning buffer state
        self._reasoning_buffer = ""
        self._reasoning_buffering = False
        self._reasoning_header_shown = False

    @property
    def spinner_active(self) -> bool:
        """Check if spinner is currently active.

        Returns:
            True if spinner is active, False otherwise
        """
        return self._spinner_active

    def stop_spinner(self) -> None:
        """Stop the spinner if it's currently active."""
        if self._spinner_active:
            self._status.stop()
            self._spinner_active = False

    def start_spinner(self) -> None:
        """Start the spinner if it's currently inactive."""
        if not self._spinner_active:
            self._status.start()
            self._spinner_active = True

    def update_spinner(self, message: str) -> None:
        """Update the spinner message.

        Args:
            message: New status message to display
        """
        self._status.update(message)

    def flush_text(self, *, final: bool = False) -> None:
        """Finalize text output (add newline after streamed content).

        Args:
            final: If True, finalize the text output
        """
        if not final:
            return

        if self._spinner_active:
            self.stop_spinner()

        # Text was already streamed, just add newline if there was content
        if self.pending_text.strip():
            self._console.print()  # Add newline after streamed content

        self.pending_text = ""

    def append_text(self, text: str) -> None:
        """Stream text token directly to output.

        Args:
            text: Text to stream
        """
        if self._spinner_active:
            self.stop_spinner()

        # Show response marker on first text
        if not self.has_responded:
            self._console.print("●", style=self._colors["agent"], markup=False, end=" ")
            self.has_responded = True

        # Stream text directly
        self._console.print(text, end="", style=self._colors["agent"], markup=False)
        if hasattr(self._console.file, 'flush'):
            self._console.file.flush()

        # Also accumulate for any final markdown rendering if needed
        self.pending_text += text

    def start_reasoning(self) -> None:
        """Start reasoning mode with buffering."""
        self._reasoning_buffer = ""
        self._reasoning_buffering = True
        self._reasoning_header_shown = False

        # Show reasoning animation
        self._status.update(f"[bold {self._colors['thinking']}]Reasoning...")
        if not self._spinner_active:
            self._status.start()
            self._spinner_active = True

    def append_reasoning(self, text: str) -> None:
        """Append reasoning token, buffering initially then streaming.

        Buffers first REASONING_BUFFER_CHARS characters, then streams the rest.
        This works better than time-based buffering since SSE events arrive in batches.

        Args:
            text: Reasoning text to append
        """
        if not self._reasoning_buffering and not self._reasoning_header_shown:
            # First reasoning token - start buffering
            self.start_reasoning()

        if self._reasoning_buffering:
            # Still in buffer phase - accumulate
            self._reasoning_buffer += text

            # Check if buffer is full
            if len(self._reasoning_buffer) >= REASONING_BUFFER_CHARS:
                # Buffer full - flush and switch to streaming mode
                self._flush_reasoning_buffer()
                self._reasoning_buffering = False
        else:
            # Streaming mode - output directly
            self._console.print(f"[dim italic magenta]{text}[/dim italic magenta]", end="")
            if hasattr(self._console.file, 'flush'):
                self._console.file.flush()

    def _flush_reasoning_buffer(self) -> None:
        """Flush accumulated reasoning buffer to display."""
        if self._spinner_active:
            self.stop_spinner()

        if not self._reasoning_header_shown:
            self._console.print()
            self._console.print(f"[magenta dim]Thinking:[/magenta dim]")
            self._reasoning_header_shown = True

        if self._reasoning_buffer:
            self._console.print(f"[dim italic magenta]{self._reasoning_buffer}[/dim italic magenta]", end="")
            if hasattr(self._console.file, 'flush'):
                self._console.file.flush()
            self._reasoning_buffer = ""

    def end_reasoning(self) -> None:
        """End reasoning mode, flush any remaining buffer."""
        # Flush any remaining buffered content
        if self._reasoning_buffer:
            self._flush_reasoning_buffer()

        if self._spinner_active:
            self.stop_spinner()

        # Add newline after reasoning content if we showed any
        if self._reasoning_header_shown:
            self._console.print()
            self._console.print()

        # Reset reasoning state
        self._reasoning_buffer = ""
        self._reasoning_buffering = False
        self._reasoning_header_shown = False
