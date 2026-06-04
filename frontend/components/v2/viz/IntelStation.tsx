"use client";

/** v11 全屏情报站 (方案1 作战室 lite): 点开弹出整屏深色指挥台, 把图文资料做成影院级沉浸网格.
 *  WorldMonitor 风: 深色底 + 脉动渐变 + 大图 + 来源徽章 + 扫描线. 图片走 /api/img 代理. */

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { CSSProperties } from "react";
import type { MediaCard } from "./InfoFeed";
import { GlobeHero } from "./GlobeHero";
import { MapPins, type MapPlace } from "./MapPins";

type Props = {
  open: boolean;
  onClose: () => void;
  title?: string;
  mediaCards: MediaCard[];
  mapPlaces?: MapPlace[];
  backendUrl?: string;
};

export function IntelStation({ open, onClose, title = "情报站", mediaCards, mapPlaces = [], backendUrl = "" }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [open, onClose]);

  // 点地图钉 → 聚焦某家店 (下方卡片随之过滤); null = 看全部
  const [focused, setFocused] = useState<number | null>(null);

  const proxied = (u?: string): string => {
    if (!u) return "";
    if (u.startsWith("data:")) return u;
    // backendUrl 为空=同源部署 → 相对 /api/img 仍走后端代理(绕过防盗链);见 InfoFeed 同款修复。
    return `${backendUrl}/api/img?url=${encodeURIComponent(u)}`;
  };

  // 无封面图时的兜底: 按来源/标题生成稳定渐变 + 图标, 保证"一定有图"(永不空白)
  const coverBg = (seed: string): string => {
    let h = 0;
    for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) % 360;
    return `linear-gradient(135deg, hsl(${h},45%,24%), hsl(${(h + 48) % 360},52%,13%))`;
  };
  const sourceEmoji = (s?: string): string => {
    const k = (s || "").toLowerCase();
    if (k.includes("dianping") || k.includes("点评")) return "🍽";
    if (k.includes("xiaohongshu") || k.includes("小红")) return "📕";
    if (k.includes("zhihu") || k.includes("知乎")) return "💡";
    if (k.includes("reddit")) return "👽";
    if (k.includes("bilibili") || k.includes("youtube") || k.includes("douyin")) return "🎬";
    if (k.includes("github") || k.includes("stack")) return "💻";
    if (k.includes("weibo") || k.includes("xueqiu")) return "📈";
    if (k.includes("trip") || k.includes("mafengwo") || k.includes("马蜂窝")) return "✈️";
    if (k.includes("wikipedia") || k.includes("百科")) return "📖";
    if (k.includes("taobao") || k.includes("jd") || k.includes("smzdm")) return "🛍";
    return "🔖";
  };

  if (!open) return null;

  const cards = mediaCards.filter((m) => m.title || m.image_url || m.body);
  const imgCount = cards.filter((m) => m.type === "image" && m.image_url).length;

  // 聚焦某家店时, 只显示标题/正文里提到这家店的卡片 (best-effort 名称匹配)
  const focusedPlace = focused != null ? mapPlaces[focused] : null;
  const displayCards = focusedPlace
    ? cards.filter((m) => {
        const hay = `${m.title || ""} ${m.body || ""}`.toLowerCase();
        const key = (focusedPlace.poi_name || focusedPlace.name || "").toLowerCase();
        if (!key) return false;
        if (hay.includes(key)) return true;
        const core = key.replace(/(店|餐厅|餐廳|馆|館|总店|分店|旗舰店)$/g, "").slice(0, 6);
        return core.length >= 2 && hay.includes(core);
      })
    : cards;

  const shell: CSSProperties = {
    position: "fixed", inset: 0, zIndex: 9999, background: "#070b14",
    color: "#e6edf6", display: "flex", flexDirection: "column", overflow: "hidden",
  };

  return (
    <AnimatePresence>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }} style={shell}>
        {/* 动态背景: 脉动径向渐变 + 网格 */}
        <div aria-hidden style={{
          position: "absolute", inset: 0, pointerEvents: "none",
          background: "radial-gradient(1200px 600px at 20% -10%, rgba(56,120,255,0.18), transparent 60%), radial-gradient(900px 500px at 100% 110%, rgba(168,85,247,0.16), transparent 55%)",
          animation: "intelPulse 8s ease-in-out infinite",
        }} />
        <div aria-hidden style={{
          position: "absolute", inset: 0, pointerEvents: "none", opacity: 0.06,
          backgroundImage: "linear-gradient(rgba(255,255,255,.6) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.6) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
        }} />

        {/* 顶栏 */}
        <div style={{
          position: "relative", zIndex: 2, display: "flex", alignItems: "center", gap: 12,
          padding: "16px 24px", borderBottom: "1px solid rgba(255,255,255,0.08)",
          background: "rgba(7,11,20,0.7)", backdropFilter: "blur(10px)",
        }}>
          <span style={{ width: 9, height: 9, borderRadius: "50%", background: "#3ddc84", boxShadow: "0 0 10px #3ddc84", animation: "intelBlink 1.6s ease-in-out infinite" }} />
          <span style={{ fontSize: 13, letterSpacing: 2, fontWeight: 700, fontFamily: "ui-monospace, monospace", color: "#9fb3c8" }}>🛰 情报站 · INTEL</span>
          <span style={{ fontSize: 16, fontWeight: 800 }}>{title}</span>
          <span style={{ marginLeft: "auto", fontSize: 12, color: "#7d93ab", fontFamily: "ui-monospace, monospace" }}>{cards.length} 条 · {imgCount} 图</span>
          <button type="button" onClick={onClose} aria-label="关闭"
            style={{ marginLeft: 8, width: 34, height: 34, borderRadius: 9, border: "1px solid rgba(255,255,255,0.14)", background: "rgba(255,255,255,0.06)", color: "#e6edf6", cursor: "pointer", fontSize: 16 }}>✕</button>
        </div>

        {/* 滚动区: 3D 地球 hero (scrollytelling) → 影院级网格 */}
        <div style={{ position: "relative", zIndex: 1, flex: 1, overflowY: "auto" }}>
          {/* 真 3D 地球头图, 向下滚动隐入情报网格 */}
          <GlobeHero count={cards.length} />
          {/* 方案4 地图钉店: 决策推荐的店铺/地点 (有坐标才显示) */}
          {mapPlaces.length > 0 && <MapPins places={mapPlaces} onPick={setFocused} selected={focused} />}
          <div style={{ padding: "20px 24px 40px" }}>
          {focusedPlace && (
            <div style={{ maxWidth: 1400, margin: "0 auto 16px", padding: "14px 18px", borderRadius: 14, border: "1px solid rgba(61,220,132,0.35)", background: "rgba(61,220,132,0.08)", display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
              <button type="button" onClick={() => setFocused(null)}
                style={{ padding: "7px 14px", borderRadius: 9, border: "1px solid rgba(255,255,255,0.2)", background: "rgba(255,255,255,0.08)", color: "#e6edf6", cursor: "pointer", fontSize: 13, fontWeight: 600, whiteSpace: "nowrap" }}>
                ← 返回全部 {mapPlaces.length} 家
              </button>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 16, fontWeight: 800, color: "#fff" }}>#{(focused ?? 0) + 1} {focusedPlace.poi_name || focusedPlace.name}</div>
                <div style={{ fontSize: 12.5, color: "#9fb3c8", marginTop: 3 }}>
                  {[focusedPlace.category, focusedPlace.rating != null ? `★ ${focusedPlace.rating}` : "", focusedPlace.cost != null ? `人均 ¥${focusedPlace.cost}` : ""].filter(Boolean).join("  ·  ")}
                </div>
                {focusedPlace.address && <div style={{ fontSize: 12, color: "#7d93ab", marginTop: 3 }}>📍 {focusedPlace.address}</div>}
                {focusedPlace.tel && <div style={{ fontSize: 12, color: "#7d93ab", marginTop: 2 }}>☎ {focusedPlace.tel}</div>}
              </div>
              <span style={{ marginLeft: "auto", fontSize: 12, color: "#7d93ab", whiteSpace: "nowrap" }}>{displayCards.length} 条相关图文</span>
            </div>
          )}
          {displayCards.length === 0 ? (
            <div style={{ textAlign: "center", color: "#7d93ab", marginTop: 80 }}>{focusedPlace ? "暂无该店的相关图文资料 (可点「返回全部」看全部情报)" : "暂无情报"}</div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gridAutoRows: "200px", gap: 14, maxWidth: 1400, margin: "0 auto" }}>
              {cards.map((m, i) => {
                const hasImg = m.type === "image" && !!m.image_url;
                const big = hasImg && i % 5 === 0; // 每隔几张放一张大图, 制造节奏
                const span: CSSProperties = big ? { gridColumn: "span 2", gridRow: "span 2" } : (hasImg ? { gridRow: "span 2" } : {});
                return (
                  <motion.div key={i}
                    initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.5), duration: 0.35 }}
                    whileHover={{ scale: 1.015 }}
                    style={{
                      ...span, position: "relative", borderRadius: 14, overflow: "hidden",
                      border: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.04)",
                      boxShadow: "var(--shadow-lg)",
                      cursor: m.url ? "pointer" : "default",
                    }}
                    onClick={() => { if (m.url) window.open(m.url, "_blank", "noopener"); }}>
                    {hasImg ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={proxied(m.image_url)} alt="" onError={(e) => {
                        // 真图加载失败 → 退化成兜底渐变封面 (替换父节点背景, 保证不空白)
                        const el = e.currentTarget as HTMLImageElement;
                        el.style.display = "none";
                        const p = el.parentElement;
                        if (p && !p.dataset.fb) { p.dataset.fb = "1"; p.style.background = coverBg(m.title || m.source || String(i)); }
                      }}
                        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
                    ) : (
                      <>
                        <div style={{ position: "absolute", inset: 0, background: coverBg(m.title || m.source || String(i)) }} />
                        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 44, opacity: 0.4 }}>{sourceEmoji(m.source)}</div>
                      </>
                    )}
                    {/* 统一暗角 + 来源徽章 + 可信度 + 标题, 不论真图还是占位都有 */}
                    <div style={{ position: "absolute", inset: 0, background: "linear-gradient(to top, rgba(0,0,0,0.88) 0%, rgba(0,0,0,0.25) 48%, transparent 76%)" }} />
                    {m.source && <span style={{ position: "absolute", top: 10, left: 10, padding: "3px 9px", borderRadius: 999, fontSize: 10.5, fontWeight: 600, background: "rgba(0,0,0,0.5)", backdropFilter: "blur(6px)", color: "#cfe0f0" }}>{m.source}</span>}
                    {m.credibility != null && <span style={{ position: "absolute", top: 10, right: 10, padding: "3px 9px", borderRadius: 999, fontSize: 10.5, fontWeight: 700, color: "#06121f", background: m.credibility >= 70 ? "rgba(61,220,132,0.9)" : m.credibility >= 40 ? "rgba(245,179,1,0.9)" : "rgba(214,69,61,0.85)" }}>可信 {m.credibility}</span>}
                    {(m.title || m.body) && <div style={{ position: "absolute", left: 14, right: 14, bottom: 12, fontSize: big ? 18 : 14, fontWeight: 700, lineHeight: 1.35, color: "#fff", textShadow: "0 2px 12px rgba(0,0,0,0.7)", display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{m.title || m.body}</div>}
                  </motion.div>
                );
              })}
            </div>
          )}
          </div>
        </div>

        <style>{`
          @keyframes intelPulse { 0%,100%{opacity:.7} 50%{opacity:1} }
          @keyframes intelBlink { 0%,100%{opacity:1} 50%{opacity:.3} }
        `}</style>
      </motion.div>
    </AnimatePresence>
  );
}
