from __future__ import annotations

import logging
import subprocess

from layerten.config import REPO_CLONE_DIR

logger = logging.getLogger(__name__)

MAX_DIFF_BYTES = 50_000
MAX_FILE_BYTES = 100_000


def read_diff(sha: str, path: str | None = None) -> dict:
    """Get untruncated diff for a commit, optionally filtered to a single file."""
    cmd = ["git", "diff-tree", "-p", sha]
    if path:
        cmd += ["--", path]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(REPO_CLONE_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout
        if len(output) > MAX_DIFF_BYTES:
            output = output[:MAX_DIFF_BYTES] + f"\n\n... truncated at {MAX_DIFF_BYTES} bytes ..."
        return {"diff": output, "truncated": len(result.stdout) > MAX_DIFF_BYTES}
    except subprocess.TimeoutExpired:
        return {"error": f"Diff retrieval timed out for {sha}"}
    except Exception as e:
        return {"error": str(e)}


def read_codebase(path: str, ref: str = "HEAD") -> dict:
    """Read a file at any commit from the local git mirror."""
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=str(REPO_CLONE_DIR),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip() or f"File not found: {path}@{ref}"}
        output = result.stdout
        if len(output) > MAX_FILE_BYTES:
            output = output[:MAX_FILE_BYTES] + f"\n\n... truncated at {MAX_FILE_BYTES} bytes ..."
        return {"content": output, "truncated": len(result.stdout) > MAX_FILE_BYTES}
    except subprocess.TimeoutExpired:
        return {"error": f"Read timed out for {path}@{ref}"}
    except Exception as e:
        return {"error": str(e)}
