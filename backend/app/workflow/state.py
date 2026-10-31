from __future__ import annotations

import operator
from typing import Annotated, List, Optional, Tuple, TypedDict

from app.workflow.schemas import EvidenceItem, Plan


class State(TypedDict):
    topic: str
    run_id: str

    # routing / research
    mode: str
    needs_research: bool
    queries: List[str]
    evidence: List[EvidenceItem]
    plan: Optional[Plan]

    # recency
    as_of: str
    recency_days: int

    # workers: (task_id, section_md)
    sections: Annotated[List[Tuple[int, str]], operator.add]
    # non-fatal problems, shown to the user
    warnings: Annotated[List[str], operator.add]

    # reducer / images
    merged_md: str
    md_with_placeholders: str
    image_specs: List[dict]
    images: List[str]
    visuals: int

    final: str
