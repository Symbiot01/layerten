"""Parse cross-references from text (closes #N, fixes #N, @username, etc.)."""

import re

_CLOSING_RE = re.compile(
    r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)",
    re.IGNORECASE,
)

_BARE_REF_RE = re.compile(r"(?<!\w)#(\d+)(?!\d)")

_MENTION_RE = re.compile(r"(?<!\w)@([a-zA-Z0-9_-]+)")


def parse_references(text: str) -> list[dict]:
    """Extract cross-references from a single text string."""
    if not text:
        return []

    refs: list[dict] = []

    for m in _CLOSING_RE.finditer(text):
        refs.append({"type": "closes", "target": f"issue:{m.group(1)}"})

    closing_numbers = {m.group(1) for m in _CLOSING_RE.finditer(text)}
    for m in _BARE_REF_RE.finditer(text):
        num = m.group(1)
        if num not in closing_numbers:
            refs.append({"type": "mentions", "target_number": int(num)})

    for m in _MENTION_RE.finditer(text):
        refs.append({
            "type": "mentions_person",
            "target": f"person:{m.group(1)}",
        })

    return refs


def collect_references(*text_fields: str | None) -> list[dict]:
    """Collect and deduplicate references from multiple text fields."""
    seen: dict[str, dict] = {}

    for text in text_fields:
        if not text:
            continue
        for ref in parse_references(text):
            key = f"{ref['type']}:{ref.get('target') or ref.get('target_number')}"
            if key in seen:
                seen[key]["evidence_count"] += 1
            else:
                ref["evidence_count"] = 1
                seen[key] = ref

    return list(seen.values())
