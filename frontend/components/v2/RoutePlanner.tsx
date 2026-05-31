"use client";

import { useCallback, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

export type RouteId = "all" | "multi" | "key" | "single" | "ceo_only";
export type RoundsBand = "heavy" | "medium" | "light";

type ArmView = { mean: number; n: number; sampled: number };

type PreflightResp = {
  mode_id: string;
  mode_label: string;
  all_depts: string[];
  all_labels: Record<string, string>;
  multi_depts: string[];
  key_depts: string[];
  single_dept: string;
  reasoning: string;
  ceo_recommended_route: RouteId;
  ceo_recommended_rounds_band: RoundsBand;
  sop: { recommended_route: RouteId; recommended_rounds_band: RoundsBand; recommended_rounds: number; explored: boolean; arms: Record<string, ArmView> };
  sop_has_history: boolean;
  difficulty: "light" | "medium" | "heavy";
  recommended_route: RouteId;
  recommended_rounds_band: RoundsBand;
  llm_error?: string;
};

export type RunParams = {
  route: RouteId;
  departments: string[];
  rounds: number;
  rounds_band: RoundsBand;
  difficulty: string;
};

type Props = {
  backendUrl: string;
  task: string;
  modeId: string;
  images: string[];
  docFiles: { name: string; content_b64: string }[];
  busy: boolean;
  onRun: (p: RunParams) => void;
};

const ROUTES: { id: RouteId; icon: string; label: string; desc: string }[] = [
  { id: "all", icon: "🏛", label: "全部门", desc: "所有专科都上，最全面但最慢最贵" },
  { id: "multi", icon: "🐝", label: "CEO选多部门", desc: "CEO 挑相关的几个并行" },
  { id: "key", icon: "🎯", label: "重点部门", desc: "只上最关键的 2-3 个" },
  { id: "single", icon: "📍", label: "单部门", desc: "1 个最相关的深入回答" },
  { id: "ceo_only", icon: "⚡", label: "CEO 单独回答", desc: "不开部门，CEO 直接答，最快最省" },
];

const BANDS: { id: RoundsBand; icon: string; label: string; desc: string }[] = [
  { id: "heavy", icon: "🔥", label: "重度 3-5 轮", desc: "部门多轮深度辩论，最严谨" },
  { id: "medium", icon: "💬", label: "1-3 轮", desc: "适度讨论，性价比好" },
  { id: "light", icon: "⚡", label: "1 轮轻度", desc: "各说一次，CEO 综合，最快" },
];
const BAND_ROUNDS: Record<RoundsBand, number> = { heavy: 4, medium: 2, light: 1 };

const wrap: CSSProperties = {
  marginTop: 8, padding: 14, borderRadius: 12,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--info-bg)",
  background: "var(--info-bg)", display: "flex", flexDirection: "column", gap: 12,
};
const grid: CSSProperties = { display: "flex", flexWrap: "wrap", gap: 8 };
const card = (active: boolean, recommended: boolean): CSSProperties => ({
  flex: "1 1 150px", minWidth: 140, padding: "9px 11px", borderRadius: 9, cursor: "pointer",
  borderWidth: active ? 2 : 1, borderStyle: "solid",
  borderColor: active ? "var(--accent)" : recommended ? "var(--accent-bg)" : "var(--border)",
  background: active ? "var(--accent-bg)" : "var(--bg-subtle)",
  display: "flex", flexDirection: "column", gap: 3, position: "relative",
});
const btn = (primary: boolean): CSSProperties => ({
  padding: "9px 16px", fontSize: 13, fontWeight: 600, borderRadius: 8, cursor: "pointer",
  borderWidth: 1, borderStyle: "solid",
  borderColor: primary ? "var(--accent)" : "var(--border-strong)",
  background: primary ? "var(--accent)" : "var(--bg-subtle)",
  color: primary ? "#000" : "inherit",
});

function deptsForRoute(p: PreflightResp, route: RouteId): string[] {
  if (route === "all") return p.all_depts;
  if (route === "multi") return p.multi_depts;
  if (route === "key") return p.key_depts;
  if (route === "single") return p.single_dept ? [p.single_dept] : [];
  return []; // ceo_only
}

export function RoutePlanner({ backendUrl, task, modeId, images, docFiles, busy, onRun }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pf, setPf] = useState<PreflightResp | null>(null);
  const [route, setRoute] = useState<RouteId>("multi");
  const [band, setBand] = useState<RoundsBand>("medium");

  const analyze = useCallback(async () => {
    if (!task.trim()) { setError("先在上面写一句话告诉我你要什么"); return; }
    setLoading(true); setError(null);
    try {
      const res = await fetchWithTimeout(
        `${backendUrl}/api/decision/preflight`,
        { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ task, mode_id: modeId, images, files: docFiles }) },
        TIMEOUT_MS.decisionStart,
      );
      if (!res.ok) throw new Error(`preflight ${res.status}`);
      const j = (await res.json()) as PreflightResp;
      setPf(j);
      setRoute(j.recommended_route);
      setBand(j.recommended_rounds_band);
    } catch (e) {
      setError(`CEO 预分析失败: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, [backendUrl, task, modeId, images, docFiles]);

  if (!pf) {
    return (
      <div style={{ marginTop: 8 }}>
        <button type="button" style={btn(false)} disabled={loading || busy || !task.trim()} onClick={analyze}>
          {loading ? "🤔 CEO 正在分析任务..." : "🎯 让 CEO 先分析 (推荐部门 + 路线 + 轮数)"}
        </button>
        {error && <span style={{ marginLeft: 10, color: "#f87171", fontSize: 12 }}>⚠ {error}</span>}
      </div>
    );
  }

  const selectedDepts = deptsForRoute(pf, route);
  const labelOf = (d: string) => pf.all_labels[d] || d;
  const armKey = (r: RouteId) => `${r}|${band}`;
  const winRate = (r: RouteId): number | null => {
    const a = pf.sop?.arms?.[armKey(r)];
    return a && a.n > 0 ? a.mean : null;
  };

  return (
    <div style={wrap}>
      <div style={{ fontSize: 13 }}>
        <b style={{ color: "var(--info)" }}>🎬 CEO 预分析</b>
        <span style={{ opacity: 0.55, marginLeft: 8, fontSize: 11 }}>
          难度: {pf.difficulty} · {pf.sop_has_history ? "已结合历史偏好" : "暂无历史, 按当前判断"}
          {pf.sop?.explored && " · 🎲 本次随机探索(防僵化)"}
        </span>
        <div style={{ marginTop: 5, opacity: 0.85, lineHeight: 1.6 }}>{pf.reasoning}</div>
      </div>

      <div>
        <div style={{ fontSize: 12, opacity: 0.6, marginBottom: 6 }}>① 选路线 (推荐已高亮 ⭐):</div>
        <div style={grid}>
          {ROUTES.map((r) => {
            const active = route === r.id;
            const rec = pf.recommended_route === r.id;
            const wr = winRate(r.id);
            const cnt = deptsForRoute(pf, r.id).length;
            return (
              <div key={r.id} style={card(active, rec)} onClick={() => setRoute(r.id)}>
                {rec && <span style={{ position: "absolute", top: 4, right: 6, fontSize: 11 }}>⭐</span>}
                <div style={{ fontSize: 13, fontWeight: 600 }}>{r.icon} {r.label}</div>
                <div style={{ fontSize: 10.5, opacity: 0.6, lineHeight: 1.4 }}>{r.desc}</div>
                <div style={{ fontSize: 10.5, opacity: 0.8, marginTop: 2 }}>
                  {r.id === "ceo_only" ? "0 部门" : `${cnt} 个部门`}
                  {wr != null && <span style={{ color: "#86efac", marginLeft: 6 }}>历史好评 {Math.round(wr * 100)}%</span>}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <div style={{ fontSize: 12, opacity: 0.6, marginBottom: 6 }}>② 选讨论轮数:</div>
        <div style={grid}>
          {BANDS.map((b) => {
            const active = band === b.id;
            const rec = pf.recommended_rounds_band === b.id;
            const disabled = route === "ceo_only"; // CEO单答无所谓轮数
            return (
              <div key={b.id}
                style={{ ...card(active && !disabled, rec), opacity: disabled ? 0.4 : 1, cursor: disabled ? "not-allowed" : "pointer" }}
                onClick={() => { if (!disabled) setBand(b.id); }}>
                {rec && !disabled && <span style={{ position: "absolute", top: 4, right: 6, fontSize: 11 }}>⭐</span>}
                <div style={{ fontSize: 13, fontWeight: 600 }}>{b.icon} {b.label}</div>
                <div style={{ fontSize: 10.5, opacity: 0.6, lineHeight: 1.4 }}>{b.desc}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 选中部门预览 */}
      {route !== "ceo_only" && (
        <div style={{ fontSize: 11, opacity: 0.7, lineHeight: 1.7 }}>
          <b>将启动 {selectedDepts.length} 个部门:</b>{" "}
          {selectedDepts.map((d) => labelOf(d).split(" ")[0]).join("、") || "(无)"}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <button type="button" style={btn(true)} disabled={busy}
          onClick={() => onRun({
            route,
            departments: selectedDepts,
            rounds: route === "ceo_only" ? 0 : BAND_ROUNDS[band],
            rounds_band: band,
            difficulty: pf.difficulty,
          })}>
          ▶ 生成执行命令 · 开跑
        </button>
        <span style={{ fontSize: 11, opacity: 0.6 }}>
          = {ROUTES.find((r) => r.id === route)?.label}
          {route !== "ceo_only" && ` × ${BANDS.find((b) => b.id === band)?.label}`}
        </span>
        <button type="button" style={{ ...btn(false), padding: "6px 10px", fontSize: 11 }} disabled={busy || loading}
          onClick={analyze}>🔄 重新分析</button>
      </div>
    </div>
  );
}
