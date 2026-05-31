"use client";

import { Icon } from "./Icon";
import { avBg, initial } from "../../lib/scenes";

export type DeptHeat = {
  dept: string;
  label?: string;
  heat: number; // 0-1
  callCount?: number;
  model?: string;
  status?: "idle" | "running" | "done";
  opinion?: string;
  /** v8 协作条: 该顾问的自信度 (dept_done 事件携带), 用于进度条充能 */
  confidence?: number;
};

/** 中文标签取「括号前」短名 */
function shortLabel(name: string): string {
  const cut = name.split(/[\s(（]/)[0];
  return cut || name;
}

const STEP_DEFS = [
  { icon: "psychology", text: "分诊官读题，判断需要哪些顾问" },
  { icon: "groups", text: "顾问们并行讨论，互相质疑收敛" },
  { icon: "gpp_maybe", text: "红队挑刺，标注风险" },
  { icon: "auto_awesome", text: "分诊官综合各方，给出最终建议" },
];

export function SwarmDashboardModal({
  open,
  onClose,
  heats,
  progressPct,
  etaSec,
  labels = {},
}: {
  open: boolean;
  onClose: () => void;
  heats: DeptHeat[];
  progressPct?: number;
  etaSec?: number;
  flowText?: string;
  /** 部门 id → 中文名 */
  labels?: Record<string, string>;
}) {
  if (!open) return null;

  const nameOf = (h: DeptHeat) => shortLabel(h.label ?? labels[h.dept] ?? h.dept);
  const pct = progressPct ?? 0;
  const allDone = heats.length > 0 && heats.every((h) => h.status === "done");
  const stepState = [
    heats.length > 0, // 1 分诊完成
    allDone,          // 2 讨论完成
    pct >= 90,        // 3 红队完成
    pct >= 100,       // 4 综合完成
  ];
  const opinions = heats.filter((h) => h.opinion);

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "var(--overlay)", display: "flex",
        alignItems: "center", justifyContent: "center", zIndex: 100, padding: 24 }}
      onClick={onClose}
    >
      <div
        className="app-scroll"
        style={{ background: "var(--bg-surface)", borderRadius: "var(--radius-xl)", padding: 22,
          width: "min(680px, 96vw)", maxHeight: "90vh", overflowY: "auto",
          border: "1px solid var(--border-1)", boxShadow: "var(--shadow-lg)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
          <div className="spark" style={{ width: 36, height: 36 }}>
            <Icon name="hub" fill />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ font: "600 17px var(--font-sans)", color: "var(--fg-1)" }}>顾问团协作实况</div>
            <div style={{ font: "400 12px var(--font-sans)", color: "var(--fg-3)", marginTop: 2 }}>
              {heats.length === 0 ? "等待任务开始…" : allDone ? "已完成协作" : `${heats.length} 位顾问参与中`}
            </div>
          </div>
          <button type="button" className="ghost-btn" onClick={onClose} aria-label="关闭">
            <Icon name="close" />
          </button>
        </div>

        {/* 步骤时间线 */}
        <div className="steps" style={{ marginBottom: 18 }}>
          {STEP_DEFS.map((s, i) => (
            <div key={i} className={`step${stepState[i] ? " done" : ""}`}>
              <span className="pip"><Icon name={stepState[i] ? "check" : s.icon} /></span>
              {s.text}
            </div>
          ))}
        </div>

        {/* 顾问思考卡网格 */}
        {heats.length === 0 ? (
          <div style={{ font: "400 13px var(--font-sans)", color: "var(--fg-4)", padding: "20px 0", textAlign: "center", lineHeight: 1.7 }}>
            还没有开始任务 —— 在主界面写下问题并发送，这里会实时显示各位顾问的工作状态。
          </div>
        ) : (
          <div className="advisors" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(160px,1fr))" }}>
            {heats.map((h, i) => {
              const isDone = h.status === "done";
              const isThinking = h.status === "running";
              const cls = isThinking ? "thinking" : !isDone && h.status === "idle" ? "idle" : "";
              const conf = h.confidence != null ? h.confidence : isDone ? h.heat : 0;
              const cpct = Math.round(Math.max(0, Math.min(1, conf)) * 100);
              const name = nameOf(h);
              return (
                <div key={h.dept + i} className={`adv ${cls}`} style={{ alignItems: "stretch", flexDirection: "column", gap: 8, padding: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 9, width: "100%", minWidth: 0 }}>
                    <span className="adv-av" style={{ background: avBg(i) }}>{initial(name)}</span>
                    <span className="adv-name" title={name} style={{ flex: 1 }}>{name}</span>
                    <span className="adv-state">{isDone ? cpct + "%" : isThinking ? "思考中" : "待命"}</span>
                  </div>
                  <span className="adv-bar" style={{ width: "100%" }}>
                    <i style={{ width: isDone ? cpct + "%" : isThinking ? "40%" : 0, opacity: isThinking ? 0.5 : 1 }} />
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {/* 顾问实时想法 */}
        {opinions.length > 0 && (
          <div style={{ marginTop: 18 }}>
            <div style={{ font: "600 13px var(--font-sans)", color: "var(--fg-2)", marginBottom: 8 }}>顾问们的实时想法</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {opinions.map((h, i) => (
                <div key={h.dept + i} className="dept" style={{ padding: "10px 13px" }}>
                  <div style={{ font: "600 12.5px var(--font-sans)", color: "var(--fg-1)", marginBottom: 4 }}>{nameOf(h)}</div>
                  <div style={{ font: "400 12.5px var(--font-sans)", color: "var(--fg-2)", lineHeight: 1.55 }}>{h.opinion}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 总进度 */}
        {progressPct !== undefined && (
          <div style={{ marginTop: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", font: "500 12px var(--font-sans)", color: "var(--fg-3)", marginBottom: 6 }}>
              <span>总进度</span>
              <span style={{ font: "600 13px var(--font-mono)", color: "var(--fg-1)" }}>{pct}%{etaSec ? ` · 约还有 ${etaSec}s` : ""}</span>
            </div>
            <div style={{ height: 8, borderRadius: 99, background: "var(--bg-active)", overflow: "hidden" }}>
              <div style={{ width: pct + "%", height: "100%", borderRadius: 99,
                background: "var(--gradient-brand)", transition: "width 0.4s var(--ease-out)" }} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
