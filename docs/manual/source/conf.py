from __future__ import annotations

import re
import subprocess

from pathlib import Path
from datetime import datetime


project = "EchoGTFS Manual"
author = "EchoGTFS"
copyright = f"{datetime.now().year}, EchoGTFS"


def _find_git_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / ".git").exists():
            return path
    return start


def _normalize_tag(tag: str) -> str:
    # Match setuptools_scm-style normalization for common v-prefixed tags.
    return tag[1:] if tag.startswith("v") else tag


def _version_from_git() -> str:
    repo_root = _find_git_root(Path(__file__).resolve())

    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--long", "--dirty", "--always"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "0.0.dev0"

    describe = result.stdout.strip()
    match = re.match(
        r"^(?P<tag>.+)-(?P<distance>\d+)-g(?P<sha>[0-9a-f]+)(?P<dirty>-dirty)?$",
        describe,
    )

    if match:
        tag = _normalize_tag(match.group("tag"))
        distance = int(match.group("distance"))
        sha = match.group("sha")
        dirty = bool(match.group("dirty"))

        if distance == 0 and not dirty:
            return tag

        suffix = f".dev{distance}+g{sha}"
        if dirty:
            suffix += ".dirty"
        return f"{tag}{suffix}"

    short_sha_match = re.match(r"^(?P<sha>[0-9a-f]+)(?P<dirty>-dirty)?$", describe)
    if short_sha_match:
        sha = short_sha_match.group("sha")
        dirty = bool(short_sha_match.group("dirty"))
        value = f"0.0.dev0+g{sha}"
        return f"{value}.dirty" if dirty else value

    return "0.0.dev0"


release = _version_from_git()
version = release.split("+")[0]

extensions = [
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

source_suffix = {
    ".md": "markdown",
}

language = "de"
locale_dirs = ["locale/"]
gettext_compact = False

html_theme = "furo"
html_title = "EchoGTFS"
html_static_path = ["_static"]
html_css_files = ["version-selector.css"]
html_js_files = ["version-selector.js", "language-selector.js"]
