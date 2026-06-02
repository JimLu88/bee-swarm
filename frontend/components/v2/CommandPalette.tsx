"use client";

/** v6-S2 全局快捷搜索 — Cmd/Ctrl+K 打开, 搜索决策/记忆/主管/场景. */

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type Hit = {
  kind: "mode" | "decision" | "memory" | "persona";
  label: string;
  sub?: string;
  onPick: () => void;
};

type Props = {
  backendUrl: string;
  modes: { mode_id: string; label: string }[];
  onPickMode: (modeId: string) => void;
  onPickDecision: (decisionId: string, modeId: string) => void;
  onOpenSettings: () => void;
};

const backdrop: CSSProperties = {
  position: "fixed", inset: 0,
  background: "var(--overlay)", zIndex: 400,
  display: "flex", alignItems: "flex-start", justifyContent: "center",
  paddingTop: "12vh",
};

const panel: CSSProperties = {
  width: "min(640px, 92vw)", background: "var(--bg)", color: "var(--text)",
  borderRadius: 12, overflow: "hidden",
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border-strong)",
  boxShadow: "var(--shadow-lg)",
  display: "flex", flexDirection: "column",
};

const input: CSSProperties = {
  width: "100%", padding: "14px 16px", fontSize: 15,
  background: "transparent", border: "none", outline: "none",
  color: "var(--text)", borderBottomWidth: 1, borderBottomStyle: "solid",
  borderBottomColor: "var(--border)",
};

const list: CSSProperties = {
  maxHeight: "60vh", overflowY: "auto",
  display: "flex", flexDirection: "column",
};

const row = (active: boolean): CSSProperties => ({
  padding: "10px 14px", fontSize: 13, cursor: "pointer",
  display: "flex", alignItems: "center", gap: 10,
  background: active ? "var(--accent-bg)" : "transparent",
  borderLeftWidth: 3, borderLeftStyle: "solid",
  borderLeftColor: active ? "var(--accent)" : "transparent",
});

const kindIcon: Record<Hit["kind"], string> = {
  mode: "🎬",
  decision: "📜",
  memory: "💾",
  persona: "👤",
};

const kindLabel: Record<Hit["kind"], string> = {
  mode: "场景",
  decision: "历史决策",
  memory: "记忆",
  persona: "主管",
};

const kbdStyle: CSSProperties = {
  padding: "1px 5px", fontSize: 10, borderRadius: 3,
  background: "var(--bg-hover)",
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border-strong)",
};

export function CommandPalette({ backendUrl, modes, onPickMode, onPickDecision, onOpenSettings }: Props) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const [remote, setRemote] = useState<Hit[]>([]);
  const debounceRef = useRef<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    if (open && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 10);
      setActive(0);
    }
  }, [open]);

  const localHits = useMemo<Hit[]>(() => {
    const kw = q.trim().toLowerCase();
    const hits: Hit[] = [];
    modes.forEach((m) => {
      if (!kw || m.label.toLowerCase().includes(kw) || m.mode_id.includes(kw)) {
        hits.push({
          kind: "mode", label: m.label, sub: m.mode_id,
          onPick: () => { onPickMode(m.mode_id); setOpen(false); },
        });
      }
    });
    if (!kw || "设置".includes(kw) || "settings".startsWith(kw)) {
      hits.push({
        kind: "mode", label: "⚙️ 打开设置", sub: "AI / 记忆 / 高级 / 技术",
        onPick: () => { onOpenSettings(); setOpen(false); },
      });
    }
    return hits;
  }, [q, modes, onPickMode, onOpenSettings]);

  useEffect(() => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    const kw = q.trim();
    if (kw.length < 2) { setRemote([]); return; }
    debounceRef.current = window.setTimeout(async () => {
      const hits: Hit[] = [];
      try {
        const res = await fetchWithTimeout(
          `${backendUrl}/api/memory/search?q=${encodeURIComponent(kw)}&limit=6`,
          undefined, TIMEOUT_MS.default,
        );
        if (res.ok) {
          const j = await res.json();
          const rows: Array<{ id?: string; decision_id?: string; mode_id?: string; task?: string; summary?: string; kind?: string }> = j.items ?? j ?? [];
          rows.forEach((r) => {
            const did = r.decision_id ?? r.id ?? "";
            const isDecision = r.kind === "decision" || !!r.decision_id;
            hits.push({
              kind: isDecision ? "decision" : "memory",
              label: r.task ?? r.summary ?? did ?? "?",
              sub: `${r.mode_id ?? "—"}${r.kind ? ` · ${r.kind}` : ""}`,
              onPick: () => {
                if (isDecision && did && r.mode_id) {
                  onPickDecision(did, r.mode_id);
                }
                setOpen(false);
              },
            });
          });
        }
      } catch { /* 后端可能没此端点, silent */ }
      setRemote(hits);
    }, 300) as unknown as number;
    return () => { if (debounceRef.current) window.clearTimeout(debounceRef.current); };
  }, [q, backendUrl, onPickDecision]);

  const all = useMemo(() => [...localHits, ...remote], [localHits, remote]);

  const move = useCallback((delta: number) => {
    setActive((a) => Math.max(0, Math.min(all.length - 1, a + delta)));
  }, [all.length]);

  const onInputKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter") {
      e.preventDefault();
      const hit = all[active];
      if (hit) hit.onPick();
    }
  };

  if (!open) return null;

  return (
    <div style={backdrop} onClick={() => setOpen(false)}>
      <div style={panel} onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          style={input}
          placeholder="搜索场景 / 历史决策 / 记忆..."
          value={q}
          onChange={(e) => { setQ(e.target.value); setActive(0); }}
          onKeyDown={onInputKey}
        />
        <div style={list}>
          {all.length === 0 && (
            <div style={{ padding: 24, fontSize: 12, color: "var(--text-faint)", textAlign: "center" }}>
              {q.trim().length < 2 ? "输入关键字搜索 (≥2 字触发远程搜索)" : "无匹配"}
            </div>
          )}
          {all.map((h, i) => (
            <div key={`${h.kind}-${i}-${h.label}`}
                 style={row(i === active)}
                 onMouseEnter={() => setActive(i)}
                 onClick={() => h.onPick()}>
              <span style={{ width: 22 }}>{kindIcon[h.kind]}</span>
              <span style={{ flex: 1, color: "var(--text)" }}>{h.label}</span>
              {h.sub && <span style={{ fontSize: 11, color: "var(--text-faint)" }}>{h.sub}</span>}
              <span style={{ fontSize: 10, color: "var(--text-faint)" }}>{kindLabel[h.kind]}</span>
            </div>
          ))}
        </div>
        <div style={{
          padding: "8px 14px", fontSize: 10, color: "var(--text-faint)",
          borderTopWidth: 1, borderTopStyle: "solid", borderTopColor: "var(--bg-hover)",
          display: "flex", gap: 12,
        }}>
          <span><kbd style={kbdStyle}>↑↓</kbd> 移动</span>
          <span><kbd style={kbdStyle}>Enter</kbd> 选择</span>
          <span><kbd style={kbdStyle}>Esc</kbd> 关闭</span>
        </div>
      </div>
    </div>
  );
}
