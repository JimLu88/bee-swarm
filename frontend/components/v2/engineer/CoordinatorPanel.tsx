"use client";

import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../../lib/http";
import { resolveBackendHttpBase } from "../../../lib/backend";

type Evolver = { id: string; label: string; layer: string; last_run: number | null };
type SchedulerStatus = { running: boolean; jobs: { id: string; next_run: string }[] };

const card: CSSProperties = {
  padding: 14, borderRadius: 10,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
  background: "var(--bg-subtle)",
  display: "flex", flexDirection: "column", gap: 10,
};

const row: CSSProperties = {
  display: "flex", justifyContent: "space-between", alignItems: "center",
  padding: "6px 10px", borderRadius: 6,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--bg-hover)",
  background: "var(--bg-subtle)",
};

const btn = (variant: "default" | "primary"): CSSProperties => ({
  padding: "3px 10px", fontSize: 11, borderRadius: 4,
  borderWidth: 1, borderStyle: "solid",
  borderColor: variant === "primary" ? "var(--accent)" : "var(--border)",
  background: variant === "primary" ? "var(--accent-bg)" : "var(--bg-subtle)",
  color: "inherit", cursor: "pointer",
});

const HIGHLIGHT_EVOLVERS: Record<string, { emoji: string; cost_hint: string }> = {
  p16_knowledge_curator: { emoji: "📚", cost_hint: "DeepSeek ~¥0.5-1, 4 persona × books+pitfalls+standards" },
  p13_model_discovery: { emoji: "🔭", cost_hint: "免费 (爬 LiteLLM 价表)" },
  p14_skill_discovery: { emoji: "🧩", cost_hint: "免费 (GitHub Search)" },
  p15_team_evolve: { emoji: "👑", cost_hint: "需要 14 天 ELO 数据, 否则空跑" },
  p12_code_self_update: { emoji: "🤖", cost_hint: "~¥3-5 Opus, 全过 git verify+shadow+kpi 才合" },
  p5_elo_update: { emoji: "🏆", cost_hint: "免费 (本地计算 ELO)" },
};

export function CoordinatorPanel() {
  const [evolvers, setEvolvers] = useState<Evolver[]>([]);
  const [sched, setSched] = useState<SchedulerStatus | null>(null);
  const [intervalDays, setIntervalDays] = useState<number>(3);
  const [running, setRunning] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<{ id: string; ok: boolean; msg: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const backendUrl = resolveBackendHttpBase();

  const reload = useCallback(async () => {
    setError(null);
    try {
      const [statusRes, schRes, cfgRes] = await Promise.all([
        fetchWithTimeout(`${backendUrl}/coordinator/status`, undefined, TIMEOUT_MS.default),
        fetchWithTimeout(`${backendUrl}/coordinator/scheduler-status`, undefined, TIMEOUT_MS.default),
        fetchWithTimeout(`${backendUrl}/coordinator/schedule-config`, undefined, TIMEOUT_MS.default),
      ]);
      if (statusRes.ok) setEvolvers((await statusRes.json()).evolvers || []);
      if (schRes.ok) setSched(await schRes.json());
      if (cfgRes.ok) setIntervalDays((await cfgRes.json()).interval_days ?? 3);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [backendUrl]);

  useEffect(() => { reload(); }, [reload]);

  const trigger = useCallback(async (id: string) => {
    if (!window.confirm(`手动触发 ${id}? ${HIGHLIGHT_EVOLVERS[id]?.cost_hint || ""}`)) return;
    setRunning(id);
    setLastResult(null);
    try {
      const res = await fetchWithTimeout(`${backendUrl}/coordinator/trigger?evolver=${id}`,
        { method: "POST" }, TIMEOUT_MS.decisionStart);
      const j = await res.json();
      setLastResult({
        id, ok: res.ok,
        msg: j.result?.status || (res.ok ? "完成" : `失败 ${res.status}`),
      });
    } catch (e) {
      setLastResult({ id, ok: false, msg: (e as Error).message });
    } finally {
      setRunning(null);
    }
  }, [backendUrl]);

  const changeInterval = useCallback(async (n: number) => {
    setIntervalDays(n);
    setError(null);
    try {
      const res = await fetchWithTimeout(`${backendUrl}/coordinator/schedule-config`,
        { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ interval_days: n }) }, TIMEOUT_MS.default);
      if (res.ok) {
        const j = await res.json();
        if (j.next_run) {
          setSched((s) => ({ running: s?.running ?? true,
            jobs: [{ id: "ev_all_02", next_run: j.next_run }] }));
        }
      } else {
        setError(`保存频率失败 ${res.status}`);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }, [backendUrl]);

  return (
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>🔄 演化协调器 (P0-P16)</div>
        <div style={{ fontSize: 11, opacity: 0.65 }}>
          {sched?.running ? "✅ Cron 运行中" : "⏸ Cron 未启动"}
          {sched?.jobs?.[0] && ` · 下次 ${sched.jobs[0].next_run.slice(0, 16)}`}
        </div>
      </div>

      <div style={row}>
        <div style={{ fontSize: 12 }}>⏱ 自动跑频率 <span style={{ opacity: 0.55, fontSize: 10 }}>(改了即时生效)</span></div>
        <select value={intervalDays} onChange={(e) => changeInterval(Number(e.target.value))}
                style={{ fontSize: 12, padding: "3px 8px", borderRadius: 4, cursor: "pointer",
                         borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
                         background: "var(--bg-subtle)", color: "inherit" }}>
          <option value={1}>每天</option>
          <option value={3}>每 3 天</option>
          <option value={7}>每周</option>
        </select>
      </div>

      {error && <div style={{ fontSize: 12, color: "#f44336" }}>⚠ {error}</div>}
      {lastResult && (
        <div style={{
          padding: 8, borderRadius: 6, fontSize: 12,
          background: lastResult.ok ? "rgba(76,175,80,0.10)" : "rgba(244,67,54,0.10)",
          borderWidth: 1, borderStyle: "solid",
          borderColor: lastResult.ok ? "#4caf50" : "#f44336",
        }}>
          [{lastResult.id}] {lastResult.msg}
        </div>
      )}

      {evolvers.map((e) => {
        const h = HIGHLIGHT_EVOLVERS[e.id];
        return (
          <div key={e.id} style={row}>
            <div>
              <div style={{ fontSize: 12, fontWeight: 500 }}>
                {h?.emoji || "·"} {e.id} <span style={{ opacity: 0.55 }}>· {e.label}</span>
                <span style={{ opacity: 0.45, marginLeft: 6, fontSize: 10 }}>{e.layer}</span>
              </div>
              {h && <div style={{ fontSize: 10, opacity: 0.55 }}>{h.cost_hint}</div>}
            </div>
            <button type="button" disabled={running === e.id}
                    onClick={() => trigger(e.id)}
                    style={btn(e.id === "p16_knowledge_curator" ? "primary" : "default")}>
              {running === e.id ? "..." : "▶ 触发"}
            </button>
          </div>
        );
      })}

      <div style={{ fontSize: 11, opacity: 0.55, marginTop: 4 }}>
        💡 Cron 每 {intervalDays} 天 02:00 串行跑 P0-P16。上方改频率即时生效、无需重启。手动触发不影响 cron。
      </div>
    </div>
  );
}
