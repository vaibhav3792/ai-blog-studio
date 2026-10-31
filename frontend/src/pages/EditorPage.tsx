import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Download, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { formatDate, readingMinutes } from "../lib/format";
import Markdown from "../components/Markdown";

type View = "edit" | "split" | "preview";

export default function EditorPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const blog = useQuery({ queryKey: ["blog", id], queryFn: () => api.getBlog(id) });

  const [title, setTitle] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [view, setView] = useState<View>("split");

  useEffect(() => {
    if (blog.data) {
      setTitle(blog.data.title);
      setMarkdown(blog.data.markdown);
    }
  }, [blog.data?.id, blog.data?.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = !!blog.data && (title !== blog.data.title || markdown !== blog.data.markdown);

  const save = useMutation({
    mutationFn: () => api.updateBlog(id, { title, markdown }),
    onSuccess: (data) => {
      qc.setQueryData(["blog", id], data);
      qc.invalidateQueries({ queryKey: ["blogs"] });
    },
  });

  const remove = useMutation({
    mutationFn: () => api.deleteBlog(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["blogs"] });
      navigate("/library");
    },
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (dirty && !save.isPending) save.mutate();
      }
    };
    const onLeave = (e: BeforeUnloadEvent) => {
      if (dirty) e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("beforeunload", onLeave);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("beforeunload", onLeave);
    };
  }, [dirty, save]);

  if (blog.isLoading) return <p className="text-muted">Loading post.</p>;
  if (blog.isError || !blog.data) return <p className="text-bad">Could not load this post. <Link to="/library" className="underline">Back to library</Link></p>;

  const b = blog.data;
  if (b.status !== "complete") {
    return (
      <div className="max-w-prose">
        <h1 className="mb-2 font-serif text-2xl font-semibold">{b.status === "failed" ? "This post failed to generate" : "This post is still generating"}</h1>
        {b.error ? <p className="border-l-2 border-bad pl-3">{b.error}</p> : null}
        <Link to={`/?run=${b.id}`} className="text-pencil underline underline-offset-4">View progress</Link>
      </div>
    );
  }

  const words = markdown.trim() ? markdown.trim().split(/\s+/).length : 0;
  const seg = (v: View, label: string) => (
    <button
      type="button"
      onClick={() => setView(v)}
      aria-pressed={view === v}
      className={`px-3 py-1 text-sm ${view === v ? "bg-ink text-paper" : "text-muted hover:text-ink"}`}
    >
      {label}
    </button>
  );

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          aria-label="Title"
          className="min-w-[12rem] flex-1 border-b border-transparent bg-transparent py-1 font-serif text-2xl font-semibold tracking-tight hover:border-rule focus:border-pencil"
        />
        <div className="flex overflow-hidden rounded border border-rule">{seg("edit", "Edit")}{seg("split", "Split")}{seg("preview", "Preview")}</div>
        <button
          type="button"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate()}
          className="rounded bg-ink px-4 py-1.5 font-medium text-paper disabled:opacity-40"
        >
          {save.isPending ? "Saving" : dirty ? "Save changes" : "Saved"}
        </button>
        <a href={api.exportUrl(id, "md")} className="inline-flex items-center gap-1.5 text-sm underline underline-offset-4">
          <Download size={15} /> Markdown
        </a>
        <a href={api.exportUrl(id, "zip")} className="inline-flex items-center gap-1.5 text-sm underline underline-offset-4">
          <Download size={15} /> Zip with images
        </a>
        <button
          type="button"
          aria-label="Delete post"
          onClick={() => confirm("Delete this post and its images?") && remove.mutate()}
          className="rounded p-2 text-muted hover:text-bad"
        >
          <Trash2 size={18} />
        </button>
      </div>
      <p className="mb-5 text-sm text-muted">
        {words} words, about {readingMinutes(words)} min read. Created {formatDate(b.created_at)}.
        {save.isError ? <span className="ml-2 text-bad">{(save.error as Error).message}</span> : null}
      </p>

      <div className={`grid gap-6 ${view === "split" ? "lg:grid-cols-2" : ""}`}>
        {view !== "preview" ? (
          <textarea
            value={markdown}
            onChange={(e) => setMarkdown(e.target.value)}
            spellCheck={false}
            aria-label="Markdown source"
            className="min-h-[70vh] w-full resize-y rounded border border-rule bg-panel p-4 font-mono text-[0.85rem] leading-relaxed"
          />
        ) : null}
        {view !== "edit" ? (
          <div className="min-w-0 rounded border border-rule bg-panel p-6">
            <Markdown source={markdown} blogId={id} />
          </div>
        ) : null}
      </div>

      {b.evidence.length > 0 || b.warnings.length > 0 ? (
        <div className="mt-8 max-w-3xl space-y-3 text-sm">
          {b.evidence.length > 0 ? (
            <details>
              <summary className="cursor-pointer font-medium">Sources ({b.evidence.length})</summary>
              <ul className="mt-2 list-none space-y-1.5 p-0">
                {b.evidence.map((e) => (
                  <li key={e.url}>
                    <a href={e.url} target="_blank" rel="noreferrer noopener" className="text-pencil underline underline-offset-3">{e.title}</a>
                    <span className="ml-2 text-muted">{[e.source, e.published_at].filter(Boolean).join(", ")}</span>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
          {b.warnings.length > 0 ? (
            <details open>
              <summary className="cursor-pointer font-medium">Generation notes ({b.warnings.length})</summary>
              <ul className="mt-2 list-none space-y-1 p-0 text-warn">
                {b.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </details>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
