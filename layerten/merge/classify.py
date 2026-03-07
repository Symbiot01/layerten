"""File categorization by extension/path and processing hints computation."""

from __future__ import annotations

import os

_SOURCE_EXTS = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt", ".scala", ".sh",
})

_CONFIG_NAMES = frozenset({
    "pyproject.toml", "setup.cfg", "setup.py", "makefile", "dockerfile",
    ".dockerignore", ".editorconfig", ".pre-commit-config.yaml",
    ".ruff.toml", ".coveragerc", ".gitignore",
})

_CONFIG_EXTS = frozenset({".yml", ".yaml", ".toml", ".ini", ".cfg"})

_LOCKFILE_NAMES = frozenset({
    "poetry.lock", "package-lock.json", "pipfile.lock", "yarn.lock",
    "cargo.lock", "pnpm-lock.yaml",
})

_ASSET_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".eot", ".mp4", ".webm", ".pdf",
})

_DOC_EXTS = frozenset({".md", ".rst", ".txt", ".adoc"})

_BOT_AUTHORS = frozenset({
    "dependabot", "renovate", "github-actions", "web-flow",
    "dependabot[bot]", "renovate[bot]", "snyk-bot", "codecov",
    "stale[bot]", "pre-commit-ci[bot]",
})

_VENDOR_DIRS = ("vendor/", "third_party/", "node_modules/")
_TEST_DIRS = ("tests/", "test/", "__tests__/")


def classify_file(path: str) -> str:
    """Return the category for a file path."""
    basename = os.path.basename(path).lower()
    _, ext = os.path.splitext(basename)
    path_lower = path.lower()

    if basename in _LOCKFILE_NAMES:
        return "lockfile"

    if any(path_lower.startswith(d) for d in _VENDOR_DIRS):
        return "vendor"

    if ext in _ASSET_EXTS:
        return "asset"

    if "_pb2" in basename or ".generated." in basename:
        return "generated"

    if any(path_lower.startswith(d) for d in _TEST_DIRS):
        return "test"
    if basename.startswith("test_") or basename.endswith(("_test.py", "_spec.js", ".test.ts", ".test.js")):
        return "test"

    if ext in _SOURCE_EXTS:
        return "source"

    if basename in _CONFIG_NAMES or ext in _CONFIG_EXTS:
        return "config"

    if ext in _DOC_EXTS:
        return "docs"

    return "other"


def classify_files_changed(files_changed: list[dict]) -> list[dict]:
    """Add a 'category' field to each entry in files_changed."""
    for fc in files_changed:
        path = fc.get("path") or fc.get("new_path") or ""
        fc["category"] = classify_file(path)
    return files_changed


def compute_processing_hints(event: dict) -> dict:
    """Compute processing_hints for a single merged event."""
    etype = event["type"]
    hints: dict = {}

    files_changed = event.get("files_changed", [])
    hints["skip_files"] = [
        fc["path"] for fc in files_changed
        if fc.get("category") in ("lockfile", "generated", "vendor", "asset")
        and fc.get("path")
    ]

    if etype == "commit":
        msg = event.get("message", "")
        hints["message_length"] = len(msg)
        hints["is_merge_commit"] = len(event.get("parent_shas", [])) >= 2

        author_login = (event.get("author") or {}).get("login", "")
        committer_login = (event.get("committer") or {}).get("login", "")
        hints["is_bot"] = (
            (author_login or "").lower() in _BOT_AUTHORS
            or (committer_login or "").lower() in _BOT_AUTHORS
        )

        hints["needs_agentic"] = (
            len(msg) > 100
            and not hints["is_merge_commit"]
            and not hints["is_bot"]
        )

    elif etype == "pr":
        body = event.get("body") or ""
        hints["body_length"] = len(body)
        hints["is_bot"] = (event.get("author_login") or "").lower() in _BOT_AUTHORS
        hints["needs_agentic"] = True

    elif etype == "issue":
        body = event.get("body") or ""
        hints["body_length"] = len(body)
        hints["is_bot"] = (event.get("author_login") or "").lower() in _BOT_AUTHORS
        hints["needs_agentic"] = True

    elif etype == "discussion":
        body = event.get("body") or ""
        hints["body_length"] = len(body)
        hints["is_bot"] = (event.get("author_login") or "").lower() in _BOT_AUTHORS
        hints["needs_agentic"] = True

    elif etype == "tag":
        release_body = event.get("release_body") or ""
        hints["is_bot"] = False
        hints["needs_agentic"] = len(release_body) > 50

    else:
        hints["is_bot"] = False
        hints["needs_agentic"] = False

    return hints
