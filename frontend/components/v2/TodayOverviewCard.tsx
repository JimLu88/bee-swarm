"use client";

/** v6-S1 首屏"今天概览"卡片 — 打开应用第一眼: 到期复习 / 待审批 / 上次决策. */

import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type Props = {
  backendUrl: string;
  /** 当用户点击复习数字, 父级可选: 打开 SettingsDrawer 的 memory tab */
  onClickReview?: () => void;
};

type Overview = {
  reviewDue: number | null;
  pendingCount: number | null;
  lastDecisionAgoMin: number | null;
  lastDecisionMode: string | null;
};

const wrap: CSSProperties = {
  padding: "10px 14px", borderRadius: 10,
  background: "linear-gradient(135deg, var(--accent-bg), var(--info-bg))",
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--accent-bg)",
  display: "flex", alignItems: "center", justifyContent: "space-between",
  gap: 16, flexWrap: "wrap",
};

const item: CSSProperties = {
  display: "flex", alignItems: "baseline", gap: 6,
};

const num = (color: string): CSSProperties => ({
  fontSize: 20, fontWeight: 700, color,
});

const label: CSSProperties = { fontSize: 11, color: "var(--text-dim)" };

function ago(min: number | null): string {
  if (min == null) return "无";
  if (min < 1) return "刚刚";
  if (min < 60) return `${Math.round(min)} 分钟前`;
  if (min < 60 * 24) return `${Math.round(min / 60)} 小时前`;
  return `${Math.round(min / 60 / 24)} 天前`;
}

export function TodayOverviewCard({ backendUrl, onClickReview }: Props) {
  const [data, setData] = useState<Overview>({
    reviewDue: null, pendingCount: null,
    lastDecisionAgoMin: null, lastDecisionMode: null,
  });

  const load = useCallback(async () => {
    const [reviewRes, pendingRes, hxRes] = await Promise.allSettled([
      fetchWithTimeout(`${backendUrl}/api/memory/review/stats`,
        { headers: { Authorization: "Bearer dev-token-change-me" } }, TIMEOUT_MS.default),
      fetchWithTimeout(`${backendUrl}/api/pending/list?status=pending&limit=1`,
        undefined, TIMEOUT_MS.default),
      fetchWithTimeout(`${backendUrl}/api/memory/recent?limit=1`,
        undefined, TIMEOUT_MS.default),
    ]);

    let reviewDue: number | null = null;
    if (reviewRes.status === "fulfilled" && reviewRes.value.ok) {
      try { const j = await reviewRes.value.json(); reviewDue = j.due_now ?? 0; } catch { /* ignore */ }
    }

    let pendingCount: number | null = null;
    if (pendingRes.status === "fulfilled" && pendingRes.value.ok) {
      try {
        const j = await pendingRes.value.json();
        pendingCount = j.total ?? (Array.isArray(j.items) ? j.items.length : 0);
      } catch { /* ignore */ }
    }

    let lastDecisionAgoMin: number | null = null;
    let lastDecisionMode: string | null = null;
    if (hxRes.status === "fulfilled" && hxRes.value.ok) {
      try {
        const j = await hxRes.value.json();
        const row = Array.isArray(j?.items) ? j.items[0] : (Array.isArray(j) ? j[0] : null);
        if (row?.ts) {
          const tsMs = typeof row.ts === "number" ? row.ts * (row.ts < 1e12 ? 1000 : 1) : Date.parse(row.ts);
          lastDecisionAgoMin = (Date.now() - tsMs) / 1000 / 60;
        } else if (row?.created_at) {
          lastDecisionAgoMin = (Date.now() - Date.parse(row.created_at)) / 1000 / 60;
        }
        lastDecisionMode = row?.mode_label ?? row?.mode_id ?? null;
      } catch { /* ignore */ }
    }

    setData({ reviewDue, pendingCount, lastDecisionAgoMin, lastDecisionMode });
  }, [backendUrl]);

  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, [load]);

  const review = data.reviewDue;
  const pending = data.pendingCount;

  return (
    <div style={wrap}>
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
        <div style={item} onClick={onClickReview}
             title="点击打开复习面板"
             role={onClickReview ? "button" : undefined}
        >
          <span style={num(review && review > 0 ? "var(--accent)" : "#7f8c8d")}>
            {review == null ? "—" : review}
          </span>
          <span style={label}>到期复习</span>
        </div>
        <div style={item}>
          <span style={num(pending && pending > 0 ? "#ffb300" : "#7f8c8d")}>
            {pending == null ? "—" : pending}
          </span>
          <span style={label}>待审批</span>
        </div>
        <div style={item}>
          <span style={{ fontSize: 13, color: "var(--text-dim)" }}>
            {ago(data.lastDecisionAgoMin)}{data.lastDecisionMode ? ` · ${data.lastDecisionMode}` : ""}
          </span>
          <span style={label}>上次决策</span>
        </div>
      </div>
      <div style={{ fontSize: 11, color: "var(--text-faint)" }}>
        提示: <kbd style={{
          padding: "1px 5px", fontSize: 10, borderRadius: 3,
          background: "var(--bg-hover)",
          borderWidth: 1, borderStyle: "solid", borderColor: "var(--border-strong)",
        }}>Ctrl/⌘ K</kbd> 全局搜索
      </div>
    </div>
  );
}
