"use client";

/** SVG 决策流 DAG: 任务 → dispatcher → N 部门 → CEO. 纯 SVG, 无外部依赖. */

import type { CSSProperties } from "react";

export type DAGNodeDept = {
  dept: string;
  confidence?: number;
  status?: "ok" | "warn" | "bad";
};

type Props = {
  task?: string;
  depts: DAGNodeDept[];
  ceoLabel?: string;
};

function depTone(d: DAGNodeDept): string {
  if (d.status === "bad" || (d.confidence ?? 1) < 0.5) return "#ff5252";
  if (d.status === "warn" || (d.confidence ?? 1) < 0.7) return "#ffb300";
  return "#66bb6a";
}

const wrap: CSSProperties = {
  padding: "12px 14px", borderRadius: 8,
  background: "var(--bg-subtle)",
  borderWidth: 1, borderStyle: "solid",
  borderColor: "var(--border)",
  overflow: "hidden",
};

export function DecisionFlowDAG({ task, depts, ceoLabel = "CEO 综合" }: Props) {
  if (!depts || depts.length === 0) return null;
  const n = depts.length;
  const W = 720;
  const H = Math.max(180, 70 + n * 28);
  const taskX = 60, taskY = H / 2;
  const dispX = 220, dispY = H / 2;
  const deptX = 410;
  const ceoX = 640, ceoY = H / 2;

  const margin = 30;
  const innerH = H - margin * 2;
  const step = n > 1 ? innerH / (n - 1) : 0;
  const deptYs = depts.map((_, i) => (n === 1 ? H / 2 : margin + step * i));

  return (
    <div style={wrap}>
      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", marginBottom: 6 }}>
        🔀 决策流程图
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} style={{ display: "block" }}>
        <defs>
          <marker id="arrowhead" markerWidth="8" markerHeight="8"
                  refX="7" refY="4" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L8,4 L0,8 z" fill="#888" />
          </marker>
        </defs>

        <line x1={taskX + 50} y1={taskY} x2={dispX - 50} y2={dispY}
              stroke="#888" strokeWidth="1.5" markerEnd="url(#arrowhead)" />

        {deptYs.map((y, i) => (
          <line key={`d2dpt-${i}`}
                x1={dispX + 50} y1={dispY}
                x2={deptX - 50} y2={y}
                stroke="#666" strokeWidth="1.2" markerEnd="url(#arrowhead)" />
        ))}

        {deptYs.map((y, i) => (
          <line key={`dpt2ceo-${i}`}
                x1={deptX + 50} y1={y}
                x2={ceoX - 50} y2={ceoY}
                stroke={depTone(depts[i])} strokeWidth="1.4"
                strokeOpacity="0.75" markerEnd="url(#arrowhead)" />
        ))}

        <rect x={taskX - 50} y={taskY - 18} width="100" height="36"
              rx="6" fill="var(--bg-card)" stroke="var(--info)" strokeWidth="1.5" />
        <text x={taskX} y={taskY + 4} fontSize="11" fill="#f5f5f5"
              textAnchor="middle" fontWeight="600">📝 任务</text>

        <rect x={dispX - 50} y={dispY - 18} width="100" height="36"
              rx="6" fill="var(--bg-card)" stroke="#ce93d8" strokeWidth="1.5" />
        <text x={dispX} y={dispY + 4} fontSize="11" fill="#f5f5f5"
              textAnchor="middle" fontWeight="600">🚦 蜂枢</text>

        {depts.map((d, i) => {
          const tone = depTone(d);
          return (
            <g key={`dpt-${i}`}>
              <rect x={deptX - 50} y={deptYs[i] - 12} width="100" height="24"
                    rx="5" fill="var(--bg-card)" stroke={tone} strokeWidth="1.3" />
              <text x={deptX} y={deptYs[i] + 4} fontSize="10" fill="#f5f5f5"
                    textAnchor="middle" fontWeight="500">{d.dept.length > 14 ? d.dept.slice(0, 13) + "…" : d.dept}</text>
              {typeof d.confidence === "number" && (
                <text x={deptX + 52} y={deptYs[i] + 3} fontSize="9"
                      fill={tone} fontWeight="700">{(d.confidence).toFixed(2)}</text>
              )}
            </g>
          );
        })}

        <rect x={ceoX - 50} y={ceoY - 18} width="100" height="36"
              rx="6" fill="var(--bg-card)" stroke="var(--accent)" strokeWidth="2" />
        <text x={ceoX} y={ceoY + 4} fontSize="11" fill="var(--accent)"
              textAnchor="middle" fontWeight="700">🎯 {ceoLabel}</text>
      </svg>
      {task && (
        <div style={{
          marginTop: 4, fontSize: 10, color: "var(--text-dim)",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          原任务: {task}
        </div>
      )}
    </div>
  );
}
