from __future__ import annotations

import runpy
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
runpy.run_path(str(PROJECT_ROOT / "src" / "scope_cli.py"), run_name="__main__")
