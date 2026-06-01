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
import type { MapPlace } from "./MapPins";

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
  mapPlaces?: MapPlace[];
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

export function InfoFeed({ deptQuotes = [], mediaCards = [], mapPlaces = [], backendUrl = "" }: Props) {
  const [lb, setLb] = useState<string | null>(null);
  const [view, setView] = useState<View>("editorial");

  // 数据墙用: 有评分/人均的地点 (高德 biz_ext)
  const metricPlaces = mapPlaces.filter((p) => p && (p.rating != null || p.cost != null));

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
      {(([["editorial", "📰 编辑长卡"], ["bento", "▦ 数据墙"], ["feed", "⊞ 瀑布流"]]) as [View, string][]).map(([v, label]) => (
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
    // Gemini 杂志式: 有图卡 = 大 Hero 图 + 标题压在底部渐变上 + 来源徽章; 无图卡 = 左强调条 + 大字排版
    body = (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {items.map((m, i) => {
          const hasImg = m.type === "image" && !!m.image_url;
          if (hasImg) {
            return (
              <motion.div key={i}
                initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.4), duration: 0.3 }}
                whileHover={{ y: -3 }}
                style={{ ...cardBase, position: "relative", cursor: "zoom-in" }}
                onClick={() => setLb(m.image_url!)}>
                <div style={{ position: "relative", width: "100%", aspectRatio: "16 / 9", overflow: "hidden" }}>
                  <Img src={m.image_url!} h="100%" />
                  {/* 底部渐变压字 */}
                  <div style={{ position: "absolute", inset: 0, background: "linear-gradient(to top, rgba(0,0,0,0.78) 0%, rgba(0,0,0,0.25) 42%, rgba(0,0,0,0) 70%)" }} />
                  {m.source && (
                    <span style={{ position: "absolute", top: 12, left: 12, padding: "3px 10px", borderRadius: 999, fontSize: 11, fontWeight: 600, color: "#fff", background: "rgba(0,0,0,0.45)", backdropFilter: "blur(6px)" }}>{m.source}</span>
                  )}
                  {m.title && (
                    <div style={{ position: "absolute", left: 16, right: 16, bottom: 14, color: "#fff", fontSize: 18, fontWeight: 800, lineHeight: 1.35, textShadow: "0 2px 12px rgba(0,0,0,0.5)" }}>{m.title}</div>
                  )}
                </div>
                {(m.body || (m.url && (m.type === "link" || m.type === "video"))) && (
                  <div style={{ padding: "12px 16px 14px" }}>
                    {m.body && <div style={cardBody}>{m.body}</div>}
                    {linkLine(m)}
                  </div>
                )}
              </motion.div>
            );
          }
          return (
            <motion.div key={i}
              initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.4), duration: 0.3 }}
              whileHover={{ y: -2 }}
              style={{ ...cardBase, padding: "16px 18px", borderLeft: "3px solid var(--accent)" }}>
              {m.title && <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8, color: "var(--text)", lineHeight: 1.4 }}>{m.title}</div>}
              {m.body && <div style={cardBody}>{m.body}</div>}
              {m._conflicts && m._conflicts.length > 0 && <div style={{ marginTop: 8, fontSize: 11.5, color: "var(--warn)" }}>⚡ {m._conflicts.join("；")}</div>}
              {linkLine(m)}
              {m.source && <div style={srcLine}>来源: {m.source}</div>}
            </motion.div>
          );
        })}
      </div>
    );
  } else if (view === "bento") {
    // 升级版 Bento 数据墙 (Linear/Vercel 风): KPI 大数字 + 每店评分仪表盘/人均/迷你条, 再接图文格
    const rated = metricPlaces.filter((p) => p.rating != null);
    const avgRating = rated.length ? rated.reduce((s, p) => s + (p.rating || 0), 0) / rated.length : 0;
    const costs = metricPlaces.map((p) => p.cost).filter((c): c is number => c != null);
    const costMin = costs.length ? Math.min(...costs) : null;
    const costMax = costs.length ? Math.max(...costs) : null;

    const StatTile = ({ label, value, sub, accent }: { label: string; value: ReactNode; sub?: string; accent?: string }) => (
      <div style={{ ...cardBase, padding: "13px 16px", display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
        <div style={{ fontSize: 11, color: "var(--text-dim)", fontWeight: 600, letterSpacing: 0.4 }}>{label}</div>
        <div style={{ fontSize: 26, fontWeight: 800, color: accent || "var(--text)", lineHeight: 1.1, fontVariantNumeric: "tabular-nums" }}>{value}</div>
        {sub && <div style={{ fontSize: 11, color: "var(--text-faint)" }}>{sub}</div>}
      </div>
    );

    const GaugeRing = ({ rating }: { rating: number }) => {
      const pct = Math.max(0, Math.min(1, rating / 5));
      return (
        <div style={{ position: "relative", width: 60, height: 60, borderRadius: "50%", flexShrink: 0, background: `conic-gradient(var(--accent) ${pct * 360}deg, var(--border) 0)` }}>
          <div style={{ position: "absolute", inset: 5, borderRadius: "50%", background: "var(--bg-card)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontSize: 17, fontWeight: 800, color: "var(--text)", lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>{rating.toFixed(1)}</span>
            <span style={{ fontSize: 9, color: "#f59e0b" }}>★ 评分</span>
          </div>
        </div>
      );
    };

    body = (
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {metricPlaces.length > 0 && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(118px, 1fr))", gap: 10 }}>
              <StatTile label="推荐地点" value={`${mapPlaces.length}`} sub="家已定位" accent="var(--accent)" />
              {rated.length > 0 && <StatTile label="平均评分" value={avgRating.toFixed(1)} sub={`${rated.length} 家有评分`} accent="#f59e0b" />}
              {costMin != null && <StatTile label="人均价位" value={costMin === costMax ? `¥${costMin}` : `¥${costMin}–${costMax}`} sub="大众点评口径" />}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(248px, 1fr))", gap: 10 }}>
              {metricPlaces.map((p, i) => (
                <motion.div key={`pl-${i}`} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.3), duration: 0.3 }}
                  whileHover={{ y: -2 }} style={{ ...cardBase, padding: 14, display: "flex", gap: 12, alignItems: "center" }}>
                  {p.rating != null ? <GaugeRing rating={p.rating} /> : (
                    <div style={{ width: 60, height: 60, borderRadius: "50%", border: "1px dashed var(--border)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: "var(--text-faint)", flexShrink: 0, textAlign: "center" }}>暂无评分</div>
                  )}
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ width: 18, height: 18, borderRadius: 6, background: "var(--accent-bg)", color: "var(--accent)", fontSize: 11, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{i + 1}</span>
                      <span style={{ fontSize: 14, fontWeight: 700, color: "var(--text)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{p.poi_name || p.name}</span>
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8, alignItems: "baseline" }}>
                      {p.cost != null && <span style={{ fontSize: 18, fontWeight: 800, color: "var(--text)" }}>¥{p.cost}<span style={{ fontSize: 10, fontWeight: 400, color: "var(--text-dim)" }}> /人</span></span>}
                      {p.category && <span style={{ fontSize: 10.5, padding: "2px 7px", borderRadius: 999, background: "var(--accent-bg)", color: "var(--text-dim)" }}>{p.category}</span>}
                    </div>
                    {p.rating != null && (
                      <div style={{ marginTop: 8, height: 5, borderRadius: 3, background: "var(--border)", overflow: "hidden" }}>
                        <div style={{ width: `${Math.min(100, (p.rating / 5) * 100)}%`, height: "100%", background: "linear-gradient(90deg,#f59e0b,var(--accent))" }} />
                      </div>
                    )}
                  </div>
                </motion.div>
              ))}
            </div>
          </>
        )}
        {/* 图文 Bento: 图片大格 + 文本小格 */}
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
