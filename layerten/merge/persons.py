"""Build person alias map from email<->login correlations in merged commits."""

from __future__ import annotations

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def build_person_map(
    alias_pairs: list[tuple[str, str, str]],
    merged_commits: list[dict],
) -> tuple[dict, dict[str, str]]:
    """Build the canonical person alias map and resolve clone-only commits.

    Args:
        alias_pairs: list of (email, login, name) from commits with both sources.
        merged_commits: all merged commit dicts (mutated in-place to fill in
                        author.login / committer.login when resolved).

    Returns:
        (persons_dict, email_to_login) where persons_dict is
        {login: {canonical_login, display_name, aliases, alias_sources, commit_count}}
    """
    login_to_emails: dict[str, set[str]] = defaultdict(set)
    login_to_names: dict[str, set[str]] = defaultdict(set)
    email_to_login: dict[str, str] = {}
    alias_sources: dict[str, dict[str, str]] = defaultdict(dict)

    for email, login, name in alias_pairs:
        if not login or not email:
            continue
        login_lower = login.lower()
        login_to_emails[login].add(email)
        email_to_login[email] = login
        if name:
            login_to_names[login].add(name)
        if email not in alias_sources.get(login, {}):
            alias_sources.setdefault(login, {})[email] = "discovered"

    resolved_count = 0
    for commit in merged_commits:
        for role in ("author", "committer"):
            person = commit.get(role)
            if not person or person.get("login"):
                continue
            email = person.get("email", "")
            if email in email_to_login:
                person["login"] = email_to_login[email]
                resolved_count += 1

    logger.info("Resolved %d author/committer logins via alias map", resolved_count)

    login_commit_counts: dict[str, int] = defaultdict(int)
    for commit in merged_commits:
        login = (commit.get("author") or {}).get("login")
        if login:
            login_commit_counts[login] += 1

    persons: dict[str, dict] = {}
    all_logins = set(login_to_emails.keys())
    for commit in merged_commits:
        for role in ("author", "committer"):
            person = commit.get(role)
            if person and person.get("login"):
                all_logins.add(person["login"])

    for login in sorted(all_logins):
        emails = login_to_emails.get(login, set())
        names = login_to_names.get(login, set())
        all_aliases = sorted(emails | names | {login})
        persons[login] = {
            "canonical_login": login,
            "display_name": next(iter(sorted(names))) if names else login,
            "aliases": all_aliases,
            "alias_sources": alias_sources.get(login, {}),
            "commit_count": login_commit_counts.get(login, 0),
        }

    logger.info("Built person map: %d unique identities", len(persons))
    return persons, email_to_login
