import type { BlogStatus } from "../lib/types";

const STYLE: Record<BlogStatus, { dot: string; label: string }> = {
  queued: { dot: "bg-muted", label: "Queued" },
  running: { dot: "bg-warn", label: "Generating" },
  complete: { dot: "bg-ok", label: "Ready" },
  failed: { dot: "bg-bad", label: "Failed" },
};

export default function StatusBadge({ status }: { status: BlogStatus }) {
  const s = STYLE[status];
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-muted">
      <span className={`h-2 w-2 rounded-full ${s.dot}`} aria-hidden />
      {s.label}
    </span>
  );
}
