from __future__ import annotations

import re
from pathlib import Path
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.services import image_gen, llm
from app.workflow.prompts import decide_images_system
from app.workflow.schemas import GlobalImagePlan
from app.workflow.state import State
from app.workflow.utils import clean_mermaid, insert_after_intro


def _ordered_sections(state: State) -> List[tuple[int, str]]:
    return sorted(state["sections"], key=lambda x: x[0])


def merge_content(state: State) -> dict:
    plan = state["plan"]
    if plan is None:
        raise ValueError("merge_content called without plan.")
    body = "\n\n".join(md for _, md in _ordered_sections(state)).strip()
    return {"merged_md": f"# {plan.blog_title}\n\n{body}\n"}


def _outline_for_images(state: State) -> str:
    """Section ids, titles and a short excerpt. Sending only this (not the whole post)
    keeps the request far below Groq's free-tier tokens-per-minute limit."""
    lines = []
    for task_id, md in _ordered_sections(state):
        title = md.splitlines()[0].lstrip("# ").strip()
        body = re.sub(r"\s+", " ", re.sub(r"```.*?```", " ", md, flags=re.DOTALL))[len(title) + 3 :]
        lines.append(f"[{task_id}] {title}: {body[:300]}")
    return "\n".join(lines)


def decide_images(state: State) -> dict:
    s = get_settings()
    plan = state["plan"]
    assert plan is not None

    illustration_cap = s.max_images if s.images_ready else 0
    diagram_cap = s.max_diagrams
    warnings: List[str] = []
    if s.images_enabled and not s.images_ready:
        warnings.append("Illustrations skipped: Cloudflare credentials are not set.")

    passthrough = {"md_with_placeholders": state["merged_md"], "image_specs": []}
    if illustration_cap == 0 and diagram_cap == 0:
        return {**passthrough, **({"warnings": warnings} if warnings else {})}

    result = llm.structured(
        GlobalImagePlan,
        [
            SystemMessage(content=decide_images_system(illustration_cap, diagram_cap)),
            HumanMessage(
                content=(
                    f"Blog title: {plan.blog_title}\nBlog kind: {plan.blog_kind}\nTopic: {state['topic']}\n\n"
                    f"Sections:\n{_outline_for_images(state)}"
                )
            ),
        ],
        tier="fast",
        max_tokens=1500,
    )

    valid_ids = {tid for tid, _ in state["sections"]}
    specs: List[dict] = []
    placeholders: dict[int, str] = {}
    n_diagrams = n_illustrations = 0

    for p in result.images:
        if p.section_id not in valid_ids or p.section_id in placeholders:
            continue
        mermaid = ""
        if p.kind == "diagram":
            if n_diagrams >= diagram_cap:
                continue
            mermaid = clean_mermaid(p.mermaid)
            if not mermaid:
                warnings.append(f"A diagram for section {p.section_id} was skipped (unusable Mermaid code).")
                continue
            n_diagrams += 1
        else:
            if n_illustrations >= illustration_cap or not p.prompt.strip():
                continue
            n_illustrations += 1
        placeholder = f"[[IMAGE_{len(specs) + 1}]]"
        placeholders[p.section_id] = placeholder
        specs.append({**p.model_dump(), "mermaid": mermaid, "placeholder": placeholder})

    parts = []
    for task_id, md in _ordered_sections(state):
        parts.append(insert_after_intro(md, placeholders[task_id]) if task_id in placeholders else md)
    body = "\n\n".join(parts).strip()

    out = {"md_with_placeholders": f"# {plan.blog_title}\n\n{body}\n", "image_specs": specs}
    if warnings:
        out["warnings"] = warnings
    return out


def _file_stem(name: str, index: int) -> str:
    stem = re.sub(r"[^a-z0-9_-]+", "", Path(name).stem.lower().replace(" ", "_")) or "figure"
    return f"{index}_{stem[:40]}"


def generate_and_place_images(state: State) -> dict:
    s = get_settings()
    md = state.get("md_with_placeholders") or state["merged_md"]
    specs = state.get("image_specs", []) or []

    saved: List[str] = []
    warnings: List[str] = []
    placed = 0
    out_dir = s.images_dir / str(state["run_id"])

    for index, spec in enumerate(specs, start=1):
        placeholder = spec["placeholder"]

        if spec.get("kind") == "diagram":
            # Mermaid renders in the browser (and on GitHub), so there is nothing to generate.
            md = md.replace(placeholder, f"```mermaid\n{spec['mermaid']}\n```\n\n*{spec['caption']}*")
            placed += 1
            continue

        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            full_prompt = f"{spec['prompt'].strip()} {s.image_style}".strip()
            data, ext = image_gen.generate_image(full_prompt)
            filename = f"{_file_stem(spec['filename'] or 'figure', index)}.{ext}"
            (out_dir / filename).write_bytes(data)
        except Exception as exc:
            warnings.append(f"Illustration '{spec.get('caption', '')[:60]}' failed ({type(exc).__name__}: {exc}).")
            inner = f"image skipped: {spec.get('alt', '')} | prompt: {spec.get('prompt', '')}".replace("--", "- -")
            md = md.replace(placeholder, f"<!-- {inner} -->")
            continue
        saved.append(filename)
        placed += 1
        md = md.replace(placeholder, f"![{spec['alt']}](images/{filename})\n*{spec['caption']}*")

    md = re.sub(r"\n*\[\[IMAGE_\d+\]\]\n*", "\n\n", md)
    out = {"final": md, "images": saved, "visuals": placed}
    if warnings:
        out["warnings"] = warnings
    return out
