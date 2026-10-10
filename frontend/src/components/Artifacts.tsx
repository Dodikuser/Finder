import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "motion/react";
import type { Artifact } from "../api";
import { ease } from "../lib";
import Dashboard from "./Dashboard";
import { IconBoard, IconDownload, IconFile } from "./Icons";

function size(n: number): string {
  return n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/** What the agent attached to an answer: dashboards, downloadable documents, images. */
export default function Artifacts({ items }: { items: Artifact[] }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState<Artifact | null>(null);
  if (!items.length) return null;
  const images = items.filter((a) => a.kind === "image");
  const rest = items.filter((a) => a.kind !== "image");
  return (
    <div className="flex flex-col gap-3">
      {rest.map((a, i) => (
        <motion.div key={a.id} initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                    transition={{ duration: 0.4, ease, delay: i * 0.05 }}>
          {a.kind === "dashboard" && a.data ? (
            <button onClick={() => setOpen(a)}
                    className="group w-full text-left flex items-center gap-4 px-5 py-4 rounded-[20px] bg-night text-night-ink cursor-pointer transition hover:-translate-y-0.5 hover:shadow-[0_16px_34px_rgba(14,38,33,0.22)]">
              <span className="w-12 h-12 shrink-0 rounded-2xl bg-night-2 text-glow flex items-center justify-center"><IconBoard size={22} /></span>
              <span className="flex flex-col gap-0.5 min-w-0 flex-1">
                <span className="text-xs font-semibold tracking-[0.08em] uppercase text-night-muted">{t("analytics.title")}</span>
                <span className="font-bold text-base truncate">{a.title}</span>
                <span className="text-[13px] text-night-muted">{t("analytics.chartsCount", { count: a.data.charts.length })}</span>
              </span>
              <span className="shrink-0 px-4 py-2.5 rounded-xl bg-glow text-night font-bold text-sm transition group-hover:brightness-105">{t("analytics.open")}</span>
            </button>
          ) : (
            <a href={`${a.url}?download=1`} download={a.filename}
               className="group flex items-center gap-4 px-5 py-3.5 rounded-[18px] bg-surface border border-line no-underline text-ink transition hover:border-brand hover:-translate-y-0.5">
              <span className="w-11 h-11 shrink-0 rounded-xl bg-tint text-brand-deep flex items-center justify-center"><IconFile size={20} /></span>
              <span className="flex flex-col gap-0.5 min-w-0 flex-1">
                <span className="font-semibold text-[15px] truncate">{a.filename}</span>
                <span className="text-[13px] text-muted">{(a.filename.split(".").pop() || "").toUpperCase()} · {size(a.size)}</span>
              </span>
              <span className="shrink-0 flex items-center gap-2 text-sm font-semibold text-brand-ink"><IconDownload size={17} />{t("analytics.download")}</span>
            </a>
          )}
        </motion.div>
      ))}
      {images.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
          {images.map((a) => (
            <motion.figure key={a.id} initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4, ease }}
                           className="m-0 flex flex-col rounded-[18px] overflow-hidden bg-surface border border-line">
              <a href={a.url} target="_blank" rel="noopener noreferrer" className="block bg-soft">
                <img src={a.url} alt={a.caption || a.title} loading="lazy" className="block w-full max-h-[360px] object-contain" />
              </a>
              {(a.caption || a.source_url) && (
                <figcaption className="px-3.5 py-2.5 text-[13px] text-ink-2 leading-snug">
                  {a.caption}
                  {a.source_url && <> <a href={a.source_url} target="_blank" rel="noopener noreferrer" className="text-xs">↗</a></>}
                </figcaption>
              )}
            </motion.figure>
          ))}
        </div>
      )}
      {open?.data && <Dashboard data={open.data} onClose={() => setOpen(null)} />}
    </div>
  );
}
