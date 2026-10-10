export type Lang = "uk" | "en" | "de";
export type I18nText = Partial<Record<Lang, string>>;

export interface User { id: number; email: string; display_name: string; language: Lang }

export interface Agent {
  id: number;
  preset: string;
  kind: "research" | "grants";
  name: I18nText;
  description: I18nText;
  instructions: string;
  tools: string[];
  skills: string[];
  sources: string[];
  org_profile: string;
  default_model: string;
  answer_language: "ui" | Lang;
  position: number;
}

export interface Provider { id: string; name: string; flow?: "device" | "code"; recommended?: boolean; connected: boolean }
export interface ProvidersResponse { oauth: Provider[]; api_key: Provider[]; connected: string[] }

export interface LoginSession {
  session_id: string; provider: string; flow: "device" | "code";
  status: "starting" | "waiting" | "verifying" | "approved" | "error" | "cancelled";
  verification_url: string; user_code: string; message: string; expires_at: number;
}

export interface Model { id: string; name: string; description: string; provider: string; connected: boolean }
export interface ModelsResponse { models: Model[]; current: string; needs_account: boolean }

export interface Step { id: string; title: string; kind: string; status: string; input: string; output: string }
export interface ChartSpec {
  type: "bar" | "hbar" | "stacked" | "line" | "area" | "share";
  title: string; subtitle: string; unit: string; x_label: string; y_label: string; source: string;
  series: { name: string; points: { x: string; y: number }[] }[];
}
export interface DashboardData { title: string; summary: string; kpis: { label: string; value: string; hint: string }[]; charts: ChartSpec[] }
export interface Artifact {
  id: string; kind: "dashboard" | "document" | "image"; title: string; filename: string; mime: string; size: number;
  caption: string; url: string; data?: DashboardData; source_url?: string;
}
export interface Message {
  id: number | string; role: "user" | "assistant"; content: string; steps: Step[]; status: string; artifacts?: Artifact[];
}
export interface Thread { id: number; agent_id: number; title: string; model_id: string; updated_at: string; busy: boolean }

export type Verdict = "fits" | "next_year" | "not_for_us";
export interface Grant {
  id: number; agent_id: number; thread_id: number | null; title: string; funder: string; amount: string;
  deadline: string; eligibility: string; verdict: Verdict; reasoning: string; url: string; updated_at: string;
}

export class ApiError extends Error {
  constructor(public status: number, public code: string) { super(code); }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "include",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let code = res.statusText;
    try {
      const data = await res.json();
      code = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch { /* not json */ }
    throw new ApiError(res.status, code);
  }
  return res.json() as Promise<T>;
}

export const api = {
  me: () => request<User>("GET", "/api/auth/me"),
  login: (email: string, password: string) => request<User>("POST", "/api/auth/login", { email, password }),
  authConfig: () => request<{ registration: boolean; invite_required: boolean }>("GET", "/api/auth/config"),
  register: (email: string, password: string, display_name: string, language: Lang, invite_code = "") =>
    request<User>("POST", "/api/auth/register", { email, password, display_name, language, invite_code }),
  logout: () => request<{ ok: boolean }>("POST", "/api/auth/logout"),
  updateMe: (patch: Partial<Pick<User, "display_name" | "language">>) => request<User>("PATCH", "/api/auth/me", patch),

  agents: () => request<Agent[]>("GET", "/api/agents"),
  agentCatalog: () => request<{ tools: string[]; skills: string[]; presets: { slug: string; name: I18nText }[] }>(
    "GET", "/api/agents/catalog"),
  createAgent: (body: Partial<Agent> & { preset?: string; copy_of?: number }) => request<Agent>("POST", "/api/agents", body),
  updateAgent: (id: number, body: Partial<Agent>) => request<Agent>("PATCH", `/api/agents/${id}`, body),
  resetAgent: (id: number) => request<Agent>("POST", `/api/agents/${id}/reset`),
  deleteAgent: (id: number) => request<{ ok: boolean }>("DELETE", `/api/agents/${id}`),

  providers: () => request<ProvidersResponse>("GET", "/api/providers"),
  startLogin: (provider: string) => request<LoginSession>("POST", `/api/providers/${provider}/login`),
  pollLogin: (sid: string) => request<LoginSession>("GET", `/api/providers/login/${sid}`),
  submitLoginCode: (sid: string, code: string) => request<LoginSession>("POST", `/api/providers/login/${sid}/code`, { code }),
  cancelLogin: (sid: string) => request<{ ok: boolean }>("DELETE", `/api/providers/login/${sid}`),
  addKey: (provider: string, api_key: string) => request<ProvidersResponse>("POST", `/api/providers/${provider}/key`, { api_key }),
  disconnect: (provider: string) => request<ProvidersResponse>("DELETE", `/api/providers/${provider}`),
  models: () => request<ModelsResponse>("GET", "/api/models"),

  threads: (agentId?: number) => request<Thread[]>("GET", `/api/threads${agentId ? `?agent_id=${agentId}` : ""}`),
  thread: (id: number) => request<Thread & { messages: Message[] }>("GET", `/api/threads/${id}`),
  createThread: (agent_id: number) => request<Thread>("POST", "/api/threads", { agent_id }),
  deleteThread: (id: number) => request<{ ok: boolean }>("DELETE", `/api/threads/${id}`),
  cancelThread: (id: number) => request<{ ok: boolean }>("POST", `/api/threads/${id}/cancel`),

  grants: (agentId?: number) => request<Grant[]>("GET", `/api/grants${agentId ? `?agent_id=${agentId}` : ""}`),
  setVerdict: (id: number, verdict: Verdict) => request<Grant>("PATCH", `/api/grants/${id}`, { verdict }),
  deleteGrant: (id: number) => request<{ ok: boolean }>("DELETE", `/api/grants/${id}`),
};

export type StreamEvent =
  | { type: "status"; state: string; model_id?: string }
  | { type: "text"; delta: string }
  | { type: "thought"; delta: string }
  | { type: "step"; step: Step }
  | { type: "plan"; entries: { content: string; status: string }[] }
  | { type: "notice"; message: string }
  | { type: "artifact"; artifact: Artifact }
  | { type: "grants"; items: { id: number; title: string; verdict: Verdict }[] }
  | { type: "done"; stop_reason: string }
  | { type: "error"; message: string };

/** POST a message and read the server-sent event stream it returns. */
export async function streamMessage(threadId: number, body: { text: string; model_id: string; language: Lang; display?: string },
                                    onEvent: (e: StreamEvent) => void, signal?: AbortSignal): Promise<void> {
  const res = await fetch(`/api/threads/${threadId}/messages`, {
    method: "POST", credentials: "include", signal,
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    let code = res.statusText;
    try { code = (await res.json()).detail; } catch { /* ignore */ }
    throw new ApiError(res.status, code);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data: ")) {
          try { onEvent(JSON.parse(line.slice(6))); } catch { /* malformed */ }
        }
      }
    }
  }
}
