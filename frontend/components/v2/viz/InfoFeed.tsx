"use client";

/** v11 信息流: 三视图可切换(编辑长卡/Bento/瀑布流) + 图片走 /api/img 代理(修防盗链坏图).
 *  - editorial 编辑长卡: 大图 + 标题 + 多段文字 + 来源, 仪式感强;
 *  - bento: 大小格拼贴, 图片占大格;
 *  - feed: 瀑布流(小红书式). */

import { useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { motion } from "framer-motion";
import Masonry from "react-masonry-css";
import Lightbox from "yet-another-react-lightbox";
import "yet-another-react-lightbox/styles.css";

export type MediaCard = {
  type: "text" | "image" | "video" | "link";
  title?: string;
  body?: string;
  url?: string;
  image_url?: string;
  source?: string;
};

export type DeptQuote = {
  dept: string;
  consensus?: string;
  conflicts?: string[];
};

type View = "editorial" | "bento" | "feed";

type Props = {
  deptQuotes?: DeptQuote[];
  mediaCards?: MediaCard[];
  backendUrl?: string;
};

const cardBase: CSSProperties = {
  borderRadius: 12, background: "var(--bg-card)", border: "1px solid var(--border)",
  boxShadow: "var(--shadow)", overflow: "hidden",
};
const cardTitle: CSSProperties = { fontSize: 12.5, fontWeight: 700, color: "var(--info)", marginBottom: 6 };
const cardBody: CSSProperties = { fontSize: 12.5, lineHeight: 1.65, color: "var(--text)", whiteSpace: "pre-wrap" };
const srcLine: CSSProperties = { fontSize: 10.5, color: "var(--text-faint)", marginTop: 8 };
const BREAKPOINTS = { default: 3, 900: 2, 560: 1 };

type Item = MediaCard & { _conflicts?: string[] };

export function InfoFeed({ deptQuotes = [], mediaCards = [], backendUrl = "" }: Props) {
  const [lb, setLb] = useState<string | null>(null);
  const [view, setView] = useState<View>("editorial");

  // 图片代理: 走后端 /api/img 带 Referer 取图, 解决小红书/点评/抖音防盗链空白
  const proxied = (u?: string): string => {
    if (!u) return "";
    if (u.startsWith("data:") || !backendUrl) return u;
    return `${backendUrl}/api/img?url=${encodeURIComponent(u)}`;
  };

  const items: Item[] = [
    ...deptQuotes.map((q) => ({ type: "text" as const, title: `🗣 ${q.dept}`, body: q.consensus, _conflicts: q.conflicts })),
    ...mediaCards,
  ];
  if (items.length === 0) {
    return <div style={{ fontSize: 12, color: "var(--text-dim)" }}>暂无更多信息</div>;
  }

  const Img = ({ src, h, onClick }: { src: string; h?: number | string; onClick?: () => void }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={proxied(src)} alt="" onClick={onClick}
      onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
      style={{ width: "100%", height: h ?? "auto", objectFit: "cover", display: "block", cursor: onClick ? "zoom-in" : "default" }} />
  );

  const linkLine = (m: Item): ReactNode => (m.url && (m.type === "link" || m.type === "video"))
    ? <a href={m.url} target="_blank" rel="noopener noreferrer" style={{ display: "inline-block", marginTop: 6, fontSize: 12.5, color: "var(--info)" }}>{m.type === "video" ? "▶ 看视频" : "🔗 原文"}</a>
    : null;

  const toggle = (
    <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
      {(([["editorial", "📰 编辑长卡"], ["bento", "▦ Bento"], ["feed", "⊞ 瀑布流"]]) as [View, string][]).map(([v, label]) => (
        <button key={v} type="button" onClick={() => setView(v)} style={{
          padding: "4px 11px", borderRadius: 8, fontSize: 12, cursor: "pointer",
          border: "1px solid var(--border)", background: view === v ? "var(--accent-bg)" : "transparent",
          color: view === v ? "var(--accent)" : "var(--text-dim)", fontWeight: view === v ? 600 : 400,
        }}>{label}</button>
      ))}
    </div>
  );

  let body: ReactNode = null;

  if (view === "editorial") {
    body = (
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {items.map((m, i) => (
          <motion.div key={i} style={cardBase}
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.02, 0.3), duration: 0.25 }}>
            {m.type === "image" && m.image_url && <Img src={m.image_url} h={210} onClick={() => setLb(m.image_url!)} />}
            <div style={{ padding: 14 }}>
              {m.title && <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 8, color: "var(--text)", lineHeight: 1.4 }}>{m.title}</div>}
              {m.body && <div style={cardBody}>{m.body}</div>}
              {m._conflicts && m._conflicts.length > 0 && <div style={{ marginTop: 8, fontSize: 11.5, color: "var(--warn)" }}>⚡ {m._conflicts.join("；")}</div>}
              {linkLine(m)}
              {m.source && <div style={srcLine}>来源: {m.source}</div>}
            </div>
          </motion.div>
        ))}
      </div>
    );
  } else if (view === "bento") {
    body = (
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gridAutoRows: "118px", gap: 10 }}>
        {items.map((m, i) => {
          const hasImg = m.type === "image" && !!m.image_url;
          const span: CSSProperties = hasImg
            ? { gridColumn: "span 2", gridRow: "span 2" }
            : (i % 4 === 0 ? { gridColumn: "span 2" } : {});
          return (
            <div key={i} style={{ ...cardBase, ...span, display: "flex", flexDirection: "column" }}>
              {hasImg ? (
                <>
                  <div style={{ flex: 1, overflow: "hidden" }}><Img src={m.image_url!} h="100%" onClick={() => setLb(m.image_url!)} /></div>
                  {m.title && <div style={{ padding: "6px 9px", fontSize: 11.5, fontWeight: 600, color: "var(--text)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{m.title}</div>}
                </>
              ) : (
                <div style={{ padding: 11, overflow: "hidden", display: "flex", flexDirection: "column", height: "100%" }}>
                  {m.title && <div style={cardTitle}>{m.title}</div>}
                  {m.body && <div style={{ fontSize: 11.5, lineHeight: 1.55, color: "var(--text)", overflow: "hidden", flex: 1 }}>{m.body}</div>}
                  {linkLine(m)}
                  {m.source && <div style={{ fontSize: 10, color: "var(--text-faint)", marginTop: 4 }}>{m.source}</div>}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  } else {
    body = (
      <Masonry breakpointCols={BREAKPOINTS} className="bee-masonry" columnClassName="bee-masonry-col">
        {items.map((m, i) => (
          <motion.div key={i} style={{ ...cardBase, marginBottom: 12 }}
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.02, 0.3), duration: 0.25 }}>
            {m.type === "image" && m.image_url && <Img src={m.image_url} onClick={() => setLb(m.image_url!)} />}
            <div style={{ padding: 12 }}>
              {m.title && <div style={m.type === "image" ? { fontSize: 12.5, fontWeight: 600, marginBottom: 4 } : cardTitle}>{m.title}</div>}
              {m.body && <div style={cardBody}>{m.body}</div>}
              {m._conflicts && m._conflicts.length > 0 && <div style={{ marginTop: 6, fontSize: 11, color: "var(--warn)" }}>⚡ {m._conflicts.join("；")}</div>}
              {linkLine(m)}
              {m.source && <div style={srcLine}>来源: {m.source}</div>}
            </div>
          </motion.div>
        ))}
      </Masonry>
    );
  }

  return (
    <div style={{ width: "100%" }}>
      {toggle}
      {body}
      <style>{`
        .bee-masonry { display: flex; margin-left: -12px; width: auto; }
        .bee-masonry-col { padding-left: 12px; background-clip: padding-box; }
      `}</style>
      {lb && (
        <Lightbox open close={() => setLb(null)} slides={[{ src: proxied(lb) }]}
          render={{ buttonPrev: () => null, buttonNext: () => null }} />
      )}
    </div>
  );
}
