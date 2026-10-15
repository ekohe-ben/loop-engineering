"""Chat module test configuration - ensures bin/ is on sys.path."""
import sys
from pathlib import Path

# Add bin/ to path for chat module imports
# This must happen at module level before any test imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))
