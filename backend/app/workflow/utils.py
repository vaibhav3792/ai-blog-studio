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
