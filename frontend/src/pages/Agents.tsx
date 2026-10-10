import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "motion/react";
import { api, type Agent, type Lang } from "../api";
import { IconAlert, IconCheck, IconChat, IconShield, IconTrash } from "../components/Icons";
import { cx, ease, pick } from "../lib";

const LANGS: Lang[] = ["uk", "en", "de"];

export default function Agents() {
  const { agentId } = useParams();
  const agents = useQuery({ queryKey: ["agents"], queryFn: api.agents });
  const qc = useQueryClient();
  const navigate = useNavigate();
  const creating = useRef(false);

  useEffect(() => {
    if (agentId !== "new" || creating.current) return;
    creating.current = true;
    api.createAgent({}).then((a) => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      navigate(`/agents/${a.id}`, { replace: true });
    }).finally(() => { creating.current = false; });
  }, [agentId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (agentId === "new" || !agents.data) return <div className="p-10"><div className="shimmer h-40 rounded-3xl" /></div>;
  if (!agentId) return agents.data.length ? <Navigate to={`/agents/${agents.data[0].id}`} replace /> : null;
  const agent = agents.data.find((a) => a.id === Number(agentId));
  if (!agent) return <Navigate to="/agents" replace />;
  return <Editor key={agent.id} agent={agent} all={agents.data} />;
}

function Editor({ agent, all }: { agent: Agent; all: Agent[] }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const catalog = useQuery({ queryKey: ["agent-catalog"], queryFn: api.agentCatalog, staleTime: Infinity });
  const models = useQuery({ queryKey: ["models"], queryFn: api.models, staleTime: 60_000 });
  const [draft, setDraft] = useState<Agent>(agent);
  const [nameLang, setNameLang] = useState<Lang>((i18n.language as Lang) || "uk");
  const [sources, setSources] = useState(agent.sources.join("\n"));
  const [savedAt, setSavedAt] = useState(0);

  const set = <K extends keyof Agent>(k: K, v: Agent[K]) => setDraft((d) => ({ ...d, [k]: v }));
  const toggle = (k: "tools" | "skills", v: string) =>
    setDraft((d) => ({ ...d, [k]: d[k].includes(v) ? d[k].filter((x) => x !== v) : [...d[k], v] }));

  const afterSave = (a: Agent) => {
    qc.setQueryData<Agent[]>(["agents"], (list) => list?.map((x) => (x.id === a.id ? a : x)));
    setDraft(a);
    setSources(a.sources.join("\n"));
    setSavedAt(Date.now());
  };
  const save = useMutation({
    mutationFn: () => api.updateAgent(agent.id, {
      name: draft.name, description: draft.description, instructions: draft.instructions, tools: draft.tools,
      skills: draft.skills, sources: sources.split("\n").map((s) => s.trim()).filter(Boolean), org_profile: draft.org_profile,
      default_model: draft.default_model, answer_language: draft.answer_language, kind: draft.kind,
    }),
    onSuccess: afterSave,
  });
  const reset = useMutation({ mutationFn: () => api.resetAgent(agent.id), onSuccess: afterSave });
  const duplicate = useMutation({
    mutationFn: () => api.createAgent({ copy_of: agent.id }),
    onSuccess: (a) => { qc.invalidateQueries({ queryKey: ["agents"] }); navigate(`/agents/${a.id}`); },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteAgent(agent.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["agents"] }); navigate("/agents"); },
  });

  // Deep link from the grants board: /agents/:id#org-profile
  useEffect(() => {
    if (location.hash !== "#org-profile") return;
    const timer = setTimeout(() => {
      document.getElementById("org-profile")?.scrollIntoView({ behavior: "smooth", block: "center" });
      document.getElementById("org")?.focus({ preventScroll: true });
    }, 400);
    return () => clearTimeout(timer);
  }, []);

  const justSaved = Date.now() - savedAt < 2500;
  const field = "w-full box-border font-[inherit] text-[15px] px-4 py-3 rounded-[14px] border-[1.5px] border-line bg-ground text-ink outline-none transition focus:border-brand focus:bg-surface focus:shadow-[0_0_0_4px_var(--c-soft)]";
  const connectedModels = (models.data?.models || []).filter((m) => m.connected);

  return (
    <div className="px-5 sm:px-10 py-8 flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          <h1 className="m-0 text-[30px] font-bold tracking-tight">{t("agents.title")}</h1>
          <p className="m-0 text-[15px] text-muted">{t("agents.subtitle")}</p>
        </div>
        <div className="flex flex-wrap gap-2.5">
          <Link to={`/chat/${agent.id}`} className="flex items-center gap-2 px-4 py-3 rounded-[14px] border border-line-strong text-brand-ink font-semibold text-sm no-underline hover:bg-soft">
            <IconChat size={16} />{t("agents.openChat")}
          </Link>
          <button onClick={() => duplicate.mutate()} className="px-[18px] py-3 rounded-[14px] border border-line-strong text-brand-ink font-semibold text-sm cursor-pointer hover:bg-soft">
            {t("agents.duplicate")}
          </button>
          <button onClick={() => save.mutate()} disabled={save.isPending}
                  className="relative overflow-hidden min-w-[160px] px-[22px] py-3 rounded-[14px] bg-brand text-white font-bold text-sm cursor-pointer shadow-[0_10px_24px_rgba(17,134,106,0.25)] hover:brightness-110 disabled:opacity-70">
            <AnimatePresence mode="wait" initial={false}>
              <motion.span key={justSaved ? "ok" : "save"} className="flex items-center justify-center gap-2"
                           initial={{ y: 14, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -14, opacity: 0 }} transition={{ duration: 0.25 }}>
                {justSaved ? <><IconCheck size={14} />{t("agents.saved")}</> : t("agents.save")}
              </motion.span>
            </AnimatePresence>
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {all.map((a) => (
          <Link key={a.id} to={`/agents/${a.id}`}
                className={cx("px-3.5 py-2 rounded-full text-sm no-underline border transition", a.id === agent.id ? "bg-tint border-transparent text-brand-deep font-semibold" : "border-line text-ink-2 hover:bg-soft")}>
            {pick(a.name, i18n.language)}
          </Link>
        ))}
      </div>

      <div className="flex flex-wrap gap-6 items-start">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease }}
                    className="flex-[999_1_520px] min-w-0 flex flex-col gap-5 p-6 sm:p-[26px] rounded-[22px] bg-surface border border-line">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <label htmlFor="nm" className="font-semibold text-sm">{t("agents.name")}</label>
              <div className="flex gap-1 p-[3px] rounded-[10px] bg-soft text-xs" role="group">
                {LANGS.map((l) => (
                  <button key={l} type="button" onClick={() => setNameLang(l)} aria-pressed={nameLang === l}
                          className={cx("px-2.5 py-1 rounded-lg cursor-pointer", nameLang === l ? "bg-surface font-semibold text-brand-deep" : "text-ink-2")}>{l.toUpperCase()}</button>
                ))}
              </div>
            </div>
            <input id="nm" className={field} value={draft.name[nameLang] || ""} onChange={(e) => set("name", { ...draft.name, [nameLang]: e.target.value })} />
            <input aria-label={t("agents.description")} placeholder={t("agents.description")} className={cx(field, "text-sm")}
                   value={draft.description[nameLang] || ""} onChange={(e) => set("description", { ...draft.description, [nameLang]: e.target.value })} />
          </div>

          <AnimatePresence initial={false}>
            {draft.kind === "grants" && (
              <motion.div id="org-profile" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                          className="flex flex-col gap-2 overflow-hidden p-4 -mx-1 rounded-2xl bg-soft border border-line-strong">
                <label htmlFor="org" className="font-semibold text-sm">{t("agents.orgProfile")} <span className="font-normal text-muted">{t("agents.orgHint")}</span></label>
                {/\[[^\]]+\]/.test(draft.org_profile) && (
                  <div className="flex items-start gap-2 text-[13px] px-3 py-2 rounded-xl bg-amber-bg text-amber-ink">
                    <IconAlert size={16} className="shrink-0 mt-0.5" />{t("agents.orgTemplateWarning")}
                  </div>
                )}
                <textarea id="org" rows={8} className={cx(field, "text-sm leading-relaxed resize-y bg-surface")} value={draft.org_profile}
                          onChange={(e) => set("org_profile", e.target.value)} />
              </motion.div>
            )}
          </AnimatePresence>

          <div className="flex flex-col gap-2">
            <label htmlFor="ins" className="font-semibold text-sm">{t("agents.instructions")}</label>
            <textarea id="ins" rows={9} className={cx(field, "text-sm leading-relaxed resize-y")} value={draft.instructions}
                      onChange={(e) => set("instructions", e.target.value)} />
          </div>

          <Chips label={t("agents.tools")} items={catalog.data?.tools || []} selected={draft.tools} onToggle={(v) => toggle("tools", v)} mono />
          <Chips label={t("agents.skills")} items={catalog.data?.skills || []} selected={draft.skills} onToggle={(v) => toggle("skills", v)} />

          <div className="flex flex-col gap-2">
            <label htmlFor="src" className="font-semibold text-sm">{t("agents.sources")} <span className="font-normal text-muted">{t("agents.sourcesHint")}</span></label>
            <textarea id="src" rows={5} className={cx(field, "font-mono text-[13px] leading-7 resize-y")} value={sources} onChange={(e) => setSources(e.target.value)} />
          </div>
        </motion.div>

        <div className="flex-[1_1_300px] max-w-[380px] flex flex-col gap-4">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1, duration: 0.45, ease }}
                      className="p-[22px] rounded-[22px] bg-surface border border-line flex flex-col gap-3">
            <label htmlFor="kind" className="font-semibold text-sm">{t("agents.kind")}</label>
            <select id="kind" className={cx(field, "text-sm")} value={draft.kind} onChange={(e) => set("kind", e.target.value as Agent["kind"])}>
              <option value="research">{t("agents.kindResearch")}</option>
              <option value="grants">{t("agents.kindGrants")}</option>
            </select>
            <label htmlFor="md" className="font-semibold text-sm">{t("agents.model")}</label>
            <select id="md" className={cx(field, "text-sm")} value={draft.default_model} onChange={(e) => set("default_model", e.target.value)}>
              <option value="">{t("agents.modelAuto")}</option>
              {connectedModels.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            <label htmlFor="lg" className="font-semibold text-sm">{t("agents.language")}</label>
            <select id="lg" className={cx(field, "text-sm")} value={draft.answer_language} onChange={(e) => set("answer_language", e.target.value as Agent["answer_language"])}>
              <option value="ui">{t("agents.langUi")}</option>
              <option value="uk">Українська</option>
              <option value="en">English</option>
              <option value="de">Deutsch</option>
            </select>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2, duration: 0.45, ease }}
                      className="p-[22px] rounded-[22px] bg-night text-night-ink flex flex-col gap-3">
            <div className="flex items-center gap-2.5 font-bold"><IconShield className="text-glow" size={20} />{t("agents.isolatedTitle")}</div>
            <div className="text-sm leading-relaxed text-night-muted">{t("agents.isolatedBody")}</div>
          </motion.div>

          <div className="flex flex-wrap gap-2">
            {agent.preset && (
              <button onClick={() => reset.mutate()} className="flex-1 px-4 py-2.5 rounded-xl border border-line text-sm font-semibold text-ink-2 cursor-pointer hover:bg-soft">
                {t("agents.reset")}
              </button>
            )}
            <button onClick={() => { if (confirm(t("agents.confirmDelete"))) remove.mutate(); }}
                    className="flex items-center justify-center gap-2 flex-1 px-4 py-2.5 rounded-xl bg-danger-bg text-danger-ink text-sm font-semibold cursor-pointer hover:brightness-95">
              <IconTrash size={15} />{t("agents.delete")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Chips({ label, items, selected, onToggle, mono }: { label: string; items: string[]; selected: string[]; onToggle: (v: string) => void; mono?: boolean }) {
  return (
    <fieldset className="flex flex-col gap-2.5 border-none p-0 m-0">
      <legend className="font-semibold text-sm mb-2.5">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {items.map((it) => {
          const on = selected.includes(it);
          return (
            <motion.button key={it} type="button" onClick={() => onToggle(it)} aria-pressed={on} whileHover={{ y: -2 }} whileTap={{ scale: 0.96 }}
                           className={cx("px-3.5 py-2 rounded-full text-[13px] cursor-pointer transition-colors duration-200", mono && "font-mono",
                                         on ? "bg-brand text-white" : "bg-soft text-ink-2 hover:bg-tint")}>
              {it}
            </motion.button>
          );
        })}
      </div>
    </fieldset>
  );
}
