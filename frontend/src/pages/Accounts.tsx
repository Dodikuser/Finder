import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "motion/react";
import { api, ApiError, type LoginSession, type Provider } from "../api";
import { IconCheck, IconClose, IconCopy, IconExternal, IconKey } from "../components/Icons";
import { cx, ease } from "../lib";

const ACTIVE = ["starting", "waiting", "verifying"];
const hintKey = (providerId: string) => (providerId === "anthropic" ? "claude" : providerId === "antigravity-oauth" ? "gemini" : "other");

export default function Accounts() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers });
  const [login, setLogin] = useState<{ provider: Provider; session: LoginSession | null; error?: string } | null>(null);
  const [keyOpen, setKeyOpen] = useState(false);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["providers"] });
    qc.invalidateQueries({ queryKey: ["models"] });
  };
  const disconnect = useMutation({ mutationFn: api.disconnect, onSuccess: refresh });

  async function startLogin(p: Provider) {
    setLogin({ provider: p, session: null });
    try {
      const session = await api.startLogin(p.id);
      setLogin((cur) => (cur && cur.provider.id === p.id ? { ...cur, session } : cur));
    } catch (err) {
      setLogin((cur) => cur && { ...cur, error: err instanceof ApiError ? err.code : String(err) });
    }
  }

  // Poll the device-code session until the user approves it on the provider's page.
  useEffect(() => {
    const sid = login?.session?.session_id;
    if (!sid || !ACTIVE.includes(login.session!.status)) return;
    const timer = setInterval(async () => {
      try {
        const s = await api.pollLogin(sid);
        setLogin((cur) => (cur && cur.session?.session_id === sid ? { ...cur, session: s } : cur));
        if (s.status === "approved") { refresh(); setTimeout(() => setLogin(null), 1600); }
      } catch { /* transient */ }
    }, 2000);
    return () => clearInterval(timer);
  }, [login?.session?.session_id, login?.session?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // Leaving the page with a sign-in still open: cancel it so no process keeps waiting on the server.
  const pending = useRef<string | null>(null);
  pending.current = login?.session && ACTIVE.includes(login.session.status) ? login.session.session_id : null;
  useEffect(() => () => { if (pending.current) api.cancelLogin(pending.current).catch(() => {}); }, []);

  function closeLogin() {
    if (login?.session && ACTIVE.includes(login.session.status)) api.cancelLogin(login.session.session_id);
    setLogin(null);
  }

  async function submitCode(code: string) {
    const sid = login?.session?.session_id;
    if (!sid) return;
    try {
      const session = await api.submitLoginCode(sid, code);
      setLogin((cur) => (cur && cur.session?.session_id === sid ? { ...cur, session } : cur));
    } catch (err) {
      setLogin((cur) => cur && { ...cur, error: err instanceof ApiError ? err.code : String(err) });
    }
  }

  const data = providers.data;
  // A provider can be offered both as a subscription and as an API key (Anthropic): list it once.
  const connected = [...(data?.oauth || []), ...(data?.api_key || [])]
    .filter((p, i, arr) => p.connected && arr.findIndex((x) => x.id === p.id) === i);
  const recommended = data?.oauth.find((p) => p.recommended && !p.connected);
  const others = (data?.oauth || []).filter((p) => !p.connected && !p.recommended);

  return (
    <div className="px-5 sm:px-10 py-8 flex flex-wrap gap-8 items-start">
      <div className="flex-[999_1_520px] min-w-0 max-w-[760px] flex flex-col gap-6">
        <div className="text-sm text-muted">
          {(t("accounts.crumbs", { returnObjects: true }) as string[]).map((c, i, arr) => (
            <span key={c}>{i === arr.length - 1 ? <span className="text-ink font-semibold">{c}</span> : c}{i < arr.length - 1 && <span className="mx-1.5">›</span>}</span>
          ))}
        </div>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-col gap-1.5">
            <h1 className="m-0 text-[30px] font-bold tracking-tight">{t("accounts.title")}</h1>
            <p className="m-0 text-[15px] text-muted">{t("accounts.subtitle")}</p>
          </div>
          <button onClick={() => setKeyOpen(true)}
                  className="text-sm font-semibold px-3.5 py-2.5 rounded-xl border border-line-strong text-brand-ink hover:bg-soft cursor-pointer transition">
            {t("accounts.haveKey")}
          </button>
        </div>

        {providers.isLoading && <div className="shimmer h-20 rounded-[18px]" />}

        {recommended && (
          <motion.button initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease }}
                         onClick={() => startLogin(recommended)}
                         className="group text-left flex items-center gap-4 px-5 py-[18px] rounded-[18px] bg-surface border-[1.5px] border-brand shadow-[0_12px_32px_rgba(17,134,106,0.12)] cursor-pointer transition hover:-translate-y-0.5">
            <span className="w-11 h-11 rounded-[13px] bg-night text-tint flex items-center justify-center font-bold">N</span>
            <span className="flex flex-col gap-1 flex-1">
              <span className="flex flex-wrap items-center gap-2.5 font-bold text-base">{recommended.name}
                <span className="text-[11px] tracking-[0.1em] uppercase px-2 py-0.5 rounded-md bg-brand text-white">{t("accounts.recommended")}</span>
              </span>
              <span className="text-sm text-muted">{t("accounts.recommendedHint")}</span>
            </span>
            <span className="text-sm font-semibold text-brand-ink transition group-hover:translate-x-1">{t("accounts.signIn")} →</span>
          </motion.button>
        )}

        {connected.length > 0 && (
          <Section title={t("accounts.connected")}>
            <AnimatePresence initial={false}>
              {connected.map((p) => (
                <motion.div key={p.id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }}
                            className="flex flex-wrap items-center gap-3.5 px-5 py-4 rounded-2xl bg-surface border border-line">
                  <span className="flex flex-col gap-1 flex-1 min-w-[220px]">
                    <span className="flex flex-wrap items-center gap-2.5 font-semibold text-[15px]">{p.name}
                      <span className="inline-flex items-center gap-1 text-xs px-2.5 py-0.5 rounded-full bg-tint text-brand-deep"><IconCheck size={11} />{t("accounts.connectedBadge")}</span>
                    </span>
                    <span className="text-[13px] text-muted">{p.flow ? t("accounts.deviceHint") : t("accounts.keyHint")}</span>
                  </span>
                  <button onClick={() => disconnect.mutate(p.id)} disabled={disconnect.isPending}
                          className="text-[13px] font-semibold px-3.5 py-2.5 rounded-[10px] bg-danger-bg text-danger-ink cursor-pointer hover:brightness-95 disabled:opacity-50">
                    {t("accounts.disconnect")}
                  </button>
                </motion.div>
              ))}
            </AnimatePresence>
          </Section>
        )}

        <Section title={t("accounts.other")}>
          {others.map((p, i) => (
            <motion.button key={p.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05, duration: 0.35, ease }}
                           onClick={() => startLogin(p)}
                           className={cx("text-left flex flex-col gap-1 px-5 py-4 rounded-2xl transition-all duration-300 cursor-pointer hover:bg-soft hover:translate-x-[3px]",
                                         login?.provider.id === p.id && "bg-soft")}>
              <span className="font-semibold text-[15px]">{p.name}</span>
              <span className="text-[13px] text-muted">{p.flow === "code" ? t(`accounts.codeHint.${hintKey(p.id)}`) : t("accounts.deviceHint")}</span>
            </motion.button>
          ))}
        </Section>
      </div>

      <AnimatePresence>
        {login && <DevicePanel key={login.provider.id} name={login.provider.name} providerId={login.provider.id}
                               flow={login.provider.flow || "device"}
                               session={login.session} error={login.error} onClose={closeLogin} onCode={submitCode} />}
      </AnimatePresence>
      <AnimatePresence>
        {keyOpen && <KeyDialog providers={data?.api_key || []} onClose={() => setKeyOpen(false)} onSaved={refresh} />}
      </AnimatePresence>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="text-xs font-semibold tracking-[0.08em] uppercase text-muted px-1 py-1.5">{title}</div>
      {children}
    </div>
  );
}

function DevicePanel({ name, providerId, flow, session, error, onClose, onCode }: {
  name: string; providerId: string; flow: "device" | "code"; session: LoginSession | null; error?: string; onClose: () => void; onCode: (code: string) => void;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [code, setCode] = useState("");
  const status = error ? "error" : session?.status || "starting";
  const copy = async () => {
    if (!session?.user_code) return;
    try { await navigator.clipboard.writeText(session.user_code); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* denied */ }
  };
  return (
    <motion.div role="dialog" aria-label={t("accounts.modalTitle", { name })}
                initial={{ opacity: 0, y: 16, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12, scale: 0.98 }}
                transition={{ duration: 0.4, ease }}
                className="flex-[1_1_320px] max-w-[400px] sticky top-6 flex flex-col gap-[18px] p-[26px] rounded-3xl bg-night text-night-ink shadow-[0_24px_60px_rgba(14,38,33,0.25)]">
      <div className="flex items-center justify-between">
        <div className="font-bold text-lg">{t("accounts.modalTitle", { name })}</div>
        <button onClick={onClose} aria-label={t("common.close")} className="w-11 h-11 flex items-center justify-center rounded-xl text-tint hover:bg-night-2 cursor-pointer"><IconClose size={16} /></button>
      </div>
      {status === "approved" ? (
        <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="flex flex-col items-center gap-3 py-6">
          <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 300, damping: 15 }}
                       className="w-16 h-16 rounded-full bg-glow text-night flex items-center justify-center"><IconCheck size={30} /></motion.span>
          <div className="font-semibold">{t("accounts.approved")}</div>
        </motion.div>
      ) : status === "error" || status === "cancelled" ? (
        <div className="text-sm rounded-xl px-4 py-3 bg-danger-bg text-danger-ink">{t("accounts.failed")}{(error || session?.message) ? `: ${error || session?.message}` : ""}</div>
      ) : flow === "code" ? (
        <>
          <div className="text-sm text-night-muted leading-relaxed">{t("accounts.codeStep1")}<br />{t("accounts.codeStep2")}<br />{t("accounts.codeStep3")}</div>
          <a href={session?.verification_url || undefined} target="_blank" rel="noopener noreferrer" aria-disabled={!session?.verification_url}
             className={cx("flex items-center justify-center gap-2 p-3.5 rounded-[14px] bg-glow text-night font-bold no-underline hover:brightness-105 transition",
                           !session?.verification_url && "opacity-50 pointer-events-none")}>
            {t("accounts.openSignIn")} <IconExternal size={16} />
          </a>
          <form className="flex flex-col gap-2.5" onSubmit={(e) => { e.preventDefault(); if (code.trim()) onCode(code); }}>
            <label className="flex flex-col gap-1.5 text-sm font-semibold">{t("accounts.codeLabel")}
              <input value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" spellCheck={false}
                     disabled={status !== "waiting"}
                     className="font-mono font-normal text-sm px-3.5 py-3 rounded-xl bg-night-2 text-night-ink border border-white/10 outline-none focus:border-glow placeholder:text-night-muted/50" />
            </label>
            <button type="submit" disabled={status !== "waiting" || !code.trim()}
                    className="p-3 rounded-[14px] bg-night-2 text-glow font-bold cursor-pointer border border-glow/40 hover:bg-glow hover:text-night transition disabled:opacity-40 disabled:cursor-default">
              {status === "verifying" ? t("accounts.saving") : t("accounts.codeSubmit")}
            </button>
          </form>
          <div className="text-xs text-night-muted leading-relaxed">{t(`accounts.codeNote.${hintKey(providerId)}`)}</div>
          {status !== "waiting" && (
            <div className="flex items-center gap-2.5 text-sm text-night-muted">
              <span className="w-4 h-4 rounded-full border-2 border-night-2 border-t-glow animate-spin" />
              {status === "verifying" ? t("accounts.saving") : t("accounts.starting")}
            </div>
          )}
        </>
      ) : (
        <>
          <div className="text-sm text-night-muted leading-relaxed">{t("accounts.step1")}<br />{t("accounts.step2")}</div>
          <button onClick={copy} disabled={!session?.user_code} title={t("accounts.copy")}
                  className="group relative font-mono text-[28px] sm:text-[32px] font-semibold tracking-[0.12em] text-center p-[18px] rounded-2xl bg-night-2 text-glow cursor-pointer">
            {session?.user_code || <span className="inline-block w-48 h-8 rounded-lg bg-white/10 animate-pulse align-middle" />}
            {session?.user_code && <span className="absolute right-3 top-3 text-xs font-sans tracking-normal text-night-muted flex items-center gap-1 opacity-70 group-hover:opacity-100">
              {copied ? <><IconCheck size={11} />{t("accounts.copied")}</> : <IconCopy size={13} />}
            </span>}
          </button>
          <a href={session?.verification_url || undefined} target="_blank" rel="noopener noreferrer" aria-disabled={!session?.verification_url}
             className={cx("flex items-center justify-center gap-2 p-3.5 rounded-[14px] bg-glow text-night font-bold no-underline hover:brightness-105 transition",
                           !session?.verification_url && "opacity-50 pointer-events-none")}>
            {t("accounts.open")} <IconExternal size={16} />
          </a>
          <div className="flex items-center gap-2.5 text-sm text-night-muted">
            <span className="w-4 h-4 rounded-full border-2 border-night-2 border-t-glow animate-spin" />
            {session ? t("accounts.waiting") : t("accounts.starting")}
          </div>
        </>
      )}
    </motion.div>
  );
}

function KeyDialog({ providers, onClose, onSaved }: { providers: Provider[]; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const [provider, setProvider] = useState(providers[0]?.id || "");
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const save = useMutation({
    mutationFn: () => api.addKey(provider, key.trim()),
    onSuccess: () => { onSaved(); onClose(); },
    onError: (err) => setError(err instanceof ApiError ? err.code : String(err)),
  });
  const submit = (e: FormEvent) => { e.preventDefault(); setError(""); save.mutate(); };
  const field = "w-full box-border text-[15px] px-4 py-3 rounded-[14px] border-[1.5px] border-line bg-ground text-ink outline-none focus:border-brand";
  return (
    <motion.div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-night/50" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                onClick={onClose}>
      <motion.form role="dialog" aria-label={t("accounts.keyTitle")} onSubmit={submit} onClick={(e) => e.stopPropagation()}
                   initial={{ y: 20, scale: 0.97 }} animate={{ y: 0, scale: 1 }} exit={{ y: 20, scale: 0.97 }} transition={{ duration: 0.35, ease }}
                   className="w-full max-w-[440px] flex flex-col gap-4 p-6 rounded-3xl bg-surface border border-line shadow-2xl">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5 font-bold text-lg"><IconKey />{t("accounts.keyTitle")}</div>
          <button type="button" onClick={onClose} aria-label={t("common.close")} className="w-10 h-10 flex items-center justify-center rounded-xl hover:bg-soft cursor-pointer"><IconClose size={16} /></button>
        </div>
        <label className="flex flex-col gap-2 text-sm font-semibold">{t("accounts.provider")}
          <select className={field} value={provider} onChange={(e) => setProvider(e.target.value)}>
            {providers.map((p) => <option key={p.id} value={p.id}>{p.name}{p.connected ? " ✓" : ""}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-2 text-sm font-semibold">{t("accounts.key")}
          <input className={cx(field, "font-mono")} type="password" autoComplete="off" required minLength={8} value={key} onChange={(e) => setKey(e.target.value)} />
          <span className="text-xs font-normal text-muted">{t("accounts.keyHint")}</span>
        </label>
        {error && <div className="text-sm rounded-xl px-4 py-3 bg-danger-bg text-danger-ink" role="alert">{error}</div>}
        <button type="submit" disabled={save.isPending}
                className="py-3 rounded-[14px] bg-brand text-white font-bold cursor-pointer hover:brightness-110 disabled:opacity-60">
          {save.isPending ? t("accounts.saving") : t("accounts.save")}
        </button>
      </motion.form>
    </motion.div>
  );
}
