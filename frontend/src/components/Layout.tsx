import { useState } from "react";
import { NavLink, Outlet, useMatch, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "motion/react";
import { api, type Lang, type User } from "../api";
import { applyTheme, cx, ease, getTheme, pick } from "../lib";
import { IconBoard, IconBot, IconChat, IconClose, IconKey, IconLogout, IconMenu, IconMoon, IconPlus, IconSun } from "./Icons";

const NAV = [
  { to: "/chat", key: "nav.chat", icon: IconChat },
  { to: "/agents", key: "nav.agents", icon: IconBot },
  { to: "/grants", key: "nav.grants", icon: IconBoard },
  { to: "/accounts", key: "nav.accounts", icon: IconKey },
];

export function Logo() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <svg viewBox="0 0 96 96" className="w-9 h-9 shrink-0 drop-shadow-[0_6px_12px_rgba(17,134,106,0.25)]" aria-hidden>
        <rect width="96" height="96" rx="24" fill="#e8f7f0" />
        <path d="M34 72V24H66M34 47H56" fill="none" stroke="#11866a" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
        <g fill="#f3faf7" stroke="#0e2621" strokeWidth="5">
          <circle cx="34" cy="24" r="7" /><circle cx="66" cy="24" r="7" /><circle cx="56" cy="47" r="7" /><circle cx="34" cy="72" r="7" />
        </g>
      </svg>
      <div className="font-bold text-xl tracking-tight">Finder</div>
    </div>
  );
}

export default function Layout({ user }: { user: User }) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const chatMatch = useMatch("/chat/:agentId/*");
  const activeAgent = chatMatch ? Number(chatMatch.params.agentId) : null;
  const agents = useQuery({ queryKey: ["agents"], queryFn: api.agents });
  const [theme, setTheme] = useState(getTheme());

  const setLang = useMutation({
    mutationFn: (lang: Lang) => api.updateMe({ language: lang }),
    onMutate: (lang) => { i18n.changeLanguage(lang); },
  });
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => { qc.clear(); navigate("/login"); qc.invalidateQueries({ queryKey: ["me"] }); },
  });

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : theme === "light" ? "system" : "dark";
    setTheme(next);
    applyTheme(next);
  };

  const sidebar = (
    <aside className="h-full w-[272px] shrink-0 box-border px-4 py-6 bg-surface border-r border-line flex flex-col gap-6 overflow-y-auto">
      <div className="flex items-center justify-between">
        <Logo />
        <button className="lg:hidden w-11 h-11 flex items-center justify-center rounded-xl text-ink-2 hover:bg-soft"
                aria-label={t("common.close")} onClick={() => setOpen(false)}><IconClose /></button>
      </div>

      <nav className="flex flex-col gap-1">
        {NAV.map(({ to, key, icon: Icon }) => (
          <NavLink key={to} to={to} onClick={() => setOpen(false)}
                   className={({ isActive }) => cx(
                     "relative flex items-center gap-3 px-3 py-[11px] rounded-xl text-[15px] no-underline transition-colors",
                     isActive ? "text-brand-deep font-semibold" : "text-ink-2 hover:bg-soft hover:text-ink")}>
            {({ isActive }) => (<>
              {isActive && <motion.span layoutId="nav-pill" className="absolute inset-0 rounded-xl bg-tint"
                                        transition={{ type: "spring", stiffness: 420, damping: 34 }} />}
              <Icon className="relative" /><span className="relative">{t(key)}</span>
            </>)}
          </NavLink>
        ))}
      </nav>

      <div className="flex flex-col gap-1.5">
        <div className="text-xs font-semibold tracking-[0.08em] uppercase text-muted px-3">{t("nav.myAgents")}</div>
        {(agents.data || []).map((a) => {
          const active = a.id === activeAgent;
          return (
            <NavLink key={a.id} to={`/chat/${a.id}`} onClick={() => setOpen(false)}
                     className={cx("flex flex-col gap-0.5 p-3 rounded-[14px] border-[1.5px] no-underline transition-all duration-300",
                                   active ? "border-brand bg-surface shadow-[0_6px_18px_rgba(17,134,106,0.12)]" : "border-transparent hover:bg-soft")}>
              <span className="font-semibold text-sm text-ink">{pick(a.name, i18n.language)}</span>
              <span className="text-xs text-muted line-clamp-1">{pick(a.description, i18n.language)}</span>
            </NavLink>
          );
        })}
        <NavLink to="/agents/new" onClick={() => setOpen(false)}
                 className="flex items-center gap-2 px-3 py-2.5 rounded-xl border-[1.5px] border-dashed border-line-strong text-brand-ink text-sm font-semibold no-underline hover:bg-soft transition-colors">
          <IconPlus size={16} /> {t("nav.newAgent")}
        </NavLink>
      </div>

      <div className="mt-auto flex flex-col gap-3">
        <div className="flex gap-1 p-1 bg-soft rounded-xl" role="group" aria-label="Language">
          {(["uk", "en", "de"] as Lang[]).map((l) => (
            <button key={l} onClick={() => setLang.mutate(l)} aria-pressed={i18n.language === l}
                    className={cx("relative flex-1 py-2 rounded-[9px] text-[13px] cursor-pointer transition-colors",
                                  i18n.language === l ? "text-brand-deep font-semibold" : "text-ink-2 hover:text-ink")}>
              {i18n.language === l && <motion.span layoutId="lang-pill" className="absolute inset-0 rounded-[9px] bg-surface shadow-sm"
                                                   transition={{ type: "spring", stiffness: 500, damping: 36 }} />}
              <span className="relative">{l.toUpperCase()}</span>
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 px-1">
          <div className="w-8 h-8 rounded-full bg-tint text-brand-deep flex items-center justify-center text-sm font-bold shrink-0">
            {(user.display_name || user.email)[0]?.toUpperCase()}
          </div>
          <div className="min-w-0 flex-1 text-sm truncate text-ink-2">{user.display_name || user.email}</div>
          <button onClick={toggleTheme} title={`${t("nav.theme")}: ${t(`common.${theme}`)}`} aria-label={t("nav.theme")}
                  className="w-9 h-9 flex items-center justify-center rounded-lg text-muted hover:bg-soft hover:text-ink cursor-pointer">
            {theme === "dark" ? <IconMoon size={17} /> : <IconSun size={17} />}
          </button>
          <button onClick={() => logout.mutate()} title={t("nav.logout")} aria-label={t("nav.logout")}
                  className="w-9 h-9 flex items-center justify-center rounded-lg text-muted hover:bg-soft hover:text-ink cursor-pointer">
            <IconLogout size={17} />
          </button>
        </div>
      </div>
    </aside>
  );

  return (
    <div className="h-full flex bg-ground text-ink">
      <div className="hidden lg:block h-full">{sidebar}</div>
      <AnimatePresence>
        {open && (
          <>
            <motion.div className="fixed inset-0 z-30 bg-night/40 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }} onClick={() => setOpen(false)} />
            <motion.div className="fixed inset-y-0 left-0 z-40 lg:hidden" initial={{ x: -290 }} animate={{ x: 0 }} exit={{ x: -290 }}
                        transition={{ duration: 0.35, ease }}>{sidebar}</motion.div>
          </>
        )}
      </AnimatePresence>
      <div className="flex-1 min-w-0 flex flex-col h-full">
        <div className="lg:hidden flex items-center gap-2 px-4 py-3 border-b border-line bg-surface">
          <button className="w-11 h-11 flex items-center justify-center rounded-xl hover:bg-soft" aria-label="Menu"
                  onClick={() => setOpen(true)}><IconMenu /></button>
          <Logo />
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto"><Outlet /></div>
      </div>
    </div>
  );
}
