"use client";

import type { CSSProperties } from "react";
import { PersonaCard, type Persona } from "./PersonaCard";

export type Dept = {
  dept_id: string;
  label: string;
  head: Persona;
  staff: Persona[];
};

/** v6-S8 主管近况统计 */
export type DeptStats = {
  recent_confidence?: number[];
  recent_dissent?: number[];
  decisions_count?: number;
  last_seen?: string;
};

type Props = {
  dept: Dept;
  busy?: boolean;
  stats?: DeptStats;
  teamGeneratedAt?: number;
  onRegenDept: (deptId: string) => void;
  onRegenPersona: (deptId: string, personaId: string) => void;
  onEditPrompt: (deptId: string, persona: Persona) => void;
};

const wrap: CSSProperties = {
  padding: 12,
  borderRadius: 10,
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--border)",
  background: "rgba(255,255,255,0.025)",
  display: "flex",
  flexDirection: "column",
  gap: 10,
};

const header: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  fontWeight: 600,
  fontSize: 14,
};

const btnRegenDept: CSSProperties = {
  padding: "4px 10px",
  fontSize: 12,
  borderRadius: 6,
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "rgba(255,193,7,0.4)",
  background: "rgba(255,193,7,0.08)",
  color: "inherit",
  cursor: "pointer",
};

const staffGrid: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
  gap: 8,
};

function MiniSpark({ values, color }: { values: number[]; color: string }) {
  if (values.length === 0) return null;
  const max = Math.max(1, ...values);
  return (
    <svg width={values.length * 6} height={14} style={{ verticalAlign: "middle" }}>
      {values.map((v, i) => {
        const h = Math.max(2, (v / max) * 12);
        return <rect key={i} x={i * 6} y={14 - h} width={4} height={h} fill={color} />;
      })}
    </svg>
  );
}

function StatChip({ stats, teamGeneratedAt }: { stats?: DeptStats; teamGeneratedAt?: number }) {
  if (!stats || (stats.decisions_count ?? 0) === 0) {
    return (
      <span style={{ fontSize: 10, color: "var(--text-faint)", marginLeft: 8 }}>
        近况: 暂无数据 (跑几次决策后会显示)
      </span>
    );
  }
  const cs = stats.recent_confidence ?? [];
  const ds = stats.recent_dissent ?? [];
  const avgC = cs.length > 0 ? cs.reduce((a, b) => a + b, 0) / cs.length : 0;
  const tone = avgC >= 0.7 ? "#4caf50" : avgC >= 0.5 ? "var(--accent)" : "#f44336";
  return (
    <span style={{
      fontSize: 10, color: "var(--text-dim)", marginLeft: 8,
      display: "inline-flex", alignItems: "center", gap: 6,
    }} title={`最近 ${cs.length} 次自信度 / 分歧度 · 共参与 ${stats.decisions_count} 次决策`}>
      <span style={{ color: tone }}>● {(avgC * 100).toFixed(0)}%</span>
      <MiniSpark values={cs.map(c => c * 100)} color="var(--info)" />
      <span style={{ opacity: 0.6 }}>分歧</span>
      <MiniSpark values={ds.map(d => d * 100)} color="#ffb300" />
      <span style={{ opacity: 0.6 }}>· {stats.decisions_count} 次</span>
      {teamGeneratedAt && (
        <span style={{ opacity: 0.6 }}>
          · 上次重生 {new Date(teamGeneratedAt * 1000).toLocaleDateString()}
        </span>
      )}
    </span>
  );
}

export function DeptCard({ dept, busy, stats, teamGeneratedAt, onRegenDept, onRegenPersona, onEditPrompt }: Props) {
  return (
    <div style={wrap}>
      <div style={header}>
        <span>
          🏥 {dept.label}
          <StatChip stats={stats} teamGeneratedAt={teamGeneratedAt} />
        </span>
        <button type="button" style={btnRegenDept} disabled={busy}
                onClick={() => onRegenDept(dept.dept_id)}>
          🔄 重生整个部门
        </button>
      </div>
      <PersonaCard
        persona={dept.head}
        role="head"
        busy={busy}
        onRegen={(pid) => onRegenPersona(dept.dept_id, pid)}
        onEditPrompt={(p) => onEditPrompt(dept.dept_id, p)}
      />
      {dept.staff?.length > 0 && (
        <div>
          <div style={{ fontSize: 11, opacity: 0.55, marginBottom: 4 }}>
            ↓ 职员 ({dept.staff.length} 人, 本地模型)
          </div>
          <div style={staffGrid}>
            {dept.staff.map((s) => (
              <PersonaCard
                key={s.persona_id}
                persona={s}
                role="staff"
                busy={busy}
                onRegen={(pid) => onRegenPersona(dept.dept_id, pid)}
                onEditPrompt={(p) => onEditPrompt(dept.dept_id, p)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
