from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from app.services.llm import is_retryable
from app.workflow.nodes.orchestrator import fanout, orchestrator_node
from app.workflow.nodes.reducer import decide_images, generate_and_place_images, merge_content
from app.workflow.nodes.research import research_node
from app.workflow.nodes.router import route_next, router_node
from app.workflow.nodes.worker import worker_node
from app.workflow.state import State

# Router -> (Research?) -> Orchestrator -> Workers (parallel) -> merge -> decide images -> generate images
NODE_ORDER = [
    "router",
    "research",
    "orchestrator",
    "worker",
    "merge_content",
    "decide_images",
    "generate_and_place_images",
]


def build_graph():
    retry = RetryPolicy(
        max_attempts=3,
        initial_interval=3.0,
        backoff_factor=2.0,
        max_interval=30.0,
        retry_on=is_retryable,
    )

    g = StateGraph(State)
    g.add_node("router", router_node, retry_policy=retry)
    g.add_node("research", research_node)
    g.add_node("orchestrator", orchestrator_node, retry_policy=retry)
    g.add_node("worker", worker_node)
    g.add_node("merge_content", merge_content)
    g.add_node("decide_images", decide_images, retry_policy=retry)
    g.add_node("generate_and_place_images", generate_and_place_images)

    g.add_edge(START, "router")
    g.add_conditional_edges("router", route_next, {"research": "research", "orchestrator": "orchestrator"})
    g.add_edge("research", "orchestrator")
    g.add_conditional_edges("orchestrator", fanout, ["worker"])
    g.add_edge("worker", "merge_content")
    g.add_edge("merge_content", "decide_images")
    g.add_edge("decide_images", "generate_and_place_images")
    g.add_edge("generate_and_place_images", END)
    return g.compile()
