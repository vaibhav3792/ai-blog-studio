export type BlogStatus = "queued" | "running" | "complete" | "failed";

export interface BlogSummary {
  id: number;
  topic: string;
  title: string;
  status: BlogStatus;
  mode: string | null;
  word_count: number;
  created_at: string;
  updated_at: string;
}

export interface EvidenceItem {
  title: string;
  url: string;
  published_at?: string | null;
  snippet?: string | null;
  source?: string | null;
}

export interface BlogDetail extends BlogSummary {
  markdown: string;
  error: string | null;
  evidence: EvidenceItem[];
  warnings: string[];
  images: string[];
}

export interface Health {
  status: string;
  providers: { groq: boolean; tavily: boolean; cloudflare_images: boolean };
  models: { main: string; fast: string; image: string };
  auth: { required: boolean; ok: boolean };
}

export type NodeName =
  | "router"
  | "research"
  | "orchestrator"
  | "worker"
  | "merge_content"
  | "decide_images"
  | "generate_and_place_images";

export type RunEvent =
  | { type: "started"; message: string }
  | { type: "node"; node: NodeName; message: string; data: Record<string, any> }
  | { type: "warning"; message: string }
  | { type: "done"; blog_id: number }
  | { type: "error"; message: string };
