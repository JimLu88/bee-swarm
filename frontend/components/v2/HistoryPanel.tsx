"use client";

import { useEffect, useState, type CSSProperties, type MouseEvent } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

export type HistoryRow = {
  decision_id?: string;
  task?: string;
  task_truncated?: boolean;
  ceo_decision?: string;
  created_at?: string;
  mode_id?: string;
};

const card: CSSProperties = {
  padding: 12, borderRadius: 10,
  border: "1px solid var(--border)",
  background: "var(--bg-subtle)",
};

const rowStyle: CSSProperties = {
  padding: "8px 10px", borderRadius: 6,
  background: "var(--bg-subtle)",
  fontSize: 12, display: "flex", gap: 8, alignItems: "center",
};

const starBtn = (active: boolean): CSSProperties => ({
  padding: "2px 6px", borderRadius: 4, fontSize: 14, cursor: "pointer",
  borderWidth: 1, borderStyle: "solid",
  borderColor: active ? "var(--accent)" : "var(--border)",
  background: active ? "var(--accent-bg)" : "var(--bg-subtle)",
  color: active ? "var(--accent)" : "#888",
  lineHeight: 1,
});

export function HistoryPanel({
  rows, onPick, backendUrl,
}: {
  rows: HistoryRow[];
  onPick: (decision_id: string) => void;
  backendUrl?: string;
}) {
  const [starred, setStarred] = useState<Set<string>>(new Set());
  // v6-S/D 搜索 + ⭐only 筛选
  const [q, setQ] = useState("");
  const [starOnly, setStarOnly] = useState(false);

  useEffect(() => {
    if (!backendUrl) return;
    (async () => {
      try {
        const r = await fetchWithTimeout(`${backendUrl}/api/favorites/list`, undefined, TIMEOUT_MS.default);
        if (!r.ok) return;
        const j = await r.json();
        setStarred(new Set((j.items || []).map((it: { decision_id: string }) => it.decision_id)));
      } catch { /* ignore */ }
    })();
  }, [backendUrl]);

  const toggleStar = async (e: MouseEvent, r: HistoryRow) => {
    e.stopPropagation();
    if (!r.decision_id || !backendUrl) return;
    const isStarred = starred.has(r.decision_id);
    try {
      if (isStarred) {
        await fetchWithTimeout(`${backendUrl}/api/favorites/${r.decision_id}`,
          { method: "DELETE" }, TIMEOUT_MS.default);
        setStarred((s) => {
          const next = new Set(s); next.delete(r.decision_id!); return next;
        });
      } else {
        await fetchWithTimeout(`${backendUrl}/api/favorites/star`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision_id: r.decision_id, mode_id: r.mode_id ?? "" }),
        }, TIMEOUT_MS.default);
        setStarred((s) => new Set(s).add(r.decision_id!));
      }
    } catch { /* ignore */ }
  };

  if (!rows || rows.length === 0) {
    return <div style={{ ...card, color: "var(--text-dim)", textAlign: "center" }}>(还没问过 AI, 上面输入第一个任务试试)</div>;
  }

  // v6-S/D 过滤
  const kw = q.trim().toLowerCase();
  const filtered = rows.filter((r) => {
    if (starOnly && !(r.decision_id && starred.has(r.decision_id))) return false;
    if (kw) {
      const hay = `${r.task ?? ""} ${r.ceo_decision ?? ""} ${r.mode_id ?? ""}`.toLowerCase();
      if (!hay.includes(kw)) return false;
    }
    return true;
  });

  return (
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, gap: 8, flexWrap: "wrap" }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>
          📜 之前问过的 <span style={{ fontSize: 10, color: "var(--text-dim)", marginLeft: 6 }}>
            ({filtered.length}/{rows.length} · 默认留最近 100; 点 ⭐ 永久保留)
          </span>
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input
            type="text" placeholder="搜索任务/决策..." value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{
              padding: "4px 8px", fontSize: 12, borderRadius: 4, width: 180,
              borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
              background: "var(--bg-subtle)", color: "var(--text)", outline: "none",
            }}
          />
          <button type="button" onClick={() => setStarOnly((v) => !v)}
            title="只看收藏"
            style={{
              padding: "4px 10px", fontSize: 12, borderRadius: 4, cursor: "pointer",
              borderWidth: 1, borderStyle: "solid",
              borderColor: starOnly ? "var(--accent)" : "var(--border)",
              background: starOnly ? "var(--accent-bg)" : "var(--bg-subtle)",
              color: starOnly ? "var(--accent)" : "#bbb",
              fontWeight: starOnly ? 700 : 400,
            }}>
            {starOnly ? "★ 已开" : "☆ 只看收藏"}
          </button>
        </div>
      </div>
      {filtered.length === 0 && (
        <div style={{ padding: 16, fontSize: 12, color: "var(--text-faint)", textAlign: "center" }}>
          {kw || starOnly ? "无匹配, 试着清空筛选" : "暂无历史"}
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 360, overflowY: "auto" }}>
        {filtered.map((r, i) => {
          const isStarred = !!(r.decision_id && starred.has(r.decision_id));
          return (
            <div
              key={`${r.decision_id ?? "noid"}-${i}`}
              style={rowStyle}
              role="button"
            >
              {backendUrl && (
                <button
                  type="button"
                  style={starBtn(isStarred)}
                  onClick={(e) => toggleStar(e, r)}
                  title={isStarred ? "取消收藏" : "收藏 (永久保留)"}
                >
                  {isStarred ? "★" : "☆"}
                </button>
              )}
              <div
                style={{ flex: 1, cursor: "pointer" }}
                onClick={() => r.decision_id && onPick(r.decision_id)}
              >
                <div style={{ color: "var(--text-dim)", fontSize: 10 }}>{r.created_at}</div>
                <div style={{ marginTop: 2, color: "var(--text)" }}>{r.task ?? "(无标题任务)"}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
