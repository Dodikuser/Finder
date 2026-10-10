import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "motion/react";
import { api, ApiError, type Lang } from "../api";
import { Logo } from "../components/Layout";
import { IconCheck } from "../components/Icons";
import { cx, ease } from "../lib";

const DEMO_STEPS = ["web_search", "pubmed_search", "fetch_page", "eu_funding_search"];

export default function Login() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [invite, setInvite] = useState("");
  const config = useQuery({ queryKey: ["auth-config"], queryFn: api.authConfig, staleTime: Infinity });
  const canRegister = config.data?.registration !== false;
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = mode === "login"
        ? await api.login(email, password)
        : await api.register(email, password, name, i18n.language as Lang, invite);
      qc.setQueryData(["me"], user);
      navigate(mode === "register" ? "/accounts" : "/chat");
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "generic";
      setError(t(`auth.errors.${code}`, { defaultValue: t("auth.errors.generic") }));
    } finally {
      setBusy(false);
    }
  }

  const input = "w-full box-border text-[15px] px-4 py-3 rounded-[14px] border-[1.5px] border-line bg-ground text-ink outline-none transition focus:border-brand focus:shadow-[0_0_0_4px_var(--c-soft)]";

  return (
    <div className="min-h-full flex flex-wrap bg-ground">
      <section className="relative overflow-hidden flex-[1_1_420px] min-h-[320px] bg-night text-night-ink p-10 flex flex-col justify-between">
        <div className="absolute -top-32 -right-24 w-[420px] h-[420px] rounded-full bg-brand opacity-30 blur-3xl" />
        <div className="absolute -bottom-40 -left-20 w-[380px] h-[380px] rounded-full bg-glow opacity-20 blur-3xl" />
        <div className="relative [&_.font-bold]:text-white"><Logo /></div>
        <div className="relative max-w-md flex flex-col gap-6">
          <motion.h1 initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease }}
                     className="m-0 text-[34px] leading-tight font-bold tracking-tight text-white">{t("auth.tagline")}</motion.h1>
          <div className="flex flex-col gap-2.5 p-5 rounded-[20px] bg-night-2/80 border border-white/5">
            {DEMO_STEPS.map((s, i) => (
              <motion.div key={s} className="flex items-center gap-3 text-sm"
                          initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 + i * 0.35, duration: 0.5, ease }}>
                <motion.span className="w-[22px] h-[22px] rounded-full flex items-center justify-center bg-glow text-night"
                             initial={{ scale: 0.4 }} animate={{ scale: 1 }} transition={{ delay: 0.6 + i * 0.35, type: "spring", stiffness: 400 }}>
                  <IconCheck size={12} />
                </motion.span>
                <span className="font-mono text-[13px] text-glow">{s}</span>
              </motion.div>
            ))}
          </div>
        </div>
        <div className="relative text-sm text-night-muted">Hermes Agent · uk · en · de</div>
      </section>

      <section className="flex-[1_1_420px] flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-[400px] flex flex-col gap-6">
          <div className="flex justify-end gap-1">
            {(["uk", "en", "de"] as Lang[]).map((l) => (
              <button key={l} onClick={() => i18n.changeLanguage(l)} aria-pressed={i18n.language === l}
                      className={cx("px-3 py-1.5 rounded-lg text-[13px] cursor-pointer", i18n.language === l ? "bg-tint text-brand-deep font-semibold" : "text-muted hover:bg-soft")}>
                {l.toUpperCase()}
              </button>
            ))}
          </div>
          <AnimatePresence mode="wait">
            <motion.form key={mode} onSubmit={submit} className="flex flex-col gap-4"
                         initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.3, ease }}>
              <h2 className="m-0 text-3xl font-bold tracking-tight">{mode === "login" ? t("auth.login") : t("auth.register")}</h2>
              {mode === "register" && (
                <label className="flex flex-col gap-2 text-sm font-semibold">{t("auth.name")}
                  <input className={input} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
                </label>
              )}
              {mode === "register" && config.data?.invite_required && (
                <label className="flex flex-col gap-2 text-sm font-semibold">{t("auth.invite")}
                  <input className={input} required value={invite} onChange={(e) => setInvite(e.target.value)} autoComplete="off" />
                </label>
              )}
              <label className="flex flex-col gap-2 text-sm font-semibold">{t("auth.email")}
                <input className={input} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
              </label>
              <label className="flex flex-col gap-2 text-sm font-semibold">{t("auth.password")}
                <input className={input} type="password" required minLength={mode === "register" ? 8 : 1} value={password}
                       onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} />
                {mode === "register" && <span className="text-xs font-normal text-muted">{t("auth.passwordHint")}</span>}
              </label>
              <AnimatePresence>
                {error && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                              className="text-sm rounded-xl px-4 py-3 bg-danger-bg text-danger-ink" role="alert">{error}</motion.div>
                )}
              </AnimatePresence>
              <button type="submit" disabled={busy}
                      className="mt-2 py-3.5 rounded-[14px] bg-brand text-white font-bold text-[15px] cursor-pointer shadow-[0_10px_24px_rgba(17,134,106,0.25)] transition hover:brightness-110 active:scale-[0.99] disabled:opacity-60">
                {busy ? "…" : mode === "login" ? t("auth.login") : t("auth.register")}
              </button>
              {(canRegister || mode === "register") && (
                <button type="button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}
                        className="text-sm font-semibold text-brand-ink hover:text-brand-deep cursor-pointer">
                  {mode === "login" ? t("auth.toRegister") : t("auth.toLogin")}
                </button>
              )}
            </motion.form>
          </AnimatePresence>
        </div>
      </section>
    </div>
  );
}
