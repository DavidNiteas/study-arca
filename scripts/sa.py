#!/usr/bin/env python
"""sa 入口：python scripts/sa.py <command>"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sa.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
