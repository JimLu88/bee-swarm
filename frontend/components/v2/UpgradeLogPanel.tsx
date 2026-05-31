"use client";

import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type LogItem = {
  id: string;
  ts: number;
  branch: string;
  status: string;
  diff_summary: string;
  gates_passed: string;
};

type Props = { backendUrl: string };

const wrap: CSSProperties = {
  padding: 14, borderRadius: 12,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
  background: "var(--bg-subtle)",
  display: "flex", flexDirection: "column", gap: 10,
};

const item: CSSProperties = {
  padding: "8px 10px", borderRadius: 6,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--bg-hover)",
  background: "var(--bg-subtle)",
  display: "flex", flexDirection: "column", gap: 4,
};

const statusBadge = (s: string): CSSProperties => {
  const color = s.startsWith("merged") ? "#4caf50" : (s === "rejected" || s === "rolled_back") ? "#f44336" : "var(--accent)";
  return {
    display: "inline-block", padding: "1px 6px", borderRadius: 4,
    fontSize: 10, fontWeight: 600,
    borderWidth: 1, borderStyle: "solid", borderColor: color,
    color, marginRight: 6,
  };
};

export function UpgradeLogPanel({ backendUrl }: Props) {
  const [items, setItems] = useState<LogItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    setError(null);
    try {
      const res = await fetchWithTimeout(`${backendUrl}/coordinator/upgrades?days=14&limit=50`,
        undefined, TIMEOUT_MS.default);
      if (res.ok) setItems((await res.json()).items || []);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [backendUrl]);

  useEffect(() => { reload(); }, [reload]);

  const rollback = useCallback(async (run_id: string) => {
    if (!window.confirm(`回滚 ${run_id}? (走 git revert + 重启服务)`)) return;
    setBusy(true);
    try {
      await fetchWithTimeout(`${backendUrl}/coordinator/upgrades/${run_id}/rollback`,
        { method: "POST" }, TIMEOUT_MS.decisionStart);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [backendUrl, reload]);

  return (
    <div style={wrap}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>📈 v5-F 升级日志 + 一键回滚</div>
        <button type="button" onClick={reload}
                style={{
                  padding: "3px 10px", fontSize: 11, borderRadius: 6,
                  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
                  background: "var(--bg-subtle)", color: "inherit", cursor: "pointer",
                }}>🔃</button>
      </div>

      {error && <div style={{ fontSize: 12, color: "#f44336" }}>⚠ {error}</div>}
      {items.length === 0 && (
        <div style={{ fontSize: 12, opacity: 0.55 }}>暂无升级记录 (p12 代码自更新还没跑过)</div>
      )}

      {items.map((it) => (
        <div key={it.id} style={item}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={statusBadge(it.status)}>{it.status}</span>
            <span style={{ fontSize: 11, opacity: 0.55 }}>
              {new Date(it.ts * 1000).toLocaleString()}
            </span>
            <span style={{ fontSize: 11, opacity: 0.45 }}>{it.branch}</span>
            <div style={{ marginLeft: "auto" }}>
              {it.status.startsWith("merged") && (
                <button type="button" disabled={busy}
                        onClick={() => rollback(it.id)}
                        style={{
                          padding: "2px 8px", fontSize: 10, borderRadius: 4,
                          borderWidth: 1, borderStyle: "solid", borderColor: "rgba(244,67,54,0.4)",
                          background: "rgba(244,67,54,0.08)", color: "inherit", cursor: "pointer",
                        }}>↶ 回滚</button>
              )}
            </div>
          </div>
          <div style={{ fontSize: 12, opacity: 0.75 }}>
            {it.diff_summary?.split("\n")[0] || "(无摘要)"}
          </div>
          {it.gates_passed && (
            <div style={{ fontSize: 10, opacity: 0.55 }}>过关: {it.gates_passed}</div>
          )}
        </div>
      ))}
    </div>
  );
}
