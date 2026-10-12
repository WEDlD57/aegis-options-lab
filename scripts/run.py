"""Source-tree entry point: no pip install or network needed."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aegis.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
