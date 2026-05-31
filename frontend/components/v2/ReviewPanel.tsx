"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type DueItem = {
  id: string;
  kind: string;
  content: string;
  importance: number;
  ef: number;
  interval_days: number;
  repetitions: number;
};

type Props = { backendUrl: string };

const wrap: CSSProperties = {
  padding: 14, borderRadius: 12,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
  background: "var(--bg-subtle)",
  display: "flex", flexDirection: "column", gap: 10,
};

const itemBox: CSSProperties = {
  padding: "10px 12px", borderRadius: 8,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--bg-hover)",
  background: "var(--bg-subtle)",
};

const btnGrade = (g: number): CSSProperties => ({
  padding: "4px 10px", fontSize: 12, borderRadius: 6,
  borderWidth: 1, borderStyle: "solid",
  borderColor: g >= 4 ? "#4caf50" : g >= 3 ? "var(--accent)" : "#f44336",
  background: g >= 4 ? "rgba(76,175,80,0.10)" : g >= 3 ? "var(--accent-bg)" : "rgba(244,67,54,0.10)",
  color: "inherit", cursor: "pointer",
});

export function ReviewPanel({ backendUrl }: Props) {
  const [items, setItems] = useState<DueItem[]>([]);
  const [stats, setStats] = useState<{ total: number; due: number; week: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // v6-O 走 swarm 代理 (解决浏览器跨域 + bearer)
  const memBase = `${backendUrl}/api`;

  const reload = useCallback(async () => {
    setError(null);
    try {
      const [dueRes, statsRes] = await Promise.all([
        fetchWithTimeout(`${memBase}/memory/review/due?limit=20`,
          { headers: { Authorization: "Bearer dev-token-change-me" } }, TIMEOUT_MS.default),
        fetchWithTimeout(`${memBase}/memory/review/stats`,
          { headers: { Authorization: "Bearer dev-token-change-me" } }, TIMEOUT_MS.default),
      ]);
      if (dueRes.ok) setItems((await dueRes.json()).items || []);
      if (statsRes.ok) {
        const s = await statsRes.json();
        setStats({ total: s.total_enrolled || 0, due: s.due_now || 0, week: s.due_within_7d || 0 });
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }, [memBase]);

  useEffect(() => { reload(); }, [reload]);

  // v6-S3 键盘快捷键打分: 1=不会 2=勉强 3=会 4=完全掌握 (照 Anki 习惯)
  const itemsRef = useRef(items);
  const busyRef = useRef(busy);
  itemsRef.current = items;
  busyRef.current = busy;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (busyRef.current) return;
      const first = itemsRef.current[0];
      if (!first) return;
      // 输入框获焦时不抢键
      const tgt = e.target as HTMLElement | null;
      if (tgt && (tgt.tagName === "INPUT" || tgt.tagName === "TEXTAREA" || tgt.isContentEditable)) return;
      const map: Record<string, number> = { "1": 0, "2": 3, "3": 4, "4": 5 };
      const g = map[e.key];
      if (g == null) return;
      e.preventDefault();
      void grade(first.id, g);  // grade 在下方定义, useRef 闭包安全
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const grade = useCallback(async (memory_id: string, g: number) => {
    setBusy(true);
    try {
      await fetchWithTimeout(`${memBase}/memory/review/grade`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer dev-token-change-me" },
        body: JSON.stringify({ memory_id, grade: g }),
      }, TIMEOUT_MS.default);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [memBase, reload]);

  return (
    <div style={wrap}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>📝 v3-F 复习闸 (SM-2)</div>
        {stats && (
          <div style={{ fontSize: 11, opacity: 0.65 }}>
            纳入复习 {stats.total} · 今天到期 {stats.due} · 本周 {stats.week}
          </div>
        )}
      </div>
      {/* G4 "这是什么"说明 */}
      <details style={{ fontSize: 11 }}>
        <summary style={{ cursor: "pointer", color: "var(--info)" }}>💡 这是什么 / 为什么没数据?</summary>
        <div style={{
          padding: 10, marginTop: 6, borderRadius: 6, lineHeight: 1.7,
          background: "var(--info-bg)", color: "var(--text-dim)",
          borderWidth: 1, borderStyle: "solid", borderColor: "var(--info-bg)",
        }}>
          <b style={{ color: "var(--info)" }}>Anki SM-2 复习算法</b> — 当部门主管学到一条新知识 (比如"PDA 是急性心梗的常见类型"),
          这条会进入"复习闸". 按 Anki 间隔 (1天 → 3天 → 7天 → 15天 → 1月...) 让 AI 反复"自测",
          答对了加大间隔, 答错重置. 长期下来主管的专业知识就稳了.
          <br/><br/>
          <b style={{ color: "var(--info)" }}>没数据是正常的</b> — 你还没存过 <code>kind=knowledge_*</code> 类型的记忆,
          或者今天没到期的卡. 跑几次决策, 或在 CoordinatorPanel 触发 <code>p16_knowledge_curator</code> 后会有.
        </div>
      </details>
      {error && (
        <div style={{
          padding: "10px 12px", borderRadius: 8, fontSize: 12,
          background: "rgba(255,179,0,0.08)",
          borderWidth: 1, borderStyle: "solid", borderColor: "rgba(255,179,0,0.30)",
          color: "#ffb300", lineHeight: 1.6,
        }}>
          <b>⚠ 暂时取不到复习数据</b>
          <div style={{ color: "var(--text-dim)", marginTop: 4 }}>
            可能原因: bee-memory (端口 8004) 没启动 / Bearer Token 不对 / 还没存过 kind=knowledge_* 的记忆.
          </div>
          <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
            <button type="button" onClick={async () => {
              setError(null);
              try {
                await fetchWithTimeout(`${backendUrl}/api/tray/start/bee-memory`,
                  { method: "POST" }, TIMEOUT_MS.default);
              } catch { /* tray 端可能没启, 让用户看到下一行提示 */ }
              setTimeout(() => { void reload(); }, 1500);
            }} style={{
              padding: "4px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer",
              borderWidth: 1, borderStyle: "solid", borderColor: "#4caf50",
              background: "rgba(76,175,80,0.12)", color: "#a5d6a7",
            }}>🚀 尝试启动 bee-memory</button>
            <button type="button" onClick={() => { void reload(); }} style={{
              padding: "4px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer",
              borderWidth: 1, borderStyle: "solid", borderColor: "var(--border-strong)",
              background: "var(--bg-subtle)", color: "var(--text)",
            }}>🔄 重试</button>
            <a href="#" onClick={(e) => {
              e.preventDefault();
              alert("手动启动方式:\n\n1. 右下角托盘找 🐝 图标\n2. 右键 → 启动 bee-memory\n\n或:\n\ncd D:/AI/AI 记忆中心\nuvicorn backend.app.main:app --port 8004");
            }} style={{ fontSize: 11, color: "var(--info)", alignSelf: "center" }}>📖 手动启动方式</a>
          </div>
          <div style={{ color: "var(--text-dim)", marginTop: 6, fontSize: 10 }}>详情: {error}</div>
        </div>
      )}
      {items.length === 0 && (
        <div style={{ fontSize: 12, opacity: 0.55 }}>暂无到期复习项。重要记忆可在记忆面板点 [纳入复习闸]。</div>
      )}
      {items.map((it) => (
        <div key={it.id} style={itemBox}>
          <div style={{ fontSize: 11, opacity: 0.55, marginBottom: 4 }}>
            {it.kind} · 间隔 {it.interval_days} 天 · 复习 {it.repetitions} 次 · EF {it.ef.toFixed(2)}
          </div>
          <div style={{ fontSize: 13, marginBottom: 8 }}>{it.content.slice(0, 280)}{it.content.length > 280 ? "…" : ""}</div>
          <div style={{ display: "flex", gap: 6 }}>
            <button type="button" style={btnGrade(0)} disabled={busy} onClick={() => grade(it.id, 0)}>不会 (0)</button>
            <button type="button" style={btnGrade(3)} disabled={busy} onClick={() => grade(it.id, 3)}>勉强 (3)</button>
            <button type="button" style={btnGrade(4)} disabled={busy} onClick={() => grade(it.id, 4)}>会 (4)</button>
            <button type="button" style={btnGrade(5)} disabled={busy} onClick={() => grade(it.id, 5)}>完全掌握 (5)</button>
          </div>
        </div>
      ))}
    </div>
  );
}
