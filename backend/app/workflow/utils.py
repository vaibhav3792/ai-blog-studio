from __future__ import annotations

import re
from typing import Iterable, List

from app.workflow.schemas import EvidenceItem


def safe_slug(title: str) -> str:
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9 _-]+", "", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s[:80] or "blog"


def evidence_lines(items: Iterable[EvidenceItem], *, snippet_chars: int = 0, limit: int = 20) -> str:
    lines: List[str] = []
    for e in list(items)[:limit]:
        line = f"- {e.title} | {e.url} | {e.published_at or 'date:unknown'}"
        if snippet_chars and e.snippet:
            line += f" | {e.snippet[:snippet_chars]}"
        lines.append(line)
    return "\n".join(lines)


def clean_section(md: str, title: str) -> str:
    """Strip an outer code fence and make sure the section starts with '## Title'."""
    md = md.strip()
    fenced = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```$", md, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        md = fenced.group(1).strip()
    if not md.startswith("#"):
        md = f"## {title}\n\n{md}"
    return md


_LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")


def _norm_url(url: str) -> str:
    return url.strip().lower().rstrip("/").split("#")[0]


def strip_unverified_links(md: str, allowed_urls: Iterable[str]) -> str:
    """Keep a Markdown link only if it points at a collected source (or is an in-page anchor or mailto link).

    Language models invent plausible-looking URLs that return 404. Any external link that is not one
    of the evidence URLs is replaced by its plain text. Fenced code blocks are left untouched.
    """
    allowed = {_norm_url(u) for u in allowed_urls}

    def fix(match: re.Match) -> str:
        text, url = match.group(1), match.group(2)
        if url.startswith("#") or url.lower().startswith("mailto:"):
            return match.group(0)  # in-page anchors and email links
        # External links must be collected sources. Relative paths ("/docs/x") and scheme-less
        # addresses ("example.com/x") would resolve against this app's own domain and 404.
        return match.group(0) if _norm_url(url) in allowed else text

    parts = re.split(r"(```.*?```)", md, flags=re.DOTALL)
    return "".join(p if p.startswith("```") else _LINK_RE.sub(fix, p) for p in parts)


_GENERIC_LINK_TEXT = {"source", "sources", "link", "here", "read more", "more", "ref", "reference", "citation", "this", "article"}


def name_generic_links(md: str) -> str:
    """Turn leftover '[Source](url)' links into '[site.com](url)' so every link says where it goes.

    Fenced code blocks are left untouched.
    """
    from urllib.parse import urlparse

    def fix(match: re.Match) -> str:
        text, url = match.group(1), match.group(2)
        label = text.strip().strip("[]").lower()
        if label not in _GENERIC_LINK_TEXT and not label.isdigit():
            return match.group(0)
        host = (urlparse(url).hostname or "").removeprefix("www.")
        return f"[{host}]({url})" if host else match.group(0)

    parts = re.split(r"(```.*?```)", md, flags=re.DOTALL)
    return "".join(p if p.startswith("```") else _LINK_RE.sub(fix, p) for p in parts)


_NO_SOURCE_LINE = re.compile(
    r"^[\s>*_-]*(?:(?:sources?|citations?)[\s:*_]*)?not found in provided sources\.?[\s*_]*$",
    re.IGNORECASE | re.MULTILINE,
)
_NO_SOURCE_PHRASE = re.compile(r"\s*\(?\[?not found in provided sources\.?\]?\)?", re.IGNORECASE)


def remove_no_source_notes(md: str) -> str:
    """Delete leftover 'Not found in provided sources' notes the model sometimes writes."""
    md = _NO_SOURCE_LINE.sub("", md)
    md = _NO_SOURCE_PHRASE.sub("", md)
    return re.sub(r"\n{3,}", "\n\n", md).strip()


def insert_after_intro(md: str, placeholder: str) -> str:
    """Put `placeholder` after the first plain paragraph of a section (never inside a code fence)."""
    blocks = re.split(r"\n\s*\n", md.strip())
    in_fence = False
    for i, block in enumerate(blocks):
        if i == 0:
            continue
        starts_fence = block.lstrip().startswith("```")
        fence_count = block.count("```")
        plain = not in_fence and not starts_fence and not re.match(r"^\s*(#|\||[-*+]\s|\d+\.\s|>)", block)
        if fence_count % 2 == 1:
            in_fence = not in_fence
        if plain:
            blocks.insert(i + 1, placeholder)
            return "\n\n".join(blocks)
    return md.strip() + "\n\n" + placeholder


_MERMAID_STARTS = ("flowchart", "graph", "sequenceDiagram", "stateDiagram", "classDiagram", "erDiagram")


def clean_mermaid(src: str) -> str:
    """Return tidy Mermaid source, or "" if it looks unusable (the browser also guards against errors)."""
    src = re.sub(r"^```(?:mermaid)?\s*|\s*```$", "", src.strip(), flags=re.IGNORECASE).strip()
    if not src or len(src) > 1500 or "```" in src or "<" in src:
        return ""
    if not src.startswith(_MERMAID_STARTS):
        return ""
    if src.count("[") != src.count("]") or src.count("(") != src.count(")") or src.count('"') % 2:
        return ""
    return src
