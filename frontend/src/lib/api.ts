import type { BlogDetail, BlogSummary, Health } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : body.detail?.[0]?.msg ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<Health>("/api/health"),
  login: (code: string) => request<{ ok: boolean }>("/api/auth", json("POST", { code })),
  listBlogs: () => request<BlogSummary[]>("/api/blogs"),
  getBlog: (id: number) => request<BlogDetail>(`/api/blogs/${id}`),
  generate: (topic: string) => request<BlogSummary>("/api/blogs/generate", json("POST", { topic })),
  updateBlog: (id: number, patch: { title?: string; markdown?: string }) =>
    request<BlogDetail>(`/api/blogs/${id}`, json("PATCH", patch)),
  deleteBlog: (id: number) => request<void>(`/api/blogs/${id}`, { method: "DELETE" }),
  eventsUrl: (id: number) => `/api/blogs/${id}/events`,
  exportUrl: (id: number, format: "md" | "zip") => `/api/blogs/${id}/export?format=${format}`,
};
