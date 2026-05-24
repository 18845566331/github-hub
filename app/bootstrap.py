"""Runtime bootstrap helpers."""

from __future__ import annotations

import os
import site
import sys


def _add_path(path: str):
    if path and os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)


def ensure_user_site_packages():
    """Add the per-user site-packages path when this Python build omits it."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _add_path(os.path.join(base_dir, ".runtime_packages"))
    try:
        user_site = site.getusersitepackages()
    except Exception:
        return
    _add_path(user_site)
