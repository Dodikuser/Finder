import type { I18nText, Lang } from "./api";

export function pick(text: I18nText | undefined, lang: string): string {
  if (!text) return "";
  return text[lang as Lang] || text.en || text.uk || Object.values(text)[0] || "";
}

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

/** Spring-ish easing used across the UI for smooth, calm motion. */
export const ease = [0.2, 0.8, 0.2, 1] as const;

type Theme = "system" | "light" | "dark";

export function getTheme(): Theme {
  try { return (localStorage.getItem("finder.theme") as Theme) || "system"; } catch { return "system"; }
}

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
  try { localStorage.setItem("finder.theme", theme); } catch { /* storage unavailable */ }
}
