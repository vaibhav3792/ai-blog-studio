import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { derivePipeline } from "../lib/pipeline";
import { useRunEvents } from "../hooks/useRunEvents";
import PipelineTracker from "../components/PipelineTracker";
import Markdown from "../components/Markdown";

const EXAMPLES = [
  "How KV caching speeds up LLM inference",
  "RAG vs fine-tuning: when each one wins",
  "This week's open-source LLM releases",
];

export default function WritePage() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const runId = params.get("run") ? Number(params.get("run")) : null;
  const [topic, setTopic] = useState("");

  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const events = useRunEvents(runId);
  const view = derivePipeline(events);

  const generate = useMutation({
    mutationFn: (t: string) => api.generate(t),
    onSuccess: (blog) => {
      setParams({ run: String(blog.id) });
      qc.invalidateQueries({ queryKey: ["blogs"] });
    },
  });

  const finished = view.outcome === "done";
  const blog = useQuery({
    queryKey: ["blog", runId],
    queryFn: () => api.getBlog(runId!),
    enabled: runId != null && finished,
  });

  const running = runId != null && view.outcome === null;
  const missingKey = health.data && !health.data.providers.groq;
  const canSubmit = topic.trim().length >= 3 && !running && !generate.isPending && !missingKey;

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
      <section>
        <h1 className="mb-4 font-serif text-2xl font-semibold tracking-tight">What should the post cover?</h1>

        {missingKey ? (
          <p className="mb-4 border-l-2 border-warn pl-3 text-sm">
            GROQ_API_KEY is missing. Add it to <code className="font-mono">backend/.env</code> and restart the backend.
          </p>
        ) : null}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit) generate.mutate(topic.trim());
          }}
        >
          <label htmlFor="topic" className="sr-only">Topic</label>
          <textarea
            id="topic"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            rows={4}
            maxLength={400}
            placeholder="A topic, a question, or a news angle"
            className="w-full resize-y rounded border border-rule bg-panel p-3 leading-relaxed"
          />
          <button
            type="submit"
            disabled={!canSubmit}
            className="mt-3 rounded bg-ink px-4 py-2 font-medium text-paper disabled:cursor-not-allowed disabled:opacity-40"
          >
            {generate.isPending ? "Starting" : "Generate post"}
          </button>
          {generate.isError ? <p className="mt-2 text-sm text-bad">{(generate.error as Error).message}</p> : null}
        </form>

        {runId == null ? (
          <div className="mt-8 text-sm text-muted">
            <p className="mb-2">Try one of these:</p>
            <ul className="m-0 list-none space-y-1 p-0">
              {EXAMPLES.map((ex) => (
                <li key={ex}>
                  <button type="button" onClick={() => setTopic(ex)} className="text-left underline underline-offset-4 hover:text-ink">
                    {ex}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="mt-8 border-t border-rule pt-6">
            <PipelineTracker view={view} />
            {view.warnings.length > 0 ? (
              <ul className="mt-5 list-none space-y-1 p-0 text-sm text-warn">
                {view.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            ) : null}
          </div>
        )}
      </section>

      <section className="min-w-0">
        {runId == null ? (
          <p className="max-w-prose text-muted">
            The draft appears here. Posts that need current information are researched first, then outlined,
            written section by section, and illustrated.
          </p>
        ) : view.outcome === "error" ? (
          <div className="max-w-prose border-l-2 border-bad pl-4">
            <h2 className="mb-1 font-serif text-xl font-semibold">Generation stopped</h2>
            <p className="m-0">{view.error}</p>
          </div>
        ) : finished && blog.data ? (
          <>
            <div className="mb-6 flex items-center gap-4 border-b border-rule pb-4">
              <Link to={`/blogs/${blog.data.id}`} className="rounded bg-ink px-4 py-2 font-medium text-paper">
                Open in editor
              </Link>
              <span className="text-sm text-muted">{blog.data.word_count} words</span>
            </div>
            <Markdown source={blog.data.markdown} blogId={blog.data.id} />
          </>
        ) : view.sections.length > 0 ? (
          <div className="max-w-prose">
            <h2 className="mb-4 font-serif text-xl font-semibold">{view.title}</h2>
            <ul className="m-0 list-none space-y-2 p-0">
              {view.sections.map((s) => (
                <li key={s.id} className={s.done ? "" : "text-muted"}>
                  {s.title}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-muted">Working on the outline. Sections will be listed here as soon as it is ready.</p>
        )}
      </section>
    </div>
  );
}
