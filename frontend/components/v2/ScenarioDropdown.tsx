"use client";

import { useState, useRef, useEffect, type CSSProperties } from "react";
import { BUILTIN_MODES } from "./ModePicker";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type Props = {
  selected: string;
  onSelect: (mode: string) => void;
  onManage: () => void; // 打开设置抽屉的"场景"tab
  backendUrl?: string;  // v7 W5: 拉全部 63 场景(含 50 自定义)
};

type ModeItem = { mode_id: string; label: string; emoji: string };

const wrap: CSSProperties = { position: "relative", display: "inline-block" };

const trigger: CSSProperties = {
  display: "flex", alignItems: "center", gap: 8,
  padding: "8px 14px", borderRadius: 10, cursor: "pointer",
  border: "1px solid var(--border, var(--border-strong))",
  background: "var(--bg-elev, var(--bg-subtle))",
  color: "var(--text, inherit)", fontSize: 14, fontWeight: 600,
};

const menu: CSSProperties = {
  position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 50,
  minWidth: 260, maxHeight: 360, overflowY: "auto",
  borderRadius: 10, padding: 6,
  border: "1px solid var(--border, var(--border))",
  background: "var(--bg-card, #1a1a1e)",
  boxShadow: "var(--shadow, 0 8px 28px rgba(0,0,0,0.35))",
};

const item = (active: boolean): CSSProperties => ({
  display: "flex", alignItems: "center", gap: 8,
  padding: "8px 10px", borderRadius: 7, cursor: "pointer", fontSize: 13,
  background: active ? "var(--accent-bg, var(--accent-bg))" : "transparent",
  color: "var(--text, inherit)",
});

export function ScenarioDropdown({ selected, onSelect, onManage, backendUrl }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const [allModes, setAllModes] = useState<ModeItem[]>(
    BUILTIN_MODES.map((m) => ({ mode_id: m.mode_id, label: m.label, emoji: m.emoji })));

  // v7 W5: 拉后端全部场景(13内置+50自定义); 内置保留 emoji, 自定义给默认图标
  useEffect(() => {
    if (!backendUrl) return;
    let aborted = false;
    (async () => {
      try {
        const res = await fetchWithTimeout(`${backendUrl}/api/modes`, undefined, TIMEOUT_MS.default);
        if (!res.ok) return;
        const j = await res.json();
        if (aborted || !Array.isArray(j.modes)) return;
        const emojiOf = (id: string) => BUILTIN_MODES.find((b) => b.mode_id === id)?.emoji || "🗂";
        setAllModes(j.modes.map((m: { mode_id: string; label: string }) => ({
          mode_id: m.mode_id, label: m.label, emoji: emojiOf(m.mode_id),
        })));
      } catch { /* 保持内置兜底 */ }
    })();
    return () => { aborted = true; };
  }, [backendUrl]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const cur = allModes.find((m) => m.mode_id === selected);

  return (
    <div style={wrap} ref={ref}>
      <button type="button" style={trigger} onClick={() => setOpen((v) => !v)}>
        <span>{cur?.emoji || "🎬"}</span>
        <span>{cur?.label || "选择场景"}</span>
        <span style={{ opacity: 0.5, fontSize: 11 }}>▾</span>
      </button>
      {open && (
        <div style={menu}>
          {allModes.map((m) => (
            <div key={m.mode_id} style={item(m.mode_id === selected)}
              onClick={() => { onSelect(m.mode_id); setOpen(false); }}>
              <span>{m.emoji}</span><span>{m.label}</span>
            </div>
          ))}
          <div style={{ borderTop: "1px solid var(--border, var(--border))", marginTop: 6, paddingTop: 6 }}>
            <div style={item(false)} onClick={() => { onManage(); setOpen(false); }}>
              <span>⚙</span><span>管理场景 / 顾问团 / 自定义…</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
