"use client";

/** v11 全屏情报站 (方案1 作战室 lite): 点开弹出整屏深色指挥台, 把图文资料做成影院级沉浸网格.
 *  WorldMonitor 风: 深色底 + 脉动渐变 + 大图 + 来源徽章 + 扫描线. 图片走 /api/img 代理. */

import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { CSSProperties } from "react";
import type { MediaCard } from "./InfoFeed";
import { GlobeHero } from "./GlobeHero";

type Props = {
  open: boolean;
  onClose: () => void;
  title?: string;
  mediaCards: MediaCard[];
  backendUrl?: string;
};

export function IntelStation({ open, onClose, title = "情报站", mediaCards, backendUrl = "" }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [open, onClose]);

  const proxied = (u?: string): string => {
    if (!u) return "";
    if (u.startsWith("data:") || !backendUrl) return u;
    return `${backendUrl}/api/img?url=${encodeURIComponent(u)}`;
  };

  if (!open) return null;

  const cards = mediaCards.filter((m) => m.title || m.image_url || m.body);
  const imgCount = cards.filter((m) => m.type === "image" && m.image_url).length;

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
          <div style={{ padding: "20px 24px 40px" }}>
          {cards.length === 0 ? (
            <div style={{ textAlign: "center", color: "#7d93ab", marginTop: 80 }}>暂无情报</div>
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
                      boxShadow: "0 8px 30px rgba(0,0,0,0.4)",
                      cursor: m.url ? "pointer" : "default",
                    }}
                    onClick={() => { if (m.url) window.open(m.url, "_blank", "noopener"); }}>
                    {hasImg ? (
                      <>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={proxied(m.image_url)} alt="" onError={(e) => { (e.currentTarget as HTMLImageElement).style.opacity = "0"; }}
                          style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
                        <div style={{ position: "absolute", inset: 0, background: "linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.2) 45%, transparent 72%)" }} />
                        {m.source && <span style={{ position: "absolute", top: 10, left: 10, padding: "3px 9px", borderRadius: 999, fontSize: 10.5, fontWeight: 600, background: "rgba(0,0,0,0.5)", backdropFilter: "blur(6px)", color: "#cfe0f0" }}>{m.source}</span>}
                        {m.title && <div style={{ position: "absolute", left: 14, right: 14, bottom: 12, fontSize: big ? 18 : 14, fontWeight: 700, lineHeight: 1.35, color: "#fff", textShadow: "0 2px 12px rgba(0,0,0,0.6)" }}>{m.title}</div>}
                      </>
                    ) : (
                      <div style={{ padding: 16, height: "100%", display: "flex", flexDirection: "column" }}>
                        {m.title && <div style={{ fontSize: 14, fontWeight: 700, color: "#e6edf6", marginBottom: 8, lineHeight: 1.4 }}>{m.title}</div>}
                        {m.body && <div style={{ fontSize: 12.5, lineHeight: 1.6, color: "#aebfd1", overflow: "hidden", flex: 1 }}>{m.body}</div>}
                        {m.source && <div style={{ fontSize: 10.5, color: "#6f86a0", marginTop: 8, fontFamily: "ui-monospace, monospace" }}>{m.source}</div>}
                      </div>
                    )}
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
