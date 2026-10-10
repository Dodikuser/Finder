import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "motion/react";
import { api, ApiError, streamMessage, type Agent, type Artifact, type Lang, type Message, type Model, type Step, type StreamEvent } from "../api";
import Artifacts from "../components/Artifacts";
import Markdown from "../components/Markdown";
import { IconAlert, IconArrow, IconBoard, IconChart, IconChat, IconCheck, IconClose, IconFile, IconKey, IconPlus, IconStop, IconTrash } from "../components/Icons";
import { cx, ease, pick } from "../lib";

interface Live {
  content: string; thought: string; steps: Step[]; status: "running" | "done" | "error" | "cancelled"; error?: string;
  notices: string[]; grants: number; artifacts: Artifact[];
}

const modelKey = (agentId: number) => `finder.model.${agentId}`;

export default function Chat() {
  const params = useParams();
  const agents = useQuery({ queryKey: ["agents"], queryFn: api.agents });
  if (!params.agentId) {
    if (agents.data?.length) return <Navigate to={`/chat/${agents.data[0].id}`} replace />;
    return null;
  }
  const agent = agents.data?.find((a) => a.id === Number(params.agentId));
  if (agents.data && !agent) return <Navigate to="/chat" replace />;
  if (!agent) return null;
  return <ChatView key={agent.id} agent={agent} threadId={params.threadId ? Number(params.threadId) : null} />;
}

function ChatView({ agent, threadId }: { agent: Agent; threadId: number | null }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language as Lang;
  const qc = useQueryClient();
  const navigate = useNavigate();
  const models = useQuery({ queryKey: ["models"], queryFn: api.models, staleTime: 60_000 });
  const thread = useQuery({ queryKey: ["thread", threadId], queryFn: () => api.thread(threadId!), enabled: !!threadId });
  const [messages, setMessages] = useState<Message[]>([]);
  const [live, setLive] = useState<Live | null>(null);
  const [text, setText] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const streaming = useRef(false);
  const activeThread = useRef<number | null>(threadId);
  const scroller = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const [model, setModel] = useState<string>(() => {
    try { return localStorage.getItem(modelKey(agent.id)) || ""; } catch { return ""; }
  });

  const available = useMemo(() => (models.data?.models || []).filter((m) => m.connected), [models.data]);
  const effectiveModel = useMemo(() => {
    const candidates = [model, thread.data?.model_id, agent.default_model, models.data?.current];
    return candidates.find((c) => c && available.some((m) => m.id === c)) || available[0]?.id || "";
  }, [model, thread.data, agent.default_model, models.data, available]);

  useEffect(() => { activeThread.current = threadId; }, [threadId]);

  // "Run analysis" on the grants board opens the chat with a prepared prompt.
  const [search, setSearch] = useSearchParams();
  const autoSent = useRef(false);
  useEffect(() => {
    const q = search.get("q");
    if (!q || autoSent.current || threadId || models.isLoading) return;
    autoSent.current = true;
    setSearch({}, { replace: true });
    if (!models.data?.needs_account) send(q);
    else setText(q);
  }, [search, models.isLoading]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!streaming.current) setMessages(threadId ? thread.data?.messages || [] : []);
  }, [thread.data, threadId]);

  useEffect(() => {
    const el = scroller.current;
    if (el && pinned.current) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, live]);

  function onEvent(e: StreamEvent) {
    setLive((prev) => {
      if (!prev) return prev;
      switch (e.type) {
        case "text": return { ...prev, content: prev.content + e.delta };
        case "thought": return { ...prev, thought: (prev.thought + e.delta).slice(-600) };
        case "step": {
          const i = prev.steps.findIndex((s) => s.id === e.step.id);
          const steps = i >= 0 ? prev.steps.map((s, j) => (j === i ? e.step : s)) : [...prev.steps, e.step];
          return { ...prev, steps };
        }
        case "notice": return { ...prev, notices: [...prev.notices, e.message] };
        case "artifact": return prev.artifacts.some((a) => a.id === e.artifact.id) ? prev : { ...prev, artifacts: [...prev.artifacts, e.artifact] };
        case "grants": return { ...prev, grants: e.items.length };
        case "done": return { ...prev, status: e.stop_reason === "cancelled" ? "cancelled" : "done" };
        case "error": return { ...prev, status: "error", error: e.message };
        default: return prev;
      }
    });
  }

  /** `display`: what the chat shows when a button sends a longer instruction to the agent. */
  async function send(raw: string, display?: string) {
    const body = raw.trim();
    if (!body || streaming.current) return;
    streaming.current = true;
    pinned.current = true;
    setText("");
    let tid = threadId;
    try {
      if (!tid) {
        const th = await api.createThread(agent.id);
        tid = th.id;
        activeThread.current = tid;
        navigate(`/chat/${agent.id}/${tid}`, { replace: true });
      }
      setMessages((prev) => [...prev, { id: `u${Date.now()}`, role: "user", content: display || body, steps: [], status: "done" }]);
      setLive({ content: "", thought: "", steps: [], status: "running", notices: [], grants: 0, artifacts: [] });
      await streamMessage(tid, { text: body, model_id: effectiveModel, language: lang, display }, onEvent);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : String(err);
      setLive((prev) => ({ ...(prev || { content: "", thought: "", steps: [], notices: [], grants: 0, artifacts: [] }), status: "error",
                           error: code === "needs_account" ? t("chat.needsAccount") : code }));
    } finally {
      streaming.current = false;
      if (tid) {
        const fresh = await api.thread(tid).catch(() => null);
        if (fresh && activeThread.current === tid) {
          qc.setQueryData(["thread", tid], fresh);
          setMessages(fresh.messages);
          setLive((prev) => (prev && prev.status === "error" ? prev : null));
        }
      }
      qc.invalidateQueries({ queryKey: ["threads", agent.id] });
      qc.invalidateQueries({ queryKey: ["grants"] });
    }
  }

  function submit(e: FormEvent) { e.preventDefault(); send(text); }
  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(text); }
  }
  function chooseModel(id: string) {
    setModel(id);
    try { localStorage.setItem(modelKey(agent.id), id); } catch { /* storage unavailable */ }
  }

  const running = live?.status === "running";
  const needsAccount = models.data?.needs_account;
  const suggestions = (t(`chat.suggestions.${agent.preset}`, { returnObjects: true, defaultValue: [] }) as unknown as string[]) || [];
  const empty = messages.length === 0 && !live;
  // Offer "show analytics / make a PDF" once the agent has given a real answer and is idle.
  const last = messages[messages.length - 1];
  const canFollowUp = !running && !needsAccount && (!live || live.status === "done") && last?.role === "assistant"
    && last.status === "done" && last.content.trim().length > 200;
  const lastHasDashboard = !!last?.artifacts?.some((a) => a.kind === "dashboard");

  return (
    <div className="h-full flex">
      <div className="flex-1 min-w-0 flex flex-col h-full">
        <header className="flex flex-wrap items-center justify-between gap-3 px-5 sm:px-8 py-4 border-b border-line bg-surface/70 backdrop-blur">
          <div className="flex flex-col gap-0.5 min-w-0">
            <div className="font-bold text-lg truncate">{pick(agent.name, lang)}</div>
            <div className="text-[13px] text-muted truncate">{pick(agent.description, lang)}</div>
          </div>
          <div className="flex items-center gap-2 min-w-0 max-w-full">
            <ModelPicker models={available} loading={models.isLoading} value={effectiveModel} onChange={chooseModel} />
            <button onClick={() => setHistoryOpen((v) => !v)} aria-expanded={historyOpen} title={t("chat.history")}
                    className={cx("xl:hidden w-11 h-11 flex items-center justify-center rounded-xl border border-line cursor-pointer", historyOpen ? "bg-tint text-brand-deep" : "bg-surface text-ink-2 hover:bg-soft")}>
              <IconChat size={18} />
            </button>
          </div>
        </header>

        <div ref={scroller} className="flex-1 overflow-y-auto"
             onScroll={(e) => { const el = e.currentTarget; pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120; }}>
          <div className="max-w-[900px] mx-auto px-4 sm:px-8 py-8 flex flex-col gap-6">
            {needsAccount && <NeedsAccount />}
            {empty && !needsAccount && (
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease }}
                          className="flex flex-col items-center text-center gap-3 pt-10">
                <div className="w-14 h-14 rounded-2xl bg-tint text-brand-deep flex items-center justify-center"><IconChat size={26} /></div>
                <h2 className="m-0 text-2xl font-bold tracking-tight">{t("chat.emptyTitle")}</h2>
                <p className="m-0 text-muted max-w-md">{t("chat.emptyHint")}</p>
                <div className="flex flex-wrap justify-center gap-2 mt-4 max-w-2xl">
                  {suggestions.map((s, i) => (
                    <motion.button key={s} onClick={() => send(s)} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                                   transition={{ delay: 0.15 + i * 0.08, duration: 0.4, ease }}
                                   className="text-sm text-left px-4 py-2.5 rounded-2xl bg-surface border border-line hover:border-brand hover:-translate-y-0.5 transition cursor-pointer">
                      {s}
                    </motion.button>
                  ))}
                </div>
              </motion.div>
            )}
            {messages.map((m) => <MessageView key={m.id} m={m} />)}
            {live && <LiveView live={live} />}
            {canFollowUp && (
              <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease, delay: 0.15 }}
                          className="flex flex-wrap gap-2">
                {!lastHasDashboard && (
                  <button onClick={() => send(t("analytics.prompt"), t("analytics.button"))}
                          className="flex items-center gap-2 px-4 py-2.5 rounded-full bg-night text-night-ink text-sm font-semibold cursor-pointer transition hover:-translate-y-0.5 hover:shadow-lg">
                    <IconChart size={17} className="text-glow" />{t("analytics.button")}
                  </button>
                )}
                <button onClick={() => send(t("analytics.pdfPrompt"), t("analytics.pdfButton"))}
                        className="flex items-center gap-2 px-4 py-2.5 rounded-full bg-surface border border-line-strong text-brand-ink text-sm font-semibold cursor-pointer transition hover:-translate-y-0.5 hover:bg-soft">
                  <IconFile size={17} />{t("analytics.pdfButton")}
                </button>
              </motion.div>
            )}
          </div>
        </div>

        <footer className="px-4 sm:px-8 pb-6 pt-3">
          <form onSubmit={submit}
                className="max-w-[900px] mx-auto flex items-end gap-2.5 py-2.5 pr-2.5 pl-5 rounded-[22px] bg-surface border-[1.5px] border-line-strong shadow-[0_10px_30px_rgba(17,134,106,0.10)] focus-within:border-brand transition">
            <label htmlFor="msg" className="sr-only">{t("chat.placeholder")}</label>
            <textarea id="msg" rows={1} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKey}
                      placeholder={t("chat.placeholder")} disabled={needsAccount}
                      className="flex-1 resize-none border-none outline-none bg-transparent text-[15px] py-2.5 text-ink max-h-48 [field-sizing:content]" />
            {running && (
              <button type="button" aria-label={t("chat.stop")} title={t("chat.stop")} onClick={() => threadId && api.cancelThread(threadId)}
                      className="w-11 h-11 rounded-[14px] bg-soft text-brand-deep flex items-center justify-center cursor-pointer hover:bg-tint transition">
                <IconStop size={16} />
              </button>
            )}
            <button type="submit" aria-label={t("chat.send")} title={t("chat.send")} disabled={!text.trim() || running || needsAccount}
                    className="w-11 h-11 rounded-[14px] bg-brand text-white flex items-center justify-center cursor-pointer transition hover:brightness-110 disabled:opacity-40 disabled:cursor-default">
              <IconArrow size={18} strokeWidth={2.2} />
            </button>
          </form>
        </footer>
      </div>

      <History agentId={agent.id} threadId={threadId} open={historyOpen} onClose={() => setHistoryOpen(false)} />
    </div>
  );
}

function ModelPicker({ models, loading, value, onChange }: { models: Model[]; loading: boolean; value: string; onChange: (id: string) => void }) {
  const { t } = useTranslation();
  return (
    <label className="flex items-center gap-2.5 py-1.5 pr-1.5 pl-3.5 rounded-full bg-surface border border-line text-sm min-w-0 max-w-full">
      <span className={cx("w-2 h-2 rounded-full", models.length ? "bg-brand" : "bg-slate-dot")} />
      <span className="text-muted hidden sm:inline">{t("chat.model")}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} disabled={!models.length}
              className="min-w-0 w-full max-w-[230px] border-none bg-soft rounded-full px-3 py-1.5 font-semibold text-brand-deep text-sm cursor-pointer outline-none">
        {loading && <option>{t("chat.loadingModels")}</option>}
        {!loading && !models.length && <option>{t("chat.noModels")}</option>}
        {models.map((m) => <option key={m.id} value={m.id}>{m.name.replace(/^.*?·\s*/, "")} · {m.provider}</option>)}
      </select>
    </label>
  );
}

function NeedsAccount() {
  const { t } = useTranslation();
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                className="flex flex-wrap items-center gap-4 p-5 rounded-[20px] bg-night text-night-ink">
      <div className="w-11 h-11 rounded-xl bg-night-2 text-glow flex items-center justify-center"><IconKey /></div>
      <div className="flex-1 min-w-[200px] text-[15px]">{t("chat.needsAccount")}</div>
      <Link to="/accounts" className="px-4 py-2.5 rounded-xl bg-glow text-night font-bold no-underline hover:brightness-105">{t("chat.connect")}</Link>
    </motion.div>
  );
}

function MessageView({ m }: { m: Message }) {
  const { t } = useTranslation();
  if (m.role === "user") {
    return (
      <motion.div layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease }}
                  className="self-end max-w-[85%] sm:max-w-[560px] px-[18px] py-3.5 rounded-[20px_20px_6px_20px] bg-brand text-white text-[15px] leading-relaxed whitespace-pre-wrap">
        {m.content}
      </motion.div>
    );
  }
  return (
    <motion.div layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease }} className="flex flex-col gap-3">
      {m.steps?.length > 0 && <Timeline steps={m.steps} running={false} collapsedByDefault />}
      {!!m.artifacts?.length && <Artifacts items={m.artifacts} />}
      {(m.content || m.status !== "done") && (
        <div className="px-6 py-5 rounded-[20px_20px_20px_6px] bg-surface border border-line">
          {m.content ? <Markdown text={m.content} /> : null}
          {m.status === "cancelled" && <div className="text-sm text-muted mt-2">{t("chat.cancelled")}</div>}
          {m.status === "error" && <div className="text-sm text-danger-ink mt-2">{t("chat.failed")}</div>}
        </div>
      )}
    </motion.div>
  );
}

function LiveView({ live }: { live: Live }) {
  const { t } = useTranslation();
  const running = live.status === "running";
  return (
    <div className="flex flex-col gap-3">
      {(live.steps.length > 0 || running) && <Timeline steps={live.steps} running={running} thought={live.thought} />}
      {live.notices.map((n, i) => (
        <div key={i} className="text-sm px-4 py-2.5 rounded-xl bg-amber-bg text-amber-ink">{t("chat.blocked")} ({n})</div>
      ))}
      {live.content && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                    className="px-6 py-5 rounded-[20px_20px_20px_6px] bg-surface border border-line">
          <Markdown text={live.content} />
          {running && <span className="inline-block w-2 h-4 align-middle ml-0.5 bg-brand animate-pulse rounded-sm" />}
        </motion.div>
      )}
      {live.artifacts.length > 0 && <Artifacts items={live.artifacts} />}
      {live.grants > 0 && (
        <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }}
                    className="flex items-center gap-3 px-5 py-3.5 rounded-2xl bg-tint text-brand-deep">
          <IconBoard /> <span className="flex-1 text-sm font-semibold">{t("chat.grantsSaved", { count: live.grants })}</span>
          <Link to="/grants" className="text-sm font-bold">{t("chat.openBoard")} →</Link>
        </motion.div>
      )}
      {live.status === "error" && (
        <div className="flex items-start gap-3 px-5 py-4 rounded-2xl bg-danger-bg text-danger-ink text-sm" role="alert">
          <IconAlert className="shrink-0 mt-0.5" /> <span className="break-words">{live.error}</span>
        </div>
      )}
    </div>
  );
}

function stepLabel(s: Step): { tool: string; detail: string } {
  const title = s.title || s.kind || "tool";
  const m = title.match(/^(?:mcp[_:.-]+)?(?:finder[-_]reach[_:.-]+)?([\w.-]+)[:\s]*(.*)$/i);
  const tool = (m?.[1] || title).replace(/^mcp_finder_reach_/, "");
  let detail = m?.[2] || "";
  if (!detail && s.input) {
    try {
      const obj = JSON.parse(s.input);
      detail = String(obj.query ?? obj.url ?? obj.keyword ?? obj.pmids ?? obj.video ?? Object.values(obj)[0] ?? "");
    } catch { detail = s.input; }
  }
  return { tool, detail };
}

function Timeline({ steps, running, thought, collapsedByDefault }: { steps: Step[]; running: boolean; thought?: string; collapsedByDefault?: boolean }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(!collapsedByDefault);
  return (
    <motion.div layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease }}
                className="flex flex-col gap-2.5 px-5 py-4 rounded-[20px] bg-surface border border-line">
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open}
              className="flex items-center justify-between cursor-pointer text-left">
        <span className="text-[13px] font-semibold tracking-[0.06em] uppercase text-muted flex items-center gap-2">
          {running && <span className="w-2 h-2 rounded-full bg-brand animate-[var(--animate-pulse-ring)]" />}
          {running ? t("chat.working") : t("chat.didSteps")}
        </span>
        <span className="text-[13px] text-muted">{t("chat.steps", { count: steps.length })}</span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.ol initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                     transition={{ duration: 0.3, ease }} className="flex flex-col gap-2 m-0 p-0 list-none overflow-hidden">
            {steps.map((s) => {
              const { tool, detail } = stepLabel(s);
              const done = s.status === "completed";
              const failed = s.status === "failed";
              return (
                <motion.li key={s.id} layout initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.35, ease }}
                           className="text-sm">
                  <details className="group">
                    <summary className="flex items-center gap-3 cursor-pointer list-none [&::-webkit-details-marker]:hidden">
                      {done ? (
                        <motion.span initial={{ scale: 0.4 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 450 }}
                                     className="w-[22px] h-[22px] shrink-0 rounded-full bg-tint text-brand-deep flex items-center justify-center"><IconCheck size={12} /></motion.span>
                      ) : failed ? (
                        <span className="w-[22px] h-[22px] shrink-0 rounded-full bg-danger-bg text-danger-ink flex items-center justify-center"><IconClose size={12} /></span>
                      ) : (
                        <span className="w-[22px] h-[22px] shrink-0 rounded-full bg-brand animate-[var(--animate-pulse-ring)]" />
                      )}
                      <span className="font-mono text-[13px] text-brand-deep shrink-0">{tool}</span>
                      <span className="text-muted truncate min-w-0">{detail}</span>
                    </summary>
                    {s.output && (
                      <pre className="mt-2 ml-[34px] text-xs whitespace-pre-wrap break-words font-mono bg-soft text-ink-2 rounded-xl p-3 max-h-48 overflow-auto">{s.output}</pre>
                    )}
                  </details>
                </motion.li>
              );
            })}
            {running && (
              <li className="flex items-center gap-3 text-sm">
                <span className="w-[22px] h-[22px] shrink-0 rounded-full border-2 border-line border-t-brand animate-spin" />
                <span className="shimmer h-2.5 w-40 rounded-md" />
                {thought && <span className="text-xs text-muted truncate italic">{thought.split("\n").pop()}</span>}
              </li>
            )}
          </motion.ol>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function History({ agentId, threadId, open, onClose }: { agentId: number; threadId: number | null; open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const threads = useQuery({ queryKey: ["threads", agentId], queryFn: () => api.threads(agentId) });

  async function remove(id: number) {
    await api.deleteThread(id);
    qc.invalidateQueries({ queryKey: ["threads", agentId] });
    if (id === threadId) navigate(`/chat/${agentId}`);
  }

  return (
    <aside className={cx("w-[272px] shrink-0 border-l border-line bg-surface flex-col h-full",
                         open ? "flex fixed right-0 inset-y-0 z-20 shadow-2xl xl:static xl:shadow-none" : "hidden xl:flex")}>
      <div className="flex items-center justify-between px-4 py-4">
        <div className="text-xs font-semibold tracking-[0.08em] uppercase text-muted">{t("chat.history")}</div>
        <button onClick={onClose} className="xl:hidden w-9 h-9 flex items-center justify-center rounded-lg hover:bg-soft" aria-label={t("common.close")}><IconClose size={16} /></button>
      </div>
      <div className="px-3">
        <Link to={`/chat/${agentId}`} onClick={onClose}
              className="flex items-center gap-2 px-3 py-2.5 rounded-xl border-[1.5px] border-dashed border-line-strong text-brand-ink text-sm font-semibold no-underline hover:bg-soft">
          <IconPlus size={16} /> {t("chat.newChat")}
        </Link>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-3 flex flex-col gap-1">
        <AnimatePresence initial={false}>
          {(threads.data || []).map((th) => (
            <motion.div key={th.id} layout initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }}
                        className={cx("group flex items-center gap-1 rounded-xl transition-colors", th.id === threadId ? "bg-tint" : "hover:bg-soft")}>
              <Link to={`/chat/${agentId}/${th.id}`} onClick={onClose}
                    className={cx("flex-1 min-w-0 px-3 py-2.5 text-sm no-underline truncate", th.id === threadId ? "text-brand-deep font-semibold" : "text-ink-2")}>
                {th.title || "…"}
              </Link>
              <button onClick={() => remove(th.id)} aria-label={t("chat.deleteChat")} title={t("chat.deleteChat")}
                      className="opacity-0 group-hover:opacity-100 focus:opacity-100 w-8 h-8 mr-1 flex items-center justify-center rounded-lg text-muted hover:text-danger-ink cursor-pointer">
                <IconTrash size={15} />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </aside>
  );
}
