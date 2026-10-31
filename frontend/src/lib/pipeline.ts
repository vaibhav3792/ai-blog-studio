import type { RunEvent } from "./types";

export type StepId = "router" | "research" | "outline" | "write" | "images";
export type StepState = "pending" | "active" | "done" | "skipped" | "failed";

export interface Step {
  id: StepId;
  label: string;
  state: StepState;
  note?: string;
}

export interface SectionStatus {
  id: number;
  title: string;
  done: boolean;
}

export interface PipelineView {
  steps: Step[];
  sections: SectionStatus[];
  title?: string;
  warnings: string[];
  started: boolean;
  outcome: "done" | "error" | null;
  error?: string;
}

const LABELS: Record<StepId, string> = {
  router: "Decide how to research",
  research: "Gather sources",
  outline: "Outline the post",
  write: "Write sections",
  images: "Add visuals",
};
const ORDER: StepId[] = ["router", "research", "outline", "write", "images"];

/** Pure function: the whole UI state is rebuilt from the event list, so reconnects are safe. */
export function derivePipeline(events: RunEvent[]): PipelineView {
  const state: Record<StepId, StepState> = { router: "pending", research: "pending", outline: "pending", write: "pending", images: "pending" };
  const notes: Partial<Record<StepId, string>> = {};
  const view: PipelineView = { steps: [], sections: [], warnings: [], started: false, outcome: null };

  for (const ev of events) {
    if (ev.type === "started") view.started = true;
    else if (ev.type === "warning") view.warnings.push(ev.message);
    else if (ev.type === "done") view.outcome = "done";
    else if (ev.type === "error") {
      view.outcome = "error";
      view.error = ev.message;
    } else if (ev.type === "node") {
      const d = ev.data;
      switch (ev.node) {
        case "router":
          state.router = "done";
          notes.router = d.mode;
          if (!d.needs_research) state.research = "skipped";
          break;
        case "research":
          state.research = "done";
          notes.research = `${d.sources} ${d.sources === 1 ? "source" : "sources"}`;
          break;
        case "orchestrator":
          state.outline = "done";
          view.title = d.title;
          view.sections = (d.sections as { id: number; title: string }[]).map((s) => ({ ...s, done: false }));
          break;
        case "worker":
          view.sections = view.sections.map((s) => (s.id === d.task_id ? { ...s, done: true } : s));
          notes.write = `${d.done} of ${d.total}`;
          if (d.done >= d.total) state.write = "done";
          break;
        case "merge_content":
          state.write = "done";
          break;
        case "decide_images":
          if (d.images === 0) {
            state.images = "skipped";
            notes.images = "none needed";
          }
          break;
        case "generate_and_place_images":
          if (state.images !== "skipped") {
            state.images = "done";
            notes.images = `${d.visuals} added`;
          }
          break;
      }
    }
  }

  if (view.outcome === "done") {
    for (const id of ORDER) if (state[id] === "pending" || state[id] === "active") state[id] = "done";
  } else if (view.started) {
    const active = ORDER.find((id) => state[id] === "pending");
    if (active) state[active] = view.outcome === "error" ? "failed" : "active";
  }

  view.steps = ORDER.map((id) => ({ id, label: LABELS[id], state: state[id], note: notes[id] }));
  return view;
}
