import { Check, Circle, Minus } from "lucide-react";
import type { PipelineView } from "../lib/pipeline";

export default function PipelineTracker({ view }: { view: PipelineView }) {
  return (
    <ol className="m-0 list-none space-y-3 p-0" aria-label="Generation progress">
      {view.steps.map((step) => (
        <li key={step.id} className="step flex items-baseline gap-3" data-state={step.state}>
          <span className="mt-0.5 w-4 shrink-0 text-muted" aria-hidden>
            {step.state === "done" ? (
              <Check size={16} className="text-ok" />
            ) : step.state === "skipped" ? (
              <Minus size={16} />
            ) : (
              <Circle size={10} className={step.state === "pending" ? "opacity-40" : ""} />
            )}
          </span>
          <span className={step.state === "pending" ? "text-muted" : ""}>
            <span className="step-label font-medium">{step.label}</span>
            {step.state === "skipped" && !step.note ? <span className="ml-2 text-sm text-muted">not needed</span> : null}
            {step.note ? <span className="ml-2 text-sm text-muted">{step.note}</span> : null}
          </span>
        </li>
      ))}
    </ol>
  );
}
