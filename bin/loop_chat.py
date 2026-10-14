#!/usr/bin/env python3
"""Loop X Chat - CLI entry point for chat mode.

Usage:
    python3 bin/loop_chat.py                    # List sessions
    python3 bin/loop_chat.py <session-id>       # Open/create session
    python3 bin/loop_chat.py "My new chat"      # Create session with title
    
Convenience wrapper: add to PATH or create alias:
    alias le-chat='python3 ~/.loop-engineering/bin/loop_chat.py'
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chat.repl import ChatREPL


def main():
    """CLI entry point."""
    repl = ChatREPL()
    
    if len(sys.argv) < 2:
        # No argument - show session list
        repl.start()
    else:
        # Open or create session
        session_arg = sys.argv[1]
        repl.start(session_arg)


if __name__ == "__main__":
    main()
