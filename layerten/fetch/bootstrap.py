"""
Main orchestrator: fetches all historical data from a GitHub repo.

Usage:
    python -m layerten.fetch.bootstrap
"""

import logging
import sys
import time

from layerten.config import (
    GITHUB_TOKEN,
    RAW_EVENTS_PATH,
    REPO_CLONE_DIR,
    REPO_NAME,
    REPO_OWNER,
    TARGET_REPO,
)
from layerten.fetch.clone import (
    clone_repo,
    extract_commit_diff,
    extract_commit_files,
    extract_commit_full_message,
    extract_commits,
    extract_file_tree,
    extract_renames,
    extract_tags,
)
from layerten.fetch.graphql import (
    fetch_all_discussions,
    fetch_all_issues,
    fetch_all_prs,
)
from layerten.fetch.rest import (
    fetch_branches,
    fetch_commits_metadata,
    fetch_labels,
    fetch_releases,
)
from layerten.store.raw_events import (
    clear_checkpoint,
    count_events_by_type,
    get_fetched_ids,
    load_checkpoint,
    save_checkpoint,
    write_raw_event,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

COMMIT_CHECKPOINT_INTERVAL = 500


def _step_clone():
    """Step 1: Clone the repo (or fetch updates)."""
    repo_url = f"https://github.com/{TARGET_REPO}.git"
    clone_repo(repo_url, REPO_CLONE_DIR)
    logger.info("Clone complete: %s", REPO_CLONE_DIR)


def _step_commits():
    """Step 2: Extract commits + diffs from the local clone."""
    fetched = get_fetched_ids("commit_clone")
    commits = extract_commits(REPO_CLONE_DIR)
    total = len(commits)
    logger.info("Found %d commits in clone", total)

    checkpoint = load_checkpoint("commits_clone")
    start_idx = checkpoint.get("last_index", 0) if checkpoint else 0

    for i, commit in enumerate(commits):
        if i < start_idx:
            continue
        event_id = f"commit_clone:{commit['sha']}"
        if event_id in fetched:
            continue

        full_message = extract_commit_full_message(REPO_CLONE_DIR, commit["sha"])
        diff, truncated = extract_commit_diff(REPO_CLONE_DIR, commit["sha"])
        files_changed = extract_commit_files(REPO_CLONE_DIR, commit["sha"])

        payload = {
            **commit,
            "message": full_message,
            "diff": diff,
            "diff_truncated": truncated,
            "files_changed": files_changed,
        }
        write_raw_event("commit_clone", commit["sha"], payload, source="git_clone")

        if (i + 1) % COMMIT_CHECKPOINT_INTERVAL == 0:
            save_checkpoint("commits_clone", {"last_index": i + 1})
            logger.info("Commits: %d / %d extracted", i + 1, total)

    clear_checkpoint("commits_clone")
    logger.info("Commits: all %d extracted", total)


def _step_file_tree():
    """Step 3: Extract the file tree at HEAD."""
    fetched = get_fetched_ids("file_tree")
    if "file_tree:HEAD" in fetched:
        logger.info("File tree at HEAD already fetched, skipping")
        return

    tree = extract_file_tree(REPO_CLONE_DIR, "HEAD")
    write_raw_event("file_tree", "HEAD", {"ref": "HEAD", "files": tree}, source="git_clone")
    logger.info("File tree at HEAD: %d files", len(tree))


def _step_renames():
    """Step 4: Extract rename history."""
    fetched = get_fetched_ids("rename")
    if "rename:all" in fetched:
        logger.info("Renames already fetched, skipping")
        return

    renames = extract_renames(REPO_CLONE_DIR)
    write_raw_event("rename", "all", {"renames": renames}, source="git_clone")
    logger.info("Renames: %d detected across history", len(renames))


def _step_tags():
    """Step 5: Extract tags."""
    fetched = get_fetched_ids("tag")
    tags = extract_tags(REPO_CLONE_DIR)
    new_count = 0
    for tag in tags:
        eid = f"tag:{tag['name']}"
        if eid in fetched:
            continue
        write_raw_event("tag", tag["name"], tag, source="git_clone")
        new_count += 1
    logger.info("Tags: %d total, %d new", len(tags), new_count)


def _step_branches():
    """Step 6: Fetch branches from REST API."""
    fetched = get_fetched_ids("branch")
    branches = fetch_branches(REPO_OWNER, REPO_NAME, GITHUB_TOKEN)
    new_count = 0
    for b in branches:
        eid = f"branch:{b['name']}"
        if eid in fetched:
            continue
        write_raw_event("branch", b["name"], b, source="github_api")
        new_count += 1
    logger.info("Branches: %d total, %d new", len(branches), new_count)


def _step_labels():
    """Step 7: Fetch labels from REST API."""
    fetched = get_fetched_ids("label")
    labels = fetch_labels(REPO_OWNER, REPO_NAME, GITHUB_TOKEN)
    new_count = 0
    for label in labels:
        eid = f"label:{label['name']}"
        if eid in fetched:
            continue
        write_raw_event("label", label["name"], label, source="github_api")
        new_count += 1
    logger.info("Labels: %d total, %d new", len(labels), new_count)


def _step_releases():
    """Step 8: Fetch releases from REST API."""
    fetched = get_fetched_ids("release")
    releases = fetch_releases(REPO_OWNER, REPO_NAME, GITHUB_TOKEN)
    new_count = 0
    for r in releases:
        eid = f"release:{r['tag_name']}"
        if eid in fetched:
            continue
        write_raw_event("release", r["tag_name"], r, source="github_api")
        new_count += 1
    logger.info("Releases: %d total, %d new", len(releases), new_count)


def _step_commits_metadata():
    """Step 9: Fetch commit metadata from REST API (author login, verified)."""
    fetched = get_fetched_ids("commit_api")
    commits = fetch_commits_metadata(REPO_OWNER, REPO_NAME, GITHUB_TOKEN)
    new_count = 0
    for c in commits:
        eid = f"commit_api:{c['sha']}"
        if eid in fetched:
            continue
        write_raw_event("commit_api", c["sha"], c, source="github_api")
        new_count += 1
    logger.info("Commit metadata (API): %d total, %d new", len(commits), new_count)


def _step_prs():
    """Step 10: Fetch all PRs via GraphQL."""
    fetched = get_fetched_ids("pr")
    checkpoint = load_checkpoint("prs_graphql")
    start_cursor = checkpoint.get("cursor") if checkpoint else None

    prs, _ = fetch_all_prs(REPO_OWNER, REPO_NAME, GITHUB_TOKEN, start_cursor)
    new_count = 0
    for pr in prs:
        pr_num = str(pr["number"])
        eid = f"pr:{pr_num}"
        if eid in fetched:
            continue
        write_raw_event("pr", pr_num, pr, source="github_api")
        new_count += 1

    clear_checkpoint("prs_graphql")
    logger.info("Pull Requests: %d fetched, %d new", len(prs), new_count)


def _step_issues():
    """Step 11: Fetch all issues via GraphQL."""
    fetched = get_fetched_ids("issue")
    checkpoint = load_checkpoint("issues_graphql")
    start_cursor = checkpoint.get("cursor") if checkpoint else None

    issues, _ = fetch_all_issues(REPO_OWNER, REPO_NAME, GITHUB_TOKEN, start_cursor)
    new_count = 0
    for issue in issues:
        issue_num = str(issue["number"])
        eid = f"issue:{issue_num}"
        if eid in fetched:
            continue
        write_raw_event("issue", issue_num, issue, source="github_api")
        new_count += 1

    clear_checkpoint("issues_graphql")
    logger.info("Issues: %d fetched, %d new", len(issues), new_count)


def _step_discussions():
    """Step 12: Fetch all discussions via GraphQL."""
    fetched = get_fetched_ids("discussion")
    checkpoint = load_checkpoint("discussions_graphql")
    start_cursor = checkpoint.get("cursor") if checkpoint else None

    discussions, _ = fetch_all_discussions(
        REPO_OWNER, REPO_NAME, GITHUB_TOKEN, start_cursor
    )
    new_count = 0
    for disc in discussions:
        disc_num = str(disc["number"])
        eid = f"discussion:{disc_num}"
        if eid in fetched:
            continue
        write_raw_event("discussion", disc_num, disc, source="github_api")
        new_count += 1

    clear_checkpoint("discussions_graphql")
    logger.info("Discussions: %d fetched, %d new", len(discussions), new_count)


def _print_summary(elapsed: float):
    """Print final summary of what was fetched."""
    counts = count_events_by_type()
    total = sum(counts.values())

    file_size_mb = 0.0
    if RAW_EVENTS_PATH.exists():
        file_size_mb = RAW_EVENTS_PATH.stat().st_size / (1024 * 1024)

    print("\n" + "=" * 60)
    print("BOOTSTRAP COMPLETE")
    print("=" * 60)
    print(f"  Time elapsed:  {elapsed:.1f}s ({elapsed / 60:.1f}m)")
    print(f"  Raw log size:  {file_size_mb:.1f} MB")
    print(f"  Total events:  {total}")
    print()
    for et, count in sorted(counts.items()):
        print(f"  {et:20s}  {count:>6}")
    print("=" * 60)


STEPS = [
    ("Clone repo", _step_clone),
    ("Extract commits + diffs", _step_commits),
    ("Extract file tree at HEAD", _step_file_tree),
    ("Extract renames", _step_renames),
    ("Extract tags", _step_tags),
    ("Fetch branches (REST)", _step_branches),
    ("Fetch labels (REST)", _step_labels),
    ("Fetch releases (REST)", _step_releases),
    ("Fetch commit metadata (REST)", _step_commits_metadata),
    ("Fetch PRs (GraphQL)", _step_prs),
    ("Fetch issues (GraphQL)", _step_issues),
    ("Fetch discussions (GraphQL)", _step_discussions),
]


def run_bootstrap():
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN not set in .env — aborting")
        sys.exit(1)

    logger.info("Starting bootstrap for %s", TARGET_REPO)
    start = time.time()

    for i, (name, step_fn) in enumerate(STEPS, 1):
        logger.info("─── Step %d/%d: %s ───", i, len(STEPS), name)
        step_start = time.time()
        try:
            step_fn()
        except Exception:
            logger.exception("Step %d (%s) failed", i, name)
            raise
        step_elapsed = time.time() - step_start
        logger.info("Step %d done in %.1fs", i, step_elapsed)

    elapsed = time.time() - start
    _print_summary(elapsed)


if __name__ == "__main__":
    run_bootstrap()
