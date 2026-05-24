"""Reviewed install and launch recipes for repositories tested end to end.

Recipes are owned by this application instead of being loaded from a cloned
repository. Unknown projects therefore cannot inject commands that run
automatically on the user's computer.
"""
from copy import deepcopy
from urllib.parse import urlparse


VERIFIED_RECIPES = {
    "nexu-io/open-design": {
        "key": "nexu-io/open-design",
        "title": "Open Design",
        "verified_on": "2026-05-24",
        "verification": "real_pnpm_install_tools_dev_http_stop",
        "install": {
            "runtime": "node",
        },
        "launch": {
            "cmd": ["pnpm", "run", "tools-dev"],
            "required_files": ["package.json"],
            "description": "Verified recipe: pnpm run tools-dev",
        },
    },
    "shekhargulati/python-flask-docker-hello-world": {
        "key": "shekhargulati/python-flask-docker-hello-world",
        "title": "Python Flask Docker Hello World",
        "verified_on": "2026-05-24",
        "verification": "real_clone_install_launch_http_stop",
        "install": {
            "runtime": "python",
            "requirements": ["requirements.txt"],
            "install_project": False,
        },
        "launch": {
            "cmd": ["{python}", "app.py"],
            "required_files": ["app.py"],
            "description": "Verified recipe: python app.py",
        },
    },
}


def _repository_key_from_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("git@github.com:"):
        text = "https://github.com/" + text.split(":", 1)[1]
    try:
        path = urlparse(text).path if "://" in text else text
    except ValueError:
        return ""
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) < 2:
        return ""
    repo = parts[1].removesuffix(".git")
    return f"{parts[0]}/{repo}".lower()


def repository_key(project: dict) -> str:
    """Return an owner/repository identifier represented by a project."""
    owner = str(project.get("owner", "")).strip()
    repo = str(project.get("repo", "")).strip()
    if owner and repo:
        return f"{owner}/{repo.removesuffix('.git')}".lower()
    full_name = str(project.get("full_name", "")).strip()
    if "/" in full_name:
        return full_name.removesuffix(".git").lower()
    for field in ("html_url", "clone_url", "url"):
        key = _repository_key_from_url(project.get(field, ""))
        if key:
            return key
    return ""


def get_verified_recipe(project: dict) -> dict | None:
    """Return a reviewed recipe for a known project, if one is available."""
    recipe = VERIFIED_RECIPES.get(repository_key(project))
    return deepcopy(recipe) if recipe else None


def recipe_summary(recipe: dict) -> dict:
    return {
        "key": recipe.get("key", ""),
        "title": recipe.get("title", ""),
        "verified_on": recipe.get("verified_on", ""),
        "verification": recipe.get("verification", ""),
    }
