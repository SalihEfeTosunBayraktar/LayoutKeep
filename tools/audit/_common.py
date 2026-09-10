"""Shared helper for audit reproduction scripts.

Usage (from any script in tools/audit/):

    from _common import REPO, TMP, setup
    setup()  # sys.path + os.chdir + writable temp dir

Design notes:
- Scripts must run unchanged from any working directory: `setup()` locates the repo by
  walking up from this file, so the audit evidence does not depend on where you invoke it.
- Scratch output (epubs, pdfs, sqlite) goes to a temp dir, NOT the repo: the audit must not
  dirty the working tree it is auditing. Default is %TEMP%/lk-audit; set LK_AUDIT_TMP to override.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

#: Repository root, resolved from this file's location (tools/audit/_common.py -> ../..).
REPO = Path(__file__).resolve().parent.parent.parent
#: Directory for scratch output. Never inside the repo.
TMP = Path(os.environ.get("LK_AUDIT_TMP", Path(tempfile.gettempdir()) / "lk-audit"))


def setup() -> None:
    """Make `import layoutkeep...` work and point the cwd at the repo root."""
    sys.path.insert(0, str(REPO / "src"))
    os.chdir(REPO)
    TMP.mkdir(parents=True, exist_ok=True)
