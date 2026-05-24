"""Configuration normalization helpers for GitHub Hub."""

from __future__ import annotations

from .mirror_manager import GITHUB_MIRRORS, NPM_MIRRORS, PIP_MIRRORS


# ──── ───────────────────────────────── ────
# Legacy key mappings — DO NOT REMOVE
# These map config values that were corrupted by encoding
# issues (UTF-8 read as GBK, re-encoded as UTF-8) back to
# valid mirror display names. Each garbled key corresponds
# to a real-world corruption pattern seen in existing config files.
# ──── ───────────────────────────────── ────
LEGACY_MIRROR_VALUES = {
    "github_mirror": {
        "Default GitHub mirror": "直连 GitHub (默认)",
        "Default": "直连 GitHub (默认)",
        "GitHub": "直连 GitHub (默认)",
    },
    "npm_mirror": {
        "Default npm mirror": "官方 npm (默认)",
        "Default": "官方 npm (默认)",
        "npm": "官方 npm (默认)",
    },
    "pip_mirror": {
        "Default PyPI mirror": "官方 PyPI (默认)",
        "Default": "官方 PyPI (默认)",
        "PyPI": "官方 PyPI (默认)",
        "������": "阿里云",
        "闃块噷浜?": "阿里云",
    },
}


def _normalize_choice(value: str, valid: dict, fallback: str, legacy: dict) -> str:
    if value in valid:
        return value
    mapped = legacy.get(value)
    if mapped in valid:
        return mapped
    return fallback


def migrate_config_values(cfg: dict) -> dict:
    """Normalize legacy or corrupted config values without changing user projects."""
    migrated = dict(cfg or {})
    migrated["github_mirror"] = _normalize_choice(
        migrated.get("github_mirror", ""),
        GITHUB_MIRRORS,
        "直连 GitHub (默认)",
        LEGACY_MIRROR_VALUES["github_mirror"],
    )
    migrated["npm_mirror"] = _normalize_choice(
        migrated.get("npm_mirror", ""),
        NPM_MIRRORS,
        "官方 npm (默认)",
        LEGACY_MIRROR_VALUES["npm_mirror"],
    )
    migrated["pip_mirror"] = _normalize_choice(
        migrated.get("pip_mirror", ""),
        PIP_MIRRORS,
        "官方 PyPI (默认)",
        LEGACY_MIRROR_VALUES["pip_mirror"],
    )
    try:
        migrated["dep_mode"] = int(migrated.get("dep_mode", 1))
    except (TypeError, ValueError):
        migrated["dep_mode"] = 1
    if migrated["dep_mode"] not in (0, 1):
        migrated["dep_mode"] = 1
    migrated.setdefault("projects", [])
    if not isinstance(migrated["projects"], list):
        migrated["projects"] = []
    return migrated
