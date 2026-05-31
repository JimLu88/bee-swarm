"use client";

/** v6-L 预算环 — 顶部实时显示 ¥X / ¥800 + tier badge. */

import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type Budget = {
  ok: boolean;
  today_yuan?: number;
  month_yuan?: number;
  budget_yuan?: number;
  budget_used_pct?: number;
  tier?: string;
};

const TIER_COLOR: Record<string, string> = {
  ok: "#66bb6a",
  warn: "#ffb300",
  downgrade: "#ff8a3d",
  emergency: "#ff5252",
  unknown: "#888",
};

const wrap: CSSProperties = {
  position: "relative", width: 64, height: 32,
  padding: "0 10px", borderRadius: 6,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
  background: "var(--bg-subtle)",
  display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
  cursor: "default", fontSize: 11,
};

export function BudgetRing({ backendUrl }: { backendUrl: string }) {
  const [data, setData] = useState<Budget | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetchWithTimeout(`${backendUrl}/api/budget`, undefined, TIMEOUT_MS.default);
      if (res.ok) setData(await res.json());
    } catch { /* ignore */ }
  }, [backendUrl]);

  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, [load]);

  const month = Math.round(data?.month_yuan ?? 0);
  const budget = data?.budget_yuan ?? 800;
  const pct = Math.min(100, data?.budget_used_pct ?? 0);
  const tier = data?.tier ?? "unknown";
  const color = TIER_COLOR[tier] || "#888";
  const tooltip = data?.ok
    ? `今天: ¥${(data.today_yuan ?? 0).toFixed(2)} · 本月: ¥${month}/¥${budget} · ${pct.toFixed(0)}%`
    : "bee-ledger 不可达";

  return (
    <div style={{ ...wrap, borderColor: color }} title={tooltip}>
      <div style={{
        fontSize: 11, fontWeight: 700, color,
        fontVariantNumeric: "tabular-nums", lineHeight: 1,
      }}>
        ¥{month}/{budget}
      </div>
      <div style={{
        marginTop: 3, width: "100%", height: 3, borderRadius: 1.5,
        background: "var(--bg-hover)", overflow: "hidden",
      }}>
        <div style={{
          width: `${pct}%`, height: "100%", background: color,
          transition: "width 0.4s ease",
        }} />
      </div>
    </div>
  );
}
