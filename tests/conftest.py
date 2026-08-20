"""pytest 共享 fixtures。"""
from __future__ import annotations

import sys
from pathlib import Path

# 让 tests 可以无需 pip install 也能 import src（pip install -e . 后这行是 no-op）。
SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
