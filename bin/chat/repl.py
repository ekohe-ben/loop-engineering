#!/usr/bin/env python3
"""REPL interface for chat mode - interactive chat with session management
and backend switching. See design PDF section 8."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chat.assembler import AssemblerConfig, ContextAssembler
from chat.backends import get_backend
from chat.session import SessionManager
from chat.summarizer import Summarizer


class ChatREPL:
    """Interactive REPL for chat mode."""

    def __init__(self, sessions_root: str | None = None, sandbox_dir: str | None = None):
        """Initialize REPL.
        
        Args:
            sessions_root: Root directory for sessions (defaults to ~/.loop-engineering/sessions/)
            sandbox_dir: Sandbox directory for chat mode (defaults to ~/.loop-engineering/chat-sandbox/)
        """
        self.session_mgr = SessionManager(sessions_root)
        
        # Sandbox directory for chat mode (no access to real files)
        if sandbox_dir is None:
            home = Path(os.environ.get("LOOP_ENGINEERING_HOME",
                                      str(Path.home() / ".loop-engineering")))
            sandbox_dir = home / "chat-sandbox"
        
        self.sandbox_dir = Path(sandbox_dir)
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        
        self.assembler = ContextAssembler()
        self.summarizer = Summarizer()
        
        # Current session state
        self.current_session = None
        self.current_backend = None

    def start(self, session_id: str | None = None):
        """Start REPL loop.
        
        Args:
            session_id: Existing session to open, or None to list sessions
        """
        if session_id is None:
            # List recent sessions and prompt for selection or new
            print("Loop X Chat Mode")
            print("=" * 50)
            self._show_session_list()
            return
        
        try:
            # Open existing session
            meta = self.session_mgr.open_session(session_id)
            self.current_session = meta
            self.current_backend = get_backend(meta.active_seat)
            print(f"\nOpened session: {meta.title}")
            print(f"Mode: {meta.mode} | Seat: {meta.active_seat}")
        except FileNotFoundError:
            # Create new session with this as title
            print(f"\nCreating new session: {session_id}")
            meta = self.session_mgr.create_session(session_id)
            self.current_session = meta
            self.current_backend = get_backend(meta.active_seat)
        
        # Show current transcript summary
        transcript = self.session_mgr.read_transcript(meta.id)
        print(f"Messages in transcript: {len(transcript)}")
        print()
        
        # Start REPL loop
        self._repl_loop()

    def _show_session_list(self):
        """Show recent sessions and prompt for action."""
        sessions = self.session_mgr.list_sessions(limit=10)
        
        if sessions:
            print("\nRecent sessions:")
            for i, meta in enumerate(sessions, 1):
                print(f"  {i}. {meta.title} ({meta.id}) - {meta.active_seat}, {len(self.session_mgr.read_transcript(meta.id))} messages")
        else:
            print("\nNo existing sessions.")
        
        print("\nUsage:")
        print("  le chat <session-id>  - Open existing session or create new")
        print("  le chat <title>       - Create new session with this title")

    def _repl_loop(self):
        """Main REPL loop."""
        print("Type your message, or /help for commands")
        print("-" * 50)
        
        while True:
            try:
                # Read user input
                user_input = input(f"[{self.current_session.mode}] > ").strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.startswith("/"):
                    if not self._handle_command(user_input):
                        break  # /end command
                    continue
                
                # Process chat message
                self._handle_message(user_input)
                
            except (KeyboardInterrupt, EOFError):
                print("\n")
                self._end_session()
                break

    def _handle_command(self, cmd: str) -> bool:
        """Handle REPL commands. Returns False to exit.
        
        Args:
            cmd: Command string starting with '/'
            
        Returns:
            True to continue REPL, False to exit
        """
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else None
        
        if command == "/help":
            self._show_help()
        
        elif command == "/seat":
            if not arg:
                print(f"Current seat: {self.current_session.active_seat}")
                print("Available: claude, agy")
                print("Usage: /seat <backend>")
            else:
                self._switch_seat(arg)
        
        elif command == "/mode":
            if not arg:
                print(f"Current mode: {self.current_session.mode}")
                print("Usage: /mode <chat|task>")
            else:
                self._switch_mode(arg)
        
        elif command == "/replay":
            print("Forcing replay with current context...")
            # Clear native session to force replay on next message
            self.session_mgr.update_seat(self.current_session.id, 
                                         self.current_session.active_seat,
                                         native_id=None)
            print("Next message will use full context replay.")
        
        elif command == "/summary":
            self._show_summary()
        
        elif command == "/end":
            self._end_session()
            return False
        
        else:
            print(f"Unknown command: {command}")
            print("Type /help for available commands")
        
        return True

    def _show_help(self):
        """Show help message."""
        print("""
Available commands:
  /seat [backend]  - Show or switch backend (claude, agy)
  /mode [mode]     - Show or switch mode (chat, task)
  /replay          - Force full context replay on next message
  /summary         - Show or generate summary
  /end             - End session and exit
  /help            - Show this help
""")

    def _switch_seat(self, seat: str):
        """Switch to a different backend.
        
        Args:
            seat: Backend name ('claude', 'agy', etc.)
        """
        try:
            backend = get_backend(seat)
            self.current_backend = backend
            # Clear native_id when switching seats (forces replay)
            self.session_mgr.update_seat(self.current_session.id, seat, native_id=None)
            self.current_session.active_seat = seat
            print(f"Switched to {seat}")
            print("Next message will replay full context with new backend.")
        except ValueError as e:
            print(f"Error: {e}")

    def _switch_mode(self, mode: str):
        """Switch between chat and task mode.
        
        Args:
            mode: 'chat' or 'task'
        """
        if mode not in ("chat", "task"):
            print("Mode must be 'chat' or 'task'")
            return
        
        self.session_mgr.update_mode(self.current_session.id, mode)
        self.current_session.mode = mode
        print(f"Switched to {mode} mode")
        
        if mode == "task":
            print("⚠️  Task mode enables file/shell tools - use with caution!")

    def _show_summary(self):
        """Show or generate summary."""
        summary_path = self.session_mgr.sessions_root / self.current_session.id / "summary.md"
        
        if summary_path.exists():
            with open(summary_path) as f:
                summary = f.read()
            print(f"\nCurrent summary:\n{summary}\n")
        else:
            print("\nNo summary yet. Summarizer is Phase 2 - will be implemented in next iteration.")
            print("For long conversations (>20 turns), summary helps reduce replay cost.")

    def _end_session(self):
        """End current session and clean up."""
        if self.current_session:
            print(f"\nSession ended: {self.current_session.title}")
            print(f"Transcript saved at: {self.session_mgr.sessions_root / self.current_session.id}")

    def _handle_message(self, user_input: str):
        """Process a chat message.
        
        Args:
            user_input: User's message text
        """
        # Determine if we can use native resume or need full replay
        # Check BEFORE appending user message (don't store if CLI fails)
        native_id = self.session_mgr.get_native_id(
            self.current_session.id,
            self.current_backend.name
        )
        
        transcript = self.session_mgr.read_transcript(self.current_session.id)
        is_first_message = len(transcript) == 0  # No messages yet
        
        # Try native resume first if available
        response = None
        if native_id and not is_first_message:
            print(f"[Resuming with {self.current_backend.name}...]")
            response = self.current_backend.resume(
                native_id=native_id,
                prompt=user_input,
                mode=self.current_session.mode,
                cwd=str(self.sandbox_dir),
            )
        
        # Fall back to full replay if resume failed or unavailable
        if response is None:
            print(f"[Invoking {self.current_backend.name} with full context...]")
            
            # Load summary if available
            summary = self.summarizer.load_summary(
                self.session_mgr.sessions_root / self.current_session.id
            )
            
            # Get recent messages
            recent_messages = [
                (entry.role, entry.text)
                for entry in transcript[:-1]  # Exclude the user message we just added
            ]
            
            # Assemble replay package
            replay = self.assembler.assemble_replay(
                summary=summary,
                recent_messages=recent_messages,
                current_input=user_input,
                is_continuation=(not is_first_message),
            )
            
            # Invoke backend
            response = self.current_backend.invoke(
                prompt=replay.prompt,
                mode=self.current_session.mode,
                cwd=str(self.sandbox_dir),
            )
        
        if response is None:
            print("Error: Failed to get response from backend")
            return
        
        # Display response
        print(f"\n{response.text}\n")
        
        # Only NOW append both user and assistant messages to transcript
        # (CLI succeeded, safe to persist)
        self.session_mgr.append_message(
            self.current_session.id,
            role="user",
            text=user_input,
        )
        
        # Append assistant message to transcript
        self.session_mgr.append_message(
            self.current_session.id,
            role="assistant",
            text=response.text,
            seat=self.current_backend.name,
            native_id=response.native_id,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
        )
        
        # Update native session ID if provided
        if response.native_id:
            self.session_mgr.update_seat(
                self.current_session.id,
                self.current_backend.name,
                native_id=response.native_id,
            )


def main():
    """CLI entry point for chat REPL."""
    import sys
    
    if len(sys.argv) < 2:
        # No session ID - show list
        repl = ChatREPL()
        repl.start()
    else:
        # Open/create session
        session_id = sys.argv[1]
        repl = ChatREPL()
        repl.start(session_id)


if __name__ == "__main__":
    main()
