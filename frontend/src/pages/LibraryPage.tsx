import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import StatusBadge from "../components/StatusBadge";

export default function LibraryPage() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["blogs"], queryFn: api.listBlogs });
  const remove = useMutation({
    mutationFn: api.deleteBlog,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["blogs"] }),
  });

  return (
    <div className="max-w-4xl">
      <h1 className="mb-6 font-serif text-2xl font-semibold tracking-tight">Library</h1>

      {list.isLoading ? <p className="text-muted">Loading posts.</p> : null}
      {list.isError ? <p className="text-bad">Could not load posts: {(list.error as Error).message}</p> : null}
      {list.data?.length === 0 ? (
        <p className="text-muted">
          No posts yet. <Link to="/" className="text-pencil underline underline-offset-4">Write the first one.</Link>
        </p>
      ) : null}

      <ul className="m-0 list-none divide-y divide-rule border-y border-rule p-0">
        {list.data?.map((b) => (
          <li key={b.id} className="flex items-center gap-4 py-4">
            <div className="min-w-0 flex-1">
              <Link
                to={b.status === "complete" ? `/blogs/${b.id}` : `/?run=${b.id}`}
                className="block truncate font-serif text-lg font-semibold hover:underline"
              >
                {b.title || b.topic}
              </Link>
              <p className="m-0 truncate text-sm text-muted">{b.topic}</p>
            </div>
            <div className="hidden w-28 shrink-0 sm:block"><StatusBadge status={b.status} /></div>
            <div className="hidden w-24 shrink-0 text-sm text-muted md:block">
              {b.word_count > 0 ? `${b.word_count} words` : ""}
            </div>
            <div className="hidden w-40 shrink-0 text-sm text-muted lg:block">{formatDate(b.created_at)}</div>
            <button
              type="button"
              aria-label={`Delete ${b.title || b.topic}`}
              disabled={b.status === "running" || b.status === "queued"}
              onClick={() => {
                if (confirm("Delete this post and its images?")) remove.mutate(b.id);
              }}
              className="rounded p-2 text-muted hover:text-bad disabled:opacity-30"
            >
              <Trash2 size={18} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
