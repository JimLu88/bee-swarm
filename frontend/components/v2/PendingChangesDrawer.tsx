"use client";

import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type PC = {
  id: string;
  ts: number;
  evolver: string;
  kind: string;
  target: string;
  description: string;
  proposal: unknown;
  status: string;
};

type Props = { backendUrl: string };

const btn = (n: number): CSSProperties => ({
  position: "relative",
  padding: "6px 12px", borderRadius: 6, fontSize: 13,
  borderWidth: 1, borderStyle: "solid",
  borderColor: n > 0 ? "var(--accent)" : "var(--border)",
  background: n > 0 ? "var(--accent-bg)" : "var(--bg-subtle)",
  color: "inherit", cursor: "pointer",
  fontWeight: n > 0 ? 600 : 400,
});

const badge: CSSProperties = {
  position: "absolute", top: -6, right: -6,
  minWidth: 18, height: 18, padding: "0 5px",
  borderRadius: 9, background: "var(--accent)", color: "#111",
  fontSize: 10, fontWeight: 700,
  display: "flex", alignItems: "center", justifyContent: "center",
};

const drawerStyle: CSSProperties = {
  position: "fixed", top: 0, right: 0, bottom: 0,
  width: "min(560px, 92vw)", background: "var(--bg)", color: "var(--text)",
  borderLeftWidth: 1, borderLeftStyle: "solid",
  borderLeftColor: "var(--border-strong)",
  zIndex: 250, padding: 16, overflow: "auto",
  display: "flex", flexDirection: "column", gap: 12,
  boxShadow: "-8px 0 30px rgba(0,0,0,0.6)",
};

const card: CSSProperties = {
  padding: "10px 12px", borderRadius: 8,
  borderWidth: 1, borderStyle: "solid",
  borderColor: "var(--border)",
  background: "var(--bg-subtle)",
  color: "var(--text)",
  display: "flex", flexDirection: "column", gap: 6,
};

const actionBtn = (variant: "approve" | "reject"): CSSProperties => ({
  padding: "4px 12px", fontSize: 11, borderRadius: 4, cursor: "pointer",
  borderWidth: 1, borderStyle: "solid",
  borderColor: variant === "approve" ? "#4caf50" : "#f44336",
  background: variant === "approve" ? "rgba(76,175,80,0.12)" : "rgba(244,67,54,0.10)",
  color: "inherit",
});

const KIND_LABEL: Record<string, string> = {
  persona_update: "👤 人设优化",
  bug_fix: "🐛 修 Bug",
  trend_integration: "🌍 趋势整合",
  code_change: "🔧 代码变更",
};

export function PendingChangesDrawer({ backendUrl }: Props) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<PC[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  // v6-S9 批量勾选
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await fetchWithTimeout(
        `${backendUrl}/api/pending/list?status=pending&limit=50`,
        undefined, TIMEOUT_MS.default,
      );
      if (!res.ok) { setError(`HTTP ${res.status}`); return; }
      const j = await res.json();
      setItems(j.items || []);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [backendUrl]);

  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, [load]);

  const toggleOne = useCallback((id: string) => {
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }, []);

  const toggleGroup = useCallback((ids: string[]) => {
    setSelected((prev) => {
      const n = new Set(prev);
      const allOn = ids.every((id) => n.has(id));
      if (allOn) ids.forEach((id) => n.delete(id));
      else ids.forEach((id) => n.add(id));
      return n;
    });
  }, []);

  const bulkAct = useCallback(async (decision: "approve" | "reject") => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    if (!window.confirm(
      decision === "approve"
        ? `批量应用 ${ids.length} 条? 应用后可能会真改 prompt / 配置.`
        : `批量拒绝 ${ids.length} 条?`,
    )) return;
    setBulkBusy(true); setError("");
    let ok = 0, fail = 0;
    for (const id of ids) {
      try {
        const res = await fetchWithTimeout(
          `${backendUrl}/api/pending/${id}/${decision}`,
          { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
          TIMEOUT_MS.default,
        );
        if (res.ok) ok++; else fail++;
      } catch { fail++; }
    }
    setBulkBusy(false);
    setSelected(new Set());
    await load();
    if (fail > 0) setError(`批量处理: ${ok} 成功 / ${fail} 失败`);
  }, [backendUrl, selected, load]);

  const act = useCallback(async (id: string, decision: "approve" | "reject") => {
    if (decision === "approve" && !window.confirm(
        `确认应用这个改动? 应用后可能会真改 prompt / 配置.`)) return;
    try {
      const res = await fetchWithTimeout(
        `${backendUrl}/api/pending/${id}/${decision}`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
        TIMEOUT_MS.default,
      );
      if (!res.ok) setError(`HTTP ${res.status}`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }, [backendUrl, load]);

  const count = items.length;

  // v6-S9 按 kind 分组
  const grouped = items.reduce<Record<string, PC[]>>((acc, it) => {
    const k = it.kind || "other";
    if (!acc[k]) acc[k] = [];
    acc[k].push(it);
    return acc;
  }, {});

  return (
    <>
      <button type="button" style={btn(count)} onClick={() => setOpen(true)}
              title="待审批的自更新提案">
        ⚖️ 待审
        {count > 0 && <span style={badge}>{count}</span>}
      </button>

      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{
            position: "fixed", inset: 0, background: "var(--overlay)", zIndex: 240,
          }} />
          <div style={drawerStyle} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontWeight: 700, fontSize: 15, color: "var(--text)" }}>⚖️ 待审批改动 · {count} 条</div>
              <div style={{ display: "flex", gap: 6 }}>
                <button type="button" onClick={load}
                        style={{
                          padding: "3px 10px", fontSize: 11, borderRadius: 4,
                          borderWidth: 1, borderStyle: "solid",
                          borderColor: "var(--border)",
                          background: "var(--bg-card)", color: "var(--text)",
                          cursor: "pointer",
                        }}>{loading ? "..." : "↻"}</button>
                <button type="button" title="清空全部待审建议" onClick={async () => {
                          if (!window.confirm("清空所有待审建议? 会标记为已忽略 (不影响已实现/已部署的功能)。")) return;
                          try { await fetchWithTimeout(`${backendUrl}/api/pending/clear`, { method: "POST" }, TIMEOUT_MS.default); } catch { /* ignore */ }
                          await load();
                        }}
                        style={{
                          padding: "3px 10px", fontSize: 11, borderRadius: 4,
                          borderWidth: 1, borderStyle: "solid",
                          borderColor: "var(--border)",
                          background: "var(--bg-card)", color: "var(--text)",
                          cursor: "pointer",
                        }}>🗑 清空</button>
                <button type="button" onClick={() => setOpen(false)}
                        style={{
                          padding: "3px 10px", fontSize: 11, borderRadius: 4,
                          borderWidth: 1, borderStyle: "solid",
                          borderColor: "var(--border)",
                          background: "var(--bg-card)", color: "var(--text)",
                          cursor: "pointer",
                        }}>✕</button>
              </div>
            </div>

            {error && <div style={{ color: "#f44336", fontSize: 12 }}>⚠ {error}</div>}

            {count === 0 && !loading && (
              <div style={{ padding: 24, color: "var(--text-dim)", fontSize: 13 }}>
                暂无待审批提案. evolvers (p12/p15/p17 等) 跑出新建议后会出现在这.
              </div>
            )}

            {/* v6-S9 批量操作条 */}
            {selected.size > 0 && (
              <div style={{
                position: "sticky", top: 0, zIndex: 1,
                padding: "8px 10px", borderRadius: 6,
                background: "var(--accent-bg)",
                borderWidth: 1, borderStyle: "solid", borderColor: "var(--accent-bg)",
                display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6,
              }}>
                <span style={{ fontSize: 12, color: "var(--accent)", fontWeight: 600 }}>
                  已选 {selected.size} 条
                </span>
                <div style={{ display: "flex", gap: 6 }}>
                  <button type="button" disabled={bulkBusy} onClick={() => setSelected(new Set())}
                    style={{ padding: "3px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer",
                      borderWidth: 1, borderStyle: "solid", borderColor: "var(--border-strong)",
                      background: "transparent", color: "var(--text-dim)" }}>清空</button>
                  <button type="button" disabled={bulkBusy} onClick={() => bulkAct("reject")}
                    style={{ ...actionBtn("reject"), opacity: bulkBusy ? 0.5 : 1 }}>
                    {bulkBusy ? "处理中…" : "✗ 批量拒绝"}
                  </button>
                  <button type="button" disabled={bulkBusy} onClick={() => bulkAct("approve")}
                    style={{ ...actionBtn("approve"), opacity: bulkBusy ? 0.5 : 1 }}>
                    {bulkBusy ? "处理中…" : "✓ 批量应用"}
                  </button>
                </div>
              </div>
            )}

            {/* v6-S9 按 kind 分组渲染 */}
            {Object.entries(grouped).map(([kind, group]) => {
              const groupIds = group.map((g) => g.id);
              const allChecked = groupIds.every((id) => selected.has(id));
              const someChecked = !allChecked && groupIds.some((id) => selected.has(id));
              return (
                <div key={kind} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <div style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "4px 8px", borderRadius: 4,
                    background: "var(--bg-subtle)",
                  }}>
                    <input type="checkbox" checked={allChecked}
                      ref={(el) => { if (el) el.indeterminate = someChecked; }}
                      onChange={() => toggleGroup(groupIds)}
                    />
                    <span style={{ fontSize: 12, fontWeight: 600, color: "var(--info)" }}>
                      {KIND_LABEL[kind] || kind}
                    </span>
                    <span style={{ fontSize: 11, color: "var(--text-faint)" }}>· {group.length} 条</span>
                  </div>
                  {group.map((it) => (
              <div key={it.id} style={{ ...card, borderColor: selected.has(it.id) ? "var(--accent)" : "var(--border)" }}>
                <div style={{ display: "flex", alignItems: "start", gap: 8 }}>
                  <input type="checkbox" checked={selected.has(it.id)}
                    onChange={() => toggleOne(it.id)}
                    style={{ marginTop: 3 }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>
                      {KIND_LABEL[it.kind] || it.kind} <span style={{ color: "#9ccc65", fontWeight: 600 }}> · {it.evolver}</span>
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                      {new Date(it.ts * 1000).toLocaleString()} · 目标: <code style={{ color: "var(--info)" }}>{it.target}</code>
                    </div>
                  </div>
                </div>
                <div style={{ fontSize: 12, lineHeight: 1.55, color: "var(--text)" }}>{it.description}</div>
                {it.proposal !== undefined && it.proposal !== null && (
                  <pre style={{
                    margin: 0, padding: 8, borderRadius: 4, fontSize: 10,
                    background: "var(--bg-subtle)", maxHeight: 160, overflow: "auto",
                    whiteSpace: "pre-wrap", wordBreak: "break-all",
                  }}>
                    {typeof it.proposal === "string"
                      ? it.proposal
                      : JSON.stringify(it.proposal, null, 2)}
                  </pre>
                )}
                <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                  <button type="button" style={actionBtn("reject")} onClick={() => act(it.id, "reject")}>
                    ✗ 拒绝
                  </button>
                  <button type="button" style={actionBtn("approve")} onClick={() => act(it.id, "approve")}>
                    ✓ 应用
                  </button>
                </div>
              </div>
                  ))}
                </div>
              );
            })}

            {/* v6-S9 旧的扁平列表保留为 0 元素 ghost (保 diff 最小) */}
            {false && items.map((it) => (
              <div key={it.id} style={card}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 8 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>
                      {KIND_LABEL[it.kind] || it.kind} <span style={{ color: "#9ccc65", fontWeight: 600 }}> · {it.evolver}</span>
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                      {new Date(it.ts * 1000).toLocaleString()} · 目标: <code style={{ color: "var(--info)" }}>{it.target}</code>
                    </div>
                  </div>
                </div>
                <div style={{ fontSize: 12, lineHeight: 1.55, color: "var(--text)" }}>{it.description}</div>
                {it.proposal !== undefined && it.proposal !== null && (
                  <pre style={{
                    margin: 0, padding: 8, borderRadius: 4, fontSize: 10,
                    background: "var(--bg-subtle)", maxHeight: 160, overflow: "auto",
                    whiteSpace: "pre-wrap", wordBreak: "break-all",
                  }}>
                    {typeof it.proposal === "string"
                      ? it.proposal
                      : JSON.stringify(it.proposal, null, 2)}
                  </pre>
                )}
                <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                  <button type="button" style={actionBtn("reject")} onClick={() => act(it.id, "reject")}>
                    ✗ 拒绝
                  </button>
                  <button type="button" style={actionBtn("approve")} onClick={() => act(it.id, "approve")}>
                    ✓ 应用
                  </button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
