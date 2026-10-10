import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "motion/react";
import { api, type Agent, type Grant, type Lang, type Verdict } from "../api";
import { IconAlert, IconBoard, IconBot, IconExternal, IconTrash } from "../components/Icons";
import { cx, ease, pick } from "../lib";

const COLUMNS: { verdict: Verdict; bg: string; dot: string; chip: string; chipText: string }[] = [
  { verdict: "fits", bg: "bg-soft", dot: "bg-brand", chip: "bg-tint", chipText: "text-brand-deep" },
  { verdict: "next_year", bg: "bg-amber-bg", dot: "bg-amber-dot", chip: "bg-amber-chip", chipText: "text-amber-ink" },
  { verdict: "not_for_us", bg: "bg-slate-bg", dot: "bg-slate-dot", chip: "bg-surface", chipText: "text-slate-ink" },
];

export default function Grants() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const grants = useQuery({ queryKey: ["grants"], queryFn: () => api.grants() });
  const agents = useQuery({ queryKey: ["agents"], queryFn: api.agents });
  // The board always belongs to ONE grants agent: its profile decides the verdicts.
  const grantAgents = (agents.data || []).filter((a) => a.kind === "grants");
  const [selectedId, setSelectedId] = useState<number | null>(() => {
    try { return Number(localStorage.getItem("finder.grantAgent")) || null; } catch { return null; }
  });
  const grantAgent = grantAgents.find((a) => a.id === selectedId) || grantAgents[0];
  const [profileOpen, setProfileOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftProfile, setDraftProfile] = useState("");
  const lang = i18n.language as Lang;
  const chooseAgent = (id: number) => {
    setSelectedId(id);
    setEditing(false);
    try { localStorage.setItem("finder.grantAgent", String(id)); } catch { /* storage unavailable */ }
  };
  const startEdit = (agent: Agent) => {
    setDraftName(pick(agent.name, lang));
    setDraftProfile(agent.org_profile);
    setEditing(true);
  };
  const saveProfile = useMutation({
    mutationFn: (agent: Agent) => api.updateAgent(agent.id, {
      org_profile: draftProfile, name: { ...agent.name, [lang]: draftName.trim() || pick(agent.name, lang) },
    }),
    onSuccess: (saved) => {
      qc.setQueryData<Agent[]>(["agents"], (list) => list?.map((x) => (x.id === saved.id ? saved : x)));
      setEditing(false);
    },
  });
  // A new profile = a new grants agent (copy of the current one, or the preset when there is none).
  const createProfile = useMutation({
    mutationFn: async () => {
      const n = grantAgents.length + 1;
      const name = { uk: `Профіль ${n}`, en: `Profile ${n}`, de: `Profil ${n}` };
      return grantAgent ? api.createAgent({ copy_of: grantAgent.id, name }) : api.createAgent({ preset: "it-grants" });
    },
    onSuccess: (created) => {
      qc.setQueryData<Agent[]>(["agents"], (list) => [...(list || []), created]);
      chooseAgent(created.id);
      startEdit(created);
    },
  });

  const move = useMutation({
    mutationFn: ({ id, verdict }: { id: number; verdict: Verdict }) => api.setVerdict(id, verdict),
    onMutate: ({ id, verdict }) => {
      qc.setQueryData<Grant[]>(["grants"], (list) => list?.map((g) => (g.id === id ? { ...g, verdict } : g)));
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteGrant(id),
    onMutate: (id) => { qc.setQueryData<Grant[]>(["grants"], (list) => list?.filter((g) => g.id !== id)); },
  });

  function run() {
    if (!grantAgent) return;
    navigate(`/chat/${grantAgent.id}?q=${encodeURIComponent(t("grants.runPrompt"))}`);
  }

  const items = (grants.data || []).filter((g) => !grantAgent || g.agent_id === grantAgent.id);
  const profileLines = (grantAgent?.org_profile || "").split("\n").map((l) => l.trim()).filter(Boolean);
  const templateProfile = !grantAgent?.org_profile.trim() || /[[][^\]]+[\]]/.test(grantAgent.org_profile);

  return (
    <div className="px-5 sm:px-10 py-8 flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          <h1 className="m-0 text-[30px] font-bold tracking-tight">{t("grants.title")}</h1>
          <p className="m-0 text-[15px] text-muted">{t("grants.subtitle")}</p>
        </div>
        <button onClick={run} disabled={!grantAgent}
                className="px-[22px] py-3 rounded-[14px] bg-brand text-white font-bold text-sm cursor-pointer shadow-[0_10px_24px_rgba(17,134,106,0.25)] hover:brightness-110 disabled:opacity-50">
          {t("grants.run")}
        </button>
      </div>

      {agents.data && !grantAgent && (
        <div className="flex flex-wrap items-center gap-3 px-5 py-4 rounded-2xl bg-amber-bg text-amber-ink text-sm">
          <IconAlert className="shrink-0" /> <span className="flex-1">{t("grants.noAgent")}</span>
          <button onClick={() => createProfile.mutate()} className="font-bold cursor-pointer">{t("grants.newProfile")}</button>
        </div>
      )}

      {grantAgent && (
        <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease }}
                        aria-label={t("grants.activeAgent")}
                        className="flex flex-col gap-3 px-5 py-4 rounded-[20px] bg-surface border border-line">
          <div className="flex flex-wrap items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-tint text-brand-deep flex items-center justify-center shrink-0"><IconBot size={20} /></div>
            <label className="flex flex-col gap-1 min-w-0 flex-1">
              <span className="text-xs font-semibold tracking-[0.08em] uppercase text-muted">{t("grants.activeAgent")}</span>
              <select value={grantAgent.id} disabled={createProfile.isPending}
                      onChange={(e) => (e.target.value === "new" ? createProfile.mutate() : chooseAgent(Number(e.target.value)))}
                      className="max-w-full w-fit min-w-[220px] font-bold text-base bg-soft text-ink rounded-xl px-3 py-2 border border-line-strong cursor-pointer">
                {grantAgents.map((a) => <option key={a.id} value={a.id}>{pick(a.name, lang)}</option>)}
                <option value="new">{t("grants.newProfile")}</option>
              </select>
            </label>
            {!editing && (
              <button onClick={() => startEdit(grantAgent)}
                      className="px-4 py-2.5 rounded-xl border border-line-strong text-brand-ink font-semibold text-sm cursor-pointer hover:bg-soft">
                {t("grants.changeProfile")}
              </button>
            )}
          </div>

          {/* Plain elements + CSS fade: the switch must not depend on an exit animation finishing. */}
          {editing ? (
              <form key="edit" className="flex flex-col gap-3 animate-rise"
                           onSubmit={(e) => { e.preventDefault(); saveProfile.mutate(grantAgent); }}>
                <label className="flex flex-col gap-1.5 text-sm font-semibold">{t("agents.name")}
                  <input value={draftName} onChange={(e) => setDraftName(e.target.value)} maxLength={120}
                         className="font-normal text-[15px] px-4 py-2.5 rounded-xl border-[1.5px] border-line bg-ground text-ink outline-none focus:border-brand" />
                </label>
                <label className="flex flex-col gap-1.5 text-sm font-semibold">
                  <span>{t("agents.orgProfile")} <span className="font-normal text-muted">{t("agents.orgHint")}</span></span>
                  <textarea value={draftProfile} onChange={(e) => setDraftProfile(e.target.value)} rows={9} autoFocus
                            className="font-normal text-sm leading-relaxed px-4 py-3 rounded-xl border-[1.5px] border-line bg-ground text-ink outline-none resize-y focus:border-brand" />
                </label>
                <div className="flex flex-wrap items-center gap-2.5">
                  <button type="submit" disabled={saveProfile.isPending}
                          className="px-5 py-2.5 rounded-xl bg-brand text-white font-bold text-sm cursor-pointer hover:brightness-110 disabled:opacity-60">
                    {t("accounts.save")}
                  </button>
                  <button type="button" onClick={() => setEditing(false)}
                          className="px-4 py-2.5 rounded-xl border border-line text-ink-2 font-semibold text-sm cursor-pointer hover:bg-soft">
                    {t("common.cancel")}
                  </button>
                  <Link to={`/agents/${grantAgent.id}`} className="ml-auto text-[13px] font-semibold">{t("grants.allSettings")} →</Link>
                </div>
              </form>
            ) : (
              <div key="view" className="flex flex-col gap-1.5 pl-[52px] max-sm:pl-0 animate-rise">
                <span className="text-xs font-semibold tracking-[0.08em] uppercase text-muted">{t("agents.editProfile")}</span>
                {profileLines.length === 0 ? (
                  <span className="text-sm text-muted">{t("grants.profileEmpty")}</span>
                ) : (
                  <div className="text-sm leading-relaxed text-ink-2 whitespace-pre-line">
                    {(profileOpen ? profileLines : profileLines.slice(0, 2)).join("\n")}
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted">
                  {profileLines.length > 2 && (
                    <button onClick={() => setProfileOpen((v) => !v)} aria-expanded={profileOpen}
                            className="font-semibold text-brand-ink hover:text-brand-deep cursor-pointer">
                      {profileOpen ? t("grants.profileLess") : t("grants.profileMore")}
                    </button>
                  )}
                  <span>{t("grants.sourcesCount", { count: grantAgent.sources.length })}</span>
                </div>
              </div>
            )}
        </motion.section>
      )}

      {grantAgent && templateProfile && !editing && (
        <button onClick={() => startEdit(grantAgent)}
                className="text-left flex items-start gap-3 px-5 py-4 rounded-2xl bg-amber-bg text-amber-ink text-sm cursor-pointer hover:brightness-95">
          <IconAlert className="shrink-0 mt-0.5" /> <span>{t("agents.orgTemplateWarning")} <b>{t("grants.changeProfile")} →</b></span>
        </button>
      )}

      {!grants.isLoading && items.length === 0 && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                    className="flex flex-col items-center text-center gap-3 py-16 rounded-3xl border-[1.5px] border-dashed border-line-strong">
          <div className="w-14 h-14 rounded-2xl bg-tint text-brand-deep flex items-center justify-center"><IconBoard size={26} /></div>
          <div className="text-xl font-bold">{t("grants.empty")}</div>
          <div className="text-muted max-w-md">{t("grants.emptyHint")}</div>
        </motion.div>
      )}

      {items.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(270px,1fr))] gap-5 items-start">
          {COLUMNS.map((col) => {
            const list = items.filter((g) => g.verdict === col.verdict);
            return (
              <section key={col.verdict} className={cx("flex flex-col gap-3 p-4 rounded-[22px]", col.bg)}>
                <div className="flex items-center justify-between px-1.5 py-1">
                  <div className="flex items-center gap-2 font-bold"><span className={cx("w-2.5 h-2.5 rounded-full", col.dot)} />{t(`grants.${col.verdict}`)}</div>
                  <motion.span key={list.length} initial={{ scale: 1.3 }} animate={{ scale: 1 }}
                               className={cx("text-[13px] font-semibold px-2.5 py-0.5 rounded-full bg-surface", col.chipText)}>{list.length}</motion.span>
                </div>
                <AnimatePresence initial={false}>
                  {list.map((g, i) => (
                    <motion.article key={g.id} layout layoutId={`grant-${g.id}`}
                                    initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }}
                                    transition={{ duration: 0.45, ease, delay: Math.min(i * 0.05, 0.3) }}
                                    className={cx("flex flex-col gap-2.5 p-[18px] rounded-2xl bg-surface transition-shadow hover:shadow-[0_16px_34px_rgba(14,38,33,0.10)]",
                                                  col.verdict === "not_for_us" && "opacity-90")}>
                      <div className="font-bold text-[15px] leading-snug">{g.title}</div>
                      {(g.funder || g.amount) && <div className="text-[13px] text-muted">{[g.funder, g.amount].filter(Boolean).join(" · ")}</div>}
                      {g.reasoning && <div className="text-[13px] leading-relaxed">{g.reasoning}</div>}
                      {g.eligibility && <div className="text-xs text-muted leading-relaxed">{g.eligibility}</div>}
                      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                        {g.deadline ? <span className={cx("text-xs font-semibold px-2.5 py-1 rounded-full", col.chip, col.chipText)}>{t("grants.deadline")} {g.deadline}</span> : <span />}
                        <div className="flex items-center gap-1">
                          <select aria-label={t("grants.moveTo")} value={g.verdict} onChange={(e) => move.mutate({ id: g.id, verdict: e.target.value as Verdict })}
                                  className="text-xs bg-soft rounded-lg px-2 py-1.5 border-none text-ink-2 cursor-pointer">
                            {COLUMNS.map((c) => <option key={c.verdict} value={c.verdict}>{t(`grants.${c.verdict}`)}</option>)}
                          </select>
                          {g.url && <a href={g.url} target="_blank" rel="noopener noreferrer" title={t("grants.open")} aria-label={t("grants.open")}
                                       className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-soft"><IconExternal size={15} /></a>}
                          <button onClick={() => remove.mutate(g.id)} title={t("grants.delete")} aria-label={t("grants.delete")}
                                  className="w-8 h-8 flex items-center justify-center rounded-lg text-muted hover:text-danger-ink hover:bg-soft cursor-pointer"><IconTrash size={14} /></button>
                        </div>
                      </div>
                    </motion.article>
                  ))}
                </AnimatePresence>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
