export type Doc = {
  id: string; filename: string; status: string; size_bytes: number;
  pages: number; num_chunks: number; error?: string | null; created_at: string;
};
export type Source = { document_id: string; filename: string; page: number | null; chunk_id: string; score: number };
export type Metrics = {
  latency_ms: number; input_tokens: number; output_tokens: number;
  node_latency_ms: Record<string, number>; retries: number; estimated_cost_usd: number | null;
};
export type ChatResult = { run_id: string; answer: string; sources: Source[]; status: string; metrics: Metrics };
export type TraceStep = { node: string; status: string; latency_ms: number; [k: string]: unknown };
export type Run = ChatResult & { question: string; trace: TraceStep[] };
export type EvalReport = {
  metadata: Record<string, string | number>;
  summary: Record<string, number | null>;
  questions: { id: string; type: string; status: string; abstained: boolean; should_abstain: boolean; latency_ms: number }[];
};

const BASE = "/api/v1";

async function request<T>(path: string, key: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, { ...init, headers: { "X-API-Key": key, ...(init.headers || {}) } });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body?.error?.message ?? `Request failed (${res.status})`);
  return body as T;
}

export const api = {
  listDocs: (k: string) => request<Doc[]>("/documents", k),
  upload: (k: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Doc>("/documents", k, { method: "POST", body: form });
  },
  deleteDoc: (k: string, id: string) => request<void>(`/documents/${id}`, k, { method: "DELETE" }),
  chat: (k: string, question: string, document_ids: string[]) =>
    request<ChatResult>("/chat", k, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, document_ids: document_ids.length ? document_ids : null }),
    }),
  run: (k: string, id: string) => request<Run>(`/runs/${id}`, k),
  runEval: (k: string) => request<EvalReport>("/evaluations/run", k, { method: "POST" }),
  latestEval: (k: string) => request<EvalReport>("/evaluations/latest", k),
};
